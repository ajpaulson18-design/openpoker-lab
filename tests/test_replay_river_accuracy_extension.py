"""Focused contract tests for the saved river-accuracy replay gate."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import unittest
import uuid

from scripts.benchmark_turn_river_independent import CONFIG, solve
from scripts.replay_river_accuracy_extension import main, rational_polarised
from scripts.river_analytical import equilibrium, serialized_profile
from scripts.turn_river_validation import replay_policy


ROOT = Path(__file__).resolve().parents[1]
ANCHOR_ID = "river-polarised-bluffcatcher"


class RiverAccuracyReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cases = json.loads(CONFIG.read_text(encoding="utf-8"))["scenarios"]
        cls.case = next(item for item in cases if item["id"] == ANCHOR_ID)
        # Ten CFR+ iterations exercise the actual serializer at negligible cost.
        # In particular, stack-sized wagers serialize as all_in@100.
        cls.result = solve(cls.case, "materialized", "cfrplus", 10)

    def test_exact_rational_anchor_alias_and_known_value_interval(self):
        self.assertTrue(any("all_in@100" in row["history"]
                            for row in self.result["strategy"]))
        with self.assertRaisesRegex(ValueError, "does not match"):
            serialized_profile(self.result)

        witness = rational_polarised(self.result, self.case)

        self.assertIs(witness["known_value_in_interval"], True)
        self.assertEqual(witness["known_game_value_fraction"], "25")
        self.assertLessEqual(Fraction(witness["value_lower_fraction"]), 25)
        self.assertLessEqual(25, Fraction(witness["value_upper_fraction"]))

    def test_rational_anchor_rejects_a_different_fixture(self):
        wrong = deepcopy(self.case)
        wrong["board"] = "2c7d9hJsQc"
        with self.assertRaisesRegex(ValueError, "exact rational anchor"):
            rational_polarised(self.result, wrong)

    def test_hand_built_equilibrium_has_exact_known_value_and_zero_gap(self):
        result = deepcopy(self.result)
        profile, expected_value = equilibrium()
        self.assertEqual(expected_value, Fraction(25))
        for row in result["strategy"]:
            player = 0 if row["player"] == "oop" else 1
            holding = frozenset(row["hand"][i:i + 2] for i in (0, 2))
            if player == 0:
                hand = ({frozenset(("As", "Ah")): "nuts",
                         frozenset(("3c", "4c")): "air"}[holding])
            else:
                hand = {frozenset(("Qs", "Qh")): "catcher"}[holding]
            history = tuple("bet" if token.split("@")[0] == "all_in"
                            else token.split("@")[0] for token in row["history"])
            key = (player, hand, history)
            semantic_names = (("check", "bet") if any(
                action["name"] in ("check", "all_in") for action in row["actions"])
                else ("fold", "call"))
            probabilities = dict(zip(semantic_names, profile[key]))
            for action in row["actions"]:
                name = "bet" if action["name"] == "all_in" else action["name"]
                action["probability"] = float(probabilities[name])

        result.update({
            "value_oop": 25.0,
            "value_ip": -25.0,
            "oop_best_response_value": 25.0,
            "ip_best_response_value": -25.0,
            "oop_best_response_gain": 0.0,
            "ip_best_response_gain": 0.0,
            "nash_conv": 0.0,
            "exploitability": 0.0,
        })
        witness = rational_polarised(result, self.case)

        self.assertEqual(witness["value_oop_fraction"], "25")
        self.assertEqual(witness["oop_br_fraction"], "25")
        self.assertEqual(witness["ip_br_fraction"], "-25")
        self.assertEqual(witness["nash_conv_fraction"], "0")
        self.assertEqual(witness["known_game_value_fraction"], "25")
        self.assertIs(witness["known_value_in_interval"], True)
        self.assertIs(witness["target_met"], True)

    def test_complete_validator_rejects_nonfinite_or_corrupt_probabilities(self):
        for bad_probability in (float("nan"), float("inf"), float("-inf"), -0.01):
            with self.subTest(probability=bad_probability):
                corrupt = deepcopy(self.result)
                corrupt["strategy"][0]["actions"][0]["probability"] = bad_probability
                with self.assertRaises((ValueError, TypeError)):
                    replay_policy(corrupt, self.case["oop"], self.case["ip"],
                                  board=self.case["board"], config=self.case["config"])

    def test_saved_policy_byte_hash_tampering_is_rejected(self):
        temp_root = ROOT / "tests" / f".tmp-river-replay-{uuid.uuid4().hex}"
        policies_root = temp_root / "policies"
        policies_root.mkdir(parents=True)
        report_path = temp_root / "report.json"
        output_path = temp_root / "output.json"
        policy_name = "synthetic-anchor.json"
        policy_path = policies_root / policy_name
        payload = (json.dumps(self.result, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        report = {
            "fixtures": [self.case],
            "results": [{
                "scenario": self.case["id"], "backend": "materialized", "iterations": 10,
                "policy_file": policy_name,
                "policy_sha256": hashlib.sha256(payload).hexdigest(),
            }],
        }
        try:
            policy_path.write_bytes(payload + b" ")
            report_path.write_text(json.dumps(report), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "byte hash"):
                main(["--report", str(report_path), "--policies-dir", str(policies_root),
                      "--output", str(output_path)])
        finally:
            for path in (policy_path, report_path, output_path):
                path.unlink(missing_ok=True)
            policies_root.rmdir()
            temp_root.rmdir()


if __name__ == "__main__":
    unittest.main()
