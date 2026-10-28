"""Physical-support membership and no-expanded-map controls for the Q row plan."""
from dataclasses import replace
import gc
import unittest
from unittest.mock import patch

from pokerlab.exact_selected_solver import _prepare_exact_selected
from pokerlab.shared_public_topology import SharedPublicTopology, DecisionVertex
from pokerlab.suit_quotient_plan import SuitQuotientPlan
from tests.test_equivariant_selected_solver import symmetric_case
from tests.test_selected_operator_solver import request


def prepared(case=None):
    return _prepare_exact_selected(request(symmetric_case() if case is None else case),
        pair_diagnostics="compact", exact_arithmetic="dyadic", training_reduction="suit-equivariant")


class SuitQuotientPlanTests(unittest.TestCase):
    def test_actual_hand_exchange_uses_q_keys_and_complete_distinct_member_masks(self):
        value = prepared()
        with patch("pokerlab.exact_selected_kernel.rank_hand", side_effect=AssertionError("ranking")), \
             patch("pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.pair_probability_exact", side_effect=AssertionError("pairs")):
            plan = SuitQuotientPlan(value, 10)
        rows = list(plan.iter_rows())  # Test-only physical enumeration.
        seen = [0] * len(plan.keys)
        for key, menu in rows:
            q, offset, bit = plan.locate(key)
            self.assertFalse(seen[q] & bit)
            seen[q] |= bit
            self.assertEqual(menu, plan.menus[q])
            self.assertEqual(offset, plan.offsets[q])
        self.assertEqual(tuple(seen), plan.expected_masks)
        self.assertEqual(plan.receipt["group_size"], 2)
        self.assertEqual(len(plan.locations), len(plan.keys))
        self.assertEqual(len(rows), plan.receipt["expanded_information_rows"])
        self.assertEqual(len(plan.keys) * 2, len(rows))
        self.assertEqual(plan.receipt["retained_expanded_row_lookup_entries"], 0)
        self.assertEqual(value.kernel.statistics()["rank_calls"], 0)
        with self.assertRaises(AttributeError):
            plan.keys = ()
        with self.assertRaises(TypeError):
            plan.locations[plan.keys[0]] = 999
        with self.assertRaises(TypeError):
            plan._maps[0]["c"] = "d"
        original = plan.receipt
        changed = plan.receipt
        changed["public_graph_closure"]["permutations"].clear()
        changed["quotient_information_rows"] = 0
        self.assertEqual(plan.receipt, original)
        admission = plan.admission
        admission["group_size"] = 0
        self.assertEqual(plan.admission["group_size"], 2)

    def test_weight_breaking_selects_identity_and_keeps_distinct_full_histories(self):
        case = symmetric_case()
        case["sb_range"] = "AcAh:0.7,AdAh:0.3"
        case["bb_range"] = "KcKh:0.4,KdKh:0.6"
        value = prepared(case)
        plan = SuitQuotientPlan(value, 10)
        self.assertEqual(plan.group, (tuple("cdhs"),))
        self.assertEqual(len(plan.keys), plan.receipt["expanded_information_rows"])
        self.assertTrue(all(size == 1 for size in plan.sizes))
        by_vertex = {}
        for occurrence in value.topology.iter_occurrences():
            if isinstance(value.topology.vertices[occurrence.vertex_id], DecisionVertex):
                by_vertex.setdefault(occurrence.vertex_id, set()).add(occurrence.history)
        self.assertTrue(any(len(histories) > 1 for histories in by_vertex.values()))
        all_keys = {key for key, _ in plan.iter_rows()}
        self.assertEqual(set(plan.keys), all_keys)

    def test_fixed_holding_stabilizer_deduplicates_group_images(self):
        case = symmetric_case()
        case["sb_range"], case["bb_range"] = "AcAd", "KcKd"
        value = prepared(case)
        plan = SuitQuotientPlan(value, 10)
        self.assertEqual(plan.receipt["group_size"], 2)
        self.assertEqual(set(plan.sizes), {1, 2})
        self.assertEqual(sum(plan.sizes), plan.receipt["expanded_information_rows"])
        for size, mask in zip(plan.sizes, plan.expected_masks):
            self.assertEqual(mask, (1 << size) - 1)

    def test_duplicate_occurrence_rejects_instead_of_count_only_acceptance(self):
        value = prepared()
        original = SharedPublicTopology.iter_occurrences
        def repeated(topology):
            for item in original(topology):
                yield item
                if isinstance(topology.vertices[item.vertex_id], DecisionVertex):
                    yield item
        with patch.object(SharedPublicTopology, "iter_occurrences", new=repeated):
            with self.assertRaisesRegex(ValueError, "Duplicate supported"):
                SuitQuotientPlan(value, 10)

    def test_omitted_actual_member_rejects(self):
        value = prepared()
        original = SuitQuotientPlan.iter_rows
        def omitted(plan):
            skipped = False
            for key, menu in original(plan):
                if not skipped:
                    skipped = True
                    continue
                yield key, menu
        with patch.object(SuitQuotientPlan, "iter_rows", new=omitted):
            with self.assertRaisesRegex(ValueError, "lost a distinct supported"):
                SuitQuotientPlan(value, 10)

    def test_whole_work_rejects_before_support_and_q_rows(self):
        value = prepared()
        admission = {**value.admission, "combined_modeled_work_upper": 500_000_000}
        value = replace(value, admission=admission)
        with patch("pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.legal_hands", side_effect=AssertionError("support")):
            with self.assertRaisesRegex(ValueError, "group-search admission|whole-request additional work"):
                SuitQuotientPlan(value, 10)

    def test_mutated_or_expired_owner_rejects_without_a_cycle(self):
        value = prepared()
        plan = SuitQuotientPlan(value, 10)
        original = value.kernel.hands
        with self.assertRaises(AttributeError):
            value.kernel.hands = tuple(list(original))
        object.__setattr__(value.kernel, "hands", tuple(list(original)))
        with self.assertRaisesRegex(ValueError, "owner changed"):
            plan.locate(plan.keys[0])
        object.__setattr__(value.kernel, "hands", original)
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            del value
            with self.assertRaisesRegex(ValueError, "expired"):
                plan.locate(plan.keys[0])
        finally:
            if was_enabled:
                gc.enable()

    def test_iteration_mismatch_rejects_before_group_or_support(self):
        value = prepared()
        with patch("pokerlab.suit_quotient_plan._group", side_effect=AssertionError("group")):
            for iterations in (True, 100, 10000):
                with self.subTest(iterations=iterations), self.assertRaisesRegex(ValueError, "iteration count"):
                    SuitQuotientPlan(value, iterations)

    def test_malformed_or_foreign_history_and_actor_reject_as_value_error(self):
        value = prepared()
        plan = SuitQuotientPlan(value, 10)
        for history in (("flop@",), ("turn@xx",), ("bogus",)):
            with self.subTest(history=history), self.assertRaises(ValueError):
                plan.canonicalize((0, 0, history))
        player, hand, history = plan.keys[0]
        with self.assertRaisesRegex(ValueError, "actor"):
            plan.canonicalize((1 - player, hand, history))

    def test_partial_support_setup_clears_plan_state_with_retained_traceback(self):
        from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
        value = prepared()
        original = ExactSelectedRunoutKernel.legal_hands
        calls = 0
        def fail_later(kernel, prefix):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise MemoryError("controlled second-prefix support failure")
            return original(kernel, prefix)
        was_enabled = gc.isenabled()
        gc.disable()
        error = None
        try:
            with patch.object(ExactSelectedRunoutKernel, "legal_hands", new=fail_later):
                try:
                    SuitQuotientPlan(value, 10)
                except MemoryError as exc:
                    error = exc
            self.assertIsNotNone(error)
            frame = error.__traceback__
            caught = None
            while frame is not None:
                candidate = frame.tb_frame.f_locals.get("self")
                if type(candidate) is SuitQuotientPlan:
                    caught = candidate
                    break
                frame = frame.tb_next
            self.assertIsNotNone(caught)
            self.assertEqual(caught._support, {})
            self.assertEqual(caught.locations, {})
            self.assertEqual(caught._hand_maps, ())
            self.assertEqual(caught._maps, ())
            self.assertEqual(caught.keys, ())
        finally:
            if was_enabled:
                gc.enable()


if __name__ == "__main__":
    unittest.main()
