"""Candidate-only exact sequence-form quotient for AA/QQ/JJ versus KK.

The separate saved-data transport verifier authenticates all physical pair
counts. This module builds a reduced rank-mean game and lifts its policy; the
independent physical pure-response verifier, not this producer or its LP, is
the policy authority. No training or board enumeration occurs here.
"""
from fractions import Fraction as Q
import hashlib
import json
import math
from pathlib import Path
import re

from scripts import preflop_checkdown_validation as rules
from scripts import preflop_three_rank_transport_validation as transport
from scripts import river_sequence_form as lp

ROOT = Path(__file__).resolve().parents[1]
TRANSPORT_PATH = ROOT / "benchmarks/results/preflop-three-rank-transport-v1/candidate.json"
TRANSPORT_SHA256 = "fc98072bef74e1570a13db5c876d36226bcec1b3a2f7959c361872feb3abdbb9"
CERTIFICATE_ID = "preflop-three-rank-physical-exact-v1"
MAX_OUTPUT_BYTES = 512 * 1024
EXPECTED_CAPS = {"rows": 96, "columns": 256, "cells": 25_000, "pivots": 512,
                 "updates": 10_000_000, "bits": 4096, "exact_work": 100_000,
                 "exact_depth": 64, "exact_bits": 65_536}
EXPECTED_TREE = {"decision_nodes": 8, "fold_terminals": 7,
                 "continuations": 7, "public_states": 22}
EXPECTED_SHAPES = {"oop": [24, 79, 2000], "ip": [39, 110, 4440]}


def expected_request():
    """Return a fresh, complete literal request, independent of source files."""
    return {
        "schema_version": 1,
        "certificate_id": CERTIFICATE_ID,
        "sb_range_weights": {"AA": "1", "QQ": "1/2", "JJ": "1/4"},
        "bb_range": "KK",
        "small_blind": "1/2",
        "big_blind": "1",
        "starting_stack": ["3", "3"],
        "raise_sizes": ["1/2", "1"],
        "max_raises": 2,
        "include_all_in": True,
        "physical_pair_count": 108,
        "own_hand_counts": {"sb": 18, "bb": 6},
        "rank_masses": {"AA": "4/7", "QQ": "2/7", "JJ": "1/7"},
        "sequence_counts": {"sb": 34, "bb": 11},
        "flow_counts": {"sb": 13, "bb": 5},
        "candidate_lp_shapes": {key: list(value) for key, value in EXPECTED_SHAPES.items()},
        "public_tree": dict(EXPECTED_TREE),
        "transport_artifact_sha256": TRANSPORT_SHA256,
        "lp_caps": dict(EXPECTED_CAPS),
    }


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _validate_request(request):
    expected = expected_request()
    # Exact built-in container/scalar types prevent bool/int aliasing and
    # subclasses from bypassing this fixed whole-request admission.
    def same(actual, wanted):
        if type(wanted) is dict:
            return (type(actual) is dict and actual.keys() == wanted.keys()
                    and all(same(actual[key], value) for key, value in wanted.items()))
        if type(wanted) is list:
            return (type(actual) is list and len(actual) == len(wanted)
                    and all(same(a, b) for a, b in zip(actual, wanted)))
        return type(actual) is type(wanted) and actual == wanted
    _require(same(request, expected), "Requires the entire fixed three-rank candidate request")
    _require(type(lp.CAPS) is dict and lp.CAPS == EXPECTED_CAPS
             and all(type(value) is int for value in lp.CAPS.values()),
             "Existing exact LP caps changed")


def _fraction(value):
    if type(value) is not str or len(value) > 256:
        raise ValueError("Malformed exact transport fraction")
    if not re.fullmatch(r"(?:0|-[1-9][0-9]*|[1-9][0-9]*)(?:/[1-9][0-9]*)?", value):
        raise ValueError("Malformed exact transport fraction")
    if "/" in value:
        numerator_text, denominator_text = value.split("/", 1)
        numerator, denominator = int(numerator_text), int(denominator_text)
        if denominator == 1 or math.gcd(abs(numerator), denominator) != 1:
            raise ValueError("Transport fraction is not canonical")
    result = Q(value)
    if str(result) != value:
        raise ValueError("Transport fraction is not canonical")
    if max(abs(result.numerator).bit_length(), result.denominator.bit_length()) > 4096:
        raise ValueError("Transport fraction exceeds the exact bit bound")
    return result


