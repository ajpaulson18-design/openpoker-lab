"""Independent card-free projection of the numeric betting rules for tests.

This compiler is test support only.  It delegates each menu and transition to
the independent matrix-free numeric rules, then interns equivalent money
continuations while keeping the special preflop empty-history bit.  It is not a
trainer, physical-support census, or replacement public game.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from typing import Any

from pokerlab.cards import DECK, cards
from scripts.matrix_free_certificate_budget import Budget
from scripts.matrix_free_four_street_rules import (
    _RevealStart, _TerminalStart,
    _actions_for, _blind_all_in, _charge_action_menu, _charge_settlement,
    _charge_successor, _initial_state,
    _next_decision, _settle_state, _snapshot_inputs, _state_after_reveal,
)
from scripts.preflop_validation import _State


DEFAULT_TEMPLATE_LIMITS = {
    "nodes": 250_000,
    "edges": 1_000_000,
    "work": 500_000_000,
    "entries": 2_000_000,
    "occurrences": 1_000_000_000_000,
    "depth": 64,
}
DEFAULT_NATIVE_TEST_LIMITS = {
    # Explicit geometry keeps the probe's pessimistic response forecast under
    # its fixed 64 MiB ceiling for these small structural parity fixtures.
    **DEFAULT_TEMPLATE_LIMITS,
    "nodes": 4_000,
    "edges": 16_000,
}

_PHASE = {"decision": 0, "reveal": 1, "fold": 2, "showdown": 3}
_STREET_ORDER = (0, 3, 4, 5)


@dataclass(frozen=True)
class ReferenceEdge:
    kind: str
    amount: float = 0.0
    target: float = 0.0
    local_target: float = 0.0
    has_local_target: bool = False
    full_raise: bool = False
    token: str | None = None
    child: int = 0


@dataclass
class ReferenceNode:
    key: tuple
    phase: str
    street: int
    state: Any
    history_empty: bool
    edges: list[ReferenceEdge] = field(default_factory=list)


@dataclass(frozen=True)
class ReferenceTemplate:
    case: dict
    stacks: tuple
    small_blind: float
    big_blind: float
    stages: dict
    nodes: tuple[ReferenceNode, ...]
    root: int
    histories: tuple[tuple[int, int, int, int, int], ...]
    receipt: dict
    topological_order: tuple[int, ...]


def _limits_snapshot(limits):
    if limits is None:
        return dict(DEFAULT_TEMPLATE_LIMITS)
    if type(limits) is not dict or set(limits) - set(DEFAULT_TEMPLATE_LIMITS):
        raise ValueError("template reference limits must be a bounded plain mapping")
    result = dict(DEFAULT_TEMPLATE_LIMITS)
    for key, value in limits.items():
        if type(value) is not int or value <= 0 or value > DEFAULT_TEMPLATE_LIMITS[key]:
            raise ValueError("template reference limits are positive reduce-only integers")
        result[key] = value
    return result


def _source_parts(case, budget):
    # Use one supplied outcome only to normalize the existing case/config
    # contract.  This function never enumerates ranks or deals.
    if type(case) is not dict or not case.get("runouts"):
        raise ValueError("the rules-reference case must supply a bounded runout anchor")
    inputs = _snapshot_inputs(case, budget, {
        "hands_per_seat": 16, "selected_outcomes": 64,
        "public_nodes": 250_000, "public_depth": 64,
    })
    normalized_case, _ranges, _outcomes, stacks, sb, bb, stages = inputs
    return normalized_case, tuple(stacks), float(sb), float(bb), stages


def _double_bits(value):
    import struct
    return struct.unpack(">Q", struct.pack(">d", float(value)))[0]


def _state_parts(value, history_empty):
    if isinstance(value, _RevealStart):
        state, phase, next_street = value.state, "reveal", value.board_length
    elif isinstance(value, _TerminalStart):
        state = value.state
        phase = "fold" if value.winner is not None else "showdown"
        next_street = 0
    elif isinstance(value, _State):
        state, phase, next_street = value, "decision", 0
    else:
        raise TypeError(f"unexpected rule continuation type {type(value).__name__}")
    winner = value.winner if isinstance(value, _TerminalStart) and value.winner is not None else 2
    key = (
        _PHASE[phase], state.street, state.player, next_street, winner,
        _double_bits(state.committed[0]), _double_bits(state.committed[1]),
        _double_bits(state.increment), state.raises, bool(state.reopened), state.checks,
        state.origin is not None, _double_bits(0.0 if state.origin is None else state.origin),
        _double_bits(state.boundary_pot), state.local_committed is not None,
        _double_bits(0.0 if state.local_committed is None else state.local_committed[0]),
        _double_bits(0.0 if state.local_committed is None else state.local_committed[1]),
        history_empty,
    )
    return state, phase, next_street, winner, key


def _edge_from_detail(action, detail, child):
    name, amount, target, full_raise = detail[:4]
    local = detail[4] if len(detail) > 4 else None
    return ReferenceEdge(
        kind=name, amount=float(action.amount), target=float(action.raise_to),
        local_target=0.0 if local is None else float(local),
        has_local_target=local is not None, full_raise=bool(full_raise),
        token=action.token, child=child,
    )


def build_reference_template(case, *, limits=None, initial_history_empty=True, rule_budget=None):
    """Build a bounded symbolic continuation graph from independent numeric rules."""
    if type(initial_history_empty) is not bool:
        raise ValueError("initial_history_empty must be boolean")
    ceilings = _limits_snapshot(limits)
    if rule_budget is not None and type(rule_budget) is not Budget:
        raise ValueError("shared numeric-rule budget must be a Budget owner")
    # Default component accounting is unchanged. Integration can share one
    # parent meter across multiple builds without resetting numeric costs.
    budget = (Budget({"work": 500_000_000, "entries": 8_000_000})
              if rule_budget is None else rule_budget)
    normalized_case, stacks, sb, bb, stages = _source_parts(case, budget)
    initial = _initial_state(stacks, sb, bb, budget)
    # The numeric rules' legacy state has no explicit empty-history flag. A
    # marker is used only to make its preflop BB-option check reflect the
    # template flag; suffix counters below start at zero and exclude it.
    if not initial_history_empty:
        initial = replace(initial, history=("__prior_history_present__",))
    root_value = _TerminalStart(initial) if _blind_all_in(initial, stacks) else initial
    states = []
    nodes = []
    index = {}
    queue = deque()
    python_work = 0

    def intern(raw, history_empty=False):
        nonlocal python_work
        if isinstance(raw, _State) and float(raw.committed[raw.player]) >= float(stacks[raw.player]) - 1e-9:
            raw = _settle_state(raw, stacks, budget)
        state, phase, next_street, _winner, key = _state_parts(raw, history_empty)
        found = index.get(key)
        if found is not None:
            return found
        if len(nodes) >= ceilings["nodes"]:
            raise ValueError("reference template node limit exceeded")
        node_id = len(nodes)
        index[key] = node_id
        states.append(raw)
        nodes.append(ReferenceNode(
            key=key, phase=phase, street=state.street, state=raw,
            history_empty=history_empty))
        queue.append(node_id)
        python_work += 1
        return node_id

    root = intern(root_value, initial_history_empty)
    edge_count = 0
    while queue:
        node_id = queue.popleft()
        raw = states[node_id]
        node = nodes[node_id]
        if isinstance(raw, _TerminalStart):
            continue
        if isinstance(raw, _RevealStart):
            # This representative card prefix is used only to advance the
            # numeric money state; no real card is in the template key.
            prefix = {3: ("2c", "3c", "4d"), 4: ("2c", "3c", "4d", "7h"),
                      5: ("2c", "3c", "4d", "7h", "8h")}[raw.board_length]
            child_state = _state_after_reveal(raw.state, prefix, raw.board_length, budget)
            child_id = intern(child_state, False)
            node.edges.append(ReferenceEdge(kind="reveal", child=child_id))
            edge_count += 1
        else:
            _charge_action_menu(budget, raw, stages)
            actions, details = _actions_for(raw, stacks, stages, budget)
            for action, detail in zip(actions, details):
                _charge_successor(budget, raw)
                child_state, _winner = _next_decision(raw, detail, stacks, budget)
                child_flag = node.history_empty if detail[0] == "fold" else False
                child_id = intern(child_state, child_flag)
                node.edges.append(_edge_from_detail(action, detail, child_id))
                edge_count += 1
        if edge_count > ceilings["edges"]:
            raise ValueError("reference template edge limit exceeded")
        python_work += len(node.edges)

    topology = _topological_order(nodes)
    histories, counts, max_depth, total_occurrences = _history_census(
        nodes, root, topology, ceilings)
    receipt = {
        "nodes": len(nodes), "edges": edge_count, "max_depth": max_depth,
        "logical_occurrences": total_occurrences,
        "python_reference_steps": python_work,
        "rule_budget": budget.receipt(),
        "decisions": counts["decisions"], "reveals": counts["reveals"],
        "folds": counts["folds"], "showdowns": counts["showdowns"],
        "action_slots": counts["action_slots"],
    }
    return ReferenceTemplate(normalized_case, stacks, sb, bb, stages, tuple(nodes),
                             root, tuple(histories), receipt, tuple(topology))


def _topological_order(nodes):
    indegree = [0] * len(nodes)
    for node in nodes:
        for edge in node.edges:
            indegree[edge.child] += 1
    ready = deque(i for i, degree in enumerate(indegree) if degree == 0)
    result = []
    while ready:
        node_id = ready.popleft()
        result.append(node_id)
        for edge in nodes[node_id].edges:
            indegree[edge.child] -= 1
            if indegree[edge.child] == 0:
                ready.append(edge.child)
    if len(result) != len(nodes):
        raise ValueError("reference template contains a cycle")
    return result


def _history_census(nodes, root, topology, limits):
    size = len(nodes)
    paths = [0] * size
    semantic_tokens = [0] * size
    semantic_bytes = [0] * size
    legacy_tokens = [0] * size
    legacy_bytes = [0] * size
    depth = [0] * size
    paths[root] = 1
    street = CounterLike()
    total_occurrences = 0
    for node_id in topology:
        node = nodes[node_id]
        visits = paths[node_id]
        if visits == 0:
            raise ValueError("reference template contains unreachable node")
        total_occurrences += visits
        if total_occurrences > limits["occurrences"]:
            raise ValueError("reference template occurrence limit exceeded")
        count_street = node.state.board_length if node.phase == "reveal" else node.street
        index = _STREET_ORDER.index(count_street)
        if node.phase == "decision":
            street["decisions"][index][node.state.player] += visits
            street["action_slots"][index] += visits * len(node.edges)
        elif node.phase == "reveal":
            street["reveals"][index] += visits
        elif node.phase == "fold":
            street["folds"][index] += visits
        else:
            street["showdowns"][index] += visits
        for edge in node.edges:
            child = edge.child
            token_edge = True  # Every edge is one action or one public reveal.
            sem_increment = 1
            sem_bytes_inc = (11 if node.state.board_length == 3 else
                             7 if node.state.board_length == 4 else 8) if edge.kind == "reveal" else (
                             len(edge.token.encode("ascii")) if edge.token is not None else 0)
            old_edge = token_edge and not (node.phase == "decision" and edge.kind == "fold")
            paths[child] += visits
            semantic_tokens[child] += semantic_tokens[node_id] + sem_increment * visits
            semantic_bytes[child] += semantic_bytes[node_id] + sem_bytes_inc * visits
            legacy_tokens[child] += legacy_tokens[node_id] + (visits if old_edge else 0)
            legacy_bytes[child] += legacy_bytes[node_id] + (sem_bytes_inc * visits if old_edge else 0)
            depth[child] = max(depth[child], depth[node_id] + 1)
            if depth[child] > limits["depth"]:
                raise ValueError("reference template depth limit exceeded")
    histories = tuple((paths[i], semantic_tokens[i], semantic_bytes[i],
                       legacy_tokens[i], legacy_bytes[i]) for i in range(size))
    return histories, street, max(depth, default=0), total_occurrences


def literal_reference_census(case, *, initial_history_empty=True, limits=None, rule_budget=None):
    """Expand each symbolic action/reveal path without interning states.

    This is intentionally a small-fixture oracle. It independently checks the
    DAG's path multiplicities and semantic/legacy token totals by grouping a
    literal tree walk only after every path has been visited.
    """
    ceilings = _limits_snapshot(limits)
    if rule_budget is not None and type(rule_budget) is not Budget:
        raise ValueError("shared numeric-rule budget must be a Budget owner")
    # Default component accounting is unchanged. Integration can share one
    # parent meter across multiple builds without resetting numeric costs.
    budget = (Budget({"work": 500_000_000, "entries": 8_000_000})
              if rule_budget is None else rule_budget)
    _normalized, stacks, sb, bb, stages = _source_parts(case, budget)
    initial = _initial_state(stacks, sb, bb, budget)
    if not initial_history_empty:
        initial = replace(initial, history=("__prior_history_present__",))
    root = _TerminalStart(initial) if _blind_all_in(initial, stacks) else initial
    todo = [(root, 0, 0, 0, 0, 0, initial_history_empty)]
    grouped = {}
    street = CounterLike()
    visits = edge_count = max_depth = 0
    while todo:
        raw, depth, sem_tokens, sem_bytes, old_tokens, old_bytes, empty_flag = todo.pop()
        if isinstance(raw, _State) and float(raw.committed[raw.player]) >= float(stacks[raw.player]) - 1e-9:
            _charge_settlement(budget, raw)
            raw = _settle_state(raw, stacks, budget)
        state, phase, _next_street, _winner, key = _state_parts(raw, empty_flag)
        visits += 1
        if visits > ceilings["occurrences"]:
            raise ValueError("literal reference occurrence limit exceeded")
        max_depth = max(max_depth, depth)
        if depth > ceilings["depth"]:
            raise ValueError("literal reference depth limit exceeded")
        bucket = grouped.setdefault(key, [0, 0, 0, 0, 0])
        bucket[0] += 1
        bucket[1] += sem_tokens
        bucket[2] += sem_bytes
        bucket[3] += old_tokens
        bucket[4] += old_bytes
        count_street = raw.board_length if isinstance(raw, _RevealStart) else state.street
        street_index = _STREET_ORDER.index(count_street)
        if phase == "decision":
            street["decisions"][street_index][state.player] += 1
        elif phase == "reveal":
            street["reveals"][street_index] += 1
        elif phase == "fold":
            street["folds"][street_index] += 1
        else:
            street["showdowns"][street_index] += 1
        if phase in ("fold", "showdown"):
            continue
        if phase == "reveal":
            prefix = {3: ("2c", "3c", "4d"), 4: ("2c", "3c", "4d", "7h"),
                      5: ("2c", "3c", "4d", "7h", "8h")}[raw.board_length]
            child = _state_after_reveal(state, prefix, raw.board_length, budget)
            edge_count += 1
            byte_width = {3: 11, 4: 7, 5: 8}[raw.board_length]
            todo.append((child, depth + 1, sem_tokens + 1, sem_bytes + byte_width,
                         old_tokens + 1, old_bytes + byte_width, False))
            continue
        _charge_action_menu(budget, state, stages)
        actions, details = _actions_for(state, stacks, stages, budget)
        street["action_slots"][street_index] += len(actions)
        for action, detail in zip(actions, details):
            _charge_successor(budget, state)
            child, _winner = _next_decision(state, detail, stacks, budget)
            is_fold = detail[0] == "fold"
            edge_count += 1
            todo.append((child, depth + 1, sem_tokens + 1,
                         sem_bytes + len(action.token.encode("ascii")),
                         old_tokens + (0 if is_fold else 1),
                         old_bytes + (0 if is_fold else len(action.token.encode("ascii"))),
                         empty_flag if is_fold else False))
        if edge_count > ceilings["edges"]:
            raise ValueError("literal reference edge limit exceeded")
    return {"nodes": visits, "edges": edge_count, "max_depth": max_depth,
            "logical_occurrences": visits, "streets": street._v,
            "by_key": {key: tuple(value) for key, value in grouped.items()},
            "rule_budget": budget.receipt()}


def project_unfiltered_selected_prefix_counts(case, template):
    """Project a card-independent template over distinct selected prefixes.

    This multiplies structural histories by public prefix multiplicities only;
    it deliberately does not consult blockers, ranges, private support, or ranks.
    """
    if type(case) is not dict or type(template) is not ReferenceTemplate:
        raise ValueError("expected a bounded case and its reference template")
    card_order = {card: i for i, card in enumerate(DECK)}
    outcomes = []
    for text in case["runouts"]:
        board = cards(text, 5)
        outcomes.append(tuple(sorted(board[:3], key=card_order.__getitem__)) + board[3:])
    prefixes = {length: {board[:length] for board in outcomes}
                for length in (0, 3, 4, 5)}
    prefix_counts = {0: 1, **{length: len(prefixes[length]) for length in (3, 4, 5)}}
    per_street = CounterLike()
    totals = {"decisions": 0, "action_slots": 0, "reveals": 0,
              "reveal_edges": 0, "folds": 0, "showdowns": 0,
              "history_tokens": 0, "history_characters": 0,
              "semantic_history_tokens": 0, "semantic_history_characters": 0,
              "action_token_characters": 0}
    for index, node in enumerate(template.nodes):
        raw = node.state
        state = raw.state if hasattr(raw, "state") else raw
        current_street = state.street
        multiplicity = prefix_counts[current_street]
        paths, sem_tokens, sem_bytes, legacy_tokens, legacy_bytes = template.histories[index]
        totals["history_tokens"] += legacy_tokens * multiplicity
        totals["history_characters"] += legacy_bytes * multiplicity
        totals["semantic_history_tokens"] += sem_tokens * multiplicity
        totals["semantic_history_characters"] += sem_bytes * multiplicity
        street_index = _STREET_ORDER.index(current_street)
        if node.phase == "decision":
            slots = len(node.edges)
            totals["decisions"] += paths * multiplicity
            totals["action_slots"] += paths * multiplicity * slots
            totals["action_token_characters"] += paths * multiplicity * sum(
                len(edge.token.encode("ascii")) for edge in node.edges if edge.token is not None)
            per_street["decisions"][street_index][state.player] += paths * multiplicity
            per_street["action_slots"][street_index] += paths * multiplicity * slots
        elif node.phase == "reveal":
            next_length = raw.board_length
            totals["reveals"] += paths * multiplicity
            totals["reveal_edges"] += paths * prefix_counts[next_length]
            per_street["reveals"][street_index] += paths * multiplicity
        elif node.phase == "fold":
            totals["folds"] += paths * multiplicity
            per_street["folds"][street_index] += paths * multiplicity
        else:
            totals["showdowns"] += paths * multiplicity
            per_street["showdowns"][street_index] += paths * multiplicity
    totals["public_nodes"] = totals["decisions"] + totals["reveals"] + totals["folds"] + totals["showdowns"]
    totals["depth"] = template.receipt["max_depth"]
    return {"prefix_counts": prefix_counts, "selected_outcomes": len(outcomes),
            "unfiltered_prefix_geometry": True, "counts": totals,
            "per_street": per_street._v}


class CounterLike:
    def __init__(self):
        self._v = {
            "decisions": [[0, 0] for _ in range(4)],
            "reveals": [0] * 4, "folds": [0] * 4, "showdowns": [0] * 4,
            "action_slots": [0] * 4,
        }

    def __getitem__(self, key):
        return self._v[key]


def native_config_tokens(case, *, initial_history_empty=True, limits=None):
    """Return a token list for Terra's VIRTUAL_BETTING_V1 BUILD grammar."""
    _case, stacks, sb, bb, stages = _source_parts(case, Budget())
    lim = dict(DEFAULT_NATIVE_TEST_LIMITS) if limits is None else _limits_snapshot(limits)
    fields = ["VIRTUAL_BETTING_V1", "BUILD", "limits",
              str(lim["nodes"]), str(lim["edges"]), str(lim["work"]),
              str(lim["entries"]), str(lim["occurrences"]), str(lim["depth"]),
              "config", _bits(stacks[0]), _bits(stacks[1]), _bits(sb), _bits(bb),
              "1" if initial_history_empty else "0"]
    for street in _STREET_ORDER:
        stage = stages[street]
        fields.extend(["stage", str(street), str(len(stage["bet_sizes"]))])
        fields.extend(_bits(x) for x in stage["bet_sizes"])
        fields.append(str(len(stage["raise_sizes"])))
        fields.extend(_bits(x) for x in stage["raise_sizes"])
        fields.extend([str(stage["max_raises"]), "1" if stage["include_all_in"] else "0"])
    return " ".join(fields) + "\n"


