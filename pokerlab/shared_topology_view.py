"""Solve-local lazy views of shared public topology for the existing CFR kernel.

Only topology is shared. Every cursor carries its complete visible history;
information-set keys and average-strategy rows remain distinct. The compiler
bridge still consumes the literal prepared tree, so this is not a construction
peak-memory improvement.
"""
from array import array
from collections.abc import Mapping, Sequence
from math import frexp, isfinite, ldexp

from .river_tree import _Terminal
from .shared_public_topology import (
    SharedPublicTopology, DecisionVertex, ChanceVertex, TerminalVertex,
)


MAX_HISTORY_LOOKUP_ENTRIES = 500_000_000


class _Children(Sequence):
    __slots__ = ("cursor",)

    def __init__(self, cursor):
        self.cursor = cursor

    def __len__(self):
        return len(self.cursor.vertex.child_ids)

    def __getitem__(self, index):
        if type(index) is not int:
            raise TypeError("Lazy public children require an integer index.")
        vertex = self.cursor.vertex
        child = vertex.child_ids[index]
        return self.cursor.view._cursor(
            child, self.cursor.history + (vertex.actions[index].token,))


class _Branches(Mapping):
    __slots__ = ("cursor",)

    def __init__(self, cursor):
        self.cursor = cursor

    def __len__(self):
        return len(self.cursor.vertex.branches)

    def __iter__(self):
        return (token for token, _child in self.cursor.vertex.branches)

    def __getitem__(self, token):
        for candidate, child in self.cursor.vertex.branches:
            if candidate == token:
                return self.cursor.view._cursor(
                    child, self.cursor.history + (f"{self.cursor.vertex.street}@{token}",))
        raise KeyError(token)

    def items(self):
        for token, child in self.cursor.vertex.branches:
            yield token, self.cursor.view._cursor(
                child, self.cursor.history + (f"{self.cursor.vertex.street}@{token}",))


class DecisionCursor:
    __slots__ = ("view", "vertex_id", "history")

    def __init__(self, view, vertex_id, history):
        self.view, self.vertex_id, self.history = view, vertex_id, history

    @property
    def vertex(self):
        return self.view.topology.vertices[self.vertex_id]

    @property
    def player(self):
        return self.vertex.player

    @property
    def actions(self):
        return self.vertex.actions

    @property
    def children(self):
        return _Children(self)


class ChanceCursor:
    __slots__ = ("view", "vertex_id", "history")

    def __init__(self, view, vertex_id, history):
        self.view, self.vertex_id, self.history = view, vertex_id, history

    @property
    def vertex(self):
        return self.view.topology.vertices[self.vertex_id]

    @property
    def branches(self):
        return _Branches(self)

    @property
    def street(self):
        return self.vertex.street

    @property
    def card_index(self):
        return self.vertex.card_index


class SharedPublicView:
    """An admitted compiler snapshot and O(unique terminals) shifted payoffs."""
    __slots__ = ("topology", "anchor", "_terminals")

    def __init__(self, topology):
        if type(topology) is not SharedPublicTopology:
            raise TypeError("A compiled shared public topology is required.")
        self.topology = topology
        minimum = None
        for vertex in topology.vertices:
            if isinstance(vertex, TerminalVertex):
                matched = min(vertex.contributions)
                minimum = matched if minimum is None else min(minimum, matched)
        if minimum is None or not isfinite(minimum) or minimum <= 0:
            raise ValueError("Shared public training requires positive terminal contributions.")
        # Identical to the retained literal view's anchor and subtraction.
        self.anchor = ldexp(1.0, frexp(minimum)[1] - 1)
        self._terminals = tuple(
            _Terminal(v.kind, tuple(x - self.anchor for x in v.contributions), v.winner)
            if isinstance(v, TerminalVertex) else None for v in topology.vertices)

    def _cursor(self, vertex_id, history):
        vertex = self.topology.vertices[vertex_id]
        if isinstance(vertex, TerminalVertex):
            return self._terminals[vertex_id]
        if isinstance(vertex, ChanceVertex):
            return ChanceCursor(self, vertex_id, history)
        if isinstance(vertex, DecisionVertex):
            return DecisionCursor(self, vertex_id, history)
        raise ValueError("Unsupported shared public vertex.")

    @property
    def root(self):
        return self._cursor(self.topology.root_id, self.topology.initial_history)


