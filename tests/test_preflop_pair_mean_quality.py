"""Lightweight provenance and guard tests for the 8000-sweep follow-up."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import benchmark_preflop_pair_mean_quality as quality
from scripts.benchmark_native_preflop import checksum

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REQUESTS = (
    ("weighted-three-pairs", "vanilla"),
    ("weighted-three-pairs", "dcfr"),
    ("weighted-short-bb", "vanilla"),
    ("split-four-pairs", "vanilla"),
)


class PreflopPairMeanQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(quality.SPEC.read_text(encoding="utf-8"))

    def test_spec_is_frozen_and_material_changes_reject(self):
        self.assertEqual(checksum(self.spec), quality.SPEC_SHA256)
        self.assertIs(quality.validate_spec(self.spec), self.spec)

        altered = copy.deepcopy(self.spec)
        altered["iterations"] += 1
        with self.assertRaisesRegex(ValueError, "exact frozen pair-mean quality"):
            quality.validate_spec(altered)

        altered = copy.deepcopy(self.spec)
        altered["requests"].pop()
        with self.assertRaisesRegex(ValueError, "exact frozen pair-mean quality"):
            quality.validate_spec(altered)

    def test_pinned_prior_report_identifies_exact_four_two_mode_3000_sweep_misses(self):
        provenance = quality.previous_report(self.spec)
        reference = self.spec["previous_report"]
        self.assertEqual(provenance["path"], reference["path"])
        self.assertEqual(provenance["git_blob_sha1"], reference["git_blob_sha1"])
        self.assertEqual(provenance["artifact_sha256"], reference["artifact_sha256"])
        self.assertIs(provenance["original_final_gates_pass"], False)

        report = json.loads((ROOT / reference["path"]).read_text(encoding="utf-8"))
        self.assertEqual(report["spec_sha256"], self.spec["base_spec_sha256"])
        self.assertTrue(report["source"]["unchanged"])
        self.assertIs(report["all_final_gates_pass"], False)

        actual_requests = set()
        for case in report["cases"]:
            for profile in case["profiles"]:
                if profile["iterations"] != 3000:
                    continue
                checks = profile["modes"]
                misses_both_modes = all(
                    mode in checks
                    and checks[mode]["checks"]
                    and all(not sample["meets_final_quality_gate"]
                            for sample in checks[mode]["checks"])
                    and all(sample["independent_replay"]["nash_conv"]
                            + self.spec["acceptance"]["gate_padding"]
                            > self.spec["acceptance"]["final_nash_conv_chip_limit"]
                            for sample in checks[mode]["checks"])
                    for mode in ("categorical", "pair-mean")
                )
                if misses_both_modes:
                    actual_requests.add((case["id"], profile["algorithm"]))

        self.assertEqual(actual_requests, set(EXPECTED_REQUESTS))
        self.assertEqual(set((item["case"], item["algorithm"])
                             for item in self.spec["requests"]), set(EXPECTED_REQUESTS))

    def test_dirty_source_rejects_before_prior_report_or_case_preparation(self):
        dirty = {"revision": "fixture", "status": [" M pokerlab/example.py"]}
        with patch.object(quality.paired.baseline, "snapshot", return_value=dirty), \
                patch.object(quality, "source_hashes", return_value={"fixture": "stable"}), \
                patch.object(quality, "previous_report",
                             side_effect=AssertionError("prior report must not load")) as previous, \
                patch.object(quality.paired, "prepare_cases",
                             side_effect=AssertionError("case preflight must not run")) as prepare:
            with self.assertRaisesRegex(ValueError, "clean committed source"):
                quality.run(self.spec)
        previous.assert_not_called()
        prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()