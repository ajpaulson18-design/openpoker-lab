"""History-free immutable structural DAG for bounded public poker trees.

This compiler is a representation bridge, not a replacement builder: callers
must already own a materialized source tree.  The returned DAG stores local
transitions only.  :meth:`SharedPublicTopology.iter_occurrences` reconstructs
each logical history on demand and never retains the expanded tree or a table
of histories.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import math
import struct
from numbers import Real

from .cards import DECK
from .postflop_solver import _Chance
from .river_tree import _Action, _Node, _Terminal


@dataclass(frozen=True, slots=True)
class TopologyLimits:
    """Separate upper bounds for compiler work and retained structure."""

    max_source_nodes: int = 250_000
    max_source_edges: int = 1_000_000
    max_vertices: int = 250_000
    max_edges: int = 1_000_000
    max_logical_visits: int = 250_000
    max_depth: int = 512
    max_history_token_work: int = 50_000_000
    max_history_token_bytes: int = 16_000_000
    max_build_scratch_entries: int = 250_000
    max_support_prefixes: int = 250_000

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer.")


@dataclass(frozen=True, slots=True)
class ActionRecord:
    """Immutable whole-hand action fields; numeric values retain binary64 bits."""

    name: str
    amount: float
    raise_to: float
    full_raise: bool
    token: str


@dataclass(frozen=True, slots=True)
class DecisionVertex:
    """A global-player decision and its ordered action/child transitions."""

    player: int
    actions: tuple[ActionRecord, ...]
    child_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ChanceVertex:
    """A chance node whose branch tokens are raw cards or canonical flops."""

    street: str
    card_index: int
    branches: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class TerminalVertex:
    """A settled public state; path/history remains an occurrence property."""

    kind: str
    contributions: tuple[float, float]
    winner: int | None


TopologyVertex = DecisionVertex | ChanceVertex | TerminalVertex


@dataclass(frozen=True, slots=True)
class PrefixStorageCensus:
    """Information-row/action-slot census for one public board prefix."""

    board_prefix: tuple[str, ...]
    hand_counts: tuple[int, int]
    decision_occurrences: int
    information_rows: int
    action_slots: int


@dataclass(frozen=True, slots=True)
class TopologyCensus:
    """Logical traversal and unique retained DAG counts."""

    unique_source_nodes: int
    unique_source_edges: int
    unique_vertices: int
    unique_edges: int
    expanded_logical_visits: int
    decision_occurrences: int
    chance_occurrences: int
    terminal_occurrences: int
    logical_history_token_work: int
    logical_history_token_bytes: int
    maximum_depth: int
    build_scratch_peak_entries: int
    information_rows: int | None
    action_slots: int | None
    prefix_storage: tuple[PrefixStorageCensus, ...]


@dataclass(frozen=True, slots=True)
class TopologyOccurrence:
    """One streamed logical occurrence, with history reconstructed on demand."""

    vertex_id: int
    kind: str
    history: tuple[str, ...]
    depth: int


@dataclass(frozen=True, slots=True)
class _SourceSnapshot:
    source: object
    kind: str
    history: tuple[str, ...] | None
    player: int | None = None
    actions: tuple[ActionRecord, ...] = ()
    children: tuple[object, ...] = ()
    street: str | None = None
    card_index: int | None = None
    branches: tuple[tuple[str, object], ...] = ()
    terminal_kind: str | None = None
    contributions: tuple[float, float] | None = None
    winner: int | None = None


@dataclass(slots=True)
class _WalkFrame:
    source_id: int
    depth: int
    restore_history_length: int
    children: tuple[tuple[str, object], ...]
    next_child: int = 0
    entered: bool = False


@dataclass(slots=True)
class _CompileFrame:
    source_id: int
    next_child: int = 0
    entered: bool = False


@dataclass(frozen=True, slots=True)
class SharedPublicTopology:
    """Immutable interned DAG plus a bounded streaming logical-tree cursor."""

    vertices: tuple[TopologyVertex, ...]
    root_id: int
    initial_history: tuple[str, ...]
    census: TopologyCensus
    limits: TopologyLimits

    def iter_occurrences(self):
        """Yield every logical occurrence in source order without retaining paths.

        The mutable path buffer and explicit DFS stack are bounded by the
        compiler's maximum depth.  A fresh history tuple is yielded for each
        occurrence; consumers decide whether to retain it.
        """
        history = list(self.initial_history)
        stack = [_WalkFrame(self.root_id, 0, len(history), ())]
        while stack:
            frame = stack[-1]
            vertex = self.vertices[frame.source_id]
            if not frame.entered:
                frame.entered = True
                if isinstance(vertex, DecisionVertex):
                    kind = "decision"
                elif isinstance(vertex, ChanceVertex):
                    kind = "chance"
                else:
                    kind = "terminal"
                yield TopologyOccurrence(
                    frame.source_id, kind, tuple(history), frame.depth)
            if isinstance(vertex, DecisionVertex):
                if frame.next_child < len(vertex.child_ids):
                    index = frame.next_child
                    frame.next_child += 1
                    restore = len(history)
                    history.append(vertex.actions[index].token)
                    stack.append(_WalkFrame(
                        vertex.child_ids[index], frame.depth + 1, restore, ()))
                    if len(stack) > self.limits.max_build_scratch_entries:
                        raise RuntimeError("Topology cursor exceeded its admitted stack bound.")
                    continue
            elif isinstance(vertex, ChanceVertex):
                if frame.next_child < len(vertex.branches):
                    token, child_id = vertex.branches[frame.next_child]
                    frame.next_child += 1
                    restore = len(history)
                    history.append(f"{vertex.street}@{token}")
                    stack.append(_WalkFrame(
                        child_id, frame.depth + 1, restore, ()))
                    if len(stack) > self.limits.max_build_scratch_entries:
                        raise RuntimeError("Topology cursor exceeded its admitted stack bound.")
                    continue
            popped = stack.pop()
            del history[popped.restore_history_length:]

    def iter_prefix_storage(self, hand_support_counts_by_prefix):
        """Stream per-board-prefix row/action counts from supplied hand counts.

        ``hand_support_counts_by_prefix`` maps a tuple of revealed cards to
        ``(SB hand count, BB hand count)``.  These counts do not validate
        chance support or physical partitions.  Missing prefixes reject rather
        than silently assuming a hand is live.
        """
        counts = _validate_support_counts(
            hand_support_counts_by_prefix, self.limits.max_support_prefixes)
        yield from _iter_prefix_storage(
            self.vertices, self.root_id, self.initial_history, self.limits, counts)


def compile_shared_public_topology(root, *, limits=TopologyLimits(),
                                   hand_support_counts_by_prefix=None):
    """Compile a validated ``_Node``/``_Chance``/``_Terminal`` tree to a DAG.

    Source snapshots, expanded logical visits, DAG vertices/edges, history-token
    work and traversal-stack entries are independently bounded.  Source node
    identity is only a compilation aid: history-free structural equality
    interns vertices, while every occurrence is still visited and counted.
    """
    if not isinstance(limits, TopologyLimits):
        raise TypeError("limits must be a TopologyLimits instance.")
    support_counts = (_validate_support_counts(
        hand_support_counts_by_prefix, limits.max_support_prefixes)
        if hand_support_counts_by_prefix is not None else None)

    snapshots: dict[int, _SourceSnapshot] = {}
    unique_source_edges = 0
    logical_visits = decisions = chances = terminals = 0
    history_token_work = history_token_bytes = 0
    maximum_depth = build_scratch_peak = 0
    stack: list[_WalkFrame] = []
    active: set[int] = set()

    def snapshot_for(node):
        nonlocal unique_source_edges
        source_id = id(node)
        existing = snapshots.get(source_id)
        if existing is not None:
            if existing.source is not node:
                raise ValueError("Source object identity changed during compilation.")
            return existing
        if len(snapshots) >= limits.max_source_nodes:
            raise ValueError("Public topology exceeds its source-node limit.")
        if isinstance(node, _Node):
            degree = len(node.children)
        elif isinstance(node, _Chance):
            degree = len(node.branches)
        elif isinstance(node, _Terminal):
            degree = 0
        else:
            raise TypeError("Public topology accepts only _Node, _Chance or _Terminal sources.")
        if unique_source_edges + degree > limits.max_source_edges:
            raise ValueError("Public topology exceeds its source-edge limit.")
        projected_scratch = len(snapshots) + 1 + len(stack) + len(active)
        if projected_scratch > limits.max_build_scratch_entries:
            raise ValueError("Public topology exceeds its build-scratch limit.")
        nonlocal build_scratch_peak
        build_scratch_peak = max(build_scratch_peak, projected_scratch)
        snap = _snapshot_node(node)
        # The source is mutable. Charge the captured child sequence itself,
        # even if its length changed after the fast pre-snapshot check.
        captured_degree = len(snap.children) if snap.kind == "decision" else len(snap.branches)
        if unique_source_edges + captured_degree > limits.max_source_edges:
            raise ValueError("Public topology exceeds its source-edge limit.")
        unique_source_edges += captured_degree
        snapshots[source_id] = snap
        return snap

    root_snapshot = snapshot_for(root)
    initial_history = root_snapshot.history if root_snapshot.history is not None else ()
    if type(initial_history) is not tuple:
        raise ValueError("Root history must be an immutable token tuple.")
    _validate_history_tokens(initial_history)
    _board_prefix(initial_history)
    history = list(initial_history)
    history_token_work = len(history)
    history_token_bytes = sum(_token_bytes(token) for token in history)
    _check_history_work(history_token_work, history_token_bytes, limits)

    def snapshot_children(snap):
        return snap.children if snap.kind == "decision" else snap.branches

    root_id = id(root)
    stack.append(_WalkFrame(root_id, 0, len(history), snapshot_children(root_snapshot)))
    while stack:
        build_scratch_peak = max(build_scratch_peak, len(stack) + len(active))
        if build_scratch_peak > limits.max_build_scratch_entries:
            raise ValueError("Public topology exceeds its build-scratch limit.")
        frame = stack[-1]
        snap = snapshots[frame.source_id]
        if not frame.entered:
            if frame.source_id in active:
                raise ValueError("Public topology source contains a cycle.")
            active.add(frame.source_id)
            frame.entered = True
            logical_visits += 1
            if logical_visits > limits.max_logical_visits:
                raise ValueError("Public topology exceeds its logical-visit limit.")
            if frame.depth > limits.max_depth:
                raise ValueError("Public topology exceeds its logical-depth limit.")
            maximum_depth = max(maximum_depth, frame.depth)
            if snap.history is not None and tuple(history) != snap.history:
                raise ValueError("Source node history differs from its reconstructed public path.")
            if snap.history is not None:
                _board_prefix(snap.history)
            if snap.kind == "decision":
                decisions += 1
            elif snap.kind == "chance":
                chances += 1
            else:
                terminals += 1
            history_token_work += len(history)
            history_token_bytes += sum(_token_bytes(token) for token in history)
            _check_history_work(history_token_work, history_token_bytes, limits)
        child_count = len(frame.children)
        if frame.next_child < child_count:
            if snap.kind == "decision":
                token = snap.actions[frame.next_child].token
                child = frame.children[frame.next_child]
            else:
                raw_token, child = frame.children[frame.next_child]
                token = f"{snap.street}@{raw_token}"
            frame.next_child += 1
            child_id = id(child)
            if child_id in active:
                raise ValueError("Public topology source contains a cycle.")
            child_snap = snapshot_for(child)
            restore = len(history)
            history.append(token)
            history_token_work += 1
            history_token_bytes += _token_bytes(token)
            _check_history_work(history_token_work, history_token_bytes, limits)
            stack.append(_WalkFrame(
                child_id, frame.depth + 1, restore,
                snapshot_children(child_snap)))
            continue
        active.remove(frame.source_id)
        popped = stack.pop()
        del history[popped.restore_history_length:]

    vertex_values: list[TopologyVertex] = []
    interned: dict[tuple, int] = {}
    source_to_vertex: dict[int, int] = {}
    dag_edges = 0
    compile_active: set[int] = set()
    compile_stack = [_CompileFrame(root_id)]
    while compile_stack:
        current_scratch = (len(snapshots) + len(source_to_vertex) + len(interned) +
                           len(compile_stack) + len(compile_active))
        build_scratch_peak = max(build_scratch_peak, current_scratch)
        if current_scratch > limits.max_build_scratch_entries:
            raise ValueError("Public topology exceeds its build-scratch limit.")
        frame = compile_stack[-1]
        source_id = frame.source_id
        if source_id in source_to_vertex:
            compile_stack.pop()
            continue
        snap = snapshots[source_id]
        # Index the snapshotted branch pairs directly. Rebuilding a tuple of
        # all chance children once per child would introduce quadratic work.
        child_entries = snap.children if snap.kind == "decision" else snap.branches
        if not frame.entered:
            if source_id in compile_active:
                raise ValueError("Public topology source contains a cycle.")
            compile_active.add(source_id)
            frame.entered = True
        while frame.next_child < len(child_entries) and id(
                child_entries[frame.next_child] if snap.kind == "decision"
                else child_entries[frame.next_child][1]) in source_to_vertex:
            frame.next_child += 1
        if frame.next_child < len(child_entries):
            child = (child_entries[frame.next_child] if snap.kind == "decision"
                     else child_entries[frame.next_child][1])
            frame.next_child += 1
            child_id = id(child)
            if child_id in compile_active:
                raise ValueError("Public topology source contains a cycle.")
            if child_id not in snapshots:
                raise ValueError("Source graph changed after its bounded snapshot.")
            if (len(snapshots) + len(source_to_vertex) + len(interned) +
                    len(compile_stack) + 1 + len(compile_active)) > limits.max_build_scratch_entries:
                raise ValueError("Public topology exceeds its build-scratch limit.")
            compile_stack.append(_CompileFrame(child_id))
            continue

        if snap.kind == "decision":
            child_ids = tuple(source_to_vertex[id(child)] for child in snap.children)
            key = ("decision", snap.player,
                   tuple(_action_key(action) for action in snap.actions), child_ids)
            vertex = DecisionVertex(snap.player, snap.actions, child_ids)
        elif snap.kind == "chance":
            child_ids = tuple(source_to_vertex[id(child)] for _, child in snap.branches)
            branches = tuple((token, child_id)
                             for (token, _), child_id in zip(snap.branches, child_ids))
            key = ("chance", snap.street, snap.card_index, branches)
            vertex = ChanceVertex(snap.street, snap.card_index, branches)
        else:
            key = ("terminal", snap.terminal_kind,
                   tuple(_float_bits(value) for value in snap.contributions), snap.winner)
            vertex = TerminalVertex(snap.terminal_kind, snap.contributions, snap.winner)
        vertex_id = interned.get(key)
        if vertex_id is None:
            if len(vertex_values) >= limits.max_vertices:
                raise ValueError("Public topology exceeds its unique-vertex limit.")
            degree = _vertex_degree(vertex)
            if dag_edges + degree > limits.max_edges:
                raise ValueError("Public topology exceeds its unique-edge limit.")
            projected_scratch = (len(snapshots) + len(source_to_vertex) +
                                 len(interned) + 1 + len(compile_stack) +
                                 len(compile_active))
            if projected_scratch > limits.max_build_scratch_entries:
                raise ValueError("Public topology exceeds its build-scratch limit.")
            vertex_id = len(vertex_values)
            interned[key] = vertex_id
            vertex_values.append(vertex)
            dag_edges += degree
        elif (len(snapshots) + len(source_to_vertex) + len(interned) +
              1 + len(compile_stack) + len(compile_active)) > limits.max_build_scratch_entries:
            raise ValueError("Public topology exceeds its build-scratch limit.")
        source_to_vertex[source_id] = vertex_id
        compile_active.remove(source_id)
        compile_stack.pop()

    dag_edges = sum(_vertex_degree(vertex) for vertex in vertex_values)
    if dag_edges > limits.max_edges:
        raise ValueError("Public topology exceeds its unique-edge limit.")
    if support_counts is None:
        prefix_storage = ()
        information_rows = action_slots = None
    else:
        prefix_storage = tuple(_iter_prefix_storage(
            tuple(vertex_values), source_to_vertex[root_id], initial_history,
            limits, support_counts))
        information_rows = sum(item.information_rows for item in prefix_storage)
        action_slots = sum(item.action_slots for item in prefix_storage)
    _revalidate_sources(snapshots)
    census = TopologyCensus(
        len(snapshots), unique_source_edges, len(vertex_values), dag_edges,
        logical_visits, decisions, chances, terminals,
        history_token_work, history_token_bytes, maximum_depth,
        build_scratch_peak, information_rows, action_slots, prefix_storage,
    )
    return SharedPublicTopology(
        tuple(vertex_values), source_to_vertex[root_id], initial_history,
        census, limits,
    )


def _snapshot_node(node):
    if isinstance(node, _Node):
        history = _snapshot_history(node.history)
        if type(node.player) is not int or node.player not in (0, 1):
            raise ValueError("Decision player must be global player 0 or 1.")
        if type(node.actions) is not tuple or type(node.children) is not tuple:
            raise ValueError("Decision actions and children must be immutable tuples.")
        if not node.actions or len(node.actions) != len(node.children):
            raise ValueError("Decision actions and children must be nonempty and aligned.")
        actions = tuple(_snapshot_action(action) for action in node.actions)
        return _SourceSnapshot(node, "decision", history, node.player,
                               actions, node.children)
    if isinstance(node, _Chance):
        history = _snapshot_history(node.history)
        if type(node.card_index) is not int or node.card_index < 0:
            raise ValueError("Chance card_index must be a nonnegative integer.")
        if type(node.street) is not str or node.street not in ("flop", "turn", "river"):
            raise ValueError("Chance street must be flop, turn or river.")
        if type(node.branches) is not dict or not node.branches:
            raise ValueError("Chance branches must be a nonempty ordered dictionary.")
        branches = tuple(node.branches.items())
        if any(type(token) is not str or not token for token, _ in branches):
            raise ValueError("Chance branch tokens must be nonempty strings.")
        for token, _ in branches:
            _validate_chance_token(node.street, token)
        return _SourceSnapshot(node, "chance", history,
                               street=node.street, card_index=node.card_index,
                               branches=branches)
    if isinstance(node, _Terminal):
        if type(node.kind) is not str or node.kind not in ("fold", "showdown"):
            raise ValueError("Terminal kind must be fold or showdown.")
        if type(node.contributions) is not tuple or len(node.contributions) != 2:
            raise ValueError("Terminal contributions must be a two-value tuple.")
        contributions = tuple(_finite_float(value, "Terminal contribution")
                              for value in node.contributions)
        if any(value < 0 for value in contributions):
            raise ValueError("Terminal contributions cannot be negative.")
        if node.winner is not None and (type(node.winner) is not int or node.winner not in (0, 1)):
            raise ValueError("Terminal winner must be player 0, player 1 or None.")
        if node.kind == "fold" and node.winner is None:
            raise ValueError("A fold terminal requires a winner.")
        if node.kind == "showdown" and node.winner is not None:
            raise ValueError("A showdown terminal cannot have a declared winner.")
        return _SourceSnapshot(node, "terminal", None,
                               terminal_kind=node.kind,
                               contributions=contributions, winner=node.winner)
    raise TypeError("Public topology accepts only _Node, _Chance or _Terminal sources.")


def _snapshot_action(action):
    if not isinstance(action, _Action):
        raise TypeError("Decision actions must be _Action instances.")
    if type(action.name) is not str or not action.name:
        raise ValueError("Action name must be a nonempty string.")
    if type(action.full_raise) is not bool:
        raise ValueError("Action full_raise must be boolean.")
    amount = _finite_float(action.amount, "Action amount")
    raise_to = _finite_float(action.raise_to, "Action raise_to")
    if amount < 0 or raise_to < 0:
        raise ValueError("Action amounts and targets cannot be negative.")
    token = action.token
    if type(token) is not str or not token:
        raise ValueError("Action token must be a nonempty string.")
    return ActionRecord(action.name, amount, raise_to, action.full_raise, token)


def _snapshot_history(history):
    if type(history) is not tuple:
        raise ValueError("Source public history must be an immutable token tuple.")
    _validate_history_tokens(history)
    return history


def _validate_history_tokens(history):
    if any(type(token) is not str or not token for token in history):
        raise ValueError("Public histories must contain nonempty string tokens.")


def _finite_float(value, label):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite real number.")
    try:
        converted = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite real number.") from exc
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be a finite real number.")
    return converted


def _float_bits(value):
    return struct.pack("!d", value)


def _action_key(action):
    return (action.name, _float_bits(action.amount), _float_bits(action.raise_to),
            action.full_raise, action.token)


def _token_bytes(token):
    try:
        return len(token.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError("Public history tokens must be UTF-8 encodable.") from exc


def _check_history_work(tokens, byte_count, limits):
    if tokens > limits.max_history_token_work:
        raise ValueError("Public topology exceeds its history-token work limit.")
    if byte_count > limits.max_history_token_bytes:
        raise ValueError("Public topology exceeds its history-token byte limit.")


def _revalidate_sources(snapshots):
    for snap in snapshots.values():
        try:
            current = _snapshot_node(snap.source)
        except Exception as exc:
            raise ValueError("Source tree mutated during topology compilation.") from exc
        if _snapshot_signature(current) != _snapshot_signature(snap):
            raise ValueError("Source tree mutated during topology compilation.")


def _snapshot_signature(snap):
    if snap.kind == "decision":
        return (snap.kind, snap.history, snap.player,
                tuple(_action_key(action) for action in snap.actions),
                tuple(id(child) for child in snap.children))
    if snap.kind == "chance":
        return (snap.kind, snap.history, snap.street, snap.card_index,
                tuple((token, id(child)) for token, child in snap.branches))
    return (snap.kind, snap.terminal_kind,
            tuple(_float_bits(value) for value in snap.contributions), snap.winner)


def _vertex_degree(vertex):
    if isinstance(vertex, DecisionVertex):
        return len(vertex.child_ids)
    if isinstance(vertex, ChanceVertex):
        return len(vertex.branches)
    return 0


def _iter_prefix_storage(vertices, root_id, initial_history, limits, counts):
    totals: dict[tuple[str, ...], list[int]] = {
        prefix: [0, 0, 0] for prefix in counts
    }
    topology = SharedPublicTopology(
        vertices, root_id, initial_history,
        TopologyCensus(0, 0, len(vertices), 0, 0, 0, 0, 0, 0, 0, 0, 0,
                       None, None, ()),
        limits,
    )
    for occurrence in topology.iter_occurrences():
        if occurrence.kind != "decision":
            continue
        vertex = vertices[occurrence.vertex_id]
        prefix = _board_prefix(occurrence.history)
        support = counts.get(prefix)
        if support is None:
            raise ValueError(f"Missing private-hand support census for board prefix {prefix!r}.")
        row = totals[prefix]
        row[0] += 1
        hands = support[vertex.player]
        row[1] += hands
        row[2] += hands * len(vertex.actions)
    for prefix, support in counts.items():
        decisions, rows, slots = totals[prefix]
        yield PrefixStorageCensus(prefix, support, decisions, rows, slots)


def _validate_support_counts(hand_support_counts_by_prefix, max_prefixes):
    if not isinstance(hand_support_counts_by_prefix, Mapping):
        raise TypeError("hand_support_counts_by_prefix must be a mapping.")
    copied = {}
    for prefix, value in hand_support_counts_by_prefix.items():
        if len(copied) >= max_prefixes:
            raise ValueError("Private-support prefix census exceeds its prefix limit.")
        if type(prefix) is not tuple or len(prefix) > 5:
            raise ValueError("Board prefixes must be tuples of zero through five cards.")
        if any(type(card) is not str or card not in DECK for card in prefix):
            raise ValueError("Board-prefix entries must be valid card tokens.")
        if len(set(prefix)) != len(prefix):
            raise ValueError("Board prefixes cannot repeat cards.")
        if type(value) is not tuple or len(value) != 2 or any(
                type(count) is not int or count < 0 for count in value):
            raise ValueError("Private-support values must be (SB count, BB count) tuples.")
        copied[prefix] = value
    return dict(sorted(copied.items()))


def _board_prefix(history):
    board = []
    for token in history:
        if token.startswith("flop@"):
            cards = token[5:]
            if len(cards) != 6:
                raise ValueError("A flop history token must contain exactly three cards.")
            board.extend(cards[offset:offset + 2] for offset in (0, 2, 4))
        elif token.startswith("turn@"):
            card = token[5:]
            if len(card) != 2:
                raise ValueError("A turn history token must contain exactly one card.")
            board.append(card)
        elif token.startswith("river@"):
            card = token[6:]
            if len(card) != 2:
                raise ValueError("A river history token must contain exactly one card.")
            board.append(card)
    if any(card not in DECK for card in board) or len(set(board)) != len(board):
        raise ValueError("Reconstructed public board contains invalid or repeated cards.")
    return tuple(board)


def _validate_chance_token(street, token):
    expected_cards = 3 if street == "flop" else 1
    if len(token) != 2 * expected_cards:
        raise ValueError(f"A {street} chance branch token has the wrong card count.")
    cards = tuple(token[index:index + 2] for index in range(0, len(token), 2))
    if any(card not in DECK for card in cards) or len(set(cards)) != len(cards):
        raise ValueError(f"A {street} chance branch token contains invalid or repeated cards.")
