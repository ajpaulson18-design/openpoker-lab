"""Fixed three-hand, seven-river-class CFR+ tail adapter (research only).

The public solver APIs and their admission limits remain untouched. This
module prepares a lossless class representation for one literal fixture, calls
the existing original-weight tail trainer once, then lifts every legal row to
the complete physical tree before diagnostics.
"""
from __future__ import annotations

from fractions import Fraction
import math
from typing import Any

from . import turn_class_vector_budget as budget
from .cards import DECK, cards, expand_range
from .postflop_solver import (
    _Chance, _MAX_PUBLIC_NODES, _MAX_PUBLIC_STATES, _MAX_WORLD_NODE_WORK,
    _MAX_WORLD_ITERATIONS, _MAX_CANDIDATE_HAND_ITERATIONS,
    _build_postflop_tree, _enumerate_worlds,
    _prefix_hand_index, _public_reveals,
)
from .public_cfr import MAX_PREFIX_EDGES, _aggregate_prefixes, _validate_inputs
from .public_diagnostics import evaluate_profile
from .river_config import RiverConfig
from .river_tree import _Node, _Terminal
from .turn_tail_adapter import (
    MAX_DENSE_HAND_STATE_PASS_WORK, MAX_INFO_ACTION_SLOTS,
    _train_original_weight_tail,
)


BOARD = ("Js", "8d", "4c", "2h")
OOP_RANGE = "AsAh:0.5,KsKh:1,QsQh:0.75"
IP_RANGE = "AcAd:1,KcKd:0.75,QcQd:0.5"
CONFIG = {
    "pot": 100.0,
    "effective_stack": 220.0,
    "bet_sizes": [0.5],
    "raise_sizes": [0.5],
    "max_raises": 1,
    "include_all_in": False,
}
SOLVER_VERSION = "research-turn-seven-class-tail-adapter-v1"
SCOPE = (
    "Fixed three-hand turn game using a globally lossless seven-class public-river "
    "representation; full physical policy rows are restored before diagnostics. "
    "No preflop, multiway, rake, unrestricted no-limit, or exact-equilibrium claim."
)
DIAGNOSTIC_PROVENANCE = (
    "Fresh full-physical public-batched profile and best-response diagnostics on "
    "the lifted policy; numeric convergence diagnostics are not an exact certificate."
)

_BLOCKER_CLASSES = {
    "Ac": ("Ac", "Ad"), "Ah": ("Ah", "As"),
    "Kc": ("Kc", "Kd"), "Kh": ("Kh", "Ks"),
    "Qc": ("Qc", "Qd"), "Qh": ("Qh", "Qs"),
}
_SPECIAL_CARDS = {card for members in _BLOCKER_CLASSES.values() for card in members}
_CLASS_FOR_CARD = {
    card: label for label, members in _BLOCKER_CLASSES.items() for card in members
}
_NEUTRAL = tuple(card for card in DECK if card not in BOARD and card not in _SPECIAL_CARDS)
_REPRESENTATIVE = {"neutral": _NEUTRAL[0], **{k: v[0] for k, v in _BLOCKER_CLASSES.items()}}
_CLASS_MEMBERS = {"neutral": _NEUTRAL, **_BLOCKER_CLASSES}
_FULL_RIVERS = tuple(card for card in DECK if card not in BOARD)
_FULL_RIVER_SET = frozenset(_FULL_RIVERS)
_CLASS_REPRESENTATIVES = frozenset(_REPRESENTATIVE.values())
def _fixed_config() -> RiverConfig:
    return RiverConfig.from_dict(CONFIG)


def _class_for(card: str) -> str:
    return _CLASS_FOR_CARD.get(card, "neutral")


def _normalize_history(history: tuple) -> tuple:
    normalized = []
    for token in history:
        if token.startswith("river@"):
            normalized.append("river@" + _REPRESENTATIVE[_class_for(token[6:])])
        else:
            normalized.append(token)
    return tuple(normalized)


def _action_signature(action: Any) -> tuple:
    return (action.name, action.token, action.amount, action.raise_to)


