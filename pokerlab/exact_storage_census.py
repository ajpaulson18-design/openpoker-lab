"""Rank-free storage frontier for the admitted unified exact-product game.

Suit orbits are structural opportunities only. No policy, regret or information
row is merged, and no solve, rank, private-pair query or quality proof occurs.
"""
from collections import Counter
from dataclasses import asdict, dataclass
from itertools import permutations

from .cards import DECK
from .exact_selected_solver import _prepare_exact_selected, _tokens
from .preflop_solver import _revealed_board
from .shared_public_topology import DecisionVertex, ChanceVertex, TerminalVertex

_CARD_ORDER = {card: i for i, card in enumerate(DECK)}
_SUITS = "cdhs"


@dataclass(frozen=True, slots=True)
class ExactStorageCensusLimits:
    max_additional_entries: int = 2_000_000
    max_modeled_work: int = 500_000_000
    max_history_token_bytes: int = 16_000_000

    def __post_init__(self):
        for name, ceiling in (("max_additional_entries", 2_000_000),
                              ("max_modeled_work", 500_000_000),
                              ("max_history_token_bytes", 16_000_000)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError(f"{name} must be a positive integer at most {ceiling}.")


def _card(card, suit_map):
    return card[0] + suit_map[card[1]]


def _hand(hand, suit_map):
    return tuple(sorted(_card(card, suit_map) for card in hand))


def _board(board, suit_map):
    flop, turn, river = board
    return (tuple(sorted((_card(card, suit_map) for card in flop), key=_CARD_ORDER.__getitem__)),
            _card(turn, suit_map), _card(river, suit_map))


def _history(history, suit_map):
    result = []
    for token in history:
        if token.startswith("flop@"):
            flop = tuple(token[i:i+2] for i in (5, 7, 9))
            transformed = sorted((_card(card, suit_map) for card in flop), key=_CARD_ORDER.__getitem__)
            result.append("flop@" + "".join(transformed))
        elif token.startswith("turn@"):
            result.append("turn@" + _card(token[5:], suit_map))
        elif token.startswith("river@"):
            result.append("river@" + _card(token[6:], suit_map))
        else:
            result.append(token)
    return tuple(result)


def _suit_stabilizer(kernel):
    """Sufficient subgroup preserving both role-ordered priors and all boards."""
    priors = tuple(dict(zip(hands, weights)) for hands, weights in zip(kernel.hands, kernel.weights))
    selected = set(kernel.selected)
    result = []
    for permutation in permutations(_SUITS):
        suit_map = dict(zip(_SUITS, permutation))
        if any({_hand(hand, suit_map): weight for hand, weight in prior.items()} != prior for prior in priors):
            continue
        if {_board(board, suit_map) for board in selected} != selected:
            continue
        result.append(tuple(permutation))
    if tuple(_SUITS) not in result:
        raise RuntimeError("Exact weighted-game stabilizer lost the identity.")
    return tuple(result)


def _witness(kernel, topology):
    """Export unique structure/inputs, never expanded histories or hidden deals."""
    vertices = []
    for vertex in topology.vertices:
        if isinstance(vertex, DecisionVertex):
            vertices.append({"kind": "decision", "player": vertex.player,
                "actions": [{"name": a.name, "amount_hex": float(a.amount).hex(),
                             "raise_to_hex": float(a.raise_to).hex(), "full_raise": a.full_raise,
                             "token": a.token} for a in vertex.actions],
                "children": list(vertex.child_ids)})
        elif isinstance(vertex, ChanceVertex):
            vertices.append({"kind": "chance", "street": vertex.street, "card_index": vertex.card_index,
                             "branches": [[token, child] for token, child in vertex.branches]})
        elif isinstance(vertex, TerminalVertex):
            vertices.append({"kind": "terminal", "terminal_kind": vertex.kind, "winner": vertex.winner,
                             "contributions_hex": [float(value).hex() for value in vertex.contributions]})
        else:
            raise TypeError("Unsupported census witness vertex.")
    return {"contract": "exact-selected-structural-witness-v1", "root_id": topology.root_id,
            "initial_history": list(topology.initial_history), "vertices": vertices,
            "ranges": [[{"hand": "".join(hand), "weight_hex": float(weight).hex()}
                        for hand, weight in zip(hands, weights)]
                       for hands, weights in zip(kernel.hands, kernel.weights)],
            "selected_runouts": [[*flop, turn, river] for flop, turn, river in kernel.selected],
            "scope": "Compact unique topology/input witness. Independent structural replay is conditional on this exported public graph; it is not independent proof of legal betting-game construction or solver quality."}


def census_exact_selected_storage(request, *, rank_cache_boards=1, kernel_limits=None,
                                 exact_arithmetic="fraction", suit_orbits=True, limits=None,
                                 include_witness=False):
    """Count actual supported rows using precisely the solve's admitted setup.

    A rejected requested solve stays rejected: census callers must retain that
    failure, never infer missing counts or train under a relaxed envelope.
    """
    if type(suit_orbits) is not bool:
        raise TypeError("suit_orbits must be boolean.")
    if type(include_witness) is not bool:
        raise TypeError("include_witness must be boolean.")
    limits = ExactStorageCensusLimits() if limits is None else limits
    if type(limits) is not ExactStorageCensusLimits:
        raise TypeError("limits must be ExactStorageCensusLimits.")
    prepared = _prepare_exact_selected(request, rank_cache_boards=rank_cache_boards,
        kernel_limits=kernel_limits, pair_diagnostics="compact", exact_arithmetic=exact_arithmetic)
    kernel, topology = prepared.kernel, prepared.topology
    upper = prepared.layout_upper
    hsum = sum(kernel.hand_counts)
    prefixes = len(prepared.unique_prefixes)
    logical = topology.census.expanded_logical_visits
    maximum_depth = topology.census.maximum_depth
    context_upper = min(logical, len(topology.vertices) * len(prepared.prefix_counts))
    edge_upper = max(0, logical - 1)
    support_entries = prefixes * (2 * hsum + 16)
    orbit_entries = (16 * upper["upper_dense_decision_hand_slots"] +
                     4 * upper["upper_history_token_entries"] + 16 * maximum_depth + 1024) if suit_orbits else 0
    witness_entries = (32 * (len(topology.vertices) + topology.census.unique_edges) +
                       16 * hsum + 16 * len(kernel.selected) + 128) if include_witness else 0
    additional = (support_entries + 12 * context_upper + 24 * edge_upper + orbit_entries +
                  32 * hsum + 32 * len(kernel.selected) + witness_entries + 512)
    group_work = 24 * (8 * hsum + 16 * len(kernel.selected)) if suit_orbits else 0
    orbit_work = (24 * (12 * upper["upper_history_token_entries"] +
                       32 * upper["upper_dense_decision_hand_slots"])) if suit_orbits else 0
    work = (group_work + orbit_work + logical * (maximum_depth + 32) +
            upper["upper_dense_decision_hand_slots"] * 8 + 4 * witness_entries)
    if additional > limits.max_additional_entries or work > limits.max_modeled_work:
        raise ValueError("Exact storage census additional work/retained-entry admission exceeded before support/orbit allocation.")
    if upper["upper_history_token_bytes"] > limits.max_history_token_bytes:
        raise ValueError("Exact storage census history-byte admission exceeded before support/orbit allocation.")
    stabilizer = _suit_stabilizer(kernel) if suit_orbits else (tuple(_SUITS),)
    suit_maps = tuple(dict(zip(_SUITS, image)) for image in stabilizer)
    support = {prefix: kernel.legal_hands(prefix) for prefix in prepared.unique_prefixes}
    row_counts, slot_counts = Counter(), Counter()
    orbit_rows = {}
    contexts, context_edges, path = set(), set(), []
    rows = slots = history_tokens = history_bytes = dense = 0
    actual_orbit_work = 0
    for occurrence in topology.iter_occurrences():
        prefix = _tokens(_revealed_board(occurrence.history))
        context = (occurrence.vertex_id, prefix)
        del path[occurrence.depth:]
        if path:
            # Distinct action/reveal branches remain distinct even when their
            # child vertex and public prefix coincide in the shared DAG.
            context_edges.add((path[-1], occurrence.history[-1], context))
        path.append(context)
        contexts.add(context)
        vertex = topology.vertices[occurrence.vertex_id]
        if not isinstance(vertex, DecisionVertex):
            continue
        player = vertex.player
        street = ("preflop", "flop", "turn", "river")[len(prefix)]
        dense += kernel.hand_counts[player]
        live = support[prefix][player]
        group = (street, player)
        row_counts[group] += len(live)
        slot_counts[group] += len(live) * len(vertex.actions)
        rows += len(live)
        slots += len(live) * len(vertex.actions)
        history_tokens += len(live) * len(occurrence.history)
        history_bytes += len(live) * sum(len(token.encode("utf-8")) for token in occurrence.history)
        if suit_orbits:
            representatives = orbit_rows.setdefault(group, set())
            for hand_index in live:
                hand = kernel.hands[player][hand_index]
                key = min((player, _hand(hand, suit_map), _history(occurrence.history, suit_map))
                          for suit_map in suit_maps)
                representatives.add(key)
                actual_orbit_work += len(suit_maps) * (12 * len(occurrence.history) + 32)
    if (len(contexts) > context_upper or len(context_edges) > edge_upper or
            rows > upper["upper_dense_decision_hand_slots"] or slots > upper["upper_action_slots"] or
            history_tokens > upper["upper_history_token_entries"] or
            history_bytes > upper["upper_history_token_bytes"] or actual_orbit_work > orbit_work):
        raise RuntimeError("Exact storage census exceeded its preallocation envelope.")
    if kernel.statistics()["rank_calls"]:
        raise RuntimeError("Rank-free storage census entered ranking.")
    orbit_count = sum(map(len, orbit_rows.values())) if suit_orbits else None
    per_group = [{"street": street, "player": "sb" if player == 0 else "bb",
                  "information_rows": count, "action_slots": slot_counts[(street, player)],
                  "suit_row_orbits": len(orbit_rows[(street, player)]) if suit_orbits else None}
                 for (street, player), count in sorted(row_counts.items())]
    result = {"contract": "exact-selected-storage-census-v1", "chance_contract": "exact-product-selected-v1",
        "iterations_requested": request.iterations, "arithmetic": exact_arithmetic,
        "hand_counts": list(kernel.hand_counts), "selected_boards": len(kernel.selected),
        "reachable_boards": len(prepared.reachable), "support_pair_board_occurrences": kernel.statistics()["support_pair_board_occurrences"],
        "unique_vertices": len(topology.vertices), "unique_edges": topology.census.unique_edges,
        "vertex_prefix_contexts": len(contexts), "context_edges": len(context_edges),
        "logical_visits": logical, "maximum_depth": maximum_depth,
        "information_rows": rows, "action_slots": slots, "dense_slots": dense, "dense_holes": dense - rows,
        "history_token_entries": history_tokens, "history_token_bytes": history_bytes,
        "per_street_player": per_group,
        "four_packed_numeric_buffers_payload_bytes": 4 * slots * 8,
        "serialized_policy_rows": rows, "serialized_action_rows": slots,
        "complete_solve_admission": prepared.admission, "bit_forecast": prepared.bit_forecast,
        "rank_free_kernel_receipt": kernel.statistics(),
        "additional_census_admission": {"retained_entries_upper": additional, "modeled_work_upper": work,
            "history_bytes_upper": upper["upper_history_token_bytes"], "context_upper": context_upper,
            "orbit_work_upper": orbit_work, "actual_orbit_work": actual_orbit_work,
            "witness_entries_upper": witness_entries, "limits": asdict(limits)},
        "suit_symmetry": {"requested": suit_orbits, "permutations": ["".join(p) for p in stabilizer],
            "conservative_stabilizer_size": len(stabilizer), "supported_row_orbits": orbit_count,
            "potential_row_reduction": rows - orbit_count if suit_orbits else None,
            "scope": "Whole weighted-range/selected-board S4 stabilizer gives a sufficient conservative symmetry opportunity. No policy/regret rows are merged, no BR equivalence is certified, and absent symmetries do not prove no other quotient exists."},
        "training_calls": 0, "pair_query_calls": 0, "native_calls": 0,
        "quality_gate": None,
        "scope": "Actual admitted direct-game support/history census, no solve/rank/private-pair queries. Modeled phase slots, pure numeric payload bytes and structural symmetry opportunities are separate from measured memory, convergence and approved compression."}
    if include_witness:
        result["structural_witness"] = _witness(kernel, topology)
    return result
