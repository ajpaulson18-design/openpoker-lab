"""Preflop-local prototype for reusable public CFR+ target-delta plans.

This module is an experiment, not a production trainer. It compiles ordered
node metadata and terminal edge references, then preserves the shared
``public_cfr._cfrplus_target_deltas`` recursive arithmetic while avoiding
repeated node classification and prefix/key construction. It deliberately
does not claim to remove recursive calls.
"""

from collections.abc import Mapping
import math

from pokerlab.river_tree import _Node, _Terminal


MAX_PLAN_RECORDS = 250_000
MAX_PLAN_INFO_REFERENCES = 500_000
MAX_PLAN_KEY_REFERENCES = 1_000_000
MAX_PLAN_CHILD_REFERENCES = 1_000_000
MAX_PLAN_TERMINAL_EDGE_REFERENCES = 250_000

_CHANCE = 0
_TERMINAL_FOLD = 1
_TERMINAL_SHOWDOWN = 2
_DECISION = 3
_MAX_HANDS = 1326


class _PlanRecord:
    __slots__ = ("kind", "children", "edges", "payoff", "player",
                 "action_count", "keys", "history")

    def __init__(self, kind, *, children=(), edges=(), payoff=0.0,
                 player=None, action_count=0, keys=(), history=()):
        self.kind = kind
        self.children = children
        self.edges = edges
        self.payoff = payoff
        self.player = player
        self.action_count = action_count
        self.keys = keys
        self.history = history


class TargetDeltaPlan:
    """Compiled tree metadata reusable across target-player delta passes."""

    __slots__ = ("_root", "_infos_by_player", "hand_counts", "metadata")

    def __init__(self, root, infos_by_player, hand_counts, metadata):
        self._root = root
        self._infos_by_player = infos_by_player
        self.hand_counts = hand_counts
        self.metadata = metadata

    def target_deltas(self, current, target_player):
        if type(target_player) is not int or target_player not in (0, 1):
            raise ValueError("target_player must be 0 or 1")
        if not isinstance(current, Mapping):
            raise TypeError("current must map information-set keys to strategies")

        deltas = {key: [0.0] * action_count
                  for key, action_count in self._infos_by_player[target_player]}
        target_count = self.hand_counts[target_player]
        opponent = 1 - target_player

        def visit(record, opponent_reach):
            if record.kind == _CHANCE:
                value = [0.0] * target_count
                for child in record.children:
                    child_value = visit(child, opponent_reach)
                    for index, result in enumerate(child_value):
                        value[index] += result
                return value

            if record.kind in (_TERMINAL_FOLD, _TERMINAL_SHOWDOWN):
                value = [0.0] * target_count
                if record.kind == _TERMINAL_FOLD:
                    if target_player == 0:
                        for oop_index, ip_index, mass, _signed_mass in record.edges:
                            value[oop_index] += mass * opponent_reach[ip_index] * record.payoff
                    else:
                        for oop_index, ip_index, mass, _signed_mass in record.edges:
                            value[ip_index] -= mass * opponent_reach[oop_index] * record.payoff
                else:
                    if target_player == 0:
                        for oop_index, ip_index, _mass, signed_mass in record.edges:
                            value[oop_index] += signed_mass * opponent_reach[ip_index] * record.payoff
                    else:
                        for oop_index, ip_index, _mass, signed_mass in record.edges:
                            value[ip_index] -= signed_mass * opponent_reach[oop_index] * record.payoff
                return value

            action_count = record.action_count
            uniform = [1.0 / action_count] * action_count
            probabilities = [current.get(key, uniform) for key in record.keys]

            if record.player == target_player:
                action_values = [visit(child, opponent_reach)
                                 for child in record.children]
                value = [0.0] * target_count
                for hand_index in range(target_count):
                    sigma = probabilities[hand_index]
                    expected = sum(sigma[action] * action_values[action][hand_index]
                                   for action in range(action_count))
                    value[hand_index] = expected
                    row = deltas.get(record.keys[hand_index])
                    if row is not None:
                        for action in range(action_count):
                            row[action] += action_values[action][hand_index] - expected
                return value

            value = [0.0] * target_count
            for action_index, child in enumerate(record.children):
                child_reach = [opponent_reach[hand_index] *
                               probabilities[hand_index][action_index]
                               for hand_index in range(self.hand_counts[opponent])]
                child_value = visit(child, child_reach)
                for hand_index, result in enumerate(child_value):
                    value[hand_index] += result
            return value

        try:
            visit(self._root, [1.0] * self.hand_counts[opponent])
        finally:
            # Release recursive local references promptly, also on exceptions.
            visit = None
        return deltas


