import unittest
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from pokerlab import preflop_sampled_budget as budget
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
SAMPLED = {"traversal": "chance-sampled", "resource_model": "chance-sampled",
           "diagnostics": "public-batched", "algorithm": "vanilla"}


class PreflopSampledIntegrationTests(unittest.TestCase):
    def test_repeatability_and_full_independent_weighted_policy_replay(self):
        common = dict(KWARGS, **SAMPLED, iterations=50,
                      samples_per_iteration=4, sampling_seed=17)
        left = solver.solve_preflop(SB, BB, **common)
        right = solver.solve_preflop(SB, BB, **common)
        self.assertEqual(left, right)
        oracle = replay_policy(left, SB, BB, **KWARGS)
        compare_result(left, oracle)
        self.assertEqual(oracle["checked_information_sets"], len(left["strategy"]))
        stats, bounds = left["sampling_statistics"], left["sampled_work_budget"]
        self.assertEqual(stats["world_draws"], 200)
        self.assertLessEqual(stats["actual_node_visits"], bounds["total_node_visits_upper_bound"])
        self.assertFalse(left["world_decision_work_enforced"])
        self.assertEqual(left["world_construction_admission_iterations"], 1)
        other = solver.solve_preflop(SB, BB, **dict(common, sampling_seed=18))
        self.assertNotEqual(left["strategy"], other["strategy"])
        # Numeric replay independently enforces own-hand/public-history keys,
        # including the shared hidden-future preflop and earlier-street rows.
        self.assertTrue(any(not row["revealed_board"] for row in left["strategy"]))

    def test_options_and_incompatible_algorithms_fail_before_enumeration(self):
        bad = [dict(SAMPLED, sampling_seed=True), dict(SAMPLED, sampling_seed=-1),
               dict(SAMPLED, sampling_seed=2**64), dict(SAMPLED, samples_per_iteration=0),
               dict(SAMPLED, samples_per_iteration=True),
               dict(SAMPLED, samples_per_iteration=257),
               dict(SAMPLED, samples_per_iteration=1.5),
               dict(SAMPLED, algorithm="cfrplus"), dict(SAMPLED, algorithm="dcfr"),
               dict(SAMPLED, diagnostics="recursive"),
               dict(SAMPLED, resource_model="world"),
               {"sampling_seed": 1}, {"samples_per_iteration": 2},
               {"resource_model": "chance-sampled"}]
        for options in bad:
            with self.subTest(options=options):
                with patch.object(solver, "_enumerate_physical_worlds") as enumeration:
                    with self.assertRaises(ValueError):
                        solver.solve_preflop(SB, BB, **KWARGS, iterations=10, **options)
                    enumeration.assert_not_called()

    def test_sample_work_and_exact_diagnostic_guards_precede_training_or_view(self):
        for cap in ("MAX_SAMPLED_NODE_VISITS", "MAX_SAMPLED_ACTION_CELLS"):
            with patch.object(budget, cap, 1):
                with patch.object(solver, "train_chance_sampled") as train:
                    with patch.object(solver, "_positive_pot_training_view") as view:
                        with self.assertRaisesRegex(ValueError, "Sampled training exceeds"):
                            solver.solve_preflop(SB, BB, **KWARGS, **SAMPLED, iterations=10)
                        train.assert_not_called()
                        view.assert_not_called()
        with patch.object(solver, "estimate_vector_budget", side_effect=ValueError("exact cap")):
            with patch.object(solver, "train_chance_sampled") as train:
                with patch.object(solver, "_positive_pot_training_view") as view:
                    with self.assertRaisesRegex(ValueError, "exact cap"):
                        solver.solve_preflop(SB, BB, **KWARGS, **SAMPLED, iterations=10)
                    train.assert_not_called()
                    view.assert_not_called()

    def test_mode_replaces_iterative_charge_but_retains_constructor_guard(self):
        original = solver._enumerate_physical_worlds
        with patch.object(solver, "_enumerate_physical_worlds", wraps=original) as enumeration:
            result = solver.solve_preflop(SB, BB, **KWARGS, **SAMPLED, iterations=10)
            self.assertEqual(enumeration.call_args.args[-1], 1)
            self.assertIsNone(result["limits"]["world_iterations"])
        with patch.object(solver, "_MAX_WORLD_ITERATIONS", 1):
            with patch.object(solver, "_rank_world") as rank:
                with self.assertRaisesRegex(ValueError, "world iterations"):
                    solver.solve_preflop(SB, BB, **KWARGS, **SAMPLED, iterations=10)
                rank.assert_not_called()
        with patch.object(solver, "MAX_SAMPLER_ENTRIES", 1):
            with patch.object(solver, "_rank_world") as rank:
                with self.assertRaisesRegex(ValueError, "sampler-world entry"):
                    solver.solve_preflop(SB, BB, **KWARGS, **SAMPLED, iterations=10)
                rank.assert_not_called()
        with patch.object(solver, "estimate_sampler_storage", side_effect=ValueError("CDF cap")):
            with patch.object(solver, "train_chance_sampled") as train:
                with self.assertRaisesRegex(ValueError, "CDF cap"):
                    solver.solve_preflop(SB, BB, **KWARGS, **SAMPLED, iterations=10)
                train.assert_not_called()
        with self.assertRaisesRegex(ValueError, "Full-deck preflop"):
            solver.solve_preflop(SB, BB, iterations=10, **SAMPLED)

    def test_no_information_sets_do_not_sample_and_still_verify_refunds(self):
        kwargs = {"config": {"starting_stack": [0.5, 20], "max_raises": 0},
                  "runouts": ("2c3c4d7h8h",)}
        with patch.object(solver, "train_chance_sampled") as train:
            result = solver.solve_preflop("AsAd", "KsKd", **kwargs, **SAMPLED,
                                          iterations=10, samples_per_iteration=256)
            train.assert_not_called()
        self.assertEqual(result["sampled_work_budget"]["world_draws"], 0)
        self.assertEqual(result["sampling_statistics"]["world_draws"], 0)
        compare_result(result, replay_policy(result, "AsAd", "KsKd", **kwargs))

    def test_explicit_default_sampling_options_preserve_existing_outputs(self):
        options = dict(KWARGS, iterations=10)
        old = solver.solve_preflop(SB, BB, **options)
        new = solver.solve_preflop(SB, BB, **options,
                                   sampling_seed=0, samples_per_iteration=1)
        self.assertEqual(old, new)
        self.assertNotIn("sampling_statistics", new)


if __name__ == "__main__":
    unittest.main()
