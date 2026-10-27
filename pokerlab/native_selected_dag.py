"""Explicit native packed CFR+ over a directly shared selected-public DAG.

The Python adapter retains unique vertices and reachable ``(vertex, prefix)``
contexts, then streams logical occurrences only to authenticate policy rows.
Its limits are modeled entry/work bounds, not allocator or process-RSS bounds.
"""
from __future__ import annotations

from dataclasses import dataclass
from array import array
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys

from .cards import DECK, cards
from .native_selected_operator import _rank_code, arithmetic_identity
from .selected_operator_solver import MAX_OPERATOR_SCAN_ENTRIES
from .selected_runout_operator import SelectedRunoutOperator
from .shared_public_topology import (
    ChanceVertex, DecisionVertex, SharedPublicTopology, TerminalVertex,
)
from .shared_topology_view import SharedPublicView


SOURCE = Path(__file__).resolve().parents[1] / "native" / "selected_dag_train.cpp"
PROTOCOL = "OPENPOKER_SELECTED_DAG_V1"
WORK_MODEL = "native-selected-dag-work-v1"
HELPER_BASE = "native-selected-dag-train"
MANIFEST_NAME = "native-selected-dag-manifest.json"
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_STDERR_BYTES = 8192
MAX_HEAP_BYTES = 256 * 1024 * 1024
MAX_WORK = 500_000_000
MAX_DEPTH = 64
MAX_HANDS = 128
MAX_VISITS = 250_000
MAX_DENSE_SLOTS = 2_000_000
MAX_ACTION_SLOTS = 1_000_000
MAX_ROWS = 1_000_000
MAX_PREFIXES = 193
MAX_CONTEXTS = 250_000
MAX_BOARDS = 64
MAX_RANK_ENTRIES = 8192
TIMEOUT = 180
_BITS = {card: 1 << index for index, card in enumerate(DECK)}
_DECK_INDEX = {card: index for index, card in enumerate(DECK)}


@dataclass(frozen=True, slots=True)
class _Summary:
    visits: int = 1
    rows: int = 0
    slots: int = 0
    dense: int = 0
    terminal_candidates: int = 0
    marginal_candidates: int = 0
    action_hands: int = 0
    opponent_hands: int = 0
    chance_children: int = 0
    decision_children: int = 0
    maximum_depth: int = 0

    def plus(self, other: "_Summary") -> "_Summary":
        return _Summary(
            self.visits + other.visits, self.rows + other.rows,
            self.slots + other.slots, self.dense + other.dense,
            self.terminal_candidates + other.terminal_candidates,
            self.marginal_candidates + other.marginal_candidates,
            self.action_hands + other.action_hands,
            self.opponent_hands + other.opponent_hands,
            self.chance_children + other.chance_children,
            self.decision_children + other.decision_children,
            max(self.maximum_depth, other.maximum_depth + 1),
        )


@dataclass(frozen=True, slots=True)
class _Context:
    vertex_id: int
    prefix_id: int
    child_contexts: tuple[int, ...]
    summary: _Summary


@dataclass(frozen=True, slots=True)
class NativeSelectedDagPlan:
    view: SharedPublicView
    operator: SelectedRunoutOperator
    iterations: int
    mode: int
    prefixes: tuple[tuple[str, ...], ...]
    active_hands: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]
    contexts: tuple[_Context, ...]
    context_root: int
    preorder_keys: tuple[tuple[int, int, tuple[str, ...]], ...]
    row_counts: tuple[int, ...]
    receipt: dict
    operator_snapshot: tuple
    topology_snapshot: tuple


def _mask(cards_):
    return sum(_BITS[card] for card in cards_)


