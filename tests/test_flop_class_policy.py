"""Focused tests for exact-grid compact policy output normalization."""
from fractions import Fraction
import unittest
from unittest.mock import patch

from scripts import flop_class_policy as POLICY


def _key(index=0):
    return (0, "AdAs", ("check", f"history-{index}"))


class FlopClassPolicyTests(unittest.TestCase):
    def test_every_canonical_pair_has_exact_binary_fraction_sum_one(self):
        raw = {
            _key(0): (0.1, 0.9),
            _key(1): (1.0 / 3.0, 2.0 / 3.0),
            _key(2): (0.0, 1.0),
            _key(3): (1.0, 0.0),
            _key(4): (-0.0, 1.0),
        }
        canonical, audit = POLICY.canonicalize_binary_rows(raw)
        self.assertEqual(list(canonical), list(raw))
        self.assertEqual(audit["grid_bits"], 52)
        for first, second in canonical.values():
            self.assertIs(type(first), float)
            self.assertIs(type(second), float)
            self.assertEqual(Fraction(first) + Fraction(second), 1)
        self.assertEqual(canonical[_key(2)], (0.0, 1.0))
        self.assertEqual(canonical[_key(3)], (1.0, 0.0))

    def test_tiny_positive_probability_can_be_rounded_to_zero(self):
        raw = {_key(): (2.0 ** -54, 1.0)}
        canonical, audit = POLICY.canonicalize_binary_rows(raw)
        self.assertEqual(canonical[_key()], (0.0, 1.0))
        self.assertEqual(audit["zeroed_positive_probabilities"], 1)

    def test_ties_round_to_even_on_the_52_bit_grid(self):
        # Both inputs and their complements are exactly representable floats.
        lower_even = POLICY.GRID // 2
        for lower, expected in ((lower_even, lower_even), (lower_even + 1, lower_even + 2)):
            numerator = 2 * lower + 1
            first = float(Fraction(numerator, 2 * POLICY.GRID))
            second = float(Fraction(2 * POLICY.GRID - numerator, 2 * POLICY.GRID))
            self.assertEqual(Fraction(first) + Fraction(second), 1)
            canonical, _ = POLICY.canonicalize_binary_rows({_key(): (first, second)})
            self.assertEqual(Fraction(canonical[_key()][0]), Fraction(expected, POLICY.GRID))

    def test_reports_exact_distance_bounds_and_changed_rows(self):
        raw = {_key(): (1.0 / 3.0, 2.0 / 3.0)}
        canonical, audit = POLICY.canonicalize_binary_rows(raw)
        normalized_distance = Fraction(audit["max_normalized_probability_distance"])
        raw_distance = Fraction(audit["max_raw_distance"])
        self.assertLessEqual(normalized_distance, Fraction(1, 2 ** 53))
        self.assertGreaterEqual(raw_distance, normalized_distance)
        self.assertEqual(audit["rows_changed"], int(canonical[_key()] != raw[_key()]))

    def test_input_is_not_mutated(self):
        values = [0.2, 0.8]
        raw = {_key(): values}
        before = (list(raw), list(values))
        POLICY.canonicalize_binary_rows(raw)
        self.assertEqual((list(raw), values), before)

    def test_unchanged_list_row_is_not_counted_as_changed(self):
        raw = {_key(): [0.5, 0.5]}
        canonical, audit = POLICY.canonicalize_binary_rows(raw)
        self.assertEqual(canonical[_key()], (0.5, 0.5))
        self.assertEqual(audit["rows_changed"], 0)

    def test_signed_zero_bit_change_is_counted(self):
        raw = {_key(): (-0.0, 1.0)}
        canonical, audit = POLICY.canonicalize_binary_rows(raw)
        self.assertEqual(canonical[_key()], (0.0, 1.0))
        self.assertEqual(audit["rows_changed"], 1)

    def test_rejects_malformed_keys_rows_and_probability_types(self):
        bad_inputs = (
            {(True, "AdAs", ()): (0.5, 0.5)},
            {(0, "AsAd", ()): (0.5, 0.5)},  # not canonical card order
            {(0, "AdAd", ()): (0.5, 0.5)},
            {(0, "AdAs", (1,)): (0.5, 0.5)},
            {_key(): (0.5,)},
            {_key(): (True, 0.0)},
            {_key(): (float("nan"), 0.0)},
            {_key(): (-0.1, 1.1)},
            {_key(): (0.0, 0.0)},
            {_key(): (0.4, 0.4)},
        )
        for raw in bad_inputs:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                POLICY.canonicalize_binary_rows(raw)

    def test_oversize_rejects_before_fraction_construction(self):
        raw = {_key(index): (0.5, 0.5) for index in range(POLICY.MAX_ROWS + 1)}
        with patch.object(POLICY, "Fraction", side_effect=AssertionError("too early")):
            with self.assertRaises(ValueError):
                POLICY.canonicalize_binary_rows(raw)

    def test_oversize_history_rejects_before_fraction_construction(self):
        raw = {(0, "AdAs", ("x" * (POLICY.MAX_HISTORY_TOKEN_CHARS + 1),)): (0.5, 0.5)}
        with patch.object(POLICY, "Fraction", side_effect=AssertionError("too early")):
            with self.assertRaises(ValueError):
                POLICY.canonicalize_binary_rows(raw)


if __name__ == "__main__":
    unittest.main()
