"""Focused checks for the bounded weighted preflop sequence-form candidate."""
import hashlib
import json
import unittest
from fractions import Fraction
from unittest.mock import patch

from pokerlab import cards
from scripts import preflop_sequence_equilibrium as candidate
from scripts.preflop_sequence_fixture import (
    ARTIFACTS, EXPECTED_PRIORS, SPEC_SHA256, canonical_sha256,
    load_pinned_fixture,
)


class PreflopSequenceEquilibriumTests(unittest.TestCase):
    def test_fixture_verifies_full_artifacts_and_exact_collision_conditioning(self):
        spec, rows, ranges = load_pinned_fixture()
        self.assertEqual(canonical_sha256(spec), SPEC_SHA256)
        self.assertEqual(len(rows), 3)
        self.assertEqual(tuple((row["sb_hand"], row["bb_hand"]) for row in rows),
                         tuple((row[3], row[4]) for row in ARTIFACTS))
        self.assertEqual(tuple(
            Fraction(row["wins"] + row["ties"] + row["losses"], row["boards"])
            for row in rows), (Fraction(1),) * 3)
        self.assertEqual(EXPECTED_PRIORS, (Fraction(8, 13), Fraction(1, 13), Fraction(4, 13)))
        self.assertEqual(len(ranges[0]), 2)
        self.assertEqual(len(ranges[1]), 2)

    def test_build_censuses_all_hidden_pair_information_before_dense_matrix(self):
        with patch.object(cards, "rank_hand", side_effect=AssertionError("ranking forbidden")), \
                patch.object(cards, "combinations", side_effect=AssertionError("board enumeration forbidden")):
            model = candidate.build_model()
        self.assertEqual(model["node_counts"]["public_states"], 19)
        self.assertEqual(model["node_counts"]["decision_nodes"], 7)
        self.assertEqual(model["node_counts"]["fold_terminals"], 6)
        self.assertEqual(model["node_counts"]["showdown_terminals"], 6)
        self.assertEqual(tuple(map(len, model["infos"])), (6, 8))
        self.assertEqual(tuple(map(len, model["sequences"])), (19, 19))
        self.assertEqual(len(model["A"]), 19)
        self.assertTrue(all(len(row) == 19 for row in model["A"]))
        self.assertEqual([pair["prior"] for pair in model["pairs"]], list(EXPECTED_PRIORS))
        self.assertEqual(sum(model["flow_labels"][0]["player"] == p for p in (0, 1)), 1)
        for row in model["information_sets"]:
            self.assertEqual(set(row), {"player", "hand", "history", "parent_sequence",
                                        "action_tokens", "child_sequences"})

    def test_exact_lp_returns_saddle_value_and_fraction_behavioral_rows(self):
        witness = candidate.solve_model(candidate.build_model())
        self.assertEqual(witness["status"], "exact-candidate-feasibility")
        self.assertEqual(witness["equilibrium"]["lower_bound_fraction"],
                         "100107990869/130471452826")
        self.assertEqual(witness["equilibrium"]["lower_bound_fraction"],
                         witness["equilibrium"]["upper_bound_fraction"])
        self.assertEqual(witness["equilibrium"]["gap_fraction"], "0")
        self.assertEqual(witness["equilibrium"]["flow_residuals"][0][0]["residual"], "0")
        self.assertEqual(witness["equilibrium"]["flow_residuals"][1][0]["residual"], "0")
        self.assertEqual(witness["equilibrium"]["complementary_slackness"], {
            "sb_realization_dot_ip_slack": "0",
            "bb_realization_dot_oop_slack": "0",
        })
        self.assertEqual(len(witness["census"]["payoff_matrix"]["fractions"]), 19)
        self.assertEqual(len(witness["oop_lp"]["own_realization"]["fractions"]), 19)
        self.assertEqual(len(witness["ip_lp"]["own_realization"]["fractions"]), 19)
        self.assertTrue(all(sum(map(Fraction, row["probabilities"]), Fraction(0)) == 1
                            for row in witness["policies"]))
        self.assertEqual(witness["count_provenance"]["physical_boards"], 3 * 1_712_304)
        expected_hash = hashlib.sha256(json.dumps(
            {key: value for key, value in witness.items() if key != "artifact_sha256"},
            sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")).hexdigest()
        self.assertEqual(witness["artifact_sha256"], expected_hash)

    def test_only_frozen_fixture_is_accepted(self):
        spec, _, _ = load_pinned_fixture()
        altered = json.loads(json.dumps(spec))
        altered["fixture"]["config"]["max_raises"] = 2
        with self.assertRaisesRegex(ValueError, "Only the frozen"):
            candidate.build_model(altered)

    def test_returned_caps_do_not_alias_lp_guards_or_future_preflight(self):
        original = dict(candidate.exact_lp.CAPS)
        witness = candidate.solve_model(candidate.build_model())
        witness["caps"]["rows"] = 0
        self.assertEqual(candidate.exact_lp.CAPS, original)
        later = candidate.build_model()
        self.assertEqual(later["lp_shape"]["oop_guarantee"]["rows"], 26)
        self.assertEqual(later["lp_shape"]["ip_ceiling"]["rows"], 28)


if __name__ == "__main__":
    unittest.main()