def _history_matches(physical: tuple, compact: tuple, phase: Any) -> bool:
    if len(physical) != len(compact) or len(physical) > 9:
        return False
    for left, right in zip(physical, compact):
        phase.charge("tree_isomorphism", 3)
        normalized = left
        if left.startswith("river@"):
            normalized = "river@" + _REPRESENTATIVE[_class_for(left[6:])]
        if normalized != right:
            return False
    return True


def _assert_tree_equivalent(physical: Any, compact: Any, phase: Any,
                            depth: int = 0) -> None:
    """Stream-compare the complete trees without allocating signature copies."""
    if depth > 9:
        raise ValueError("fixed tree exceeds the admitted depth")
    phase.charge_storage("maximum_recursion_depth", depth)
    phase.charge("tree_isomorphism", 1)
    if isinstance(physical, _Terminal) and isinstance(compact, _Terminal):
        phase.charge("tree_isomorphism", 4)
        if (physical.kind != compact.kind or physical.winner != compact.winner
                or len(physical.contributions) != 2 or len(compact.contributions) != 2
                or physical.contributions[0] != compact.contributions[0]
                or physical.contributions[1] != compact.contributions[1]):
            raise ValueError("physical and compact terminal refunds/payoffs differ")
        return
    if isinstance(physical, _Chance) and isinstance(compact, _Chance):
        if not _history_matches(physical.history, compact.history, phase):
            raise ValueError("physical and compact chance histories differ")
        phase.charge("tree_isomorphism", 2 * (len(physical.branches) + len(compact.branches)))
        physical_cards = set(physical.branches)
        compact_cards = set(compact.branches)
        if physical_cards != _FULL_RIVER_SET or compact_cards != _CLASS_REPRESENTATIVES:
            raise ValueError("physical/compact chance branches differ from the fixed partition")
        for card, child in physical.branches.items():
            phase.charge("tree_isomorphism", 2)
            representative = _REPRESENTATIVE[_class_for(card)]
            _assert_tree_equivalent(child, compact.branches[representative], phase, depth + 1)
        return
    if isinstance(physical, _Node) and isinstance(compact, _Node):
        phase.charge("tree_isomorphism", 1)
        if (physical.player != compact.player
                or not _history_matches(physical.history, compact.history, phase)
                or len(physical.actions) != len(compact.actions)
                or len(physical.children) != len(physical.actions)
                or len(compact.children) != len(compact.actions)):
            raise ValueError("physical and compact decision shape/history differs")
        for pa, ca, pc, cc in zip(physical.actions, compact.actions,
                                  physical.children, compact.children):
            phase.charge("tree_isomorphism", 5)
            if (pa.name != ca.name or pa.token != ca.token
                    or pa.amount != ca.amount or pa.raise_to != ca.raise_to):
                raise ValueError("physical and compact legal action metadata differs")
            _assert_tree_equivalent(pc, cc, phase, depth + 1)
        return
    raise ValueError("physical and compact node kinds differ")


def _validate_class_partition(selected: tuple[str, ...]) -> None:
    if len(selected) != 48 or len(set(selected)) != 48:
        raise ValueError("fixed physical river support must contain 48 unique cards")
    if any(card in BOARD for card in selected):
        raise ValueError("fixed river support overlaps the board")
    if set(selected) != set(card for card in DECK if card not in BOARD):
        raise ValueError("fixed river support differs from the full deck")
    if tuple(selected) != tuple(card for card in DECK if card not in BOARD):
        raise ValueError("fixed river order differs from the full-deck preparation order")
    if len(_NEUTRAL) != 36 or len(_BLOCKER_CLASSES) != 6:
        raise ValueError("fixed class partition dimensions changed")
    if set(_CLASS_FOR_CARD) != _SPECIAL_CARDS or set(_SPECIAL_CARDS) & set(BOARD):
        raise ValueError("fixed blocker class map is malformed")


