"""Independent replay must reject invalid evidence in every Python mode."""
from copy import deepcopy
from fractions import Fraction
import subprocess
import sys
import unittest

from scripts.preflop_validation import compare_result, physical_worlds, replay_policy


def _fixture():
    return {"strategy": [{"player": "sb", "hand": "AdAs", "street": "preflop",
                          "revealed_board": [], "history": [],
                          "actions": [{"name": "fold", "amount": 0, "raise_to": 0,
                                       "history_key": "fold", "probability": .5},
                                      {"name": "call", "amount": .5, "raise_to": 1,
                                       "history_key": "call", "probability": .5}]}]}


def _replay(candidate):
    return replay_policy(candidate, "AsAd", "KsKd",
                         config={"starting_stack": [2, 1], "max_raises": 0},
                         runouts=["2c3c4d7h8h", "Kc2d3h7s8c"])


class PreflopReplaySafetyTests(unittest.TestCase):
    def test_valid_control_and_hidden_future_rejection(self):
        good = _fixture()
        self.assertEqual(_replay(good)["value_sb"], -.25)
        bad = deepcopy(good)
        bad["strategy"][0]["revealed_board"] = ["Kc"]
        with self.assertRaisesRegex(AssertionError, "leak"):
            _replay(bad)

    def test_duplicate_missing_and_unreachable_information_sets(self):
        duplicated = _fixture()
        duplicated["strategy"].append(deepcopy(duplicated["strategy"][0]))
        with self.assertRaisesRegex(AssertionError, "Duplicate"):
            _replay(duplicated)
        with self.assertRaisesRegex(AssertionError, "Missing"):
            _replay({"strategy": []})
        extra = _fixture()
        off_tree = deepcopy(extra["strategy"][0])
        off_tree["history"] = ["nonexistent"]
        extra["strategy"].append(off_tree)
        with self.assertRaisesRegex(AssertionError, "Unreachable"):
            _replay(extra)

    def test_wrong_legal_action_money_token_and_street_rejected(self):
        for field, value in (("name", "check"), ("amount", .75),
                             ("raise_to", 1.5), ("history_key", "call@future")):
            bad = _fixture()
            bad["strategy"][0]["actions"][1][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                _replay(bad)
        bad = _fixture()
        bad["strategy"][0]["street"] = "river"
        with self.assertRaises(AssertionError):
            _replay(bad)
        bad = _fixture()
        bad["strategy"][0]["actions"].pop()
        with self.assertRaises(AssertionError):
            _replay(bad)

    def test_negative_nonfinite_and_unnormalized_probabilities_rejected(self):
        for probability in (-.5, float("nan"), float("inf"), .9):
            bad = _fixture()
            bad["strategy"][0]["actions"][0]["probability"] = probability
            with self.subTest(probability=probability), self.assertRaises(AssertionError):
                _replay(bad)

    def test_metrics_and_tolerance_cannot_hide_nonfinite_or_wrong_values(self):
        good = {field: 0.0 for field in ("value_sb", "value_bb", "sb_best_response_value",
                                        "bb_best_response_value", "nash_conv")}
        good["worlds"] = 1
        self.assertEqual(max(compare_result(good, good).values()), 0)
        for field in ("value_sb", "value_bb", "sb_best_response_value",
                      "bb_best_response_value", "nash_conv", "worlds"):
            bad = dict(good)
            bad[field] = 2
            with self.subTest(field=field), self.assertRaises(AssertionError):
                compare_result(bad, good)
        for value in (float("nan"), float("inf"), True):
            for side in (0, 1):
                bad = dict(good, nash_conv=value)
                with self.subTest(value=value, side=side), self.assertRaises(AssertionError):
                    compare_result(bad, good) if side == 0 else compare_result(good, bad)
        for tolerance in (-1, float("nan"), float("inf"), True):
            with self.subTest(tolerance=tolerance), self.assertRaises(AssertionError):
                compare_result(good, good, tolerance)

    def test_independent_chance_law_normalizes_exact_products_before_conversion(self):
        for second, bb_weight in ((1e-161, 1e-156), (5e-161, 2e-156)):
            worlds = physical_worlds(f"AsAh:1e-160,QsQh:{second}",
                                     f"KsKh:{bb_weight}", ["2c3d4h5s6c"])
            first_q, second_q = map(Fraction.from_float, (1e-160, second))
            expected = [float(first_q / (first_q + second_q)),
                        float(second_q / (first_q + second_q))]
            self.assertEqual([row[2] for row in worlds], expected)
            self.assertTrue(all(row[2] > 0 for row in worlds))


class OptimizedReplaySubprocessTests(unittest.TestCase):
    def test_safety_controls_execute_under_optimized_python(self):
        result = subprocess.run(
            [sys.executable, "-B", "-O", "-m", "unittest",
             "tests.test_preflop_replay_safety.PreflopReplaySafetyTests"],
            capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
