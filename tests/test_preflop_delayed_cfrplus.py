import dis
import sys
import unittest
import weakref
from unittest.mock import patch

from pokerlab import cfr_plus, public_cfr
from pokerlab.postflop_solver import _Chance
from pokerlab.preflop_solver import _Action
from pokerlab.preflop_vector_budget import estimate_vector_budget
from pokerlab.preflop_delayed_cfrplus import train_delayed_public_cfrplus
from pokerlab.river_tree import _Node, _Terminal, _terminal_value


def _weighted_game(*, shifted=False):
    def terminal(kind, contributions, winner=None):
        offset = 0.5 if shifted else 0.0
        return _Terminal(kind, tuple(value - offset for value in contributions), winner)

    branch_a = _Node(("a",), 1, (_Action("fold"), _Action("call")),
                     (terminal("fold", (0.5, 1.0), 0),
                      terminal("showdown", (1.0, 1.0))))
    branch_b = _Node(("b",), 1,
                     (_Action("fold"), _Action("call"), _Action("raise")),
                     (terminal("fold", (0.5, 1.0), 0),
                      terminal("showdown", (1.0, 1.0)),
                      terminal("showdown", (1.5, 1.5))))
    root = _Node((), 0, (_Action("fold"), _Action("continue")),
                 (terminal("fold", (0.5, 1.0), 1),
                  _Chance(("public",), {"a": branch_a, "b": branch_b})))
    worlds = ((0, 0, 0.6, 1, "a"), (0, 1, 0.4, -1, "b"),
              (1, 0, 0.3, -1, "a"), (1, 1, 0.7, 1, "b"))
    infos = {(0, 0, ()): 2, (0, 1, ()): 2,
             (1, 0, ("a",)): 2, (1, 1, ("a",)): 2,
             (1, 0, ("b",)): 3, (1, 1, ("b",)): 3}
    return root, worlds, infos


def _generic_cfrplus(root, worlds, infos, iterations, delay):
    def node_key(node, world):
        return node.player, world[node.player], node.history

    def chance_child(node, world):
        return node.branches[world[4]] if isinstance(node, _Chance) else None

    return cfr_plus.train(
        root, worlds, infos, iterations, "cfrplus",
        lambda terminal, world: _terminal_value(terminal, world[3], 0.0),
        node_key, chance_child, delay=delay,
    )


def _assert_rows_equal(test, expected, actual, tolerance=1e-12):
    test.assertEqual(set(expected), set(actual))
    for key in expected:
        test.assertEqual(len(expected[key]), len(actual[key]))
        for a, b in zip(expected[key], actual[key]):
            test.assertAlmostEqual(a, b, delta=tolerance)