def _jsonable(value):
    if isinstance(value, Q):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _load_authenticated_transport():
    raw = transport._bounded_file(TRANSPORT_PATH, transport.MAX_REPORT_BYTES)
    report = transport._load_json(raw)
    _require(type(report) is dict and report.get("artifact_sha256") == TRANSPORT_SHA256
             and transport._artifact(report) == TRANSPORT_SHA256,
             "Transport candidate does not match the pinned publication")
    receipt = transport.verify_candidate_report(TRANSPORT_PATH)
    final_raw = transport._bounded_file(TRANSPORT_PATH, transport.MAX_REPORT_BYTES)
    _require(final_raw == raw,
             "Transport candidate changed during saved-data authentication")
    _require(receipt.get("candidate_artifact_sha256") == TRANSPORT_SHA256
             and receipt.get("physical_pair_rows_authenticated") == 108,
             "Transport verifier receipt does not authenticate the fixed table")
    rows = report.get("rows")
    _require(type(rows) is list and len(rows) == 108,
             "Authenticated transport table has the wrong row count")
    return rows, receipt


def _rank_means(rows):
    totals = {rank: Q(0) for rank in "AQJ"}
    masses = {rank: Q(0) for rank in "AQJ"}
    priors = {"A": Q(1, 63), "Q": Q(1, 126), "J": Q(1, 252)}
    seen = set()
    for row in rows:
        _require(type(row) is dict, "Malformed authenticated transport row")
        sb, bb = row.get("sb_hand"), row.get("bb_hand")
        _require(type(sb) is str and type(bb) is str and sb[:1] in "AQJ",
                 "Malformed physical pair identity")
        key = (sb, bb)
        _require(key not in seen, "Duplicate physical pair in authenticated table")
        seen.add(key)
        rank = sb[0]
        prior = _fraction(row.get("prior_fraction"))
        _require(prior == priors[rank], "Authenticated exact pair prior changed")
        wins, ties, losses, boards = (row.get(k) for k in ("wins", "ties", "losses", "boards"))
        _require(all(type(v) is int for v in (wins, ties, losses, boards))
                 and min(wins, ties, losses) >= 0 and boards == 1_712_304
                 and wins + ties + losses == boards,
                 "Malformed authenticated physical W/T/L row")
        totals[rank] += prior * Q(wins - losses, boards)
        masses[rank] += prior
    expected_masses = {"A": Q(4, 7), "Q": Q(2, 7), "J": Q(1, 7)}
    _require(len(seen) == 108 and masses == expected_masses,
             "Physical rank masses differ from fixed global conditioning")
    return {rank: totals[rank] / masses[rank] for rank in "AQJ"}


def _tree_model(root, means):
    sequences = [[("empty",)], [("empty",)]]
    parents, menus, children = [{}, {}], [{}, {}], [{}, {}]
    rank_mass = {"AA": Q(4, 7), "QQ": Q(2, 7), "JJ": Q(1, 7)}
    rank_symbol = {"AA": "A", "QQ": "Q", "JJ": "J"}
    abstract_pairs = [(hand, "KK", rank_mass[hand], means[rank_symbol[hand]])
                      for hand in ("AA", "QQ", "JJ")]

    def collect(node, current, pair):
        if isinstance(node, rules._Terminal):
            return
        player = node.player
        hand = pair[player]
        key = (hand, node.history)
        if key in parents[player]:
            _require(parents[player][key] == current[player], "Perfect-recall parent changed")
        parents[player][key] = current[player]
        tokens = tuple(action.token for action in node.actions)
        if key in menus[player]:
            _require(menus[player][key] == tokens, "Rank abstraction changed an information menu")
        menus[player][key] = tokens
        child_sequences = []
        for action, child in zip(node.actions, node.children):
            sequence = (hand, node.history, action.token)
            if sequence not in sequences[player]:
                sequences[player].append(sequence)
            child_sequences.append(sequence)
            nxt = list(current)
            nxt[player] = sequence
            collect(child, tuple(nxt), pair)
        if key in children[player]:
            _require(children[player][key] == child_sequences,
                     "Rank abstraction changed child sequences")
        children[player][key] = child_sequences

    for pair in abstract_pairs:
        collect(root, (("empty",), ("empty",)), pair)
    nx, ny = map(len, sequences)
    me, mf = (len(items) + 1 for items in parents)
    shapes = {}
    for name, (rows, columns) in (
            ("oop", (me + ny, nx + 2 * mf + ny + me + ny)),
            ("ip", (mf + nx, ny + 2 * me + nx + mf + nx))):
        shapes[name] = [rows, columns, (rows + 1) * (columns + 1)]
    _require((nx, ny, me, mf) == (34, 11, 13, 5), "Candidate sequence/flow census changed")
    _require(shapes == EXPECTED_SHAPES, "Candidate exact LP dimensions changed")
    for rows, columns, cells in shapes.values():
        _require(rows <= lp.CAPS["rows"] and columns <= lp.CAPS["columns"]
                 and cells <= lp.CAPS["cells"], "Candidate exceeds an unchanged LP tableau cap")
    return abstract_pairs, sequences, parents, menus, children, shapes


