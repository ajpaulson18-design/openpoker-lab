"""Separate exact full-physical policy and visible-information BR oracle.

This module does not import either fixed-game exact auditor, the sequence-form
certificate code, or a production best-response evaluator.  Its only input
structure is the independently rebuilt reference tree and the numeric rules'
row-legality checker.
"""
from fractions import Fraction
from collections import Counter
from functools import lru_cache
from itertools import combinations
import math

from scripts import turn_river_validation as rules


EXPECTED_WORLDS = 176
EXPECTED_RUNOUTS = 48
EXPECTED_DECISIONS = 1_254
EXPECTED_PUBLIC_NODES = 3_039
EXPECTED_DEPTH = 9
MAX_TREE_VISITS = 6 * EXPECTED_PUBLIC_NODES
MAX_WEIGHTED_ROW_OPERATIONS = 3 * EXPECTED_WORLDS * EXPECTED_PUBLIC_NODES
MAX_FRACTION_BITS = 65_536
PLAYERS = ("oop", "ip")
METRICS = (
    "value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value",
    "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability",
)
RANKS = {rank: index for index, rank in enumerate("23456789TJQKA", 2)}


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _measure(value, state):
    if not isinstance(value, Fraction):
        value = Fraction(value)
    bits = max(abs(value.numerator).bit_length(), value.denominator.bit_length())
    _need(bits <= MAX_FRACTION_BITS, "Fraction bit cap exceeded")
    state["max_fraction_bits"] = max(state["max_fraction_bits"], bits)
    return value


def _add(left, right, state):
    return _measure(left + right, state)


def _multiply(left, right, state):
    return _measure(left * right, state)


def _sum(values, state):
    total = Fraction(0)
    for value in values:
        total = _add(total, value, state)
    return total


def _rank_five(cards):
    """Independent lexicographic rank of a five-card poker hand."""
    _need(len(cards) == 5 and len(set(cards)) == 5, "Invalid five-card hand")
    ranks = [RANKS[card[0]] for card in cards]
    suits = [card[1] for card in cards]
    counts = Counter(ranks)
    groups = sorted(((count, rank) for rank, count in counts.items()), reverse=True)
    distinct = sorted(counts, reverse=True)
    straight_high = 0
    if len(distinct) == 5:
        if distinct[0] - distinct[-1] == 4:
            straight_high = distinct[0]
        elif distinct == [14, 5, 4, 3, 2]:
            straight_high = 5
    flush = len(set(suits)) == 1
    if flush and straight_high:
        return (8, straight_high)
    if groups[0][0] == 4:
        return (7, groups[0][1], groups[1][1])
    if [count for count, _ in groups] == [3, 2]:
        return (6, groups[0][1], groups[1][1])
    if flush:
        return (5, *sorted(ranks, reverse=True))
    if straight_high:
        return (4, straight_high)
    if groups[0][0] == 3:
        return (3, groups[0][1], *sorted((rank for rank in ranks
                                           if rank != groups[0][1]), reverse=True))
    if [count for count, _ in groups] == [2, 2, 1]:
        pairs = sorted((rank for count, rank in groups if count == 2), reverse=True)
        kicker = next(rank for count, rank in groups if count == 1)
        return (2, *pairs, kicker)
    if groups[0][0] == 2:
        pair = groups[0][1]
        return (1, pair, *sorted((rank for rank in ranks if rank != pair), reverse=True))
    return (0, *sorted(ranks, reverse=True))


@lru_cache(maxsize=176)
def _best_seven(cards):
    _need(len(cards) == 7 and len(set(cards)) == 7, "Invalid seven-card showdown")
    return max(_rank_five(combo) for combo in combinations(cards, 5))


def _independent_showdown_sign(world):
    board = tuple(world["board"])
    _need(len(board) == 5, "Showdown requires the complete five-card board")
    hands = world["hands"]
    oop = _best_seven(tuple(hands[0]) + board)
    ip = _best_seven(tuple(hands[1]) + board)
    return 1 if oop > ip else -1 if oop < ip else 0


def _player_id(label):
    if label == "oop":
        return 0
    if label == "ip":
        return 1
    raise ValueError("Unknown policy player")


