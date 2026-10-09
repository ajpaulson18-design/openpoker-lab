"""Anchors for the independent serialized-policy replay oracle."""
from copy import deepcopy
import unittest

from scripts.preflop_validation import compare_result, independent_rank, physical_worlds, replay_policy


class PreflopOracleTests(unittest.TestCase):
    def test_best_five_rank_anchors(self):
        def rank(raw):
            return independent_rank(tuple(raw[index:index + 2] for index in range(0, len(raw), 2)))
        self.assertEqual(rank("As2s3s4s5sKdQc"), (8, 5))
        self.assertEqual(rank("AcAdAhAsKdQc2c"), (7, 14, 13))
        self.assertEqual(rank("AcAdAhKsKdKh2c"), (6, 14, 13))
        self.assertEqual(rank("AcKdQhJsTc9c2c"), (4, 14))
        self.assertEqual(rank("AcAdKsKdQhJs2c"), (2, 14, 13, 12))

    def test_joint_blocker_prior_rational_anchor(self):
        worlds = physical_worlds("AsAd:1,AhAc:0.25", "KsKd:1,KcKh:0.5",
                                 ["2c3c4d7h8h", "Kc2d3h7s8c", "Ac2d3h7s8c"])
        self.assertEqual(len(worlds), 8)
        self.assertAlmostEqual(sum(world[2] for world in worlds if world[0] == "AdAs"), 4 / 4.625)
        self.assertNotAlmostEqual(4 / 4.625, .8)
        self.assertAlmostEqual(sum(world[2] for world in worlds), 1)

    def test_legal_response_cannot_peek_at_flop(self):
        result = {"strategy": [{"player": "sb", "hand": "AdAs", "street": "preflop",
                                "revealed_board": [], "history": [],
                                "actions": [{"name": "fold", "amount": 0, "raise_to": 0,
                                             "history_key": "fold", "probability": .5},
                                            {"name": "call", "amount": .5, "raise_to": 1,
                                             "history_key": "call", "probability": .5}]}]}
        kwargs = dict(config={"starting_stack": [2, 1], "max_raises": 0},
                      runouts=["2c3c4d7h8h", "Kc2d3h7s8c"])
        oracle = replay_policy(result, "AsAd", "KsKd", **kwargs)
        self.assertAlmostEqual(oracle["value_sb"], -.25)
        self.assertAlmostEqual(oracle["sb_best_response_value"], 0)
        self.assertAlmostEqual(oracle["bb_best_response_value"], .25)
        # Illegal clairvoyant choice: call on the win, fold on the loss.
        self.assertGreater(.5 * 1 + .5 * -.5, oracle["sb_best_response_value"])
        leaked = deepcopy(result)
        leaked["strategy"][0]["revealed_board"] = ["Kc"]
        with self.assertRaisesRegex(AssertionError, "leak"):
            replay_policy(leaked, "AsAd", "KsKd", **kwargs)
        wrong_target = deepcopy(result)
        wrong_target["strategy"][0]["actions"][1]["raise_to"] = 1.5
        with self.assertRaises(AssertionError):
            replay_policy(wrong_target, "AsAd", "KsKd", **kwargs)

    def test_production_serialized_live_game_matches_independent_rules_and_responses(self):
        from pokerlab.preflop_solver import solve_preflop
        kwargs = dict(config={"starting_stack": [4, 3], "raise_sizes": [.5],
                              "max_raises": 1, "include_all_in": False},
                      runouts=["2c3c4d7h8h", "Kc2d3h7s8c", "Ac2d3h7s8c"],
                      flop_config={"bet_sizes": [.5], "include_all_in": False},
                      turn_config={"bet_sizes": [.25]},
                      river_config={"bet_sizes": [.5], "raise_sizes": [.5], "max_raises": 1})
        for algorithm, traversal in (("vanilla", "recursive"), ("dcfr", "planned")):
            with self.subTest(algorithm=algorithm, traversal=traversal):
                result = solve_preflop("AsAd:1,AhAc:0.25", "KsKd:1,KcKh:0.5",
                                       iterations=10, algorithm=algorithm, traversal=traversal, **kwargs)
                oracle = replay_policy(result, "AsAd:1,AhAc:0.25", "KsKd:1,KcKh:0.5", **kwargs)
                compare_result(result, oracle)
                self.assertGreater(oracle["checked_information_sets"], 10)

    def test_production_short_blind_refunds_use_matched_total_chips(self):
        from pokerlab.preflop_solver import solve_preflop
        for stacks, best_value in (([.5, 20], .5), ([20, .25], .25), ([.75, 20], .75)):
            with self.subTest(stacks=stacks):
                kwargs = dict(config={"starting_stack": stacks, "max_raises": 0}, runouts=["2c3c4d7h8h"])
                result = solve_preflop("AsAd", "KsKd", iterations=10, **kwargs)
                oracle = replay_policy(result, "AsAd", "KsKd", **kwargs)
                compare_result(result, oracle)
                self.assertAlmostEqual(oracle["sb_best_response_value"], best_value)

    def test_finite_iteration_hidden_flop_quality_gates(self):
        from pokerlab.preflop_solver import solve_preflop
        kwargs = dict(config={"starting_stack": [2, 1], "max_raises": 0},
                      runouts=["2c3c4d7h8h", "Kc2d3h7s8c"])
        for algorithm, ceiling in (("vanilla", .0025000001), ("dcfr", .00000074)):
            result = solve_preflop("AsAd", "KsKd", iterations=100, algorithm=algorithm, **kwargs)
            compare_result(result, replay_policy(result, "AsAd", "KsKd", **kwargs))
            self.assertAlmostEqual(result["sb_best_response_value"], 0)
            self.assertLessEqual(result["nash_conv"], ceiling)


if __name__ == "__main__":
    unittest.main()
