"""No-training exact public-chance quotient audit for one weighted flop game.

The candidate partitioner is not a physical authority. This auditor rebuilds
the physical game independently, checks both reveal layers and every numeric
betting subtree, then checks class-constant policies against unrestricted
physical own-hand responses. No solver, API or resource admission is changed.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
from fractions import Fraction
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import struct
from unittest.mock import patch

from scripts import flop_multistreet_validation as physical
from scripts import flop_public_classes_candidate as candidate


BOARD = ("2c", "3d", "4h")
OOP = (("AsAd", "1"), ("QsQd", "1/2"))
IP = (("AsKh", "1/4"), ("KsKd", "1"))
CONFIG = {"pot": 10, "effective_stack": 5, "bet_sizes": [0.5],
          "raise_sizes": [], "max_raises": 0, "include_all_in": False}
METRICS = ("value_oop", "value_ip", "oop_best_response_value",
           "ip_best_response_value", "oop_best_response_gain",
           "ip_best_response_gain", "nash_conv", "exploitability")
MAX_FRACTION_BITS = 65_536
# Filled from an independent fresh reconstruction, never from a trainer.
PHYSICAL_WORLDS_SHA256 = "c865b4d9a9052b613809389046d44a90d313daeddf0cee371c397a2e020f3568"
PHYSICAL_TREE_SHA256 = "e83e0793562bd48c7ce0b1073d2ca5af01855c6d073a55925cae74626505036e"


def _source_hashes():
    root = Path(__file__).resolve().parents[1]
    paths = ("scripts/flop_public_classes.py", "scripts/flop_public_classes_candidate.py",
             "scripts/flop_multistreet_validation.py", "scripts/preflop_validation.py",
             "scripts/benchmark_weighted_full_deck_flop.py", "scripts/benchmark_flop_alternating.py")
    out = {}
    for path in paths:
        raw = (root / path).read_bytes()
        _need(len(raw) <= 2*1024*1024, "Audit source exceeds size bound")
        out[path] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    return out


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _typed(value):
    """A typed canonical structure: bool/int and signed zero cannot alias."""
    if type(value) is dict:
        return ("dict", tuple((k, _typed(v)) for k, v in sorted(value.items())))
    if type(value) in (list, tuple):
        return (type(value).__name__, tuple(_typed(v) for v in value))
    if type(value) is float:
        return ("float", struct.pack(">d", value).hex())
    return (type(value).__name__, value)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


@contextmanager
def independent_guard():
    """Fail closed if preparation/auditing calls a production poker authority."""
    from scripts import benchmark_weighted_full_deck_flop as base
    from scripts.benchmark_flop_alternating import _forbid_new_trainers
    from pokerlab import alternating_public_cfr, postflop_solver
    calls = {}
    with ExitStack() as stack:
        legacy = stack.enter_context(base.independent_guard())
        _forbid_new_trainers(stack, alternating_public_cfr, calls)
        key = "pokerlab.postflop_solver.solve_postflop"
        calls[key] = 0
        def forbidden(*args, **kwargs):
            calls[key] += 1
            raise AssertionError("No-training audit called solve_postflop")
        stack.enter_context(patch.object(postflop_solver, "solve_postflop", forbidden))
        yield calls
        calls.update(legacy)
    _need(not any(calls.values()), "Independent audit used production authority")


def _bounded_partition(partition):
    pending = [(partition, 0)]
    count = 0
    while pending:
        value, depth = pending.pop()
        count += 1
        _need(count <= 100_000 and depth <= 12, "Partition exceeds audit size bound")
        if type(value) is dict:
            _need(len(value) <= 64 and all(type(k) is str and len(k) <= 256 for k in value),
                  "Partition object exceeds audit bound")
            pending.extend((v, depth+1) for v in value.values())
        elif type(value) is list:
            _need(len(value) <= 2352, "Partition list exceeds physical runout bound")
            pending.extend((v, depth+1) for v in value)
        else:
            _need(type(value) in (str, int, bool, type(None)), "Unexpected partition value type")
            if type(value) is int:
                _need(value.bit_length() <= 384, "Partition integer exceeds exact input bound")
            if type(value) is str:
                _need(len(value) <= 2048, "Partition string exceeds audit bound")


def _world_rows(worlds):
    return [[w[0], w[1], str(w[2]), w[3], list(w[4])] for w in worlds]


def _walk(root, *, cap=30_812):
    pending = [(root, 1)]
    out = []
    while pending:
        node, depth = pending.pop()
        out.append(node)
        _need(len(out) <= cap and depth <= 16, "Fixed public tree exceeds bound")
        if isinstance(node, physical._Decision):
            _need(len(node.actions) == len(node.children) == 2,
                  "Fixed decision must retain both legal actions")
            pending.extend((child, depth + 1) for child in node.children)
        elif isinstance(node, physical._Chance):
            _need(0 < len(node.branches) <= 49, "Fixed chance exceeds branch bound")
            pending.extend((child, depth + 1) for child in node.branches.values())
        else:
            _need(isinstance(node, physical._Terminal), "Unknown public node")
    return out


def _structure(node):
    if isinstance(node, physical._Terminal):
        return ["terminal", list(node.history), node.kind, node.winner,
                _typed(node.contributions)]
    if isinstance(node, physical._Decision):
        return ["decision", list(node.history), node.player, node.street,
                list(node.board), _typed(node.actions),
                [_structure(child) for child in node.children]]
    return ["chance", list(node.history), node.card_index, node.street,
            [[card, _structure(child)] for card, child in sorted(node.branches.items())]]


def _maps(partition):
    turns = {card: "T%02d" % group["id"]
             for group in partition["turn_classes"] for card in group["members"]}
    rivers = {(row["turn"], row["river"]): "R%02d" % group["id"]
              for group in partition["river_classes"] for row in group["members"]}
    return turns, rivers


def _mapped_history(history, turns, rivers):
    turn = None
    mapped = []
    for token in history:
        if token.startswith("turn@"):
            turn = token[5:]
            mapped.append("turn@" + turns[turn])
        elif token.startswith("river@"):
            mapped.append("river@" + rivers[(turn, token[6:])])
        else:
            mapped.append(token)
    return tuple(mapped)


def _verify_partition(partition, worlds):
    """Independently check supplied classes against every original joint row."""
    _bounded_partition(partition)
    _need(type(partition) is dict and len(partition.get("turn_classes", ())) == 11
          and len(partition.get("river_classes", ())) == 19
          and len(partition.get("class_worlds", ())) == 126,
          "Fixed partition dimensions differ")
    turns, rivers = _maps(partition)
    pair_order = sorted({w[:2] for w in worlds})
    source = {(w[4][3], w[4][4], w[0], w[1]): (w[2], w[3]) for w in worlds}
    actual_turns = {w[4][3] for w in worlds}
    actual_runouts = {w[4][3:] for w in worlds}
    _need(set(turns) == actual_turns and len(turns) == 49,
          "Turn classes omit or repeat physical support")
    _need(sum(len(g["members"]) for g in partition["turn_classes"]) == 49,
          "Duplicate turn class member")
    _need(set(rivers) == actual_runouts and sum(len(g["members"]) for g in
          partition["river_classes"]) == len(actual_runouts),
          "River classes omit or repeat physical support")
    _need([g["id"] for g in partition["turn_classes"]] == list(range(11)) and
          [g["id"] for g in partition["river_classes"]] == list(range(19)),
          "Class IDs differ from deterministic fixed partition")
    # Explicit absence, original joint mass and showdown sign all enter here.
    signatures = {runout: tuple(source.get((*runout, *pair)) for pair in pair_order)
                  for runout in actual_runouts}
    for group in partition["river_classes"]:
        members = [(m["turn"], m["river"]) for m in group["members"]]
        _need(members and all(signatures[m] == signatures[members[0]] for m in members),
              "River class changes joint support, mass or showdown sign")
    turn_masses = {t: tuple(sum((w[2] for w in worlds if w[:2] == pair and
                                 w[4][3] == t), Fraction()) for pair in pair_order)
                   for t in actual_turns}
    for group in partition["turn_classes"]:
        members = group["members"]
        representative = group["representative"]
        _need(representative in members and members, "Turn representative is missing")
        counts = {t: Counter(rivers[r] for r in actual_runouts if r[0] == t)
                  for t in members}
        _need(all(turn_masses[t] == turn_masses[representative] and
                  counts[t] == counts[representative] for t in members),
              "Turn class changes posterior or river transition multiplicity")
        transports = group["river_transports"]
        _need(len(transports) <= 49 * 49, "River transport exceeds fixed bound")
        seen = set()
        for t in members:
            rows = [r for r in transports if r["turn"] == t]
            src = {(r["turn"], r["river"]) for r in rows}
            dst = {(r["representative_turn"], r["representative_river"]) for r in rows}
            _need(len(rows) == len(src) == len(dst) and
                  src == {r for r in actual_runouts if r[0] == t} and
                  dst == {r for r in actual_runouts if r[0] == representative},
                  "River transport is not a complete per-turn bijection")
            for row in rows:
                a = (t, row["river"])
                b = (row["representative_turn"], row["representative_river"])
                _need(signatures[a] == signatures[b] and rivers[a] == rivers[b]
                      and rivers[a] == "R%02d" % row["river_class_id"],
                      "River transport changes original joint signature")
                seen.add(a)
        _need(len(seen) == len(transports), "Extra or duplicate river transport")
    aggregate = defaultdict(Fraction)
    signs = {}
    counts = Counter()
    for oop, ip, mass, sign, board in worlds:
        key = (oop, ip, turns[board[3]], rivers[board[3:]])
        aggregate[key] += mass
        counts[key] += 1
        _need(key not in signs or signs[key] == sign, "Aggregate changes payoff")
        signs[key] = sign
    compact_worlds = []
    observed = set()
    for row in partition["class_worlds"]:
        key = (row["oop_hand"], row["ip_hand"], "T%02d" % row["turn_class_id"],
               "R%02d" % row["river_class_id"])
        _need(key in aggregate and key not in observed, "Class world support differs")
        observed.add(key)
        _need(type(row["sign"]) is int and row["sign"] == signs[key]
              and type(row["physical_world_count"]) is int
              and row["physical_world_count"] == counts[key]
              and type(row["mass"]) is list and len(row["mass"]) == 2
              and all(type(v) is int for v in row["mass"])
              and row["mass"][0] > 0 and row["mass"][1] > 0
              and Fraction(*row["mass"]) == aggregate[key],
              "Class world changes exact original mass, sign or coverage")
        compact_worlds.append((key[0], key[1], aggregate[key], signs[key], BOARD + key[2:]))
    _need(observed == set(aggregate) and sum(aggregate.values(), Fraction()) == 1,
          "Class aggregation drops original support or global mass")
    for pair in pair_order:
        _need(sum((w[2] for w in compact_worlds if w[:2] == pair), Fraction()) ==
              sum((w[2] for w in worlds if w[:2] == pair), Fraction()),
              "Class aggregation renormalizes a private pair")
    # Independently proved above; also authenticate every descriptive output
    # field (signatures, per-pair summaries, counts and candidate-only scope).
    rebuilt = candidate.build_candidate(_world_rows(worlds), board=BOARD)
    _need(_typed(partition) == _typed(rebuilt), "Candidate descriptive record differs from original rows")
    return turns, rivers, compact_worlds


def _collapse(root, turns, rivers):
    """Compare every branch's entire descendant tree, including both reveals."""
    compared = 0
    visited = 0
    def visit(node):
        nonlocal compared, visited
        visited += 1
        _need(visited <= 30_812, "Subtree audit exceeds physical bound")
        history = _mapped_history(node.history, turns, rivers)
        if isinstance(node, physical._Terminal):
            out = physical._Terminal(history, node.kind, node.contributions, node.winner)
        elif isinstance(node, physical._Decision):
            board = BOARD + tuple(physical._revealed(history))
            out = physical._Decision(history, node.player, node.street, board,
                                     deepcopy(node.actions), [visit(c)[0] for c in node.children])
        else:
            branches = {}
            structures = {}
            previous_turn = physical._revealed(node.history)
            for card, child in sorted(node.branches.items()):
                label = turns[card] if node.card_index == 3 else rivers[(previous_turn[0], card)]
                collapsed, structure = visit(child)
                if label in structures:
                    _need(structure == structures[label],
                          "Complete numeric betting subtrees differ within class")
                else:
                    structures[label] = structure
                    branches[label] = collapsed
                compared += 1
            out = physical._Chance(history, node.card_index, node.street, branches)
        return out, _structure(out)
    collapsed, structure = visit(root)
    _need(visited == 30_812, "Not every physical public node was audited")
    return collapsed, {"physical_nodes_checked": visited,
                       "physical_branch_subtrees_compared": compared,
                       "compact_tree_sha256": _digest(structure)}


