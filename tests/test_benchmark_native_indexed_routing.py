from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import hashlib
import json
import unittest
from unittest.mock import patch

from scripts import benchmark_native_indexed_routing as study
from pokerlab import native_exact_four_street as native


class NativeIndexedRoutingStudyTests(unittest.TestCase):
    def test_fixed_schedule_is_old18_mapped_plus_two_shadow_checks(self):
        self.assertEqual(len(study.SCHEDULE), 20)
        mapped = study.SCHEDULE[:18]
        self.assertEqual(tuple(row[0] for row in mapped),
            tuple(row[0] for row in study._MAPPED_SCHEDULE))
        self.assertEqual(sum(row[1] == "full-history" for row in mapped), 9)
        self.assertEqual(sum(row[1] == "indexed" for row in mapped), 9)
        self.assertEqual(study.SCHEDULE[-2:], (
            ("original-22-t10", "shadow", "shadow", False),
            ("mixed-stabilizer", "shadow", "shadow", False)))
        self.assertEqual(sum(row[3] for row in study.SCHEDULE), 2)
        self.assertEqual([row for row in study.SCHEDULE if row[0].endswith("qreject")], [
            ("original-22-qreject", "full-history", 0, False),
            ("original-22-qreject", "indexed", 0, False)])

    def test_first_child_failure_retains_raw_streams_manifest_and_does_not_retry(self):
        source = {"commit": "fixture", "status": "", "sha256": {}}
        failed = SimpleNamespace(returncode=17, stdout=b"first raw stdout", stderr=b"first raw stderr")
        with TemporaryDirectory() as directory, patch.object(study, "_identity", return_value=source), \
                patch.object(study, "executable_identity", return_value={"build": "fixture"}), \
                patch.object(study, "_run_child", return_value=failed) as calls:
            output = Path(directory) / "study"
            result = study.run(output, Path(directory) / "native-exact-four-street-train.exe")
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(calls.call_count, 1)
            self.assertEqual((output / "original-22-t10-full-history-0.stdout.bin").read_bytes(), b"first raw stdout")
            self.assertEqual((output / "original-22-t10-full-history-0.stderr.bin").read_bytes(), b"first raw stderr")
            self.assertTrue((output / "original-22-t10-full-history-0-failure.json").is_file())
            self.assertTrue((output / "manifest.json").is_file())

    def test_child_forwards_explicit_routing_to_one_native_solve(self):
        observed = {}
        def solve(request, **kwargs):
            observed["request"] = request
            observed["kwargs"] = kwargs
            return {"fake": "complete"}
        with patch("pokerlab.exact_selected_solver.solve_four_street_exact_selected", side_effect=solve):
            raw = study.child("original-22-t10", "indexed", 0, False, Path("native.exe"))
        self.assertEqual(observed["kwargs"]["native_routing"], "indexed")
        self.assertEqual(observed["kwargs"]["native_executable"], Path("native.exe"))
        self.assertEqual(observed["kwargs"]["training_reduction"], "suit-equivariant")
        self.assertEqual(raw["payload"], {"fake": "complete"})
        self.assertEqual(raw["failure"], None)
        self.assertEqual(raw["counts"]["native_invoke"], 0)

    def test_t1000_pretraining_rejection_requires_resource_error_and_no_launch(self):
        entry = next(item for item in study.SCHEDULE if item[0].endswith("qreject"))
        raw = {"case": entry[0], "routing": entry[1], "sample": entry[2], "traced": entry[3],
            "runtime": study._runtime(), "iterations": 1000, "seconds": 1.0,
            "process_peak_bytes": 1, "python_allocation_peak_bytes": None,
            "counts": {"python_trainer": 0, "native_invoke": 0, "python_rank": 0,
                "rank_before_native": None, "pair": 0, "world": 0, "legacy": 0},
            "failure": {"type": "ValueError", "message": "whole-request resource limit exceeded"},
            "payload": None, "native_streams": []}
        study.validate(raw, entry)
        raw["failure"]["message"] = "argument parsing failed"
        with self.assertRaises(ValueError):
            study.validate(raw, entry)

    def test_forbidden_path_counter_fails_even_if_payload_is_present(self):
        entry = study.SCHEDULE[0]
        raw = {"case": entry[0], "routing": entry[1], "sample": entry[2], "traced": entry[3],
            "runtime": study._runtime(), "iterations": 10, "seconds": 1.0,
            "process_peak_bytes": 1, "python_allocation_peak_bytes": None,
            "counts": {"python_trainer": 0, "native_invoke": 1, "python_rank": 0,
                "rank_before_native": 0, "pair": 1, "world": 0, "legacy": 0},
            "failure": None, "payload": {}, "native_streams": [{}]}
        with self.assertRaises(ValueError):
            study.validate(raw, entry)

    def test_successful_native_run_allows_python_diagnostics_only_after_launch(self):
        entry = study.SCHEDULE[0]
        raw = {"case": entry[0], "routing": entry[1], "sample": entry[2], "traced": entry[3],
            "runtime": study._runtime(), "iterations": 10, "seconds": 1.0,
            "process_peak_bytes": 1, "python_allocation_peak_bytes": None,
            "counts": {"python_trainer": 0, "native_invoke": 1, "python_rank": 1,
                "rank_before_native": 0, "pair": 0, "world": 0, "legacy": 0},
            "failure": None, "payload": {}, "native_streams": [{}]}
        encoded = json.dumps(raw["payload"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        raw["payload_sha256"], raw["payload_bytes"] = hashlib.sha256(encoded).hexdigest(), len(encoded)
        with self.assertRaisesRegex(ValueError, "backend, law, or routing marker"):
            study.validate(raw, entry)
        raw["counts"]["rank_before_native"] = 1
        with self.assertRaisesRegex(ValueError, "Forbidden or malformed"):
            study.validate(raw, entry)

    def test_paired_metrics_require_identical_binary64_bits(self):
        left = {name: 1.0 for name in study.METRICS}
        right = dict(left)
        right[study.METRICS[0]] = 1.0 + 2.0 ** -52
        left["native_routing"], right["native_routing"] = "full-history", "indexed"
        with patch.object(study, "_policy_metric_certificate_identity", return_value={"identity": True}):
            with self.assertRaisesRegex(ValueError, "binary64 values differ"):
                study._verify_pair(left, right, {}, {})


if __name__ == "__main__":
    unittest.main()