def _class_worlds(hands, physical_worlds, selected, phase):
    """Return exact-original-mass class worlds and check all physical signs."""
    phase.charge("class_mapping", 27_356 - 372 + budget._CLASS_PARTITION + 63)
    _validate_class_partition(tuple(selected))
    ranges = (expand_range(OOP_RANGE, BOARD), expand_range(IP_RANGE, BOARD))
    expected_hands = (
        (tuple(sorted(cards("AsAh", 2))), tuple(sorted(cards("KsKh", 2))),
         tuple(sorted(cards("QsQh", 2)))),
        (tuple(sorted(cards("AcAd", 2))), tuple(sorted(cards("KcKd", 2))),
         tuple(sorted(cards("QcQd", 2)))),
    )
    if tuple(tuple(player_hands) for player_hands in hands) != expected_hands:
        raise ValueError("fixed hand order changed")
    if len(physical_worlds) != 396:
        raise ValueError("fixed physical deal count changed")

    pair_weights: dict[tuple[int, int], Fraction] = {}
    for oop_index, oop_hand in enumerate(hands[0]):
        for ip_index, ip_hand in enumerate(hands[1]):
            if set(oop_hand).isdisjoint(ip_hand):
                pair_weights[(oop_index, ip_index)] = (
                    Fraction.from_float(ranges[0][oop_hand]) *
                    Fraction.from_float(ranges[1][ip_hand]))
    if len(pair_weights) != 9:
        raise ValueError("fixed range must have nine compatible private pairs")
    global_weight = sum(pair_weights.values(), Fraction())
    if global_weight <= 0:
        raise ValueError("fixed physical prior has no positive mass")

    blocked_by_pair = {
        key: set(hands[0][key[0]]) | set(hands[1][key[1]])
        for key in pair_weights
    }
    physical_signs: dict[tuple[int, int, str], int] = {}
    pair_world_counts = {key: 0 for key in pair_weights}
    phase.charge("validation_aggregation", len(physical_worlds))
    for i, j, mass, sign, river in physical_worlds:
        if (type(i) is not int or type(j) is not int or not (0 <= i < 3 and 0 <= j < 3)
                or type(sign) is not int or sign not in (-1, 0, 1)
                or type(river) is not str or river not in selected
                or type(mass) is not float):
            raise ValueError("malformed physical world")
        if (i, j) not in pair_weights:
            raise ValueError("physical world uses an incompatible private pair")
        blocked = blocked_by_pair[(i, j)]
        if river in blocked:
            raise ValueError("physical world river is blocked by a private hand")
        expected_mass = float(pair_weights[(i, j)] / (44 * global_weight))
        if not math.isfinite(mass) or abs(mass - expected_mass) > 1e-15:
            raise ValueError("physical world mass differs from the literal original joint prior")
        # Independent pocket-pair rule for this fixed unpaired turn board:
        # a river matching one pocket rank makes that hand trips; otherwise
        # the higher pocket pair wins. Equal pocket ranks tie on every river.
        oop_rank = "23456789TJQKA".index(hands[0][i][0][0])
        ip_rank = "23456789TJQKA".index(hands[1][j][0][0])
        river_rank = river[0]
        if oop_rank == ip_rank:
            expected_sign = 0
        elif river_rank == hands[0][i][0][0]:
            expected_sign = 1
        elif river_rank == hands[1][j][0][0]:
            expected_sign = -1
        else:
            expected_sign = (oop_rank > ip_rank) - (oop_rank < ip_rank)
        if sign != expected_sign:
            raise ValueError("physical showdown sign violates the fixed pocket-pair rule")
        key = (i, j, river)
        if key in physical_signs:
            raise ValueError("duplicate physical world")
        physical_signs[key] = sign
        pair_world_counts[(i, j)] += 1
        if not math.isfinite(mass) or mass <= 0:
            raise ValueError("physical world mass must be positive and finite")
    if len(physical_signs) != 396:
        raise ValueError("physical world support is incomplete")
    phase.charge("validation_aggregation", 9 * 48)
    expected_support = set()
    for i, j in pair_weights:
        blocked = blocked_by_pair[(i, j)]
        for river in selected:
            if river not in blocked:
                expected_support.add((i, j, river))
    if set(physical_signs) != expected_support:
        raise ValueError("physical worlds do not match the complete compatible support")
    if any(pair_world_counts[key] != 44 for key in pair_weights):
        raise ValueError("each fixed private pair must retain all 44 legal river cards")

    result = []
    exact_total = Fraction()
    phase.charge("class_mapping", 9 * 7)
    for i in range(3):
        for j in range(3):
            blocked = blocked_by_pair[(i, j)]
            for label in ("neutral", *_BLOCKER_CLASSES):
                members = tuple(card for card in _CLASS_MEMBERS[label] if card in selected)
                legal_members = tuple(card for card in members if card not in blocked)
                if not legal_members:
                    continue
                if legal_members != members:
                    raise ValueError("a fixed class is only partially supported by a private pair")
                phase.charge("validation_aggregation", len(legal_members))
                signs = {physical_signs[(i, j, card)] for card in legal_members}
                if len(signs) != 1:
                    raise ValueError("showdown sign varies inside a fixed river class")
                exact_mass = pair_weights[(i, j)] * len(members) / (44 * global_weight)
                exact_total += exact_mass
                mass = float(exact_mass)
                if not math.isfinite(mass) or mass <= 0:
                    raise ValueError("class mass underflowed or became nonfinite")
                phase.charge("class_mapping", 1)
                result.append((i, j, mass, signs.pop(), _REPRESENTATIVE[label]))
    if len(result) != 45:
        raise ValueError("fixed compact world count changed")
    if exact_total != 1:
        raise ValueError("exact class masses do not sum to one")
    if abs(math.fsum(world[2] for world in result) - 1.0) > 1e-15:
        raise ValueError("class world mass does not sum to one")
    return result


