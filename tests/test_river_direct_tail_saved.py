"""Reconstruct both accepted river tails with producer execution disabled."""
from contextlib import ExitStack
from fractions import Fraction
from hashlib import sha256
import unittest
from unittest.mock import patch

from scripts import benchmark_river_direct_tail as audit


class RiverDirectTailSavedTests(unittest.TestCase):
    def test_complete_saved_bundle_without_training(self):
        expected_hashes = {
            "report": "68a0fe3ff150c37c47784cc22cfe928f19974f27208ee16dee61c53ee81a35a5",
            "river-polarised-bluffcatcher": "2f558f363f716c0dc67794d329d167254b7b65bcf339cd8480d61e7e8fe53117",
            "river-weighted-raises": "905c2cb42bfb1fbb69117ae2dda07f502935b657f3871f536dffe34363cbfacf",
        }
        for key, path in audit._fixed_targets().items():
            self.assertEqual(sha256(path.read_bytes()).hexdigest(), expected_hashes[key])
        with ExitStack() as stack:
            for target in (
                "pokerlab.river_tail_adapter.solve_river_tail",
                "pokerlab.river_tail_adapter._train_original_weight_tail",
                "pokerlab.turn_tail_adapter.solve_turn_tail",
                "pokerlab.turn_tail_adapter._train_original_weight_tail",
                "scripts.benchmark_turn_tail.capture",
                "pokerlab.postflop_solver.solve_postflop",
                "pokerlab.matrix_free_turn.solve_matrix_free_turn",
                "pokerlab.postflop_solver.train_public_batched",
                "pokerlab.matrix_free_turn.train_ranked_turn",
            ):
                stack.enter_context(patch(target, side_effect=AssertionError("Training called")))
            report = audit.verify()
        self.assertEqual(report["historical_producer_head"],
                         "3ba950acb96f3b37206251ab82ae230ed0240a78")
        self.assertEqual((report["completed_training_calls"], report["iterations"],
                          report["discard"], report["target_meet_count"],
                          report["target_miss_count"]), (2, 10000, 3000, 1, 1))
        for fixture_id, row in report["results"].items():
            self.assertEqual((row["averaged_sweeps"], row["average_weight_sum"],
                              row["requested_regret_passes"], row["requested_average_passes"],
                              row["requested_total_traversal_passes"], row["training_calls"]),
                             (7000, 45503500, 20000, 7000, 27000, 1))
            gap = Fraction(row["exact_metrics_fractions"]["nash_conv"])
            self.assertGreater(gap, 0)
            self.assertFalse(row["exact_nash_conv_zero"])
            self.assertEqual(row["exact_threshold_met"],
                             fixture_id == "river-weighted-raises")
            self.assertEqual(row["exact_threshold_met"], gap <= Fraction(1, 1000))
            self.assertLessEqual(Fraction(row["own_action_flow_max_error_fraction"]),
                                 Fraction(1, 10**11))
            self.assertTrue(row["known_game_reference_in_response_interval"])


if __name__ == "__main__":
    unittest.main()
