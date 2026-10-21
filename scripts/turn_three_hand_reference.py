"""Independent fixed physical reference for the three-hand raised TURN game.

This module constructs one literal 3x3 weighted fixture. It imports only the
independent numeric rules and their exhaustive best-five ranker.
It does not import or invoke a production solver or trainer.
"""
from collections import defaultdict
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from itertools import product
import json

from scripts import turn_river_validation as rules


FIXTURE = {
    "id": "turn-three-hand-physical-v1",
    "board": "Js8d4c2h",
    "oop": "AsAh:0.5,KsKh:1,QsQh:0.75",
    "ip": "AcAd:1,KcKd:0.75,QcQd:0.5",
    "config": {
        "pot": 100.0,
        "effective_stack": 220.0,
        "bet_sizes": [0.5],
        "raise_sizes": [0.5],
        "max_raises": 1,
        "include_all_in": False,
    },
}
EXPECTED_TREE_SHA256 = "70d87064c6d7048b75784b6623a2dc6249f57ac61384a27d1724c3d53563bd61"
EXPECTED_PAIR_MASS_NUMERATORS = (
    (8, 6, 4),
    (16, 12, 8),
    (12, 9, 6),
)
EXPECTED_PAIR_NAMES = ("AA", "KK", "QQ")
EXPECTED_PAIR_RANKS = (14, 13, 12)

CANDIDATE_PAIRS = 9
CANDIDATE_PAIR_RIVER_SLOTS = 432
EXPECTED_WORLDS = 396
EXPECTED_RIVERS = 48
EXPECTED_OWN_RIVERS = 46
RIVERS_PER_PAIR = 44
EXPECTED_PUBLIC_NODES = 3_039
EXPECTED_DECISIONS = 1_254
EXPECTED_TERMINALS = 1_780
EXPECTED_CHANCE_NODES = 5
EXPECTED_CHANCE_EDGES = 240
EXPECTED_DECISION_EDGES = 2_798
EXPECTED_DEPTH = 9
EXPECTED_ROWS = 3_606
EXPECTED_ACTION_SLOTS = 8_046
EXPECTED_INITIAL_RANK_CALLS = 792

METRICS = (
    "value_oop",
    "value_ip",
    "oop_best_response_value",
    "ip_best_response_value",
    "oop_best_response_gain",
    "ip_best_response_gain",
    "nash_conv",
    "exploitability",
)
PLAYERS = ("oop", "ip")
RANKS = {rank: index for index, rank in enumerate("23456789TJQKA", 2)}


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def structure(node):
    if isinstance(node, rules._Terminal):
        return ["terminal", node.kind, node.winner, list(node.contributions)]
    if isinstance(node, rules._Chance):
        return ["chance", list(node.history),
                [[river, structure(child)] for river, child in sorted(node.branches.items())]]
    _need(isinstance(node, rules._Decision), "Unknown public-tree node")
    return [
        "decision", node.player, list(node.history), list(node.board),
        [[action.name, action.token, action.amount, action.raise_to, structure(child)]
         for action, child in zip(node.actions, node.children)],
    ]


def _tree_census(root):
    nodes = decisions = terminals = chance_nodes = chance_edges = decision_edges = deepest = 0
    pending = [(root, 1)]
    while pending:
        node, depth = pending.pop()
        nodes += 1
        deepest = max(deepest, depth)
        _need(nodes <= EXPECTED_PUBLIC_NODES and depth <= EXPECTED_DEPTH,
              "Public tree exceeds fixed structural bound")
        if isinstance(node, rules._Decision):
            decisions += 1
            decision_edges += len(node.children)
            _need(len(node.actions) == len(node.children) and 0 < len(node.actions) <= 3,
                  "Malformed decision action/child structure")
            pending.extend((child, depth + 1) for child in node.children)
        elif isinstance(node, rules._Chance):
            chance_nodes += 1
            chance_edges += len(node.branches)
            _need(0 < len(node.branches) <= EXPECTED_RIVERS,
                  "Malformed or oversized chance branch set")
            pending.extend((child, depth + 1) for child in node.branches.values())
        else:
            _need(isinstance(node, rules._Terminal), "Unknown public-tree node")
            terminals += 1
    census = {
        "public_nodes": nodes,
        "public_decisions": decisions,
        "terminal_nodes": terminals,
        "chance_nodes": chance_nodes,
        "chance_edges": chance_edges,
        "decision_edges": decision_edges,
        "depth": deepest,
    }
    expected = {
        "public_nodes": EXPECTED_PUBLIC_NODES,
        "public_decisions": EXPECTED_DECISIONS,
        "terminal_nodes": EXPECTED_TERMINALS,
        "chance_nodes": EXPECTED_CHANCE_NODES,
        "chance_edges": EXPECTED_CHANCE_EDGES,
        "decision_edges": EXPECTED_DECISION_EDGES,
        "depth": EXPECTED_DEPTH,
    }
    _need(census == expected, "Public tree fixed census differs")
    return census


