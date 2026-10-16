"""Unit tests for the bounded per-solve turn branch cache."""
import math
import struct
import unittest
from dataclasses import replace

from pokerlab.ranked_river import RankedRiverPayoffs
from pokerlab.river_tree import _Terminal
from pokerlab.turn_range_kernel import TurnRangePayoffs
from pokerlab.turn_terminal_cache import (
    CACHE_SLOTS_PER_CALL,
    FIXED_SETUP_SLOTS,
    MAX_CACHE_ENTRIES,
    MAX_CACHE_SLOT_WORK,
    SETUP_SLOTS_PER_BRANCH,
    CacheRuntime,
    _BranchValuesProxy,
    admit_cache,
    install_branch_cache,
)


def _hand(text):
    return tuple(sorted((text[:2], text[2:])))


def _ordinary_turn_kernel():
    board = ("Js", "8d", "4c", "2h")
    hands = ((_hand("AsAh"), _hand("KsKh")),
             (_hand("AcAd"), _hand("KcKd")))
    weights = ((0.5, 1.0), (1.0, 0.75))
    return TurnRangePayoffs(board, hands, weights, pot=100,
                            runouts=("3c", "5h"))


class TurnTerminalCacheTests(unittest.TestCase):
    def test_full_requested_admission_boundaries_and_exact_work_model(self):
        full = admit_cache(722, 48, 1_036)
        self.assertEqual(full.reserved_calls, 1_498_872)
        self.assertEqual(full.setup_slots, 16 * 48 + 64)
        self.assertEqual(full.reserved_slots, 29_978_272)
        with self.assertRaisesRegex(ValueError, "reservation"):
            admit_cache(722, 48, 1_037)

        selected = admit_cache(107, 2, 7_007)
        self.assertEqual(selected.reserved_calls, 1_499_926)
        self.assertEqual(selected.reserved_slots, 29_998_616)
        with self.assertRaisesRegex(ValueError, "reservation"):
            admit_cache(107, 2, 7_008)

        for bad in (True, 1.0, 0, -1):
            with self.subTest(terminal_count=bad), self.assertRaises(ValueError):
                admit_cache(bad, 1, 10)
        for bad in (True, 1.0, 0, 49):
            with self.subTest(branch_count=bad), self.assertRaises(ValueError):
                admit_cache(1, bad, 10)
        for bad in (True, 9, 10_001):
            with self.subTest(iterations=bad), self.assertRaises(ValueError):
                admit_cache(1, 1, bad)
        with self.assertRaisesRegex(ValueError, "up to 30000000"):
            admit_cache(1, 1, 10, slot_limit=MAX_CACHE_SLOT_WORK + 1)

    def test_lru_evicts_before_insert_and_returns_defensive_fresh_lists(self):
        admission = admit_cache(1, 1, 10)
        runtime = CacheRuntime(admission, entry_limit=1)
        runtime.reserve_call()
        runtime.insert(("first",), [1.0, 2.0])
        first = runtime.get(("first",))
        self.assertEqual(first, [1.0, 2.0])
        first[0] = 999.0
        self.assertEqual(runtime.get(("first",)), [1.0, 2.0])
        runtime.insert(("second",), [3.0])
        self.assertEqual(runtime.evictions, 1)
        self.assertEqual(list(runtime.cache), [("second",)])
        self.assertEqual(runtime.maximum_entries, 1)
        runtime.clear()
        self.assertEqual(runtime.entries_before_cleanup, 1)
        self.assertEqual(runtime.entries_after_cleanup, 0)
        self.assertEqual(runtime.to_dict()["current_entries"], 0)

    def test_runtime_call_guard_keeps_full_admission_when_test_limit_is_lowered(self):
        admission = admit_cache(722, 48, 1_000)
        runtime = CacheRuntime(admission, call_limit=1)
        self.assertEqual(admission.reserved_calls, 1_446_888)
        self.assertEqual(admission.reserved_slots, 28_938_592)
        runtime.reserve_call()
        with self.assertRaisesRegex(ValueError, "call ceiling"):
            runtime.reserve_call()
        self.assertEqual(runtime.calls, 1)

    def test_forged_admission_fields_are_revalidated_before_cache_allocation(self):
        admission = admit_cache(1, 1, 10)
        for field, bad in (
            ("terminal_count", True),
            ("reserved_calls", True),
            ("setup_slots", 1.0),
            ("reserved_slots", -1),
            ("slot_limit", MAX_CACHE_SLOT_WORK + 1),
        ):
            with self.subTest(field=field), self.assertRaises((ValueError, TypeError)):
                forged = replace(admission, **{field: bad})
                CacheRuntime(forged)

    def test_cleaned_runtime_and_nested_installation_cannot_be_reused(self):
        kernel = _ordinary_turn_kernel()
        branches = list(kernel._branches.values())
        admission = admit_cache(4, len(branches), 10)
        with install_branch_cache(kernel, admission) as runtime:
            retained_proxy = branches[0]["kernel"]
            with self.assertRaisesRegex(ValueError, "Nested or foreign"):
                install_branch_cache(kernel, admission)
            retained_proxy.values(
                _Terminal("fold", (0.0, 0.0), winner=0), (1.0, 0.5), 0)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            runtime.get(("missing",))
        with self.assertRaisesRegex(RuntimeError, "closed"):
            runtime.insert(("late",), [1.0])
        with self.assertRaisesRegex(RuntimeError, "cannot accept calls"):
            retained_proxy.values(
                _Terminal("fold", (0.0, 0.0), winner=0), (1.0, 0.5), 0)

    def test_installer_rechecks_filtered_branch_hand_shape(self):
        kernel = _ordinary_turn_kernel()
        branch = next(iter(kernel._branches.values()))
        branch["kernel"].hands = ((), branch["kernel"].hands[1])
        admission = admit_cache(4, len(kernel._branches), 10)
        with self.assertRaisesRegex(ValueError, "one-to-two-hand shape"):
            install_branch_cache(kernel, admission)

    def test_proxy_keys_raw_reach_bits_terminal_and_branch_and_forwards_limit(self):
        kernel = _ordinary_turn_kernel()
        branch0, branch1 = list(kernel._branches.values())[:2]
        original = branch0["kernel"]
        runtime = CacheRuntime(admit_cache(1, 2, 10))
        proxy = _BranchValuesProxy(original, runtime, 0)
        same_model_other_branch = _BranchValuesProxy(original, runtime, 1)
        terminal = _Terminal("fold", (10.0, 10.0), winner=0)
        reach = (1.0, 0.5)

        expected = original.values(terminal, reach, 0)
        got = proxy.values(terminal, reach, 0)
        got[0] = 999.0
        self.assertEqual(proxy.values(terminal, reach, 0), expected)
        self.assertEqual(runtime.hits, 1)
        self.assertEqual(runtime.misses, 1)
        self.assertEqual(same_model_other_branch.values(terminal, reach, 0), expected)
        self.assertEqual(runtime.misses, 2)

        proxy.values(terminal, (-0.0, 0.5), 0)
        proxy.values(terminal, (0.0, 0.5), 0)
        self.assertNotEqual(_bits(-0.0), _bits(0.0))
        self.assertEqual(runtime.misses, 4)

        proxy.values(_Terminal("fold", (0.0, 0.0), winner=0), reach, 0)
        proxy.values(_Terminal("fold", (0.0, 0.0), winner=1), reach, 0)
        proxy.values(_Terminal("showdown", (10.0, 10.0)), reach, 0)
        self.assertEqual(runtime.misses, 7)

        proxy.fallback_pair_limit = 17
        self.assertEqual(original.fallback_pair_limit, 17)
        with self.assertRaises(AttributeError):
            proxy.weights = ((1.0,), (1.0,))
        with self.assertRaises(AttributeError):
            proxy._runtime = CacheRuntime(admit_cache(1, 1, 10))
        self.assertIs(branch1, kernel._branches[list(kernel._branches)[1]])

    def test_invalid_terminal_player_and_reach_are_rechecked_on_a_hit(self):
        kernel = _ordinary_turn_kernel()
        original = next(iter(kernel._branches.values()))["kernel"]
        runtime = CacheRuntime(admit_cache(1, 1, 10))
        proxy = _BranchValuesProxy(original, runtime, 0)
        terminal = _Terminal("fold", (0.0, 0.0), winner=0)
        reach = (1.0, 0.5)
        proxy.values(terminal, reach, 0)
        self.assertEqual(runtime.hits, 0)

        invalid_calls = (
            (terminal, reach, True),
            (terminal, (1.0, True), 0),
            (terminal, (1.0, math.nan), 0),
            (_Terminal("fold", (0.0, math.inf), winner=0), reach, 0),
            (_Terminal("fold", (0.0, 0.0), winner=True), reach, 0),
        )
        for bad_terminal, bad_reach, player in invalid_calls:
            with self.subTest(terminal=bad_terminal, reach=bad_reach, player=player):
                with self.assertRaises(ValueError):
                    proxy.values(bad_terminal, bad_reach, player)
        self.assertEqual(runtime.hits, 0)

        exhausted = CacheRuntime(admit_cache(1, 1, 10), call_limit=0)
        invalid_proxy = _BranchValuesProxy(original, exhausted, 0)
        with self.assertRaisesRegex(ValueError, "player must"):
            invalid_proxy.values(terminal, reach, True)
        self.assertEqual(exhausted.calls, 0)

    def test_only_successful_zero_fallback_calls_are_cached(self):
        board = ("2c", "7d", "9h", "Js", "Kd")
        original = RankedRiverPayoffs(
            board,
            ((_hand("AhAs"),), (_hand("AhKs"), _hand("QhQs"))),
            ((1.0,), (1.0, 1e-12)), pot=100,
        )
        runtime = CacheRuntime(admit_cache(1, 1, 10))
        proxy = _BranchValuesProxy(original, runtime, 0)
        fold = _Terminal("fold", (0.0, 0.0), winner=0)
        reach = (1.0, 1.0)
        expected = original.values(fold, reach, 0)
        before = original.fallback_pair_checks
        self.assertGreater(before, 0)
        proxy.values(fold, reach, 0)
        after_first = original.fallback_pair_checks
        proxy.values(fold, reach, 0)
        self.assertGreater(after_first, before)
        self.assertGreater(original.fallback_pair_checks, after_first)
        self.assertEqual(runtime.hits, 0)
        self.assertEqual(runtime.misses, 2)
        self.assertEqual(len(runtime.cache), 0)
        self.assertEqual(proxy.values(fold, reach, 0), expected)

    def test_branch_references_restore_after_success_failure_and_partial_install(self):
        kernel = _ordinary_turn_kernel()
        branches = list(kernel._branches.values())
        originals = [branch["kernel"] for branch in branches]
        admission = admit_cache(4, len(branches), 10)
        context = install_branch_cache(kernel, admission)
        with context as runtime:
            self.assertTrue(all(branch["kernel"] is not original
                                for branch, original in zip(branches, originals)))
            first_branch = next(iter(kernel._branches.values()))
            first_branch["kernel"].values(
                _Terminal("fold", (0.0, 0.0), winner=0), (1.0, 0.5), 0)
        self.assertEqual(runtime.entries_after_cleanup, 0)
        self.assertEqual(len(runtime.cache), 0)
        self.assertTrue(all(branch["kernel"] is original
                            for branch, original in zip(branches, originals)))

        with self.assertRaisesRegex(RuntimeError, "injected"):
            with install_branch_cache(kernel, admission) as failed_runtime:
                next(iter(kernel._branches.values()))["kernel"].values(
                    _Terminal("fold", (0.0, 0.0), winner=0), (1.0, 0.5), 0)
                raise RuntimeError("injected")
        self.assertTrue(all(branch["kernel"] is original
                            for branch, original in zip(branches, originals)))
        self.assertEqual(len(failed_runtime.cache), 0)

        class FailingBranch(dict):
            def __init__(self, values, fail=False):
                super().__init__(values)
                self.fail = fail
                self.proxy_seen = False

            def __setitem__(self, key, value):
                if key == "kernel" and isinstance(value, _BranchValuesProxy):
                    self.proxy_seen = True
                if self.fail and key == "kernel" and isinstance(value, _BranchValuesProxy):
                    raise RuntimeError("partial installation")
                super().__setitem__(key, value)

        original_branch_map = kernel._branches
        original_branches = list(original_branch_map.values())
        originals = [branch["kernel"] for branch in original_branches]
        failing = {
            river: FailingBranch(branch, fail=(index == 1))
            for index, (river, branch) in enumerate(original_branch_map.items())
        }
        kernel._branches = failing
        with self.assertRaisesRegex(RuntimeError, "partial installation"):
            install_branch_cache(kernel, admission).__enter__()
        self.assertTrue(failing[list(failing)[0]].proxy_seen)
        self.assertTrue(all(branch["kernel"] is original
                            for branch, original in zip(failing.values(), originals)))

    def test_interleaved_contexts_keep_runtimes_and_branch_refs_separate(self):
        first = _ordinary_turn_kernel()
        second = _ordinary_turn_kernel()
        first_originals = [branch["kernel"] for branch in first._branches.values()]
        second_originals = [branch["kernel"] for branch in second._branches.values()]
        first_admission = admit_cache(4, len(first._branches), 10)
        second_admission = admit_cache(4, len(second._branches), 10)
        with install_branch_cache(first, first_admission) as first_runtime:
            with install_branch_cache(second, second_admission) as second_runtime:
                self.assertIsNot(first_runtime, second_runtime)
                for kernel in (first, second):
                    next(iter(kernel._branches.values()))["kernel"].values(
                        _Terminal("fold", (4.0, 4.0), winner=1), (1.0, 0.5), 0)
                self.assertEqual(first_runtime.calls, 1)
                self.assertEqual(second_runtime.calls, 1)
        self.assertTrue(all(branch["kernel"] is original for branch, original in
                            zip(first._branches.values(), first_originals)))
        self.assertTrue(all(branch["kernel"] is original for branch, original in
                            zip(second._branches.values(), second_originals)))


def _bits(value):
    return struct.pack(">d", value)


if __name__ == "__main__":
    unittest.main()