@dataclass(frozen=True)
class ClassModel:
    physical: dict
    partition: dict
    turns: dict
    rivers: dict
    worlds: tuple
    root: object
    census: dict


def _physical_anchor(oracle):
    _need(len(oracle["worlds"]) == 5940 and oracle["normalizer"] == Fraction(13, 8),
          "Independent fixed physical game differs")
    _need(_digest(_world_rows(oracle["worlds"])) == PHYSICAL_WORLDS_SHA256,
          "Physical worlds differ from independent fixed-game anchor")
    nodes = _walk(oracle["root"])
    _need(_digest(_structure(oracle["root"])) == PHYSICAL_TREE_SHA256,
          "Physical numeric tree differs from independent fixed-game anchor")
    decisions = {(n.player, n.history): n for n in nodes
                 if isinstance(n, physical._Decision)}
    _need(type(oracle["nodes"]) is dict and oracle["nodes"].keys() == decisions.keys()
          and all(oracle["nodes"][k] is v for k, v in decisions.items()),
          "Physical policy node index differs from anchored tree")
    active = defaultdict(set)
    for world in oracle["worlds"]:
        for length in range(3):
            for player in (0, 1):
                active[(player, world[4][3:3+length])].add(world[player])
    _need(oracle["active_hands_by_prefix"] == dict(active),
          "Physical own-hand visibility differs from original worlds")
    configs = physical._normalize_configs(CONFIG)
    expected = {"board": BOARD, "pot": 10.0, "effective_stack": [5.0, 5.0],
                "config": physical._public_config(configs["flop"]),
                "street_configs": {s: physical._public_config(c) for s, c in configs.items()},
                "runout_mode": "full-deck", "runouts": physical._canonical_runouts(None, BOARD),
                "reachable_runouts": tuple(sorted({w[4][3:] for w in oracle["worlds"]},
                    key=lambda r: tuple(physical.DECK_INDEX[c] for c in r))),
                "public_nodes": 9512, "public_states": 30812, "chance_nodes": 248,
                "terminal_nodes": 21052, "compatible_pairs": 3}
    _need(all(_typed(oracle[k]) == _typed(v) for k, v in expected.items()),
          "Physical header or census differs from fixed game")


