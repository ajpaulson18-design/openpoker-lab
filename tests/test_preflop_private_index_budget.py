import dis
import sys
import unittest
from unittest.mock import patch

from pokerlab.postflop_solver import _Chance
from pokerlab.preflop_vector_budget import estimate_vector_budget
from pokerlab.preflop_private_indices import compact_private_indices

from tests.test_preflop_vector_budget import _instrumentation_game


class PreflopPrivateIndexBudgetTests(unittest.TestCase):
    def test_default_delayed_and_convergence_budget_versions_stay_stable(self):
        root, worlds, infos = _instrumentation_game()
        base = estimate_vector_budget(root, worlds, infos, 8, "cfrplus",
                                       chance_type=_Chance)
        delayed = estimate_vector_budget(root, worlds, infos, 8, "cfrplus",
                                         chance_type=_Chance, averaging_delay=3)
        convergence = estimate_vector_budget(
            root, worlds, infos, 8, "cfrplus", chance_type=_Chance,
            averaging_delay=3, checkpoint_interval=2)
        self.assertEqual(base["budget_version"], "preflop-public-vector-budget-v1")
        self.assertEqual(delayed["budget_version"], "preflop-public-vector-delayed-budget-v2")
        self.assertEqual(convergence["budget_version"],
                         "preflop-public-vector-convergence-budget-v3")
        for estimate in (base, delayed, convergence):
            self.assertNotIn("private_indexing", estimate)
            self.assertNotIn("private_index_compaction_loop_entries_upper_bound", estimate)

    def test_compact_budget_uses_active_dimensions_and_charges_copy_work(self):
        root, worlds, infos = _instrumentation_game()
        original = estimate_vector_budget(root, worlds, infos, 8, "cfrplus",
                                          chance_type=_Chance, averaging_delay=3)
        compact = estimate_vector_budget(
            root, worlds, infos, 8, "cfrplus", chance_type=_Chance,
            averaging_delay=3, private_indexing="compact")
        compact_copy = compact_private_indices(worlds, infos)
        self.assertEqual(original["hand_counts"], [101, 4])
        self.assertEqual(compact["hand_counts"], [2, 2])
        self.assertEqual(compact["active_hand_counts"], [2, 2])
        self.assertEqual(compact["original_hand_counts"], [101, 4])
        self.assertEqual(compact["world_count"], original["world_count"])
        self.assertEqual(compact["prefix_edges"], original["prefix_edges"])
        self.assertEqual(
            compact["total_loop_entries_upper_bound"],
            compact["training_loop_entries_upper_bound"] +
            compact["diagnostics_loop_entries_upper_bound"] +
            compact["aggregation_loop_entries_upper_bound"] +
            compact["private_index_compaction_loop_entries_upper_bound"],
        )
        self.assertGreater(compact["private_index_compaction_loop_entries_upper_bound"], 0)
        self.assertLessEqual(compact["private_index_compaction_reference_slots_upper_bound"],
                             compact["private_index_compaction_reference_slot_limit"])
        expected_reference_slots = (
            128 + 4 * compact["private_index_world_fields"] + 4 * len(worlds) +
            12 * len(infos) + 16 * sum(compact["hand_counts"])
        )
        self.assertEqual(compact["private_index_compaction_reference_slots_upper_bound"],
                         expected_reference_slots)
        self.assertEqual(compact["private_indexing"], "compact")
        self.assertEqual(compact_copy.metadata["compact_hand_dimensions"], [2, 2])

    def test_caps_and_invalid_mode_reject_before_solver_creates_compact_copy(self):
        from pokerlab import preflop_solver

        kwargs = {
            "config": {"starting_stack": 2, "max_raises": 0,
                       "include_all_in": False},
            "runouts": ("2c3c4d7h8h",), "iterations": 10,
            "algorithm": "cfrplus", "averaging_delay": 5,
            "traversal": "public-batched", "diagnostics": "public-batched",
            "resource_model": "public-vector", "private_indexing": "compact",
        }
        with patch("pokerlab.preflop_vector_budget.MAX_COMPACTION_REFERENCE_SLOTS", 1), \
                patch.object(preflop_solver, "compact_private_indices") as copy_view:
            with self.assertRaisesRegex(ValueError, "references exceed"):
                preflop_solver.solve_preflop("AsAd", "KsKd", **kwargs)
            copy_view.assert_not_called()

        with patch.object(preflop_solver, "_enumerate_physical_worlds",
                          side_effect=AssertionError("enumeration started")), \
                patch.object(preflop_solver, "compact_private_indices") as copy_view:
            with self.assertRaisesRegex(ValueError, "private_indexing"):
                preflop_solver.solve_preflop(
                    "AsAd", "KsKd", runouts=kwargs["runouts"], iterations=10,
                    private_indexing="invalid")
            copy_view.assert_not_called()

    def test_compaction_copy_and_restore_for_iter_count_fits_extra_loop_bound(self):
        monitoring = getattr(sys, "monitoring", None)
        if monitoring is None:
            self.skipTest("sys.monitoring instruction events require Python 3.12+")
        root, worlds, infos = _instrumentation_game()
        budget = estimate_vector_budget(
            root, worlds, infos, 8, "cfrplus", chance_type=_Chance,
            averaging_delay=3, private_indexing="compact")
        observed = 0
        tool_id = next((index for index in range(6)
                        if monitoring.get_tool(index) is None), None)
        if tool_id is None:
            self.skipTest("no sys.monitoring tool ID is available")

        def instruction(code, offset):
            nonlocal observed
            filename = code.co_filename.replace("\\", "/").rsplit("/", 1)[-1]
            if (filename == "preflop_private_indices.py" and
                    code.co_code[offset] == dis.opmap["FOR_ITER"]):
                observed += 1

        allocated = False
        try:
            monitoring.use_tool_id(tool_id, "preflop-private-index-budget-test")
            allocated = True
            monitoring.register_callback(tool_id, monitoring.events.INSTRUCTION,
                                         instruction)
            monitoring.set_events(tool_id, monitoring.events.INSTRUCTION)
            compact = compact_private_indices(worlds, infos)
            policy = {key: [1.0 / action_count] * action_count
                      for key, action_count in compact.infos.items()}
            restored = compact.restore_policy(policy)
            self.assertEqual(list(restored), list(infos))
        finally:
            if allocated:
                try:
                    monitoring.set_events(tool_id, 0)
                    monitoring.register_callback(tool_id,
                                                 monitoring.events.INSTRUCTION, None)
                finally:
                    monitoring.free_tool_id(tool_id)
        self.assertGreater(observed, 0)
        self.assertGreaterEqual(
            budget["private_index_compaction_loop_entries_upper_bound"], observed)


if __name__ == "__main__":
    unittest.main()
