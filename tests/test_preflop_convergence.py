import math
import unittest
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from pokerlab import preflop_vector_budget as budget
from scripts.preflop_validation import compare_result, replay_policy

SB = "AsAd:1,AhAc:0.25"
BB = "KsKd:1,KcKh:0.5"
KWARGS = {"config": {"starting_stack": [4, 3], "raise_sizes": [0.5],
                     "max_raises": 1, "include_all_in": False},
          "runouts": ("2c3c4d7h8h", "Kc2d3h7s8c", "Ac2d3h7s8c"),
          "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                          "max_raises": 0, "include_all_in": False}}
OPTIONS = {"algorithm": "cfrplus", "traversal": "public-batched",
           "diagnostics": "public-batched", "resource_model": "public-vector"}


class PreflopConvergenceTests(unittest.TestCase):
    def test_exact_early_stop_matches_fixed_policy_and_independent_best_responses(self):
        fixed = solver.solve_preflop(SB, BB, **KWARGS, **OPTIONS,
                                     iterations=10, averaging_delay=5)
        with patch.object(solver, "evaluate_public_profile",
                          wraps=solver.evaluate_public_profile) as evaluate:
            result = solver.solve_preflop(SB, BB, **KWARGS, **OPTIONS,
                iterations=30, averaging_delay=5, target_nash_conv=10,
                convergence_check_interval=10)
        self.assertEqual(result["strategy"], fixed["strategy"])
        self.assertEqual(result["iterations"], 30)
        self.assertEqual(result["completed_iterations"], 10)
        self.assertEqual(result["training_regret_passes"], 20)
        self.assertEqual(result["training_average_passes"], 5)
        self.assertEqual(result["training_passes"], 25)
        self.assertTrue(result["stopped_early"])
        self.assertTrue(result["convergence_target_reached"])
        self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(result["vector_work_budget"]["iterations"], 30)
        compare_result(result, replay_policy(result, SB, BB, **KWARGS))

    def test_unmet_target_and_each_checkpoint_replay_at_fixed_delay(self):
        result = solver.solve_preflop(SB, BB, **KWARGS, **OPTIONS,
            iterations=35, averaging_delay=5, target_nash_conv=1e-30,
            convergence_check_interval=10)
        self.assertFalse(result["convergence_target_reached"])
        self.assertFalse(result["stopped_early"])
        self.assertEqual(result["completed_iterations"], 35)
        self.assertEqual([r["completed_iterations"] for r in result["convergence_checkpoints"]],
                         [10, 20, 30, 35])
        for row in result["convergence_checkpoints"]:
            fixed = solver.solve_preflop(SB, BB, **KWARGS, **OPTIONS,
                iterations=row["completed_iterations"], averaging_delay=5)
            oracle = replay_policy(fixed, SB, BB, **KWARGS)
            compare_result(fixed, oracle)
            for field in ("value_sb", "sb_best_response_value", "bb_best_response_value", "nash_conv"):
                self.assertAlmostEqual(row[field], oracle[field], delta=1e-11)
            self.assertFalse(row["target_reached"])
        self.assertEqual(result["strategy"], fixed["strategy"])

    def test_zero_weight_checkpoints_are_not_evaluated(self):
        with patch.object(solver, "evaluate_public_profile",
                          wraps=solver.evaluate_public_profile) as evaluate:
            result = solver.solve_preflop(SB, BB, **KWARGS, **OPTIONS,
                iterations=10, averaging_delay=8, target_nash_conv=10,
                convergence_check_interval=2)
        self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(result["completed_iterations"], 10)
        self.assertEqual(len(result["convergence_checkpoints"]), 1)
        self.assertEqual(result["vector_work_budget"]["checkpoint_count_upper_bound"], 5)
        self.assertEqual(result["vector_work_budget"]["checkpoint_diagnostics_upper_bound"], 1)

    def test_validation_and_full_ceiling_admission_precede_training(self):
        bad_targets = (True, False, None, 0, -1, math.nan, math.inf, "0.1", 10**1000)
        for target in bad_targets:
            with self.subTest(target=str(target)[:20]):
                with patch.object(solver, "_enumerate_physical_worlds") as worlds:
                    with self.assertRaisesRegex(ValueError, "Convergence"):
                        solver.solve_preflop(SB, BB, **KWARGS, **OPTIONS,
                            iterations=20, averaging_delay=5, target_nash_conv=target,
                            convergence_check_interval=10)
                    worlds.assert_not_called()
        for interval in (None, True, 0, -1, 1.5):
            with patch.object(solver, "_enumerate_physical_worlds") as worlds:
                with self.assertRaisesRegex(ValueError, "Convergence"):
                    solver.solve_preflop(SB, BB, **KWARGS, **OPTIONS,
                        iterations=20, averaging_delay=5, target_nash_conv=.01,
                        convergence_check_interval=interval)
                worlds.assert_not_called()
        for override in ({"averaging_delay": 0}, {"resource_model": "world"}):
            options = dict(OPTIONS, averaging_delay=5)
            options.update(override)
            with patch.object(solver, "_enumerate_physical_worlds") as worlds:
                with self.assertRaisesRegex(ValueError, "Convergence"):
                    solver.solve_preflop(SB, BB, **KWARGS, **options,
                        iterations=20, target_nash_conv=.01, convergence_check_interval=10)
                worlds.assert_not_called()
        with patch.object(budget, "MAX_TOTAL_LOOP_ENTRIES", 1):
            with patch.object(solver, "_positive_pot_training_view") as view:
                with patch.object(solver, "train_delayed_public_cfrplus") as train:
                    with self.assertRaisesRegex(ValueError, "loop entries"):
                        solver.solve_preflop(SB, BB, **KWARGS, **OPTIONS,
                            iterations=20, averaging_delay=5, target_nash_conv=10,
                            convergence_check_interval=10)
                    view.assert_not_called()
                    train.assert_not_called()

    def test_likely_early_stop_cannot_bypass_full_ceiling_and_check_admission(self):
        fixed = solver.solve_preflop(SB, BB, **KWARGS, **OPTIONS,
                                    iterations=35, averaging_delay=5)
        fixed_bound = fixed["vector_work_budget"]["total_loop_entries_upper_bound"]
        # The fixed ceiling fits; even a loose target that would stop at ten
        # must first admit the full ceiling plus its possible exact checks.
        with patch.object(budget, "MAX_TOTAL_LOOP_ENTRIES", fixed_bound):
            with patch.object(solver, "_positive_pot_training_view") as view:
                with patch.object(solver, "train_delayed_public_cfrplus") as train:
                    with self.assertRaisesRegex(ValueError, "loop entries"):
                        solver.solve_preflop(SB, BB, **KWARGS, **OPTIONS,
                            iterations=35, averaging_delay=5, target_nash_conv=10,
                            convergence_check_interval=10)
                    view.assert_not_called()
                    train.assert_not_called()

    def test_padding_fail_closed_and_terminal_game(self):
        with patch.object(solver, "evaluate_public_profile", return_value=(0.0, 0.1, 0.0)):
            result = solver.solve_preflop(SB, BB, **KWARGS, **OPTIONS,
                iterations=20, averaging_delay=5, target_nash_conv=0.1,
                convergence_check_interval=10)
        self.assertFalse(result["convergence_target_reached"])
        self.assertEqual(result["completed_iterations"], 20)
        with patch.object(solver, "evaluate_public_profile", return_value=(math.nan, 0.0, 0.0)):
            with self.assertRaisesRegex(ValueError, "nonfinite"):
                solver.solve_preflop(SB, BB, **KWARGS, **OPTIONS,
                    iterations=20, averaging_delay=5, target_nash_conv=10,
                    convergence_check_interval=10)
        kwargs = {"config": {"starting_stack": [0.5, 20], "max_raises": 0},
                  "runouts": ("2c3c4d7h8h",)}
        with patch.object(solver, "train_delayed_public_cfrplus") as train:
            result = solver.solve_preflop("AsAd", "KsKd", **kwargs, **OPTIONS,
                iterations=20, averaging_delay=5, target_nash_conv=.01,
                convergence_check_interval=10)
        train.assert_not_called()
        self.assertEqual(result["completed_iterations"], 0)
        self.assertEqual(result["training_passes"], 0)
        self.assertEqual(len(result["convergence_checkpoints"]), 1)
        self.assertEqual(result["vector_work_budget"]["diagnostic_evaluations_upper_bound"], 1)
        self.assertTrue(result["convergence_target_reached"])
        compare_result(result, replay_policy(result, "AsAd", "KsKd", **kwargs))


if __name__ == "__main__":
    unittest.main()