def _pair_label(hand):
    ranks = sorted((RANKS[card[0]] for card in hand), reverse=True)
    _need(ranks[0] == ranks[1] and ranks[0] in EXPECTED_PAIR_RANKS,
          "Fixture contains an unexpected private hand")
    return EXPECTED_PAIR_NAMES[EXPECTED_PAIR_RANKS.index(ranks[0])]


def _world_key(world):
    return (tuple(tuple(hand) for hand in world["hands"]), world["river"])


def _pair_summaries(worlds, board):
    grouped = defaultdict(list)
    pair_mass = defaultdict(Fraction)
    for world in worlds:
        pair = world["hands"]
        grouped[pair].append(world["sign"])
        pair_mass[pair] += world["weight"]
    _need(len(grouped) == CANDIDATE_PAIRS, "Pair support differs")
    expected_rivers = set(rules.DECK) - set(board)
    rows = []
    mass_matrix = []
    for oop_name, oop_rank in zip(EXPECTED_PAIR_NAMES, EXPECTED_PAIR_RANKS):
        mass_row = []
        for ip_name, ip_rank in zip(EXPECTED_PAIR_NAMES, EXPECTED_PAIR_RANKS):
            pair = next(pair for pair in grouped
                        if _pair_label(pair[0]) == oop_name
                        and _pair_label(pair[1]) == ip_name)
            signs = grouped[pair]
            wins, ties, losses = signs.count(1), signs.count(0), signs.count(-1)
            law = ((0, 44, 0) if oop_rank == ip_rank else
                   (42, 0, 2) if oop_rank > ip_rank else (2, 0, 42))
            _need((wins, ties, losses) == law, "Pair/rivers showdown law differs")
            rivers = {world["river"] for world in worlds if world["hands"] == pair}
            legal = expected_rivers - set(pair[0]) - set(pair[1])
            _need(len(rivers) == RIVERS_PER_PAIR and rivers == legal,
                  "Pair has missing, duplicate, or illegal river support")
            mass = pair_mass[pair]
            mass_row.append(mass)
            rows.append({"oop": "".join(pair[0]), "ip": "".join(pair[1]),
                         "mass_fraction": str(mass),
                         "world_mass_fraction": str(mass / RIVERS_PER_PAIR),
                         "rivers": RIVERS_PER_PAIR, "wins": wins,
                         "ties": ties, "losses": losses})
        mass_matrix.append(mass_row)
    expected = [[Fraction(value, 81) for value in row]
                for row in EXPECTED_PAIR_MASS_NUMERATORS]
    _need(mass_matrix == expected, "Literal pair-mass matrix differs")
    rows.sort(key=lambda row: (row["oop"], row["ip"]))
    return rows


