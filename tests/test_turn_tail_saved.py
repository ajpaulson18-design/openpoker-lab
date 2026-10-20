"""Replay the accepted complete tail report with production training disabled."""
from contextlib import ExitStack
import unittest
from unittest.mock import patch

from scripts import benchmark_turn_tail as runner


class TurnTailSavedTests(unittest.TestCase):
    def test_saved_six_profiles_replay_without_training(self):
        with ExitStack() as stack:
            for target in ('scripts.benchmark_turn_tail.capture',
                           'pokerlab.postflop_solver.solve_postflop',
                           'pokerlab.matrix_free_turn.solve_matrix_free_turn',
                           'pokerlab.postflop_solver.train_public_batched',
                           'pokerlab.matrix_free_turn.train_ranked_turn'):
                stack.enter_context(patch(target, side_effect=AssertionError('Production training called')))
            checked = runner._verify_saved(runner.REPORT, runner.POLICIES_DIR)
        self.assertEqual((checked['profiles'], checked['training_calls']), (6, 0))
        self.assertEqual(checked['report_sha256'], '9e51cbcf9f031f371806be06e6a23589e0dd27d5e3ffffcf36fc545eed5d6998')


if __name__ == '__main__':
    unittest.main()