def _make_infos(nodes, legal_hands, phase):
    phase.charge("info_layout", 3)
    infos, metadata = {}, {}
    for (player, history), node in nodes.items():
        phase.charge("info_layout", 10 + len(history))
        prefix = _public_reveals(history)
        for hand_index in sorted(legal_hands.get((player, prefix), ())):
            phase.charge("info_layout", 7)
            key = (player, hand_index, history)
            infos[key] = len(node.actions)
            metadata[key] = node
    phase.charge("info_layout", 2)
    return infos, metadata


def solve_turn_class_tail(*, iterations: int, discard: int,
                          resource_model: str) -> dict[str, Any]:
    """Solve the literal three-hand turn fixture through seven river classes.

    The explicit resource model is experimental and separate from ordinary
    solver admission. Full physical request limits and the compact complete-T
    model are checked before enumeration. ``iterations`` and ``discard`` must
    be strict integers; the resource planner sets the permitted range.
    """
    if type(resource_model) is not str:
        raise ValueError("resource_model must be the explicit fixed model name")
    plan = budget.plan_request(iterations, discard, resource_model)
    phase = budget.PhaseBudget(plan)
    # Reserve the complete source-derived work before any enumeration/ranking
    # or tree construction. These values are modeled allowances, not observed
    # instructions, elapsed time, bytes, or RSS.
    for component, allowance in plan["components"].items():
        phase.reserve(component, allowance)

    # Reserve known simultaneous logical peaks before the corresponding
    # allocations. These are modeled slot ceilings, not observed RSS/bytes.
    for name, amount in {
        "physical_enumeration_peak_world_tuple_fields": 3960,
        "physical_pair_future_list_peak_entries": 48,
        "modeled_rank_cache_entries": 276,
        "rank_cache_key_fields": 828,
        "rank_cache_result_fields": 1656,
        "rank_input_tuple_peak_fields": 7,
        "maximum_recursion_depth": 9,
        "physical_and_compact_public_states": 3039 + 456,
        "physical_and_compact_world_tuple_fields": 5 * (396 + 45),
        "physical_and_compact_tree_nodes": 3039 + 456,
        "physical_and_compact_tree_action_objects": 3218,
        "physical_and_compact_tree_action_tuple_fields": 6436,
        "physical_and_compact_tree_temporary_action_list_fields": 6436,
        "physical_and_compact_policy_rows": 3606 + 486,
        "physical_and_compact_action_slots": 8046 + 1086,
        "physical_and_compact_prefix_edges": 405 + 54,
        "physical_output_board_slots": 18012,
        "physical_output_row_dict_fields": 21636,
        "physical_output_action_dict_fields": 40230,
        "lifted_and_diagnostic_probability_slots": 2 * 8046,
        "lifted_and_diagnostic_policy_dict_entries": 2 * 3606,
        "diagnostic_normalized_probability_slots": 8046,
        "diagnostic_normalized_policy_key_fields": 0,
        "diagnostic_concurrent_prefix_edges": 405,
        "diagnostic_concurrent_marginal_slots": 294,
        "diagnostic_recursion_depth": 9,
        "diagnostic_live_visit_frames": 10,
        "diagnostic_peak_numeric_vector_slots": 132,
        "diagnostic_peak_list_tuple_fields": 159,
        "diagnostic_peak_policy_fallback_slots": 9,
    }.items():
        phase.reserve_storage(name, amount)

    # Reserve fixed setup maps/sets, metadata, histories and aggregation peaks
    # before enumeration or any owned construction. These are logical fields.
    phase.reserve_storage("class_validation_key_tuple_fields", 2376)
    phase.reserve_storage("class_validation_map_and_set_entries", 1224)
    phase.reserve_storage("class_member_temporary_tuple_fields", 72)
    phase.reserve_storage("physical_and_compact_info_metadata_entries", 8184)
    phase.reserve_storage("information_key_tuple_fields", 12276)
    phase.reserve_storage("sorted_hand_list_peak_fields", 3)
    phase.reserve_storage("prefix_legal_map_key_fields", 228)
    phase.reserve_storage("prefix_legal_map_entries", 114)
    phase.reserve_storage("prefix_legal_memberships", 324)
    phase.reserve_storage("tree_decision_index_key_fields", 2884)
    phase.reserve_storage("stored_and_transient_tree_history_fields", 7394)
    phase.reserve_storage("both_prefix_edge_tuple_fields", 1836)
    phase.reserve_storage("both_prefix_edge_container_slots", 468)
    phase.reserve_storage("prefix_aggregation_edge_mass_slots", 918)
    phase.reserve_storage("prefix_aggregation_edge_key_fields", 918)
    phase.reserve_storage("prefix_aggregation_edge_mapping_entries", 459)
    phase.reserve_storage("prefix_aggregation_outer_map_entries", 171)
    phase.reserve_storage("physical_output_history_slots", 18105)
    phase.reserve_storage("physical_output_container_slots", 11652)

    # Every logical structure is reserved before enumeration or allocation.
    for name, amount in plan["storage_requirements"].items():
        phase.reserve_storage(name, amount)

    board = cards(BOARD)
    config = _fixed_config()
    if type(iterations) is not int or type(discard) is not int:
        raise ValueError("iterations and discard must be strict integers")

    # The original production helper receives the entire requested T.
    hands, physical_worlds, selected, pair_count = _enumerate_worlds(
        board, OOP_RANGE, IP_RANGE, runouts=None, iterations=iterations)
    if len(physical_worlds) != 396 or pair_count != 9 or len(selected) != 48:
        raise ValueError("fixed physical enumeration census changed")
    phase.charge_storage("physical_worlds", len(physical_worlds))
    phase.charge_storage("physical_selected_rivers", len(selected))

    # Reserve both public tree shapes before their builders allocate nodes.
    physical_counter = budget.BoundedTreeCounts("physical")
    physical_counts = physical_counter.preflight()
    physical_root, physical_nodes, physical_chance_nodes, physical_visited, _ = (
        _build_postflop_tree(board, config, river_config=config,
                             worlds=physical_worlds,
                             allocation_counts=physical_counter))
    physical_counter.verify_public_counts(physical_counter)
    if (len(physical_nodes) != 1254 or physical_chance_nodes != 5
            or physical_visited != 32):
        raise ValueError("physical public tree census changed")
    physical_world_work = len(physical_worlds) * physical_visited * iterations * 3
    for key, value in {
        "physical_states": 3039, "physical_decisions": 1254,
        "physical_terminals": 1780, "physical_chance_nodes": 5,
        "physical_chance_edges": 240, "physical_decision_edges": 2798,
    }.items():
        phase.charge_storage(key, value)

    # Class construction preserves original pair mass and rank signs.
    class_worlds = _class_worlds(hands, physical_worlds, selected, phase)
    phase.charge_storage("compact_worlds", len(class_worlds))

    compact_counter = budget.BoundedTreeCounts("compact")
    compact_counts = compact_counter.preflight()
    compact_root, compact_nodes, compact_chance_nodes, compact_visited, _ = (
        _build_postflop_tree(board, config, river_config=config,
                             worlds=class_worlds,
                             allocation_counts=compact_counter))
    compact_counter.verify_public_counts(compact_counter)
    if (len(compact_nodes) != 188 or compact_chance_nodes != 5
            or compact_visited != 32):
        raise ValueError("compact public tree census changed")
    for key, value in {
        "compact_states": 456, "compact_decisions": 188,
        "compact_terminals": 263, "compact_chance_nodes": 5,
        "compact_chance_edges": 35, "compact_decision_edges": 420,
    }.items():
        phase.charge_storage(key, value)
    for key, value in {
        "physical_and_compact_public_states": 3039 + 456,
        "physical_and_compact_world_tuple_fields": 5 * (396 + 45),
        "physical_and_compact_tree_nodes": 3039 + 456,
        "physical_and_compact_tree_action_objects": 3218,
        "physical_and_compact_tree_action_tuple_fields": 6436,
        "physical_and_compact_tree_temporary_action_list_fields": 6436,
    }.items():
        phase.charge_storage(key, value)
    _assert_tree_equivalent(physical_root, compact_root, phase)

    # Full-information dense inputs, infos and edges remain subject to original caps.
    physical_legal = _prefix_hand_index(physical_worlds)
    compact_legal = _prefix_hand_index(class_worlds)
    physical_slots = 0
    for (player, history), node in physical_nodes.items():
        physical_slots += len(node.actions) * len(
            physical_legal.get((player, _public_reveals(history)), ()))
        if physical_slots > MAX_INFO_ACTION_SLOTS:
            raise ValueError("original physical information/action cap exceeded")
    dense_work = max(map(len, hands)) * physical_counts["total"] * (3 * iterations + 3)
    physical_infos, physical_metadata = _make_infos(physical_nodes, physical_legal, phase)
    compact_infos, compact_metadata = _make_infos(compact_nodes, compact_legal, phase)
    if (len(physical_infos) != 3606 or sum(physical_infos.values()) != 8046
            or len(compact_infos) != 486 or sum(compact_infos.values()) != 1086):
        raise ValueError("fixed policy row/action-slot census changed")
    if sum(physical_infos.values()) > MAX_INFO_ACTION_SLOTS:
        raise ValueError("physical information/action cap exceeded")
    for key, value in {
        "physical_and_compact_policy_rows": len(physical_infos) + len(compact_infos),
        "physical_and_compact_action_slots": sum(physical_infos.values()) + sum(compact_infos.values()),
        "physical_and_compact_prefix_edges": 405 + 54,
    }.items():
        phase.charge_storage(key, value)

    _, physical_hand_counts = _validate_inputs(
        physical_worlds, physical_infos, iterations, "cfrplus", config.pot, _Chance)
    _, class_hand_counts = _validate_inputs(
        class_worlds, compact_infos, iterations, "cfrplus", config.pot, _Chance)
    physical_edges, physical_marginals = _aggregate_prefixes(physical_worlds, physical_hand_counts)
    class_edges, class_marginals = _aggregate_prefixes(class_worlds, class_hand_counts)
    if sum(map(len, physical_edges.values())) != 405 or sum(map(len, class_edges.values())) != 54:
        raise ValueError("prefix-edge census changed")
    phase.charge_storage("physical_policy_rows", len(physical_infos))
    phase.charge_storage("physical_action_slots", sum(physical_infos.values()))
    phase.charge_storage("physical_prefix_edges", 405)
    phase.charge_storage("physical_marginal_slots", 294)
    phase.charge_storage("physical_legal_prefix_memberships", 282)
    phase.charge_storage("compact_policy_rows", len(compact_infos))
    phase.charge_storage("compact_action_slots", sum(compact_infos.values()))
    phase.charge_storage("compact_prefix_edges", 54)
    phase.charge_storage("compact_marginal_slots", 48)
    phase.charge_storage("compact_legal_prefix_memberships", 42)

    phase.reserve_storage("live_training_action_maps", 6 * 1086)
    phase.reserve_storage("live_training_delta_action_slots", 2 * (1086 // 2))
    compact_averages = _train_original_weight_tail(
        compact_root, class_worlds, compact_infos, iterations, discard,
        pot=config.pot, chance_type=_Chance, edges=class_edges,
        marginals=class_marginals, hand_counts=class_hand_counts)

    lifted: dict[tuple[int, int, tuple], list[float]] = {}
    strategy_rows = []
    phase.charge("lift_serialization", len(physical_infos))
    for key in sorted(physical_infos):
        action_count = physical_infos[key]
        # Reserve before row, history, probability and action allocations.
        # Treat every action as a wager for the helper-entry bound.
        phase.charge("lift_serialization", 29 + 5 * len(key[2]) + 12 * action_count)
        player, hand_index, history = key
        class_key = (player, hand_index, _normalize_history(history))
        row = compact_averages.get(class_key)
        if row is None or len(row) != action_count:
            raise ValueError("compact policy does not cover a physical legal row")
        lifted[key] = list(row)
        node = physical_metadata[key]
        board_now = board + _public_reveals(history)
        actions = []
        for action, probability in zip(node.actions, row):
            actions.append({"name": action.name, "amount": action.amount,
                            "raise_to": action.raise_to, "history_key": action.token,
                            "probability": probability})
        strategy_rows.append({
            "player": "oop" if player == 0 else "ip",
            "hand": "".join(hands[player][hand_index]),
            "street": "river" if len(board_now) == 5 else "turn",
            "board": list(board_now), "history": list(history), "actions": actions,
        })
    if len(lifted) != 3606:
        raise ValueError("lift did not restore all physical policy rows")
    phase.charge_storage("output_policy_rows", len(lifted))
    phase.charge_storage("output_action_slots", sum(physical_infos.values()))
    phase.charge_storage("lifted_probability_slots", sum(physical_infos.values()))
    phase.charge_storage("lifted_policy_key_fields", 3 * len(lifted))
    phase.charge_storage("physical_output_row_dict_fields", 6 * len(strategy_rows))
    phase.charge_storage("physical_output_action_dict_fields", 5 * sum(physical_infos.values()))
    phase.charge_storage("physical_output_board_slots",
                         sum(len(row["board"]) for row in strategy_rows))

    # Preserve the small scalar census needed in the output, then release
    # class-side and prefix intermediates before full-physical diagnostics.
    physical_info_count = len(physical_infos)
    physical_action_slots = sum(physical_infos.values())
    physical_prefix_edges = sum(map(len, physical_edges.values()))
    physical_node_count = len(physical_nodes)
    physical_tree_actions = sum(len(node.actions) for node in physical_nodes.values())
    del physical_edges, physical_marginals, class_edges, class_marginals
    del physical_hand_counts, class_hand_counts, physical_legal, compact_legal
    del compact_averages, class_worlds, compact_root, compact_nodes
    del compact_infos, compact_metadata, physical_infos, physical_metadata
    del physical_nodes

    value, br0, br1 = evaluate_profile(physical_root, physical_worlds, lifted,
                                       pot=config.pot, chance_type=_Chance)
    if not all(math.isfinite(x) for x in (value, br0, br1)):
        raise ValueError("physical diagnostics returned nonfinite values")
    tolerance = 1e-10 * max(1.0, config.pot, abs(value), abs(br0), abs(br1))
    if br0 < value - tolerance or br1 < -value - tolerance:
        raise RuntimeError("physical best responses violate legal response bounds")
    oop_gain, ip_gain = max(0.0, br0 - value), max(0.0, br1 + value)
    nash_conv = oop_gain + ip_gain
    exploitability = nash_conv / 2.0
    if not all(math.isfinite(x) for x in (oop_gain, ip_gain, nash_conv, exploitability)):
        raise ValueError("derived diagnostics are nonfinite")
    avg_weight = iterations * (iterations + 1) // 2 - discard * (discard + 1) // 2
    result = {
        "method": "Direct original-weight CFR+ tail averaging on seven exact public-river classes",
        "algorithm": "cfrplus", "solver_version": SOLVER_VERSION,
        "strategy_schema": "postflop-strategy-v1",
        "backend": "exact-public-chance-tree",
        "execution_backend": "direct-original-weight-seven-class-tail-python",
        "diagnostics_backend": "public-batched-python",
        "board": list(board), "config": config.to_dict(),
        "street_configs": {"turn": config.to_dict(), "river": config.to_dict()},
        "turn_config": config.to_dict(), "river_config": config.to_dict(),
        "runouts": list(selected), "reachable_runouts": list(selected),
        "runout_mode": "full-deck",
        "chance_note": "Class masses derive from the original rational joint law; all 48 physical rivers are restored in the output policy.",
        "iterations": iterations, "requested_iterations": iterations,
        "discard": discard, "source_iteration_window": [discard + 1, iterations],
        "averaged_sweeps": iterations - discard,
        "average_weight_sum": avg_weight,
        "average_schedule": "direct-original-linear-sweep-weight-own-reach-tail",
        "update_schedule": "alternating-oop-then-ip",
        "requested_regret_passes": 2 * iterations,
        "requested_average_passes": iterations - discard,
        "requested_total_traversal_passes": 3 * iterations - discard,
        "deals": pair_count, "compatible_pairs": pair_count,
        "worlds": len(physical_worlds), "worlds_materialized": len(physical_worlds),
        "info_sets": physical_info_count, "public_nodes": physical_node_count,
        "public_states": physical_counts["total"],
        "terminal_nodes": physical_counts["terminal"], "chance_nodes": physical_chance_nodes,
        "world_traversal_nodes": physical_visited,
        "tree_actions": physical_tree_actions,
        "public_state_limit": _MAX_PUBLIC_STATES,
        "public_node_limit": _MAX_PUBLIC_NODES,
        "public_batch_edge_limit": MAX_PREFIX_EDGES,
        "resource_model": plan["resource_model"],
        "resource_usage": {
            "ordinary_physical_reference": {
                "world_node_work": physical_world_work,
                "world_node_work_limit": _MAX_WORLD_NODE_WORK,
                "world_node_work_would_admit": physical_world_work <= _MAX_WORLD_NODE_WORK,
                "dense_hand_state_pass_work": dense_work,
                "dense_hand_state_pass_work_limit": MAX_DENSE_HAND_STATE_PASS_WORK,
                "dense_hand_state_pass_work_would_admit": dense_work <= MAX_DENSE_HAND_STATE_PASS_WORK,
                "enforced": False,
            },
            "info_action_slots": physical_action_slots,
            "info_action_slots_limit": MAX_INFO_ACTION_SLOTS,
            "prefix_hand_edges": physical_prefix_edges,
            "prefix_hand_edge_limit": MAX_PREFIX_EDGES,
            "physical_world_iterations": plan["physical_world_iterations"],
            "candidate_pair_iterations": plan["candidate_pair_iterations"],
            "compact_world_proxy": plan["compact_world_proxy"],
            "compact_dense_proxy": plan["compact_dense_proxy"],
            "legacy_physical_world_proxy": plan["legacy_physical_world_proxy"],
            "legacy_proxy_enforced": False,
            "trainer_vector_work": plan["trainer_vector_work"],
            "complete_vector_work": plan["complete_vector_work"],
            "one_time_work_reserve": plan["one_time_work_reserve"],
            "explicit_list_writes": plan["explicit_list_writes"],
            "component_charge_note": "Component allowances are source-derived modeled work reservations; observed counts contain adapter-owned logical traversal counts only. Neither is measured runtime, bytes, or RSS.",
        },
        "physical_representation": {"worlds": 396, "rivers": 48, "public_states": 3039,
                                    "policy_rows": 3606, "action_slots": 8046},
        "training_representation": {"worlds": 45, "river_classes": 7,
                                    "public_states": 456, "policy_rows": 486,
                                    "action_slots": 1086},
        "modeled_rank_inputs": plan["modeled_rank_inputs"],
        "modeled_rank_loop_cells": plan["modeled_rank_loop_cells"],
        "pot": config.pot, "effective_stack": config.to_dict()["effective_stack"],
        "value_oop": value, "value_ip": -value,
        "oop_best_response_value": br0, "ip_best_response_value": br1,
        "oop_best_response_gain": oop_gain, "ip_best_response_gain": ip_gain,
        "nash_conv": nash_conv, "exploitability": exploitability,
        "scope": SCOPE, "diagnostic_provenance": DIAGNOSTIC_PROVENANCE,
        "training_calls": 1, "strategy": strategy_rows,
    }
    result["resource_usage"]["resource_accounting"] = phase.verify()
    return result
