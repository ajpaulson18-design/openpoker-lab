"""Independent rank-free PROOF9 geometry for frozen-grid update preflight.

This module counts literal numeric-template occurrences and physical support
for each visible prefix. It does not build card ranks, payoff tables, native
forecast objects, or update values.
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations, permutations

from tests.full_deck_public_chance_reference import PROOF9
from tests.virtual_betting_template_reference import build_reference_template
from tests.virtual_frozen_update_reference import _template_case, scaled_proof9_ranges


STREETS = (0, 3, 4, 5)
_RANGES = scaled_proof9_ranges()
_HAND_SETS = tuple(tuple(frozenset(hand) for hand, _weight in side)
                   for side in _RANGES)


def boards():
    """Yield all 2,520 canonical flops with ordered turn and river cards."""
    for flop in combinations(PROOF9, 3):
        remaining = tuple(card for card in PROOF9 if card not in flop)
        for turn, river in permutations(remaining, 2):
            yield (*flop, turn, river)


def _validate_board(board):
    if (type(board) is not tuple or len(board) != 5 or
            any(type(card) is not int or card not in PROOF9 for card in board) or
            tuple(sorted(board[:3])) != board[:3] or
            len(set(board)) != 5):
        raise ValueError("board must be a canonical PROOF9 flop and ordered turn/river")


def _prefix_support(prefix):
    """Return per-seat positive own-holding support from compatible pair mass."""
    blocked = frozenset(prefix)
    supported = []
    for actor in (0, 1):
        opponent_hands = _HAND_SETS[1 - actor]
        actor_support = []
        for hand_index, own_hand in enumerate(_HAND_SETS[actor]):
            mass = 0
            if not (blocked & own_hand):
                for opponent, (_opponent_ids, weight) in zip(opponent_hands, _RANGES[1 - actor]):
                    if not (blocked & opponent) and not (own_hand & opponent):
                        # Sum exact joint pair mass; both range weights are
                        # positive, so this is the joint law's support test.
                        own_weight = _RANGES[actor][hand_index][1]
                        mass += own_weight * weight
            actor_support.append(mass > 0)
        supported.append(tuple(actor_support))
    return tuple(supported)


def _geometry():
    template = build_reference_template(_template_case())
    counts = {
        street: {
            "decision_occurrences": [0, 0],
            "decision_action_slots": 0,
            "decision_action_slots_by_actor": [0, 0],
            "reveals": 0,
            "folds": 0,
            "showdowns": 0,
        }
        for street in STREETS
    }
    occurrence_count = 0

    def visit(node_id, past, total_decisions):
        nonlocal occurrence_count
        occurrence_count += 1
        node = template.nodes[node_id]
        street = node.street if node.phase != "reveal" else node.state.board_length
        row = counts[street]
        next_past = list(past)
        next_total = total_decisions
        if node.phase == "decision":
            actor = node.state.player
            row["decision_occurrences"][actor] += 1
            row["decision_action_slots"] += len(node.edges)
            row["decision_action_slots_by_actor"][actor] += len(node.edges)
            next_past[actor] += 1
            next_total += 1
        elif node.phase == "reveal":
            row["reveals"] += 1
        elif node.phase == "fold":
            row["folds"] += 1
        elif node.phase == "showdown":
            row["showdowns"] += 1
        for edge in node.edges:
            visit(edge.child, tuple(next_past), next_total)

    visit(template.root, (0, 0), 0)

    route_maxima = [0, 0]
    max_total = 0
    target_mix_same_actor_suffix_max = 0
    target_mix_all_future_max = 0

    def routes(node_id, actors):
        nonlocal max_total, target_mix_same_actor_suffix_max, target_mix_all_future_max
        node = template.nodes[node_id]
        if node.phase == "decision":
            actor = node.state.player
            next_actors = actors + (actor,)
        else:
            next_actors = actors
        if not node.edges:
            actor_counts = Counter(next_actors)
            max_total = max(max_total, len(next_actors))
            for actor in (0, 1):
                route_maxima[actor] = max(route_maxima[actor], actor_counts[actor])
            # At every target decision on this completed route, count the
            # opponent decisions before it and target decisions after it.
            for index, actor in enumerate(next_actors):
                target_mix_same_actor_suffix_max = max(
                    target_mix_same_actor_suffix_max,
                    sum(previous != actor for previous in next_actors[:index]) +
                    sum(future == actor for future in next_actors[index + 1:]),
                )
                target_mix_all_future_max = max(
                    target_mix_all_future_max,
                    sum(previous != actor for previous in next_actors[:index]) +
                    len(next_actors[index + 1:]),
                )
            return
        for edge in node.edges:
            routes(edge.child, next_actors)

    routes(template.root, ())
    if occurrence_count != 1105:
        raise ArithmeticError("literal occurrence census differs from PROOF9 contract")
    if (route_maxima != [6, 7] or max_total != 12 or
            target_mix_all_future_max > 11):
        raise ArithmeticError("decision-depth or target-mixture bound differs")
    return {
        "literal_occurrences": occurrence_count,
        "by_street": counts,
        "max_actor_decisions": tuple(route_maxima),
        "max_total_decisions": max_total,
        "max_opponent_past_plus_target_future_excluding_current": target_mix_same_actor_suffix_max,
        "max_opponent_past_plus_all_future_decisions_excluding_current": target_mix_all_future_max,
        "template_nodes": len(template.nodes),
        "template_edges": template.receipt["edges"],
    }


_GEOMETRY = None


def geometry():
    """Return the immutable public betting geometry report."""
    global _GEOMETRY
    if _GEOMETRY is None:
        _GEOMETRY = _geometry()
    return _GEOMETRY


def census(board):
    """Census supported rows/slots for one canonical complete board.

    Prefix support is computed from exact positive compatible-pair range mass,
    independently for each actor and original holding. A full-board zero does
    not erase support at the flop, turn, or river prefix.
    """
    _validate_board(board)
    report = geometry()
    prefixes = {0: (), 3: board[:3], 4: board[:4], 5: board}
    support = {length: _prefix_support(prefix) for length, prefix in prefixes.items()}
    by_street = {}
    total_rows = total_slots = 0
    for street in STREETS:
        item = report["by_street"][street]
        hand_support = support[street]
        rows = sum(item["decision_occurrences"][actor] * sum(hand_support[actor])
                   for actor in (0, 1))
        slots = sum(item["decision_action_slots_by_actor"][actor] *
                    sum(hand_support[actor]) for actor in (0, 1))
        by_street[street] = {
            "supported_rows": rows,
            "supported_action_slots": slots,
            "supported_holding_counts": tuple(sum(hand_support[actor]) for actor in (0, 1)),
        }
        total_rows += rows
        total_slots += slots
    zero_full_positive_prefix = []
    full_support = support[5]
    for actor in (0, 1):
        for holding in range(len(_HAND_SETS[actor])):
            if not full_support[actor][holding] and any(
                    support[length][actor][holding] for length in (0, 3, 4)):
                zero_full_positive_prefix.append((actor, holding))
    return {
        "board": board,
        "by_street": by_street,
        "supported_rows": total_rows,
        "supported_action_slots": total_slots,
        "full_board_supported_holdings": tuple(tuple(x) for x in full_support),
        "full_target_positive": any(any(side) for side in full_support),
        "positive_prefix_lengths_by_actor_holding": tuple(
            tuple(tuple(length for length in (0, 3, 4, 5)
                        if support[length][actor][holding])
                  for holding in range(len(_HAND_SETS[actor])))
            for actor in (0, 1)),
        "zero_full_board_positive_prefix_holdings": tuple(zero_full_positive_prefix),
        "zero_full_target_with_positive_prefix": (
            not any(any(side) for side in full_support) and bool(zero_full_positive_prefix)),
    }


def dense_public_census():
    """Return the independent rank-free dense public catalog shape.

    Proposal outcomes are grouped by their visible card prefix. Support is
    computed from exact compatible private-pair mass; this never enumerates
    physical worlds or evaluates card ranks/payoffs.
    """
    prefix_groups = {length: set() for length in (0, 3, 4, 5)}
    prefix_groups[0].add(())
    for board in boards():
        prefix_groups[3].add(board[:3])
        prefix_groups[4].add(board[:4])
        prefix_groups[5].add(board)

    supported_prefix_counts = {length: 0 for length in (0, 3, 4, 5)}
    supported_hands = {
        length: [[0] * len(_HAND_SETS[actor]) for actor in (0, 1)]
        for length in (0, 3, 4, 5)
    }
    for length, prefixes in prefix_groups.items():
        for prefix in prefixes:
            support = _prefix_support(prefix)
            if any(any(side) for side in support):
                supported_prefix_counts[length] += 1
            for actor in (0, 1):
                for hand_index, positive in enumerate(support[actor]):
                    supported_hands[length][actor][hand_index] += int(positive)

    prefixes_by_street = {length: len(prefix_groups[length])
                          for length in (0, 3, 4, 5)}
    if prefixes_by_street != {0: 1, 3: 84, 4: 504, 5: 2520}:
        raise ArithmeticError("proposal prefix grouping differs from the fixed PROOF9 geometry")

    template = build_reference_template(_template_case())
    shape = Counter()
    visible_phase = {
        street: Counter() for street in (0, 3, 4, 5)
    }

    def visit(node_id):
        node = template.nodes[node_id]
        street = node.street
        prefix_count = supported_prefix_counts[street]
        shape["visits"] += prefix_count
        visible_phase[street][node.phase] += prefix_count
        if node.phase == "decision":
            actor = node.state.player
            menu = len(node.edges)
            shape["actions"] += prefix_count * menu
            rows = sum(supported_hands[street][actor])
            shape["rows"] += rows
            shape["slots"] += rows * menu
        elif node.phase == "reveal":
            next_street = node.state.board_length
            shape["reveals"] += supported_prefix_counts[next_street]
            candidates = {0: 84, 3: 6, 4: 5}.get(street)
            if candidates is None:
                raise ArithmeticError("unexpected visible street at reveal")
            shape["candidates"] += prefix_count * candidates
        elif node.phase == "fold":
            shape["folds"] += prefix_count
        elif node.phase == "showdown":
            shape["showdowns"] += prefix_count
        else:
            raise ArithmeticError("unknown numeric-template phase")
        for edge in node.edges:
            visit(edge.child)

    visit(template.root)
    expected = {
        "visits": 61099, "actions": 57363, "reveals": 3735,
        "candidates": 15662, "folds": 16631, "showdowns": 17356,
        "rows": 24420, "slots": 58164,
    }
    result_shape = {key: shape[key] for key in expected}
    if result_shape != expected:
        raise ArithmeticError("independent dense public census differs from the pinned catalog geometry")
    return {
        "shape": result_shape,
        "prefix_counts": prefixes_by_street,
        "positive_joint_mass_prefix_counts": dict(supported_prefix_counts),
        "positive_own_holding_prefix_counts": {
            length: tuple(tuple(side) for side in supported_hands[length])
            for length in (0, 3, 4, 5)
        },
        "by_visible_street": {
            street: dict(counts) for street, counts in visible_phase.items()
        },
        "literal_occurrences": template.receipt["logical_occurrences"],
        "scope": "rank-free dense public catalog geometry; no native forecast or physical world enumeration",
    }