def _check_limit(name, value):
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def compile_target_plan(root, edges, infos, hand_counts, half_pot, chance_type, *,
                        max_records=MAX_PLAN_RECORDS,
                        max_info_references=MAX_PLAN_INFO_REFERENCES,
                        max_key_references=MAX_PLAN_KEY_REFERENCES,
                        max_child_references=MAX_PLAN_CHILD_REFERENCES,
                        max_terminal_edge_references=MAX_PLAN_TERMINAL_EDGE_REFERENCES):
    """Census then compile a bounded tree description for repeated CFR+ passes.

    The first walk validates and counts every occurrence before any compiled
    record/key/child tuple is allocated. The supplied ``edges`` and ``infos``
    are only read. Child and terminal-edge iteration order is preserved.
    """
    for name, value in (("max_records", max_records),
                        ("max_info_references", max_info_references),
                        ("max_key_references", max_key_references),
                        ("max_child_references", max_child_references),
                        ("max_terminal_edge_references", max_terminal_edge_references)):
        _check_limit(name, value)
    if not isinstance(edges, Mapping) or not isinstance(infos, Mapping):
        raise TypeError("edges and infos must be mappings")
    if not isinstance(chance_type, type):
        raise TypeError("chance_type must be a node class")
    if (not isinstance(hand_counts, (tuple, list)) or len(hand_counts) != 2 or
            any(type(count) is not int or not 1 <= count <= _MAX_HANDS
                for count in hand_counts)):
        raise ValueError("hand_counts must contain two valid dense hand dimensions")
    if isinstance(half_pot, bool) or not isinstance(half_pot, (int, float)):
        raise ValueError("half_pot must be a finite number")
    try:
        half_pot = float(half_pot)
    except (OverflowError, ValueError):
        raise ValueError("half_pot must be a finite number") from None
    if not math.isfinite(half_pot):
        raise ValueError("half_pot must be a finite number")

    info_reference_count = len(infos)
    if info_reference_count > max_info_references:
        raise ValueError("target plan information-row reference cap exceeded")
    for key, action_count in infos.items():
        if (not isinstance(key, tuple) or len(key) != 3 or
                type(key[0]) is not int or key[0] not in (0, 1) or
                type(key[1]) is not int or not 0 <= key[1] < hand_counts[key[0]] or
                not isinstance(key[2], tuple) or type(action_count) is not int or
                action_count < 1):
            raise ValueError("infos must map valid (player, hand, history) keys to action counts")

    counts = {"records": 0, "decision_records": 0, "chance_records": 0,
              "terminal_records": 0, "key_references": 0,
              "child_references": 0, "terminal_edge_references": 0}
    active = set()

    def census(node, prefix):
        ident = id(node)
        if ident in active:
            raise ValueError("public tree contains a cycle")
        active.add(ident)
        try:
            counts["records"] += 1
            if counts["records"] > max_records:
                raise ValueError("target plan record cap exceeded")
            if isinstance(node, chance_type):
                branches = getattr(node, "branches", None)
                if not isinstance(branches, Mapping):
                    raise ValueError("chance nodes need an ordered branch mapping")
                counts["chance_records"] += 1
                counts["child_references"] += len(branches)
                if counts["child_references"] > max_child_references:
                    raise ValueError("target plan child-reference cap exceeded")
                for card, child in branches.items():
                    try:
                        hash(card)
                    except TypeError as exc:
                        raise ValueError("chance branch labels must be hashable") from exc
                    census(child, prefix + (card,))
            elif isinstance(node, _Terminal):
                counts["terminal_records"] += 1
                try:
                    row = edges[prefix]
                except (KeyError, TypeError) as exc:
                    raise ValueError("terminal public prefix has no aggregated edge row") from exc
                try:
                    edge_count = len(row)
                except TypeError as exc:
                    raise ValueError("terminal edge rows must be sized sequences") from exc
                counts["terminal_edge_references"] += edge_count
                if counts["terminal_edge_references"] > max_terminal_edge_references:
                    raise ValueError("target plan terminal-edge reference cap exceeded")
            elif isinstance(node, _Node):
                if (type(node.player) is not int or node.player not in (0, 1) or
                        len(node.actions) != len(node.children) or not node.children):
                    raise ValueError("decision action and child counts must match")
                counts["decision_records"] += 1
                counts["child_references"] += len(node.children)
                if counts["child_references"] > max_child_references:
                    raise ValueError("target plan child-reference cap exceeded")
                key_count = hand_counts[node.player]
                counts["key_references"] += key_count
                if counts["key_references"] > max_key_references:
                    raise ValueError("target plan key-reference cap exceeded")
                for child in node.children:
                    census(child, prefix)
            else:
                raise TypeError("tree contains an unsupported public node")
        finally:
            active.remove(ident)

    try:
        census(root, ())
    finally:
        census = None

    # Partition rows only after the full structural census and every cap have
    # passed, so rejected trees do not first duplicate the caller's infos map.
    infos_by_player = ([], [])
    for key, action_count in infos.items():
        infos_by_player[key[0]].append((key, action_count))

    compile_counts = {"records": 0, "key_references": 0, "child_references": 0,
                      "terminal_edge_references": 0}

    def compile_node(node, prefix):
        compile_counts["records"] += 1
        if compile_counts["records"] > max_records:
            raise ValueError("target plan record cap exceeded during compile")
        if isinstance(node, chance_type):
            children = []
            for card, child in node.branches.items():
                compile_counts["child_references"] += 1
                if compile_counts["child_references"] > max_child_references:
                    raise ValueError("target plan child-reference cap exceeded during compile")
                children.append(compile_node(child, prefix + (card,)))
            return _PlanRecord(_CHANCE, children=tuple(children))
        if isinstance(node, _Terminal):
            edge_row = edges[prefix]
            compile_counts["terminal_edge_references"] += len(edge_row)
            if compile_counts["terminal_edge_references"] > max_terminal_edge_references:
                raise ValueError("target plan terminal-edge reference cap exceeded during compile")
            if node.kind == "fold":
                player0_sign = 1.0 if node.winner == 0 else -1.0
                payoff = player0_sign * (half_pot + min(node.contributions))
                return _PlanRecord(_TERMINAL_FOLD, edges=edge_row, payoff=payoff)
            scale = half_pot + min(node.contributions)
            return _PlanRecord(_TERMINAL_SHOWDOWN, edges=edge_row, payoff=scale)

        keys = []
        player = node.player
        for hand_index in range(hand_counts[player]):
            compile_counts["key_references"] += 1
            if compile_counts["key_references"] > max_key_references:
                raise ValueError("target plan key-reference cap exceeded during compile")
            keys.append((player, hand_index, node.history))
        children = []
        for child in node.children:
            compile_counts["child_references"] += 1
            if compile_counts["child_references"] > max_child_references:
                raise ValueError("target plan child-reference cap exceeded during compile")
            children.append(compile_node(child, prefix))
        return _PlanRecord(_DECISION, children=tuple(children), player=player,
                           action_count=len(node.actions), keys=tuple(keys),
                           history=node.history)

    try:
        compiled_root = compile_node(root, ())
    finally:
        compile_node = None

    metadata = {**counts,
                "max_records": max_records,
                "information_row_references": info_reference_count,
                "max_info_references": max_info_references,
                "max_key_references": max_key_references,
                "max_child_references": max_child_references,
                "max_terminal_edge_references": max_terminal_edge_references}
    return TargetDeltaPlan(compiled_root, tuple(tuple(rows) for rows in infos_by_player),
                           tuple(hand_counts), metadata)
