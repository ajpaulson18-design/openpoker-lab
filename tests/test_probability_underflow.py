"""Prevent accepted ranges from silently defining a different chance game."""
from fractions import Fraction
import sys
import unittest
from unittest.mock import patch

from pokerlab import postflop_solver, preflop_solver, solver
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.river_config import RiverConfig
from scripts.preflop_validation import compare_result, replay_policy


BOARD = "2c3d4h5s6c"


class ProbabilityUnderflowTests(unittest.TestCase):
    def test_preflop_rejects_erased_and_positive_but_distorted_posteriors_before_ranking(self):
        cases = (("AsAh:1e-160,QsQh:1e-161", "KsKh:1e-156"),
                 ("AsAh:1e-160,QsQh:5e-161", "KsKh:2e-156"))
        # The second request used to return (.5, .5), although both raw masses
        # stayed positive. A zero-only check does not contain this defect.
        self.assertEqual(Fraction.from_float(1e-160) /
                         (Fraction.from_float(1e-160) + Fraction.from_float(5e-161)),
                         Fraction(2, 3))
        for sb, bb in cases:
            with self.subTest(sb=sb), patch.object(preflop_solver, "_rank_world") as rank:
                with self.assertRaisesRegex(ValueError, "probability underflow"):
                    preflop_solver.solve_preflop(
                        sb, bb, PreflopConfig(max_raises=0),
                        runouts=(BOARD,), iterations=10)
                rank.assert_not_called()

    def test_postflop_rejects_bad_joint_mass_before_ranking_or_training(self):
        for board, runouts in ((BOARD, None), ("2c3d4h5s", ("6c",)),
                               ("2c3d4h", (("5s", "6c"),))):
            with self.subTest(board=board), patch.object(postflop_solver, "rank_hand") as rank:
                with self.assertRaisesRegex(ValueError, "probability underflow"):
                    postflop_solver.solve_postflop(
                        board, "AsAh:1e-160,QsQh:1e-161", "KsKh:1e-163",
                        runouts=runouts, iterations=10)
                rank.assert_not_called()

    def test_both_river_routes_reject_lost_or_distorted_support(self):
        for config in (None, RiverConfig()):
            for sb, bb in (("AsAh:1e-160,QsQh:1e-161", "KsKh:1e-163"),
                           ("AsAh:1e-160,QsQh:5e-161", "KsKh:4e-164")):
                with self.subTest(config=config, sb=sb):
                    with self.assertRaisesRegex(ValueError, "probability underflow"):
                        solver.solve(BOARD, sb, bb, config=config, iterations=10)

    def test_river_rejects_normal_raw_weights_that_normalize_into_subnormals(self):
        sb = f"AsAh:{sys.float_info.min},QsQh:1,JsJh:1"
        for config in (None, RiverConfig()):
            with self.subTest(config=config):
                with self.assertRaisesRegex(ValueError, "probability underflow"):
                    solver.solve(BOARD, sb, "KsKh", config=config, iterations=10)

    def test_ordinary_weighted_complete_game_still_matches_independent_replay(self):
        sb, bb = "AsAh:1,QsQh:0.5", "KsKh:1"
        kwargs = dict(config={"starting_stack": [2, 1], "max_raises": 0},
                      runouts=(BOARD, "2c3d4h5sAc"))
        result = preflop_solver.solve_preflop(sb, bb, iterations=10, **kwargs)
        compare_result(result, replay_policy(result, sb, bb, **kwargs))
        self.assertTrue(all(row["probability"] > 0
                            for row in result["private_pair_probabilities"]))

    def test_normal_probability_arithmetic_remains_literal(self):
        _, worlds, _, posterior, _, _ = preflop_solver._enumerate_physical_worlds(
            "AsAh:1,QsQh:0.5", "KsKh", (BOARD,), 10)
        raw_a, raw_b = 1 / 34246080, .5 / 34246080
        from math import fsum
        expected = [raw_a / fsum((raw_a, raw_b)), raw_b / fsum((raw_a, raw_b))]
        self.assertEqual([row[2] for row in worlds], expected)
        self.assertEqual([row["probability"] for row in posterior], expected)


if __name__ == "__main__":
    unittest.main()
