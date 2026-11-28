"""Deterministic exact-law and full-coordinate joint-sampling proof controls."""
from collections import Counter
from dataclasses import replace
from fractions import Fraction
from itertools import combinations, permutations
from unittest.mock import patch
import unittest

from tests.full_deck_public_chance_reference import PROOF9
from tests.virtual_dyadic_training_reference import Q
from tests.virtual_joint_sample_reference import (
    AVERAGE_DENOMINATOR, CREATED_BITS_UPPER, ENTRIES_UPPER, ENTRY_PARTITION, INTERMEDIATE_BITS_UPPER,
    LIMITS, MEAN_TICKETS, REGRET_DENOMINATOR, WORK_UPPER, Request,
    board_count, build_law, complete_expectation, inventory, one_sample,
    prefix_ticket_counts, ticket, unrank_board,
)


class JointSampleReferenceTests(unittest.TestCase):
    def test_all_private_and_board_tickets_have_exact_nonuniform_joint_law(self):
        law = build_law()
        self.assertEqual((law.weights, law.compatible, law.normalizer), (((1, 6), (3, 8)), (11, 3), 29))
        worlds = inventory(law)
        self.assertEqual(len(worlds), 60)
        self.assertEqual(sum(count for _sample, count in worlds), MEAN_TICKETS)
        masses = Counter()
        for sample, count in worlds:
            masses[sample.holdings] += count
            self.assertEqual(count, sample.mass)
            self.assertEqual(Fraction(count, 580), Fraction(sample.mass, 29 * 20))
            private_cards = {card for actor, holding in enumerate(sample.holdings)
                             for card in law.ranges[actor][holding][0]}
            self.assertEqual(len(private_cards), 4)
            self.assertTrue(private_cards.isdisjoint(sample.board))
        self.assertEqual(dict(masses), {(0, 0): 60, (0, 1): 160, (1, 0): 360})
        self.assertNotEqual({Fraction(count, 580) for _sample, count in worlds}, {Fraction(1, 60)})

    def test_board_unranking_matches_separate_combination_and_permutation_order(self):
        law = build_law()
        for i, j in ((0, 0), (0, 1), (1, 0)):
            excluded = (*law.ranges[0][i][0], *law.ranges[1][j][0])
            left = tuple(card for card in PROOF9 if card not in excluded)
            expected = tuple((*flop, *tail) for flop in combinations(left, 3)
                             for tail in permutations(tuple(card for card in left if card not in flop), 2))
            actual = tuple(unrank_board(tuple(PROOF9), excluded, rank) for rank in range(20))
            self.assertEqual(actual, expected)
            self.assertEqual(len(set(actual)), 20)
        self.assertEqual(board_count(9), 20)
        self.assertEqual(board_count(52), 34_246_080)  # Formula only, no range/trainer admission.

    def test_ticket_prefix_marginal_has_correct_original_holding_identity(self):
        law = build_law(); prefixes = prefix_ticket_counts(law)
        self.assertEqual(prefixes[0, 0, ()], 220)
        self.assertEqual(prefixes[0, 1, ()], 360)
        self.assertEqual(prefixes[1, 0, ()], 420)
        self.assertEqual(prefixes[1, 1, ()], 160)
        for actor in (0, 1):
            for length in (0, 3, 4, 5):
                self.assertEqual(sum(count for (seat, _holding, prefix), count in prefixes.items()
                                     if seat == actor and len(prefix) == length), 580)
        # Different hidden opponents can contribute to a single own-hand/flop
        # prefix. Their ticket masses sum instead of creating another row.
        worlds = inventory(law)
        duplicate = next((a, b) for a, _ in worlds for b, _ in worlds
                         if a.holdings[0] == b.holdings[0] and a.holdings[1] != b.holdings[1]
                         and a.board[:3] == b.board[:3])
        a, b = duplicate
        total = sum(count for sample, count in worlds
                    if sample.holdings[0] == a.holdings[0] and sample.board[:3] == a.board[:3])
        self.assertEqual(prefixes[0, a.holdings[0], a.board[:3]], total)
        self.assertGreater(total, a.mass)

    def test_both_full_q52_profiles_match_all_literal_regret_and_average_coordinates(self):
        self.assertEqual(REGRET_DENOMINATOR, 1 << 625)
        self.assertEqual(AVERAGE_DENOMINATOR, 1 << 364)
        for profile in ('uniform', 'zero-skew'):
            with self.subTest(profile=profile):
                request = Request(profile)
                result = complete_expectation(request)
                self.assertTrue(result['literal_expectation_match'])
                self.assertTrue(result['prefix_marginal_match'])
                self.assertEqual((result['rows'], result['slots']), (24_420, 58_164))
                self.assertEqual((result['worlds'], result['tickets'], result['sample_calls']), (60, 580, 60))
                self.assertEqual((result['sample_rows'], result['sample_slots']), (434, 1039))
                self.assertLessEqual(result['maximum_sample_regret_bits'], 630)
                self.assertLessEqual(result['maximum_sample_average_bits'], 365)
                self.assertEqual((result['rng_calls'], result['native_calls'], result['training_iterations']), (0, 0, 0))
                self.assertIsNone(result['quality_gate'])
                for name, used in result['resource_accounting'].items():
                    if name in LIMITS:
                        self.assertLessEqual(used, LIMITS[name])
                if profile == 'zero-skew':
                    self.assertGreater(result['zero_own_nonzero_regret_rows'], 0)
                    self.assertGreater(result['zero_policy_nonzero_regret_slots'], 0)
                with self.assertRaisesRegex(ValueError, 'one-shot'):
                    complete_expectation(request)
                del request, result

    def test_hidden_opponent_and_future_cards_cannot_change_earlier_policy_or_average(self):
        request = Request('zero-skew')
        worlds = tuple(sample for sample, _count in inventory(request.law))
        first, opponent = next((a, b) for a in worlds for b in worlds
                               if a.holdings[0] == b.holdings[0] and a.holdings[1] != b.holdings[1]
                               and a.board[:3] == b.board[:3])
        future = next(sample for sample in worlds
                      if sample.holdings == first.holdings and sample.board[:3] == first.board[:3]
                      and sample.board[3:] == first.board[3:][::-1])
        results = tuple(one_sample(request, sample) for sample in (first, opponent, future))
        for comparison in results[1:]:
            common = set(results[0].rows) & set(comparison.rows)
            earlier = {key for key in common if len(request.grid.prefixes[key]) <= 3}
            self.assertTrue(any(len(request.grid.prefixes[key]) == 3 for key in earlier))
            for key in earlier:
                a, b = results[0].rows[key], comparison.rows[key]
                self.assertEqual(a.units, b.units)
                self.assertEqual(a.units, request.grid.units[key])
                self.assertEqual(a.averages, b.averages)
                self.assertEqual(sum(a.units), Q)
        self.assertTrue(set(results[0].rows) - set(results[2].rows), 'new visible turns must have distinct rows')
        for result in results:
            self.assertEqual((result.visits, result.actions, result.reveals, result.terminals), (1105, 1039, 65, 606))
            self.assertEqual(len(result.rows), 434)
            for key, row in result.rows.items():
                self.assertIn(key, request.fixture.menus)
                self.assertTrue(all(value % (1 << (52 * row.prior_own_actions)) == 0 for value in row.regrets))
                self.assertTrue(all(value % (1 << (312 - 52 * row.prior_own_actions)) == 0 for value in row.averages))

    def test_request_limits_reject_before_source_or_private_preparation(self):
        self.assertEqual(CREATED_BITS_UPPER, 15_405_760_000)
        self.assertEqual(sum(ENTRY_PARTITION.values()), 6_909_632)
        self.assertLessEqual(sum(ENTRY_PARTITION.values()), ENTRIES_UPPER)
        for name, value in (('work', WORK_UPPER - 1), ('entries', ENTRIES_UPPER - 1),
                            ('created_bits', CREATED_BITS_UPPER - 1),
                            ('integer_bits', INTERMEDIATE_BITS_UPPER - 1)):
            with self.subTest(limit=name), patch('tests.virtual_joint_sample_reference.Fixture') as constructor:
                with self.assertRaisesRegex(ValueError, 'admission rejected'):
                    Request(limits={name: value})
                constructor.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'reduce-only'):
            Request(limits={'work': LIMITS['work'] + 1})

    def test_forged_or_foreign_sample_rejects_before_rank_or_walk(self):
        request = Request()
        sample = ticket(request.law, 0, 0)
        foreign = ticket(build_law(), 0, 0)
        for changed in (foreign, replace(sample, holdings=(1, 1)), replace(sample, mass=1),
                        replace(sample, board=sample.board[:3] + sample.board[3:][::-1])):
            with self.subTest(sample=changed), patch('tests.virtual_joint_sample_reference.independent_rank') as rank:
                with self.assertRaisesRegex(ValueError, 'owner or selector changed'):
                    one_sample(request, changed)
                rank.assert_not_called()
                self.assertEqual(request.sample_calls, 0)
        with self.assertRaisesRegex(ValueError, 'immutable snapshot'):
            ticket(replace(request.law, normalizer=28), 0, 0)
        for private, board in ((-1, 0), (29, 0), (0, -1), (0, 20)):
            with self.assertRaises(ValueError):
                ticket(request.law, private, board)


if __name__ == '__main__':
    unittest.main()