class PreflopDelayedCFRPlusTests(unittest.TestCase):
    def test_delay_zero_matches_existing_vector_and_generic_paths(self):
        root, worlds, infos = _weighted_game(shifted=True)
        vector = public_cfr.train_public_batched(
            root, worlds, infos, 12, "cfrplus", pot=1.0, chance_type=_Chance,
        )
        local = train_delayed_public_cfrplus(
            root, worlds, infos, 12, averaging_delay=0, pot=1.0,
            chance_type=_Chance,
        )
        original_root, _, _ = _weighted_game()
        generic = _generic_cfrplus(original_root, worlds, infos, 12, 0)
        _assert_rows_equal(self, vector, local, 0.0)
        _assert_rows_equal(self, generic, local, 1e-12)

    def test_weighted_hidden_chance_matches_generic_for_positive_delays(self):
        for delay in (1, 4, 8):
            with self.subTest(delay=delay):
                root, worlds, infos = _weighted_game(shifted=True)
                local = train_delayed_public_cfrplus(
                    root, worlds, infos, 12, averaging_delay=delay,
                    pot=1.0, chance_type=_Chance,
                )
                original_root, _, _ = _weighted_game()
                generic = _generic_cfrplus(original_root, worlds, infos, 12, delay)
                _assert_rows_equal(self, generic, local, 2e-12)
                # Rows are keyed only by own private hand and revealed history.
                self.assertEqual(set(local), set(infos))
                self.assertTrue(all(len(key) == 3 for key in local))

    def test_hand_derived_delay_one_anchor(self):
        root = _Node((), 0, (_Action("win"), _Action("lose")),
                     (_Terminal("fold", (0, 0), 0),
                      _Terminal("fold", (0, 0), 1)))
        worlds, infos = ((0, 0, 1.0, 0),), {(0, 0, ()): 2}
        def controlled(delay):
            p0_sweeps = 0

            def deltas(_root, _edges, current_infos, _current, player,
                       _hands, _half_pot, _chance_type):
                nonlocal p0_sweeps
                if player != 0:
                    return {}
                p0_sweeps += 1
                return {key: ([1.0, 0.0] if p0_sweeps == 1 else [0.0, 2.0])
                        for key in current_infos}

            with patch.object(public_cfr, "_cfrplus_target_deltas", side_effect=deltas):
                return train_delayed_public_cfrplus(
                    root, worlds, infos, 2, averaging_delay=delay, pot=2.0,
                    chance_type=_Chance,
                )

        delayed = controlled(1)
        zero_delay = controlled(0)
        # Control only the regret helper to isolate averaging chronology:
        # post-sweep profiles are [1,0], then [1/3,2/3].
        # Delay 1 drops sweep 1 and weights sweep 2 by one.
        self.assertEqual(delayed[(0, 0, ())], [1.0 / 3.0, 2.0 / 3.0])
        # Delay 0 weights those profiles by 1 and 2 respectively.
        self.assertAlmostEqual(zero_delay[(0, 0, ())][0], 5.0 / 9.0, delta=1e-15)
        self.assertAlmostEqual(zero_delay[(0, 0, ())][1], 4.0 / 9.0, delta=1e-15)

    def test_invalid_delay_rejected_before_validation_or_aggregation(self):
        root, worlds, infos = _weighted_game()
        for bad in (True, -1, 1.5, "1", 12):
            with self.subTest(delay=bad):
                with patch.object(public_cfr, "_validate_inputs",
                                  side_effect=AssertionError("validation started")):
                    with patch.object(public_cfr, "_aggregate_prefixes",
                                      side_effect=AssertionError("aggregation started")):
                        with self.assertRaisesRegex(ValueError, "averaging delay"):
                            train_delayed_public_cfrplus(
                                root, worlds, infos, 12, averaging_delay=bad,
                                pot=1.0, chance_type=_Chance,
                            )
        with self.assertRaisesRegex(ValueError, "positive integer"):
            train_delayed_public_cfrplus(root, worlds, infos, True,
                                         averaging_delay=0, pot=1.0,
                                         chance_type=_Chance)

    def test_average_closure_released_when_traversal_raises(self):
        class Token:
            pass

        def run_failure():
            token = Token()
            token_ref = weakref.ref(token)
            history = (token,)
            root = _Node(history, 0, (_Action("only"),), (_Terminal("showdown", (1, 1)),))
            infos = {(0, 0, history): 1}

            def fake_delta(root, edges, infos, current, player, hand_counts,
                           half_pot, chance_type):
                return {key: [0.0] * count for key, count in infos.items()
                        if key[0] == player}

            # Plain replacements avoid MagicMock call-history cycles retaining
            # the root/infos independently of the trainer's closure lifetime.
            with patch.object(public_cfr, "_aggregate_prefixes", new=lambda *_: ({}, {})):
                with patch.object(public_cfr, "_cfrplus_target_deltas", new=fake_delta):
                    with self.assertRaises(KeyError) as caught:
                        train_delayed_public_cfrplus(
                            root, ((0, 0, 1.0, 0),), infos, 1,
                            averaging_delay=0, pot=1.0, chance_type=_Chance,
                        )
                    caught.exception.__traceback__ = None
            del caught, fake_delta, root, infos, history, token
            return token_ref

        token_ref = run_failure()
        self.assertIsNone(token_ref())

    def test_existing_cfrplus_budget_covers_delayed_adapter_loops(self):
        monitoring = getattr(sys, "monitoring", None)
        if monitoring is None:
            self.skipTest("sys.monitoring instruction events require Python 3.12+")
        root, worlds, infos = _weighted_game()
        budget = estimate_vector_budget(root, worlds, infos, 8, "cfrplus",
                                        chance_type=_Chance)
        observed = 0
        allowed = {"preflop_delayed_cfrplus.py", "public_cfr.py", "cfr.py"}
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
            monitoring.use_tool_id(tool_id, "delayed-cfrplus-budget-test")
            allocated = True
            monitoring.register_callback(tool_id, monitoring.events.INSTRUCTION, instruction)
            monitoring.set_events(tool_id, monitoring.events.INSTRUCTION)
            train_delayed_public_cfrplus(
                root, worlds, infos, 8, averaging_delay=3, pot=1.0,
                chance_type=_Chance,
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
        self.assertLessEqual(observed, budget["total_loop_entries_upper_bound"])


if __name__ == "__main__":
    unittest.main()