def _expected_rows(oracle):
    rows = {}
    for node in _walk(oracle["root"]):
        if isinstance(node, physical._Decision):
            for hand in oracle["active_hands_by_prefix"][(node.player, physical._revealed(node.history))]:
                rows[(node.player, hand, node.history)] = node
    _need(len(rows) == 16_912, "Physical information-set census differs")
    return rows


def _make_model(oracle, partition):
    _physical_anchor(oracle)
    turns, rivers, worlds = _verify_partition(partition, oracle["worlds"])
    root, census = _collapse(oracle["root"], turns, rivers)
    physical_rows = _expected_rows(oracle)
    keys = {(p, hand, _mapped_history(h, turns, rivers)) for p, hand, h in physical_rows}
    nodes = _walk(root)
    census.update(compact_public_states=len(nodes),
                  compact_decisions=sum(isinstance(n, physical._Decision) for n in nodes),
                  compact_chance_nodes=sum(isinstance(n, physical._Chance) for n in nodes),
                  compact_terminals=sum(isinstance(n, physical._Terminal) for n in nodes),
                  physical_policy_rows=len(physical_rows), compact_policy_rows=len(keys),
                  physical_action_slots=2*len(physical_rows), compact_action_slots=2*len(keys),
                  compact_worlds=len(worlds), turn_classes=len(partition["turn_classes"]),
                  river_signatures=len(partition["river_classes"]))
    return ClassModel(oracle, partition, turns, rivers, tuple(worlds), root, census)