def _construct_model():
    fixture = deepcopy(FIXTURE)
    board = rules.cards(fixture["board"])
    _need(len(board) == 4 and len(set(board)) == 4, "Fixed turn board is malformed")
    config = rules._config(fixture["config"], "config")
    oop_range = rules.expand_range(fixture["oop"], board)
    ip_range = rules.expand_range(fixture["ip"], board)
    _need(len(oop_range) == len(ip_range) == 3,
          "Fixture private ranges must each contain three hands")
    selected = tuple(card for card in rules.DECK if card not in board)
    _need(len(selected) == EXPECTED_RIVERS, "Fixed river support differs")
    pairs = [(h0, h1) for h0, h1 in product(oop_range, ip_range)
             if not set(h0) & set(h1)]
    _need(len(pairs) == CANDIDATE_PAIRS, "Candidate pair count differs")
    slots = len(pairs) * len(selected)
    _need(slots == CANDIDATE_PAIR_RIVER_SLOTS,
          "Candidate pair/river slots differ before ranking")
    planned = sum(1 for h0, h1 in pairs for river in selected
                  if river not in set(h0) | set(h1))
    _need(planned == EXPECTED_WORLDS,
          "Accepted physical worlds differ before ranking")

    # This independent rules routine performs two actual seven-card ranks for
    # each accepted world. The fixed preflight above runs before those calls.
    worlds, actual_selected = rules._worlds(board, (oop_range, ip_range), None)
    _need(tuple(actual_selected) == selected and len(worlds) == EXPECTED_WORLDS,
          "Independent world builder returned unexpected support")
    _need(len({_world_key(world) for world in worlds}) == EXPECTED_WORLDS,
          "Independent world builder returned duplicate physical worlds")
    _need(sum((world["weight"] for world in worlds), Fraction(0)) == 1,
          "Original physical world mass is not one")
    _need({world["river"] for world in worlds} == set(selected),
          "Physical worlds do not cover every public river")
    pair_rows = _pair_summaries(worlds, board)
    root = rules._public_tree(board, config, config, selected, worlds)
    census = _tree_census(root)
    tree_hash = sha256(_canonical(structure(root))).hexdigest()
    _need(tree_hash == EXPECTED_TREE_SHA256, "Fixed public-tree hash differs")
    _need(census["chance_edges"] == 240, "Chance edge support differs")
    decision_edges = sum(len(node.actions) for node in rules._collect_nodes(root)
                         if isinstance(node, rules._Decision))
    _need(decision_edges == EXPECTED_DECISION_EDGES,
          "Public decision-edge count differs")
    return (fixture, board, config, worlds, selected, root, pair_rows), {
        "initial_seven_card_calls": 2 * len(worlds),
        "initial_five_card_calls": EXPECTED_INITIAL_RANK_CALLS * 21,
        "independent_showdown_sign_checks": len(worlds),
        **census, "public_tree_sha256": tree_hash,
    }


