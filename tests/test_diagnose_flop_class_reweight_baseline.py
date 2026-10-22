import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import diagnose_flop_class_reweight_baseline as diagnostic
from scripts import profile_flop_class_phases as profiler
from scripts import flop_class_reweight_cfrplus as adapter
from pokerlab import cfr_plus


class BaselineDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.raw = b'{"artifact_sha256":"artifact","quality_target_met":true}\n'
        self.baseline = {"raw_sha256": hashlib.sha256(self.raw).hexdigest(),
                         "artifact_sha256": "artifact", "quality_target_met": True}
        self.snapshot = {"revision": "a" * 40, "status": "",
                         "source_lf_sha256": {f"source-{n}": f"{n:064x}" for n in range(35)}}

    def _success_patches(self, *, snapshots=None, measure=None, train_invocations=1,
                         trigger_phase_error=False):
        if snapshots is None:
            snapshots = lambda: dict(self.snapshot,
                                     source_lf_sha256=dict(self.snapshot["source_lf_sha256"]))
        def solve(case_id, iterations):
            self.assertEqual((case_id, iterations), ("baseline", 560))
            if trigger_phase_error:
                try:
                    adapter.reweighted.validate_model(None)
                except RuntimeError:
                    pass
            for _ in range(train_invocations):
                cfr_plus.train(None)
            return {"synthetic": True}
        def measured(call, *, allocation):
            call()
            return self.raw, {"raw_sha256": self.baseline["raw_sha256"],
                              "artifact_sha256": self.baseline["artifact_sha256"],
                              "quality_target_met": True, "allocation_trace": allocation,
                              "python_traced_peak_bytes": 1 if allocation else None}
        return (
            patch.object(diagnostic, "_snapshot", side_effect=snapshots),
            patch.object(diagnostic, "_authenticate_baseline", return_value=self.baseline),
            patch.object(diagnostic, "_runtime_gate"),
            patch.object(adapter, "solve_reweighted", side_effect=solve),
            patch.object(diagnostic.measurement, "measure_call", side_effect=measure or measured),
            patch.object(cfr_plus, "train", return_value=None),
        )

    def test_real_protocol_and_admission_preflight(self):
        _, spec = diagnostic._protocol()
        requests, total = diagnostic._preflight(spec)
        self.assertEqual(len(requests), 2)
        self.assertEqual([row["total_admitted_work"] for row in requests],
                         [75_107_956, 75_107_956])
        self.assertEqual(total, 150_215_912)
        self.assertEqual(total, spec["preflight"]["total_logical_work"])

    def test_successful_orchestration_uses_real_protocol_and_two_measurement_modes(self):
        contexts = self._success_patches()
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "diagnostic"
            with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4] as measured, contexts[5]:
                result = diagnostic.run(output)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["training_calls"], 2)
            self.assertEqual([call.kwargs["allocation"] for call in measured.call_args_list],
                             [False, True])
            self.assertEqual([row["status"] for row in result["samples"]],
                             ["complete", "complete"])
            self.assertTrue(result["samples"][0]["events"])
            self.assertEqual(result["samples"][1]["events"], [])
            self.assertIsNone(result["samples"][0]["measurement"]["python_traced_peak_bytes"])
            self.assertEqual(result["samples"][1]["measurement"]["python_traced_peak_bytes"], 1)
            self.assertTrue((output / "phase-profile.json.gz").is_file())
            self.assertTrue((output / "python-allocation.json.gz").is_file())

    def test_runtime_mismatch_rejects_before_authentication_or_solver(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(diagnostic, "_snapshot", return_value=self.snapshot), \
                 patch.object(diagnostic.platform, "python_version", return_value="0.0.0"), \
                 patch.object(diagnostic, "_authenticate_baseline") as authenticate, \
                 patch.object(adapter, "solve_reweighted") as solve:
                result = diagnostic.run(Path(temp) / "runtime-reject")
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["samples"], [])
            authenticate.assert_not_called()
            solve.assert_not_called()

    def test_first_error_retains_traceback_and_marks_later_sample_not_run(self):
        def fail_after_call(call, *, allocation):
            call()
            raise RuntimeError("synthetic measurement failure")
        contexts = self._success_patches(measure=fail_after_call)
        with tempfile.TemporaryDirectory() as temp:
            with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], contexts[5]:
                result = diagnostic.run(Path(temp) / "first-error")
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["training_calls"], 1)
            self.assertEqual(len(result["samples"]), 2)
            self.assertEqual([row["status"] for row in result["samples"]], ["error", "not-run"])
            self.assertIn("RuntimeError: synthetic measurement failure",
                          result["samples"][0]["error"]["traceback"])

    def test_zero_or_double_trainer_calls_fail_before_next_sample_and_keep_returned_report(self):
        for invocation_count in (0, 2):
            with self.subTest(invocation_count=invocation_count), tempfile.TemporaryDirectory() as temp:
                contexts = self._success_patches(train_invocations=invocation_count)
                output = Path(temp) / f"call-count-{invocation_count}"
                with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], contexts[5]:
                    result = diagnostic.run(output)
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["training_calls"], invocation_count)
                self.assertEqual([row["status"] for row in result["samples"]],
                                 ["error", "not-run"])
                self.assertTrue((output / "phase-profile.json.gz").is_file())
                sample = result["samples"][0]
                self.assertEqual(sample["training_calls"], invocation_count)
                self.assertIn("exactly once", sample["error"]["message"])

    def test_malformed_allocation_metadata_is_rejected_after_report_persistence(self):
        def malformed(call, *, allocation):
            call()
            return self.raw, {"raw_sha256": self.baseline["raw_sha256"],
                              "artifact_sha256": self.baseline["artifact_sha256"],
                              "quality_target_met": True, "allocation_trace": True,
                              "python_traced_peak_bytes": None}
        contexts = self._success_patches(measure=malformed)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "bad-metadata"
            with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], contexts[5]:
                result = diagnostic.run(output)
            self.assertEqual(result["status"], "error")
            self.assertTrue((output / "phase-profile.json.gz").is_file())
            self.assertIn("allocation metadata", result["samples"][0]["error"]["message"])

    def test_phase_event_error_rejects_even_when_library_returns_matching_report(self):
        def fail_validation(_model):
            raise RuntimeError("captured phase failure")
        contexts = self._success_patches(trigger_phase_error=True)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "phase-error"
            with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], contexts[5], \
                 patch.object(adapter.reweighted, "validate_model", side_effect=fail_validation):
                result = diagnostic.run(output)
            self.assertEqual(result["status"], "error")
            self.assertTrue((output / "phase-profile.json.gz").is_file())
            self.assertTrue(any(row["phase"] == "weighted.validate_model" and
                                row["status"] == "error"
                                for row in result["samples"][0]["events"]))
            self.assertEqual(result["samples"][1]["status"], "not-run")

    def test_policy_parity_failure_is_saved_before_rejection(self):
        bad_raw = b'{"different":true}\n'
        def mismatch(call, *, allocation):
            call()
            return bad_raw, {"raw_sha256": hashlib.sha256(bad_raw).hexdigest(),
                             "artifact_sha256": "wrong", "quality_target_met": True,
                             "allocation_trace": allocation,
                             "python_traced_peak_bytes": 1 if allocation else None}
        contexts = self._success_patches(measure=mismatch)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "parity-failure"
            with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], contexts[5]:
                result = diagnostic.run(output)
            self.assertEqual(result["status"], "error")
            self.assertTrue((output / "phase-profile.json.gz").is_file())
            sample = result["samples"][0]
            self.assertEqual(sample["status"], "error")
            self.assertFalse(sample["report_matches_pilot"])
            self.assertEqual(gzip.decompress((output / "phase-profile.json.gz").read_bytes()), bad_raw)

    def test_source_drift_stops_second_call(self):
        changed = dict(self.snapshot, source_lf_sha256=dict(self.snapshot["source_lf_sha256"]))
        changed["source_lf_sha256"]["changed"] = "f" * 64
        states = [self.snapshot, self.snapshot, self.snapshot, changed, changed]
        def snapshots():
            return states.pop(0) if states else changed
        contexts = self._success_patches(snapshots=snapshots)
        with tempfile.TemporaryDirectory() as temp:
            with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], contexts[5]:
                result = diagnostic.run(Path(temp) / "source-drift")
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["training_calls"], 1)
            self.assertEqual([row["status"] for row in result["samples"]], ["error", "not-run"])
            self.assertTrue(any("Source changed" in item.get("message", "")
                                for item in result["errors"]))

    def test_instrumentation_is_nested_and_restored_after_exception(self):
        class Target:
            pass
        target = Target()
        def inner():
            return "ok"
        def outer():
            return target.inner()
        target.inner, target.outer = inner, outer
        originals = [(target, "outer", outer), (target, "inner", inner)]
        events = []
        restore = profiler._instrument((("outer", target, "outer"),
                                        ("inner", target, "inner")), events)
        try:
            self.assertEqual(target.outer(), "ok")
        finally:
            restore()
        self.assertEqual([(row["event_id"], row["parent_event_id"]) for row in events],
                         [(1, None), (2, 1)])
        self.assertTrue(all(row["status"] == "complete" for row in events))
        self.assertTrue(all(getattr(owner, name) is original for owner, name, original in originals))

        def broken():
            raise RuntimeError("instrumented failure")
        target.outer = broken
        restore = profiler._instrument((("outer", target, "outer"),), [])
        with self.assertRaisesRegex(RuntimeError, "instrumented failure"):
            target.outer()
        restore()
        self.assertIs(target.outer, broken)


if __name__ == "__main__":
    unittest.main()
