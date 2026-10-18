"""Exact sequence-form feasibility candidate for one weighted preflop game.

The candidate uses pinned full-board W/T/L artifacts and the independent
numeric rules tree.  It does not enumerate cards, rank hands, train CFR, or
change any production solver.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from pathlib import Path

from scripts import preflop_checkdown_validation as numeric
from scripts import river_sequence_form as exact_lp
from scripts.preflop_sequence_fixture import (
    BOARDS_PER_PAIR, EXPECTED_CENSUS, EXPECTED_PRIORS, ROOT, SOURCE_COMMIT,
    load_pinned_fixture,
)

CAPS = exact_lp.CAPS
CERTIFICATE_ID = "preflop-weighted-sequence-feasibility-v1"


class _Limit(ValueError):
    """A frozen shape or existing exact-LP cap rejected the candidate."""


def _fraction(value: Fraction) -> str:
    if type(value) is not Fraction:
        raise TypeError("exact witness values must be Fraction")
    return str(value)


def _float_fraction(value: float) -> Fraction:
    return Fraction.from_float(float(value))


def _flow_row(parent: int, children: tuple[int, ...], count: int) -> list[Fraction]:
    row = [Fraction(0)] * count
    for child in children:
        row[child] += 1
    row[parent] -= 1
    return row


def _tree_json(node) -> dict:
    if isinstance(node, numeric._Terminal):
        return {
            "kind": "fold" if node.winner is not None else "showdown",
            "winner": None if node.winner is None else ("sb" if node.winner == 0 else "bb"),
            "contributions": [_fraction(_float_fraction(x)) for x in node.contributions],
        }
    return {
        "kind": "decision",
        "player": "sb" if node.player == 0 else "bb",
        "history": list(node.history),
        "contributions": [_fraction(_float_fraction(x)) for x in node.contributions],
        "actions": [
            {"name": a.name, "amount": _fraction(_float_fraction(a.amount)),
             "raise_to": _fraction(_float_fraction(a.target)), "token": a.token}
            for a in node.actions
        ],
        "children": [_tree_json(child) for child in node.children],
    }


def _census_tree(root) -> tuple[list, dict]:
    nodes, seen = [], set()
    totals = {"decision_nodes": 0, "fold_terminals": 0, "showdown_terminals": 0,
              "public_states": 0, "maximum_depth": 0}
    todo = [(root, 1)]
    while todo:
        node, depth = todo.pop()
        if id(node) in seen:
            raise ValueError("Expected an explicit public betting tree")
        seen.add(id(node))
        totals["public_states"] += 1
        totals["maximum_depth"] = max(totals["maximum_depth"], depth)
        nodes.append(node)
        if isinstance(node, numeric._Terminal):
            totals["fold_terminals" if node.winner is not None else "showdown_terminals"] += 1
        else:
            totals["decision_nodes"] += 1
            if len(node.actions) != len(node.children) or not node.actions:
                raise ValueError("Incomplete independent numeric decision")
            todo.extend((child, depth + 1) for child in reversed(node.children))
    return nodes, totals


def _lp_shape(infos: tuple[dict, dict], sequences: tuple[list, list]) -> dict:
    me, mf = len(infos[0]) + 1, len(infos[1]) + 1
    nx, ny = len(sequences[0]), len(sequences[1])
    shapes = {
        "oop_guarantee": (me + ny, nx + 2 * mf + ny + me + ny),
        "ip_ceiling": (mf + nx, ny + 2 * me + nx + mf + nx),
    }
    result = {}
    for name, (rows, columns) in shapes.items():
        cells = (rows + 1) * (columns + 1)
        if (rows > CAPS["rows"] or columns > CAPS["columns"]
                or cells > CAPS["cells"]):
            raise _Limit(f"{name} LP preflight exceeds existing row/column/cell caps")
        result[name] = {"rows": rows, "columns": columns, "cells": cells}
    return result


def build_model(spec: dict | None = None) -> dict:
    """Build a bounded exact matrix after source, tree and LP preflight checks."""
    frozen, provenance, ranges = load_pinned_fixture()
    if spec is not None and spec != frozen:
        raise ValueError("Only the frozen weighted sequence fixture is supported")
    fixture = frozen["fixture"]
    config = numeric._config(fixture["config"])
    root, independent_counts = numeric._build(config)
    nodes, node_counts = _census_tree(root)

    pairs = []
    for source, prior in zip(provenance, EXPECTED_PRIORS):
        sign = Fraction(source["wins"] - source["losses"], BOARDS_PER_PAIR)
        pairs.append({**source, "prior": prior, "showdown_mean": sign})
    if sum((pair["prior"] for pair in pairs), Fraction(0)) != 1:
        raise ValueError("Conditioned private-pair prior does not normalize exactly")

    # Every information set is indexed only by actor, that actor's own hand,
    # and public history. Pair labels and showdown categories stay in chance.
    sequences: list[dict[str, dict]] = [
        {"sb:empty": {"id": "sb:empty", "player": 0, "hand": None,
                       "history": [], "action_token": None, "parent": None}},
        {"bb:empty": {"id": "bb:empty", "player": 1, "hand": None,
                       "history": [], "action_token": None, "parent": None}},
    ]
    parents: list[dict[tuple, str]] = [{}, {}]
    info_actions: list[dict[tuple, tuple]] = [{}, {}]
    info_children: list[dict[tuple, tuple[str, ...]]] = [{}, {}]

    def sequence_id(player: int, hand: str, history: tuple[str, ...], token: str) -> str:
        seat = "sb" if player == 0 else "bb"
        return f"{seat}|{hand}|{'/'.join(history) or 'root'}|{token}"

    def collect(node, current: tuple[str, str], pair: dict) -> None:
        if isinstance(node, numeric._Terminal):
            return
        player = node.player
        hand = pair["sb_hand"] if player == 0 else pair["bb_hand"]
        info = (player, hand, tuple(node.history))
        previous = parents[player].get(info)
        if previous is not None and previous != current[player]:
            raise ValueError(f"Perfect recall failed at {info}")
        parents[player][info] = current[player]
        actions = tuple(action.token for action in node.actions)
        if len(set(actions)) != len(actions):
            raise ValueError(f"Duplicate action token at {info}")
        if info in info_actions[player] and info_actions[player][info] != actions:
            raise ValueError(f"Inconsistent action menu at {info}")
        info_actions[player][info] = actions
        child_ids = []
        for token, child in zip(actions, node.children):
            sid = sequence_id(player, hand, tuple(node.history), token)
            sequence = {"id": sid, "player": player, "hand": hand,
                        "history": list(node.history), "action_token": token,
                        "parent": current[player]}
            old = sequences[player].get(sid)
            if old is not None and old != sequence:
                raise ValueError("Sequence identity collision")
            sequences[player][sid] = sequence
            child_ids.append(sid)
            next_current = list(current)
            next_current[player] = sid
            collect(child, tuple(next_current), pair)
        children = tuple(child_ids)
        if info in info_children[player] and info_children[player][info] != children:
            raise ValueError(f"Inconsistent sequence children at {info}")
        info_children[player][info] = children

    for pair in pairs:
        collect(root, ("sb:empty", "bb:empty"), pair)

    ordered_sequences, indexes = [], []
    infos = ({}, {})
    info_rows = []
    for player in (0, 1):
        root_id = ("sb:empty", "bb:empty")[player]
        names = [root_id] + sorted(key for key in sequences[player] if key != root_id)
        ordered = [sequences[player][key] for key in names]
        ordered_sequences.append(ordered)
        indexes.append({key: index for index, key in enumerate(names)})
        for info in sorted(parents[player], key=lambda key: (key[1], key[2])):
            infos[player][info] = {"tokens": info_actions[player][info],
                                   "children": info_children[player][info]}
            info_rows.append({
                "player": "sb" if player == 0 else "bb", "hand": info[1],
                "history": list(info[2]),
                "parent_sequence": parents[player][info],
                "action_tokens": list(info_actions[player][info]),
                "child_sequences": list(info_children[player][info]),
            })
    infos = tuple(infos)
    ordered_sequences = tuple(ordered_sequences)
    indexes = tuple(indexes)

    # Exact shape/model guards are checked before dense A is materialized.
    shape = _lp_shape(infos, ordered_sequences)
    observed = {
        "decision_nodes": node_counts["decision_nodes"],
        "fold_terminals": node_counts["fold_terminals"],
        "showdown_terminals": node_counts["showdown_terminals"],
        "public_states": node_counts["public_states"],
        "information_sets": tuple(map(len, infos)),
        "sequences": tuple(map(len, ordered_sequences)),
        "oop_lp": (shape["oop_guarantee"]["rows"], shape["oop_guarantee"]["columns"],
                   shape["oop_guarantee"]["cells"]),
        "ip_lp": (shape["ip_ceiling"]["rows"], shape["ip_ceiling"]["columns"],
                  shape["ip_ceiling"]["cells"]),
    }
    if observed != EXPECTED_CENSUS:
        raise ValueError(f"Frozen structural census changed: {observed}")
    expected_tree = frozen["structural_census"]
    if (node_counts["decision_nodes"] != expected_tree["decision_nodes"]
            or node_counts["fold_terminals"] != expected_tree["fold_terminals"]
            or node_counts["showdown_terminals"] != expected_tree["showdown_terminals"]
            or node_counts["public_states"] != expected_tree["public_states"]):
        raise ValueError("Independent numeric tree differs from predeclared census")

    flows, flow_labels = [], []
    for player in (0, 1):
        root_id = ("sb:empty", "bb:empty")[player]
        row = [Fraction(0)] * len(ordered_sequences[player])
        row[indexes[player][root_id]] = Fraction(1)
        flows.append(row)
        flow_labels.append({"id": f"{('sb','bb')[player]}:empty=1",
                            "player": player, "seat": "sb" if player == 0 else "bb",
                            "kind": "root",
                            "parent_sequence": root_id, "child_sequences": [], "rhs": "1"})
        for info in sorted(parents[player], key=lambda key: (key[1], key[2])):
            children = info_children[player][info]
            parent = parents[player][info]
            flows.append(_flow_row(indexes[player][parent],
                                   tuple(indexes[player][child] for child in children),
                                   len(ordered_sequences[player])))
            flow_labels.append({
                "id": f"{('sb','bb')[player]}:flow:{info[1]}:{'/'.join(info[2]) or 'root'}",
                "player": player, "seat": "sb" if player == 0 else "bb",
                "kind": "information_set",
                "parent_sequence": parent, "child_sequences": list(children), "rhs": "0",
            })

    # All showdown quantities are exact rationals. Blinds and matched
    # contributions are represented binary64 inputs, hence exact dyadic values.
    payoff = [[Fraction(0) for _ in ordered_sequences[1]]
              for _ in ordered_sequences[0]]
    pair_by_hands = {(p["sb_hand"], p["bb_hand"]): p for p in pairs}

    def terminal_utility(node, pair: dict) -> Fraction:
        matched = min(_float_fraction(value) for value in node.contributions)
        if node.winner is not None:
            sign = Fraction(1 if node.winner == 0 else -1)
        else:
            sign = pair["showdown_mean"]
        return sign * matched

    def accumulate(node, current: tuple[str, str], pair: dict) -> None:
        if isinstance(node, numeric._Terminal):
            i = indexes[0][current[0]]
            j = indexes[1][current[1]]
            payoff[i][j] += pair["prior"] * terminal_utility(node, pair)
            return
        player = node.player
        hand = pair["sb_hand"] if player == 0 else pair["bb_hand"]
        info = (player, hand, tuple(node.history))
        for token, child in zip(info_actions[player][info], node.children):
            sid = sequence_id(player, hand, tuple(node.history), token)
            next_current = list(current)
            next_current[player] = sid
            accumulate(child, tuple(next_current), pair)

    for pair in pairs:
        accumulate(root, ("sb:empty", "bb:empty"), pair)

    # Recheck exact row/column indexing and sequence-form flow shape.
    if any(len(row) != len(ordered_sequences[1]) for row in payoff):
        raise AssertionError("Payoff matrix shape changed after preflight")
    return {
        "spec": frozen, "fixture": fixture, "source_provenance": provenance,
        "pairs": pairs, "root": root, "nodes": nodes, "node_counts": node_counts,
        "sequences": ordered_sequences, "indexes": indexes,
        "infos": infos, "parents": tuple(parents),
        "info_children": tuple(info_children), "information_sets": info_rows,
        "flows": flows, "flow_labels": flow_labels, "A": payoff,
        "tree_json": _tree_json(root), "lp_shape": shape,
        "independent_tree_counts": independent_counts,
    }


def _realization_policy(model: dict, player: int, realization: list[Fraction]) -> list[dict]:
    index = model["indexes"][player]
    rows = []
    for info in sorted(model["parents"][player], key=lambda key: (key[1], key[2])):
        parent = model["parents"][player][info]
        children = model["info_children"][player][info]
        parent_mass = realization[index[parent]]
        child_masses = [realization[index[child]] for child in children]
        zero = parent_mass == 0
        if zero:
            probabilities = tuple(Fraction(1, len(children)) for _ in children)
        else:
            probabilities = tuple(value / parent_mass for value in child_masses)
        if any(value < 0 for value in probabilities) or sum(probabilities, Fraction(0)) != 1:
            raise ValueError(f"Invalid behavioral policy at {info}")
        rows.append({
            "player": "sb" if player == 0 else "bb", "hand": info[1],
            "history": list(info[2]),
            "action_tokens": list(model["infos"][player][info]["tokens"]),
            "probabilities": [_fraction(value) for value in probabilities],
            "zero_realization_fallback": zero,
        })
    return rows


def _jsonable(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def solve_model(model: dict) -> dict:
    """Solve the preflighted candidate using the unchanged project exact LP."""
    if type(model) is not dict or model.get("spec") is None:
        raise ValueError("Expected a model from build_model")
    lower_lp, sb_realization, sb_dual, sb_slacks = exact_lp._solve_lp(model, "oop_guarantee")
    upper_lp, bb_realization, bb_dual, bb_slacks = exact_lp._solve_lp(model, "ip_ceiling")
    matrix_value = exact_lp._matrix_profile(model, sb_realization, bb_realization)
    lower = sb_dual[0]
    upper = bb_dual[0]
    gap = upper - lower
    if gap < 0 or lower != matrix_value or upper != matrix_value:
        raise ValueError("Primal profile and exact dual bounds do not form an equilibrium")

    residuals = [exact_lp._flow_residuals(model, [sb_realization, bb_realization], player)
                 for player in (0, 1)]
    if sum((left * right for left, right in zip(sb_realization, bb_slacks)), Fraction(0)) != 0:
        raise ValueError("SB realization violates complementary slackness")
    if sum((left * right for left, right in zip(bb_realization, sb_slacks)), Fraction(0)) != 0:
        raise ValueError("BB realization violates complementary slackness")
    policies = _realization_policy(model, 0, sb_realization) + _realization_policy(
        model, 1, bb_realization)
    if any(sum((Fraction(value) for value in row["probabilities"]), Fraction(0)) != 1
           for row in policies):
        raise AssertionError("Serialized behavioral policy is not normalized")

    table_rows = []
    for source, pair in zip(model["source_provenance"], model["pairs"]):
        table_rows.append({
            "sb_hand": pair["sb_hand"], "bb_hand": pair["bb_hand"],
            "wins": source["wins"], "ties": source["ties"], "losses": source["losses"],
            "boards": source["boards"], "prior_fraction": _fraction(pair["prior"]),
            "showdown_mean_fraction": _fraction(pair["showdown_mean"]),
            "source_artifact": source["path"],
            "canonical_artifact_sha256": source["canonical_artifact_sha256"],
            "pinned_git_blob_sha1": source["pinned_git_blob_sha1"],
        })
    public_fixture = {
        "id": model["fixture"]["id"],
        "sb_range": model["fixture"]["sb_range"],
        "bb_range": model["fixture"]["bb_range"],
        "config": model["fixture"]["config"],
    }
    matrix = {
        "row_sequence_ids": [row["id"] for row in model["sequences"][0]],
        "column_sequence_ids": [row["id"] for row in model["sequences"][1]],
        "fractions": [[_fraction(value) for value in row] for row in model["A"]],
    }
    flow_constraints = [
        {**{key: value for key, value in row.items() if key != "player"},
         "player": row["seat"], "player_index": row["player"]}
        for row in model["flow_labels"]
    ]
    result = {
        "schema_version": 1,
        "certificate_id": CERTIFICATE_ID,
        "status": "exact-candidate-feasibility",
        "fixture": public_fixture,
        "count_provenance": {
            "source_commit": SOURCE_COMMIT,
            "rows": table_rows,
            "physical_boards": sum(row["boards"] for row in table_rows),
        },
        "pair_priors": [
            {"sb_hand": row["sb_hand"], "bb_hand": row["bb_hand"],
             "prior_fraction": row["prior_fraction"],
             "showdown_mean_fraction": row["showdown_mean_fraction"]}
            for row in table_rows
        ],
        "census": {
            "public_tree": model["tree_json"],
            "tree_counts": model["node_counts"],
            "sequences": {"sb": model["sequences"][0], "bb": model["sequences"][1]},
            "information_sets": model["information_sets"],
            "flow_constraints": flow_constraints,
            "payoff_matrix": matrix,
            "lp_preflight": model["lp_shape"],
            "independent_numeric_counts": model["independent_tree_counts"],
        },
        "oop_lp": _jsonable(lower_lp),
        "ip_lp": _jsonable(upper_lp),
        "policies": policies,
        "equilibrium": {
            "utility_perspective": "sb_net_transfer_chips",
            "lower_bound_fraction": _fraction(lower),
            "upper_bound_fraction": _fraction(upper),
            "profile_value_fraction": _fraction(matrix_value),
            "gap_fraction": _fraction(gap),
            "nash_conv_fraction": _fraction(gap),
            "flow_residuals": residuals,
            "complementary_slackness": {
                "sb_realization_dot_ip_slack": "0",
                "bb_realization_dot_oop_slack": "0",
            },
            "policy_normalization": "exact",
        },
        "caps": dict(CAPS),
        "scope": model["spec"]["scope"],
    }
    result["artifact_sha256"] = hashlib.sha256(json.dumps(
        result, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()
    return result


def build_and_solve() -> dict:
    """Convenience candidate entry point; publication is owned by the lead."""
    return solve_model(build_model())

