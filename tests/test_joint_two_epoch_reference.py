"""Changing-policy witnesses before native joint-sample coupling."""
from unittest.mock import patch
import unittest

from tests.virtual_joint_sample_reference import Request, one_sample, ticket
from tests.virtual_joint_two_epoch_reference import policy_digest, two_epochs


class JointTwoEpochReferenceTests(unittest.TestCase):
    def test_second_pair_reads_the_first_committed_policy(self):
        request = Request()
        initial, observations = two_epochs(request, ((0, 0), (11, 0)))
        first, second = observations
        self.assertNotEqual(first['policy_sha256'], policy_digest(request.fixture, initial))
        self.assertEqual(second['input_policy_sha256'], first['policy_sha256'])
        self.assertNotEqual(second['policy_sha256'], first['policy_sha256'])
        frozen = Request()
        old_second = one_sample(frozen, ticket(frozen.law, 11, 0))
        self.assertNotEqual(second['root'].numerator * (1 << 625),
                            old_second.root * second['root'].denominator)
        self.assertTrue(any(value < 0 for r, _a in second['numeric'].values() for value in r))
        self.assertEqual((second['staged_rows'], second['staged_slots']), (868, 2078))
        self.assertGreater(second['raw_zero_policy_nonzero_regret_slots'], 0)

    def test_equivalent_tickets_preserve_world_identity_without_restarting_policy(self):
        request = Request()
        initial, observations = two_epochs(request, ((0, 0), (2, 0)))
        first, second = observations
        self.assertEqual((first['holdings'], first['board']), (second['holdings'], second['board']))
        self.assertEqual(second['input_policy_sha256'], first['policy_sha256'])
        self.assertNotEqual(second['input_policy_sha256'], policy_digest(request.fixture, initial))
        self.assertEqual(set(first['numeric']), set(second['numeric']))
        self.assertEqual(len(second['policy']), 24420)

    def test_all_selectors_reject_before_first_rank_or_sample(self):
        request = Request()
        with patch('tests.virtual_joint_sample_reference.independent_rank') as rank:
            with self.assertRaises(ValueError):
                two_epochs(request, ((0, 0), (29, 0)))
            rank.assert_not_called()
        self.assertEqual(request.sample_calls, 0)


if __name__ == '__main__':
    unittest.main()