def _prefix_tokens(prefix):
    if not prefix:
        return ()
    return (_mask(cards(prefix[0], 3)),) + tuple(_BITS[card] for card in prefix[1:])


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate native selected-DAG manifest field")
        result[key] = value
    return result


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def executable_identity(executable):
    """Authenticate the distinct selected-DAG helper against the current source."""
    supplied = Path(executable)
    if supplied.is_symlink():
        raise ValueError("Native selected-DAG trainer must not be a symlink")
    path = supplied.resolve(strict=True)
    expected_names = (HELPER_BASE, HELPER_BASE + ".exe")
    if not path.is_file() or path.name not in expected_names:
        raise ValueError("Native selected-DAG trainer must have its protocol-specific name")
    manifest_path = path.parent / MANIFEST_NAME
    if manifest_path.stat().st_size > 32768:
        raise ValueError("Native selected-DAG manifest exceeds its size limit")
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8"), object_pairs_hook=_object,
        parse_constant=lambda _: (_ for _ in ()).throw(
            ValueError("Nonfinite native manifest value")))
    required = {"schema_version", "protocol", "work_model", "source_sha256",
                "source_lf_sha256", "executable", "executable_sha256", "compiler",
                "compiler_version", "flags", "platform"}
    source = SOURCE.read_bytes()
    if (type(manifest) is not dict or set(manifest) != required or
            manifest["schema_version"] != 1 or manifest["protocol"] != PROTOCOL or
            manifest["work_model"] != WORK_MODEL or manifest["executable"] != path.name or
            manifest["source_sha256"] != hashlib.sha256(source).hexdigest() or
            manifest["source_lf_sha256"] != hashlib.sha256(
                source.replace(b"\r\n", b"\n")).hexdigest() or
            manifest["executable_sha256"] != _sha(path)):
        raise ValueError("Native selected-DAG source or executable changed; rebuild explicitly")
    if (any(type(manifest[key]) is not str or not manifest[key] for key in
            ("source_sha256", "source_lf_sha256", "executable_sha256", "compiler",
             "compiler_version", "platform")) or type(manifest["flags"]) is not list or
            any(type(flag) is not str for flag in manifest["flags"])):
        raise ValueError("Malformed native selected-DAG compiler provenance")
    return manifest


def _prefix_support(operator):
    """Return deterministic supported prefixes and active own-hand vectors."""
    h0, h1 = operator.hand_counts
    selected = operator.selected
    board_masks = operator._board_masks
    hand_masks = operator._hand_masks
    board_active = [([False] * h0, [False] * h1) for _ in selected]
    supported = [False] * len(selected)
    worlds = 0
    for i, mask0 in enumerate(hand_masks[0]):
        for j, mask1 in enumerate(hand_masks[1]):
            if mask0 & mask1:
                continue
            pair_mask = mask0 | mask1
            for k, board_mask in enumerate(board_masks):
                if board_mask & pair_mask:
                    continue
                supported[k] = True
                board_active[k][0][i] = True
                board_active[k][1][j] = True
                worlds += 1
    if worlds != operator.world_count:
        raise ValueError("Selected-DAG support scan differs from operator world count")
    board_records = tuple(("".join(flop), turn, river)
                          for flop, turn, river in selected)
    supported_records = tuple(board_records[index] for index, yes in enumerate(supported) if yes)

    prefixes = [()]
    prefix_ids = {(): 0}
    active = {(): [set(), set()]}
    for index, is_supported in enumerate(supported):
        if not is_supported:
            continue
        flop, turn, river = board_records[index]
        tokens = (flop, turn, river)
        for length in (1, 2, 3):
            prefix = tokens[:length]
            if prefix not in prefix_ids:
                if len(prefixes) >= MAX_PREFIXES:
                    raise ValueError("Native selected-DAG prefix capacity exceeded")
                prefix_ids[prefix] = len(prefixes)
                prefixes.append(prefix)
                active[prefix] = [set(), set()]
            for player in (0, 1):
                active_indexes = (hand for hand, yes in
                                  enumerate(board_active[index][player]) if yes)
                active[prefix][player].update(active_indexes)
                active[()][player].update(
                    hand for hand, yes in enumerate(board_active[index][player]) if yes)
    if len(prefixes) > MAX_PREFIXES:
        raise ValueError("Native selected-DAG prefix capacity exceeded")
    active_values = tuple((tuple(sorted(active[prefix][0])),
                           tuple(sorted(active[prefix][1]))) for prefix in prefixes)
    return board_records, supported_records, tuple(prefixes), active_values


def _validate_info_rows(infos, hand_counts):
    slots = 0
    for key, count in infos.items():
        if (type(key) is not tuple or len(key) != 3 or type(key[0]) is not int or
                key[0] not in (0, 1) or type(key[1]) is not int or
                not 0 <= key[1] < hand_counts[key[0]] or type(key[2]) is not tuple or
                any(type(token) is not str for token in key[2]) or
                type(count) is not int or not 1 <= count <= 12):
            raise ValueError("Malformed native selected-DAG information row")
        slots += count
        if slots > MAX_ACTION_SLOTS:
            raise ValueError("Native selected-DAG action-slot capacity exceeded")
    return slots