def _make_flows(sequences, parents, children):
    flows, labels = [], []
    indexes = [{sequence: i for i, sequence in enumerate(side)} for side in sequences]
    for player in (0, 1):
        row = [Q(0)] * len(sequences[player])
        row[0] = Q(1)
        flows.append(row)
        labels.append({"id": f"{player}:empty"})
        for key, parent in parents[player].items():
            row = [Q(0)] * len(sequences[player])
            row[indexes[player][parent]] -= 1
            for child in children[player][key]:
                row[indexes[player][child]] += 1
            flows.append(row)
            labels.append({"id": str((player, key))})
    return flows, labels, indexes


def _payoff(root, abstract_pairs, indexes, sequences):
    matrix = [[Q(0) for _ in sequences[1]] for _ in sequences[0]]

    def visit(node, current, pair):
        if isinstance(node, rules._Terminal):
            matched = Q(str(min(node.contributions)))
            utility = matched * (pair[3] if node.winner is None
                                 else (1 if node.winner == 0 else -1))
            matrix[indexes[0][current[0]]][indexes[1][current[1]]] += pair[2] * utility
            return
        player = node.player
        hand = pair[player]
        for action, child in zip(node.actions, node.children):
            next_current = list(current)
            next_current[player] = (hand, node.history, action.token)
            visit(child, tuple(next_current), pair)

    for pair in abstract_pairs:
        visit(root, (("empty",), ("empty",)), pair)
    return matrix


def _solve_and_policy(model, sequences, parents, menus, children, indexes):
    solutions = [lp._solve_lp(model, kind)
                 for kind in ("oop_guarantee", "ip_ceiling")]
    values = [solution[2][0] for solution in solutions]
    x, y = solutions[0][1], solutions[1][1]
    matrix_value = sum((x[i] * model["A"][i][j] * y[j]
                        for i in range(len(x)) for j in range(len(y))), Q(0))
    _require(values[0] == values[1] == matrix_value,
             "Candidate primal/dual values disagree")
    flows = model["flows"]
    me = len(parents[0]) + 1
    mf = len(parents[1]) + 1
    for player, (start, size) in enumerate(((0, me), (me, mf))):
        for offset, row in enumerate(flows[start:start + size]):
            observed = sum((coefficient * value for coefficient, value in
                            zip(row, solutions[player][1])), Q(0))
            _require(observed == (Q(1) if offset == 0 else Q(0)),
                     "Candidate realization flow failed")
    _require(not any(value < 0 for solution in solutions
                     for value in (*solution[1], *solution[3])),
             "Candidate realization or dual slack is negative")
    _require(sum((a * b for a, b in zip(x, solutions[1][3])), Q(0)) == 0
             and sum((a * b for a, b in zip(y, solutions[0][3])), Q(0)) == 0,
             "Candidate complementary slackness failed")
    policies = []
    for player, solution in enumerate(solutions):
        realization = solution[1]
        for key, parent in parents[player].items():
            mass = realization[indexes[player][parent]]
            child_ids = children[player][key]
            probabilities = ([realization[indexes[player][child]] / mass for child in child_ids]
                             if mass else [Q(1, len(child_ids))] * len(child_ids))
            _require(sum(probabilities, Q(0)) == 1,
                     "Candidate behavioral policy does not normalize")
            policies.append({"player": player, "type": key[0],
                             "history": list(key[1]), "actions": list(menus[player][key]),
                             "probabilities": list(map(str, probabilities))})
    return policies, values[0], solutions, matrix_value


