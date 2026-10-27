"""Structural contract tests for the history-free shared public-topology DAG."""

import json
import math
from pathlib import Path
import struct
import unittest
from unittest import mock

from pokerlab import preflop_solver
from pokerlab.cards import DECK, expand_range
from pokerlab.preflop_tree import PreflopConfig, build_preflop_tree
from pokerlab.river_tree import _Action, _Node, _Terminal
from pokerlab.shared_public_topology import (
    ChanceVertex,
    DecisionVertex,
    TerminalVertex,
    TopologyLimits,
    compile_shared_public_topology,
)
from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions


REPO = Path(__file__).resolve().parents[1]


def _float_bits(value):
    return struct.pack("!d", float(value))


def _node_events(root):
    """Independent literal traversal with a mutable history path buffer."""
    result = []
    history = list(root.history)
    stack = [[root, 0, len(history)]]
    while stack:
        node, index, restore = stack[-1]
        if isinstance(node, _Node):
            if index == 0:
                if tuple(history) != node.history:
                    raise AssertionError("fixture source history is inconsistent")
                result.append(("decision", tuple(history), node.player,
                               tuple((a.name, _float_bits(a.amount),
                                      _float_bits(a.raise_to), a.full_raise, a.token)
                                     for a in node.actions)))
            if index < len(node.children):
                stack[-1][1] += 1
                history.append(node.actions[index].token)
                stack.append([node.children[index], 0, len(history) - 1])
                continue
        elif isinstance(node, preflop_solver._Chance):
            if index == 0:
                if tuple(history) != node.history:
                    raise AssertionError("fixture chance history is inconsistent")
                result.append(("chance", tuple(history), node.street,
                               node.card_index, tuple(node.branches.keys())))
            branches = tuple(node.branches.items())
            if index < len(branches):
                stack[-1][1] += 1
                token, child = branches[index]
                history.append(f"{node.street}@{token}")
                stack.append([child, 0, len(history) - 1])
                continue
        elif isinstance(node, _Terminal):
            if index == 0:
                result.append(("terminal", tuple(history), node.kind,
                               tuple(_float_bits(v) for v in node.contributions),
                               node.winner))
        else:
            raise AssertionError(f"unexpected fixture node {type(node)!r}")
        stack.pop()
        del history[restore:]
    return result


def _dag_events(topology):
    events = []
    for occurrence in topology.iter_occurrences():
        vertex = topology.vertices[occurrence.vertex_id]
        if isinstance(vertex, DecisionVertex):
            body = (vertex.player, tuple(
                (a.name, _float_bits(a.amount), _float_bits(a.raise_to),
                 a.full_raise, a.token) for a in vertex.actions))
        elif isinstance(vertex, ChanceVertex):
            body = (vertex.street, vertex.card_index,
                    tuple(token for token, _ in vertex.branches))
        else:
            body = (vertex.kind,
                    tuple(_float_bits(v) for v in vertex.contributions),
                    vertex.winner)
        events.append((occurrence.kind, occurrence.history, *body))
    return events


def _fixture_case():
    return json.loads((REPO / "benchmarks/four-street-integration-v1.json").read_text(
        encoding="utf-8"))["case"]


def _heldout_96_case():
    return {
        "sb_range": "2c2d,2c2h,2c2s,2c3c",
        "bb_range": "5c5d,5c5h,5c5s,5c6c",
        "runouts": ("8c8d8h9h9s", "8c8d8h9hTc", "8c8d8h9hTd",
                    "8s9c9d9h9s", "8s9c9d9hTc", "8s9c9d9hTd"),
        "config": {"small_blind": 0.5, "big_blind": 1,
                   "starting_stack": [8, 8], "raise_sizes": [0.5],
                   "max_raises": 1, "include_all_in": False},
        "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                         "max_raises": 0, "include_all_in": False},
        "turn_config": {"bet_sizes": [0.5], "raise_sizes": [],
                         "max_raises": 0, "include_all_in": False},
        "river_config": {"bet_sizes": [0.5], "raise_sizes": [],
                          "max_raises": 0, "include_all_in": False},
    }


