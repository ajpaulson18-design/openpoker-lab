"""Whole-game controls for the suit-quotiented Q-buffer CFR+ trainer."""
from array import array as _array
import gc
import unittest
import weakref
from unittest.mock import patch

from pokerlab.equivariant_packed_cfr import train_equivariant_packed
from pokerlab.exact_selected_solver import _OnePrefixMarginals, _prepare_exact_selected
from pokerlab.shared_topology_view import layout_census_shared
from pokerlab.suit_quotient_cfr import layout_census_suit_quotient, train_suit_quotient
from pokerlab.suit_quotient_plan import SuitQuotientPlan
from tests.test_equivariant_selected_solver import symmetric_case
from tests.test_selected_operator_solver import request


def _prepared(case=None, iterations=10):
    req = request(symmetric_case() if case is None else case, iterations=iterations)
    prepared = _prepare_exact_selected(req, pair_diagnostics="compact",
        exact_arithmetic="dyadic", training_reduction="suit-equivariant",
        strategy_storage="suit-quotient")
    return prepared


def _plan(case=None, iterations=10):
    prepared = _prepared(case, iterations)
    return prepared, SuitQuotientPlan(prepared, iterations)


def _bits(policy):
    return {key: tuple(value.hex() for value in row) for key, row in policy.items()}


class _TrackedArray:
    itemsize = _array("d").itemsize

    def __init__(self, typecode, values=()):
        self.value = _array(typecode, values)

    def __len__(self):
        return len(self.value)

    def __getitem__(self, index):
        return self.value[index]

    def __setitem__(self, index, value):
        self.value[index] = value

    def __iter__(self):
        return iter(self.value)

    def __mul__(self, count):
        result = object.__new__(_TrackedArray)
        result.value = self.value * count
        return result