def validate_model(candidate):
    """Validate reused fixed model data without invoking a ranker."""
    _need(type(candidate) is tuple and len(candidate) == 7,
          "Model must be the seven-field fixed reference tuple")
    fixture, board, config, worlds, selected, root, pair_rows = candidate
    expected_fixture = deepcopy(FIXTURE)
    expected_board = rules.cards(FIXTURE["board"])
    expected_config = rules._config(FIXTURE["config"], "config")
    _need(_canonical(fixture) == _canonical(expected_fixture), "Model fixture identity differs")
    _need(type(board) is tuple and board == expected_board, "Model turn board differs")
    _need(type(config) is type(expected_config) and config == expected_config
          and config.to_dict() == expected_config.to_dict(),
          "Model betting configuration differs")
    expected_selected = tuple(card for card in rules.DECK if card not in expected_board)
    _need(type(selected) is tuple and selected == expected_selected,
          "Model selected river set/order differs")
    _need(type(worlds) is list and len(worlds) == EXPECTED_WORLDS,
          "Model physical world dimensions differ")
    oop_range = rules.expand_range(FIXTURE["oop"], expected_board)
    ip_range = rules.expand_range(FIXTURE["ip"], expected_board)
    compatible = [(h0, h1) for h0, h1 in product(oop_range, ip_range)
                  if not set(h0) & set(h1)]
    raw_masses = {(h0, h1): Fraction.from_float(float(oop_range[h0]))
                  * Fraction.from_float(float(ip_range[h1])) for h0, h1 in compatible}
    normalizer = sum(raw_masses.values(), Fraction(0))
    expected_world_keys = set()
    for pair, raw_mass in raw_masses.items():
        for river in expected_selected:
            if river in set(pair[0]) | set(pair[1]):
                continue
            expected_world_keys.add((pair, river))
    _need(len(expected_world_keys) == EXPECTED_WORLDS,
          "Literal fixed world support does not match the expected count")
    required_world_fields = {"hands", "river", "board", "weight", "sign"}
    observed_world_keys = set()
    pair_signs = defaultdict(list)
    for world in worlds:
        _need(type(world) is dict and set(world) == required_world_fields,
              "Malformed physical world")
        _need(type(world["hands"]) is tuple and len(world["hands"]) == 2
              and all(type(hand) is tuple and len(hand) == 2 for hand in world["hands"]),
              "Malformed private hand identity")
        _need(type(world["river"]) is str and type(world["board"]) is tuple
              and type(world["weight"]) is Fraction and type(world["sign"]) is int,
              "Malformed physical world values")
        pair, river = world["hands"], world["river"]
        key = (pair, river)
        _need(key not in observed_world_keys and key in expected_world_keys,
              "Model contains duplicate or unexpected physical world")
        observed_world_keys.add(key)
        _need(world["board"] == expected_board + (river,),
              "Physical world board differs from fixed turn plus river")
        _need(type(world["sign"]) is int and world["sign"] in (-1, 0, 1),
              "Physical world has invalid showdown sign")
        _need(world["weight"] == raw_masses[pair] / normalizer / RIVERS_PER_PAIR,
              "Physical world mass differs from original normalized joint mass")
        # On this literal rainbow J/8/4/2 board, only pairing the lower pocket
        # rank can reverse a non-tied pair. Check the specific river as well as
        # the aggregate 42/2 law, so swapping two signs cannot pass validation.
        rank0, rank1 = (RANKS[hand[0][0]] for hand in pair)
        if rank0 == rank1:
            expected_sign = 0
        elif RANKS[river[0]] == min(rank0, rank1):
            expected_sign = 1 if rank0 < rank1 else -1
        else:
            expected_sign = 1 if rank0 > rank1 else -1
        _need(world["sign"] == expected_sign,
              "Physical showdown sign differs on the specific river")
        pair_signs[pair].append(world["sign"])
    _need(observed_world_keys == expected_world_keys,
          "Model omits one or more legal physical worlds")
    for pair, signs in pair_signs.items():
        rank0 = EXPECTED_PAIR_RANKS[EXPECTED_PAIR_NAMES.index(_pair_label(pair[0]))]
        rank1 = EXPECTED_PAIR_RANKS[EXPECTED_PAIR_NAMES.index(_pair_label(pair[1]))]
        law = ((0, 44, 0) if rank0 == rank1 else
               (42, 0, 2) if rank0 > rank1 else (2, 0, 42))
        _need((signs.count(1), signs.count(0), signs.count(-1)) == law,
              "Pair signs violate the fixed showdown law")
    _need(type(pair_rows) is list and _canonical(pair_rows) == _canonical(_pair_summaries(worlds, expected_board)),
          "Model pair summary differs")
    candidate_census = _tree_census(root)
    candidate_hash = sha256(_canonical(structure(root))).hexdigest()
    expected_census = {
        "public_nodes": EXPECTED_PUBLIC_NODES,
        "public_decisions": EXPECTED_DECISIONS,
        "terminal_nodes": EXPECTED_TERMINALS,
        "chance_nodes": EXPECTED_CHANCE_NODES,
        "chance_edges": EXPECTED_CHANCE_EDGES,
        "decision_edges": EXPECTED_DECISION_EDGES,
        "depth": EXPECTED_DEPTH,
    }
    _need(candidate_census == expected_census, "Model tree census differs")
    _need(candidate_hash == EXPECTED_TREE_SHA256,
          "Reused model tree differs from the fixed literal structure")
    row_count = action_slots = 0
    for node in rules._collect_nodes(root):
        if not isinstance(node, rules._Decision):
            continue
        for hand in (oop_range, ip_range)[node.player]:
            if any(card in node.board for card in hand):
                continue
            row_count += 1
            action_slots += len(node.actions)
    _need(row_count == EXPECTED_ROWS and action_slots == EXPECTED_ACTION_SLOTS,
          "Private information/action slot census differs")
    return {
        "initial_seven_card_calls": EXPECTED_INITIAL_RANK_CALLS,
        "initial_five_card_calls": EXPECTED_INITIAL_RANK_CALLS * 21,
        "independent_showdown_sign_checks": EXPECTED_WORLDS,
        **candidate_census,
        "public_tree_sha256": candidate_hash,
        "policy_rows": row_count,
        "policy_action_slots": action_slots,
    }


