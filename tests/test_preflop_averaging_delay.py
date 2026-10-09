import unittest
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from scripts.preflop_validation import compare_result, replay_policy


SB = "AsAd:1,AhAc:0.25"
BB = "KsKd:1,KcKh:0.5"
KWARGS = {
    "config": {"starting_stack": [4, 3], "raise_sizes": [0.5],
               "max_raises": 1, "include_all_in": False},
    "runouts": ("2c3c4d7h8h", "Kc2d3h7s8c", "Ac2d3h7s8c"),
    "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                    "max_raises": 0, "include_all_in": False},
}
FIELDS = ("value_sb", "value_bb", "sb_best_response_value",
          "bb_best_response_value", "nash_conv", "exploitability")


class PreflopAveragingDelayTests(unittest.TestCase):
    def test_delayed_trainer_meets_independent_known_kuhn_accuracy(self):
        from pokerlab.postflop_solver import _Chance
        from pokerlab.preflop_delayed_cfrplus import train_delayed_public_cfrplus
        from scripts.cfr_quality import build_kuhn_adapter, check_metrics

        adapter = build_kuhn_adapter()
        for delay in (0, 100, 500):
            with self.subTest(delay=delay):
                policy = train_delayed_public_cfrplus(
                    adapter["root"], adapter["worlds"], adapter["infos"], 2000,
                    averaging_delay=delay, pot=2, chance_type=_Chance)
                metrics = check_metrics(policy, layout=adapter["layout"])
                self.assertLess(metrics["value_error"], 1e-5)
                self.assertLess(metrics["nash_conv"], 0.001)

    def test_zero_delay_preserves_default_output_on_all_training_paths(self):
        for algorithm, traversal in (("vanilla", "recursive"), ("dcfr", "planned"),
                                     ("cfrplus", "recursive"),
                                     ("cfrplus", "public-batched")):
            with self.subTest(algorithm=algorithm, traversal=traversal):
                common = dict(KWARGS, iterations=10, algorithm=algorithm,
                              traversal=traversal)
                default = solver.solve_preflop(SB, BB, **common)
                explicit = solver.solve_preflop(SB, BB, **common, averaging_delay=0)
                self.assertEqual(default, explicit)
                self.assertNotIn("averaging_delay", default)

    def test_weighted_delayed_policies_replay_and_match_recursive_reference(self):
        for delay in (1, 8, 19):
            with self.subTest(delay=delay):
                reference = solver.solve_preflop(
                    SB, BB, **KWARGS, iterations=20, algorithm="cfrplus",
                    averaging_delay=delay)
                vector = solver.solve_preflop(
                    SB, BB, **KWARGS, iterations=20, algorithm="cfrplus",
                    traversal="public-batched", diagnostics="public-batched",
                    resource_model="public-vector", averaging_delay=delay)
                for result in (reference, vector):
                    compare_result(result, replay_policy(result, SB, BB, **KWARGS))
                    self.assertEqual(result["averaging_delay"], delay)
                    self.assertEqual(result["averaging_positive_sweeps"], 20 - delay)
                    self.assertEqual(result["training_regret_passes"], 40)
                self.assertEqual(reference["training_average_passes"], 20 - delay)
                self.assertEqual(reference["training_passes"], 60 - delay)
                self.assertIsNone(reference["training_passes_per_iteration"])
                self.assertEqual(vector["training_average_passes"], 20)
                self.assertEqual(vector["training_passes"], 60)
                self.assertEqual(vector["training_passes_per_iteration"], 3)
                for field in FIELDS:
                    self.assertAlmostEqual(reference[field], vector[field], delta=1e-11)
                self.assertEqual(len(reference["strategy"]), len(vector["strategy"]))
                for left, right in zip(reference["strategy"], vector["strategy"]):
                    self.assertEqual((left["hand"], left["history"]),
                                     (right["hand"], right["history"]))
                    for a, b in zip(left["actions"], right["actions"]):
                        self.assertEqual(a["history_key"], b["history_key"])
                        self.assertAlmostEqual(a["probability"], b["probability"],
                                               delta=1e-11)

    def test_invalid_delay_and_incompatible_methods_fail_before_enumeration(self):
        for delay in (-1, True, 1.5, "1", None, 10, 11):
            with self.subTest(delay=delay):
                with patch.object(solver, "_enumerate_physical_worlds") as enumerate_worlds:
                    with self.assertRaisesRegex(ValueError, "averaging delay"):
                        solver.solve_preflop(SB, BB, **KWARGS, iterations=10,
                                             algorithm="cfrplus", averaging_delay=delay)
                    enumerate_worlds.assert_not_called()
        for algorithm in ("vanilla", "dcfr"):
            with patch.object(solver, "_enumerate_physical_worlds") as enumerate_worlds:
                with self.assertRaisesRegex(ValueError, "requires CFR"):
                    solver.solve_preflop(SB, BB, **KWARGS, iterations=10,
                                         algorithm=algorithm, averaging_delay=2)
                enumerate_worlds.assert_not_called()
        with patch.object(solver, "_enumerate_physical_worlds") as enumerate_worlds:
            with self.assertRaisesRegex(ValueError, "CFR\\+ supports"):
                solver.solve_preflop(SB, BB, **KWARGS, iterations=10,
                                     algorithm="cfrplus", averaging_delay=2,
                                     traversal="planned")
            enumerate_worlds.assert_not_called()

    def test_future_stays_hidden_and_root_has_known_legal_gap(self):
        kwargs = {"config": {"starting_stack": [2, 1], "max_raises": 0},
                  "runouts": ("2c3c4d7h8h", "Kc2d3h7s8c")}
        result = solver.solve_preflop(
            "AsAd", "KsKd", **kwargs, iterations=10, algorithm="cfrplus",
            traversal="public-batched", diagnostics="public-batched", averaging_delay=8)
        oracle = replay_policy(result, "AsAd", "KsKd", **kwargs)
        compare_result(result, oracle)
        self.assertEqual(len(result["strategy"]), 1)
        self.assertEqual(result["strategy"][0]["history"], [])
        self.assertEqual(result["strategy"][0]["revealed_board"], [])
        self.assertAlmostEqual(oracle["value_sb"], 0, delta=1e-12)
        self.assertAlmostEqual(oracle["nash_conv"], 0, delta=1e-12)

    def test_no_information_sets_preserve_refunds_and_zero_pass_metadata(self):
        kwargs = {"config": {"starting_stack": [0.5, 20], "max_raises": 0},
                  "runouts": ("2c3c4d7h8h",)}
        for traversal in ("recursive", "public-batched"):
            with self.subTest(traversal=traversal):
                with patch.object(solver, "train_cfrplus") as generic:
                    with patch.object(solver, "train_delayed_public_cfrplus") as vector:
                        result = solver.solve_preflop(
                            "AsAd", "KsKd", **kwargs, iterations=10, algorithm="cfrplus",
                            traversal=traversal, averaging_delay=5)
                        generic.assert_not_called()
                        vector.assert_not_called()
                self.assertEqual(result["strategy"], [])
                self.assertEqual(result["averaging_positive_sweeps"], 0)
                self.assertEqual(result["training_passes"], 0)
                self.assertEqual(result["training_average_passes"], 0)
                self.assertEqual(result["training_regret_passes"], 0)
                self.assertEqual(result["training_passes_per_iteration"], 0)
                compare_result(result, replay_policy(result, "AsAd", "KsKd", **kwargs))

    def test_resource_guards_fail_before_trainer_and_view_allocation(self):
        with patch.object(solver, "_MAX_WORLD_NODE_WORK", 1):
            with patch.object(solver, "train_delayed_public_cfrplus") as trainer:
                with self.assertRaisesRegex(ValueError, "world-decision iterations"):
                    solver.solve_preflop(SB, BB, **KWARGS, iterations=10,
                                         algorithm="cfrplus", traversal="public-batched",
                                         averaging_delay=5)
                trainer.assert_not_called()
        with patch.object(solver, "estimate_vector_budget", side_effect=ValueError("bounded")):
            with patch.object(solver, "_positive_pot_training_view") as view:
                with self.assertRaisesRegex(ValueError, "bounded"):
                    solver.solve_preflop(SB, BB, **KWARGS, iterations=10,
                                         algorithm="cfrplus", traversal="public-batched",
                                         diagnostics="public-batched", resource_model="public-vector",
                                         averaging_delay=5)
                view.assert_not_called()


if __name__ == "__main__":
    unittest.main()
