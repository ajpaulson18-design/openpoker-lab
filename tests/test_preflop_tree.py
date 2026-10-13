import json
import gc
import math
import platform
import unittest
import weakref
from unittest.mock import patch

from pokerlab import cfr, planned_cfr
from pokerlab.preflop_tree import (
    PreflopConfig,
    PreflopContinuation,
    build_preflop_tree,
)
from pokerlab.river_tree import _Terminal, _terminal_value


class PreflopTreeTests(unittest.TestCase):
    def test_config_round_trips_and_rejects_invalid_values(self):
        config = PreflopConfig(starting_stack=(40, 30), raise_sizes=(0.5, 1, 2))
        encoded = json.dumps(config.to_dict(), sort_keys=True)
        restored = PreflopConfig.from_dict(json.loads(encoded))
        self.assertEqual(restored, config)
        self.assertEqual(restored.stacks, (40.0, 30.0))
        self.assertEqual(restored.pot, 0.0)
        for values in (
                {"small_blind": 1, "big_blind": 1},
                {"small_blind": 2, "big_blind": 1},
                {"small_blind": 1e-9, "big_blind": 2e-9},
                {"small_blind": .999999999, "big_blind": 1},
                {"starting_stack": 0},
                {"starting_stack": (10, float("inf"))},
                {"raise_sizes": (1,) * 9},
                {"raise_sizes": (0,)},
                {"max_raises": 9},
                {"max_raises": True},
                {"include_all_in": 1},
        ):
            with self.subTest(values=values), self.assertRaises((ValueError, TypeError)):
                PreflopConfig(**values)

    def test_blind_fold_payout_and_limp_keeps_big_blind_option(self):
        tree = build_preflop_tree(PreflopConfig(max_raises=1, include_all_in=False))
        root = tree.root
        self.assertEqual(root.player, 0)
        self.assertEqual([action.name for action in root.actions],
                         ["fold", "call", "raise"])
        self.assertEqual(_terminal_value(root.children[0], 1, 0), -0.5)
        self.assertEqual(root.children[0].contributions, (0.5, 1.0))

        bb_option = root.children[1]
        self.assertEqual((bb_option.player, bb_option.history), (1, ("call",)))
        self.assertEqual([action.name for action in bb_option.actions],
                         ["check", "raise"])
        self.assertNotIn("fold", [action.name for action in bb_option.actions])
        self.assertIsInstance(bb_option.children[0], PreflopContinuation)
        flop = bb_option.children[0]
        self.assertEqual(flop.matched_contributions, (1.0, 1.0))
        self.assertEqual(flop.pot, 2.0)
        self.assertEqual(flop.remaining_stacks, (99.0, 99.0))
        self.assertEqual((flop.street, flop.next_player), ("flop", 1))

    def test_minimum_raise_and_reraise_increments_follow_blind_and_last_full_raise(self):
        tree = build_preflop_tree(PreflopConfig(
            starting_stack=20, raise_sizes=(0.5, 1), max_raises=2,
            include_all_in=False,
        ))
        root = tree.root
        self.assertEqual([action.raise_to for action in root.actions[2:]], [2.0, 3.0])
        bb_after_raise_to_three = root.children[3]
        self.assertEqual(bb_after_raise_to_three.player, 1)
        self.assertEqual(bb_after_raise_to_three.history[-1], "raise@3")
        self.assertEqual([action.name for action in bb_after_raise_to_three.actions],
                         ["fold", "call", "raise", "raise"])
        self.assertEqual([action.raise_to for action in bb_after_raise_to_three.actions[2:]],
                         [6.0, 9.0])
        self.assertEqual(tree.nodes[(0, ("raise@3", "raise@6"))].player, 0)

    def test_capped_blinds_asymmetric_stacks_and_exact_refunds(self):
        blind_allin = build_preflop_tree(PreflopConfig(
            starting_stack=(0.25, 10),
        ))
        self.assertEqual(blind_allin.decision_node_count, 0)
        self.assertIsInstance(blind_allin.root, PreflopContinuation)
        self.assertEqual(blind_allin.root.matched_contributions, (0.25, 0.25))
        self.assertEqual(blind_allin.root.refunds, (0.0, 0.75))
        self.assertEqual(blind_allin.root.pot, 0.5)
        self.assertEqual(blind_allin.root.remaining_stacks, (0.0, 9.75))
        self.assertEqual((blind_allin.root.street, blind_allin.root.next_player),
                         ("showdown", None))

        short_bb = build_preflop_tree(PreflopConfig(starting_stack=(20, 0.25)))
        self.assertEqual(short_bb.decision_node_count, 0)
        self.assertIsInstance(short_bb.root, PreflopContinuation)
        self.assertEqual(short_bb.root.matched_contributions, (0.25, 0.25))
        self.assertEqual(short_bb.root.refunds, (0.25, 0.0))
        self.assertEqual(short_bb.root.street, "showdown")

        short_sb_call = build_preflop_tree(PreflopConfig(starting_stack=(0.75, 20)))
        self.assertEqual([action.name for action in short_sb_call.root.actions],
                         ["fold", "call"])
        called = short_sb_call.root.children[1]
        self.assertIsInstance(called, PreflopContinuation)
        self.assertEqual(called.matched_contributions, (0.75, 0.75))
        self.assertEqual(called.refunds, (0.0, 0.25))
        self.assertEqual(called.street, "showdown")

        all_in_sb_call = build_preflop_tree(PreflopConfig(starting_stack=(1, 20)))
        self.assertIsInstance(all_in_sb_call.root.children[1], PreflopContinuation)
        self.assertEqual(all_in_sb_call.root.children[1].matched_contributions,
                         (1.0, 1.0))
        self.assertEqual(all_in_sb_call.root.children[1].street, "showdown")

        short_call = build_preflop_tree(PreflopConfig(
            starting_stack=(20, 1.5), raise_sizes=(0.5,), max_raises=1,
            include_all_in=False,
        ))
        raised = short_call.root.children[2]
        self.assertEqual(raised.history, ("raise@2",))
        self.assertEqual([action.name for action in raised.actions], ["fold", "call"])
        settled = raised.children[1]
        self.assertEqual(settled.matched_contributions, (1.5, 1.5))
        self.assertEqual(settled.refunds, (0.5, 0.0))
        self.assertEqual(settled.pot, 3.0)
        self.assertEqual(settled.remaining_stacks, (18.5, 0.0))
        self.assertEqual(settled.street, "showdown")

    def test_no_raise_into_all_in_and_raise_cap_removes_free_fold(self):
        short_shove = build_preflop_tree(PreflopConfig(
            starting_stack=(1.5, 20), raise_sizes=(0.5,), max_raises=2,
        ))
        bb_response = short_shove.root.children[2]
        self.assertEqual(bb_response.history, ("all_in@1.5",))
        self.assertEqual([action.name for action in bb_response.actions], ["fold", "call"])

        capped = build_preflop_tree(PreflopConfig(
            raise_sizes=(0.5,), max_raises=1, include_all_in=False,
        ))
        bb_option = capped.root.children[1]
        self.assertEqual([action.name for action in bb_option.actions], ["check", "raise"])
        bb_reraise = bb_option.children[1]
        self.assertEqual([action.name for action in bb_reraise.actions], ["fold", "call"])

        no_raises = build_preflop_tree(PreflopConfig(max_raises=0))
        self.assertEqual([action.name for action in no_raises.root.actions], ["fold", "call"])
        self.assertEqual([action.name for action in no_raises.root.children[1].actions],
                         ["check"])

    def test_public_and_decision_budgets_fail_before_the_next_object_is_allocated(self):
        with patch("pokerlab.preflop_tree._Node") as make_node:
            with self.assertRaisesRegex(ValueError, "decision-node limit"):
                build_preflop_tree(max_decision_nodes=0)
            make_node.assert_not_called()

        with patch("pokerlab.preflop_tree._Terminal") as make_terminal:
            with self.assertRaisesRegex(ValueError, "public-state limit"):
                build_preflop_tree(max_public_states=1)
            make_terminal.assert_not_called()

    def test_callback_continuation_trains_with_shared_cfr_on_synthetic_utilities(self):
        def synthetic_factory(boundary):
            return _Terminal("showdown", boundary.matched_contributions)

        tree = build_preflop_tree(
            PreflopConfig(max_raises=0), continuation_factory=synthetic_factory,
        )
        self.assertEqual(tree.continuation_count, 1)
        infos = {key: len(node.actions) for key, node in tree.nodes.items()}
        world = (0, 0, 1.0, 1)
        # Explicit synthetic outcome: SB always wins a called hand for +1;
        # folding the posted small blind loses 0.5. This tests tree/CFR wiring,
        # not Hold'em equity or strategy quality.
        terminal_utility = lambda terminal, _world: (
            -0.5 if terminal.kind == "fold" and terminal.winner == 1 else 1.0
        )
        key = lambda node, _world: (node.player, node.history)
        direct_br0 = 1.0
        for trainer in (cfr.train, planned_cfr.train):
            for algorithm in ("vanilla", "dcfr"):
                with self.subTest(trainer=trainer.__module__, algorithm=algorithm):
                    profile = trainer(tree.root, [world], infos, 20, algorithm,
                                      terminal_utility, key)
                    value = cfr.evaluate(tree.root, [world], profile,
                                         terminal_utility, key)
                    direct = (-0.5 * profile[(0, ())][0] +
                              1.0 * profile[(0, ())][1])
                    br0 = cfr.best_response(0, tree.root, [world], profile,
                                             terminal_utility, key)
                    br1 = cfr.best_response(1, tree.root, [world], profile,
                                             terminal_utility, key)
                    self.assertAlmostEqual(value, direct)
                    self.assertAlmostEqual(br0, direct_br0)
                    self.assertAlmostEqual(br1, -value)

    @unittest.skipUnless(platform.python_implementation() == "CPython",
                         "Immediate release is specific to CPython.")
    def test_tree_and_callback_are_released_without_cyclic_collection(self):
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            def factory(boundary):
                return _Terminal("showdown", boundary.matched_contributions)
            callback_ref = weakref.ref(factory)
            tree = build_preflop_tree(PreflopConfig(max_raises=0),
                                     continuation_factory=factory)
            root_ref = weakref.ref(tree.root)
            del tree, factory
            self.assertIsNone(root_ref())
            self.assertIsNone(callback_ref())

            captured = []
            def fail(boundary):
                captured.append(weakref.ref(boundary))
                raise RuntimeError("synthetic continuation failure")
            callback_ref = weakref.ref(fail)
            with self.assertRaisesRegex(RuntimeError, "synthetic continuation failure"):
                build_preflop_tree(PreflopConfig(max_raises=0),
                                   continuation_factory=fail)
            del fail
            self.assertIsNone(callback_ref())
            self.assertTrue(captured)
            self.assertTrue(all(reference() is None for reference in captured))
        finally:
            if was_enabled:
                gc.enable()

    def test_default_unsolved_boundary_cannot_be_used_as_a_showdown_payoff(self):
        tree = build_preflop_tree(PreflopConfig(max_raises=0))
        boundary = tree.root.children[1].children[0]
        self.assertIsInstance(boundary, PreflopContinuation)
        with self.assertRaises(AttributeError):
            _terminal_value(boundary, 1, 0)


if __name__ == "__main__":
    unittest.main()
