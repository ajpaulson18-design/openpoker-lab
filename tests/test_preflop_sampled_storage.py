import math
import unittest
from unittest.mock import patch

from pokerlab import preflop_sampled_storage as storage


def world(weight):
    return ("sb", "bb", weight)


class PreflopSampledStorageTests(unittest.TestCase):
    def test_uniform_weights_have_hand_computable_bound(self):
        report = storage.estimate_sampler_storage([world(0.25)] * 4)
        self.assertEqual(report["sampler_entries"], 4)
        self.assertEqual(report["positive_weight_entries"], 4)
        self.assertEqual(report["common_denominator_exponent"], 2)
        self.assertEqual(report["cdf_integer_width_upper_bound"], 3)
        self.assertEqual(report["logical_cdf_bits_upper_bound"], 12)

    def test_unequal_and_zero_weights_keep_zero_rows_in_storage_count(self):
        report = storage.estimate_sampler_storage(
            [world(0.5), world(0.25), world(0.0), world(0.25)]
        )
        self.assertEqual(report["sampler_entries"], 4)
        self.assertEqual(report["positive_weight_entries"], 3)
        self.assertEqual(report["common_denominator_exponent"], 2)
        self.assertEqual(report["cdf_integer_width_upper_bound"], 4)
        self.assertEqual(report["logical_cdf_bits_upper_bound"], 16)

    def test_subnormal_weight_remains_positive_in_exact_ratio_bound(self):
        smallest = math.ulp(0.0)
        report = storage.estimate_sampler_storage([world(1.0), world(smallest)])
        self.assertEqual(report["common_denominator_exponent"], 1074)
        self.assertEqual(report["positive_weight_entries"], 2)
        self.assertEqual(report["cdf_integer_width_upper_bound"], 1076)
        self.assertEqual(report["logical_cdf_bits_upper_bound"], 2152)

    def test_row_cap_rejects_before_accessing_any_weight(self):
        class UnreadableSizedWorlds:
            def __len__(self):
                return 3

            def __getitem__(self, index):
                raise AssertionError("weight rows must not be accessed")

        with patch.object(storage, "MAX_SAMPLER_ENTRIES", 2):
            with self.assertRaisesRegex(ValueError, "CDF entries"):
                storage.estimate_sampler_storage(UnreadableSizedWorlds())

    def test_bit_cap_rejects_estimate_without_constructing_cdf(self):
        with patch.object(storage, "MAX_SAMPLER_CDF_BITS", 1):
            with self.assertRaisesRegex(ValueError, "logical CDF bits"):
                storage.estimate_sampler_storage([world(0.5), world(0.5)])

    def test_rejects_empty_and_all_zero_weight_sequences(self):
        for rows in ([], [world(0.0), world(0)]):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, "positive total mass|at least one"):
                storage.estimate_sampler_storage(rows)

    def test_rejects_invalid_weight_values(self):
        for weight in (True, -1, -0.1, math.nan, math.inf, -math.inf, "0.5", 10**10000):
            with self.subTest(weight=type(weight).__name__), self.assertRaises(ValueError):
                storage.estimate_sampler_storage([world(weight)])

    def test_report_names_logical_scope_and_limits(self):
        report = storage.estimate_sampler_storage([world(1)])
        self.assertEqual(report["sampler_entry_limit"], 250_000)
        self.assertEqual(report["logical_cdf_bit_limit"], 128_000_000)
        self.assertIn("not Python allocated bytes or RSS", report["scope"])
        self.assertIn("object overhead", report["scope"])


if __name__ == "__main__":
    unittest.main()