def _work_for_summary(summary, *, vertices, edges, contexts, context_edges,
                      boards, prefixes, hands, iterations):
    h0, h1 = hands
    hs = h0 + h1
    n, q, r, s = summary.visits, summary.dense, summary.rows, summary.slots
    tc, mc, ah, oh, ch, dc = (
        summary.terminal_candidates, summary.marginal_candidates,
        summary.action_hands, summary.opponent_hands,
        summary.chance_children, summary.decision_children)
    old_setup = (128 * (n + q + s) + 10 * mc + 32 * n * boards +
                 128 * boards * h0 * h1 + 64 * prefixes)
    old_sweep = (20 * tc + 10 * mc + 10 * n * hs + 12 * s +
                 6 * boards * n + 8 * ah + oh + ch * hs + 4 * dc)
    setup_extra = (256 * (vertices + edges + contexts + context_edges +
                          r + prefixes * hs) + 128 * prefixes * boards * hs +
                   32 * contexts * boards)
    sweep_extra = 16 * n * hs + 8 * q
    return old_setup + iterations * old_sweep + r + 2 * s + setup_extra + iterations * sweep_extra


def _heap_for(*, vertices, edges, contexts, context_edges, rows, slots,
              prefixes, boards, hands):
    h0, h1 = hands
    hs, width = h0 + h1, max(h0, h1)
    return (128 * 1024 * 1024 + 1 + 96 * vertices + 16 * edges +
            160 * contexts + 32 * context_edges + 24 * rows + 40 * slots +
            64 * prefixes + (2 * prefixes + boards) * hs * 8 +
            boards * (32 + 8 * hs) + 32 * hs + 65 * 66 * width * 16)


def _validate_operator(view, infos, iterations, operator):
    if type(view) is not SharedPublicView:
        raise TypeError("Native selected DAG requires an admitted SharedPublicView")
    if type(operator) is not SelectedRunoutOperator:
        raise TypeError("Native selected DAG requires its fixed selected-runout operator")
    from collections.abc import Mapping
    if not isinstance(infos, Mapping):
        raise TypeError("Native selected DAG information rows must be a mapping")
    if type(iterations) is not int or not 10 <= iterations <= 10_000:
        raise ValueError("Native selected DAG requires 10-10,000 iterations")
    h0, h1 = operator.hand_counts
    if (not 1 <= len(operator.selected) <= MAX_BOARDS or
            any(not 1 <= hand_count <= MAX_HANDS for hand_count in (h0, h1)) or
            len(operator.selected) * (h0 + h1) > MAX_RANK_ENTRIES):
        raise ValueError("Native selected-DAG board/hand/rank-vector capacity exceeded")
    if not math.isfinite(operator.normalizer) or operator.normalizer <= 0:
        raise ValueError("Native selected-DAG normalizer must be finite and positive")
    if not math.isfinite(operator.pot) or operator.pot <= 0 or operator.pot != 2 * view.anchor:
        raise ValueError("Native selected-DAG operator pot must match the shifted-view anchor")
    if view.topology.initial_history:
        raise ValueError("Native selected-DAG root must have an empty public history")
    return view.topology, (h0, h1)


def _operator_snapshot(operator):
    return (operator.hands, operator.weights, operator.hand_counts,
            operator.selected, operator._board_masks, operator._hand_masks,
            operator.normalizer.hex(), operator.pot.hex())