def model():
    """Return the fixed validated model tuple."""
    candidate, _ = _construct_model()
    validate_model(candidate)
    return candidate


def _policy_rows(game):
    fixture, board, config, worlds, selected, root, _ = game
    rows = {}
    for node in rules._collect_nodes(root):
        for world in worlds:
            if world["board"][:len(node.board)] != node.board:
                continue
            hand = world["hands"][node.player]
            if set(hand) & set(node.board):
                continue
            key = (node.player, "".join(hand), node.history)
            if key in rows:
                continue
            rows[key] = {
                "player": PLAYERS[node.player],
                "hand": "".join(hand),
                "street": "turn" if len(node.board) == 4 else "river",
                "board": list(node.board),
                "history": list(node.history),
                "actions": [
                    {
                        "name": action.name,
                        "history_key": action.token,
                        "amount": action.amount,
                        "raise_to": action.raise_to,
                        "probability": 0.0,
                    }
                    for action in node.actions
                ],
            }
    _need(len(rows) == EXPECTED_ROWS, "Complete policy row census differs")
    _need(sum(len(row["actions"]) for row in rows.values()) == EXPECTED_ACTION_SLOTS,
          "Complete policy action slot census differs")
    return [rows[key] for key in sorted(rows)]


def _serialized_policy(game, chooser):
    fixture, board, config, worlds, selected, root, _ = game
    rows = _policy_rows(game)
    for row in rows:
        chosen = chooser(row)
        _need(type(chosen) is int and 0 <= chosen < len(row["actions"]),
              "Control policy selected an invalid action")
        for index, action in enumerate(row["actions"]):
            action["probability"] = float(index == chosen)
    result = {
        "board": list(board),
        "runouts": list(selected),
        "runout_mode": "full-deck",
        "reachable_runouts": sorted({world["river"] for world in worlds}),
        "strategy": rows,
        "info_sets": EXPECTED_ROWS,
        "compatible_world_count": EXPECTED_WORLDS,
        "compatible_pairs": CANDIDATE_PAIRS,
        "config": config.to_dict(),
        "turn_config": config.to_dict(),
        "river_config": config.to_dict(),
        "street_configs": {"turn": config.to_dict(), "river": config.to_dict()},
    }
    return result


def make_check_call_policy(game):
    validate_model(game)

    def choose(row):
        names = [action["name"] for action in row["actions"]]
        if "check" in names:
            return names.index("check")
        if "call" in names:
            return names.index("call")
        raise ValueError("Control game has no legal check or call action")

    return _serialized_policy(game, choose)


def make_uniform_policy(game):
    validate_model(game)
    result = _serialized_policy(game, lambda row: 0)
    for row in result["strategy"]:
        probability = 1.0 / len(row["actions"])
        for action in row["actions"]:
            action["probability"] = probability
    return result


def make_river_deviation_policy(game):
    validate_model(game)
    result = make_check_call_policy(game)
    target = None
    for row in result["strategy"]:
        if (row["player"] == "ip" and row["hand"] == "KcKd"
                and row["history"] == ["check", "check", "river@2c", "check"]):
            target = row
            break
    _need(target is not None, "Single-river deviation row is missing")
    bet_index = next((index for index, action in enumerate(target["actions"])
                      if action["history_key"] == "bet@50"), None)
    _need(bet_index is not None, "Single-river bet@50 action is missing")
    for index, action in enumerate(target["actions"]):
        action["probability"] = float(index == bet_index)
    return result


def _response_values_by_river(worlds):
    signed = defaultdict(lambda: defaultdict(lambda: defaultdict(Fraction)))
    for world in worlds:
        for player in (0, 1):
            signed[player][world["hands"][player]][world["river"]] += (
                world["weight"] * world["sign"]
            )
    return signed