def build_model():
    """Fresh independent cards, ranking, joint conditioning and numeric tree."""
    oracle = physical.prepare_oracle(BOARD, OOP, IP, CONFIG)
    partition = candidate.build_candidate(_world_rows(oracle["worlds"]), board=BOARD)
    return _make_model(oracle, partition)


def validate_model(model):
    _need(type(model) is ClassModel, "Expected fixed ClassModel")
    rebuilt = _make_model(model.physical, model.partition)
    _need(_typed(model.turns) == _typed(rebuilt.turns) and
          _typed(model.rivers) == _typed(rebuilt.rivers) and
          _typed(model.worlds) == _typed(rebuilt.worlds) and
          _typed(model.census) == _typed(rebuilt.census) and
          _structure(model.root) == _structure(rebuilt.root),
          "Mutated compact model differs from complete physical reconstruction")
    return dict(rebuilt.census)


def _probabilities(values):
    _need(type(values) is tuple and len(values) == 2 and all(type(v) is float and
          math.isfinite(v) and 0 <= v <= 1 for v in values),
          "Expected both finite binary64 action probabilities")
    _need(sum((Fraction(v) for v in values), Fraction()) == 1,
          "Exact audit requires binary64 probabilities summing exactly to one")
    return values


def _exact_metrics(root, worlds, rows):
    """Rational profile and legal own-hand BR; hidden worlds sum before max."""
    probabilities = {k: tuple(Fraction(v) for v in _probabilities(values))
                     for k, values in rows.items()}
    def payoff(node, world):
        sign = (1 if node.winner == 0 else -1) if node.kind == "fold" else world[3]
        return sign * (Fraction(5) + min(Fraction(v) for v in node.contributions))
    def profile(node, world):
        if isinstance(node, physical._Terminal):
            return payoff(node, world)
        if isinstance(node, physical._Chance):
            return profile(node.branches[world[4][node.card_index]], world)
        return sum((p * profile(child, world) for p, child in zip(
            probabilities[(node.player, world[node.player], node.history)], node.children)), Fraction())
    def response(node, group, player):
        if isinstance(node, physical._Terminal):
            return sum((weight * payoff(node, world) * (1 if player == 0 else -1)
                        for world, weight in group), Fraction())
        if isinstance(node, physical._Chance):
            groups = defaultdict(list)
            for world, weight in group:
                groups[world[4][node.card_index]].append((world, weight))
            return sum((response(node.branches[c], g, player)
                        for c, g in sorted(groups.items())), Fraction())
        if node.player == player:
            _need(len({w[player] for w, _ in group}) <= 1, "Best response merges own hands")
            return max(response(child, group, player) for child in node.children)
        return sum((response(child, [(w, weight * probabilities[
            (node.player, w[node.player], node.history)][i]) for w, weight in group], player)
            for i, child in enumerate(node.children)), Fraction())
    value = sum((w[2] * profile(root, w) for w in worlds), Fraction())
    brs = []
    for player in (0, 1):
        brs.append(sum((response(root, [(w, w[2]) for w in worlds if w[player] == hand], player)
                        for hand in sorted({w[player] for w in worlds})), Fraction()))
    _need(brs[0] >= value and brs[1] >= -value, "Exact legal response bound failed")
    nc = brs[0] + brs[1]
    result = dict(zip(METRICS, (value, -value, *brs, brs[0]-value, brs[1]+value, nc, nc/2)))
    _need(all(v.numerator.bit_length() <= MAX_FRACTION_BITS and
              v.denominator.bit_length() <= MAX_FRACTION_BITS for v in result.values()),
          "Exact metric exceeds fixed fraction bit bound")
    return result


