"""Replay accepted full-deck raised policies without invoking any solver."""
from contextlib import ExitStack
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from scripts import benchmark_full_deck_raised_turn as benchmark


class FullDeckRaisedSavedPolicyTests(unittest.TestCase):
    def test_all_six_immutable_policies_replay_without_training_or_exact_claims(self):
        # This accepted artifact is numeric evidence. Exact trained-policy
        # auditing is deliberately forbidden here rather than implied by replay.
        with ExitStack() as stack:
            for target in (
                    'scripts.benchmark_full_deck_raised_turn.solve',
                    'pokerlab.postflop_solver.solve_postflop',
                    'pokerlab.matrix_free_turn.solve_matrix_free_turn',
                    'pokerlab.postflop_solver.train_public_batched',
                    'pokerlab.matrix_free_turn.train_ranked_turn',
                    'scripts.turn_rational_certificate.evaluate_exact'):
                stack.enter_context(patch(target, side_effect=AssertionError('No training/exact claim: ' + target)))
            accepted = benchmark.verify_saved_artifact()
        self.assertEqual(accepted['status'], 'VERIFIED_SAVED_FULL_DECK_RAISED_TURN')
        self.assertEqual((accepted['profiles'], accepted['training_calls']), (6, 0))
        raw = benchmark.REPORT.read_bytes()
        self.assertEqual(sha256(raw).hexdigest(), accepted['report_sha256'])
        report = json.loads(raw)
        self.assertEqual(report['baseline_git_commit'], '6541f3da4bc1d71954febb4c0ad70d4a91e2f617')
        self.assertEqual([(row['iterations_completed'], row['backend']) for row in report['results']],
                         [(t, b) for t in (100, 1000, 1500) for b in ('materialized', 'matrix-free')])
        for row in report['results']:
            self.assertIs(row['threshold_met'], row['metrics']['nash_conv'] <= 0.001)
            self.assertLessEqual(max(map(abs, row['scalar_differences'].values())), 1e-9)


if __name__ == '__main__':
    unittest.main()
