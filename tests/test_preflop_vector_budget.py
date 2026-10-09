import dis
import sys
import unittest
import weakref
from unittest.mock import patch

from pokerlab.postflop_solver import _Chance
from pokerlab.preflop_solver import _Action
from pokerlab.river_tree import _Node, _Terminal
from pokerlab.preflop_vector_budget import estimate_vector_budget


def _toy():
    branches = _Chance(
        ("flop",),
        {"a": _Terminal("showdown", (2, 1)),
         "b": _Terminal("showdown", (1, 2))},
    )
    root = _Node(
        (), 0, (_Action("check"), _Action("bet")),
        (_Terminal("showdown", (1, 1)), branches),
    )
    worlds = ((0, 2, 0.5, 1, "a"), (1, 3, 0.5, -1, "a"),
              (0, 2, 0.5, 1, "b"))
    infos = {(0, 100, ()): 2}
    return root, worlds, infos


def _instrumentation_game():
    branch_a = _Node(("after-a",), 1,
                     (_Action("fold"), _Action("call"), _Action("raise")),
                     (_Terminal("fold", (1, 2), 0),
                      _Terminal("showdown", (2, 2)),
                      _Terminal("showdown", (3, 3))))
    branch_b = _Node(("after-b",), 1,
                     (_Action("fold"), _Action("call")),
                     (_Terminal("fold", (1, 2), 0),
                      _Terminal("showdown", (2, 2))))
    chance = _Chance(("reveal",), {"a": branch_a, "b": branch_b})
    root = _Node((), 0,
                 (_Action("fold"), _Action("continue"), _Action("shove")),
                 (_Terminal("fold", (0.5, 1.0), 1), chance,
                  _Terminal("showdown", (3, 3))))
    worlds = ((100, 0, 0.25, 1, "a"), (100, 3, 0.25, -1, "a"),
              (95, 0, 0.25, 1, "b"), (95, 3, 0.25, -1, "b"))
    infos = {(0, 100, ()): 3, (0, 95, ()): 3,
             (1, 0, ("after-a",)): 3, (1, 3, ("after-a",)): 3,
             (1, 0, ("after-b",)): 2, (1, 3, ("after-b",)): 2}
    return root, worlds, infos