def _hand_text(hand):
    return "".join(hand)


def _row_key(player, hand, history):
    return player, _hand_text(hand), tuple(history)


def _normalize_policy(result, model, state):
    fixture, board, config, worlds, selected, root, _ = model
    _need(len(worlds) == EXPECTED_WORLDS and len(selected) == EXPECTED_RUNOUTS,
          "Full physical model dimensions differ")
    _need(sum((world["weight"] for world in worlds), Fraction(0)) == 1,
          "Original physical mass is not one")

    # This call establishes only the complete legal row set and action metadata.
    # The returned float probabilities are intentionally discarded.
    nodes = rules._collect_nodes(root)
    _need(len(nodes) == EXPECTED_DECISIONS,
          "Independent structural decision count differs")
    rules._validate_policy(result, root, nodes, worlds, board, selected,
                           runouts_were_omitted=True)

    exact = {}
    adjustments = 0
    row_count = 0
    for row in result.get("strategy", ()):
        player = _player_id(row["player"])
        hand = row["hand"]
        history = tuple(row["history"])
        key = (player, hand, history)
        _need(key not in exact, "Duplicate exact policy row")
        source = []
        for action in row["actions"]:
            value = action.get("probability")
            _need(type(value) is float and math.isfinite(value) and 0.0 <= value <= 1.0,
                  "Policy probability must be a finite binary64 value in [0, 1]")
            source.append(_measure(Fraction.from_float(value), state))
        total = _sum(source, state)
        _need(total > 0, "Policy row has zero exact probability mass")
        normalized = tuple(_measure(value / total, state) for value in source)
        _need(_sum(normalized, state) == 1,
              "Exact normalized policy row does not sum to one")
        if normalized != tuple(source):
            adjustments += 1
        exact[key] = normalized
        row_count += 1
    _need(row_count == 2_404 and len(exact) == 2_404,
          "Policy does not contain all 2,404 physical information rows")

    expected = set()
    for node in nodes:
        for world in worlds:
            if world["board"][:len(node.board)] != node.board:
                continue
            hand = _hand_text(world["hands"][node.player])
            if not set(world["hands"][node.player]) & set(node.board):
                expected.add((node.player, hand, node.history))
    _need(set(exact) == expected, "Exact policy rows do not equal complete legal support")
    state["normalization_adjusted_rows"] = adjustments
    state["policy_rows"] = row_count
    return exact


def _utility(node, world, pot, state):
    half_pot = _measure(Fraction.from_float(float(pot)) / 2, state)
    matched = min(Fraction.from_float(float(node.contributions[0])),
                  Fraction.from_float(float(node.contributions[1])))
    if node.kind == "fold":
        sign = 1 if node.winner == 0 else -1
    else:
        sign = _independent_showdown_sign(world)
        _need(sign == world["sign"], "Independent showdown ranking disagrees with reference sign")
        state["independent_showdown_sign_checks"] += 1
    _need(type(sign) is int and sign in (-1, 0, 1), "Invalid independently checked terminal sign")
    return _measure(sign * _add(half_pot, _measure(matched, state), state), state)


def _check_tree(model):
    _, _, _, worlds, selected, root, _ = model
    nodes = decisions = deepest = 0
    chance_nodes = physical_chance_edges = 0

    def walk(node, depth):
        nonlocal nodes, decisions, deepest, chance_nodes, physical_chance_edges
        nodes += 1
        deepest = max(deepest, depth)
        _need(nodes <= EXPECTED_PUBLIC_NODES and depth <= EXPECTED_DEPTH,
              "Fixed public-tree structural bound exceeded")
        if isinstance(node, rules._Decision):
            decisions += 1
            _need(len(node.actions) == len(node.children) and len(node.actions) > 0,
                  "Decision action/child structure differs")
            for child in node.children:
                walk(child, depth + 1)
        elif isinstance(node, rules._Chance):
            chance_nodes += 1
            _need(set(node.branches) == set(selected), "Chance node lost physical river cards")
            physical_chance_edges += len(node.branches)
            for card in selected:
                walk(node.branches[card], depth + 1)
        else:
            _need(isinstance(node, rules._Terminal), "Unknown public-tree node")

    walk(root, 1)
    _need((nodes, decisions, deepest) ==
          (EXPECTED_PUBLIC_NODES, EXPECTED_DECISIONS, EXPECTED_DEPTH),
          "Fixed physical public-tree census differs")
    _need(len({world["river"] for world in worlds}) == EXPECTED_RUNOUTS,
          "Physical river support is incomplete")
    return {
        "public_nodes": nodes, "decision_nodes": decisions, "depth": deepest,
        "chance_nodes": chance_nodes,
        "physical_chance_edges": physical_chance_edges,
        "physical_runouts": len(selected), "physical_worlds": len(worlds),
    }


