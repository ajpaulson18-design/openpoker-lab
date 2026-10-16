"""Regression checks for frozen full-board preflop checkdown evidence."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pokerlab import preflop_full_board_equity as equity
from scripts import benchmark_preflop_checkdown as benchmark

ROOT = Path(__file__).resolve().parents[1]
PINNED_COUNTS = {
    ("AdAs", "KdKs"): (1_410_336, 9_308, 292_660),
    ("QdQs", "AsKh"): (968_267, 7_226, 736_811),
    ("QdQs", "KdKs"): (292_846, 9_336, 1_410_122),
}


class PreflopCheckdownBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(benchmark.SPEC.read_text(encoding="utf-8"))

    def test_fixture_checksum_and_tampering_are_rejected_without_git_history(self):
        self.assertEqual(benchmark.checksum(self.spec), benchmark.SPEC_SHA256)
        self.assertIs(benchmark.validate_spec(self.spec), self.spec)
        altered = copy.deepcopy(self.spec)
        altered["checkpoints"].append(4000)
        with self.assertRaisesRegex(ValueError, "exact frozen full-checkdown fixture"):
            benchmark.validate_spec(altered)
        altered = copy.deepcopy(self.spec)
        altered["case_definitions"][0]["config"]["max_raises"] += 1
        with self.assertRaisesRegex(ValueError, "exact frozen full-checkdown fixture"):
            benchmark.validate_spec(altered)

    def test_case_preparation_reuses_pinned_counts_without_board_enumeration(self):
        provenance = [{"fixture": "synthetic-pinned-loader-stub"}]
        with patch.object(benchmark, "_load_pinned_oracles",
                          return_value=(PINNED_COUNTS, provenance)) as loader:
            with patch.object(equity.PreflopEquityPlan, "build",
                              side_effect=AssertionError("must not enumerate boards")) as build:
                with patch.object(equity, "rank_hand",
                                  side_effect=AssertionError("must not rank")) as rank:
                    with patch.object(equity, "_board_combinations",
                                      side_effect=AssertionError("must not enumerate")) as combinations:
                        prepared, used_provenance = benchmark.prepare_cases(self.spec)
        loader.assert_called_once_with(self.spec)
        build.assert_not_called()
        rank.assert_not_called()
        combinations.assert_not_called()
        self.assertEqual(used_provenance, provenance)
        self.assertEqual([item["case"]["compatible_pairs"] for item in prepared],
                         [1, 3, 3, 4])
        split = prepared[-1]
        self.assertEqual(split["table"].counts[1], PINNED_COUNTS[("QdQs", "AsKh")])
        self.assertEqual(len(split["derivations"]), 1)
        self.assertEqual(split["derivations"][0]["target_pair"], ["QdQs", "AsKc"])
        self.assertEqual(len(split["admissions"]), len(self.spec["checkpoints"]))

    def test_quality_miss_is_reported_and_prevents_final_acceptance(self):
        missed_spec = {
            "checkpoints": [10], "final_repeats": 2, "algorithm": "cfrplus",
            "traced_case": "fixture", "trace_scope": "mocked test",
            "acceptance": {"metric_absolute_tolerance": 1e-10,
                           "gate_padding": 1e-10,
                           "final_nash_conv_chip_limit": 0.005,
                           "final_known_value_error_chip_limit": 0.005},
        }
        prepared_case = {
            "case": {"id": "fixture", "config": {}, "sb_range": "",
                     "bb_range": "", "known_value_sb": 1.0},
            "admissions": [], "counts": [], "derivations": [], "table": None,
        }
        sample_result = {"value_sb": 1.0}
        timing = {"seconds": 0.01, "python_peak_bytes": None,
                  "serialized_bytes_utf8": 12, "payload_sha256": "same-payload"}
        failed_check = {
            "independent_replay": {"nash_conv": 0.02},
            "known_value_error": 0.0,
            "meets_final_quality_gate": False,
        }
        stable_state = {"revision": "fixture-revision", "status": []}
        with patch.object(benchmark, "validate_spec", side_effect=lambda spec: spec), \
                patch.object(benchmark, "snapshot", return_value=stable_state), \
                patch.object(benchmark, "source_hashes", return_value={"fixture": "stable"}), \
                patch.object(benchmark, "prepare_cases", return_value=([prepared_case], [])), \
                patch.object(benchmark, "measure", return_value=(sample_result, timing)), \
                patch.object(benchmark, "assess", return_value=failed_check):
            report = benchmark.run(missed_spec)
        checkpoint = report["cases"][0]["checkpoints"][0]
        self.assertEqual(len(checkpoint["samples"]), 2)
        self.assertEqual(len(checkpoint["checks"]), 2)
        self.assertFalse(checkpoint["checks"][0]["meets_final_quality_gate"])
        self.assertFalse(report["all_final_gates_pass"])
        self.assertEqual(report["errors"], [])
        self.assertTrue(report["source"]["unchanged"])
        self.assertFalse(report["cases"][0]["python_allocation_trace"]["check"][
            "meets_final_quality_gate"])

    def test_assess_applies_padded_final_quality_thresholds(self):
        prepared = {"case": {"id": "known-anchor", "sb_range": "SB",
                             "bb_range": "BB", "config": {},
                             "known_value_sb": 1.0},
                    "counts": []}
        spec = {"acceptance": {"metric_absolute_tolerance": 1e-10,
                               "gate_padding": 1e-10,
                               "final_nash_conv_chip_limit": 0.005,
                               "final_known_value_error_chip_limit": 0.005}}
        independent = {"nash_conv": 0.0049999998, "value_sb": 1.0,
                       "bb_best_response_value": -0.2,
                       "sb_best_response_value": 0.3}
        with patch.object(benchmark, "replay", return_value=independent) as replay:
            accepted = benchmark.assess({"value_sb": 1.0}, prepared, spec)
            replay.assert_called_once()
            self.assertTrue(accepted["meets_final_quality_gate"])
            self.assertEqual(accepted["equilibrium_value_bracket_sb"], [0.2, 0.3])

            independent["nash_conv"] = 0.0049999998
            independent["value_sb"] = 0.99499999995
            rejected = benchmark.assess({"value_sb": 0.99499999995}, prepared, spec)
            self.assertFalse(rejected["meets_final_quality_gate"])
            self.assertGreater(rejected["known_value_error"] + spec["acceptance"]["gate_padding"],
                               spec["acceptance"]["final_known_value_error_chip_limit"])

    def test_dirty_checkout_is_rejected_before_count_preparation(self):
        dirty = {"revision": "fixture-revision", "status": [" M pokerlab/example.py"]}
        with patch.object(benchmark, "snapshot", return_value=dirty):
            with patch.object(benchmark, "source_hashes", return_value={"fixture": "stable"}):
                with patch.object(benchmark, "prepare_cases",
                                  side_effect=AssertionError("preparation started")) as prepare:
                    with self.assertRaisesRegex(ValueError, "clean committed checkout"):
                        benchmark.run(self.spec)
        prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
