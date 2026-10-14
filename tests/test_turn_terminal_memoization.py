import math
import struct
import unittest

from pokerlab import matrix_free_turn, turn_range_kernel
from pokerlab.ranked_river import RankedRiverPayoffs
from pokerlab.river_tree import _Terminal
from scripts.turn_terminal_memoization import (
    CACHE_SLOTS_PER_CALL,
    MAX_CACHE_ENTRIES,
    MAX_CACHE_SLOT_WORK,
    call_ceiling,
    patched_turn_memoizer,
)


BOARD = ("As", "Ks", "Qs", "Js", "Ts")
HANDS = ((('2c', '3c'), ('4d', '5d')),
         (('6c', '7c'), ('8d', '9d')))
WEIGHTS = ((0.5, 1.0), (1.0, 0.75))


def _bits(values):
    return tuple(struct.pack(">d", float(value)) for value in values)


def _kernel(kernel_type, *, fallback_limit=None):
    return kernel_type(BOARD, HANDS, WEIGHTS, pot=100,
                       fallback_pair_limit=fallback_limit)


class TurnTerminalMemoizationTests(unittest.TestCase):
    def test_bound_and_slot_envelopes_are_conservative_and_strict(self):
        full = call_ceiling("full44-blocked-runouts", 1000)
        selected = call_ceiling("two-conditioned-runouts-asymmetric-multisize", 1000)
        self.assertEqual(full, 1_442_880)
        self.assertEqual(full * CACHE_SLOTS_PER_CALL, 28_857_600)
        self.assertEqual(selected, 192_384)
        self.assertEqual(selected * CACHE_SLOTS_PER_CALL, 3_847_680)
        self.assertLessEqual(full * CACHE_SLOTS_PER_CALL, MAX_CACHE_SLOT_WORK)
        for model, iterations in (("full44-blocked-runouts", True),
                                  ("full44-blocked-runouts", 1001),
                                  ("unknown", 300)):
            with self.subTest(model=model, iterations=iterations):
                with self.assertRaises(ValueError):
                    call_ceiling(model, iterations)
        for entries in (True, -1, MAX_CACHE_ENTRIES + 1, 1.0):
            with self.subTest(entries=entries):
                with self.assertRaises(ValueError):
                    with patched_turn_memoizer("full44-blocked-runouts", 10,
                                               max_entries=entries):
                        self.fail("invalid entry cap patched classes")
        old_ranked = turn_range_kernel.RankedRiverPayoffs
        old_turn = matrix_free_turn.TurnRangePayoffs
        with self.assertRaisesRegex(ValueError, "slot cap"):
            with patched_turn_memoizer("full44-blocked-runouts", 10,
                                       slot_limit=0):
                self.fail("insufficient cap patched classes")
        with self.assertRaisesRegex(ValueError, "Full requested"):
            with patched_turn_memoizer("full44-blocked-runouts", 1000,
                                       call_limit=1, slot_limit=20):
                self.fail("lowered test call limit bypassed full-request admission")
        self.assertIs(turn_range_kernel.RankedRiverPayoffs, old_ranked)
        self.assertIs(matrix_free_turn.TurnRangePayoffs, old_turn)

    def test_miss_and_hit_match_original_raw_bits_for_both_players_and_terminals(self):
        original_class = turn_range_kernel.RankedRiverPayoffs
        original = _kernel(original_class)
        terminals = (
            _Terminal("fold", (10.0, 40.0), winner=0),
            _Terminal("fold", (10.0, 40.0), winner=1),
            _Terminal("showdown", (10.0, 40.0)),
            _Terminal("showdown", (25.0, 25.0)),
        )
        reaches = ([0.0, 0.75], [0.375, 1.25])
        old_ranked = turn_range_kernel.RankedRiverPayoffs
        old_turn = matrix_free_turn.TurnRangePayoffs
        with patched_turn_memoizer("full44-blocked-runouts", 10) as stats:
            candidate = _kernel(turn_range_kernel.RankedRiverPayoffs)
            self.assertIsNot(type(candidate), original_class)
            for terminal in terminals:
                for player in (0, 1):
                    reach = reaches[player]
                    expected = original.values(terminal, reach, player)
                    actual = candidate.values(terminal, reach, player)
                    self.assertEqual(_bits(actual), _bits(expected))
                    again = candidate.values(terminal, reach, player)
                    self.assertEqual(_bits(again), _bits(expected))
            self.assertGreater(stats.cache_hits, 0)
            self.assertGreater(stats.cache_misses, 0)
        self.assertIs(turn_range_kernel.RankedRiverPayoffs, old_ranked)
        self.assertIs(matrix_free_turn.TurnRangePayoffs, old_turn)
        self.assertEqual(stats.entries_before_cleanup, stats.maximum_entries)
        self.assertEqual(stats.entries_after_cleanup, 0)

    def test_bit_exact_keys_separate_signed_zero_and_branch_identity(self):
        original_class = turn_range_kernel.RankedRiverPayoffs
        original = _kernel(original_class)
        with patched_turn_memoizer("full44-blocked-runouts", 10) as stats:
            kernel_class = turn_range_kernel.RankedRiverPayoffs
            kernel_a = _kernel(kernel_class)
            kernel_b = _kernel(kernel_class)
            fold = _Terminal("fold", (0.0, 0.0), winner=0)
            for kernel, reach in ((kernel_a, [-0.0, 1.0]),
                                  (kernel_a, [0.0, 1.0]),
                                  (kernel_a, [0.0, 1.0]),
                                  (kernel_b, [0.0, 1.0])):
                self.assertEqual(_bits(kernel.values(fold, reach, 0)),
                                 _bits(original.values(fold, reach, 0)))
            self.assertEqual(stats.cache_misses, 3)
            self.assertEqual(stats.cache_hits, 1)

    def test_cache_hit_returns_fresh_list_and_lru_never_exceeds_lowered_cap(self):
        with patched_turn_memoizer("full44-blocked-runouts", 10,
                                   max_entries=1) as stats:
            kernel = _kernel(turn_range_kernel.RankedRiverPayoffs)
            fold = _Terminal("fold", (10.0, 20.0), winner=0)
            first = kernel.values(fold, [0.25, 0.75], 0)
            first[:] = [123.0, 456.0]
            second = kernel.values(fold, [0.25, 0.75], 0)
            self.assertNotEqual(second, first)
            self.assertEqual(stats.cache_hits, 1)
            kernel.values(fold, [0.5, 0.75], 0)
            self.assertEqual(stats.evictions, 1)
            self.assertEqual(stats.maximum_entries, 1)
        self.assertEqual(stats.entries_before_cleanup, 1)
        self.assertEqual(stats.entries_after_cleanup, 0)

    def test_all_original_validation_runs_on_a_would_be_hit(self):
        with patched_turn_memoizer("full44-blocked-runouts", 10) as stats:
            kernel = _kernel(turn_range_kernel.RankedRiverPayoffs)
            valid = _Terminal("fold", (0.0, 0.0), winner=0)
            kernel.values(valid, [0.25, 0.75], 0)
            kernel.values(valid, [0.25, 0.75], 0)
            invalid = (
                (valid, [0.25, 0.75], True),
                (valid, [True, 0.75], 0),
                (valid, [math.nan, 0.75], 0),
                (valid, [math.inf, 0.75], 0),
                (valid, [-0.1, 0.75], 0),
                (valid, [0.25], 0),
                (_Terminal("fold", (0.0, 1.0), winner=True), [0.25, 0.75], 0),
                (_Terminal("fold", (0.0, math.inf), winner=0), [0.25, 0.75], 0),
                (_Terminal("fold", (0.0, math.nan), winner=0), [0.25, 0.75], 0),
            )
            for terminal, reach, player in invalid:
                with self.subTest(terminal=terminal, reach=reach, player=player):
                    with self.assertRaises((TypeError, ValueError)):
                        kernel.values(terminal, reach, player)
            self.assertEqual(stats.cache_hits, 1)

    def test_fallback_calls_are_never_cached_and_caps_still_fail_on_repeat(self):
        board = ("2c", "3d", "4h", "5s", "9c")
        own = (("Ah", "As"),)
        opponents = (("As", "Kc"), ("Kc", "Kd"))
        hands = (own, opponents)
        weights = ((1.0,), (1.0, 1e-20))
        fold = _Terminal("fold", (0.0, 0.0), winner=0)

        with patched_turn_memoizer("full44-blocked-runouts", 10,
                                   call_limit=2) as stats:
            kernel = turn_range_kernel.RankedRiverPayoffs(
                board, hands, weights, pot=40, fallback_pair_limit=100,
            )
            # The first opponent hand is blocked by the own holding, leaving a
            # cancellation-sized compatible residual that requires the scan.
            before = kernel.fallback_pair_checks
            kernel.values(fold, [1.0, 1.0], 0)
            after_first = kernel.fallback_pair_checks
            first_call_checks = after_first - before
            kernel.values(fold, [1.0, 1.0], 0)
            second_call_checks = kernel.fallback_pair_checks - after_first
            self.assertGreater(first_call_checks, 0)
            self.assertGreater(second_call_checks, 0)
            self.assertEqual(stats.cache_misses, 2)
            self.assertEqual(stats.cache_hits, 0)
            self.assertEqual(stats.maximum_entries, 0)

        with patched_turn_memoizer("full44-blocked-runouts", 10,
                                   call_limit=1):
            kernel = _kernel(turn_range_kernel.RankedRiverPayoffs)
            kernel.values(fold, [0.25, 0.75], 0)
            with self.assertRaisesRegex(ValueError, "inner-call ceiling"):
                kernel.values(fold, [0.25, 0.75], 0)

        original_class = turn_range_kernel.RankedRiverPayoffs
        original = original_class(board, hands, weights, pot=40,
                                  fallback_pair_limit=6)
        original.values(fold, [1.0, 1.0], 0)
        with self.assertRaisesRegex(ValueError, "fallback pair-check budget"):
            original.values(fold, [1.0, 1.0], 0)
        original_checks = original.fallback_pair_checks
        with patched_turn_memoizer("full44-blocked-runouts", 10,
                                   call_limit=2):
            candidate = turn_range_kernel.RankedRiverPayoffs(
                board, hands, weights, pot=40, fallback_pair_limit=6,
            )
            candidate.values(fold, [1.0, 1.0], 0)
            with self.assertRaisesRegex(ValueError, "fallback pair-check budget"):
                candidate.values(fold, [1.0, 1.0], 0)
            self.assertEqual(candidate.fallback_pair_checks, original_checks)

    def test_cache_is_cleared_and_module_patches_restore_after_exception(self):
        old_ranked = turn_range_kernel.RankedRiverPayoffs
        old_turn = matrix_free_turn.TurnRangePayoffs
        stats = None
        with self.assertRaisesRegex(RuntimeError, "injected"):
            with patched_turn_memoizer("full44-blocked-runouts", 10) as stats:
                kernel = _kernel(turn_range_kernel.RankedRiverPayoffs)
                kernel.values(_Terminal("fold", (0.0, 0.0), winner=0),
                              [0.25, 0.75], 0)
                self.assertIsNot(turn_range_kernel.RankedRiverPayoffs, old_ranked)
                self.assertIsNot(matrix_free_turn.TurnRangePayoffs, old_turn)
                raise RuntimeError("injected")
        self.assertIs(turn_range_kernel.RankedRiverPayoffs, old_ranked)
        self.assertIs(matrix_free_turn.TurnRangePayoffs, old_turn)
        self.assertEqual(stats.entries_before_cleanup, 1)
        self.assertEqual(stats.entries_after_cleanup, 0)

    def test_nested_patch_and_oversized_direct_ranked_shape_reject_early(self):
        with patched_turn_memoizer("full44-blocked-runouts", 10):
            active_ranked = turn_range_kernel.RankedRiverPayoffs
            active_turn = matrix_free_turn.TurnRangePayoffs
            with self.assertRaisesRegex(RuntimeError, "nested"):
                with patched_turn_memoizer("full44-blocked-runouts", 10):
                    self.fail("nested patch unexpectedly installed")
            self.assertIs(turn_range_kernel.RankedRiverPayoffs, active_ranked)
            self.assertIs(matrix_free_turn.TurnRangePayoffs, active_turn)
            too_many_hands = ((('2c', '3c'), ('4d', '5d'), ('6c', '7c')),
                              (('8d', '9d'),))
            with self.assertRaisesRegex(ValueError, "two ranked hands"):
                turn_range_kernel.RankedRiverPayoffs(
                    BOARD, too_many_hands, ((1, 1, 1), (1,)), pot=100,
                )
            for _ in range(48):
                _kernel(turn_range_kernel.RankedRiverPayoffs)
            with self.assertRaisesRegex(ValueError, "48 branch kernels"):
                _kernel(turn_range_kernel.RankedRiverPayoffs)


if __name__ == "__main__":
    unittest.main()
