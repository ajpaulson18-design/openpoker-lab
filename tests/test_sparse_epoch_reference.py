"""Focused contracts for the independent two-epoch sparse reference."""
from fractions import Fraction
import unittest

from tests.virtual_dyadic_training_reference import Fixture, Q
from tests.virtual_frozen_sample_reference import admit_sampled_board, build_sampled_reference_context
from tests.virtual_sparse_epoch_reference import (
    AVERAGE_DENOMINATOR, MAX_AVERAGE_BITS, MAX_POSITIVE_SUM_BITS,
    MAX_REGRET_BITS, MAX_SCALED_WEIGHT_BITS, REGRET_DENOMINATOR,
    _largest_remainder, _uniform_row, apply_epoch, implicit_uniform,
    observe_zero_target_prefix_averages, run_two_positive_epochs,
)


class SparseEpochReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = Fixture()
        cls.context = build_sampled_reference_context()
        cls.positive_boards = tuple(dict.fromkeys(world.board for world in cls.fixture.worlds))
        cls.zero_boards = tuple(board for board in cls.context.physical.proposals
            if not admit_sampled_board(cls.context, board, 'uniform').compatible_pairs)

    def test_two_positive_boards_make_two_frozen_policy_transitions(self):
        self.assertGreaterEqual(len(self.positive_boards), 2)
        initial, first, second = run_two_positive_epochs(
            self.fixture, self.context, self.positive_boards[0], self.positive_boards[1])
        self.assertEqual((initial.epoch, first.epoch, second.epoch), (0, 1, 2))
        self.assertTrue(any(any(row) for row in first.regrets.values()))
        self.assertTrue(any(any(row) for row in second.regrets.values()))
        self.assertTrue(first.numeric_rows)
        self.assertTrue(second.numeric_rows)
        self.assertEqual(len(first.policy), 24_420)
        self.assertEqual(len(second.policy), 24_420)
        self.assertTrue(all(sum(units) == Q for units in second.policy.values()))
        self.assertNotEqual(first.policy, initial.policy)
        self.assertNotEqual(second.policy, first.policy)
        untouched = [key for key, menu in self.fixture.menus.items()
                     if not any(second.regrets[key]) and not any(second.averages[key])]
        self.assertTrue(untouched)
        self.assertTrue(all(second.policy[key] == _uniform_row(len(self.fixture.menus[key]))
                            for key in untouched))

    def test_zero_full_target_keeps_regret_policy_and_changes_earlier_average(self):
        board = self.zero_boards[0]
        admission = admit_sampled_board(self.context, board, 'uniform')
        self.assertFalse(admission.compatible_pairs)
        state = implicit_uniform(self.fixture)
        observed = observe_zero_target_prefix_averages(self.fixture, self.context, state, board)
        self.assertEqual(observed.epoch, state.epoch)
        self.assertEqual(observed.regrets, state.regrets)
        self.assertEqual(observed.policy, state.policy)
        self.assertTrue(any(key[2] == () and observed.averages[key] != state.averages[key]
                            for key in self.fixture.menus),
                        'zero-target public board must update a preflop average')
        self.assertFalse(any(any(row) for row in state.regrets.values()))
        self.assertTrue(all(state.policy[key] == _uniform_row(len(menu))
                            for key, menu in self.fixture.menus.items()))

    def test_unclipped_negative_regret_is_persistent_and_not_cfr_plus(self):
        initial, first, _ = run_two_positive_epochs(
            self.fixture, self.context, self.positive_boards[0], self.positive_boards[1])
        negatives = [(key, i, value) for key, row in first.regrets.items()
                     for i, value in enumerate(row) if value < 0]
        self.assertTrue(negatives, 'positive sample should retain a negative raw component')
        key, action, value = negatives[0]
        self.assertLess(value, 0)
        self.assertNotEqual(max(0, value), value, 'CFR+ clipping would erase this raw state')
        self.assertEqual(initial.regrets[key][action], 0)

    def test_exact_integer_denominators_and_conservative_widths(self):
        self.assertEqual(REGRET_DENOMINATOR, 580 << 625)
        self.assertEqual(AVERAGE_DENOMINATOR, 580 << 364)
        for divisor, proposal_denominator in ((1, 1), (10, 84), (20, 504), (20, 2520)):
            self.assertLessEqual(proposal_denominator * (20 // divisor), 2520)
            for exponent in range(313):
                raw_denominator = 29 * divisor * (1 << (exponent + 52))
                self.assertEqual(AVERAGE_DENOMINATOR % raw_denominator, 0)
                self.assertEqual(AVERAGE_DENOMINATOR // raw_denominator,
                                 (20 // divisor) << (312 - exponent))
        self.assertLess((2 * 29 * 2520) << 364, 1 << MAX_AVERAGE_BITS)
        _, first, second = run_two_positive_epochs(
            self.fixture, self.context, self.positive_boards[0], self.positive_boards[1])
        for state in (first, second):
            for key, row in state.regrets.items():
                self.assertEqual(len(row), len(self.fixture.menus[key]))
                self.assertTrue(all(abs(x).bit_length() <= MAX_REGRET_BITS for x in row))
                self.assertLessEqual(sum(max(x, 0) for x in row).bit_length(), MAX_POSITIVE_SUM_BITS)
                self.assertTrue(all((max(x, 0) * Q).bit_length() <= MAX_SCALED_WEIGHT_BITS for x in row))
            for row in state.averages.values():
                self.assertTrue(all(x >= 0 and x.bit_length() <= MAX_AVERAGE_BITS for x in row))

    def test_quantizer_fallback_ties_and_weighted_law_rejection(self):
        self.assertEqual(_largest_remainder((0, 0, 0)), _uniform_row(3))
        tied = _largest_remainder((1, 1, 1))
        self.assertEqual(tied, (Q // 3 + 1, Q // 3, Q // 3))
        state = implicit_uniform(self.fixture)
        with self.assertRaises(ValueError):
            apply_epoch(self.fixture, self.context, state, self.positive_boards[0], 'river_weighted')


if __name__ == '__main__':
    unittest.main()