def _build_literal_tree(case):
    request = FourStreetSolveRequest(
        case["sb_range"], case["bb_range"], tuple(case["runouts"]),
        preflop_config=PreflopConfig.from_dict(case["config"]),
        flop_actions=PostflopActions(**case["flop_config"]),
        turn_actions=PostflopActions(**case["turn_config"]),
        river_actions=PostflopActions(**case["river_config"]),
        iterations=10, algorithm="cfrplus", traversal="public-batched",
        diagnostics="public-batched", resource_model="public-vector")
    ranges = (expand_range(request.sb_range), expand_range(request.bb_range))
    hands = (list(ranges[0]), list(ranges[1]))
    selected = preflop_solver._requested_runouts(request.runouts)
    worlds = []
    for sb_index, sb_hand in enumerate(hands[0]):
        for bb_index, bb_hand in enumerate(hands[1]):
            if not set(sb_hand).isdisjoint(bb_hand):
                continue
            for flop, turn, river in selected:
                if set(sb_hand + bb_hand).isdisjoint(flop + (turn, river)):
                    worlds.append((sb_index, bb_index, 1.0, 0,
                                   "".join(flop), turn, river))
    specs = preflop_solver._stage_configs(
        request.flop_actions.to_dict(), request.turn_actions.to_dict(),
        request.river_actions.to_dict())
    preflop = build_preflop_tree(request.preflop_config)
    root, state_count, decisions, *_ = preflop_solver._merge_preflop_tree(
        preflop, worlds, specs, "public-batched", request.iterations,
        enforce_world_work=False)
    legal = preflop_solver._legal_private_hands(worlds)
    support = {}
    for (player, prefix), values in legal.items():
        counts = list(support.get(prefix, (0, 0)))
        counts[player] = len(values)
        support[prefix] = tuple(counts)
    return root, worlds, support, (len(worlds), state_count, decisions)


def _literal_subtrees_share(root):
    """Ensure the fixture has structurally equal source nodes to intern."""
    seen = {}
    shared = False
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, _Node):
            signature = ("decision", node.player,
                         tuple((a.name, _float_bits(a.amount), _float_bits(a.raise_to),
                                a.full_raise, a.token) for a in node.actions),
                         tuple(id(child) for child in node.children))
            stack.extend(node.children)
        elif isinstance(node, preflop_solver._Chance):
            signature = ("chance", node.street, node.card_index,
                         tuple((k, id(v)) for k, v in node.branches.items()))
            stack.extend(node.branches.values())
        else:
            signature = ("terminal", node.kind,
                         tuple(_float_bits(v) for v in node.contributions), node.winner)
        if signature in seen:
            shared = True
        else:
            seen[signature] = id(node)
    return shared


