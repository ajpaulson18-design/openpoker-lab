"""Adversarial checks for bounded public-state allocation in postflop trees."""
import gc
import platform
import unittest
import weakref
from unittest.mock import patch

from pokerlab import postflop_solver, river_tree
from pokerlab.river_config import RiverConfig
from pokerlab.cards import cards
from pokerlab.postflop_solver import (
    _build_postflop_tree, _enumerate_worlds, solve_postflop,
)
from pokerlab.postflop_solver import _Chance
from pokerlab.river_tree import _Node, _Terminal


class PostflopPublicStateBudgetTests(unittest.TestCase):
    def test_reported_public_state_counts_match_a_walked_small_tree(self):
        board = "2c3c4d"
        runouts = (("5h", "6h"),)
        config = RiverConfig(pot=10, effective_stack=20, bet_sizes=(0.5,),
                             include_all_in=False)
        _, worlds, _, _ = _enumerate_worlds(
            board, "AsKd", "JsJd", runouts, iterations=10,
        )
        root, _, _, _, _ = _build_postflop_tree(
            cards(board), config, worlds=worlds,
        )
        walked = {"decision": 0, "chance": 0, "terminal": 0}

        def walk(node):
            if isinstance(node, _Chance):
                walked["chance"] += 1
                for child in node.branches.values():
                    walk(child)
            elif isinstance(node, _Node):
                walked["decision"] += 1
                for child in node.children:
                    walk(child)
            else:
                self.assertIsInstance(node, _Terminal)
                walked["terminal"] += 1

        walk(root)
        result = solve_postflop(
            board, "AsKd", "JsJd", config, runouts=runouts, iterations=10,
        )
        self.assertEqual(result["public_nodes"], walked["decision"])
        self.assertEqual(result["chance_nodes"], walked["chance"])
        self.assertEqual(result["terminal_nodes"], walked["terminal"])
        self.assertEqual(result["public_states"], sum(walked.values()))
        self.assertEqual(result["public_state_limit"],
                         postflop_solver._MAX_PUBLIC_STATES)

    def test_many_allin_reveal_leaves_hit_total_state_cap_before_allocation(self):
        # Six ordered worlds share only three turn and three river cards. The
        # short stack makes branches settle all-in, so terminal/reveal states
        # grow quickly while betting decision depth stays small.
        runouts = (("5h", "6h"), ("5h", "7h"),
                   ("6h", "5h"), ("6h", "7h"),
                   ("7h", "5h"), ("7h", "6h"))
        config = RiverConfig(pot=10, effective_stack=5, bet_sizes=(0.5,),
                             include_all_in=True)
        allocation_counts = {"decision": 0, "chance": 0, "terminal": 0}
        reserved_counts = {}
        reservation_attempts = []

        original_builder = postflop_solver._build_postflop_tree
        original_street_builder = postflop_solver._build_tree

        def capture_reservations(*args, **kwargs):
            kwargs["allocation_counts"] = reserved_counts
            return original_builder(*args, **kwargs)

        def capture_hook(config, **kwargs):
            original_hook = kwargs["allocation_hook"]

            def record(kind):
                reservation_attempts.append(kind)
                original_hook(kind)

            kwargs["allocation_hook"] = record
            return original_street_builder(config, **kwargs)

        def track_init(kind, original):
            def tracked(self, *args, **kwargs):
                allocation_counts[kind] += 1
                original(self, *args, **kwargs)
            return tracked

        cap = 33
        with patch.object(postflop_solver, "_MAX_PUBLIC_STATES", cap), \
             patch.object(postflop_solver, "_build_postflop_tree", capture_reservations), \
             patch.object(postflop_solver, "_build_tree", capture_hook):
            with patch.object(river_tree._Node, "__init__",
                              track_init("decision", river_tree._Node.__init__)), \
                 patch.object(river_tree._Terminal, "__init__",
                              track_init("terminal", river_tree._Terminal.__init__)), \
                 patch.object(postflop_solver._Chance, "__init__",
                              track_init("chance", postflop_solver._Chance.__init__)):
                with self.assertRaisesRegex(ValueError, "public state"):
                    solve_postflop(
                        "2c3c4d", "AsKd", "JsJd", config, runouts=runouts,
                        iterations=10, algorithm="vanilla", traversal="recursive",
                    )

        self.assertEqual(reserved_counts["total"], cap)
        self.assertEqual(sum(reserved_counts[kind]
                             for kind in ("decision", "chance", "terminal")), cap)
        self.assertIn("decision", reservation_attempts)
        self.assertIn("terminal", reservation_attempts)
        self.assertLess(reserved_counts["decision"], cap)
        self.assertGreater(reserved_counts["terminal"] + reserved_counts["chance"],
                           reserved_counts["decision"])
        # Reservations include in-progress chance parents; those objects are
        # constructed only after all their branches have been created.
        self.assertLessEqual(sum(allocation_counts.values()), cap)
        self.assertLess(allocation_counts["chance"], reserved_counts["chance"])
        self.assertLessEqual(allocation_counts["terminal"], reserved_counts["terminal"])

    @unittest.skipUnless(platform.python_implementation() == "CPython",
                         "Immediate weakref release is CPython-specific.")
    def test_tree_builder_releases_recursive_closures_without_cyclic_gc(self):
        board = "2c3c4d"
        config = RiverConfig(pot=10, effective_stack=20, bet_sizes=(0.5,),
                             include_all_in=False)
        _, worlds, _, _ = _enumerate_worlds(
            board, "AsKd", "JsJd", (("5h", "6h"),), iterations=10,
        )
        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            root, nodes, _, _, _ = _build_postflop_tree(
                cards(board), config, worlds=worlds,
            )
            reference = weakref.ref(root)
            self.assertIs(reference(), root)
            del root, nodes
            self.assertIsNone(reference())
        finally:
            if gc_was_enabled:
                gc.enable()
            gc.collect()


if __name__ == "__main__":
    unittest.main()