def _class_rows(model):
    return {(p, hand, _mapped_history(h, model.turns, model.rivers)): node
            for (p, hand, h), node in _expected_rows(model.physical).items()}


def project_policy(payload, model):
    """Reject card-specific policies; never average physical probabilities."""
    validate_model(model)
    rows = physical._validate_policy(payload, model.physical, 1e-10)
    projected = {}
    bits = {}
    for (player, hand, history), values in rows.items():
        _probabilities(values)
        key = (player, hand, _mapped_history(history, model.turns, model.rivers))
        raw = tuple(struct.pack(">d", v) for v in values)
        _need(key not in bits or bits[key] == raw,
              "Physical policy is not bit-exact class-constant")
        bits[key] = raw
        projected[key] = values
    _need(set(projected) == set(_class_rows(model)), "Projected class rows differ")
    return projected


def lift_policy(rows, model):
    """Lift internal class controls into complete legal physical policy rows."""
    validate_model(model)
    _need(type(rows) is dict and set(rows) == set(_class_rows(model)),
          "Internal class policy omits or adds an information set")
    for values in rows.values():
        _probabilities(values)
    oracle = model.physical
    strategy = []
    for (player, hand, history), node in sorted(_expected_rows(oracle).items()):
        key = (player, hand, _mapped_history(history, model.turns, model.rivers))
        actions = [{k: action[k] for k in ("name", "amount", "raise_to", "history_key")}
                   for action in node.actions]
        for action, probability in zip(actions, rows[key]):
            action["probability"] = probability
        strategy.append({"player": "oop" if player == 0 else "ip", "hand": hand,
                         "history": list(history), "street": node.street,
                         "board": list(node.board), "actions": actions})
    metrics = _exact_metrics(model.root, model.worlds, rows)
    return {"solver_version": "configured-postflop-v1", "algorithm": "no-training-class-policy-control",
            "strategy_schema": "postflop-strategy-v1", "board": list(BOARD),
            "config": deepcopy(oracle["config"]), "street_configs": deepcopy(oracle["street_configs"]),
            "pot": oracle["pot"], "effective_stack": list(oracle["effective_stack"]),
            "runout_mode": "full-deck", "runouts": [list(r) for r in oracle["runouts"]],
            "reachable_runouts": [list(r) for r in oracle["reachable_runouts"]],
            "worlds": 5940, "compatible_pairs": 3, "deals": 3,
            "info_sets": len(strategy), "strategy": strategy,
            **{k: oracle[k] for k in ("public_nodes", "public_states", "chance_nodes", "terminal_nodes")},
            **{k: float(v) for k, v in metrics.items()}}


