"""Fixed full-deck raised-turn fixture census and advisory work forecasts.

Physical pair/rivers and their masses are built here with exact fractions.
Public betting-tree structure comes from the pinned production tree builder;
this census performs no rank evaluation or training and is not an independent
tree oracle. Forecast labels describe reference work envelopes only and do not
make production admission decisions.
"""
from dataclasses import asdict, dataclass
from fractions import Fraction
import hashlib
import json

from pokerlab.cards import DECK, cards
from pokerlab.postflop_solver import (
    _Chance,
    _Node,
    _Terminal,
    _build_postflop_tree,
)
from pokerlab.river_config import RiverConfig


FIXTURE = {
    "id": "full-deck-raised-turn-v1",
    "board": "Js8d4c2h",
    "oop": "AsAh:0.5,KsKh:1",
    "ip": "AcAd:1,KcKd:0.75",
    "config": {
        "pot": 100.0,
        "effective_stack": 220.0,
        "bet_sizes": [0.5],
        "raise_sizes": [0.5],
        "max_raises": 1,
        "include_all_in": False,
    },
}
FORECAST_ITERATIONS = (100, 1000, 1500)
REFERENCE_WORK_CAP = 30_000_000
REFERENCE_BOUNDARIES = {
    "materialized": {
        "last_within_cap_iterations": 1775,
        "first_over_cap_iterations": 1776,
        "first_over_cap_work": 30_007_296,
    },
    "matrix-free": {
        "last_within_cap_iterations": 1644,
        "first_over_cap_iterations": 1645,
        "first_over_cap_work": 30_013_164,
    },
}


@dataclass(frozen=True)
class RangeHand:
    cards: tuple[str, str]
    weight: Fraction


@dataclass(frozen=True)
class PhysicalPair:
    oop_index: int
    ip_index: int
    oop_hand: str
    ip_hand: str
    raw_weight: Fraction
    normalized_mass: Fraction
    per_river_weight: Fraction
    rivers: tuple[str, ...]


@dataclass(frozen=True)
class PhysicalWorld:
    oop_index: int
    ip_index: int
    river: str
    weight: Fraction


@dataclass(frozen=True)
class PhysicalWorldCensus:
    board: tuple[str, ...]
    oop_range: tuple[RangeHand, ...]
    ip_range: tuple[RangeHand, ...]
    pairs: tuple[PhysicalPair, ...]
    worlds: tuple[PhysicalWorld, ...]
    global_mass: Fraction


@dataclass(frozen=True)
class Forecast:
    backend: str
    iterations: int
    work: int
    reference_cap: int
    within_reference_cap: bool
    reference_cap_label: str


@dataclass(frozen=True)
class Census:
    fixture_id: str
    board: str
    pairs: int
    worlds: int
    rivers_per_pair: tuple[int, ...]
    physical_pair_masses: tuple[tuple[str, str, str, str], ...]
    global_physical_mass: Fraction
    public_candidates: int
    reachable_rivers: int
    public_nodes: int
    decisions: int
    information_rows: int
    depth: int
    visited_decisions_per_world: int
    max_private_hands: int
    action_tokens: tuple[str, ...]
    public_tree_sha256: str
    forecasts: tuple[Forecast, ...]


def _weighted_combo_tokens(expression):
    """Parse the fixture's exact-card weighted range tokens."""
    result = []
    for token in expression.split(","):
        hand_text, separator, weight_text = token.strip().partition(":")
        if not separator or len(hand_text) != 4:
            raise ValueError("Fixture ranges require exact two-card hand:weight tokens")
        hand = tuple(sorted(cards(hand_text, 2)))
        weight = Fraction(weight_text)
        if weight <= 0:
            raise ValueError("Fixture hand weights must be positive")
        result.append(RangeHand(hand, weight))
    if len({hand.cards for hand in result}) != len(result):
        raise ValueError("Fixture range contains duplicate private hands")
    return tuple(result)