def _evaluate(result, model, state, *, kind, responder=None,
              future_aware_turn=False, hand_filter=None):
    _, _, config, worlds, _, root, _ = model
    policy = state["policy"]
    visits_key = "control_node_visits" if future_aware_turn else "structural_node_visits"
    operations_key = "control_weighted_row_operations" if future_aware_turn else "weighted_row_operations"
    visit_limit = (48 * 4 * EXPECTED_PUBLIC_NODES if future_aware_turn
                   else MAX_TREE_VISITS)

    def visit(node, batch):
        state[visits_key] += 1
        _need(state[visits_key] <= visit_limit,
              "Declared full physical traversal bound exceeded")
        if isinstance(node, rules._Terminal):
            return _sum((_multiply(mass, _utility(node, world, config.pot, state), state)
                         for world, mass in batch), state)

        if isinstance(node, rules._Chance):
            return _sum((visit(node.branches[card],
                               [(world, mass) for world, mass in batch
                                if world["river"] == card])
                         for card in sorted(node.branches)), state)

        if kind == "br" and node.player == responder:
            if future_aware_turn and len(node.board) == 4:
                # Deliberately illegal control: choose after separating the hidden
                # river before evaluating a turn action.
                by_river = []
                for card in sorted({world["river"] for world, _ in batch}):
                    river_batch = [(world, mass) for world, mass in batch
                                   if world["river"] == card]
                    action_values = [visit(child, river_batch) for child in node.children]
                    by_river.append(max(action_values) if responder == 0
                                    else min(action_values))
                return _sum(by_river, state)
            values = [visit(child, batch) for child in node.children]
            return max(values) if responder == 0 else min(values)

        action_batches = [[] for _ in node.children]
        if batch:
            for world, mass in batch:
                key = _row_key(node.player, world["hands"][node.player], node.history)
                probabilities = policy.get(key)
                _need(probabilities is not None,
                      "Policy row missing at a reachable full-physical information set")
                state[operations_key] += 1
                _need(state[operations_key] <= MAX_WEIGHTED_ROW_OPERATIONS,
                      "Declared weighted-row operation bound exceeded")
                for index, probability in enumerate(probabilities):
                    if probability:
                        child_mass = _multiply(mass, probability, state)
                        action_batches[index].append((world, child_mass))
        values = [visit(child, action_batches[index])
                  for index, child in enumerate(node.children)]
        return _sum(values, state)

    actor_hands = sorted({world["hands"][responder] for world in worlds}) if kind == "br" else \
        sorted({world["hands"][0] for world in worlds})
    results = []
    for hand in actor_hands:
        if hand_filter is not None and hand != hand_filter:
            continue
        batch = [(world, _measure(world["weight"], state)) for world in worlds
                 if world["hands"][responder if kind == "br" else 0] == hand]
        results.append(visit(root, batch))
    return _sum(results, state)


