"""Fixed-game, no-training seven-class river quotient auditor.

This module is deliberately limited to the accepted three-hand turn fixture.
It requires successful full-physical numeric and exact replay before invoking
the generic exact evaluator on the internal class game. It is not a solver or
a general abstraction interface.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
import math
import struct

from scripts import turn_three_hand_reference as reference
from scripts import turn_three_hand_exact_oracle as physical_oracle
from scripts import turn_rational_certificate as generic_exact
from scripts import turn_river_validation as rules


EXPECTED_CLASS_CENSUS = {
    "public_nodes": 456,
    "public_decisions": 188,
    "terminal_nodes": 263,
    "chance_nodes": 5,
    "chance_edges": 35,
    "decision_edges": 420,
    "depth": 9,
    "policy_rows": 486,
    "policy_action_slots": 1_086,
    "pair_class_prefix_entries": 54,
    "physical_branch_subtrees_compared": 240,
}

_EXPECTED_CLASSES = {
    "2c": None,  # Neutral class, literal members checked by rank below.
    "Ac": ("Ac", "Ad"),
    "Ah": ("Ah", "As"),
    "Kc": ("Kc", "Kd"),
    "Kh": ("Kh", "Ks"),
    "Qc": ("Qc", "Qd"),
    "Qh": ("Qh", "Qs"),
}
_METRICS = reference.METRICS
_MAX_CLASS_WORLDS = 45
_MAX_CLASS_ROWS = 486
_MAX_CLASS_ACTION_SLOTS = 1_086
_MAX_PHYSICAL_ROWS = 3_606
_MAX_PHYSICAL_ACTION_SLOTS = 8_046
_MAX_AUDIT_WORK = 100_000
_MAX_AUDIT_DEPTH = 64
_MAX_FRACTION_BITS = 65_536


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _same_typed(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return (left.keys() == right.keys()
                and all(_same_typed(left[key], right[key]) for key in left))
    if type(left) in (list, tuple):
        return (len(left) == len(right)
                and all(_same_typed(a, b) for a, b in zip(left, right)))
    return left == right


@dataclass(frozen=True)
class ClassModel:
    """Fixed physical model plus its exact seven-class internal view."""

    physical: tuple
    river_class: dict
    class_members: tuple
    class_worlds: list
    class_root: object
    census: dict
    class_masses: dict


def _all_nodes(root, *, limit=3_039):
    pending = [(root, 1)]
    result = []
    deepest = 0
    while pending:
        node, depth = pending.pop()
        result.append(node)
        deepest = max(deepest, depth)
        _need(len(result) <= limit and depth <= 9, "Public tree exceeds fixed bound")
        if isinstance(node, rules._Decision):
            _need(0 < len(node.actions) <= 3 and len(node.actions) == len(node.children),
                  "Malformed decision node before traversal expansion")
            pending.extend((child, depth + 1) for child in node.children)
        elif isinstance(node, rules._Chance):
            _need(0 < len(node.branches) <= 48, "Malformed chance node before expansion")
            pending.extend((child, depth + 1) for child in node.branches.values())
        else:
            _need(isinstance(node, rules._Terminal), "Unknown public node")
    return result, deepest


def _census(root):
    nodes, depth = _all_nodes(root)
    decisions = [node for node in nodes if isinstance(node, rules._Decision)]
    chance = [node for node in nodes if isinstance(node, rules._Chance)]
    terminals = [node for node in nodes if isinstance(node, rules._Terminal)]
    decision_edges = sum(len(node.actions) for node in decisions)
    chance_edges = sum(len(node.branches) for node in chance)
    return {
        "public_nodes": len(nodes),
        "public_decisions": len(decisions),
        "terminal_nodes": len(terminals),
        "chance_nodes": len(chance),
        "chance_edges": chance_edges,
        "decision_edges": decision_edges,
        "depth": depth,
    }, nodes


def _class_groups(selected, worlds):
    signatures = {}
    for river in selected:
        rows = tuple(sorted((world["hands"], world["weight"], world["sign"])
                            for world in worlds if world["river"] == river))
        _need(rows, "Selected river has no physical support")
        signatures.setdefault(rows, []).append(river)
    groups = tuple(sorted((tuple(cards) for cards in signatures.values()),
                          key=lambda cards: cards[0]))
    _need(len(groups) == 7, "Fixed river signature partition must have seven classes")
    mapping = {card: group[0] for group in groups for card in group}
    expected = {}
    for representative, cards in _EXPECTED_CLASSES.items():
        if cards is None:
            neutral = tuple(card for card in selected if card[0] not in "AKQ")
            expected[representative] = neutral
        else:
            expected[representative] = cards
    _need({rep: tuple(group) for rep, group in zip((g[0] for g in groups), groups)} == expected,
          "Fixed class membership differs from literal blocker partition")
    _need(set(mapping) == set(selected) and len(mapping) == 48,
          "River class map omits or duplicates a physical card")
    return mapping, tuple((rep, expected[rep]) for rep in sorted(expected))


def _aggregate_worlds(board, worlds, river_class, class_members):
    accum = {}
    pair_counts = defaultdict(int)
    pair_mass = defaultdict(Fraction)
    for world in worlds:
        pair, river = world["hands"], world["river"]
        rep = river_class[river]
        key = (pair, rep)
        pair_counts[pair] += 1
        pair_mass[pair] += world["weight"]
        if key not in accum:
            accum[key] = {
                "hands": pair,
                "river": rep,
                "board": tuple(board) + (rep,),
                "weight": Fraction(0),
                "sign": world["sign"],
            }
        aggregate = accum[key]
        _need(aggregate["sign"] == world["sign"],
              "A class combines different showdown signs for a private pair")
        aggregate["weight"] += world["weight"]
    _need(len(accum) == 45, "Expected exactly 45 private-pair/class worlds")
    _need(set(pair_counts.values()) == {44}, "Every compatible pair must have 44 rivers")
    _need(all(type(world["weight"]) is Fraction and world["weight"] > 0
              for world in accum.values()), "Class aggregation has invalid mass")
    _need(sum((world["weight"] for world in accum.values()), Fraction(0)) == 1,
          "Aggregated original physical world mass must remain one")
    member_counts = {rep: len(cards) for rep, cards in class_members}
    for key, aggregate in accum.items():
        _need(member_counts[key[1]] in (2, 36), "Unexpected fixed class multiplicity")
        expected = pair_mass[key[0]] * member_counts[key[1]] / 44
        _need(aggregate["weight"] == expected,
              "Class mass differs from original pair mass times multiplicity/44")
    ordered = [accum[key] for key in sorted(accum)]
    return ordered, {rep: sum((w["weight"] for w in ordered if w["river"] == rep), Fraction(0))
                     for rep, _ in class_members}


def _map_history(history, river_class):
    return tuple("river@" + river_class[token[6:]] if token.startswith("river@") else token
                 for token in history)


def _mapped_structure(node, river_class):
    if isinstance(node, rules._Terminal):
        return ["terminal", node.kind, node.winner, list(node.contributions)]
    if isinstance(node, rules._Chance):
        return ["chance", list(_map_history(node.history, river_class)),
                [[river_class[river], _mapped_structure(child, river_class)]
                 for river, child in sorted(node.branches.items())]]
    _need(isinstance(node, rules._Decision), "Unknown node during subtree mapping")
    board = list(node.board)
    if len(board) == 5:
        board[-1] = river_class[board[-1]]
    return ["decision", node.player, list(_map_history(node.history, river_class)), board,
            [[action.name, action.token, action.amount, action.raise_to,
              _mapped_structure(child, river_class)]
             for action, child in zip(node.actions, node.children)]]


def _collapsed_structure(node, river_class):
    """Canonical whole-tree structure with equivalent chance branches collapsed."""
    if isinstance(node, rules._Terminal):
        return ["terminal", node.kind, node.winner, list(node.contributions)]
    if isinstance(node, rules._Decision):
        board = list(node.board)
        if len(board) == 5:
            board[-1] = river_class[board[-1]]
        return ["decision", node.player, list(_map_history(node.history, river_class)), board,
                [[action.name, action.token, action.amount, action.raise_to,
                  _collapsed_structure(child, river_class)]
                 for action, child in zip(node.actions, node.children)]]
    _need(isinstance(node, rules._Chance), "Unknown node during complete tree collapse")
    grouped = defaultdict(list)
    for river, child in node.branches.items():
        grouped[river_class[river]].append(_collapsed_structure(child, river_class))
    branches = []
    for representative in sorted(grouped):
        structures = grouped[representative]
        _need(all(item == structures[0] for item in structures[1:]),
              "Physical chance branches are not structurally equivalent within class")
        branches.append([representative, structures[0]])
    return ["chance", list(_map_history(node.history, river_class)), branches]


def _verify_subtrees(physical_root, class_root, river_class):
    physical_nodes, _ = _all_nodes(physical_root)
    class_nodes, _ = _all_nodes(class_root)
    physical_chance = [node for node in physical_nodes if isinstance(node, rules._Chance)]
    class_chance = {node.history: node for node in class_nodes if isinstance(node, rules._Chance)}
    _need(len(physical_chance) == len(class_chance) == 5,
          "Fixed physical/class chance-node counts differ")
    compared = 0
    for source in physical_chance:
        target = class_chance.get(source.history)
        _need(target is not None, "Class chance node missing matching public history")
        expected_reps = {river_class[river] for river in source.branches}
        _need(set(target.branches) == expected_reps,
              "Class chance edges do not preserve physical support")
        by_class = defaultdict(list)
        for river, child in source.branches.items():
            by_class[river_class[river]].append((river, child))
        for rep, branches in by_class.items():
            _need(rep in target.branches, "Representative branch missing from class tree")
            canonical = _mapped_structure(target.branches[rep], river_class)
            for river, child in branches:
                _need(_mapped_structure(child, river_class) == canonical,
                      "Physical branch subtree differs within river class")
                compared += 1
    _need(compared == 5 * 48, "Expected all 240 chance subtrees to be compared")
    _need(_collapsed_structure(physical_root, river_class) == reference.structure(class_root),
          "Whole physical public tree does not collapse to the class tree")
    return compared


def _policy_census(root, ranges):
    nodes = [node for node in _all_nodes(root)[0] if isinstance(node, rules._Decision)]
    rows = slots = 0
    for node in nodes:
        for hand in ranges[node.player]:
            if set(hand) & set(node.board):
                continue
            rows += 1
            slots += len(node.actions)
            _need(len(node.actions) <= 3, "Decision exceeds fixed action cap")
    return rows, slots


def _make_model(physical):
    reference.validate_model(physical)
    fixture, board, config, worlds, selected, physical_root, _ = physical
    _need(len(worlds) == 396 and len(selected) == 48, "Physical model dimensions differ")
    river_class, class_members = _class_groups(selected, worlds)
    class_worlds, class_masses = _aggregate_worlds(board, worlds, river_class, class_members)
    representatives = tuple(rep for rep, _ in class_members)
    class_root = rules._public_tree(board, config, config, representatives, class_worlds)
    class_census, _ = _census(class_root)
    ranges = (rules.expand_range(fixture["oop"], board),
              rules.expand_range(fixture["ip"], board))
    rows, slots = _policy_census(class_root, ranges)
    compared = _verify_subtrees(physical_root, class_root, river_class)
    census = {**class_census,
              "policy_rows": rows,
              "policy_action_slots": slots,
              "pair_class_prefix_entries": 9 + len(class_worlds),
              "physical_branch_subtrees_compared": compared}
    for key, expected in EXPECTED_CLASS_CENSUS.items():
        _need(census[key] == expected, f"Fixed class census differs: {key}")
    return ClassModel(physical, river_class, class_members, class_worlds,
                      class_root, census, class_masses)


def build_model(physical=None):
    """Build the only supported fixed-game quotient after physical validation."""
    game = reference.model() if physical is None else physical
    return _make_model(game)


def validate_model(candidate):
    """Re-derive and verify every fixed class invariant without ranking cards."""
    _need(type(candidate) is ClassModel, "Expected a fixed ClassModel")
    physical = candidate.physical
    reference.validate_model(physical)
    _need(type(candidate.class_worlds) is list and len(candidate.class_worlds) <= _MAX_CLASS_WORLDS,
          "Class world list exceeds fixed bound")
    _need(type(candidate.river_class) is dict and len(candidate.river_class) == 48,
          "River-class map has invalid dimensions")
    _need(type(candidate.class_members) is tuple and len(candidate.class_members) == 7,
          "Class member table has invalid dimensions")
    for world in candidate.class_worlds:
        _need(type(world) is dict and set(world) == {"hands", "river", "board", "weight", "sign"},
              "Malformed class world fields")
        _need(type(world["hands"]) is tuple and len(world["hands"]) == 2
              and all(type(hand) is tuple and len(hand) == 2 for hand in world["hands"]),
              "Malformed class-world private-hand identity")
        _need(type(world["river"]) is str and type(world["board"]) is tuple
              and type(world["weight"]) is Fraction and world["weight"] > 0
              and type(world["sign"]) is int and world["sign"] in (-1, 0, 1),
              "Malformed class-world values")
    _all_nodes(candidate.class_root, limit=456)
    _need(type(candidate.census) is dict
          and all(type(candidate.census.get(key)) is int for key in EXPECTED_CLASS_CENSUS),
          "Malformed class census types")
    _need(type(candidate.class_masses) is dict and
          all(type(value) is Fraction for value in candidate.class_masses.values()),
          "Malformed class mass summary")
    rebuilt = _make_model(physical)
    _need(candidate.river_class == rebuilt.river_class,
          "Mutated river class map differs from fixed signatures")
    _need(candidate.class_members == rebuilt.class_members,
          "Mutated class membership differs from fixed model")
    _need(candidate.class_worlds == rebuilt.class_worlds,
          "Mutated class-world support or original mass differs")
    _need(_same_typed(reference.structure(candidate.class_root),
                      reference.structure(rebuilt.class_root)),
          "Mutated class public tree differs from the fixed tree")
    _need(candidate.census == rebuilt.census and candidate.class_masses == rebuilt.class_masses,
          "Mutated class census or mass summary differs")
    return dict(rebuilt.census)


def _float_bits(value):
    if type(value) is not float or not math.isfinite(value):
        raise ValueError("Class projection requires finite original binary64 probabilities")
    return struct.pack(">d", value)


def _physical_policy_rows(payload, game):
    fixture, board, _config, worlds, selected, root, _summaries = game
    _need(type(payload) is dict and type(payload.get("strategy")) is list,
          "Complete physical policy is required")
    expected_config = reference.FIXTURE["config"]
    expected_reachable = [card for card in selected if card in {world["river"] for world in worlds}]
    _need(_same_typed(payload.get("board"), list(board))
          and _same_typed(payload.get("config"), expected_config)
          and payload.get("runouts") == list(selected)
          and payload.get("runout_mode") == "full-deck"
          and payload.get("reachable_runouts") in
          (expected_reachable, sorted(expected_reachable)),
          "Physical policy header differs from the fixed game")
    for name in ("turn_config", "river_config"):
        if name in payload:
            _need(_same_typed(payload[name], expected_config),
                  f"Physical policy {name} differs from the fixed game")
    if "street_configs" in payload:
        expected_streets = {"turn": expected_config, "river": expected_config}
        _need(_same_typed(payload["street_configs"], expected_streets),
              "Physical policy street configurations differ from the fixed game")
    for name, expected_value in (("pot", expected_config["pot"]),
                                 ("effective_stack", expected_config["effective_stack"])):
        if name in payload:
            _need(type(payload[name]) in (int, float) and type(payload[name]) is not bool
                  and float(payload[name]) == float(expected_value),
                  f"Physical policy {name} differs from the fixed game")
    _need(len(payload["strategy"]) == _MAX_PHYSICAL_ROWS,
          "Physical strategy row count differs from the fixed game")
    observed_slots = 0
    for row in payload["strategy"]:
        _need(type(row) is dict and set(row) ==
              {"player", "hand", "street", "board", "history", "actions"},
              "Malformed physical strategy row")
        _need(row["player"] in ("oop", "ip") and type(row["hand"]) is str
              and len(row["hand"]) == 4 and type(row["street"]) is str,
              "Malformed physical strategy identity")
        _need(type(row["board"]) is list and len(row["board"]) in (4, 5)
              and type(row["history"]) is list and len(row["history"]) <= 9,
              "Physical strategy board/history exceeds fixed bounds")
        _need(type(row["actions"]) is list and 0 < len(row["actions"]) <= 3,
              "Physical strategy action count exceeds fixed bounds")
        observed_slots += len(row["actions"])
        _need(observed_slots <= _MAX_PHYSICAL_ACTION_SLOTS,
              "Physical policy exceeds action-slot cap")
        for action in row["actions"]:
            _need(type(action) is dict and len(action) <= 8,
                  "Malformed physical action metadata")
            _float_bits(action.get("probability"))
    _need(observed_slots == _MAX_PHYSICAL_ACTION_SLOTS,
          "Physical action-slot count differs from fixed game")
    rules._validate_count_metadata(payload, world_count=len(worlds), pair_count=9,
                                   info_count=_MAX_PHYSICAL_ROWS, board_length=len(board))
    nodes = rules._collect_nodes(root)
    validated = rules._validate_policy(payload, root, nodes, worlds, board, selected, True)
    _need(len(validated) == _MAX_PHYSICAL_ROWS,
          "Numeric rule validator returned an incomplete physical policy")
    return validated


def _project_validated(payload, model, validated):
    mapping = model.river_class
    projected = {}
    rows = {}
    for (player, hand, history), probabilities in validated.items():
        key = (player, hand, _map_history(history, mapping))
        bits = tuple(_float_bits(value) for value in probabilities)
        if key in projected and projected[key][0] != bits:
            raise ValueError("Per-card action probabilities are not class-constant")
        projected[key] = (bits, probabilities)
    for source in payload["strategy"]:
        row = deepcopy(source)
        row["history"] = list(_map_history(tuple(row["history"]), mapping))
        row["board"] = list(row["board"])
        if len(row["board"]) == 5:
            row["board"][-1] = mapping[row["board"][-1]]
        _need(row["player"] in ("oop", "ip"), "Unknown serialized player label")
        key = (0 if row["player"] == "oop" else 1, row["hand"], tuple(row["history"]))
        prior = rows.get(key)
        if prior is not None and prior != row:
            raise ValueError("Mapped physical rows disagree in metadata or action identity")
        rows[key] = row
    _need(len(projected) == len(rows) == _MAX_CLASS_ROWS,
          "Projected strategy must contain exactly 486 complete class rows")
    _need(set(projected) == set(rows), "Projected probabilities and legal row identities differ")
    compact = {"strategy": [rows[key] for key in sorted(rows)]}
    return projected, compact


def project_policy(payload, model=None):
    """Validate and losslessly project a physical policy to its fixed class rows."""
    fixed = build_model() if model is None else model
    validate_model(fixed)
    game = fixed.physical
    fixture, board, config, _worlds, _selected, _root, _ = game
    validated = _physical_policy_rows(payload, game)
    # Projection is exposed only after both independent full-physical lanes pass.
    numeric = rules.replay_policy(payload, fixture["oop"], fixture["ip"],
                                  board=fixture["board"], config=fixture["config"])
    exact = physical_oracle.audit_policy(payload, game)
    max_difference = _check_physical_metrics(numeric, exact["metrics"])
    projected, compact = _project_validated(payload, fixed, validated)
    return {"policies": {key: value[1] for key, value in projected.items()},
            "result": compact,
            "physical_numeric_metrics": numeric,
            "physical_exact_metrics": dict(exact["metrics"]),
            "max_full_numeric_difference": max_difference}


def _expected_class_rows(model):
    _, nodes = _census(model.class_root)
    ranges = (rules.expand_range(model.physical[0]["oop"], model.physical[1]),
              rules.expand_range(model.physical[0]["ip"], model.physical[1]))
    expected = {}
    for node in nodes:
        if not isinstance(node, rules._Decision):
            continue
        player = "oop" if node.player == 0 else "ip"
        for hand in ranges[node.player]:
            if set(hand) & set(node.board):
                continue
            key = (player, "".join(hand), tuple(node.history))
            expected[key] = node
    _need(len(expected) == _MAX_CLASS_ROWS, "Internal class row census differs")
    return expected


def lift_policy(compact_result, model=None):
    """Lift a complete class policy into all physical river rows without averaging."""
    fixed = build_model() if model is None else model
    validate_model(fixed)
    compact_rows = compact_result.get("strategy") if type(compact_result) is dict else None
    _need(type(compact_rows) is list and len(compact_rows) == _MAX_CLASS_ROWS,
          "A complete 486-row internal class policy is required")
    expected = _expected_class_rows(fixed)
    compact_map = {}
    action_slots = 0
    for row in compact_rows:
        _need(type(row) is dict and set(row) == {"player", "hand", "street", "board", "history", "actions"},
              "Malformed internal class strategy row")
        _need(row["player"] in ("oop", "ip") and type(row["hand"]) is str
              and len(row["hand"]) == 4 and type(row["street"]) is str
              and type(row["board"]) is list and len(row["board"]) in (4, 5)
              and type(row["history"]) is list and len(row["history"]) <= 9
              and type(row["actions"]) is list and 0 < len(row["actions"]) <= 3,
              "Compact strategy row exceeds fixed bounds")
        key = (row["player"], row["hand"], tuple(row["history"]))
        if key in compact_map:
            raise ValueError("Duplicate compact strategy row")
        node = expected.get(key)
        _need(node is not None, "Unexpected compact strategy row identity")
        _need(row["street"] == ("turn" if len(node.board) == 4 else "river")
              and row["board"] == list(node.board), "Compact row board/street differs")
        legal = rules._row_actions(node)
        actions = row["actions"]
        _need(type(actions) is list and len(actions) == len(legal),
              "Compact row legal action count differs")
        action_slots += len(actions)
        _need(action_slots <= _MAX_CLASS_ACTION_SLOTS,
              "Compact policy exceeds action-slot cap")
        probability_total = 0.0
        for action, expected_action in zip(actions, legal):
            _need(type(action) is dict and len(action) <= 8
                  and set(action) == set(expected_action) | {"probability"},
                  "Compact action metadata fields differ")
            expected_row_action = dict(expected_action)
            supplied_row_action = {name: action[name] for name in expected_action}
            _need(_same_typed(supplied_row_action, expected_row_action),
                  "Compact action identity/metadata differs")
            probability = action.get("probability")
            _float_bits(probability)
            if probability < 0 or probability > 1:
                raise ValueError("Compact probability lies outside [0, 1]")
            probability_total += probability
        if not math.isfinite(probability_total) or abs(probability_total - 1.0) > 1e-9:
            raise ValueError("Compact probabilities do not sum to one")
        compact_map[key] = row
    _need(set(compact_map) == set(expected), "Compact strategy row set is incomplete")

    mapping = fixed.river_class
    game = fixed.physical
    result = reference.make_check_call_policy(game)
    lifted_by_identity = {}
    for template_row in result["strategy"]:
        compact_history = _map_history(tuple(template_row["history"]), mapping)
        if len(template_row["board"]) == 5:
            compact_board = list(template_row["board"])
            compact_board[-1] = mapping[compact_board[-1]]
        else:
            compact_board = list(template_row["board"])
        key = template_row["player"], template_row["hand"], compact_history
        source = compact_map.get(key)
        _need(source is not None and source["board"] == compact_board,
              "Physical legal row has no matching compact class row")
        _need(len(source["actions"]) == len(template_row["actions"]),
              "Physical/compact legal action counts differ")
        lifted = deepcopy(template_row)
        for actual_action, compact_action in zip(lifted["actions"], source["actions"]):
            _need({name: value for name, value in actual_action.items() if name != "probability"}
                  == {name: value for name, value in compact_action.items() if name != "probability"},
                  "Physical/compact legal action metadata differs during lift")
            actual_action["probability"] = compact_action["probability"]
        identity = (template_row["player"], template_row["hand"], tuple(template_row["history"]))
        _need(identity not in lifted_by_identity, "Duplicate physical row in lift template")
        lifted_by_identity[identity] = lifted
    _need(len(lifted_by_identity) == _MAX_PHYSICAL_ROWS,
          "Lifted policy does not contain all physical rows")
    result["strategy"] = [lifted_by_identity[(row["player"], row["hand"], tuple(row["history"]))]
                          for row in result["strategy"]]
    _physical_policy_rows(result, fixed.physical)
    return result


def _check_physical_metrics(numeric, exact):
    _need(type(numeric) is dict and set(_METRICS).issubset(numeric)
          and all(type(numeric[name]) in (int, float)
                  and math.isfinite(numeric[name]) for name in _METRICS),
          "Complete full-physical numeric replay is required before quotient evaluation")
    _need(type(exact) is dict and set(exact) == set(_METRICS)
          and all(type(exact[name]) is Fraction for name in _METRICS),
          "Complete full-physical exact metrics are required")
    difference = max(abs(float(exact[name]) - numeric[name]) for name in _METRICS)
    _need(difference <= 1e-9,
          "Independent physical numeric and exact metrics disagree beyond tolerance")
    return difference


def audit_policy(payload, model=None, *, chance_grouping="both"):
    """Cross-check a physical policy with scan/partition generic exact quotient audits."""
    if type(chance_grouping) is not str or chance_grouping not in ("both", "scan", "partition"):
        raise ValueError("chance_grouping must be 'both', 'scan', or 'partition'")
    fixed = build_model() if model is None else model
    validate_model(fixed)
    fixture, _board, config, _worlds, _selected, _root, _ = fixed.physical
    validated = _physical_policy_rows(payload, fixed.physical)
    numeric = rules.replay_policy(payload, fixture["oop"], fixture["ip"],
                                  board=fixture["board"], config=fixture["config"])
    full = physical_oracle.audit_policy(payload, fixed.physical)
    max_numeric_difference = _check_physical_metrics(numeric, full["metrics"])
    projected, compact_result = _project_validated(payload, fixed, validated)
    modes = ("scan", "partition") if chance_grouping == "both" else (chance_grouping,)
    class_results = {}
    for mode in modes:
        cert = generic_exact.evaluate_exact(
            fixed.class_root, fixed.class_worlds,
            {key: value[1] for key, value in projected.items()},
            config.pot, result=compact_result,
            max_work=_MAX_AUDIT_WORK, max_depth=_MAX_AUDIT_DEPTH,
            max_bits=_MAX_FRACTION_BITS, chance_grouping=mode)
        _need(cert["metrics"] == full["metrics"],
              f"Class quotient differs from full physical exact metrics ({mode})")
        class_results[mode] = {"metrics": dict(cert["metrics"]), "work": cert["work"],
                               "maximum_fraction_bits": cert["maximum_fraction_bits"],
                               "work_by_kind": dict(cert["work_by_kind"])}
    return {
        "scope": "Fixed three-hand TURN game; exact class audit only for losslessly class-constant physical policies",
        "class_census": dict(fixed.census),
        "class_masses": {key: str(value) for key, value in fixed.class_masses.items()},
        "class_member_cards": {rep: list(cards) for rep, cards in fixed.class_members},
        "full_physical_numeric_metrics": dict(numeric),
        "full_physical_exact_metrics": dict(full["metrics"]),
        "max_full_numeric_difference": max_numeric_difference,
        "generic_class_audits": class_results,
        "physical_oracle_counters": dict(full["counters"]),
        "training_calls": 0,
    }
