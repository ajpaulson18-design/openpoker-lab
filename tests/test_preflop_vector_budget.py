import dis
import sys
import unittest
import weakref
from unittest.mock import patch

from pokerlab.postflop_solver import _Chance
from pokerlab.preflop_solver import _Action
from pokerlab.river_tree import _Node, _Terminal
from pokerlab.preflop_vector_budget import estimate_vector_budget
from pokerlab.preflop_delayed_cfrplus import train_delayed_public_cfrplus


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

    def test_delayed_cfrplus_budget_metadata_and_no_info_path(self):
        root, worlds, infos = _instrumentation_game()
        estimate = estimate_vector_budget(root, worlds, infos, 8, "cfrplus",
                                          chance_type=_Chance, averaging_delay=3)
        self.assertEqual(estimate["budget_version"],
                         "preflop-public-vector-delayed-budget-v2")
        self.assertEqual(estimate["averaging_delay"], 3)
        self.assertEqual(estimate["training_regret_passes"], 16)
        self.assertEqual(estimate["training_average_passes"], 5)
        self.assertEqual(estimate["training_policy_match_rows"], 9 * len(infos))
        self.assertIsNone(estimate["training_traversals_per_iteration"])
        self.assertGreater(estimate["total_loop_entries_upper_bound"],
                           estimate["diagnostics_loop_entries_upper_bound"])

        terminal = _Terminal("showdown", (0.5, 1.0))
        no_info = estimate_vector_budget(terminal, ((0, 0, 1.0, 1),), {}, 8,
                                         "cfrplus", chance_type=_Chance,
                                         averaging_delay=3)
        self.assertEqual(no_info["training_loop_entries_upper_bound"], 0)
        self.assertEqual(no_info["training_average_passes"], 0)
        self.assertEqual(no_info["training_regret_passes"], 0)
        self.assertEqual(no_info["training_policy_match_rows"], 0)
        self.assertEqual(no_info["aggregation_count"], 1)
        self.assertGreater(no_info["diagnostics_loop_entries_upper_bound"], 0)

    def test_delayed_budget_rejects_invalid_delay_before_census(self):
        for delay in (True, -1, 1.5, 1, "1"):
            with self.subTest(delay=delay):
                with self.assertRaises(ValueError):
                    estimate_vector_budget(object(), object(), object(), 1,
                                           "cfrplus", chance_type=_Chance,
                                           averaging_delay=delay)

    def test_delayed_adapter_and_exact_diagnostics_fit_measured_loop_envelope(self):
        monitoring = getattr(sys, "monitoring", None)
        if monitoring is None:
            self.skipTest("sys.monitoring instruction events require Python 3.12+")
        from pokerlab.public_diagnostics import evaluate_profile

        root, worlds, infos = _instrumentation_game()
        iterations, delay = 3, 1
        budget = estimate_vector_budget(root, worlds, infos, iterations, "cfrplus",
                                        chance_type=_Chance,
                                        averaging_delay=delay)
        observed = 0
        allowed = {"preflop_delayed_cfrplus.py", "public_cfr.py",
                   "public_diagnostics.py", "cfr.py"}
        tool_id = next((index for index in range(6)
                        if monitoring.get_tool(index) is None), None)
        if tool_id is None:
            self.skipTest("no sys.monitoring tool ID is available")

        def instruction(code, offset):
            nonlocal observed
            filename = code.co_filename.replace("\\", "/").rsplit("/", 1)[-1]
            if filename in allowed and code.co_code[offset] == dis.opmap["FOR_ITER"]:
                observed += 1

        allocated = False
        try:
            monitoring.use_tool_id(tool_id, "delayed-vector-budget-test")
            allocated = True
            monitoring.register_callback(tool_id, monitoring.events.INSTRUCTION,
                                         instruction)
            monitoring.set_events(tool_id, monitoring.events.INSTRUCTION)
            profile = train_delayed_public_cfrplus(
                root, worlds, infos, iterations, averaging_delay=delay,
                pot=1.0, chance_type=_Chance,
            )
            evaluate_profile(root, worlds, profile, pot=1.0, chance_type=_Chance)
        finally:
            if allocated:
                try:
                    monitoring.set_events(tool_id, 0)
                    monitoring.register_callback(tool_id,
                                                 monitoring.events.INSTRUCTION, None)
                finally:
                    monitoring.free_tool_id(tool_id)
        self.assertGreater(observed, 0)
        self.assertGreaterEqual(budget["total_loop_entries_upper_bound"], observed)

    def test_convergence_budget_counts_snapshots_checks_and_final_reserve(self):
        root, worlds, infos = _instrumentation_game()
        total, delay, interval = 7, 3, 2
        estimate = estimate_vector_budget(
            root, worlds, infos, total, "cfrplus", chance_type=_Chance,
            averaging_delay=delay, checkpoint_interval=interval,
        )
        checkpoints = (total + interval - 1) // interval
        exact_checks = checkpoints - delay // interval
        self.assertEqual(checkpoints, 4)  # 2, 4, 6, and final 7
        self.assertEqual(exact_checks, 3)  # only positive-average snapshots
        self.assertEqual(estimate["checkpoint_count_upper_bound"], checkpoints)
        self.assertEqual(estimate["checkpoint_diagnostics_upper_bound"], exact_checks)
        self.assertEqual(estimate["diagnostic_evaluations_upper_bound"], exact_checks + 1)
        # One training aggregation plus each checkpoint evaluation and the
        # separately reserved final evaluation.
        self.assertEqual(estimate["aggregation_count"], 1 + exact_checks + 1)

        terminal = _Terminal("showdown", (0.5, 1.0))
        no_info = estimate_vector_budget(
            terminal, ((0, 0, 1.0, 1),), {}, total, "cfrplus",
            chance_type=_Chance, averaging_delay=delay,
            checkpoint_interval=interval,
        )
        self.assertEqual(no_info["checkpoint_count_upper_bound"], 0)
        self.assertEqual(no_info["checkpoint_diagnostics_upper_bound"], 0)
        self.assertEqual(no_info["diagnostic_evaluations_upper_bound"], 1)
        self.assertEqual(no_info["aggregation_count"], 1)
        self.assertEqual(no_info["training_loop_entries_upper_bound"], 0)

    def test_convergence_budget_options_fail_before_tree_census(self):
        # Invalid options must be rejected before even inspecting these
        # deliberately unusable census inputs.
        for interval in (True, 0, -1, 1.5):
            with self.subTest(interval=interval):
                with self.assertRaises(ValueError):
                    estimate_vector_budget(
                        object(), object(), object(), 7, "cfrplus", chance_type=_Chance,
                        averaging_delay=3, checkpoint_interval=interval,
                    )
        for algorithm, delay, interval in (
            ("vanilla", 3, 2), ("cfrplus", 0, 2),
        ):
            with self.subTest(algorithm=algorithm, delay=delay):
                with self.assertRaises(ValueError):
                    estimate_vector_budget(
                        object(), object(), object(), 7, algorithm, chance_type=_Chance,
                        averaging_delay=delay, checkpoint_interval=interval,
                    )

    def test_convergence_loop_envelope_covers_checkpoint_normalization_and_checks(self):
        monitoring = getattr(sys, "monitoring", None)
        if monitoring is None:
            self.skipTest("sys.monitoring instruction events require Python 3.12+")
        from pokerlab.public_diagnostics import evaluate_profile

        root, worlds, infos = _instrumentation_game()
        total, delay, interval = 7, 3, 2
        budget = estimate_vector_budget(
            root, worlds, infos, total, "cfrplus", chance_type=_Chance,
            averaging_delay=delay, checkpoint_interval=interval,
        )
        observed = 0
        allowed = {"preflop_delayed_cfrplus.py", "public_cfr.py",
                   "public_diagnostics.py", "cfr.py"}
        tool_id = next((index for index in range(6)
                        if monitoring.get_tool(index) is None), None)
        if tool_id is None:
            self.skipTest("no sys.monitoring tool ID is available")

        def instruction(code, offset):
            nonlocal observed
            filename = code.co_filename.replace("\\", "/").rsplit("/", 1)[-1]
            if filename in allowed and code.co_code[offset] == dis.opmap["FOR_ITER"]:
                observed += 1

        def checkpoint(iteration, snapshot):
            if iteration > delay:
                evaluate_profile(root, worlds, snapshot, pot=1.0, chance_type=_Chance)
            return False

        allocated = False
        try:
            monitoring.use_tool_id(tool_id, "preflop-convergence-budget-test")
            allocated = True
            monitoring.register_callback(tool_id, monitoring.events.INSTRUCTION,
                                         instruction)
            monitoring.set_events(tool_id, monitoring.events.INSTRUCTION)
            train_delayed_public_cfrplus(
                root, worlds, infos, total, averaging_delay=delay,
                pot=1.0, chance_type=_Chance, checkpoint_interval=interval,
                checkpoint_callback=checkpoint,
            )
        finally:
            if allocated:
                try:
                    monitoring.set_events(tool_id, 0)
                    monitoring.register_callback(tool_id,
                                                 monitoring.events.INSTRUCTION, None)
                finally:
                    monitoring.free_tool_id(tool_id)
        self.assertGreater(observed, 0)
        self.assertGreaterEqual(budget["total_loop_entries_upper_bound"], observed)

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