def build_physical_worlds():
    """Return the fixed fixture's pairs/worlds with exact normalized weights."""
    board = tuple(cards(FIXTURE["board"], 4))
    oop_range = _weighted_combo_tokens(FIXTURE["oop"])
    ip_range = _weighted_combo_tokens(FIXTURE["ip"])
    pairs = []
    for oop_index, oop in enumerate(oop_range):
        if set(oop.cards).intersection(board):
            continue
        for ip_index, ip in enumerate(ip_range):
            if set(ip.cards).intersection(board) or set(oop.cards).intersection(ip.cards):
                continue
            rivers = tuple(card for card in DECK
                           if card not in board and
                           card not in oop.cards + ip.cards)
            if len(rivers) != 44:
                raise ValueError("Every compatible turn pair must have 44 legal rivers")
            pairs.append((oop_index, ip_index, "".join(oop.cards),
                          "".join(ip.cards), oop.weight * ip.weight, rivers))
    if not pairs:
        raise ValueError("Fixed fixture has no compatible private pairs")

    raw_total = sum((pair[4] for pair in pairs), Fraction())
    if raw_total <= 0:
        raise ValueError("Fixed fixture physical range mass must be positive")
    pairs = tuple(PhysicalPair(
        oop_index, ip_index, oop_hand, ip_hand, raw_weight,
        raw_weight / raw_total, raw_weight / raw_total / len(rivers), rivers,
    ) for oop_index, ip_index, oop_hand, ip_hand, raw_weight, rivers in pairs)
    worlds = tuple(
        PhysicalWorld(pair.oop_index, pair.ip_index, river, pair.per_river_weight)
        for pair in pairs for river in pair.rivers
    )
    global_mass = sum((world.weight for world in worlds), Fraction())
    if global_mass != 1:
        raise AssertionError(f"Global exact physical mass must be 1, got {global_mass}")
    return PhysicalWorldCensus(board, oop_range, ip_range, tuple(pairs),
                              worlds, global_mass)


def _tree_metrics(root):
    """Count max chance-path work, max public-state depth and action tokens."""
    action_tokens = set()

    def walk(node, depth):
        if isinstance(node, _Terminal):
            return 0, depth
        if isinstance(node, _Chance):
            children = [walk(child, depth + 1) for child in node.branches.values()]
            return max((count for count, _ in children), default=0), max(
                (child_depth for _, child_depth in children), default=depth)
        if isinstance(node, _Node):
            action_tokens.update(action.token for action in node.actions)
            children = [walk(child, depth + 1) for child in node.children]
            return 1 + sum(count for count, _ in children), max(
                (child_depth for _, child_depth in children), default=depth)
        raise TypeError(f"Unexpected public-tree node: {type(node).__name__}")

    visited, depth = walk(root, 1)
    return visited, depth, tuple(sorted(action_tokens))


def _tree_structure(node):
    """Return the stable public-tree identity projection for independent checks."""
    if isinstance(node, _Terminal):
        return ["terminal", node.kind, node.winner, list(node.contributions)]
    if isinstance(node, _Chance):
        return ["chance", list(node.history), [
            [river, _tree_structure(child)]
            for river, child in sorted(node.branches.items())
        ]]
    if isinstance(node, _Node):
        board = list(cards(FIXTURE["board"], 4))
        rivers = [token[6:] for token in node.history
                  if token.startswith("river@")]
        if rivers:
            board.append(rivers[-1])
        return ["decision", node.player, list(node.history), board, [
            [action.name, action.token, action.amount, action.raise_to,
             _tree_structure(child)]
            for action, child in zip(node.actions, node.children)
        ]]
    raise TypeError(f"Unexpected public-tree node: {type(node).__name__}")