def _context_graph(topology, prefixes, active_hands, board_records, supported_records,
                   hand_counts, infos, iterations):
    prefix_ids = {prefix: index for index, prefix in enumerate(prefixes)}
    prefix_id_map = prefix_ids
    contexts = []
    context_ids = {}
    pending = []
    context_edges = 0
    boards = len(board_records)
    prefix_count = len(prefixes)
    vertex_count = len(topology.vertices)
    edge_count = topology.census.unique_edges

    def reserve_context(vertex_id, prefix):
        key = (vertex_id, prefix_id_map[prefix])
        existing = context_ids.get(key)
        if existing is not None:
            return existing
        if len(contexts) >= MAX_CONTEXTS:
            raise ValueError("Native selected-DAG context capacity exceeded")
        projected_contexts = len(contexts) + 1
        if _heap_for(vertices=vertex_count, edges=edge_count,
                     contexts=projected_contexts, context_edges=context_edges,
                     rows=0, slots=0, prefixes=prefix_count,
                     boards=boards, hands=hand_counts) > MAX_HEAP_BYTES:
            raise ValueError("Native selected-DAG context heap admission rejected")
        context_id = len(contexts)
        context_ids[key] = context_id
        contexts.append([vertex_id, prefix_id_map[prefix], (), None])
        pending.append(context_id)
        return context_id

    root_context = reserve_context(topology.root_id, ())
    cursor = 0
    reachable_vertices = set()
    while cursor < len(pending):
        context_id = pending[cursor]
        cursor += 1
        vertex_id, prefix_id, _children, _summary = contexts[context_id]
        prefix = prefixes[prefix_id]
        vertex = topology.vertices[vertex_id]
        reachable_vertices.add(vertex_id)
        if isinstance(vertex, TerminalVertex):
            children = ()
        elif isinstance(vertex, DecisionVertex):
            if (vertex.player not in (0, 1) or not vertex.actions or
                    len(vertex.actions) != len(vertex.child_ids) or
                    len(vertex.actions) > 12):
                raise ValueError("Malformed native selected-DAG decision")
            children = tuple((action.token, child_id, prefix)
                             for action, child_id in zip(vertex.actions, vertex.child_ids))
        elif isinstance(vertex, ChanceVertex):
            stage = {"flop": 0, "turn": 1, "river": 2}.get(vertex.street)
            if stage is None or stage != len(prefix) or stage >= 3:
                raise ValueError("Native selected-DAG chance stage/prefix mismatch")
            branch_tokens = tuple(token for token, _child in vertex.branches)
            if len(branch_tokens) > 64 or len(set(branch_tokens)) != len(branch_tokens):
                raise ValueError("Malformed native selected-DAG chance branches")
            if stage == 0:
                expected_order = tuple(dict.fromkeys(board[0] for board in supported_records))
            elif stage == 1:
                expected_order = tuple(sorted({board[1] for board in supported_records
                                               if board[:1] == prefix}))
            else:
                expected_order = tuple(sorted({board[2] for board in supported_records
                                               if board[:2] == prefix}))
            if branch_tokens != expected_order:
                raise ValueError("Native selected-DAG chance branches do not partition global support")
            children = tuple((token, child_id, prefix + (token,))
                             for token, child_id in vertex.branches)
        else:
            raise ValueError("Unsupported native selected-DAG vertex")
        child_contexts = []
        if context_edges + len(children) > MAX_VISITS - 1:
            raise ValueError("Native selected-DAG context-edge capacity exceeded")
        if _heap_for(vertices=vertex_count, edges=edge_count,
                     contexts=len(contexts), context_edges=context_edges + len(children),
                     rows=0, slots=0, prefixes=prefix_count,
                     boards=boards, hands=hand_counts) > MAX_HEAP_BYTES:
            raise ValueError("Native selected-DAG context-edge heap admission rejected")
        for _token, child_vertex, child_prefix in children:
            if not 0 <= child_vertex < vertex_id:
                raise ValueError("Native selected-DAG vertices are not postorder")
            child_context = reserve_context(child_vertex, child_prefix)
            child_contexts.append(child_context)
        context_edges += len(child_contexts)
        if context_edges > MAX_VISITS - 1:
            raise ValueError("Native selected-DAG context-edge capacity exceeded")
        contexts[context_id][2] = tuple(child_contexts)
    if len(reachable_vertices) != len(topology.vertices):
        raise ValueError("Native selected-DAG contains an unreachable vertex")

    selected_matches = {}
    for prefix in prefixes:
        selected_matches[prefix] = sum(
            1 for board in board_records if board[:len(prefix)] == prefix)
        if selected_matches[prefix] == 0:
            raise ValueError("Native selected-DAG context prefix has no selected board")

    # Children have lower postorder vertex IDs, so this is a bounded postorder
    # summary pass over unique contexts; repeated context edges compose repeatedly.
    by_vertex = sorted(range(len(contexts)), key=lambda item: contexts[item][0])
    for context_id in by_vertex:
        vertex_id, prefix_id, child_ids, _ = contexts[context_id]
        prefix = prefixes[prefix_id]
        vertex = topology.vertices[vertex_id]
        matches = selected_matches[prefix]
        if isinstance(vertex, TerminalVertex):
            own = _Summary(terminal_candidates=matches * hand_counts[0] * hand_counts[1])
        elif isinstance(vertex, DecisionVertex):
            active_count = len(active_hands[prefix_id][vertex.player])
            action_count = len(vertex.actions)
            own = _Summary(
                rows=active_count, slots=active_count * action_count,
                dense=hand_counts[vertex.player],
                marginal_candidates=matches * hand_counts[0] * hand_counts[1],
                action_hands=action_count * hand_counts[vertex.player],
                opponent_hands=action_count * hand_counts[1 - vertex.player],
                decision_children=action_count,
            )
        else:
            own = _Summary(chance_children=len(vertex.branches))
        summary = own
        for child_id in child_ids:
            child_summary = contexts[child_id][3]
            if child_summary is None:
                raise ValueError("Native selected-DAG context order is not postorder")
            summary = summary.plus(child_summary)
            if (summary.visits > MAX_VISITS or summary.dense > MAX_DENSE_SLOTS or
                    summary.rows > MAX_ROWS or summary.slots > MAX_ACTION_SLOTS):
                raise ValueError("Native selected-DAG logical context summary exceeds limits")
            if _work_for_summary(
                    summary, vertices=vertex_count, edges=edge_count,
                    contexts=len(contexts), context_edges=context_edges,
                    boards=boards, prefixes=prefix_count,
                    hands=hand_counts, iterations=iterations) > MAX_WORK:
                raise ValueError("Native selected-DAG incremental work admission rejected")
            if _heap_for(
                    vertices=vertex_count, edges=edge_count, contexts=len(contexts),
                    context_edges=context_edges, rows=summary.rows, slots=summary.slots,
                    prefixes=prefix_count, boards=boards, hands=hand_counts) > MAX_HEAP_BYTES:
                raise ValueError("Native selected-DAG incremental heap admission rejected")
        if summary.maximum_depth > MAX_DEPTH:
            raise ValueError("Native selected-DAG logical depth exceeds limit")
        contexts[context_id][3] = summary
    if len(contexts) > contexts[root_context][3].visits:
        raise ValueError("Native selected-DAG contexts exceed logical visits")
    if context_edges > contexts[root_context][3].visits - 1:
        raise ValueError("Native selected-DAG context edges exceed logical edges")

    return contexts, root_context, context_edges