class PreflopVectorBudgetTests(unittest.TestCase):
    def test_known_toy_shape_prefix_repeats_and_dense_hand_holes(self):
        root, worlds, infos = _toy()
        estimate = estimate_vector_budget(root, worlds, infos, 2, "vanilla",
                                          chance_type=_Chance)
        self.assertEqual(estimate["hand_counts"], [101, 4])
        self.assertEqual(estimate["public_prefixes"], 3)
        self.assertEqual(estimate["prefix_edges"], 5)
        self.assertEqual(estimate["dense_prefix_slots"], 315)
        self.assertEqual(estimate["decision_nodes"], 1)
        self.assertEqual(estimate["chance_nodes"], 1)
        self.assertEqual(estimate["terminal_nodes"], 3)
        self.assertEqual(estimate["terminal_prefix_edge_visits"], 5)
        self.assertEqual(estimate["aggregation_count"], 2)
        self.assertEqual(estimate["training_traversals_per_iteration"], 1)
        self.assertEqual(estimate["information_set_action_slots"], 2)
        self.assertGreaterEqual(
            estimate["visitor_loop_entries_per_traversal_upper_bound"],
            10 * estimate["hand_counts"][0],
        )
        self.assertEqual(estimate["total_loop_entries_upper_bound"],
                         estimate["training_loop_entries_upper_bound"] +
                         estimate["diagnostics_loop_entries_upper_bound"] +
                         estimate["aggregation_loop_entries_upper_bound"])

    def test_cfrplus_charges_three_public_passes_and_rematching(self):
        root, worlds, infos = _toy()
        vanilla = estimate_vector_budget(root, worlds, infos, 1, "vanilla",
                                         chance_type=_Chance)
        cfrplus = estimate_vector_budget(root, worlds, infos, 1, "cfrplus",
                                         chance_type=_Chance)
        self.assertEqual(cfrplus["training_traversals_per_iteration"], 3)
        self.assertGreater(cfrplus["training_loop_entries_upper_bound"],
                           vanilla["training_loop_entries_upper_bound"])

    def test_terminal_no_info_skips_training_but_keeps_diagnostic_work(self):
        root = _Terminal("showdown", (0.5, 1.0))
        worlds = ((0, 1, 1.0, 1),)
        estimate = estimate_vector_budget(root, worlds, {}, 250, "cfrplus",
                                          chance_type=_Chance)
        self.assertEqual(estimate["training_loop_entries_upper_bound"], 0)
        self.assertEqual(estimate["aggregation_count"], 1)
        self.assertGreater(estimate["diagnostics_loop_entries_upper_bound"], 0)
        self.assertEqual(estimate["terminal_prefix_edge_visits"], 1)

    def test_caps_fail_closed(self):
        root, worlds, infos = _toy()
        with patch("pokerlab.preflop_vector_budget.MAX_PREFIX_EDGES", 1):
            with self.assertRaisesRegex(ValueError, "prefix edges"):
                estimate_vector_budget(root, worlds, infos, 1, "vanilla",
                                       chance_type=_Chance)
        with patch("pokerlab.preflop_vector_budget.MAX_DENSE_PREFIX_SLOTS", 1):
            with self.assertRaisesRegex(ValueError, "dense prefix slots"):
                estimate_vector_budget(root, worlds, infos, 1, "vanilla",
                                       chance_type=_Chance)
        with patch("pokerlab.preflop_vector_budget.MAX_INFO_ACTION_SLOTS", 1):
            with self.assertRaisesRegex(ValueError, "action slots"):
                estimate_vector_budget(root, worlds, infos, 1, "vanilla",
                                       chance_type=_Chance)
        with patch("pokerlab.preflop_vector_budget.MAX_TOTAL_LOOP_ENTRIES", 1):
            with self.assertRaisesRegex(ValueError, "loop entries"):
                estimate_vector_budget(root, worlds, infos, 1, "vanilla",
                                       chance_type=_Chance)

    def test_invalid_dimensions_are_rejected(self):
        root, worlds, infos = _toy()
        for iterations, algorithm in ((0, "vanilla"), (1, "not-cfr")):
            with self.subTest(iterations=iterations, algorithm=algorithm):
                with self.assertRaises(ValueError):
                    estimate_vector_budget(root, worlds, infos, iterations,
                                           algorithm, chance_type=_Chance)
        with self.assertRaises(ValueError):
            estimate_vector_budget(root, ((1326, 0, 1.0, 1),), {}, 1,
                                   "vanilla", chance_type=_Chance)

    def test_recursive_walk_closure_releases_infos_on_success_and_error(self):
        class Token:
            pass

        for invalid in (False, True):
            token = Token()
            token_ref = weakref.ref(token)
            history = (token,)
            root = _Node(history, 0, (_Action("only"),),
                         (object() if invalid else _Terminal("showdown", (1, 1)),))
            infos = {(0, 0, history): 1}
            if invalid:
                with self.assertRaisesRegex(TypeError, "unsupported public node"):
                    estimate_vector_budget(root, ((0, 0, 1.0, 0),), infos, 1,
                                           "vanilla", chance_type=_Chance)
            else:
                estimate_vector_budget(root, ((0, 0, 1.0, 0),), infos, 1,
                                       "vanilla", chance_type=_Chance)
            del root, infos, history, token
            self.assertIsNone(token_ref())

    def test_training_and_diagnostic_bounds_are_separate_and_nonzero(self):
        root, worlds, infos = _toy()
        combined = estimate_vector_budget(root, worlds, infos, 3, "dcfr",
                                          chance_type=_Chance)
        without_infos = estimate_vector_budget(_Terminal("showdown", (1, 1)),
                                              ((0, 0, 1.0, 0),), {}, 3,
                                              "dcfr", chance_type=_Chance)
        self.assertGreater(combined["training_loop_entries_upper_bound"], 0)
        self.assertGreater(combined["diagnostics_loop_entries_upper_bound"], 0)
        self.assertGreater(combined["aggregation_loop_entries_upper_bound"], 0)
        self.assertGreater(without_infos["diagnostics_loop_entries_upper_bound"], 0)
        self.assertEqual(without_infos["training_loop_entries_upper_bound"], 0)

    def test_total_bound_dominates_observed_backend_for_iter_entries(self):
        monitoring = getattr(sys, "monitoring", None)
        if monitoring is None:
            self.skipTest("sys.monitoring instruction events require Python 3.12+")
        from pokerlab.public_cfr import train_public_batched
        from pokerlab.public_diagnostics import evaluate_profile

        root, worlds, infos = _instrumentation_game()
        allowed = {"public_cfr.py", "public_diagnostics.py", "cfr.py"}
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                bound = estimate_vector_budget(root, worlds, infos, 1, algorithm,
                                               chance_type=_Chance)
                observed = 0
                tool_id = next((index for index in range(6)
                                if monitoring.get_tool(index) is None), None)
                if tool_id is None:
                    self.skipTest("no sys.monitoring tool ID is available")

                def instruction(code, offset):
                    nonlocal observed
                    if (code.co_filename.replace("\\", "/").rsplit("/", 1)[-1] in allowed and
                            code.co_code[offset] == dis.opmap["FOR_ITER"]):
                        observed += 1

                allocated = False
                try:
                    monitoring.use_tool_id(tool_id, "preflop-vector-budget-test")
                    allocated = True
                    monitoring.register_callback(tool_id, monitoring.events.INSTRUCTION,
                                                instruction)
                    monitoring.set_events(tool_id, monitoring.events.INSTRUCTION)
                    average = train_public_batched(root, worlds, infos, 1, algorithm,
                                                   pot=1.0, chance_type=_Chance)
                    evaluate_profile(root, worlds, average, pot=1.0, chance_type=_Chance)
                finally:
                    if allocated:
                        try:
                            monitoring.set_events(tool_id, 0)
                            monitoring.register_callback(tool_id,
                                                         monitoring.events.INSTRUCTION, None)
                        finally:
                            monitoring.free_tool_id(tool_id)
                self.assertGreater(observed, 0)
                self.assertGreaterEqual(bound["total_loop_entries_upper_bound"], observed)


if __name__ == "__main__":
    unittest.main()
