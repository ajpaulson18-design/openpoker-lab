"""Sol's closed-form vectors, real fallback failures, and rare-root witnesses."""
import math
import struct
import unittest

from pokerlab import matrix_free_turn, turn_range_kernel
from pokerlab.ranked_river import RankedRiverPayoffs
from pokerlab.river_tree import _Terminal
from pokerlab.turn_terminal_cache import (
    CacheRuntime, _BranchValuesProxy, admit_cache, install_branch_cache,
)


def bits(values):
    return struct.pack("!" + str(len(values)) + "d", *values)


def ordinary_kernel(pot):
    return turn_range_kernel.TurnRangePayoffs(
        ("Js", "8d", "4c", "2h"),
        ((("Ah", "As"), ("Kh", "Ks")), (("Ac", "Ad"), ("Kc", "Kd"))),
        ((1.0, 1.0), (1.0, 1.0)), pot=pot, runouts=("3c", "5h"))


class TurnTerminalCacheIndependentReviewTests(unittest.TestCase):
    def test_distinct_interleaved_models_match_closed_form_vectors_and_restore(self):
        first, second = ordinary_kernel(100), ordinary_kernel(200)
        original_classes = (matrix_free_turn.TurnRangePayoffs,
                            turn_range_kernel.RankedRiverPayoffs)
        originals = [{river: branch["kernel"] for river, branch in kernel._branches.items()}
                     for kernel in (first, second)]
        fold = _Terminal("fold", (0.0, 0.0), 0)
        with install_branch_cache(first, admit_cache(3, 2, 10)) as first_stats:
            with install_branch_cache(second, admit_cache(3, 2, 10)) as second_stats:
                for kernel, expected in ((first, [12.5, 12.5]),
                                          (second, [25.0, 25.0]),
                                          (first, [12.5, 12.5])):
                    result = kernel.values(fold, (1.0, 1.0), 0, ("3c",))
                    self.assertEqual(bits(result), bits(expected))
                    result[0] = -999.0
                    self.assertEqual(bits(kernel.values(fold, (1.0, 1.0), 0, ("3c",))), bits(expected))
                # Root integration bypasses branch.values and preserves its
                # four-pair/two-river exact probability law.
                before = first_stats.calls
                self.assertEqual(bits(first.values(fold, (1.0, 1.0), 0)), bits([25.0, 25.0]))
                self.assertEqual(first_stats.calls, before)
        for kernel, saved in zip((first, second), originals):
            for river, original in saved.items():
                self.assertIs(kernel._branches[river]["kernel"], original)
        self.assertEqual((matrix_free_turn.TurnRangePayoffs,
                          turn_range_kernel.RankedRiverPayoffs), original_classes)
        self.assertEqual(first_stats.to_dict()["entries_after_cleanup"], 0)
        self.assertEqual(second_stats.to_dict()["entries_after_cleanup"], 0)

    def test_original_fallback_limit_write_and_repeat_failure_are_preserved(self):
        original = RankedRiverPayoffs(
            ("2c", "7d", "9h", "Js", "Kd"),
            ((("Ah", "As"),), (("Ah", "Ks"), ("Qh", "Qs"))),
            ((1.0,), (1.0, 1e-12)), pot=100)
        runtime = CacheRuntime(admit_cache(1, 1, 10))
        proxy = _BranchValuesProxy(original, runtime, 0)
        initial = original.fallback_pair_checks
        proxy.fallback_pair_limit = initial + 2
        self.assertEqual(original.fallback_pair_limit, initial + 2)
        fold = _Terminal("fold", (0.0, 0.0), 0)
        first = proxy.values(fold, (1.0, 1.0), 0)
        self.assertTrue(all(math.isfinite(value) for value in first))
        self.assertGreater(original.fallback_pair_checks, initial)
        with self.assertRaisesRegex(ValueError, "fallback pair-check budget"):
            proxy.values(fold, (1.0, 1.0), 0)
        self.assertEqual(runtime.hits, 0)
        self.assertEqual(len(runtime.cache), 0)
        runtime.clear()

    def test_subnormal_root_values_and_atomic_pair_failure_remain_original(self):
        def build():
            kernel = turn_range_kernel.TurnRangePayoffs(
                ("2c", "5d", "9h", "Jc"),
                ((("3c", "4c"), ("Ah", "As")), (("Qh", "Qs"),)),
                ((1.0, math.ldexp(1.0, -1022)), (1.0,)),
                pot=2, runouts=("As", "Kd"))
            self.assertFalse(kernel.exceptional_conditioning)
            kernel.stable_root_pair_limit = 4
            return kernel
        baseline, candidate = build(), build()
        fold = _Terminal("fold", (0.0, 0.0), 0)
        expected = [1.0, math.ldexp(1.0, -1023)]
        original_branches = {r: b["kernel"] for r, b in candidate._branches.items()}
        with install_branch_cache(candidate, admit_cache(3, 2, 10)) as stats:
            for kernel in (baseline, candidate):
                self.assertEqual(bits(kernel.values(fold, (1.0,), 0, ("As",))), bits([0.5, 0.0]))
                self.assertEqual(bits(kernel.values(fold, (1.0,), 0)), bits(expected))
                self.assertEqual(bits(kernel.values(fold, (1.0,), 0)), bits(expected))
                self.assertEqual(bits(kernel.values(fold, (1.0,), 0, ("As",))), bits([0.5, 0.0]))
                before = (kernel.fallback_pair_checks, kernel.stable_root_fold_pair_checks)
                with self.assertRaisesRegex(ValueError, "Stable turn root-fold pair-check"):
                    kernel.values(fold, (1.0,), 0)
                self.assertEqual((kernel.fallback_pair_checks,
                                  kernel.stable_root_fold_pair_checks), before)
            self.assertEqual(stats.hits, 1)
            self.assertEqual(candidate.stable_root_fold_calls, 2)
            self.assertEqual(candidate.stable_root_fold_pair_checks, 4)
            self.assertEqual(candidate.fallback_pair_checks, baseline.fallback_pair_checks)
        for river, original in original_branches.items():
            self.assertIs(candidate._branches[river]["kernel"], original)


if __name__ == "__main__":
    unittest.main()