def _logical_rows(topology, root_context, contexts, prefixes, active_hands,
                  infos, hand_counts):
    remaining = set(infos)
    row_keys = []
    row_counts = []
    history = []
    # Frames hold only one logical path; there is no node/history occurrence table.
    stack = [(root_context, 0, 0)]
    while stack:
        context_id, child_index, restore_length = stack[-1]
        if child_index == 0:
            vertex_id, prefix_id, child_contexts, _summary = contexts[context_id]
            vertex = topology.vertices[vertex_id]
            if isinstance(vertex, DecisionVertex):
                actions = vertex.actions
                for hand in active_hands[prefix_id][vertex.player]:
                    key = (vertex.player, hand, tuple(history))
                    count = infos.get(key)
                    if count is None or count != len(actions) or key not in remaining:
                        raise ValueError("Native selected-DAG policy rows do not match logical preorder")
                    remaining.remove(key)
                    row_keys.append(key)
                    row_counts.append(count)
        vertex_id, prefix_id, child_contexts, _summary = contexts[context_id]
        vertex = topology.vertices[vertex_id]
        if child_index < len(child_contexts):
            stack[-1] = (context_id, child_index + 1, restore_length)
            child_context = child_contexts[child_index]
            child_vertex_id = contexts[child_context][0]
            child_vertex = topology.vertices[vertex_id]
            if isinstance(child_vertex, DecisionVertex):
                token = child_vertex.actions[child_index].token
            elif isinstance(child_vertex, ChanceVertex):
                token = child_vertex.branches[child_index][0]
                token = f"{child_vertex.street}@{token}"
            else:
                raise ValueError("Terminal context unexpectedly has children")
            history.append(token)
            stack.append((child_context, 0, len(history) - 1))
            continue
        stack.pop()
        if stack:
            del history[restore_length:]
    if remaining:
        raise ValueError("Native selected-DAG policy rows contain orphan information sets")
    return tuple(row_keys), tuple(row_counts)