def layout_census_shared(view, infos, hand_counts, iterations):
    """Validate every logical row and charge semantic-history lookup work."""
    from .packed_operator_cfr import (
        MAX_ACTION_SLOTS, MAX_DENSE_DECISION_HAND_SLOTS, MAX_LAYOUT_LOOP_ENTRIES,
        MAX_PUBLIC_STATES, MAX_DEPTH,
    )
    if type(view) is not SharedPublicView:
        raise TypeError("Shared layout requires its compiled public view.")
    if type(iterations) is not int or not 10 <= iterations <= 10_000:
        raise ValueError("Shared packed CFR+ requires 10-10,000 iterations.")
    if len(hand_counts) != 2 or any(type(h) is not int or not 1 <= h <= 1326 for h in hand_counts):
        raise ValueError("Shared layout requires two bounded hand dimensions.")
    slots = history_entries = history_bytes = 0
    for key, count in infos.items():
        if (type(key) is not tuple or len(key) != 3 or type(key[0]) is not int or
                key[0] not in (0, 1) or type(key[1]) is not int or
                not 0 <= key[1] < hand_counts[key[0]] or type(key[2]) is not tuple or
                any(type(token) is not str for token in key[2]) or
                type(count) is not int or count < 1):
            raise ValueError("Malformed shared information-set identity or menu.")
        slots += count
        history_entries += len(key[2])
        history_bytes += sum(len(token.encode("utf-8")) for token in key[2])
        if slots > MAX_ACTION_SLOTS or history_bytes > MAX_HISTORY_LOOKUP_ENTRIES:
            raise ValueError("Shared information/action/history capacity exceeded.")
    remaining = set(infos)
    states = dense = decisions = decision_width = lookup_work = 0
    maximum_actions = 1
    for occurrence in view.topology.iter_occurrences():
        node = view.topology.vertices[occurrence.vertex_id]
        depth, history = occurrence.depth, occurrence.history
        states += 1
        if states > MAX_PUBLIC_STATES or depth > MAX_DEPTH:
            raise ValueError("Shared logical state/depth capacity exceeded.")
        if isinstance(node, TerminalVertex):
            continue
        if isinstance(node, ChanceVertex):
            continue
        if type(node) is not DecisionVertex or not node.child_ids:
            raise ValueError("Malformed shared decision cursor.")
        player, count = node.player, len(node.child_ids)
        maximum_actions = max(maximum_actions, count)
        dense += hand_counts[player]
        decisions += 1
        decision_width += count + 1
        lookup_work += hand_counts[player] * (len(history) + 3)
        if dense > MAX_DENSE_DECISION_HAND_SLOTS:
            raise ValueError("Shared logical decision/hand capacity exceeded.")
        for hand in range(hand_counts[player]):
            key = (player, hand, history)
            if key in infos:
                if infos[key] != count or key not in remaining:
                    raise ValueError("Shared information-set menu/history occurrence mismatch.")
                remaining.remove(key)
    if remaining:
        raise ValueError("Shared information sets do not match complete logical topology.")
    vector_entries = 12 * sum(hand_counts) * (decision_width + states)
    loops = iterations * (32 * slots + vector_entries) + 8 * slots + 4 * dense + 4 * states
    # Two regret traversals and one averaging traversal per iteration, plus
    # profile/two BR diagnostics, coverage and complete row construction.
    history_work = ((3 * iterations + 3 * maximum_actions + 16) * lookup_work +
                    8 * history_entries + history_bytes)
    if loops > MAX_LAYOUT_LOOP_ENTRIES or history_work > MAX_HISTORY_LOOKUP_ENTRIES:
        raise ValueError("Shared requested layout/history loop capacity exceeded.")
    if array("d").itemsize != 8:
        raise RuntimeError("Shared packed storage requires eight-byte binary64 doubles.")
    return {"version": "selected-shared-topology-packed-v1", "information_sets": len(infos),
            "action_slots": slots, "public_states": states, "decisions": decisions,
            "dense_decision_hand_slots": dense, "retained_dense_lookup_slots": 0,
            "semantic_row_lookup_entries": len(infos),
            "semantic_row_history_token_entries": history_entries,
            "semantic_row_history_token_bytes": history_bytes,
            "numeric_buffers": 4, "numeric_buffer_bytes": 4 * slots * 8,
            "dense_lookup_payload_bytes": 0,
            "row_offset_and_count_payload_bytes": 2 * len(infos) * array("I").itemsize,
            "per_sweep_vector_entry_bound": vector_entries,
            "requested_layout_loop_entries": loops, "layout_loop_limit": MAX_LAYOUT_LOOP_ENTRIES,
            "history_lookup_work_entries": history_work,
            "history_lookup_work_limit": MAX_HISTORY_LOOKUP_ENTRIES,
            "maximum_actions": maximum_actions,
            "lazy_training_and_diagnostic_cursor_bound": (3 * iterations + 4) * states,
            "setup_occurrence_walks": 3,
            "retained_terminal_records": sum(t is not None for t in view._terminals),
            "scope": "Logical work and scalar payloads; original bridge construction, history keys, metadata, dictionaries, cursors and complete output remain separate memory costs."}
