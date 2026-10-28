"""Actual fixed-study child contracts and failure-evidence controls."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import benchmark_batched_suit_lookup as study


class BatchedSuitLookupBenchmarkTests(unittest.TestCase):
    def test_schedule_separates_repeats_traces_and_payoff_controls(self):
        self.assertEqual(len(study.SCHEDULE), 12)
        self.assertEqual(study.SCHEDULE[:4], (
            ("original-22-t10", "per-row", 0, False),
            ("original-22-t10", "per-decision", 0, False),
            ("original-22-t10", "per-decision", 1, False),
            ("original-22-t10", "per-row", 1, False)))
        self.assertEqual(sum(row[3] for row in study.SCHEDULE), 2)
        self.assertEqual({row[0] for row in study.SCHEDULE},
            {"original-22-t10", "payoff-varied-t100", "blocker-18"})

    def test_real_blocker_children_and_protected_independent_policy_replay(self):
        values, replay = {}, {}
        for mode in study.MODES:
            raw = study.child("blocker-18", mode, 0, False)
            study.validate(raw, ("blocker-18", mode, 0, False))
            values[mode] = raw["payload"]
            replay[mode] = study._protected_verification(study.case_for("blocker-18"), raw["payload"])
            self.assertTrue(replay[mode]["payload_metrics_within_tolerance"])
        identity = study._policy_metric_certificate_identity(values["per-row"], values["per-decision"],
            replay["per-row"], replay["per-decision"])
        self.assertTrue(identity["policy_bitwise_identical"])
        self.assertEqual(values["per-row"]["worlds"], 18)
        raw["counts"]["pair"] = 1
        with self.assertRaisesRegex(ValueError, "Forbidden"):
            study.validate(raw, ("blocker-18", "per-decision", 0, False))

    def test_first_failed_child_stream_is_retained_without_retry(self):
        with TemporaryDirectory() as folder:
            output = Path(folder) / "study"
            source = {"commit": "test", "status": "", "sha256": {}}
            failed = SimpleNamespace(returncode=1, stdout=b"partial child", stderr=b"failure")
            with patch.object(study, "_identity", return_value=source), \
                 patch.object(study.subprocess, "run", return_value=failed) as calls:
                result = study.run(output)
            self.assertEqual(calls.call_count, 1)
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual((output / "original-22-t10-per-row-0.json").read_bytes(), b"partial child")
            self.assertEqual((output / "original-22-t10-per-row-0.stderr.txt").read_bytes(), b"failure")
            self.assertTrue((output / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