def audit_policy(payload, model):
    rows = project_policy(payload, model)
    compact = _exact_metrics(model.root, model.worlds, rows)
    physical_rows = physical._validate_policy(payload, model.physical, 1e-10)
    full = _exact_metrics(model.physical["root"], model.physical["worlds"], physical_rows)
    _need(compact == full, "Compact and unrestricted physical exact metrics differ")
    numeric = physical.replay(payload, model.physical)
    gaps = {k: abs(float(full[k])-numeric[k]) for k in METRICS}
    _need(max(gaps.values()) <= 1e-10, "Independent physical numeric replay differs")
    lifted = physical._validate_policy(lift_policy(rows, model), model.physical, 1e-10)
    _need(all(tuple(struct.pack(">d", v) for v in values) ==
              tuple(struct.pack(">d", v) for v in lifted[key])
              for key, values in physical_rows.items()), "Lift changes a physical probability")
    return {"exact_metrics": {k: str(v) for k, v in full.items()},
            "independent_numeric_metrics": {k: numeric[k] for k in METRICS},
            "maximum_numeric_gap": max(gaps.values()), "exact_metric_count": len(METRICS),
            "physical_rows_lifted": len(lifted), "class_rows": len(rows),
            "physical_policy_sha256": _digest(payload),
            "physical_strategy_sha256": _digest(payload["strategy"]),
            "class_policy": [[p, hand, list(history), list(values)]
                             for (p, hand, history), values in sorted(rows.items())]}


def control_policy(model, mode):
    _need(mode in ("check-call", "bet-fold", "class-varying", "zero-reach"),
          "Unknown no-training control")
    rows = {}
    for key, source in sorted(_class_rows(model).items()):
        if mode == "check-call":
            first = 1.0 if source.actions[0]["name"] == "check" else 0.0
        elif mode == "bet-fold":
            first = 0.0 if source.actions[0]["name"] == "check" else 1.0
        elif mode == "zero-reach":
            first = 1.0
        else:
            first = (int(_digest([key[0], key[1], list(key[2])])[:8], 16) % 5) / 4.0
        rows[key] = (first, 1.0-first)
    return lift_policy(rows, model)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output:
        _need(not args.output.exists(), "Audit output already exists; preserve it")
    sources = _source_hashes()
    with independent_guard() as calls:
        model = build_model()
        controls = {mode: audit_policy(control_policy(model, mode), model)
                    for mode in ("check-call", "bet-fold", "class-varying", "zero-reach")}
    _need(_source_hashes() == sources, "Audit source changed during reconstruction")
    report = {"schema_version": "fixed-flop-public-classes-audit-v1",
              "status": "no-training-equivalence-verified", "training_calls": 0,
              "source_lf_sha256": sources,
              "runtime": {"implementation": platform.python_implementation(),
                          "python": platform.python_version()},
              "physical_worlds_sha256": PHYSICAL_WORLDS_SHA256,
              "physical_tree_sha256": PHYSICAL_TREE_SHA256,
              "forbidden_production_calls": calls,
              "census": model.census, "partition": model.partition, "controls": controls,
              "scope": "One fixed weighted flop game and exact-normalized binary64 class-constant policies. No convergence, trained class policy, speed or unrestricted NLHE claim."}
    report["artifact_sha256"] = _digest(report)
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(report, sort_keys=True, indent=2)+"\n")
    print(json.dumps({"status": report["status"], "census": model.census,
                      "control_count": len(controls), "artifact_sha256": report["artifact_sha256"]}))


if __name__ == "__main__":
    main()
