"""Independent physical marginal census and occupancy interval controls."""
from collections import Counter
from fractions import Fraction
from itertools import combinations, permutations
import unittest

from scripts.forecast_joint_learning_lifetime import occupancy_bounds, uniform_cells, forecast


class JointLearningLifetimeTests(unittest.TestCase):
    def test_every_nine_card_physical_world_has_uniform_own_visible_marginals(self):
        counts = [[Counter() for _ in range(4)] for _ in range(2)]; worlds = 0
        deck = set(range(9))
        for sb in combinations(range(9), 2):
            for bb in combinations(sorted(deck - set(sb)), 2):
                unseen = deck - set(sb) - set(bb)
                for flop in combinations(sorted(unseen), 3):
                    for suffix in permutations(sorted(unseen - set(flop))):
                        board = (*flop, *suffix); worlds += 1
                        for actor, hand in enumerate((sb, bb)):
                            for street, size in enumerate((0, 3, 4, 5)):
                                counts[actor][street][hand, board[:size]] += 1
        self.assertEqual(worlds, 15120)
        _public, information = uniform_cells(9)
        for actor in (0, 1):
            for k, counter in zip(information, counts[actor]):
                self.assertEqual(len(counter), k)
                self.assertEqual(set(counter.values()), {worlds // k})
        self.assertEqual(counts[0], counts[1])

    def test_rational_bounds_contain_independent_exact_occupancy(self):
        for cells in range(1, 18):
            for observations in range(20):
                exact = cells * (1 - Fraction(cells - 1, cells) ** observations)
                lower, upper = occupancy_bounds(cells, observations)
                self.assertLessEqual(lower, exact); self.assertLessEqual(exact, upper)
        for cells in (1, 1326, 25989600, 1221511200, 56189515200):
            for observations in (2, 3, 100, 1000000, 1000000000):
                lower, upper = occupancy_bounds(cells, observations)
                self.assertLessEqual(lower, upper)
                self.assertLessEqual(upper, min(cells, observations))

    def test_admission_stays_false_and_existing_width_boundary_is_exposed(self):
        report = forecast((2, 3, 100, 262143, 262144))
        for row in report['reports']:
            self.assertFalse(row['whole_request_admitted']); self.assertFalse(row['attempted_training'])
            self.assertIsNone(row['quality_gate'])
        self.assertFalse(report['reports'][1]['current_epoch_limit_allows_lifetime'])
        self.assertTrue(report['reports'][2]['catalog_expected_words_lower_exceeds_current_two_million_cap'])
        self.assertTrue(report['reports'][3]['current_numeric_widths_cover_conservative_bounds'])
        self.assertFalse(report['reports'][4]['current_numeric_widths_cover_conservative_bounds'])

    def test_invalid_or_unbounded_requests_refuse(self):
        for value in (-1, True, 1000000001):
            with self.assertRaises(ValueError):
                occupancy_bounds(1326, value)
        for counts in ((0,), (True,), (2, 2), tuple(range(1, 18))):
            with self.assertRaises(ValueError):
                forecast(counts)


if __name__ == '__main__':
    unittest.main()
