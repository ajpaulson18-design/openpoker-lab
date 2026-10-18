import copy
import hashlib
import json
from pathlib import Path
import unittest

from scripts import preflop_sequence_pure_response as oracle


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATH = ROOT / "tests" / "fixtures" / "preflop-weighted-sequence-candidate-v1.json"
SPEC_PATH = ROOT / "benchmarks" / "preflop-weighted-sequence-v1.json"


class PreflopSequencePureResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.witness = oracle._load_json(CANDIDATE_PATH)
        cls.result = oracle.public_pure_response(cls.witness)

    def test_exact_hidden_hand_profile_and_legal_pure_responses(self):
        result = self.result
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["terminal_history_count"], 12)
        self.assertEqual(result["information_set_row_count"], 14)
        self.assertEqual(result["pure_response_policies_per_hand"], {"sb": 20, "bb": 24})
        self.assertEqual(len(result["pair_priors"]), 3)
        self.assertEqual(
            [row["prior_fraction"] for row in result["pair_priors"]],
            ["8/13", "1/13", "4/13"],
        )
        self.assertEqual(sum(row["boards"] for row in result["pair_priors"]), 5_136_912)
        self.assertTrue(all(row["wins"] + row["ties"] + row["losses"] == row["boards"]
                            for row in result["pair_priors"]))

        # The independent terminal evaluator supplies both values before the
        # own-hand pure-policy maxima/minima are compared with the candidate.
        self.assertEqual(result["profile_value_fraction"],
                         result["sb_best_response_value_fraction"])
        self.assertEqual(result["profile_value_fraction"],
                         result["bb_best_response_value_fraction_sb_perspective"])
        self.assertEqual(result["profile_value_fraction"],
                         result["bb_minimum_sb_value_fraction"])
        self.assertEqual(result["sb_best_response_gain_fraction"], "0")
        self.assertEqual(result["bb_best_response_gain_fraction"], "0")
        self.assertEqual(result["nash_conv_fraction"], "0")
        self.assertTrue(result["legal_equilibrium_verified"])
        self.assertTrue(result["candidate_claimed_value_matches"])
        self.assertTrue(result["candidate_claimed_nash_conv_matches"])
        self.assertEqual([row["pure_policies_enumerated"] for row in result["sb_by_hand"]],
                         [20, 20])
        self.assertEqual([row["pure_policies_enumerated"] for row in result["bb_by_hand"]],
                         [24, 24])

    def test_clairvoyant_control_is_separate_and_weakly_stronger(self):
        control = self.result["illegal_clairvoyant_control"]
        self.assertTrue(control["sb_value_weakly_at_least_legal"])
        self.assertTrue(control["bb_value_weakly_at_most_legal"])
        self.assertEqual(len(control["sb_pair_values"]), 3)
        self.assertEqual(len(control["bb_pair_values"]), 3)
        self.assertIn("Illegal", control["scope"])

    def test_candidate_policy_tampering_and_spec_drift_are_rejected(self):
        changed = copy.deepcopy(self.witness)
        changed["policies"][0]["probabilities"][-1] = "0"
        with self.assertRaisesRegex(ValueError, "self-checksum"):
            oracle._candidate_policies(changed, {
                (row["sb_hand"], row["bb_hand"]): oracle._fraction(row["prior_fraction"], "prior")
                for row in self.witness["pair_priors"]
            })

        spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
        spec["fixture"]["config"]["starting_stack"][0] += 1
        with self.assertRaisesRegex(ValueError, "specification changed"):
            oracle._validate_spec(spec)

    def test_resigned_legal_policy_change_reaches_response_oracle(self):
        changed = copy.deepcopy(self.witness)
        root_row = next(row for row in changed["policies"]
                        if row["player"] == "sb" and row["history"] == [])
        root_row["probabilities"] = ["1", "0", "0", "0", "0"]
        unsigned = dict(changed)
        unsigned.pop("artifact_sha256")
        changed["artifact_sha256"] = hashlib.sha256(
            oracle._canonical_bytes(unsigned)).hexdigest()

        result = oracle.public_pure_response(changed)
        self.assertEqual(result["candidate_artifact_sha256"], changed["artifact_sha256"])
        self.assertNotEqual(result["candidate_artifact_sha256"],
                            result["expected_original_candidate_sha256"])
        self.assertGreater(oracle._fraction(result["nash_conv_fraction"], "NashConv"), 0)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["candidate_claimed_value_matches"])
        self.assertFalse(result["candidate_claimed_nash_conv_matches"])

    def test_untrusted_python_object_envelope_is_bounded_before_encoding(self):
        too_many = {str(index): None for index in range(oracle.MAX_JSON_OBJECT_ITEMS + 1)}
        with self.assertRaisesRegex(ValueError, "object exceeds its item limit"):
            oracle._validate_json_envelope(too_many)
        too_deep = None
        for _ in range(oracle.MAX_JSON_DEPTH + 1):
            too_deep = [too_deep]
        with self.assertRaisesRegex(ValueError, "structural limits"):
            oracle._validate_json_envelope(too_deep)

    def test_terminal_partition_and_fold_and_refunded_shove_payoffs(self):
        fixture, chance = oracle._validate_spec(oracle._load_json(SPEC_PATH))
        priors = oracle._pair_priors(fixture)
        physical_rows = oracle._load_physical_rows(chance, priors)
        uniform = {}
        for key, actions in oracle._expected_policy_keys(priors).items():
            uniform[key] = {action: oracle.Fraction(1, len(actions)) for action in actions}

        for pair in priors:
            terminal_mass = sum(
                (oracle._terminal_probability(uniform, pair[0], pair[1], path)
                 for _, path, _, _ in oracle._TERMINALS),
                oracle.Fraction(0),
            )
            self.assertEqual(terminal_mass, 1)

        fold_overrides = {
            (0, hand, ()): "fold"
            for hand in {pair[0] for pair in priors}
        }
        folded_value = sum(
            (prior * oracle._pair_value(uniform, physical_rows[pair], pair, fold_overrides)
             for pair, prior in priors.items()),
            oracle.Fraction(0),
        )
        self.assertEqual(folded_value, oracle.Fraction(-1, 2))

        shove_call_overrides = {}
        for pair in priors:
            shove_call_overrides[(0, pair[0], ())] = "all_in@4"
            shove_call_overrides[(1, pair[1], ("all_in@4",))] = "call"
        refunded_shove_value = sum(
            (prior * oracle._pair_value(
                uniform, physical_rows[pair], pair, shove_call_overrides)
             for pair, prior in priors.items()),
            oracle.Fraction(0),
        )
        expected_matched_three = 3 * sum(
            (prior * physical_rows[pair]["showdown_mean"]
             for pair, prior in priors.items()),
            oracle.Fraction(0),
        )
        self.assertEqual(refunded_shove_value, expected_matched_three)


if __name__ == "__main__":
    unittest.main()