def build_candidate(request=None):
    """Authenticate the fixed transport, then build and lift one candidate LP."""
    request = expected_request() if request is None else request
    _validate_request(request)  # Must precede every source, tree or LP access.
    rows, transport_receipt = _load_authenticated_transport()
    means = _rank_means(rows)
    game = {"small_blind": 0.5, "big_blind": 1.0, "starting_stack": [3.0, 3.0],
            "raise_sizes": [0.5, 1.0], "max_raises": 2, "include_all_in": True}
    root, census = rules._build(rules._config(game))
    _require(type(census) is dict and census == EXPECTED_TREE,
             "Independent public tree differs from the fixed candidate request")
    abstract_pairs, sequences, parents, menus, children, shapes = _tree_model(root, means)
    flows, flow_labels, indexes = _make_flows(sequences, parents, children)
    matrix = _payoff(root, abstract_pairs, indexes, sequences)
    model = {"A": matrix, "infos": parents, "flows": flows, "flow_labels": flow_labels,
             "sequences": [[{"id": str(sequence)} for sequence in side]
                           for side in sequences]}
    policies, value, solutions, matrix_value = _solve_and_policy(
        model, sequences, parents, menus, children, indexes)
    physical_policies = []
    for player, ranks in ((0, "AQJ"), (1, "K")):
        for rank in ranks:
            for first in "cdhs":
                for second in "cdhs":
                    if first >= second:
                        continue
                    hand = rank + first + rank + second
                    abstract_type = rank * 2
                    for policy in policies:
                        if policy["player"] == player and policy["type"] == abstract_type:
                            physical_policies.append({
                                "player": player, "hand": hand,
                                "history": policy["history"], "actions": policy["actions"],
                                "probabilities": policy["probabilities"],
                            })
    _require(len(physical_policies) == 96,
             "Lifted physical own-hand policy census changed")
    report = {
        "schema_version": 1,
        "certificate_id": CERTIFICATE_ID,
        "status": "candidate-only",
        "request": request,
        "transport_artifact_sha256": TRANSPORT_SHA256,
        "value_candidate_fraction": str(value),
        "policies": physical_policies,
        "candidate_details": {
            "rank_mean_fractions": {rank: str(mean) for rank, mean in means.items()},
            "transport_receipt": transport_receipt,
            "public_tree": census,
            "candidate_lp_shapes": shapes,
            "sequence_counts": {"sb": len(sequences[0]), "bb": len(sequences[1])},
            "flow_counts": {"sb": len(parents[0]) + 1, "bb": len(parents[1]) + 1},
            "rank_type_policies": policies,
            "candidate_reduced_model": {
                "sequences": model["sequences"], "flow_labels": flow_labels,
                "flows": flows, "payoff_matrix": matrix,
            },
            "candidate_primal_dual_observations": [
                {"lp": solution[0], "realization": solution[1],
                 "dual": solution[2], "slacks": solution[3]}
                for solution in solutions],
            "matrix_value_fraction": str(matrix_value),
            "authority_scope": "candidate reduced LP and physical policy lift only; independent exact physical pure-response verification is required",
        },
    }
    report = _jsonable(report)
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    _require(len(encoded) <= MAX_OUTPUT_BYTES,
             "Candidate report exceeds its separate output bound")
    report["artifact_sha256"] = hashlib.sha256(encoded).hexdigest()
    final_encoded = json.dumps(report, sort_keys=True, separators=(",", ":"),
                               allow_nan=False).encode("utf-8")
    _require(len(final_encoded) <= MAX_OUTPUT_BYTES,
             "Candidate report exceeds its separate output bound")
    return report
