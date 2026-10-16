"""Pair-mean hidden-world mode matches the categorical reference."""
from fractions import Fraction
import unittest
from unittest.mock import patch

from pokerlab import preflop_checkdown_solver as solver
from pokerlab.preflop_checkdown_budget import admit_prepared, options
from pokerlab.preflop_full_board_equity import BOARDS_PER_PAIR, FullBoardEquities, plan_preflop_equities
from scripts.preflop_checkdown_validation import replay
from tests.test_preflop_checkdown_solver import (
    AA_RANGE, BB_RANGE, SB_RANGE, prepared_table,
)


class PreflopPairMeanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table, cls.counts = prepared_table()

    def test_pair_mean_replays_all_cfr_variants_with_full_physical_counts(self):
        config = {
            "small_blind": 0.5, "big_blind": 1.0,
            "starting_stack": [3.0, 3.0], "raise_sizes": [0.5],
            "max_raises": 1, "include_all_in": True,
        }
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                result = solver.solve_prepared_preflop_checkdown(
                    self.table, config=config, iterations=100,
                    algorithm=algorithm, world_indexing="pair-mean",
                )
                exact = replay(result, SB_RANGE, BB_RANGE, config, self.counts)
                self.assertTrue(exact["exact_fraction_replay"])
                self.assertEqual(result["world_indexing"], "pair-mean")
                self.assertEqual(result["training_world_rows"], len(self.table.pairs))
                self.assertEqual(result["physical_boards"],
                                 BOARDS_PER_PAIR * len(self.table.pairs))
                self.assertEqual(result["pair_equities"],
                                 solver.solve_prepared_preflop_checkdown(
                                     self.table, config=config, iterations=100,
                                     algorithm=algorithm,
                                 )["pair_equities"])
                self.assertAlmostEqual(result["value_sb"], exact["value_sb"], delta=1e-9)
                self.assertAlmostEqual(result["sb_best_response_value"],
                                       exact["sb_best_response_value"], delta=1e-9)
                self.assertAlmostEqual(result["bb_best_response_value"],
                                       exact["bb_best_response_value"], delta=1e-9)
                self.assertLessEqual(max(exact["scalar_absolute_gaps"].values()), 1e-9)
                self.assertEqual(exact["checked_information_sets"], result["info_sets"])

    def test_default_and_explicit_categorical_payloads_remain_identical(self):
        config = {
            "small_blind": 0.5, "big_blind": 1.0,
            "starting_stack": [2.5, 2.25], "raise_sizes": [],
            "max_raises": 0, "include_all_in": False,
        }
        omitted = solver.solve_prepared_preflop_checkdown(
            self.table, config=config, iterations=20, algorithm="vanilla"
        )
        explicit = solver.solve_prepared_preflop_checkdown(
            self.table, config=config, iterations=20, algorithm="vanilla",
            world_indexing="categorical",
        )
        mean = solver.solve_prepared_preflop_checkdown(
            self.table, config=config, iterations=20, algorithm="vanilla",
            world_indexing="pair-mean",
        )
        self.assertEqual(omitted, explicit)
        self.assertNotIn("world_indexing", omitted)
        self.assertEqual(set(mean), set(omitted) | {"world_indexing"})
        self.assertEqual(mean["world_indexing"], "pair-mean")
        self.assertEqual(mean["pair_equities"], omitted["pair_equities"])
        self.assertEqual(omitted["training_world_rows"], len(self.table.worlds))
        self.assertEqual(mean["training_world_rows"], len(self.table.pairs))

    def test_pair_mean_short_all_in_and_unmatched_refund_replay(self):
        config = {
            "small_blind": 0.5, "big_blind": 1.0,
            "starting_stack": [4.0, 2.75], "raise_sizes": [0.5, 1.0],
            "max_raises": 2, "include_all_in": True,
        }
        result = solver.solve_prepared_preflop_checkdown(
            self.table, config=config, iterations=60, algorithm="cfrplus",
            world_indexing="pair-mean",
        )
        exact = replay(result, SB_RANGE, BB_RANGE, config, self.counts)
        self.assertTrue(exact["exact_fraction_replay"])
        shove = next(row for row in result["strategy"]
                     if row["player"] == "sb" and row["hand"] == "AdAs"
                     and row["history"] == [])
        all_in = next(action for action in shove["actions"]
                      if action["name"] == "all_in" and action["raise_to"] == 4.0)
        response = next(row for row in result["strategy"]
                        if row["player"] == "bb" and row["hand"] == "KdKs"
                        and row["history"] == [all_in["history_key"]])
        call = next(action for action in response["actions"]
                    if action["name"] == "call")
        self.assertEqual(call["raise_to"], 2.75)
        self.assertAlmostEqual(call["amount"], 1.75)
        self.assertTrue(result["work_budget"]["source_enumeration_charged"])

    def test_zero_mean_tie_heavy_synthetic_world_preserves_mass_fold_and_average(self):
        # Synthetic category census only; these are structural test values,
        # not a physical poker-board result or a claim about real cards.
        plan = plan_preflop_equities(AA_RANGE, "KsKd:1")
        wins, ties, losses = 1, BOARDS_PER_PAIR - 2, 1
        categorical = tuple((0, 0, float(Fraction(n, BOARDS_PER_PAIR)), sign)
                            for n, sign in ((losses, -1), (ties, 0), (wins, 1)))
        synthetic = FullBoardEquities(
            plan.hands, plan.pairs, ((wins, ties, losses),), categorical,
            plan._budget_items,
        )
        synthetic.validate()
        config = {
            "small_blind": 0.5, "big_blind": 1.0,
            "starting_stack": [2.0, 2.0], "raise_sizes": [],
            "max_raises": 0, "include_all_in": False,
        }
        categorical_result = solver.solve_prepared_preflop_checkdown(
            synthetic, config=config, iterations=60, algorithm="cfrplus",
            resource_model="prepared-counts",
        )
        mean_result = solver.solve_prepared_preflop_checkdown(
            synthetic, config=config, iterations=60, algorithm="cfrplus",
            resource_model="prepared-counts", world_indexing="pair-mean",
        )
        self.assertEqual(sum(world[2] for world in categorical), 1.0)
        self.assertEqual(mean_result["training_world_rows"], 1)
        self.assertEqual(categorical_result["training_world_rows"], 3)
        self.assertEqual(mean_result["pair_equities"], categorical_result["pair_equities"])
        self.assertEqual(mean_result["physical_boards"], BOARDS_PER_PAIR)
        for field in ("value_sb", "sb_best_response_value", "bb_best_response_value",
                      "nash_conv", "exploitability"):
            self.assertAlmostEqual(mean_result[field], categorical_result[field], delta=1e-9)
        def profiles(result):
            return {
                (row["player"], row["hand"], tuple(row["history"])):
                {action["history_key"]: action["probability"] for action in row["actions"]}
                for row in result["strategy"]
            }
        mean_profiles = profiles(mean_result)
        categorical_profiles = profiles(categorical_result)
        self.assertEqual(set(mean_profiles), set(categorical_profiles))
        for key, mean_actions in mean_profiles.items():
            self.assertAlmostEqual(sum(mean_actions.values()), 1.0, delta=1e-12)
            for action, probability in mean_actions.items():
                self.assertAlmostEqual(
                    probability, categorical_profiles[key][action], delta=1e-9
                )

    def test_pair_mean_admission_and_invalid_modes_reject_before_build(self):
        config = {
            "small_blind": 0.5, "big_blind": 1.0,
            "starting_stack": [4.0, 3.0], "raise_sizes": [0.5, 1.0],
            "max_raises": 2, "include_all_in": True,
        }
        requested = options(config, 3000, "cfrplus", "source-inclusive")
        with self.assertRaisesRegex(ValueError, "500,000,000"):
            admit_prepared(self.table, requested, 3000, "cfrplus", "source-inclusive")
        mean_budget = admit_prepared(
            self.table, requested, 3000, "cfrplus", "source-inclusive",
            world_indexing="pair-mean"
        )
        self.assertLessEqual(mean_budget["total_loop_entries_upper_bound"],
                             mean_budget["total_loop_entry_limit"])
        self.assertEqual(mean_budget["training_world_rows_upper_bound"], 3)
        self.assertEqual(mean_budget["categorical_rows_upper_bound"], 9)
        self.assertEqual(mean_budget["pair_mean_setup_loop_entries_upper_bound"],
                         256 * len(self.table.pairs))

        with patch.object(solver, "build_preflop_tree",
                          side_effect=RuntimeError("tree reached")) as build:
            with self.assertRaisesRegex(ValueError, "500,000,000"):
                solver.solve_prepared_preflop_checkdown(
                    self.table, config=config, iterations=3000,
                    algorithm="cfrplus", resource_model="source-inclusive",
                )
            build.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, "tree reached"):
                solver.solve_prepared_preflop_checkdown(
                    self.table, config=config, iterations=3000,
                    algorithm="cfrplus", resource_model="source-inclusive",
                    world_indexing="pair-mean",
                )
            self.assertEqual(build.call_count, 1)

        oversized = dict(config, raise_sizes=list(range(1, 9)), max_raises=8)
        with patch.object(solver, "build_preflop_tree",
                          side_effect=AssertionError("builder must not run")) as build:
            with patch.object(solver, "train_cfrplus",
                              side_effect=AssertionError("trainer must not run")) as trainer:
                with self.assertRaisesRegex(ValueError, "tree forecast"):
                    solver.solve_prepared_preflop_checkdown(
                        self.table, config=oversized, iterations=10_000,
                        resource_model="prepared-counts", world_indexing="pair-mean",
                    )
                with self.assertRaisesRegex(ValueError, "World indexing"):
                    solver.solve_prepared_preflop_checkdown(
                        self.table, config=config, iterations=10,
                        world_indexing="unknown",
                    )
                build.assert_not_called()
                trainer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
