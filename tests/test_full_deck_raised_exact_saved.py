"""Replay the complete accepted exact audit with production entry points disabled."""
from contextlib import ExitStack
import unittest
from unittest.mock import patch

from scripts import audit_full_deck_raised_exact as audit


class FullDeckRaisedSavedExactTests(unittest.TestCase):
    def test_saved_six_policy_exact_audit_reconstructs_without_training(self):
        with ExitStack() as stack:
            for target in ('pokerlab.postflop_solver.solve_postflop',
                           'pokerlab.matrix_free_turn.solve_matrix_free_turn',
                           'pokerlab.postflop_solver.train_public_batched',
                           'pokerlab.matrix_free_turn.train_ranked_turn'):
                stack.enter_context(patch(target, side_effect=AssertionError('Production training called')))
            checked = audit.verify_saved_artifact()
        self.assertEqual((checked['profiles'], checked['training_calls']), (6, 0))
        self.assertEqual(checked['report_sha256'],
                         '6a2b1b66631bdb892856cae38b9378b16bfb702ed84d8563cf56a90dc6f9f1ed')


if __name__ == '__main__':
    unittest.main()