def audit_policy(result, model):
    """Return exact eight-metric full-physical replay and legal own-hand BRs."""
    tree = _check_tree(model)
    state = {
        "policy": {}, "max_fraction_bits": 0, "normalization_adjusted_rows": 0,
        "policy_rows": 0, "structural_node_visits": 0,
        "weighted_row_operations": 0, "control_node_visits": 0,
        "control_weighted_row_operations": 0,
        "independent_showdown_sign_checks": 0,
    }
    state["policy"] = _normalize_policy(result, model, state)
    value_oop = _evaluate(result, model, state, kind="profile")
    br_oop = _evaluate(result, model, state, kind="br", responder=0)
    min_oop = _evaluate(result, model, state, kind="br", responder=1)
    value_ip = _measure(-value_oop, state)
    br_ip = _measure(-min_oop, state)
    gain_oop = _measure(br_oop - value_oop, state)
    gain_ip = _measure(br_ip - value_ip, state)
    _need(gain_oop >= 0 and gain_ip >= 0, "Legal best-response bound is inconsistent")
    nash_conv = _measure(gain_oop + gain_ip, state)
    exploitability = _measure(nash_conv / 2, state)
    metrics = dict(zip(METRICS, (value_oop, value_ip, br_oop, br_ip,
                                 gain_oop, gain_ip, nash_conv, exploitability)))
    _need(state["structural_node_visits"] == MAX_TREE_VISITS,
          "Six per-own-hand structural traversals were not completed")
    _need(state["weighted_row_operations"] <= MAX_WEIGHTED_ROW_OPERATIONS,
          "Weighted-row operation count exceeds declared envelope")
    state.update(tree)
    state["chance_grouping"] = False
    state["maximum_weighted_row_operations"] = MAX_WEIGHTED_ROW_OPERATIONS
    state.pop("policy")
    return {"metrics": metrics, "counters": state}


def future_aware_best_response(result, model, responder):
    """Negative control that illegally reveals the future river at turn nodes."""
    _check_tree(model)
    state = {
        "policy": {}, "max_fraction_bits": 0,
        "normalization_adjusted_rows": 0, "policy_rows": 0,
        "structural_node_visits": 0, "weighted_row_operations": 0,
        "control_node_visits": 0, "control_weighted_row_operations": 0,
        "independent_showdown_sign_checks": 0,
    }
    state["policy"] = _normalize_policy(result, model, state)
    own_hands = sorted({world["hands"][responder] for world in model[3]})
    values = []
    for hand in own_hands:
        batch = [(world, _measure(world["weight"], state)) for world in model[3]
                 if world["hands"][responder] == hand]
        values.append(_evaluate(result, model, state, kind="br", responder=responder,
                                future_aware_turn=True, hand_filter=hand))
    oop_value = _sum(values, state)
    return oop_value if responder == 0 else _measure(-oop_value, state)


def make_check_call_policy(model):
    """Construct the handwritten exact anchor policy without solver helpers."""
    fixture, board, config, worlds, selected, root, _ = model
    rows = []

    def walk(node):
        if isinstance(node, rules._Decision):
            actor = PLAYERS[node.player]
            hands = sorted({_hand_text(world["hands"][node.player]) for world in worlds
                            if world["board"][:len(node.board)] == node.board and
                            not (set(world["hands"][node.player]) & set(node.board))})
            for hand in hands:
                actions = []
                chosen = next((i for i, action in enumerate(node.actions)
                               if action.name == "check"), None)
                if chosen is None:
                    chosen = next((i for i, action in enumerate(node.actions)
                                   if action.name == "call"), None)
                _need(chosen is not None, "Check/call anchor has no legal passive action")
                for index, action in enumerate(node.actions):
                    actions.append({
                        "name": action.name, "history_key": action.token,
                        "amount": action.amount, "raise_to": action.raise_to,
                        "probability": 1.0 if index == chosen else 0.0,
                    })
                rows.append({"player": actor, "hand": hand,
                             "street": "turn" if len(node.board) == 4 else "river",
                             "board": list(node.board), "history": list(node.history),
                             "actions": actions})
            for child in node.children:
                walk(child)
        elif isinstance(node, rules._Chance):
            for card in sorted(node.branches):
                walk(node.branches[card])
        else:
            _need(isinstance(node, rules._Terminal), "Unknown public-tree node")

    walk(root)
    return {
        "board": list(board), "runouts": list(selected), "runout_mode": "full-deck",
        "reachable_runouts": sorted({world["river"] for world in worlds}),
        "strategy": rows, "info_sets": len(rows),
        "compatible_world_count": len(worlds), "worlds": len(worlds),
        "compatible_pairs": 4, "deals": 4,
        "config": config.to_dict(), "river_config": config.to_dict(),
    }
