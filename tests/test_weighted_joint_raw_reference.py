"""Sparse selected-world raw gates before native full52 coupling."""
from dataclasses import FrozenInstanceError, replace
from itertools import combinations
from unittest.mock import patch
import unittest

from tests.test_weighted_joint_reference import bits, n9_ranges
from tests.full_deck_public_chance_reference import PROOF9
from tests.virtual_joint_sample_reference import Request as LiteralRequest, one_sample, ticket
from tests.virtual_joint_two_epoch_reference import two_epochs as literal_epochs
from tests.virtual_weighted_joint_raw_reference import Request, Policy, two_epochs, DR, DA, Q


class WeightedJointRawReferenceTests(unittest.TestCase):
    def test_n9_two_epoch_sparse_result_matches_accepted_literal_all_rows(self):
        selectors = ((0, 0), (11, 0))
        request = Request(tuple(PROOF9), n9_ranges())
        observations = two_epochs(request, selectors)
        literal = LiteralRequest()
        initial, expected = literal_epochs(literal, selectors)
        for actual, reference in zip(observations, expected):
            self.assertEqual(actual['root'] * reference['root'].denominator, reference['root'].numerator * DR)
            self.assertEqual(dict(actual['numeric']), reference['numeric'])
            self.assertTrue(set(actual['policy'].rows) <= set(initial))
            reconstructed = {key: actual['policy'].rows.get(key, units) for key, units in initial.items()}
            self.assertEqual(reconstructed, reference['policy'])
            for key, row in actual['raw'].items():
                menu, source, ordinal = request.locate(key)
                self.assertEqual(menu, literal.fixture.menus[key])
                self.assertEqual(source, literal.fixture.paths[ordinal >> 33][0])
                self.assertEqual(literal.fixture.compact_key(ordinal, key[0], key[1]), key)
        self.assertLessEqual(request.fraction_ops, 20_000)

    def test_full52_weighted_two_observations_read_sparse_policy_and_keep_defaults(self):
        hands = tuple(combinations(range(52), 2))
        side = tuple((hand, bits(float(index % 7 + 1))) for index, hand in enumerate(hands))
        request = Request(tuple(range(52)), (side, side))
        # The same exact world observes its previous update without a reset.
        first, second = two_epochs(request, ((0, 34246079), (0, 34246079)))
        self.assertEqual((len(first['raw']), len(second['raw'])), (434, 434))
        self.assertEqual(first['policy'], second['input_policy'])
        self.assertNotEqual(first['root'], second['root'])
        self.assertTrue(any(value < 0 for regrets, _ in second['numeric'].values() for value in regrets))
        self.assertTrue(any(unit == 0 and regret != 0 for row in second['raw'].values()
                            for unit, regret in zip(row.units, row.regrets)))
        for observation in (first, second):
            self.assertLessEqual(len(observation['policy'].rows), 868)
            self.assertLessEqual(sum(map(len, observation['policy'].rows.values())), 2078)
            for key, row in observation['raw'].items():
                self.assertEqual(sum(row.units), Q)
                self.assertEqual(sum(value * unit for value, unit in zip(row.regrets, row.units)), 0)
                self.assertTrue(all(value >= 0 for value in row.averages))
                self.assertEqual(request.locate(key)[2], row.ordinal)
        # Legal preflop own holdings outside the selected pair remain uniform;
        # the query contract checks defaults without enumerating15.9T rows.
        for holding in (1, 50, 1325):
            key = 0, holding, ()
            self.assertNotIn(key, second['policy'].rows)
            self.assertEqual(second['policy'].lookup(*key), Policy(request, {}).lookup(*key))
        self.assertEqual(request.calls, 2)
        self.assertEqual((DR, DA), (1 << 625, 1 << 364))
        self.assertEqual(request.forecast['work'], 498_859_648)
        self.assertEqual(request.forecast['created_bits'], 15_965_219_904)

    def test_hidden_future_and_opponent_do_not_enter_policy_lookup(self):
        request = Request(tuple(PROOF9), n9_ranges())
        policy = Policy(request, {})
        a = request.law.decode(0, 0); b = request.law.decode(0, 1)
        self.assertEqual(a.board[:3], b.board[:3])
        raw_a, _ = request.one_sample(a, policy)
        raw_b, _ = request.one_sample(b, policy)
        earlier = set(key for key in raw_a if all(not token.startswith(('turn@', 'river@')) for token in key[2]))
        self.assertTrue(earlier)
        for key in earlier:
            self.assertEqual(raw_a[key].units, raw_b[key].units)
            self.assertEqual(raw_a[key].averages, raw_b[key].averages)
        with self.assertRaises(FrozenInstanceError):
            policy.rows = {}

    def test_all_selectors_and_whole_request_reject_before_first_rank_or_walk(self):
        with patch('tests.virtual_weighted_joint_raw_reference.build_law') as law:
            with self.assertRaisesRegex(ValueError, 'complete request rejected'):
                Request(tuple(PROOF9), n9_ranges(), {'work': 1})
            law.assert_not_called()
        request = Request(tuple(PROOF9), n9_ranges())
        with patch.object(type(request.law), 'decode') as decode:
            with self.assertRaisesRegex(ValueError, 'complete selector admission'):
                two_epochs(request, ((0, 0), (29, 0)))
            decode.assert_not_called()
        self.assertEqual(request.calls, 0)
        world = request.law.decode(0, 0)
        with self.assertRaisesRegex(ValueError, 'foreign physical world'):
            request.one_sample(replace(world, showdown_sign=-world.showdown_sign if world.showdown_sign else 1))
        with self.assertRaises(ValueError):
            Policy(request, {(0, 0, ('river@2c',)): (Q, 0)})
        with self.assertRaises(ValueError):
            Policy(request, {(0, 0, ()): (Q, Q, 0)})


if __name__ == '__main__':
    unittest.main()
