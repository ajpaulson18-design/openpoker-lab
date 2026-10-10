import math
import unittest
from collections import defaultdict
from collections.abc import Sequence
from unittest.mock import patch

from pokerlab import preflop_future_groups as grouping
from pokerlab import preflop_solver as solver


class _NoReadSequence(Sequence):
    def __init__(self, size):
        self.size = size
        self.reads = 0

    def __len__(self):
        return self.size

    def __getitem__(self, index):
        self.reads += 1
        raise AssertionError("estimator read a row before rejecting its cap")


class FutureGroupingTests(unittest.TestCase):
    def setUp(self):
        self.worlds = [
            (2, 9, 0.1, 1, "2c3c4d", "7h", "8h"),
            (2, 9, 0.2, -1, "2c3c4d", "Kc", "8s"),
            (2, 9, 0.3, 1, "2c3c4d", "8s", "Kc"),
            (2, 9, 0.4, 0, "2c3c4d", "7d", "8d"),
            (5, 7, 0.5, 1, "2c3c4d", "9h", "Th"),
            (2, 9, 0.6, 0, "5h6sJc", "7h", "8h"),
            (2, 9, 0.7, -1, "5h6sJc", "9d", "Td"),
        ]

    def test_groups_mass_sign_ties_blockers_order_and_unequal_priors(self):
        estimate = grouping.estimate_future_grouping(self.worlds)
        grouped = grouping.group_hidden_futures(self.worlds)
        self.assertEqual(estimate["physical_world_count"], len(self.worlds))
        self.assertEqual(estimate["grouped_rows_upper_bound"], len(self.worlds))
        self.assertEqual(estimate["grouping_reference_slot_limit"],
                         grouping.MAX_GROUP_REFERENCE_SLOTS)
        self.assertEqual(estimate["grouping_reference_slots_upper_bound"],
                         128 + 22 * len(self.worlds))
        self.assertLessEqual(len(grouped), estimate["grouped_rows_upper_bound"])
        self.assertEqual(
            [(row[0], row[1], row[4], row[3]) for row in grouped],
            [(2, 9, "2c3c4d", 1), (2, 9, "2c3c4d", -1),
             (2, 9, "2c3c4d", 0), (5, 7, "2c3c4d", 1),
             (2, 9, "5h6sJc", 0), (2, 9, "5h6sJc", -1)],
        )
        self.assertAlmostEqual(sum(row[2] for row in grouped),
                               sum(row[2] for row in self.worlds), places=15)
        self.assertEqual({row[3] for row in grouped}, {-1, 0, 1})

        original_stats = defaultdict(lambda: [[], []])
        grouped_stats = defaultdict(lambda: [[], []])
        for sb, bb, mass, sign, flop, _turn, _river in self.worlds:
            original_stats[(sb, bb, flop)][0].append(mass)
            original_stats[(sb, bb, flop)][1].append(mass * sign)
        for sb, bb, mass, sign, flop in grouped:
            grouped_stats[(sb, bb, flop)][0].append(mass)
            grouped_stats[(sb, bb, flop)][1].append(mass * sign)
        self.assertEqual(original_stats.keys(), grouped_stats.keys())
        for key in original_stats:
            self.assertAlmostEqual(math.fsum(original_stats[key][0]),
                                   math.fsum(grouped_stats[key][0]), delta=1e-15)
            self.assertAlmostEqual(math.fsum(original_stats[key][1]),
                                   math.fsum(grouped_stats[key][1]), delta=1e-15)
        self.assertAlmostEqual(sum(row[2] for row in grouped), 2.8, places=15)

    def test_blocked_physical_outcomes_are_not_reintroduced(self):
        runouts = ("As2c3c4c5c", "2d3d4d5d6d")
        worlds = solver._enumerate_physical_worlds(
            "AsAd,QsQd", "KsKd,JhJc", runouts, 1)[1]
        grouped = grouping.group_hidden_futures(worlds)
        expected_keys = {(row[0], row[1], row[4], row[3]) for row in worlds}
        actual_keys = {(row[0], row[1], row[4], row[3]) for row in grouped}
        self.assertEqual(actual_keys, expected_keys)
        self.assertEqual(len(worlds), 6)
        self.assertEqual(len(grouped), 6)
        self.assertFalse(any(row[0] == 0 and row[4] == "As2c3c"
                             for row in grouped))
        self.assertAlmostEqual(sum(row[2] for row in grouped), 1.0, places=14)

    def test_estimate_is_allocation_free_before_row_caps(self):
        source = _NoReadSequence(5)
        with patch.object(grouping, "MAX_GROUP_ROWS", 4):
            with self.assertRaisesRegex(ValueError, "row cap"):
                grouping.estimate_future_grouping(source)
        self.assertEqual(source.reads, 0)
        with patch.object(grouping, "MAX_GROUP_REFERENCE_SLOTS", 200):
            with self.assertRaisesRegex(ValueError, "reference-slot cap"):
                grouping.estimate_future_grouping(source)
        self.assertEqual(source.reads, 0)

    def test_group_function_rejects_caps_before_reading_or_allocating_groups(self):
        source = _NoReadSequence(5)
        with patch.object(grouping, "MAX_GROUP_ROWS", 4):
            with self.assertRaisesRegex(ValueError, "row cap"):
                grouping.group_hidden_futures(source)
        self.assertEqual(source.reads, 0)
        with patch.object(grouping, "MAX_GROUP_REFERENCE_SLOTS", 200):
            with self.assertRaisesRegex(ValueError, "reference-slot cap"):
                grouping.group_hidden_futures(source)
        self.assertEqual(source.reads, 0)

    def test_malformed_rows_reject_before_group_map_and_signs_stay_categorical(self):
        for bad in (
            (True, 1, 0.5, 1, "2c3c4d", "7h", "8h"),
            (1, 2, float("nan"), 1, "2c3c4d", "7h", "8h"),
            (1, 2, 0.5, 0.5, "2c3c4d", "7h", "8h"),
            (1, 2, 0.5, 1, [], "7h", "8h"),
            (1, 2, 0.5, 1, "2c3c4d", "7h", "8h", "extra"),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                grouping.group_hidden_futures([bad])
        grouped = grouping.group_hidden_futures([
            (1, 2, 0.125, -1, "f", "t1", "r1"),
            (1, 2, 0.375, 1, "f", "t2", "r2"),
        ])
        self.assertEqual([row[3] for row in grouped], [-1, 1])
        self.assertNotIn(0.5, [row[3] for row in grouped])
        unequal = grouping.group_hidden_futures([
            (1, 2, 1e16, 1, "f", "a", "b"),
            (1, 2, 1.0, 1, "f", "c", "d"),
            (1, 2, 1.0, 1, "f", "e", "f"),
        ])
        self.assertEqual(unequal[0][2], math.fsum((1e16, 1.0, 1.0)))


if __name__ == "__main__":
    unittest.main()