class SharedPublicTopologyTests(unittest.TestCase):
    def test_22_world_tree_occurrences_and_support_census_match_literal_tree(self):
        root, worlds, support, counts = _build_literal_tree(_fixture_case())
        self.assertEqual(counts[0], 22)
        self.assertTrue(_literal_subtrees_share(root))
        expected = _node_events(root)
        topology = compile_shared_public_topology(
            root, hand_support_counts_by_prefix=support)
        self.assertEqual(_dag_events(topology), expected)
        self.assertEqual(topology.census.expanded_logical_visits, len(expected))
        self.assertEqual(topology.census.unique_vertices, len(topology.vertices))
        self.assertLess(topology.census.unique_vertices,
                        topology.census.expanded_logical_visits)
        self.assertEqual(topology.census.information_rows,
                         sum(_expected_support_rows(root, support)))
        self.assertEqual(topology.census.action_slots,
                         sum(_expected_action_slots(root, support)))
        self.assertEqual(topology.census.terminal_occurrences,
                         sum(event[0] == "terminal" for event in expected))

    def test_96_world_two_flop_heldout_structure_is_a_supported_input_not_quality(self):
        root, worlds, support, counts = _build_literal_tree(_heldout_96_case())
        self.assertEqual(counts[0], 96)
        topology = compile_shared_public_topology(
            root, hand_support_counts_by_prefix=support)
        self.assertEqual(_dag_events(topology), _node_events(root))
        self.assertEqual(topology.census.information_rows,
                         sum(_expected_support_rows(root, support)))
        self.assertEqual(topology.census.unique_source_edges,
                         sum(_source_degree(node) for node in _unique_source_nodes(root)))
        board_rows = [row for row in topology.census.prefix_storage
                      if len(row.board_prefix) == 3 and row.information_rows]
        self.assertEqual(len(board_rows), 2)
        occurrences = [item for item in topology.iter_occurrences()
                       if item.kind == "decision" and len(_board_prefix_for_test(item.history)) == 3]
        by_flop = {}
        for occurrence in occurrences:
            by_flop.setdefault(_board_prefix_for_test(occurrence.history), set()).add(
                occurrence.history)
        self.assertEqual(len(by_flop), 2)
        self.assertTrue(all(histories for histories in by_flop.values()))

    def test_fractional_blinds_short_allins_and_refunds_preserve_literal_terminals(self):
        config = PreflopConfig(
            small_blind=0.3, big_blind=0.8, starting_stack=(1.25, 0.9),
            raise_sizes=(0.5, 1.0), max_raises=2, include_all_in=True)
        actions = {"bet_sizes": [0.5], "raise_sizes": [0.5],
                   "max_raises": 1, "include_all_in": True}
        specs = preflop_solver._stage_configs(actions, actions, actions)
        preflop = build_preflop_tree(config)
        worlds = [(0, 0, 1.0, 0, "2c3d4h", "5s", "6s")]
        root, _, _, *_ = preflop_solver._merge_preflop_tree(
            preflop, worlds, specs, "public-batched", 10,
            enforce_world_work=False)
        expected = _node_events(root)
        topology = compile_shared_public_topology(root)
        self.assertEqual(_dag_events(topology), expected)
        all_action_names = {action.name for vertex in topology.vertices
                            if isinstance(vertex, DecisionVertex)
                            for action in vertex.actions}
        self.assertIn("all_in", all_action_names)
        terminals = [vertex for vertex in topology.vertices
                     if isinstance(vertex, TerminalVertex)]
        self.assertTrue(any(item.contributions[0] != item.contributions[1]
                            for item in terminals))
        self.assertTrue(any(value != round(value) for item in terminals
                            for value in item.contributions))

    def test_history_free_interning_keeps_distinct_histories_as_occurrences(self):
        terminal = _Terminal("fold", (2.0, 2.0), 0)
        left = _Node(("check",), 0, (_Action("fold"),), (terminal,))
        right = _Node(("call",), 0, (_Action("fold"),), (terminal,))
        root = _Node((), 0, (_Action("check"), _Action("call")), (left, right))
        topology = compile_shared_public_topology(root)
        decisions = [item for item in topology.iter_occurrences()
                     if item.kind == "decision"]
        self.assertEqual([item.history for item in decisions],
                         [(), ("check",), ("call",)])
        self.assertEqual(decisions[1].vertex_id, decisions[2].vertex_id)
        self.assertEqual(topology.census.decision_occurrences, 3)
        self.assertEqual(topology.census.information_rows, None)
        self.assertEqual(topology.census.action_slots, None)
        self.assertEqual(topology.census.terminal_occurrences, 2)

    def test_shared_terminal_source_is_allowed_but_shared_stale_decision_is_rejected(self):
        terminal = _Terminal("fold", (1.0, 1.0), 0)
        root = _Node((), 0, (_Action("fold"), _Action("call")),
                     (terminal, terminal))
        topology = compile_shared_public_topology(root)
        self.assertEqual(topology.census.terminal_occurrences, 2)
        self.assertEqual(topology.census.unique_source_nodes, 2)
        self.assertEqual(topology.census.unique_vertices, 2)

        shared = _Node(("check",), 0, (_Action("fold"),), (terminal,))
        bad = _Node((), 0, (_Action("check"), _Action("call")), (shared, shared))
        with self.assertRaisesRegex(ValueError, "history differs"):
            compile_shared_public_topology(bad)

    def test_chance_insertion_order_and_raw_reveal_tokens_are_preserved(self):
        first = _Terminal("showdown", (3.0, 3.0))
        second = _Terminal("showdown", (4.0, 4.0))
        chance = preflop_solver._Chance(
            ("check",), {"2c3d4h": first, "5c6d7s": second}, 4, "flop")
        root = _Node((), 0, (_Action("check"),), (chance,))
        topology = compile_shared_public_topology(root)
        chance_row = next(v for v in topology.vertices if isinstance(v, ChanceVertex))
        self.assertEqual(tuple(token for token, _ in chance_row.branches),
                         ("2c3d4h", "5c6d7s"))
        occurrences = list(topology.iter_occurrences())
        self.assertEqual([o.history for o in occurrences if o.kind == "terminal"],
                         [("check", "flop@2c3d4h"),
                          ("check", "flop@5c6d7s")])

    def test_float_bitpatterns_are_part_of_interning_keys(self):
        terminal = _Terminal("showdown", (0.0, -0.0))
        left = _Node(("check",), 0, (_Action("check", amount=0.0),), (terminal,))
        right = _Node(("call",), 0, (_Action("check", amount=-0.0),), (terminal,))
        root = _Node((), 0, (_Action("check"), _Action("call")), (left, right))
        topology = compile_shared_public_topology(root)
        decision_ids = [o.vertex_id for o in topology.iter_occurrences()
                        if o.kind == "decision"]
        self.assertNotEqual(decision_ids[1], decision_ids[2])
        self.assertEqual(_float_bits(topology.vertices[0].contributions[1]),
                         _float_bits(-0.0))

    def test_cycle_malformed_numeric_and_invalid_winner_reject(self):
        cyclic = _Node((), 0, (_Action("check"),), ())
        cyclic.children = (cyclic,)
        with self.assertRaisesRegex(ValueError, "cycle"):
            compile_shared_public_topology(cyclic)

        nan_action = _Action("check", amount=math.nan)
        with self.assertRaisesRegex(ValueError, "finite real"):
            compile_shared_public_topology(
                _Node((), 0, (nan_action,), (_Terminal("showdown", (1.0, 1.0)),)))
        with self.assertRaisesRegex(ValueError, "winner"):
            compile_shared_public_topology(
                _Terminal("fold", (1.0, 1.0), 2))

    def test_support_census_uses_explicit_counts_and_requires_prefix_coverage(self):
        terminal = _Terminal("fold", (1.0, 1.0), 1)
        root = _Node((), 0, (_Action("fold"),), (terminal,))
        topology = compile_shared_public_topology(
            root, hand_support_counts_by_prefix={(): (3, 7)})
        row, = topology.census.prefix_storage
        self.assertEqual((row.board_prefix, row.decision_occurrences,
                          row.information_rows, row.action_slots),
                         ((), 1, 3, 3))
        self.assertEqual((topology.census.information_rows,
                          topology.census.action_slots), (3, 3))
        with self.assertRaisesRegex(ValueError, "support census"):
            compile_shared_public_topology(
                root, hand_support_counts_by_prefix={("2c",): (1, 1)})

    def test_all_resource_dimensions_reject_at_the_declared_boundary(self):
        root = _Node((), 0, (_Action("fold"),),
                     (_Terminal("fold", (1.0, 1.0), 1),))
        for limits in (
                TopologyLimits(max_source_nodes=1),
                TopologyLimits(max_source_edges=0),
                TopologyLimits(max_vertices=1),
                TopologyLimits(max_edges=0),
                TopologyLimits(max_logical_visits=1),
                TopologyLimits(max_depth=0),
                TopologyLimits(max_history_token_work=1),
                TopologyLimits(max_history_token_bytes=1),
                TopologyLimits(max_build_scratch_entries=1)):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                compile_shared_public_topology(root, limits=limits)

    def test_source_mutation_during_compile_is_rejected(self):
        root = _Node((), 0, (_Action("fold"),),
                     (_Terminal("fold", (1.0, 1.0), 1),))
        from pokerlab import shared_public_topology as module
        original = module._revalidate_sources

        def mutate_then_validate(snapshots):
            root.children = (_Terminal("fold", (2.0, 2.0), 1),)
            return original(snapshots)

        with mock.patch.object(module, "_revalidate_sources", mutate_then_validate):
            with self.assertRaisesRegex(ValueError, "mutated during"):
                compile_shared_public_topology(root)

    def test_dag_retains_no_source_tree_or_occurrence_history_table(self):
        root, _, _, _ = _build_literal_tree(_fixture_case())
        topology = compile_shared_public_topology(root)
        self.assertEqual(set(topology.__dataclass_fields__), {
            "vertices", "root_id", "initial_history", "census", "limits"})
        self.assertFalse(any(isinstance(value, (_Node, _Terminal,
                                                preflop_solver._Chance))
                             for value in topology.vertices))
        first = list(topology.iter_occurrences())
        second = list(topology.iter_occurrences())
        self.assertEqual(first, second)


def _source_degree(node):
    if isinstance(node, _Node):
        return len(node.children)
    if isinstance(node, preflop_solver._Chance):
        return len(node.branches)
    return 0


def _unique_source_nodes(root):
    seen = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, _Node):
            stack.extend(node.children)
        elif isinstance(node, preflop_solver._Chance):
            stack.extend(node.branches.values())
        yield node


def _expected_support_rows(root, support):
    for event in _node_events(root):
        if event[0] == "decision":
            prefix = _board_prefix_for_test(event[1])
            yield support[prefix][event[2]]


def _expected_action_slots(root, support):
    for event in _node_events(root):
        if event[0] == "decision":
            prefix = _board_prefix_for_test(event[1])
            counts = support[prefix]
            yield counts[event[2]] * len(event[3])


def _board_prefix_for_test(history):
    board = []
    for token in history:
        if token.startswith("flop@"):
            board.extend(token[5 + offset:7 + offset] for offset in (0, 2, 4))
        elif token.startswith("turn@"):
            board.append(token[5:])
        elif token.startswith("river@"):
            board.append(token[6:])
    return tuple(board)


if __name__ == "__main__":
    unittest.main()
