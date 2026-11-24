"""Independent weighted chance-law gates; no RNG or native/solver execution."""
from dataclasses import replace
from fractions import Fraction
from itertools import combinations
import struct
from unittest.mock import patch
import unittest

from tests.full_deck_public_chance_reference import PROOF9
from tests.virtual_joint_sample_reference import build_law as old_n9_law, ticket as old_n9_ticket
from tests.virtual_weighted_joint_reference import (
    LIMITS, MAX_HANDS, MAX_PRIVATE_QUERIES, U64_MAX,
    build_law, dense_hand_index, forecast,
)


def bits(number):
    return int.from_bytes(struct.pack('>d', number), 'big')


def n9_ranges():
    return ((((43, 48), bits(.125)), ((32, 43), bits(.75))),
            (((24, 37), bits(.375)), ((16, 32), bits(1.))))


def full_ranges(weighted=False):
    # One immutable ordered holding inventory; no private-pair or public-world
    # product is constructed by this input factory.
    hands = tuple(combinations(range(52), 2))
    side = tuple((hand, bits(float(index % 7 + 1) if weighted else 1.)) for index, hand in enumerate(hands))
    return hands, (side, side)


class WeightedJointReferenceTests(unittest.TestCase):
    def test_dense_pair_formula_matches_every_physical_holding(self):
        count = 0
        for index, hand in enumerate(combinations(range(52), 2)):
            self.assertEqual(dense_hand_index(hand), index)
            count += 1
        self.assertEqual(count, MAX_HANDS)
        self.assertEqual(dense_hand_index((50, 51)), 1325)

    def test_all580_n9_tickets_preserve_accepted_original_indices_and_boards(self):
        law = build_law(tuple(PROOF9), n9_ranges())
        accepted = old_n9_law()
        self.assertEqual((law.weights, law.compatible_masses, law.cdf, law.normalizer),
                         (((1, 6), (3, 8)), (11, 3), (11, 29), 29))
        self.assertEqual(law.pair_product_sum(), 29)
        observed = 0
        for private in range(29):
            for rank in range(20):
                expected = old_n9_ticket(accepted, private, rank)
                actual = law.decode(private, rank, with_sign=False)
                self.assertEqual((actual.holding_indices, actual.board, actual.integer_mass),
                                 (expected.holdings, expected.board, expected.mass))
                self.assertEqual(actual.probability, Fraction(expected.mass, 580))
                self.assertIsNone(actual.showdown_sign)
                observed += 1
        self.assertEqual(observed, 580)
        self.assertEqual((law.receipt()['world_queries'], law.receipt()['private_queries']), (580, 580))
        self.assertFalse(law.receipt()['retained_pair_table'])

    def test_odd_common_scaling_and_original_row_reordering(self):
        a = ((((43, 48), bits(1.)), ((32, 43), bits(5.))),
             (((24, 37), bits(1.)), ((16, 32), bits(3.))))
        b = ((((43, 48), bits(3.)), ((32, 43), bits(15.))),
             (((24, 37), bits(7.)), ((16, 32), bits(21.))))
        first = build_law(tuple(PROOF9), a); scaled = build_law(tuple(PROOF9), b)
        self.assertEqual((first.weights, first.cdf, first.normalizer), (scaled.weights, scaled.cdf, scaled.normalizer))
        self.assertEqual(tuple(item.aligned_gcd for item in scaled.normalization), (3, 7))
        for private in range(first.normalizer):
            self.assertEqual(first.select_pair(private), scaled.select_pair(private))
        reordered = build_law(tuple(PROOF9), (a[0][::-1], a[1][::-1]))
        for private in range(reordered.normalizer):
            selected = reordered.select_pair(private)
            for actor, original in enumerate(selected.holding_indices):
                self.assertEqual(selected.holdings[actor], reordered.ranges[actor][original][0])
            # Original index zero now identifies the former final source row.
            self.assertEqual(reordered.ranges[0][0][0], (32, 43))
        self.assertNotEqual(reordered.ranges, first.ranges)

    def test_all_minimum_subnormal_priors_have_exact_scale_invariant_law(self):
        regular = tuple(tuple((hand, bits(1.)) for hand, _raw in side) for side in n9_ranges())
        tiny = tuple(tuple((hand, 1) for hand, _raw in side) for side in n9_ranges())
        first = build_law(tuple(PROOF9), regular); second = build_law(tuple(PROOF9), tiny)
        self.assertEqual((first.weights, first.cdf, first.normalizer), (second.weights, second.cdf, second.normalizer))
        self.assertEqual(second.weights, ((1, 1), (1, 1)))
        for item in second.normalization:
            self.assertEqual(item.denominator_lcm, 1 << 1074)
            self.assertEqual(item.scale, Fraction(1, 1 << 1074))
        for private in range(first.normalizer):
            self.assertEqual(first.decode(private, 19), second.decode(private, 19))

    def test_positive_zero_compatible_row_keeps_original_index_and_repeated_cdf(self):
        ranges = ((((0, 1), bits(float(1 << 63))), ((2, 3), bits(1.))),
                  (((0, 4), bits(1.)),))
        law = build_law(tuple(range(52)), ranges)
        self.assertEqual(law.weights, ((1 << 63, 1), (1,)))
        self.assertEqual((law.compatible_masses, law.cdf, law.normalizer), ((0, 1), (0, 1), 1))
        selected = law.select_pair(0)
        self.assertEqual(selected.holding_indices, (1, 0))
        self.assertEqual(selected.holdings, ((2, 3), (0, 4)))
        self.assertEqual(law.ranges[0][0], ranges[0][0])

    def test_normalized_width_and_normalizer_limits_reject_without_cap_lift(self):
        too_wide = ((((0, 1), bits(1.)), ((2, 3), bits(float(1 << 64)))),
                    (((4, 5), bits(1.)),))
        with self.assertRaisesRegex(ValueError, 'normalized prior exceeds64bits'):
            build_law(tuple(range(52)), too_wide)
        huge_z = ((((0, 1), bits(float(1 << 63))), ((2, 3), bits(1.))),
                  (((4, 5), bits(float(1 << 63))), ((6, 7), bits(1.))))
        with self.assertRaisesRegex(ValueError, 'normalizer zero or exceeds64bits'):
            build_law(tuple(range(52)), huge_z)
        # Max finite alongside min-subnormal produces a <=2150-bit aligned
        # oracle integer, then fails the normalized-u64 contract before pairs.
        extreme = ((((0, 1), 1), ((2, 3), 0x7fefffffffffffff)), (((4, 5), bits(1.)),))
        with self.assertRaisesRegex(ValueError, 'normalized prior exceeds64bits'):
            build_law(tuple(range(52)), extreme)

    def test_invalid_weights_holdings_decks_and_empty_ranges_reject(self):
        valid = n9_ranges()
        for raw in (0, 1 << 63, bits(-1.), 0x7ff0000000000000, 0xfff0000000000000,
                    0x7ff8000000000001, -1, U64_MAX + 1, True):
            with self.subTest(weight=raw), self.assertRaises(ValueError):
                build_law(tuple(PROOF9), ((((43, 48), raw),), valid[1]))
        for hand in ((43, 43), (48, 43), (0, 43), (43,), [43, 48]):
            with self.subTest(hand=hand), self.assertRaises(ValueError):
                build_law(tuple(PROOF9), (((hand, bits(1.)),), valid[1]))
        with self.assertRaisesRegex(ValueError, 'duplicate physical holding'):
            build_law(tuple(PROOF9), ((valid[0][0], valid[0][0]), valid[1]))
        for deck in (tuple(range(10)), tuple(reversed(PROOF9)), [*PROOF9], tuple(float(card) for card in PROOF9)):
            with self.subTest(deck=deck), self.assertRaises(ValueError):
                build_law(deck, valid)
        for ranges in (((), valid[1]), [valid[0], valid[1]], (valid[0],)):
            with self.subTest(ranges=ranges), self.assertRaises(ValueError):
                build_law(tuple(PROOF9), ranges)
        with self.assertRaisesRegex(ValueError, 'normalizer zero'):
            build_law(tuple(range(52)), ((((0, 1), bits(1.)),), (((1, 2), bits(1.)),)))

    def test_complete_reduce_only_preflight_precedes_binary64_decode(self):
        plan = forecast(52, (1326, 1326))
        self.assertEqual((plan['work'], plan['created_bits'], plan['entries']),
                         (446_859_648, 14_737_379_904, 212_464))
        self.assertEqual(plan['pair_cells_retained'], 0)
        self.assertEqual(plan['streamed_pairs_per_census'], 1_758_276)
        for key in LIMITS:
            self.assertLessEqual(plan[key], LIMITS[key])
        small = forecast(9, (2, 2))
        for key in LIMITS:
            with self.subTest(limit=key), patch('tests.virtual_weighted_joint_reference.struct.unpack') as decoder:
                with self.assertRaisesRegex(ValueError, 'admission rejected'):
                    build_law(tuple(PROOF9), n9_ranges(), {key: small[key] - 1})
                decoder.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'reduce-only'):
            build_law(tuple(PROOF9), n9_ranges(), {'work': LIMITS['work'] + 1})

    def _full_cdf_boundaries(self, law, hands):
        previous = 0
        for index, end in enumerate(law.cdf):
            self.assertGreater(end, previous)
            first, last = law.select_pair(previous), law.select_pair(end - 1)
            self.assertEqual(first.holding_indices[0], index)
            self.assertEqual(last.holding_indices[0], index)
            rest = tuple(card for card in range(52) if card not in hands[index])
            self.assertEqual(first.holdings[1], rest[:2])
            self.assertEqual(last.holdings[1], rest[-2:])
            self.assertEqual(hands[first.holding_indices[1]], first.holdings[1])
            self.assertEqual(hands[last.holding_indices[1]], last.holdings[1])
            previous = end
        self.assertEqual(previous, law.normalizer)

    def _full_boards(self, law):
        count = law.receipt()['forecast']['board_count']
        ranks = tuple((count - 1) * index // 30 for index in range(31))
        self.assertEqual(len(set(ranks)), 31)
        for index, rank in enumerate(ranks):
            private = (law.normalizer - 1) * index // 30
            sample = law.decode(private, rank)
            self.assertEqual((sample.private_ticket, sample.board_rank), (private, rank))
            self.assertEqual(len(set(sample.board)), 5)
            self.assertEqual(tuple(sorted(sample.board[:3])), sample.board[:3])
            self.assertTrue(set((*sample.holdings[0], *sample.holdings[1])).isdisjoint(sample.board))
            self.assertIn(sample.showdown_sign, (-1, 0, 1))
            self.assertEqual(sample.probability, Fraction(sample.integer_mass, law.normalizer * 34_246_080))

    def test_full52_uniform_pair_census_and_all1326_original_cdf_boundaries(self):
        hands, ranges = full_ranges()
        law = build_law(tuple(range(52)), ranges)
        self.assertEqual(law.normalizer, 1_624_350)
        self.assertEqual(law.compatible_masses, (1225,) * 1326)
        self.assertEqual(law.cdf, tuple(1225 * (index + 1) for index in range(1326)))
        self.assertEqual(law.pair_product_sum(), law.normalizer)
        self._full_cdf_boundaries(law, hands)
        self._full_boards(law)
        self.assertEqual(law.prefix_probability((0, 1, 2)), Fraction(1, 22100))
        receipt = law.receipt()
        self.assertEqual(receipt['private_queries'], 2652 + 31)
        self.assertEqual(receipt['literal_pair_visits'], 3 * 1_758_276)
        self.assertFalse(receipt['retained_pair_table'])
        for key in LIMITS:
            actual_key = 'max_forecast_bits' if key == 'integer_bits' else key
            self.assertLessEqual(receipt[actual_key], LIMITS[key])

    def test_full52_nonuniform_one_to_seven_weights_literal_product_and_queries(self):
        hands, ranges = full_ranges(weighted=True)
        law = build_law(tuple(range(52)), ranges)
        self.assertEqual(law.weights[0], tuple(index % 7 + 1 for index in range(1326)))
        self.assertEqual(law.pair_product_sum(), law.normalizer)
        self._full_cdf_boundaries(law, hands)
        self._full_boards(law)
        for index in range(31):
            selected = law.select_pair((law.normalizer - 1) * index // 30)
            own, opposite = selected.holding_indices
            self.assertEqual(selected.integer_mass, law.weights[0][own] * law.weights[1][opposite])
        self.assertEqual(law.prefix_probability((), actor=0, holding=0),
                         Fraction(law.weights[0][0] * law.compatible_masses[0], law.normalizer))
        self.assertLess(law.receipt()['private_queries'], MAX_PRIVATE_QUERIES)
        self.assertEqual((law.receipt()['rng_calls'], law.receipt()['native_calls']), (0, 0))

    def test_n9_prefix_probabilities_and_invalid_or_forged_ticket_queries(self):
        law = build_law(tuple(PROOF9), n9_ranges())
        self.assertEqual(law.prefix_probability(()), 1)
        self.assertEqual(law.prefix_probability((), actor=0, holding=0), Fraction(11, 29))
        sample = law.decode(0, 0)
        self.assertEqual(law.prefix_probability(sample.board), Fraction(3, 580))
        self.assertEqual(law.prefix_probability(sample.board[:3]), Fraction(3, 290))
        for ticket in (-1, law.normalizer, True):
            with self.assertRaisesRegex(ValueError, 'private ticket'):
                law.select_pair(ticket)
        for rank in (-1, 20, True):
            with self.assertRaises(ValueError):
                law.decode(0, rank)
        with self.assertRaisesRegex(ValueError, 'immutable law snapshot'):
            replace(law, normalizer=1).select_pair(0)
        with self.assertRaisesRegex(ValueError, 'prefix_queries limit'):
            law.prefix_probability(())

    def test_private_query_limit_is_cumulative_and_does_not_reset_per_call(self):
        law = build_law(tuple(PROOF9), n9_ranges())
        for _ in range(MAX_PRIVATE_QUERIES):
            self.assertEqual(law.select_pair(0).holding_indices, (0, 0))
        with self.assertRaisesRegex(ValueError, 'private_queries limit'):
            law.select_pair(0)
        self.assertEqual(law.receipt()['private_queries'], MAX_PRIVATE_QUERIES)


if __name__ == '__main__':
    unittest.main()