def prepare(view, infos, iterations, operator):
    """Rank-free complete topology/context/row admission and plan creation."""
    topology, hand_counts = _validate_operator(view, infos, iterations, operator)
    requested_slots = _validate_info_rows(infos, hand_counts)
    h0, h1 = hand_counts
    if not 1 <= len(topology.vertices) <= MAX_VISITS:
        raise ValueError("Native selected-DAG vertex count exceeds limit")
    actual_edges = 0
    for vertex in topology.vertices:
        if isinstance(vertex, DecisionVertex):
            actual_edges += len(vertex.child_ids)
        elif isinstance(vertex, ChanceVertex):
            actual_edges += len(vertex.branches)
        elif not isinstance(vertex, TerminalVertex):
            raise ValueError("Unsupported native selected-DAG vertex")
        if actual_edges > MAX_VISITS - 1:
            raise ValueError("Native selected-DAG unique-edge capacity exceeded")
    if actual_edges != topology.census.unique_edges:
        raise ValueError("Native selected-DAG unique-edge census mismatch")
    pairs = hand_counts[0] * hand_counts[1]
    support_scan_upper = 2 * (MAX_PREFIXES + 2) * (
        pairs * len(operator.selected) + pairs + len(operator.selected))
    if support_scan_upper > MAX_OPERATOR_SCAN_ENTRIES:
        raise ValueError("Native selected-DAG prefix support scan upper bound exceeds 500 million")
    # Admit prefix/support scratch at the physical maximum before constructing it.
    if _heap_for(vertices=len(topology.vertices), edges=topology.census.unique_edges,
                 contexts=0, context_edges=0, rows=0, slots=0,
                 prefixes=min(MAX_PREFIXES, 1 + 3 * len(operator.selected)),
                 boards=len(operator.selected), hands=hand_counts) > MAX_HEAP_BYTES:
        raise ValueError("Native selected-DAG prefix support heap admission rejected")
    board_records, supported_records, prefixes, active_hands = _prefix_support(operator)
    if len(prefixes) > MAX_PREFIXES:
        raise ValueError("Native selected-DAG prefix capacity exceeded")
    support_scan = 2 * (len(prefixes) + 2) * (
        hand_counts[0] * hand_counts[1] * len(operator.selected) +
        hand_counts[0] * hand_counts[1] + len(operator.selected))
    if support_scan > MAX_OPERATOR_SCAN_ENTRIES:
        raise ValueError("Native selected-DAG prefix support scan admission rejected")
    initial_heap = _heap_for(
        vertices=len(topology.vertices), edges=topology.census.unique_edges,
        contexts=0, context_edges=0, rows=0, slots=0,
        prefixes=len(prefixes), boards=len(operator.selected), hands=hand_counts)
    if initial_heap > MAX_HEAP_BYTES:
        raise ValueError("Native selected-DAG prefix support heap admission rejected")
    contexts, root_context, context_edges = _context_graph(
        topology, prefixes, active_hands, board_records, supported_records,
        hand_counts, infos, iterations)
    summary = contexts[root_context][3]
    if summary.visits > MAX_VISITS or summary.dense > MAX_DENSE_SLOTS:
        raise ValueError("Native selected-DAG logical capacity exceeded")
    if summary.rows != len(infos) or summary.slots != requested_slots:
        raise ValueError("Native selected-DAG row/action count mismatch")
    if summary.rows > MAX_ROWS:
        raise ValueError("Native selected-DAG row capacity exceeded")
    if (len(topology.vertices) > len(contexts) or topology.census.unique_edges > context_edges or
            len(contexts) > summary.visits or context_edges > summary.visits - 1):
        raise ValueError("Native selected-DAG unique/context graph dimensions disagree")
    row_keys, row_counts = _logical_rows(
        topology, root_context, contexts, prefixes, active_hands, infos, hand_counts)
    if len(row_keys) != summary.rows or sum(row_counts) != summary.slots:
        raise ValueError("Native selected-DAG preorder rows differ from context summary")
    b, p, v, e = len(operator.selected), len(prefixes), len(topology.vertices), topology.census.unique_edges
    n, q, r, s = summary.visits, summary.dense, summary.rows, summary.slots
    ce, c = context_edges, len(contexts)
    hs, width = h0 + h1, max(h0, h1)
    if (b > MAX_BOARDS or b * hs > MAX_RANK_ENTRIES or p > MAX_PREFIXES or
            v > c or e > ce or n > MAX_VISITS or q > MAX_DENSE_SLOTS or
            r > MAX_ROWS or s > MAX_ACTION_SLOTS or c > MAX_CONTEXTS or
            ce > n - 1):
        raise ValueError("Native selected-DAG dimensions exceed protocol limits")
    tc, mc, ah, oh, ch, dc = (
        summary.terminal_candidates, summary.marginal_candidates,
        summary.action_hands, summary.opponent_hands,
        summary.chance_children, summary.decision_children)
    pairs = h0 * h1
    old_setup = 128 * (n + q + s) + 10 * mc + 32 * n * b + 128 * b * pairs + 64 * p
    old_sweep = (20 * tc + 10 * mc + 10 * n * hs + 12 * s + 6 * b * n +
                 8 * ah + oh + ch * hs + 4 * dc)
    old_work = old_setup + iterations * old_sweep + r + 2 * s
    setup_extra = (256 * (v + e + c + ce + r + p * hs) +
                   128 * p * b * hs + 32 * c * b)
    sweep_extra = 16 * n * hs + 8 * q
    work = old_work + setup_extra + iterations * sweep_extra
    support_scan = 2 * (p + 2) * (pairs * b + pairs + b)
    if work > MAX_WORK or support_scan > MAX_OPERATOR_SCAN_ENTRIES:
        raise ValueError("Native selected-DAG work/support-scan admission rejected")
    heap = _heap_for(vertices=v, edges=e, contexts=c, context_edges=ce,
                     rows=r, slots=s, prefixes=p, boards=b, hands=hand_counts)
    if heap > MAX_HEAP_BYTES:
        raise ValueError("Native selected-DAG modeled heap exceeds 256 MiB")
    if array("d").itemsize != 8:
        raise RuntimeError("Native selected-DAG requires eight-byte binary64 arrays")
    receipt = {
        "version": WORK_MODEL, "vertices": v, "edges": e,
        "contexts": c, "context_edges": ce, "rows": r, "action_slots": s,
        "hands": [h0, h1], "selected_boards": b, "prefixes": p,
        "iterations": iterations, "mode": int(sys.version_info >= (3, 12)),
        "root": topology.root_id, "logical_visits": n,
        "dense_decision_hand_slots": q,
        "structural_counters": [tc, mc, ah, oh, ch, dc],
        "python_prefix_support_scan_entries": support_scan,
        "additional_operator_scan_entries": support_scan,
        "python_prefix_support_scan_limit": MAX_OPERATOR_SCAN_ENTRIES,
        "old_modeled_work_entries": old_work, "setup_extra": setup_extra,
        "sweep_extra": sweep_extra, "modeled_work_entries": work,
        "work_limit": MAX_WORK, "modeled_heap_bytes": heap,
        "heap_limit": MAX_HEAP_BYTES,
        "stored_worlds": 0, "stored_prefix_pair_edges": 0,
        "stored_expanded_native_nodes": 0, "retained_dense_decision_hand_slots": 0,
        "prefix_hand_ordinal_slots": p * hs,
        "rank_entries": b * hs, "normalizer_verification":
            "exact-positive-binary64-superaccumulator-v1",
        "scope": ("Modeled logical/storage entries and accepted input/output bounds; "
                  "not allocator bytes, Python or process RSS, or CPU-time guarantees."),
    }
    plan = NativeSelectedDagPlan(
        view, operator, iterations, int(sys.version_info >= (3, 12)),
        prefixes, active_hands,
        tuple(_Context(*context) for context in contexts), root_context,
        row_keys, row_counts, receipt, _operator_snapshot(operator),
        (id(topology), id(topology.vertices), id(view._terminals), topology.root_id, view.anchor.hex()),
    )
    return plan, dict(receipt)


