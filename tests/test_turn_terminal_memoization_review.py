"""Sol's closed-form vectors and cumulative fallback-cap witnesses."""
import math
import struct
import unittest

from pokerlab import matrix_free_turn, turn_range_kernel
from pokerlab.ranked_river import RankedRiverPayoffs
from pokerlab.river_tree import _Terminal
from scripts.turn_terminal_memoization import patched_turn_memoizer


BOARD = ("Js", "8d", "4c", "2h", "3c")
HANDS = ((("Ah", "As"), ("Kh", "Ks")),
         (("Ac", "Ad"), ("Kc", "Kd")))
WEIGHTS = ((1.0, 1.0), (1.0, 1.0))


def bits(values):
    return struct.pack("!" + str(len(values)) + "d", *values)


class TurnMemoizationIndependentReviewTests(unittest.TestCase):
    def test_constructor_excludes_actual_exceptional_conditioning(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((("Ah", "As"), ("Kc", "Kd")), (("Qh", "Qs"),))
        weights = ((1.0, math.nextafter(0.0, 1.0)), (1.0,))
        original = matrix_free_turn.TurnRangePayoffs
        baseline = original(board, hands, weights, pot=20, runouts=("As",))
        self.assertTrue(baseline.exceptional_conditioning)
        with self.assertRaisesRegex(ValueError, "exceptional conditioning"):
            with patched_turn_memoizer("full44-blocked-runouts", 10):
                matrix_free_turn.TurnRangePayoffs(
                    board, hands, weights, pot=20, runouts=("As",))
        self.assertIs(matrix_free_turn.TurnRangePayoffs, original)

    def test_runtime_excludes_actual_activation_of_stable_root_fold_path(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((("3c", "4c"), ("Ah", "As")), (("Qh", "Qs"),))
        weights = ((1.0, math.ldexp(1.0, -1022)), (1.0,))
        original = matrix_free_turn.TurnRangePayoffs
        fold = _Terminal("fold", (0.0, 0.0), 0)
        with self.assertRaisesRegex(ValueError, "activated excluded"):
            with patched_turn_memoizer("full44-blocked-runouts", 10):
                kernel = matrix_free_turn.TurnRangePayoffs(
                    board, hands, weights, pot=2, runouts=("As", "Kd"))
                self.assertFalse(kernel.exceptional_conditioning)
                self.assertEqual(kernel.stable_root_fold_calls, 0)
                kernel.values(fold, (1.0,), 0)
        self.assertEqual(kernel.stable_root_fold_calls, 1)
        self.assertIs(matrix_free_turn.TurnRangePayoffs, original)

    def test_known_vectors_keep_model_player_kind_winner_and_matched_namespaces(self):
        original_ranked = turn_range_kernel.RankedRiverPayoffs
        original_turn = matrix_free_turn.TurnRangePayoffs
        with patched_turn_memoizer("full44-blocked-runouts", 10, max_entries=16) as stats:
            first = turn_range_kernel.RankedRiverPayoffs(BOARD, HANDS, WEIGHTS, pot=100)
            second = turn_range_kernel.RankedRiverPayoffs(BOARD, HANDS, WEIGHTS, pot=200)
            fold0 = _Terminal("fold", (0.0, 0.0), 0)
            fold1 = _Terminal("fold", (0.0, 0.0), 1)
            showdown = _Terminal("showdown", (0.0, 0.0))
            # Four equally weighted compatible pairs. Each own hand has mass
            # one half, giving +/-25 on a 50-chip fold and +/-12.5 at showdown.
            requests = [
                (first, fold0, 0, [25.0, 25.0]),
                (second, fold0, 0, [50.0, 50.0]),
                (first, fold0, 1, [-25.0, -25.0]),
                (first, fold1, 0, [-25.0, -25.0]),
                (first, showdown, 0, [12.5, -12.5]),
                (first, showdown, 1, [12.5, -12.5]),
                (first, _Terminal("fold", (10.0, 7.0), 0), 0, [28.5, 28.5]),
            ]
            for kernel, node, player, expected in requests:
                with self.subTest(pot=kernel.pot, kind=node.kind, player=player,
                                  winner=node.winner, matched=min(node.contributions)):
                    self.assertEqual(bits(kernel.values(node, (1.0, 1.0), player)), bits(expected))
                    hit = kernel.values(node, (1.0, 1.0), player)
                    self.assertEqual(bits(hit), bits(expected))
                    hit[0] = 123456.0
                    self.assertEqual(bits(kernel.values(node, (1.0, 1.0), player)), bits(expected))
            self.assertGreater(stats.cache_hits, 0)
        self.assertIs(turn_range_kernel.RankedRiverPayoffs, original_ranked)
        self.assertIs(matrix_free_turn.TurnRangePayoffs, original_turn)

    def test_cached_matched_zero_still_validates_unmatched_infinite_contribution(self):
        with patched_turn_memoizer("full44-blocked-runouts", 10) as stats:
            kernel = turn_range_kernel.RankedRiverPayoffs(BOARD, HANDS, WEIGHTS, pot=100)
            valid = _Terminal("fold", (0.0, 0.0), 0)
            kernel.values(valid, (1.0, 1.0), 0)
            kernel.values(valid, (1.0, 1.0), 0)
            hits = stats.cache_hits
            invalid = _Terminal("fold", (0.0, float("inf")), 0)
            # min(0, inf)=0, so extracting a key before validating both
            # contributions would return the valid cached fold vector.
            with self.assertRaises(ValueError):
                kernel.values(invalid, (1.0, 1.0), 0)
            self.assertEqual(stats.cache_hits, hits)

    def test_real_fallback_calls_preserve_the_second_call_budget_failure(self):
        board = ("2c", "7d", "9h", "Js", "Kd")
        hands = ((("Ah", "As"),), (("Ah", "Ks"), ("Qh", "Qs")))
        weights = ((1.0,), (1.0, 1e-12))
        fold = _Terminal("fold", (0.0, 0.0), 0)
        baseline = RankedRiverPayoffs(board, hands, weights, pot=100)
        initial = baseline.fallback_pair_checks
        baseline.fallback_pair_limit = initial + 2
        expected = baseline.values(fold, (1.0, 1.0), 0)
        expected_count = baseline.fallback_pair_checks
        self.assertGreater(expected_count, initial)
        with self.assertRaisesRegex(ValueError, "fallback pair-check budget"):
            baseline.values(fold, (1.0, 1.0), 0)

        with patched_turn_memoizer("full44-blocked-runouts", 10) as stats:
            kernel = turn_range_kernel.RankedRiverPayoffs(board, hands, weights, pot=100)
            self.assertEqual(kernel.fallback_pair_checks, initial)
            kernel.fallback_pair_limit = initial + 2
            self.assertEqual(bits(kernel.values(fold, (1.0, 1.0), 0)), bits(expected))
            self.assertEqual(kernel.fallback_pair_checks, expected_count)
            with self.assertRaisesRegex(ValueError, "fallback pair-check budget"):
                kernel.values(fold, (1.0, 1.0), 0)
            self.assertEqual(kernel.fallback_pair_checks, baseline.fallback_pair_checks)
            self.assertEqual(stats.cache_hits, 0)


if __name__ == "__main__":
    unittest.main()