def override_native_config_bits(wire, *, stack0=None, stack1=None, small_blind=None,
                                big_blind=None):
    """Replace raw config bit fields after a valid case supplies its menus."""
    fields = wire.split()
    if len(fields) < 15 or fields[9] != "config":
        raise ValueError("expected a native BUILD config request")
    for index, value in ((10, stack0), (11, stack1), (12, small_blind), (13, big_blind)):
        if value is not None:
            fields[index] = _bits(value)
    return " ".join(fields) + "\n"


def native_state_tokens(case, state, *, initial_history_empty=True, limits=None):
    """Serialize a bounded decision-root STATE request for probe invariants."""
    required = {"phase", "street", "actor", "committed", "increment", "raises",
                "reopened", "checks", "origin_present", "origin", "boundary_pot",
                "local_present", "local", "history_empty"}
    if type(state) is not dict or set(state) != required:
        raise ValueError("STATE fields must match the bounded decision schema")
    fields = native_config_tokens(case, initial_history_empty=initial_history_empty,
                                  limits=limits).split()
    fields[1] = "STATE"
    fields.extend(("state", str(state["phase"]), str(state["street"]),
                   str(state["actor"]), _bits(state["committed"][0]),
                   _bits(state["committed"][1]), _bits(state["increment"]),
                   str(state["raises"]), "1" if state["reopened"] else "0",
                   str(state["checks"]), "1" if state["origin_present"] else "0",
                   _bits(state["origin"]), _bits(state["boundary_pot"]),
                   "1" if state["local_present"] else "0", _bits(state["local"][0]),
                   _bits(state["local"][1]), "1" if state["history_empty"] else "0"))
    return " ".join(fields) + "\n"


def _bits(value):
    return f"{_double_bits(value):016x}"