def wire(plan):
    """Serialize the exact v1 DAG protocol and return logical preorder keys."""
    if type(plan) is not NativeSelectedDagPlan:
        raise TypeError("wire requires an admitted NativeSelectedDagPlan")
    operator = plan.operator
    topology = plan.view.topology
    if (_operator_snapshot(operator) != plan.operator_snapshot or
            (id(topology), id(topology.vertices), id(plan.view._terminals), topology.root_id,
             plan.view.anchor.hex()) != plan.topology_snapshot):
        raise ValueError("Native selected-DAG inputs changed after admission")
    receipt = dict(plan.receipt)
    h0, h1 = operator.hand_counts
    v, e = len(topology.vertices), topology.census.unique_edges
    # Conservative byte preflight precedes rank-vector allocation and encoding.
    estimate = (512 + 40 * (h0 + h1) +
                len(operator.selected) * (64 + 10 * (h0 + h1)) +
                128 * v + 28 * e)
    if estimate > MAX_INPUT_BYTES:
        raise ValueError("Native selected-DAG input exceeds 64 MiB")
    lines = [PROTOCOL]
    header = [receipt[key] for key in (
        "vertices", "edges", "contexts", "context_edges", "rows", "action_slots",
        "hands", "selected_boards", "prefixes", "iterations", "mode", "root",
        "logical_visits", "dense_decision_hand_slots")]
    flat_header = header[:6] + header[6] + header[7:]
    flat_header.extend(receipt["structural_counters"])
    lines.append(" ".join(map(str, flat_header)))
    lines.append(operator.normalizer.hex())
    for player in (0, 1):
        for hand, weight in zip(operator.hands[player], operator.weights[player]):
            lines.append(f"{_mask(hand)} {weight.hex()}")
    for index, (flop, turn, river) in enumerate(operator.selected):
        ranks = operator._build_rank_vectors(index)
        lines.append(f"{_mask(flop)} {_BITS[turn]} {_BITS[river]}")
        lines.append(" ".join(str(0 if rank is None else _rank_code(rank))
                               for side in ranks for rank in side))
    first = 0
    for vertex_id, vertex in enumerate(topology.vertices):
        if isinstance(vertex, DecisionVertex):
            kind, player, count, stage, terminal, payoff = (
                1, vertex.player, len(vertex.child_ids), 0, -1, 0.0)
            first_edge = first
            first += count
        elif isinstance(vertex, ChanceVertex):
            kind, player, count, stage, terminal, payoff = (
                2, -1, len(vertex.branches),
                {"flop": 1, "turn": 2, "river": 3}[vertex.street], -1, 0.0)
            first_edge = first
            first += count
        elif isinstance(vertex, TerminalVertex):
            kind, player, count, stage = 0, -1, 0, 0
            terminal = 0 if vertex.kind == "fold" else 1
            first_edge = first
            shifted = plan.view._terminals[vertex_id]
            payoff = operator.pot / 2.0 + min(shifted.contributions)
            if vertex.kind == "fold":
                payoff *= 1.0 if vertex.winner == 0 else -1.0
            if not math.isfinite(payoff) or abs(payoff) > 1e12:
                raise ValueError("Native selected-DAG terminal payoff exceeds its envelope")
        else:
            raise ValueError("Unsupported native selected-DAG vertex")
        lines.append(f"{kind} {player} {first_edge} {count} {stage} {terminal} {payoff.hex()}")
    edges = []
    for vertex_id, vertex in enumerate(topology.vertices):
        if isinstance(vertex, DecisionVertex):
            edges.extend((child, 0) for child in vertex.child_ids)
        elif isinstance(vertex, ChanceVertex):
            for token, child in vertex.branches:
                if vertex.street == "flop":
                    reveal = _mask(cards(token, 3))
                else:
                    reveal = _BITS[token]
                edges.append((child, reveal))
        elif isinstance(vertex, TerminalVertex):
            continue
    lines.extend(f"{child} {reveal}" for child, reveal in edges)
    payload = ("\n".join(lines) + "\n").encode("ascii")
    if len(payload) > MAX_INPUT_BYTES:
        raise ValueError("Native selected-DAG input exceeds 64 MiB")
    receipt["input_bytes"] = len(payload)
    return payload, list(plan.preorder_keys), receipt


