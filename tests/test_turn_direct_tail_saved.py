"""Reconstruct the accepted raw direct-tail policy with all training disabled."""
from contextlib import ExitStack
from fractions import Fraction
from hashlib import sha256
import unittest
from unittest.mock import patch

from scripts import benchmark_turn_direct_tail as audit


class TurnDirectTailSavedTests(unittest.TestCase):
    def test_complete_saved_bundle_without_training(self):
        self.assertEqual(sha256(audit.REPORT.read_bytes()).hexdigest(),
                         "ea7b5c9d8eafbec0aa99ebaf8c6f2e4e76cf9d9d93cea57226a0ad9f8d7c46b3")
        self.assertEqual(sha256(audit.POLICY.read_bytes()).hexdigest(),
                         "18553678c7d6cda7d8425d268bd79cdcb8e7add31f8d36a35ede8b1a67ba4d5c")
        with ExitStack() as stack:
            for target in ("pokerlab.turn_tail_adapter.solve_turn_tail",
                           "pokerlab.turn_tail_adapter._train_original_weight_tail",
                           "scripts.benchmark_turn_tail.capture",
                           "pokerlab.postflop_solver.solve_postflop",
                           "pokerlab.matrix_free_turn.solve_matrix_free_turn",
                           "pokerlab.postflop_solver.train_public_batched",
                           "pokerlab.matrix_free_turn.train_ranked_turn"):
                stack.enter_context(patch(target, side_effect=AssertionError("Training called")))
            report = audit.verify_bundle()
        self.assertEqual(report["exact_full_physical_metrics"], {
            "value_oop": "-400/21", "value_ip": "400/21",
            "oop_best_response_value": "-400/21", "ip_best_response_value": "400/21",
            "oop_best_response_gain": "0", "ip_best_response_gain": "0",
            "nash_conv": "0", "exploitability": "0",
        })
        self.assertTrue(report["exact_1_over_1000_met"])
        self.assertTrue(report["exact_nash_conv_zero"])
        self.assertEqual(report["completed_adapter_training_calls"], 1)
        self.assertEqual((report["iterations"], report["discard"],
                          report["averaged_sweeps"], report["average_weight_sum"]),
                         (1500, 1000, 500, 625250))
        self.assertLessEqual(Fraction(report["old_tail_own_realization_max_abs_error_fraction"]),
                             Fraction(1, 10**11))
        self.assertEqual(report["exact_counters"]["physical_worlds"], 176)
        self.assertEqual(report["exact_counters"]["physical_runouts"], 48)
        self.assertFalse(report["exact_counters"]["chance_grouping"])


if __name__ == "__main__":
    unittest.main()
