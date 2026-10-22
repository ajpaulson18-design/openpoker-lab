from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import profile_flop_class_phases as profile
from scripts import verify_flop_class_compact_cfrplus_publication as compact_publication


class PhaseProfileDraftTests(unittest.TestCase):
    def test_real_protocol_admission_and_pilot_semantics_with_mocked_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, pilot = compact_publication._read(compact_publication.PUBLICATION)
            raw = profile.runner._canonical(pilot, newline=True)
            clean = {"revision": "a" * 40, "status": "", "source_lf_sha256": {}}
            metadata = {"raw_sha256": hashlib.sha256(raw).hexdigest(),
                        "artifact_sha256": pilot["artifact_sha256"],
                        "quality_target_met": pilot["quality_target_met"],
                        "allocation_trace": False, "wall_seconds": 1.0,
                        "process_seconds": 1.0, "python_traced_peak_bytes": None,
                        "started_at_utc": "2026-10-22T12:00:00+00:00",
                        "finished_at_utc": "2026-10-22T12:00:01+00:00",
                        "runtime": {"python": "test", "implementation": "test",
                                    "platform": "test"}}
            with patch.object(profile.runner, "_source_snapshot", return_value=clean), \
                 patch.object(profile.measurement, "measure_call", return_value=(raw, metadata)) as measured:
                result = profile.run(Path(tmp) / "profile")
            measured.assert_called_once()
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["admission"]["requested_iterations"], 560)
            self.assertEqual(result["protocol"]["event_limit"], profile.MAX_EVENTS)
            self.assertEqual(result["measurement"]["raw_sha256"], hashlib.sha256(raw).hexdigest())

    def test_nested_phase_events_and_restoration_on_success_and_error(self):
        owner = SimpleNamespace()
        owner.inner = lambda: "ok"
        owner.outer = lambda: owner.inner()
        old_inner, old_outer = owner.inner, owner.outer
        events = []
        restore = profile._instrument((
            ("outer", owner, "outer"), ("inner", owner, "inner")), events)
        self.assertEqual(owner.outer(), "ok")
        restore()
        self.assertIs(owner.outer, old_outer)
        self.assertIs(owner.inner, old_inner)
        self.assertEqual([event["parent_event_id"] for event in events], [None, 1])

        owner.inner = Mock(side_effect=RuntimeError("phase failure"))
        old_inner = owner.inner
        events = []
        restore = profile._instrument((
            ("outer", owner, "outer"), ("inner", owner, "inner")), events)
        with self.assertRaisesRegex(RuntimeError, "phase failure"):
            owner.outer()
        restore()
        self.assertIs(owner.inner, old_inner)
        self.assertEqual(events[-1]["status"], "error")

    def test_source_drift_before_call_rejects_without_solver_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean = {"revision": "a" * 40, "status": "", "source_lf_sha256": {}}
            changed = {**clean, "revision": "b" * 40}
            solve = Mock()
            with patch.object(profile, "_protocol", return_value={
                    "instrumentation_overhead": "synthetic"}), \
                 patch.object(profile, "_snapshot", side_effect=[clean, changed, changed]), \
                 patch.object(profile.runner, "_pilot_expectations", return_value={}), \
                 patch.object(profile.compact, "solve_fixed_compact", solve):
                result = profile.run(Path(tmp) / "profile")
            solve.assert_not_called()
            self.assertEqual(result["status"], "error")
            self.assertIn("changed before", result["error"])
            self.assertTrue(any("Source snapshot changed before profiled call" in entry["error"]
                                for entry in result["errors"]))

    def test_dirty_source_rejects_before_solver(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean = {"revision": "a" * 40, "status": "", "source_lf_sha256": {}}
            solve = Mock()
            with patch.object(profile, "_protocol", return_value={
                    "instrumentation_overhead": "synthetic"}), \
                 patch.object(profile, "_snapshot", side_effect=[
                     ValueError("Measurement requires committed clean source"), clean]), \
                 patch.object(profile.runner, "_pilot_expectations", return_value={}), \
                 patch.object(profile.compact, "solve_fixed_compact", solve):
                result = profile.run(Path(tmp) / "profile")
            solve.assert_not_called()
            self.assertEqual(result["status"], "error")
            self.assertTrue(result["errors"])

    def test_call_failure_is_retained_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean = {"revision": "a" * 40, "status": "", "source_lf_sha256": {}}
            call_error = RuntimeError("synthetic trainer failure")
            measure = Mock(side_effect=call_error)
            with patch.object(profile, "_protocol", return_value={
                    "instrumentation_overhead": "synthetic"}), \
                 patch.object(profile, "_snapshot", return_value=clean), \
                 patch.object(profile.runner, "_pilot_expectations", return_value={}), \
                 patch.object(profile.measurement, "measure_call", measure):
                result = profile.run(Path(tmp) / "profile")
            measure.assert_called_once()
            self.assertEqual(result["status"], "error")
            self.assertIn("synthetic trainer failure", result["traceback"])
            self.assertTrue((Path(tmp) / "profile" / "index.json").is_file())

    def test_gzip_write_failure_is_retained_and_wrappers_are_restored(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean = {"revision": "a" * 40, "status": "", "source_lf_sha256": {}}
            report = {"artifact_sha256": "a" * 64, "quality_target_met": True}
            raw = json.dumps(report, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode() + b"\n"
            original_verify = profile.compact.publication.verify
            path_open = Path.open

            def fail_gzip_open(path, *args, **kwargs):
                if path.name.endswith(".json.gz"):
                    raise OSError("synthetic gzip write failure")
                return path_open(path, *args, **kwargs)

            with patch.object(profile, "_protocol", return_value={
                    "instrumentation_overhead": "synthetic"}), \
                 patch.object(profile, "_snapshot", return_value=clean), \
                 patch.object(profile.runner, "_pilot_expectations", return_value={}), \
                 patch.object(profile.measurement, "measure_call", return_value=(raw, {})), \
                 patch.object(profile.runner, "_validate_raw"), \
                 patch.object(Path, "open", fail_gzip_open):
                result = profile.run(Path(tmp) / "profile")
            self.assertEqual(result["status"], "error")
            self.assertIn("synthetic gzip write failure", result["error"])
            self.assertIs(profile.compact.publication.verify, original_verify)


if __name__ == "__main__":
    unittest.main()
