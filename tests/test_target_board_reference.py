"""Exact tests for the independent target-public-board proposal oracle."""
from dataclasses import replace
from fractions import Fraction
from types import MappingProxyType
import unittest

from tests.virtual_dyadic_training_reference import Fixture
from tests.virtual_frozen_sample_reference import build_sampled_reference_context
from tests.virtual_grid_update_reference import freeze_grid
from tests.virtual_target_board_reference import (
    AVERAGE_DENOMINATOR, BOARDS_PER_EXPERIMENT, NATIVE_CALLS,
    RAW_DENOMINATOR, SECOND_MOMENT_RATIO_BOUND, TARGET_EXPERIMENTS,
    build_target_board_law, fixed_profile, new_target_budget,
    target_board_expectation, target_board_update, validate_target_board_law,
)


class TargetBoardReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = Fixture()
        cls.context = build_sampled_reference_context()

    def test_target_board_and_prefix_marginals_normalize_exactly(self):
        budget = new_target_budget(self.context)
        law = build_target_board_law(self.context, budget)
        self.assertTrue(validate_target_board_law(self.context, law))
        self.assertEqual(sum(law.board_probabilities.values(), Fraction(0)), 1)
        self.assertEqual(len(law.positive_boards), BOARDS_PER_EXPERIMENT)
        self.assertEqual(dict(law.mass_counts), {0: 2460, 3: 20, 8: 20, 18: 20})
        self.assertEqual(
            {length: sum(n for mass, n in counts.items() if mass > 0)
             for length, counts in law.prefix_mass_counts.items()},
            {0: 1, 3: 25, 4: 56, 5: 60},
        )
        self.assertEqual(
            {length: set(mass for mass in counts if mass > 0)
             for length, counts in law.prefix_mass_counts.items()},
            {0: {29}, 3: {3, 8, 18, 21, 29},
             4: {3, 8, 18, 21}, 5: {3, 8, 18}},
        )
        self.assertEqual(law.second_moment_ratio_bound, Fraction(29, 378))
        self.assertEqual(law.receipt()["q_uniform_zero_target_fraction"], Fraction(41, 42))

    def test_flop_prefix_variance_is_not_promised_to_improve(self):
        law = build_target_board_law(self.context, new_target_budget(self.context))
        rare = next(prefix for prefix, mass in law.prefix_masses[3].items() if mass == 3)
        q_target = law.prefix_probabilities[3][rare]
        q_uniform = self.context.physical.proposal_laws["uniform"]["prefix"][rare]
        self.assertEqual(q_target, Fraction(3, 290))
        self.assertEqual(q_uniform, Fraction(1, 84))
        self.assertLess(q_target, q_uniform)

    def test_zero_target_board_rejects_before_sample_operator(self):
        budget = new_target_budget(self.context)
        law = build_target_board_law(self.context, budget)
        grid = freeze_grid(self.fixture, fixed_profile(self.fixture, "uniform"))
        board = next(board for board, q in law.board_probabilities.items() if not q)
        calls_before = budget.counters.get("target_board_operator_calls", 0)
        admissions_before = budget.counters.get("grid_sample_admission_reserved", 0)
        with self.assertRaisesRegex(ValueError, "no support"):
            target_board_update(self.context, law, board, grid, budget)
        self.assertEqual(budget.counters.get("target_board_operator_calls", 0), calls_before)
        self.assertEqual(budget.counters.get("grid_sample_admission_reserved", 0), admissions_before)

    def test_replaced_prefix_probability_is_rejected(self):
        budget = new_target_budget(self.context)
        law = build_target_board_law(self.context, budget)
        changed = dict(law.prefix_probabilities[3])
        prefix = next(prefix for prefix, q in changed.items() if q)
        changed[prefix] += Fraction(1, 1_000_000)
        maps = dict(law.prefix_probabilities)
        maps[3] = MappingProxyType(changed)
        forged = replace(law, prefix_probabilities=MappingProxyType(maps))
        with self.assertRaisesRegex(ValueError, "maps were replaced"):
            validate_target_board_law(self.context, forged)

    def test_both_frozen_profiles_match_every_literal_r_a_slot(self):
        total_board_calls = 0
        for profile_name in ("uniform", "zero-skew"):
            with self.subTest(profile=profile_name):
                policy = fixed_profile(self.fixture, profile_name)
                grid = freeze_grid(self.fixture, policy)
                budget = new_target_budget(self.context)
                law = build_target_board_law(self.context, budget)
                result = target_board_expectation(self.fixture, self.context, law, grid, budget)
                self.assertTrue(result["literal_expectation_match"])
                self.assertEqual((result["rows"], result["slots"]), (24_420, 58_164))
                self.assertEqual(result["board_calls"], BOARDS_PER_EXPERIMENT)
                self.assertLessEqual(result["maximum_sample_regret_integer_bits"], 704)
                self.assertLessEqual(result["maximum_sample_average_integer_bits"], 704)
                self.assertLessEqual(result["maximum_expected_regret_integer_bits"], 704)
                self.assertLessEqual(result["maximum_expected_average_integer_bits"], 704)
                self.assertLessEqual(result["maximum_pointwise_regret_second_moment_ratio"],
                                     SECOND_MOMENT_RATIO_BOUND)
                self.assertLessEqual(result["aggregate_regret_second_moment_ratio"],
                                     SECOND_MOMENT_RATIO_BOUND)
                for row in result["regrets"].values():
                    self.assertTrue(all((value * RAW_DENOMINATOR).denominator == 1 for value in row))
                for row in result["averages"].values():
                    self.assertTrue(all((value * AVERAGE_DENOMINATOR).denominator == 1 for value in row))
                self.assertEqual(result["native_calls"], NATIVE_CALLS)
                self.assertEqual(result["rng_calls"], 0)
                self.assertEqual(result["training_iterations"], 0)
                self.assertIsNone(result["quality_gate"])
                self.assertLessEqual(result["resource_accounting"]["work"], 500_000_000)
                self.assertLessEqual(result["resource_accounting"]["entries"], 8_000_000)
                self.assertLessEqual(result["resource_accounting"]["created_bits"],
                                     16_000_000_000)
                total_board_calls += result["board_calls"]
        self.assertEqual(TARGET_EXPERIMENTS, 2)
        self.assertEqual(total_board_calls, 120)


if __name__ == "__main__":
    unittest.main()