class SuitQuotientCfrTests(unittest.TestCase):
    def test_rank_free_layout_receipt_matches_literal_expanded_census(self):
        prepared, plan = _plan()
        quotient = layout_census_suit_quotient(prepared.view, plan,
            prepared.kernel.hand_counts, 10)
        infos = {key: len(menu) for key, menu in plan.iter_rows()}
        literal = layout_census_shared(prepared.view, infos,
            prepared.kernel.hand_counts, 10)
        for key, value in literal.items():
            self.assertEqual(quotient["expanded_layout_equivalent"][key], value, key)
        self.assertEqual(quotient["expanded_layout_equivalent"]["information_sets"],
                         plan.receipt["expanded_information_rows"])

    def test_symmetric_hand_exchange_matches_unquotiented_policy_bits(self):
        prepared, plan = _plan()
        infos = {key: len(menu) for key, menu in plan.iter_rows()}
        q_policy, receipt = train_suit_quotient(prepared.view.root, plan, 10,
            operator=prepared.adapter, marginals=_OnePrefixMarginals(prepared.adapter),
            return_receipt=True, shared_view=prepared.view)
        reference = train_equivariant_packed(prepared.view.root, infos, 10,
            operator=prepared.adapter, marginals=_OnePrefixMarginals(prepared.adapter),
            shared_view=prepared.view)
        self.assertEqual(_bits(q_policy), _bits(reference))
        self.assertEqual(receipt["q_numeric_buffer_bytes"], 32 * plan.receipt["quotient_action_slots"])
        self.assertEqual(receipt["semantic_row_lookup_entries"], len(plan.locations))
        self.assertEqual(receipt["retained_expanded_row_lookup_entries"], 0)
        self.assertLess(receipt["quotient_action_slots"], receipt["expanded_action_slots"])
        self.assertEqual(receipt["expanded_policy_shadow_rows"], len(q_policy))

    def test_identity_weighted_and_mixed_stabilizers_match_reference(self):
        cases = []
        weighted = symmetric_case()
        weighted["sb_range"] = "AcAh:0.7,AdAh:0.3"
        weighted["bb_range"] = "KcKh:0.4,KdKh:0.6"
        cases.append(weighted)
        fixed = symmetric_case()
        fixed["sb_range"], fixed["bb_range"] = "AcAd", "KcKd"
        cases.append(fixed)
        fixed_sizes = None
        for case in cases:
            prepared, plan = _plan(case)
            if case is fixed:
                fixed_sizes = plan.sizes
            infos = {key: len(menu) for key, menu in plan.iter_rows()}
            actual = train_suit_quotient(prepared.view.root, plan, 10,
                operator=prepared.adapter, marginals=_OnePrefixMarginals(prepared.adapter),
                shared_view=prepared.view)
            expected = train_equivariant_packed(prepared.view.root, infos, 10,
                operator=prepared.adapter, marginals=_OnePrefixMarginals(prepared.adapter),
                shared_view=prepared.view)
            self.assertEqual(_bits(actual), _bits(expected))
        self.assertTrue(fixed_sizes.count(1) > 0)
        self.assertTrue(fixed_sizes.count(2) > 0)

    def test_only_q_length_numeric_buffers_are_allocated(self):
        prepared, plan = _plan()
        lengths = []

        def factory(typecode, values=()):
            value = _TrackedArray(typecode, values)
            class _Recorder(_TrackedArray):
                def __mul__(self, count):
                    result = super().__mul__(count)
                    lengths.append((typecode, len(result)))
                    return result
            wrapped = object.__new__(_Recorder)
            wrapped.value = value.value
            return wrapped

        with patch("pokerlab.suit_quotient_cfr.array", side_effect=factory):
            train_suit_quotient(prepared.view.root, plan, 10,
                operator=prepared.adapter, marginals=_OnePrefixMarginals(prepared.adapter),
                shared_view=prepared.view)
        self.assertEqual([n for kind, n in lengths if kind == "d"],
                         [plan.receipt["quotient_action_slots"]] * 4)

    def test_q_buffers_are_gone_before_expanded_output_stream_starts(self):
        prepared, plan = _plan()
        refs = []
        iter_calls = 0
        original_iter_rows = SuitQuotientPlan.iter_rows

        class Tracked(_TrackedArray):
            def __mul__(self, count):
                result = super().__mul__(count)
                refs.append(weakref.ref(result))
                return result

        def checked_rows(self):
            nonlocal iter_calls
            iter_calls += 1
            if iter_calls == 2:
                self_assert = all(ref() is None for ref in refs)
                if not self_assert:
                    raise AssertionError("Q arrays remain live at expanded-output streaming.")
            yield from original_iter_rows(self)

        with patch("pokerlab.suit_quotient_cfr.array", side_effect=lambda t, v=(): Tracked(t, v)), \
             patch.object(SuitQuotientPlan, "iter_rows", new=checked_rows):
            result = train_suit_quotient(prepared.view.root, plan, 10,
                operator=prepared.adapter, marginals=_OnePrefixMarginals(prepared.adapter),
                shared_view=prepared.view)
        self.assertEqual(iter_calls, 2)
        self.assertEqual(len(result), plan._receipt["expanded_information_rows"])
        self.assertEqual(len(refs), 4)

    def test_duplicate_mismatched_and_missing_orbit_members_abort(self):
        prepared, plan = _plan()
        original_locate = plan.locate

        def duplicate(key):
            q, offset, _bit = original_locate(key)
            return q, offset, 1

        with patch.object(SuitQuotientPlan, "locate", new=lambda self, key: duplicate(key)):
            with self.assertRaisesRegex(ValueError, "Duplicate Q member"):
                train_suit_quotient(prepared.view.root, plan, 10,
                    operator=prepared.adapter, marginals=_OnePrefixMarginals(prepared.adapter),
                    shared_view=prepared.view)

        with patch("pokerlab.suit_quotient_cfr._sub", side_effect=[0.125, 0.25] * 100000):
            with self.assertRaisesRegex(ValueError, "increments differ"):
                train_suit_quotient(prepared.view.root, plan, 10,
                    operator=prepared.adapter, marginals=_OnePrefixMarginals(prepared.adapter),
                    shared_view=prepared.view)

        def omit_one(key):
            q, offset, bit = original_locate(key)
            if q == 0 and bit == 2:
                return q, offset, 0
            return q, offset, bit

        with patch.object(SuitQuotientPlan, "locate", new=lambda self, key: omit_one(key)):
            with self.assertRaisesRegex(ValueError, "Incomplete Q member coverage"):
                train_suit_quotient(prepared.view.root, plan, 10,
                    operator=prepared.adapter, marginals=_OnePrefixMarginals(prepared.adapter),
                    shared_view=prepared.view)

    def test_numeric_buffers_release_when_training_raises_with_gc_disabled(self):
        prepared, plan = _plan()
        refs = []

        class Tracked(_TrackedArray):
            def __mul__(self, count):
                result = super().__mul__(count)
                refs.append(weakref.ref(result))
                return result

        def factory(typecode, values=()):
            return Tracked(typecode, values)

        was_enabled = gc.isenabled()
        gc.disable()
        try:
            with patch("pokerlab.suit_quotient_cfr.array", side_effect=factory), \
                 patch("pokerlab.exact_selected_float_adapter.ExactSelectedFloatAdapter.values",
                       side_effect=RuntimeError("injected callback failure")):
                try:
                    train_suit_quotient(prepared.view.root, plan, 10,
                        operator=prepared.adapter, marginals=_OnePrefixMarginals(prepared.adapter),
                        shared_view=prepared.view)
                except RuntimeError as error:
                    self.assertIn("injected callback failure", str(error))
            self.assertEqual(len(refs), 4)
            self.assertTrue(all(ref() is None for ref in refs))
        finally:
            if was_enabled:
                gc.enable()

    def test_late_numeric_allocation_failure_releases_prior_q_buffers(self):
        prepared, plan = _plan()
        refs = []
        allocations = 0

        class Tracked(_TrackedArray):
            def __mul__(self, count):
                nonlocal allocations
                allocations += 1
                if allocations == 4:
                    raise MemoryError("injected fourth Q allocation failure")
                result = super().__mul__(count)
                refs.append(weakref.ref(result))
                return result

        def factory(typecode, values=()):
            return Tracked(typecode, values)

        was_enabled = gc.isenabled()
        gc.disable()
        try:
            with patch("pokerlab.suit_quotient_cfr.array", side_effect=factory):
                try:
                    train_suit_quotient(prepared.view.root, plan, 10,
                        operator=prepared.adapter, marginals=_OnePrefixMarginals(prepared.adapter),
                        shared_view=prepared.view)
                except MemoryError as error:
                    retained_traceback = error.__traceback__
            self.assertIsNotNone(retained_traceback)
            self.assertEqual(allocations, 4)
            self.assertEqual(len(refs), 3)
            self.assertTrue(all(ref() is None for ref in refs))
        finally:
            if was_enabled:
                gc.enable()

    def test_member_mismatch_releases_q_buffers_without_a_partial_result(self):
        prepared, plan = _plan()
        refs = []

        class Tracked(_TrackedArray):
            def __mul__(self, count):
                result = super().__mul__(count)
                refs.append(weakref.ref(result))
                return result

        calls = 0
        original_sub = __import__("pokerlab.suit_quotient_cfr", fromlist=["_sub"])._sub

        def mismatch(left, right, label):
            nonlocal calls
            calls += 1
            value = original_sub(left, right, label)
            return value if calls % 2 else value + 1e-12

        was_enabled = gc.isenabled()
        gc.disable()
        try:
            with patch("pokerlab.suit_quotient_cfr.array", side_effect=lambda t, v=(): Tracked(t, v)), \
                 patch("pokerlab.suit_quotient_cfr._sub", side_effect=mismatch):
                try:
                    result = train_suit_quotient(prepared.view.root, plan, 10,
                        operator=prepared.adapter, marginals=_OnePrefixMarginals(prepared.adapter),
                        shared_view=prepared.view)
                except ValueError as error:
                    self.assertIn("increments differ", str(error))
                    self.assertNotIn("result", locals())
            self.assertEqual(len(refs), 4)
            self.assertTrue(all(ref() is None for ref in refs))
        finally:
            if was_enabled:
                gc.enable()


if __name__ == "__main__":
    unittest.main()