def public_tree_sha256(root):
    """Hash the specified deterministic projection of the production tree."""
    payload = json.dumps(_tree_structure(root), sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _information_row_count(nodes, world_census):
    legal_hands = {(player, ()): set() for player in (0, 1)}
    for world in world_census.worlds:
        for player, hand_index in ((0, world.oop_index), (1, world.ip_index)):
            legal_hands[(player, ())].add(hand_index)
            legal_hands.setdefault((player, (world.river,)), set()).add(hand_index)
    total = 0
    for (player, history), _node in nodes.items():
        rivers = tuple(token[6:] for token in history if token.startswith("river@"))
        prefix = (rivers[-1],) if rivers else ()
        total += len(legal_hands.get((player, prefix), ()))
    return total


def forecast_work(backend, iterations, worlds, visited_decisions,
                  total_states, max_private_hands):
    """Return a full-request work estimate under the fixed backend formula."""
    if backend not in ("materialized", "matrix-free"):
        raise ValueError("backend must be materialized or matrix-free")
    values = (iterations, worlds, visited_decisions, total_states, max_private_hands)
    if any(type(value) is not int or value < 1 for value in values):
        raise ValueError("forecast dimensions must be positive integers")
    if backend == "materialized":
        return worlds * visited_decisions * 3 * iterations
    return max_private_hands * total_states * (3 * iterations + 3)


def forecast_for(backend, iterations, worlds, visited_decisions,
                 total_states, max_private_hands):
    work = forecast_work(backend, iterations, worlds, visited_decisions,
                         total_states, max_private_hands)
    within = work <= REFERENCE_WORK_CAP
    label = "WITHIN_REFERENCE_CAP" if within else "EXCEEDS_REFERENCE_CAP"
    return Forecast(backend, iterations, work, REFERENCE_WORK_CAP, within, label)


def census():
    """Return fixed-fixture counts and advisory forecasts; no solver is run."""
    physical = build_physical_worlds()
    config = RiverConfig.from_dict(FIXTURE["config"])
    tree_worlds = [
        (world.oop_index, world.ip_index, float(world.weight), 0, world.river)
        for world in physical.worlds
    ]
    allocation_counts = {}
    root, nodes, _chance_nodes, production_visited, _plan_ops = \
        _build_postflop_tree(physical.board, config, river_config=config,
                             worlds=tree_worlds,
                             allocation_counts=allocation_counts)
    visited, depth, action_tokens = _tree_metrics(root)
    if visited != production_visited:
        raise AssertionError("Census decision visits differ from tree-builder accounting")

    total_states = allocation_counts["total"]
    decisions = allocation_counts["decision"]
    max_hands = max(len(physical.oop_range), len(physical.ip_range))
    forecasts = tuple(
        forecast_for(backend, iterations, len(physical.worlds), visited,
                     total_states, max_hands)
        for iterations in FORECAST_ITERATIONS
        for backend in ("materialized", "matrix-free")
    )
    pair_masses = tuple(
        (pair.oop_hand, pair.ip_hand, str(pair.normalized_mass),
         str(pair.per_river_weight))
        for pair in physical.pairs
    )
    return Census(
        fixture_id=FIXTURE["id"], board="".join(physical.board),
        pairs=len(physical.pairs), worlds=len(physical.worlds),
        rivers_per_pair=tuple(len(pair.rivers) for pair in physical.pairs),
        physical_pair_masses=pair_masses,
        global_physical_mass=physical.global_mass,
        public_candidates=52 - len(physical.board),
        reachable_rivers=len({world.river for world in physical.worlds}),
        public_nodes=total_states, decisions=decisions,
        information_rows=_information_row_count(nodes, physical), depth=depth,
        visited_decisions_per_world=visited, max_private_hands=max_hands,
        action_tokens=action_tokens, public_tree_sha256=public_tree_sha256(root),
        forecasts=forecasts,
    )


def to_jsonable(result):
    value = asdict(result)
    value["global_physical_mass"] = str(result.global_physical_mass)
    return value


if __name__ == "__main__":
    print(json.dumps(to_jsonable(census()), indent=2))
