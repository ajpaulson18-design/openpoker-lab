"""Whole-snapshot checks for the sequential two-epoch math reference."""
from dataclasses import replace
from fractions import Fraction
import unittest

from tests.virtual_frozen_sample_reference import admit_sampled_board, build_sampled_reference_context
from tests.virtual_sparse_epoch_reference import (
    apply_epoch, implicit_uniform, observe_zero_target_prefix_averages,
)
from tests.virtual_sparse_two_epoch_reference import two_epochs
from tests.virtual_dyadic_training_reference import Fixture, Q


class SparseTwoEpochReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = Fixture()
        cls.context = build_sampled_reference_context()
        cls.first = (16, 17, 32, 33, 35)
        cls.second = (17, 24, 33, 35, 37)
        for board in (cls.first, cls.second):
            if not admit_sampled_board(cls.context, board, "uniform").compatible_pairs:
                raise AssertionError("pinned positive selector board lost target support")
        cls.zero = next(board for board in cls.context.physical.proposals
                        if not admit_sampled_board(cls.context, board, "uniform").compatible_pairs)

    def _assert_matches_sequential_reference(self, first, second):
        initial, observations = two_epochs(self.fixture, self.context, first, second)
        self.assertEqual(len(observations), 2)
        self.assertEqual(initial.epoch, 0)
        state = initial
        for board, observation in zip((first, second), observations):
            admission = admit_sampled_board(self.context, board, "uniform")
            if admission.compatible_pairs:
                expected = apply_epoch(self.fixture, self.context, state, board)
            else:
                expected = observe_zero_target_prefix_averages(self.fixture, self.context, state, board)
                expected = replace(expected, epoch=state.epoch + 1)
            actual = observation["state"]
            self.assertEqual(actual.epoch, state.epoch + 1)
            self.assertEqual(dict(actual.regrets), dict(expected.regrets))
            self.assertEqual(dict(actual.averages), dict(expected.averages))
            self.assertEqual(dict(actual.policy), dict(expected.policy))
            self.assertEqual(len(actual.regrets), 24_420)
            self.assertEqual(len(actual.averages), 24_420)
            self.assertEqual(len(actual.policy), 24_420)
            self.assertIsInstance(observation["root"], Fraction)
            self.assertGreaterEqual(observation["raw_rows"], 0)
            self.assertGreaterEqual(observation["raw_slots"], observation["raw_rows"])
            self.assertLessEqual(observation["quantized_rows"], observation["raw_rows"])
            if not admission.compatible_pairs:
                self.assertEqual(observation["quantized_rows"], 0)
                self.assertEqual(dict(actual.regrets), dict(state.regrets))
                self.assertEqual(dict(actual.policy), dict(state.policy))
            state = actual
        return initial, observations

    def test_pinned_positive_pair_uses_e1_policy_for_second_draw(self):
        _initial, observations = self._assert_matches_sequential_reference(self.first, self.second)
        expected_numeric = (440, 868)
        expected_overlays = (434, 674)
        expected_regret_bits = (638, 641)
        expected_average_bits = (373, 374)
        for index, observation in enumerate(observations):
            state = observation["state"]
            regret_values = [abs(value) for row in state.regrets.values() for value in row]
            average_values = [value for row in state.averages.values() for value in row]
            self.assertEqual(len(state.numeric_rows), expected_numeric[index])
            self.assertEqual(len(state.policy_overlays), expected_overlays[index])
            self.assertEqual(max(value.bit_length() for value in regret_values),
                             expected_regret_bits[index])
            self.assertEqual(max(value.bit_length() for value in average_values),
                             expected_average_bits[index])
            self.assertEqual((observation["raw_rows"], observation["raw_slots"]), (440, 1054))
        self.assertGreater(observations[0]["raw_rows"], 0)
        self.assertGreater(observations[1]["raw_rows"], 0)
        self.assertGreater(observations[0]["quantized_rows"], 0)
        self.assertGreater(observations[1]["quantized_rows"], 0)
        state0, state1 = implicit_uniform(self.fixture), observations[0]["state"]
        frozen_wrong = apply_epoch(self.fixture, self.context, state0, self.second)
        self.assertNotEqual(dict(observations[1]["state"].policy), dict(frozen_wrong.policy),
                            "epoch two must read the policy published by epoch one")
        self.assertEqual(sum(observations[1]["state"].policy[next(iter(self.fixture.menus))]), Q)

    def test_reverse_and_repeated_positive_boards(self):
        self._assert_matches_sequential_reference(self.second, self.first)
        self._assert_matches_sequential_reference(self.first, self.first)

    def test_zero_second_and_zero_first_preserve_regrets_but_allow_prefix_average(self):
        _initial, positive_then_zero = self._assert_matches_sequential_reference(self.first, self.zero)
        self.assertEqual(positive_then_zero[1]["root"], 0)
        self.assertEqual(positive_then_zero[1]["quantized_rows"], 0)
        _initial, zero_then_positive = self._assert_matches_sequential_reference(self.zero, self.first)
        self.assertEqual(zero_then_positive[0]["root"], 0)
        self.assertEqual(zero_then_positive[0]["quantized_rows"], 0)
        zero_state = zero_then_positive[0]["state"]
        self.assertTrue(any(zero_state.averages[key] != (0,) * len(self.fixture.menus[key])
                            for key in self.fixture.menus if key[2] == ()),
                        "zero-target board contributes at least a preflop prefix average")

    def test_observation_wire_shape_is_compact_and_exact(self):
        _initial, observations = two_epochs(self.fixture, self.context, self.first, self.second)
        for item in observations:
            self.assertEqual(set(item), {"state", "root", "raw_rows", "raw_slots", "quantized_rows"})
            self.assertEqual(set(item["state"].numeric_rows),
                             {key for key, (r, a) in item["state"].numeric_rows.items()
                              if any(r) or any(a)})


if __name__ == "__main__":
    unittest.main()
