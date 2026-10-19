"""Replay the accepted six-policy exact tail audit with all training disabled."""
from contextlib import ExitStack
import unittest
from unittest.mock import patch

from scripts import audit_turn_tail_exact as audit


class TurnTailSavedExactTests(unittest.TestCase):
    def test_six_saved_certificates_reconstruct_without_training(self):
        with ExitStack() as stack:
            for target in ('scripts.benchmark_turn_tail.capture',
                           'pokerlab.postflop_solver.solve_postflop',
                           'pokerlab.matrix_free_turn.solve_matrix_free_turn',
                           'pokerlab.postflop_solver.train_public_batched',
                           'pokerlab.matrix_free_turn.train_ranked_turn'):
                stack.enter_context(patch(target, side_effect=AssertionError('Production training called')))
            checked = audit.verify_saved_artifact()
        self.assertEqual((checked['accepted_profiles'], checked['rejected_profiles'],
                          checked['training_calls']), (6, 0, 0))
        self.assertEqual(checked['report_sha256'],
                         'f4901675fcb026fbac6713baf604650fd48f510c5ae4dc6be2c776c0a780c0c7')


if __name__ == '__main__':
    unittest.main()
