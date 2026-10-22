import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import benchmark_flop_class_cost as runner
from scripts import flop_class_compact_budget as budget
from scripts import flop_public_classes as proof


def _report(method):
    result = {"schema_version": runner.METHODS[method]["iterations"],
              "quality_target_met": runner.METHODS[method]["quality_target_met"],
              "runtime": {"python": "test-runtime"}, "payload": [1, 2, 3]}
    result["artifact_sha256"] = proof._digest(result)
    return result


def _expectations():
    return {method: runner._semantic_digest(report)
            for method, report in ((method, _report(method)) for method in runner.METHODS)}


def _source():
    return {"revision": "a" * 40, "status": "", "source_lf_sha256": {"file.py": "b" * 64}}


class FlopClassCostRunnerTests(unittest.TestCase):
    def _run_patched(self, directory, *, source_side_effect=None, legacy_side_effect=None):
        events = []
        old_report = _report("class-140")
        new_report = _report("class-560")
        def old_call(*_args):
            events.append("legacy-call")
            return old_report

        def new_call(*_args):
            events.append("compact-call")
            return new_report

        legacy_call = Mock(side_effect=legacy_side_effect if legacy_side_effect is not None else old_call)
        compact_call = Mock(side_effect=new_call)
        source = patch.object(runner, "_source_snapshot",
                              side_effect=source_side_effect or [_source()] * 30)
        preflight = patch.object(runner, "_preflight", side_effect=lambda spec: (
            events.append("preflight") or {"total_named_work": 375724160}))
        pilots = patch.object(runner, "_pilot_expectations", return_value=_expectations())
        old = patch.object(runner.legacy, "solve_fixed", side_effect=legacy_call)
        new = patch.object(runner.compact, "solve_fixed_compact", side_effect=compact_call)
        contexts = [source, preflight, pilots, old, new]
        return contexts, legacy_call, compact_call, events

    def test_preflight_covers_all_eight_calls_before_any_measured_solver(self):
        spec = runner.load_spec()
        legacy_admit = runner.legacy.admit_request
        with patch.object(runner.legacy, "admit_request", wraps=legacy_admit) as legacy_calls:
            forecast = runner._preflight(spec)
        self.assertEqual(forecast["total_named_work"], 375724160)
        self.assertEqual(len(forecast["per_request"]), 8)
        self.assertEqual(legacy_calls.call_count, 4)
        self.assertLessEqual(forecast["total_named_work"], 400000000)

    def test_run_retains_all_rotated_calls_and_outputs_four_exact_reports_per_method(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            contexts, old, new, events = self._run_patched(output)
            with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4]:
                report = runner.run(output, execution_state={"mode": "ordinary-process",
                                                              "system_required": False})
            self.assertEqual(report["status"], "complete")
            self.assertEqual(len(report["samples"]), 8)
            self.assertEqual(events[0], "preflight")
            self.assertEqual(events[1], "legacy-call")
            self.assertEqual(old.call_count, 4)
            self.assertEqual(new.call_count, 4)
            self.assertEqual([(row["kind"], row.get("round"), row["method"])
                              for row in report["samples"]], [
                ("timed", 1, "class-140"), ("timed", 1, "class-560"),
                ("timed", 2, "class-560"), ("timed", 2, "class-140"),
                ("timed", 3, "class-140"), ("timed", 3, "class-560"),
                ("allocation", None, "class-140"), ("allocation", None, "class-560")])
            self.assertEqual(len(list(output.glob("*.json.gz"))), 8)
            self.assertEqual(report["summary"]["class-140"]["timed_rows"], 3)
            self.assertEqual(report["summary"]["class-560"]["timed_rows"], 3)
            self.assertIs(report["summary"]["class-140"]["quality_target_met"], False)
            self.assertIs(report["summary"]["class-560"]["quality_target_met"], True)
            with patch.object(runner, "_source_snapshot", return_value=_source()), \
                 patch.object(runner, "_pilot_expectations", return_value=_expectations()), \
                 patch.object(runner, "_preflight", return_value=report["preflight"]):
                verified = runner.verify_saved(output)
            self.assertEqual(verified["status"], "saved-measurement-verified")
            self.assertEqual(verified["summary"], report["summary"])

    def test_existing_output_directory_is_rejected_before_solver(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "exists"
            output.mkdir()
            call = Mock()
            with patch.object(runner.legacy, "solve_fixed", call):
                with self.assertRaisesRegex(ValueError, "new directory"):
                    runner.run(output)
            call.assert_not_called()

    def test_source_drift_stops_future_calls_and_marks_unrun_inventory(self):
        states = [_source(), _source(), {**_source(), "revision": "c" * 40},
                  {**_source(), "revision": "c" * 40}]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "drift"
            contexts, old, new, _ = self._run_patched(output, source_side_effect=states)
            with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4]:
                report = runner.run(output)
            self.assertEqual(report["status"], "error")
            self.assertEqual(old.call_count + new.call_count, 1)
            self.assertEqual(len(report["samples"]), 8)
            self.assertTrue(any(row.get("status") == "not-run" for row in report["samples"]))

    def test_failed_measurement_retains_traceback_and_is_not_a_median_sample(self):
        failure = RuntimeError("synthetic failure")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "failure"
            contexts, old, new, _ = self._run_patched(output, legacy_side_effect=failure)
            with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4]:
                report = runner.run(output)
            first = report["samples"][0]
            self.assertEqual(report["status"], "error")
            self.assertEqual(first["status"], "error")
            self.assertIn("synthetic failure", first["traceback"])
            self.assertIsNone(report["summary"]["class-140"]["median_wall_seconds"])
            self.assertEqual(new.call_count, 4)

    def test_separate_allocation_rows_do_not_enter_timed_medians(self):
        rows = [
            {"kind": "timed", "method": "class-140", "status": "complete",
             "metadata": {"wall_seconds": value}} for value in (1.0, 3.0, 5.0)
        ]
        rows.append({"kind": "allocation", "method": "class-140", "status": "complete",
                     "metadata": {"wall_seconds": 999.0, "python_traced_peak_bytes": 12345}})
        summary = runner._summary(rows)["class-140"]
        self.assertEqual(summary["median_wall_seconds"], 3.0)
        self.assertEqual(summary["allocation_traced_peak_bytes"], 12345)

    def test_saved_verification_rejects_tampered_gzip_payload_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "valid"
            contexts, _, _, _ = self._run_patched(output)
            with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4]:
                runner.run(output)
            index = json.loads((output / "index.json").read_bytes())
            payload_row = next(row for row in index["samples"] if row["status"] == "complete")
            path = output / payload_row["file"]
            raw = gzip.decompress(path.read_bytes())
            tampered = raw.replace(b'"payload":[1,2,3]', b'"payload":[1,2,4]')
            self.assertNotEqual(raw, tampered)
            path.write_bytes(gzip.compress(tampered, mtime=0))
            with patch.object(runner, "_source_snapshot", return_value=_source()), \
                 patch.object(runner, "_pilot_expectations", return_value=_expectations()), \
                 patch.object(runner, "_preflight", return_value=index["preflight"]):
                with self.assertRaisesRegex(ValueError, "compressed report hash"):
                    runner.verify_saved(output)

    def test_saved_verification_rejects_gzip_header_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "valid"
            contexts, _, _, _ = self._run_patched(output)
            with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4]:
                runner.run(output)
            index = json.loads((output / "index.json").read_bytes())
            row = next(row for row in index["samples"] if row["status"] == "complete")
            path = output / row["file"]
            raw = gzip.decompress(path.read_bytes())
            path.write_bytes(gzip.compress(raw, mtime=1))
            with patch.object(runner, "_source_snapshot", return_value=_source()), \
                 patch.object(runner, "_pilot_expectations", return_value=_expectations()), \
                 patch.object(runner, "_preflight", return_value=index["preflight"]):
                with self.assertRaisesRegex(ValueError, "compressed report hash"):
                    runner.verify_saved(output)

    def test_resigned_index_mutations_fail_saved_audit(self):
        mutations = [
            ("Completed call source snapshot", lambda index, row: row.update(
                source_after_call={**_source(), "revision": "c" * 40})),
            ("helper metadata", lambda index, row: row["metadata"].update(
                artifact_sha256="0" * 64)),
            ("helper metadata", lambda index, row: row["metadata"].update(
                quality_target_met=not row["quality_target_met"])),
            ("aware UTC", lambda index, row: row["metadata"].update(
                started_at_utc="2026-10-21T12:00:00")),
            ("comparison limitation", lambda index, row: index.update(
                method_comparison_limit="changed")),
            ("request types", lambda index, row: row.update(iterations=True)),
        ]
        for expected_message, mutation in mutations:
            with self.subTest(expected_message=expected_message), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "valid"
                contexts, _, _, _ = self._run_patched(output)
                with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4]:
                    runner.run(output)
                index_path = output / "index.json"
                index = json.loads(index_path.read_bytes())
                mutation(index, index["samples"][0])
                unsigned = {key: value for key, value in index.items() if key != "index_sha256"}
                index["index_sha256"] = proof._digest(unsigned)
                index_path.write_bytes(json.dumps(index, sort_keys=True, indent=2,
                                                  allow_nan=False).encode("utf-8") + b"\n")
                with patch.object(runner, "_source_snapshot", return_value=_source()), \
                     patch.object(runner, "_pilot_expectations", return_value=_expectations()), \
                     patch.object(runner, "_preflight", return_value=index["preflight"]):
                    with self.assertRaisesRegex(ValueError, expected_message):
                        runner.verify_saved(output)

    def test_saved_verification_retains_reversed_utc_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "valid"
            contexts, _, _, _ = self._run_patched(output)
            with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4]:
                runner.run(output)
            index_path = output / "index.json"
            index = json.loads(index_path.read_bytes())
            metadata = index["samples"][0]["metadata"]
            metadata["started_at_utc"] = "2026-10-21T12:00:01+00:00"
            metadata["finished_at_utc"] = "2026-10-21T12:00:00+00:00"
            unsigned = {key: value for key, value in index.items() if key != "index_sha256"}
            index["index_sha256"] = proof._digest(unsigned)
            index_path.write_bytes(json.dumps(index, sort_keys=True, indent=2,
                                              allow_nan=False).encode("utf-8") + b"\n")
            with patch.object(runner, "_source_snapshot", return_value=_source()), \
                 patch.object(runner, "_pilot_expectations", return_value=_expectations()), \
                 patch.object(runner, "_preflight", return_value=index["preflight"]):
                self.assertEqual(runner.verify_saved(output)["status"],
                                 "saved-measurement-verified")


if __name__ == "__main__":
    unittest.main()
