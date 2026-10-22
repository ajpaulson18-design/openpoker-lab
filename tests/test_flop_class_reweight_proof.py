from dataclasses import replace
from fractions import Fraction
import unittest
from unittest.mock import patch

from scripts import flop_class_reweight_plan as planning
from scripts import flop_class_reweight_proof as weighted
from scripts import flop_public_classes as proof
from scripts import flop_multistreet_validation as physical


def _fixture():
    plan = planning.plan_weights((1, Fraction(1, 2)), (Fraction(1, 4), 1))
    base, current = [], []
    counts, probabilities = [], {}
    for oop, ip, prior in plan.exact_pair_priors:
        oop, ip = weighted._canonical_hand(oop), weighted._canonical_hand(ip)
        board = ("2c", "3d", "4h", "5c", "6c")
        base.append((oop, ip, Fraction(1, 3), 1, board))
        current.append((oop, ip, prior, 1, board))
        counts.append({"oop_hand": oop, "ip_hand": ip, "wins": 1,
                       "ties": 0, "losses": 0, "ordered_outcomes": 1,
                       "pair_probability_fraction": f"{prior.numerator}/{prior.denominator}",
                       "pair_probability": float(prior)})
        probabilities[(oop, ip)] = float(prior)
    return plan, tuple(base), tuple(current), tuple(counts), probabilities


class ReweightedProofTests(unittest.TestCase):
    def test_malformed_plan_rejects_before_any_oracle_preparation(self):
        plan, *_ = _fixture()
        malformed = replace(plan, oop_weights=[Fraction(1), Fraction(1, 2)])
        with patch.object(physical, "prepare_oracle") as prepare:
            with self.assertRaisesRegex(ValueError, "Reweight plan fields|two-tuple"):
                weighted.build_model(malformed)
        prepare.assert_not_called()

    def test_exact_global_blocker_conditioned_prior_anchors(self):
        plan, base, current, counts, probabilities = _fixture()
        self.assertEqual(plan.global_blocker_normalizer, Fraction(13, 8))
        self.assertEqual(tuple(row[2] for row in plan.exact_pair_priors),
                         (Fraction(8, 13), Fraction(1, 13), Fraction(4, 13)))
        self.assertTrue(weighted._validate_weighted_distribution(
            plan, base, current, counts, counts, plan.global_blocker_normalizer,
            probabilities, outcomes_per_pair=1))
        self.assertNotEqual(tuple(row[2] for row in plan.exact_pair_priors),
                            (Fraction(1, 3),) * 3)

    def test_weighted_mass_normalizer_sign_and_prior_mutations_reject(self):
        plan, base, current, counts, probabilities = _fixture()
        checks = (
            (base, (current[0][:2] + (current[0][2] + Fraction(1, 10),) + current[0][3:],) + current[1:],
             counts, plan.global_blocker_normalizer, probabilities),
            (base, current, counts, plan.global_blocker_normalizer + 1, probabilities),
            (base, (current[0][:3] + (-1,) + current[0][4:],) + current[1:],
             counts, plan.global_blocker_normalizer, probabilities),
            (base, current, counts, plan.global_blocker_normalizer,
             {**probabilities, next(iter(probabilities)): 1.0}),
        )
        for args in checks:
            with self.subTest(args=args[1:3]), self.assertRaises(ValueError):
                weighted._validate_weighted_distribution(
                    plan, args[0], args[1], args[2], args[2], args[3], args[4],
                    outcomes_per_pair=1)

    def test_plan_field_tampering_rejects(self):
        plan, *_ = _fixture()
        forged = replace(plan, global_blocker_normalizer=Fraction(1))
        with self.assertRaisesRegex(ValueError, "malformed"):
            weighted._validate_plan(forged)

    def test_numeric_alias_in_plan_metadata_rejects(self):
        plan, *_ = _fixture()
        first, *rest = plan.compatible_pair_raw_products
        forged = replace(plan, compatible_pair_raw_products=(
            (first[0], first[1], True), *rest))
        with self.assertRaisesRegex(ValueError, "malformed"):
            weighted._validate_plan(forged)

    def test_tree_mismatch_rejects_and_identical_weighted_tree_passes(self):
        plan, _, worlds, _, _ = _fixture()
        active = {}
        for world in worlds:
            for length in range(3):
                for player in (0, 1):
                    active.setdefault((player, world[4][3:3+length]), set()).add(world[player])
        def oracle(contribution, winner=0):
            root = physical._Terminal((), "fold", (contribution, contribution), winner)
            return {"root": root, "worlds": worlds, "nodes": {},
                    "active_hands_by_prefix": active,
                    "board": proof.BOARD, "config": {}, "street_configs": {},
                    "runouts": (), "reachable_runouts": (), "runout_mode": "full-deck",
                    "pot": 10.0, "effective_stack": [5.0, 5.0],
                    "physical_worlds": 3, "worlds_count": 3, "compatible_pairs": 3,
                    "public_nodes": 0, "public_states": 1, "chance_nodes": 0,
                    "terminal_nodes": 1}
        left, right = oracle(5.0), oracle(5.0)
        weighted._validate_tree_compat(left, right)
        with self.assertRaisesRegex(ValueError, "numeric tree"):
            weighted._validate_tree_compat(left, oracle(6.0))
        with self.assertRaisesRegex(ValueError, "numeric tree"):
            weighted._validate_tree_compat(oracle(5.0, 1), oracle(5.0, True))


if __name__ == "__main__":
    unittest.main()
