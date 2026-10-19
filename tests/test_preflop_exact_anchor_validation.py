"""Bounded regressions for finite-iteration exact-anchor assessment."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import preflop_exact_anchor_validation as anchor


class ExactAnchorValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = anchor.load_reference()

    def replay_result(self, *, value_error=Fraction(1, 1000), nash=Fraction(1, 50)):
        value = Fraction(*self.reference["exact_value_fraction"]) + value_error
        # Allocate the BB gain first for a profile above the anchor, so the
        # exact equilibrium remains in the valid one-sided BR bracket.
        bb_gain = min(value_error, nash)
        sb_gain = nash - bb_gain
        sb_br = value + sb_gain
        bb_br = -value + bb_gain  # BB own utility, not SB-perspective value
        exact = {
            "value_sb": [value.numerator, value.denominator],
            "sb_best_response_value": [sb_br.numerator, sb_br.denominator],
            "bb_best_response_value": [bb_br.numerator, bb_br.denominator],
            "sb_best_response_gain": [sb_gain.numerator, sb_gain.denominator],
            "bb_best_response_gain": [bb_gain.numerator, bb_gain.denominator],
            "nash_conv": [nash.numerator, nash.denominator],
            "exploitability": [(nash / 2).numerator, (nash / 2).denominator],
        }
        return {"exact_fraction_replay": exact}

    def test_loads_and_rechecks_pinned_saved_reference(self):
        reference = self.reference
        self.assertEqual(reference["identity"]["report_sha256"], anchor.REPORT_SHA256)
        self.assertEqual(reference["identity"]["witness_sha256"], anchor.WITNESS_SHA256)
        self.assertEqual(reference["identity"]["report_path"],
                         "benchmarks/results/preflop-weighted-sequence-v1.json")
        self.assertEqual(anchor.REPORT_PATH, anchor.ROOT / reference["identity"]["report_path"])
        self.assertEqual(reference["exact_value_fraction"], [100107990869, 130471452826])
        self.assertEqual(len(reference["counts"]), 3)
        self.assertEqual(reference["verification"]["status"], "passed")
        self.assertEqual(reference["verification"]["nash_conv_fraction"], "0")

    def test_assess_exact_bracket_bb_utility_sign_and_quality_threshold(self):
        replay = self.replay_result()
        with patch.object(anchor.checkdown, "replay", return_value=replay) as mocked:
            assessed = anchor.assess({}, self.reference, target_nash_conv=0.02)
        mocked.assert_called_once()
        args, kwargs = mocked.call_args
        self.assertEqual(args[1:4], (self.reference["fixture"]["sb_range"],
                                     self.reference["fixture"]["bb_range"],
                                     self.reference["fixture"]["config"]))
        self.assertEqual(args[4], self.reference["counts"])
        self.assertEqual(assessed["status"], "passed")
        self.assertTrue(assessed["quality_pass"])
        self.assertTrue(assessed["exact_anchor_contained"])
        self.assertTrue(assessed["profile_error_within_nash_conv"])
        self.assertEqual(assessed["target_nash_conv_fraction"], [1, 50])
        self.assertLess(assessed["bb_best_response_fraction"][0], 0)
        self.assertLess(assessed["lower_bound_sb_fraction"][0],
                        assessed["upper_bound_sb_fraction"][0])

    def test_quality_failure_is_preserved_without_rounding(self):
        replay = self.replay_result(value_error=Fraction(1, 100), nash=Fraction(1, 100))
        with patch.object(anchor.checkdown, "replay", return_value=replay):
            assessed = anchor.assess({}, self.reference, target_nash_conv=0.005)
        self.assertFalse(assessed["quality_pass"])
        self.assertEqual(assessed["nash_conv_fraction"], [1, 100])
        self.assertEqual(assessed["target_nash_conv_fraction"], [1, 200])

    def test_rejects_forged_reference_and_invalid_thresholds(self):
        altered = deepcopy(self.reference)
        altered["counts"][0]["wins"] += 1
        with self.assertRaisesRegex(ValueError, "count rows"):
            anchor.assess({}, altered)

        invalid = [True, float("nan"), float("inf"), -0.1, "0.005"]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                anchor.assess({}, self.reference, target_nash_conv=value)
        for value in [True, float("nan"), float("inf"), -1, 10 ** 10000]:
            with self.subTest(tolerance=value), self.assertRaises(ValueError):
                anchor.assess({}, self.reference, tolerance=value)
        with self.assertRaises(ValueError):
            anchor.assess({}, self.reference, target_nash_conv=10 ** 10000)

    def test_every_returned_reference_field_is_authenticated(self):
        altered = deepcopy(self.reference)
        altered["verification"]["public_states"] += 1
        with self.assertRaisesRegex(ValueError, "not authenticated"):
            anchor.assess({}, altered)

        original_stack = anchor._FIXTURE["config"]["starting_stack"][:]
        try:
            isolated = anchor.load_reference()
            isolated["fixture"]["config"]["starting_stack"][0] = 999
            self.assertEqual(anchor._FIXTURE["config"]["starting_stack"], original_stack)
            with self.assertRaisesRegex(ValueError, "fixture was changed"):
                anchor.assess({}, isolated)
        finally:
            anchor._FIXTURE["config"]["starting_stack"][:] = original_stack

    def test_rejects_report_tampering_even_when_json_remains_valid(self):
        report = json.loads(anchor.REPORT_PATH.read_text(encoding="utf-8"))
        report["status"] = "failed"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum"):
                anchor.load_reference(path)

    def test_rejects_inconsistent_exact_response_metrics(self):
        value = Fraction(*self.reference["exact_value_fraction"])
        bad_bounds = {"exact_fraction_replay": {
            "value_sb": [value.numerator, value.denominator],
            "sb_best_response_value": [0, 1],
            "bb_best_response_value": [0, 1],
            "sb_best_response_gain": [0, 1],
            "bb_best_response_gain": [0, 1],
            "nash_conv": [0, 1], "exploitability": [0, 1],
        }}
        with patch.object(anchor.checkdown, "replay", return_value=bad_bounds):
            with self.assertRaisesRegex(ValueError, "inconsistent best-response gains"):
                anchor.assess({}, self.reference)

        bad_gap = self.replay_result(value_error=Fraction(1, 10), nash=Fraction(1, 100))
        with patch.object(anchor.checkdown, "replay", return_value=bad_gap):
            with self.assertRaisesRegex(ValueError, "outside"):
                anchor.assess({}, self.reference)


if __name__ == "__main__":
    unittest.main()
