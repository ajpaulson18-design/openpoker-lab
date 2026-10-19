"""Replay the published complete witness bundle with training disabled."""
from contextlib import ExitStack
import unittest
from unittest.mock import patch

from scripts import build_raised_turn_witness as witness


class RaisedTurnCleanWitnessSavedTests(unittest.TestCase):
    def test_complete_saved_bundle_reconstructs_without_training(self):
        with ExitStack() as stack:
            for target in ('scripts.benchmark_turn_tail.capture',
                           'pokerlab.postflop_solver.solve_postflop',
                           'pokerlab.matrix_free_turn.solve_matrix_free_turn',
                           'pokerlab.postflop_solver.train_public_batched',
                           'pokerlab.matrix_free_turn.train_ranked_turn'):
                stack.enter_context(patch(target, side_effect=AssertionError('Production training called')))
            checked = witness.verify_saved()
        self.assertEqual((checked['profiles'], checked['training_calls']), (2, 0))
        self.assertEqual(checked['report_sha256'],
                         'e9e44108b1158840383cd025dcd995b21d3fc35d902a59ab2bae3a5060bf88e6')


if __name__ == '__main__':
    unittest.main()