def train_native_selected_dag(plan, *, executable):
    """Run the explicit helper and decode averages in logical preorder."""
    if type(plan) is not NativeSelectedDagPlan:
        raise TypeError("Native selected-DAG training requires an admitted plan")
    before = executable_identity(executable)
    if not plan.preorder_keys:
        receipt = dict(plan.receipt)
        receipt.update({"calls": 0, "identity": before,
                        "reason": "no-information-sets", **arithmetic_identity()})
        return {}, receipt
    payload, keys, receipt = wire(plan)
    try:
        process = subprocess.run([str(Path(executable).resolve(strict=True))],
                                 input=payload, capture_output=True,
                                 timeout=TIMEOUT, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Native selected-DAG trainer timed out; no fallback") from exc
    if len(process.stdout) > MAX_OUTPUT_BYTES or len(process.stderr) > MAX_STDERR_BYTES:
        raise RuntimeError("Native selected-DAG output exceeds its accepted-data bound")
    if process.returncode:
        raise RuntimeError("Native selected-DAG training failed: " +
                           process.stderr.decode("utf-8", "replace")[:4096])
    if executable_identity(executable) != before:
        raise RuntimeError("Native selected-DAG identity changed during training")
    try:
        tokens = process.stdout.decode("ascii").split()
        slots = receipt["action_slots"]
        if (len(tokens) != slots + 7 or tokens[0] != PROTOCOL or
                int(tokens[1]) != slots or tokens[-2] != "RSS"):
            raise ValueError("Malformed native selected-DAG result")
        counters = [int(value) for value in tokens[2:5]]
        tc, mc = receipt["structural_counters"][:2]
        expected_normalizations = (receipt["selected_boards"] *
                                   receipt["hands"][0] * receipt["hands"][1])
        if (any(value < 0 for value in counters) or
                counters[0] > 2 * plan.iterations * tc or
                counters[1] > plan.iterations * mc or
                counters[2] > expected_normalizations):
            raise ValueError("Native selected-DAG exceeded its admitted pair/board loops")
        native_peak = int(tokens[-1])
        if not 0 < native_peak < 1 << 64:
            raise ValueError("Invalid native selected-DAG process peak")
        values = [float.fromhex(token) for token in tokens[5:-2]]
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values):
            raise ValueError("Native selected-DAG returned invalid probabilities")
        averages = {}
        offset = 0
        for key, count in zip(keys, plan.row_counts):
            row = values[offset:offset + count]
            offset += count
            if len(row) != count or abs(math.fsum(row) - 1.0) > 1e-9:
                raise ValueError("Native selected-DAG policy row is not normalized")
            averages[key] = row
        if offset != slots:
            raise ValueError("Native selected-DAG output did not cover all action slots")
    except (UnicodeDecodeError, OverflowError, ValueError, IndexError) as exc:
        raise ValueError("Malformed native selected-DAG result") from exc
    receipt.update({
        "calls": 1, "terminal_pair_board_checks": counters[0],
        "marginal_pair_board_checks": counters[1],
        "normalization_pair_board_checks": counters[2],
        "identity": before, "native_process_lifetime_peak_working_set_bytes": native_peak,
        **arithmetic_identity(),
    })
    return averages, receipt