def check_call_response_bounds(worlds):
    """Closed-form legal responses to the fixed always-check/call policy."""
    _need(type(worlds) is list and len(worlds) == EXPECTED_WORLDS,
          "Response formula requires the fixed 396-world game")
    _need(all(type(world["weight"]) is Fraction and type(world["sign"]) is int
              and world["sign"] in (-1, 0, 1) for world in worlds),
          "Response formula received malformed physical worlds")
    _need(sum((world["weight"] for world in worlds), Fraction(0)) == 1,
          "Response formula requires original global physical mass")
    signed = _response_values_by_river(worlds)
    bounds = []
    for player in (0, 1):
        choose = max if player == 0 else min
        value = Fraction(0)
        for hand, by_river in signed[player].items():
            _need(len(by_river) == EXPECTED_OWN_RIVERS,
                  "Own hand is missing a physically reachable river")
            # At each river, choose b=0 or b=50+t after aggregating hidden
            # opponent hands. Integrate those river values before choosing t.
            coefficient = sum(
                (mass + choose(Fraction(0), mass) for mass in by_river.values()),
                Fraction(0),
            )
            value += choose(50 * coefficient, 100 * coefficient)
        bounds.append(value if player == 0 else -value)
    _need(bounds == [Fraction(6_925, 891), Fraction(57_550, 891)],
          "Closed-form check/call response values differ from literal anchor")
    return tuple(bounds)


def future_aware_check_call_controls(worlds):
    """Return illegal turn BRs that see the hidden river before choosing t."""
    signed = _response_values_by_river(worlds)
    values = []
    for player in (0, 1):
        choose = max if player == 0 else min
        total = Fraction(0)
        for hand, by_river in signed[player].items():
            for mass in by_river.values():
                coefficient = mass + choose(Fraction(0), mass)
                total += choose(50 * coefficient, 100 * coefficient)
        values.append(total if player == 0 else -total)
    _need(values == [Fraction(875, 81), Fraction(58_775, 891)],
          "Future-aware negative-control values differ from fixed anchor")
    return tuple(values)


def reconstruct():
    """Return compact literal check/call evidence for the fixed physical game."""
    game = model()
    model_counters = validate_model(game)
    response = check_call_response_bounds(game[3])
    future = future_aware_check_call_controls(game[3])
    pair_value = sum(
        (world["weight"] * world["sign"] * Fraction(50) for world in game[3]),
        Fraction(0),
    )
    _need(pair_value == Fraction(-9_500, 891),
          "Check/call profile value differs from the literal anchor")
    check_call_metrics = {
        "value_oop": pair_value,
        "value_ip": -pair_value,
        "oop_best_response_value": response[0],
        "ip_best_response_value": response[1],
        "oop_best_response_gain": response[0] - pair_value,
        "ip_best_response_gain": response[1] + pair_value,
        "nash_conv": response[0] + response[1],
        "exploitability": (response[0] + response[1]) / 2,
    }
    _need(check_call_metrics == {
        "value_oop": Fraction(-9_500, 891),
        "value_ip": Fraction(9_500, 891),
        "oop_best_response_value": Fraction(6_925, 891),
        "ip_best_response_value": Fraction(57_550, 891),
        "oop_best_response_gain": Fraction(16_425, 891),
        "ip_best_response_gain": Fraction(48_050, 891),
        "nash_conv": Fraction(64_475, 891),
        "exploitability": Fraction(64_475, 1_782),
    }, "Check/call full metric anchor differs")

    result = {
        "training_calls": 0,
        "fixture": deepcopy(FIXTURE),
        "worlds": EXPECTED_WORLDS,
        "compatible_pairs": CANDIDATE_PAIRS,
        "public_rivers": EXPECTED_RIVERS,
        "public_nodes": model_counters["public_nodes"],
        "public_decisions": model_counters["public_decisions"],
        "terminal_nodes": model_counters["terminal_nodes"],
        "chance_nodes": model_counters["chance_nodes"],
        "chance_edges": model_counters["chance_edges"],
        "depth": model_counters["depth"],
        "policy_rows": EXPECTED_ROWS,
        "policy_action_slots": EXPECTED_ACTION_SLOTS,
        "initial_seven_card_calls": model_counters["initial_seven_card_calls"],
        "initial_five_card_calls": model_counters["initial_five_card_calls"],
        "independent_showdown_sign_checks": model_counters["independent_showdown_sign_checks"],
        "public_tree_sha256": model_counters["public_tree_sha256"],
        "check_call_metrics": check_call_metrics,
        "future_aware_controls": {
            "oop_best_response_value": future[0],
            "ip_best_response_value": future[1],
        },
    }
    return result
