"""Reconstruct the immutable full-physical report with training disabled."""
from contextlib import ExitStack
from hashlib import sha256
import unittest
from unittest.mock import patch

from scripts import audit_raised_turn_full_physical as audit


class RaisedTurnFullPhysicalSavedTests(unittest.TestCase):
    def test_complete_saved_report_without_training(self):
        self.assertEqual(sha256(audit.REPORT.read_bytes()).hexdigest(),
                         'b84527caeced27674d136479cc6700929309ed6677e8ee6bd10c9e93f35cbd11')
        with ExitStack() as stack:
            for target in ('scripts.benchmark_turn_tail.capture',
                           'pokerlab.postflop_solver.solve_postflop',
                           'pokerlab.matrix_free_turn.solve_matrix_free_turn',
                           'pokerlab.postflop_solver.train_public_batched',
                           'pokerlab.matrix_free_turn.train_ranked_turn'):
                stack.enter_context(patch(target, side_effect=AssertionError('Production training called')))
            report = audit.verify_report()
        self.assertEqual(len(report['profiles']), 6)
        witnesses = [case for case in report['profiles']
                     if case['case'] == 'saved-clean-witness']
        self.assertEqual(len(witnesses), 2)
        for case in witnesses:
            self.assertEqual(case['metrics_fraction']['nash_conv'], '0')
            self.assertEqual(case['metrics_fraction']['value_oop'], '-400/21')
        self.assertEqual(len(report['source_sha256']), 10)


if __name__ == '__main__':
    unittest.main()
