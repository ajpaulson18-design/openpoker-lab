import unittest
from unittest.mock import patch

from scripts.preflop_validation import compare_result, physical_worlds, replay_policy
from pokerlab.preflop_solver import solve_preflop


_RUNOUTS = ("2c3c4d7h8h", "Kc2d3h7s8c", "Ac2d3h7s8c")
_FLOP = {"bet_sizes": [0.5], "raise_sizes": [],
         "max_raises": 0, "include_all_in": False}
_WEIGHTED_ARGS = {
    "config": {"starting_stack": [4, 3], "raise_sizes": [0.5],
                "max_raises": 1, "include_all_in": False},
    "runouts": _RUNOUTS,
    "flop_config": _FLOP,
}


class PreflopCfrPlusTests(unittest.TestCase):
    def test_weighted_asymmetric_game_replays_and_is_deterministic(self):
        args = dict(_WEIGHTED_ARGS, iterations=10, algorithm="cfrplus",
                    traversal="recursive")
        first = solve_preflop("AsAd:1,AhAc:0.25", "KsKd:1,KcKh:0.5", **args)
        oracle = replay_policy(first, "AsAd:1,AhAc:0.25", "KsKd:1,KcKh:0.5",
                               **{key: value for key, value in args.items()
                                  if key not in {"iterations", "algorithm", "traversal"}})
        compare_result(first, oracle)
        self.assertEqual(first["solver_version"], "preflop-strategy-v1")
        self.assertEqual(first["algorithm"], "cfrplus")
        self.assertEqual(first["execution_backend"], "recursive-python")
        self.assertEqual(first["training_schedule"],
                         "alternating-player-0-then-player-1; linear-own-reach-average-after-each-sweep")
        self.assertEqual(first["training_passes_per_iteration"], 3)
        self.assertEqual(first["training_passes"], 30)

        second = solve_preflop("AsAd:1,AhAc:0.25", "KsKd:1,KcKh:0.5", **args)
        self.assertEqual(first, second)

    def test_hidden_flop_root_decision_has_zero_legal_br_without_future_leakage(self):
        args = {
            "config": {"starting_stack": [2, 1], "max_raises": 0},
            "runouts": ("2c3c4d7h8h", "Kc2d3h7s8c"),
            "iterations": 10,
        }
        plus = solve_preflop("AsAd", "KsKd", algorithm="cfrplus", **args)
        oracle = replay_policy(plus, "AsAd", "KsKd",
                               config=args["config"], runouts=args["runouts"])
        compare_result(plus, oracle)
        self.assertEqual({world[3] for world in
                          physical_worlds("AsAd", "KsKd", args["runouts"])},
                         {-1, 1})
        self.assertEqual(len(plus["strategy"]), 1)
        row = plus["strategy"][0]
        self.assertEqual((row["player"], row["street"], row["revealed_board"],
                          row["history"]), ("sb", "preflop", [], []))
        self.assertEqual({action["name"] for action in row["actions"]},
                         {"fold", "call"})
        self.assertAlmostEqual(plus["sb_best_response_value"], 0.0, delta=1e-12)
        self.assertAlmostEqual(plus["bb_best_response_value"], 0.0, delta=1e-12)
        self.assertAlmostEqual(oracle["sb_best_response_value"], 0.0, delta=1e-12)
        self.assertAlmostEqual(oracle["bb_best_response_value"], 0.0, delta=1e-12)

        # Independent terminal payoffs: calling matches one chip with mean
        # showdown sign zero; folding forfeits the posted half-blind.
        call_value = sum(world[2] * world[3] for world in
                         physical_worlds("AsAd", "KsKd", args["runouts"]))
        fold_value = -0.5
        self.assertAlmostEqual(call_value, 0.0, delta=1e-12)
        self.assertAlmostEqual(fold_value, -0.5, delta=1e-12)

    def test_terminal_all_in_refund_value_and_legacy_algorithm_parity(self):
        args = {
            "config": {"starting_stack": [0.5, 20], "max_raises": 0},
            "runouts": ("2c3c4d7h8h",),
            "iterations": 10,
        }
        plus = solve_preflop("AsAd", "KsKd", algorithm="cfrplus", **args)
        vanilla = solve_preflop("AsAd", "KsKd", algorithm="vanilla", **args)
        oracle = replay_policy(plus, "AsAd", "KsKd",
                               config=args["config"], runouts=args["runouts"])
        compare_result(plus, oracle)
        self.assertEqual(plus["strategy"], [])
        self.assertEqual(plus["info_sets"], 0)
        self.assertIsNone(plus["training_schedule"])
        self.assertEqual(plus["training_passes_per_iteration"], 0)
        self.assertEqual(plus["training_passes"], 0)
        self.assertAlmostEqual(plus["value_sb"], 0.5, delta=1e-12)
        self.assertAlmostEqual(plus["value_bb"], -0.5, delta=1e-12)
        for field in ("value_sb", "value_bb", "sb_best_response_value",
                      "bb_best_response_value", "nash_conv"):
            self.assertAlmostEqual(plus[field], vanilla[field], delta=1e-12)
        self.assertNotIn("training_schedule", vanilla)
        self.assertNotIn("training_passes_per_iteration", vanilla)
        self.assertNotIn("training_passes", vanilla)

    def test_cfrplus_rejects_planned_traversal_before_world_ranking(self):
        with patch("pokerlab.preflop_solver.rank_hand") as rank:
            with self.assertRaisesRegex(ValueError, r"CFR\+ supports recursive"):
                solve_preflop("AsAd", "KsKd", config={"max_raises": 0},
                              runouts=_RUNOUTS, iterations=10,
                              algorithm="cfrplus", traversal="planned")
            rank.assert_not_called()

    def test_cfrplus_three_pass_work_guard_rejects_before_trainer(self):
        args = dict(_WEIGHTED_ARGS, iterations=10, traversal="recursive")
        vanilla = solve_preflop("AsAd:1,AhAc:0.25", "KsKd:1,KcKh:0.5",
                                algorithm="vanilla", **args)
        with patch("pokerlab.preflop_solver._MAX_WORLD_NODE_WORK",
                   vanilla["world_decision_work"]):
            with patch("pokerlab.preflop_solver.train_cfrplus") as trainer:
                with self.assertRaisesRegex(ValueError, "30 million world-decision"):
                    solve_preflop("AsAd:1,AhAc:0.25", "KsKd:1,KcKh:0.5",
                                  algorithm="cfrplus", **args)
                trainer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
