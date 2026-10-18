"""Bounded exact sequence-form candidate for one conditioned turn game."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

from pokerlab.cards import expand_range
from scripts import river_sequence_form as sequence
from scripts import turn_rational_certificate as exact_helper
from scripts import turn_river_validation as rules
from scripts.turn_sequence_fixture import FIXTURE

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "benchmarks" / "results" / "turn-sequence-equilibrium-v1.json"
REFERENCE = ROOT / "benchmarks" / "results" / "turn-sequence-model-v1.json"
REFERENCE_SHA256 = "bf645923e5cbdd4bbffd4492f2ffe730c6780bb0c8ee1a430a7b2725c93c7d69"
CERTIFICATE_ID = "turn-sequence-equilibrium-v1"
EXPECTED_WORLD_SIGNS = {
    ("AhAs", "QhQs", "8d"): 1,
    ("AhAs", "QhQs", "Kd"): 1,
    ("6hTh", "QhQs", "8d"): 1,
    ("6hTh", "QhQs", "Kd"): -1,
}
EXPECTED = {
    "worlds": 4, "public_nodes": 63, "depth_levels": 8,
    "decision_nodes": 28, "chance_nodes": 3, "terminal_nodes": 32,
    "oop_infos": 28, "ip_infos": 14, "oop_sequences": 57,
    "ip_sequences": 29, "oop_flow_rows": 29, "ip_flow_rows": 15,
    "uniform_value": Fraction(2175, 64),
    "uniform_lower": Fraction(25, 16), "uniform_upper": Fraction(75),
    "uniform_nash_conv": Fraction(1175, 16),
}
REQUIRED_SOURCE_PATHS = (
    "scripts/river_sequence_form.py",
    "scripts/turn_sequence_fixture.py",
    "scripts/turn_sequence_equilibrium.py",
    "scripts/verify_turn_sequence.py",
    "scripts/turn_river_validation.py",
    "scripts/turn_rational_certificate.py",
    "scripts/audit_river_rational_certificate.py",
    "pokerlab/cards.py",
    "scripts/preflop_validation.py",
    "tests/test_turn_sequence_equilibrium.py",
    "benchmarks/results/turn-sequence-model-v1.json",
)
LIMITS = {
    "rows": 96, "columns": 256, "cells": 25000, "pivots": 512,
    "updates": 10000000, "bits": 4096,
    "exact_work": 100000, "exact_depth": 64, "exact_bits": 65536,
}


class _BoundedLimit(Exception):
    pass


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _head() -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    value = result.stdout.strip()
    if len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Could not read a full Git HEAD")
    return value


def _source_fingerprints() -> dict[str, str]:
    values = {}
    for relative in REQUIRED_SOURCE_PATHS:
        path = ROOT / relative
        if not path.is_file():
            raise ValueError(f"Required turn-sequence provenance input is missing: {relative}")
        values[relative] = _sha256(path.read_bytes())
    if values["benchmarks/results/turn-sequence-model-v1.json"] != REFERENCE_SHA256:
        raise ValueError("Frozen independent turn model reference changed")
    return dict(sorted(values.items()))


def _snapshot() -> tuple[str, dict[str, str]]:
    return _head(), _source_fingerprints()


def _assert_unchanged(head: str, sources: dict[str, str]) -> None:
    if _head() != head:
        raise ValueError("Git HEAD changed during turn-sequence operation")
    if _source_fingerprints() != sources:
        raise ValueError("Pinned turn-sequence source changed during operation")


def _children(node):
    if isinstance(node, rules._Decision):
        return node.children
    if isinstance(node, rules._Chance):
        return tuple(node.branches.values())
    if isinstance(node, rules._Terminal):
        return ()
    raise TypeError("Unknown public-tree node")


def _preflight_tree(root):
    pending = [(root, 1)]
    seen = set()
    counts = {"decision": 0, "chance": 0, "terminal": 0}
    while pending:
        node, depth = pending.pop()
        if id(node) in seen:
            raise ValueError("Candidate game structure must be a tree")
        seen.add(id(node))
        if depth > 8 or len(seen) > 63:
            raise _BoundedLimit("Public tree exceeds fixed preflight cap")
        if isinstance(node, rules._Decision):
            counts["decision"] += 1
            if not node.actions or len(node.actions) != len(node.children):
                raise ValueError("Incomplete public decision")
        elif isinstance(node, rules._Chance):
            counts["chance"] += 1
            if not node.branches:
                raise ValueError("Chance node has no selected branches")
        elif isinstance(node, rules._Terminal):
            counts["terminal"] += 1
        else:
            raise TypeError("Unknown public-tree node")
        pending.extend((child, depth + 1) for child in _children(node))
    counts["nodes"] = len(seen)
    counts["depth_levels"] = max_depth = max(
        depth for _, depth in _walk_depths(root)
    )
    return counts


def _walk_depths(root):
    pending = [(root, 1)]
    while pending:
        node, depth = pending.pop()
        yield node, depth
        pending.extend((child, depth + 1) for child in _children(node))


def _sequence_id(player, hand, history, token):
    return f"{('oop', 'ip')[player]}|{hand}|{'/'.join(history) or 'root'}|{token}"


def _build_model(fixture):
    """Build A/E/F by traversing each normalized world through its river only."""
    board = rules.cards(fixture["board"])
    config = rules._config(fixture["config"], "config")
    ranges = (
        expand_range(fixture["oop"], board),
        expand_range(fixture["ip"], board),
    )
    ranges = tuple({hand: weight for hand, weight in side.items() if weight > 0}
                   for side in ranges)
    worlds, selected = rules._worlds(board, ranges, fixture["runouts"])
    root = rules._public_tree(board, config, config, selected, worlds)
    census = _preflight_tree(root)
    expected_census = {
        "nodes": 63, "depth_levels": 8, "decision": 28,
        "chance": 3, "terminal": 32,
    }
    if census != expected_census:
        raise ValueError(f"Turn public-tree census changed: {census}")
    observed_worlds = {}
    for world in worlds:
        oop, ip = ("".join(hand) for hand in world["hands"])
        key = (oop, ip, world["river"])
        observed_worlds[key] = world
        if world["sign"] != EXPECTED_WORLD_SIGNS.get(key):
            raise ValueError(f"Unexpected compatible-world sign: {key}")
        if world["weight"] != Fraction(1, 4):
            raise ValueError("Selected four-world fixture must have mass 1/4 per world")
    if set(observed_worlds) != set(EXPECTED_WORLD_SIGNS):
        raise ValueError("Compatible private-hand/runout set changed")
    if sum((world["weight"] for world in worlds), Fraction(0)) != 1:
        raise ValueError("World masses are not globally normalized")

    empty = ("oop:empty", "ip:empty")
    sequences = [
        {empty[p]: {"id": empty[p], "player": p, "hand": None,
                    "history": [], "action_token": None, "parent": None}}
        for p in (0, 1)
    ]
    infos, parents, children_by_info = [{}, {}], [{}, {}], [{}, {}]
    terminals = []

    def collect_world(node, current, world):
        if isinstance(node, rules._Terminal):
            matched = min(node.contributions)
            sign = (1 if node.winner == 0 else -1) if node.kind == "fold" else world["sign"]
            utility = Fraction.from_float(float(sign * (config.pot / 2 + matched)))
            terminals.append({
                "world": {
                    "oop": "".join(world["hands"][0]),
                    "ip": "".join(world["hands"][1]),
                    "river": world["river"],
                },
                "oop_sequence": current[0], "ip_sequence": current[1],
                "kind": node.kind, "winner": node.winner,
                "contributions": [float(v) for v in node.contributions],
                "matched_added_contribution": float(matched),
                "world_mass": world["weight"], "utility": utility,
                "weighted_utility": world["weight"] * utility,
            })
            return
        if isinstance(node, rules._Chance):
            river = world["river"]
            child = node.branches.get(river)
            if child is None:
                raise ValueError("World has no matching selected-river branch")
            # Chance is a branch selector here: keep world mass unchanged and
            # do not alter either player's last own sequence.
            collect_world(child, current, world)
            return
        player = node.player
        hand = "".join(world["hands"][player])
        info = (player, hand, tuple(node.history))
        if info in parents[player] and parents[player][info] != current[player]:
            raise ValueError(f"Perfect-recall failure at {info}")
        parents[player][info] = current[player]
        tokens = tuple(action.token for action in node.actions)
        if len(set(tokens)) != len(tokens):
            raise ValueError(f"Duplicate action token at {info}")
        previous = infos[player].get(info)
        if previous is not None and previous["tokens"] != tokens:
            raise ValueError(f"Inconsistent legal actions at {info}")
        infos[player][info] = {
            "tokens": tokens, "actions": tuple(node.actions),
            "board": tuple(node.board),
        }
        child_ids = []
        for token, child in zip(tokens, node.children):
            sid = _sequence_id(player, hand, tuple(node.history), token)
            record = {
                "id": sid, "player": player, "hand": hand,
                "history": list(node.history), "action_token": token,
                "parent": current[player],
            }
            if sid in sequences[player] and sequences[player][sid] != record:
                raise ValueError("Own-sequence identity collision")
            sequences[player][sid] = record
            child_ids.append(sid)
            updated = list(current)
            updated[player] = sid
            collect_world(child, tuple(updated), world)
        if info in children_by_info[player] and children_by_info[player][info] != tuple(child_ids):
            raise ValueError(f"Inconsistent information-set children at {info}")
        children_by_info[player][info] = tuple(child_ids)

    for world in worlds:
        collect_world(root, empty, world)

    ordered, index = [], []
    for player in (0, 1):
        ids = [empty[player]] + sorted(key for key in sequences[player] if key != empty[player])
        ordered.append([sequences[player][key] for key in ids])
        index.append({key: position for position, key in enumerate(ids)})

    info_labels = [
        {
            "player": player, "hand": info[1], "history": list(info[2]),
            "board": list(infos[player][info]["board"]),
            "street": "turn" if len(infos[player][info]["board"]) == 4 else "river",
            "action_tokens": list(infos[player][info]["tokens"]),
            "parent_sequence": parents[player][info],
            "child_sequences": list(children_by_info[player][info]),
        }
        for player in (0, 1)
        for info in sorted(infos[player], key=lambda key: (key[1], key[2]))
    ]
    flows, flow_labels = [], []
    for player in (0, 1):
        row = [Fraction(0)] * len(ordered[player])
        row[0] = Fraction(1)
        flows.append(row)
        flow_labels.append({
            "id": f"{('oop', 'ip')[player]}:empty=1", "player": player,
            "kind": "root", "parent_sequence": empty[player],
            "child_sequences": [], "rhs": "1",
        })
        for info in sorted(infos[player], key=lambda key: (key[1], key[2])):
            row = [Fraction(0)] * len(ordered[player])
            for child in children_by_info[player][info]:
                row[index[player][child]] += 1
            parent = parents[player][info]
            row[index[player][parent]] -= 1
            flows.append(row)
            flow_labels.append({
                "id": f"{('oop', 'ip')[player]}:flow:{info[1]}:{'/'.join(info[2]) or 'root'}",
                "player": player, "kind": "information_set",
                "parent_sequence": parent,
                "child_sequences": list(children_by_info[player][info]),
                "rhs": "0",
            })

    # Shape gates run before dense payoff-matrix allocation.
    observed_shapes = (
        len(worlds), len(info_labels), len(infos[0]), len(infos[1]),
        len(ordered[0]), len(ordered[1]), len(flows[:len(infos[0]) + 1]),
        len(flows[len(infos[0]) + 1:]),
    )
    expected_shapes = (4, 42, 28, 14, 57, 29, 29, 15)
    if observed_shapes != expected_shapes:
        raise ValueError(f"Turn information/sequence shape changed: {observed_shapes}")
    lower_dims = (len(infos[0]) + 1 + len(ordered[1]),
                  len(ordered[0]) + 2 * (len(infos[1]) + 1) +
                  len(ordered[1]) + len(infos[0]) + 1 + len(ordered[1]))
    upper_dims = (len(infos[1]) + 1 + len(ordered[0]),
                  len(ordered[1]) + 2 * (len(infos[0]) + 1) +
                  len(ordered[0]) + len(infos[1]) + 1 + len(ordered[0]))
    preflight = {
        "oop_guarantee": {
            "rows": lower_dims[0], "columns": lower_dims[1],
            "tableau_cells_including_rhs_and_objective": (lower_dims[0] + 1) * (lower_dims[1] + 1),
        },
        "ip_ceiling": {
            "rows": upper_dims[0], "columns": upper_dims[1],
            "tableau_cells_including_rhs_and_objective": (upper_dims[0] + 1) * (upper_dims[1] + 1),
        },
    }
    if preflight != {
        "oop_guarantee": {"rows": 58, "columns": 174,
                          "tableau_cells_including_rhs_and_objective": 10325},
        "ip_ceiling": {"rows": 72, "columns": 216,
                       "tableau_cells_including_rhs_and_objective": 15841},
    }:
        raise ValueError(f"Sequence LP preflight shape changed: {preflight}")
    for dims in preflight.values():
        if (dims["rows"] > LIMITS["rows"] or dims["columns"] > LIMITS["columns"] or
                dims["tableau_cells_including_rhs_and_objective"] > LIMITS["cells"]):
            raise _BoundedLimit("LP row/column/tableau-cell cap")

    payoff = [[Fraction(0) for _ in ordered[1]] for _ in ordered[0]]
    for terminal in terminals:
        i = index[0][terminal["oop_sequence"]]
        j = index[1][terminal["ip_sequence"]]
        payoff[i][j] += terminal["weighted_utility"]
    if len(terminals) != 68:
        raise ValueError(f"World traversal terminal ledger changed: {len(terminals)}")

    return {
        "fixture": fixture, "board": board, "config": config, "worlds": worlds,
        "selected_runouts": selected, "root": root, "nodes": tuple(rules._collect_nodes(root)),
        "census": census, "empty": empty, "sequences": ordered, "index": index,
        "infos": infos, "parents": parents, "children_by_info": children_by_info,
        "information_sets": info_labels, "flows": flows, "flow_labels": flow_labels,
        "A": payoff, "A_terms": terminals, "preflight": preflight,
        "seq_id": _sequence_id,
    }


def _literal_world_rows(model):
    rows = []
    for world in sorted(model["worlds"], key=lambda w: (
            "".join(w["hands"][0]), "".join(w["hands"][1]), w["river"])):
        rows.append({
            "oop_hand": "".join(world["hands"][0]),
            "ip_hand": "".join(world["hands"][1]),
            "river": world["river"], "mass": str(world["weight"]),
            "showdown_sign_oop": world["sign"],
            "independent_rank_oop": rules.independent_rank(world["board"] + world["hands"][0]),
            "independent_rank_ip": rules.independent_rank(world["board"] + world["hands"][1]),
        })
    return rows


def _reference_profile(root, worlds, policies):
    """Per-world recursive profile replay, separate from sequence-matrix products."""
    def visit(node, world):
        if isinstance(node, rules._Chance):
            child = node.branches.get(world["river"])
            if child is None:
                raise ValueError("Reference world lacks its selected chance branch")
            return visit(child, world)
        if isinstance(node, rules._Terminal):
            matched = min(node.contributions)
            sign = (1 if node.winner == 0 else -1) if node.kind == "fold" else world["sign"]
            return Fraction.from_float(float(sign * (100.0 / 2 + matched)))
        key = (node.player, "".join(world["hands"][node.player]), node.history)
        return sum((probability * visit(child, world)
                    for probability, child in zip(policies[key], node.children)),
                   Fraction(0))
    total = Fraction(0)
    for world in worlds:
        total += world["weight"] * visit(root, world)
    return total


def _policies_to_rows(model, policies):
    rows = []
    for player in (0, 1):
        for info in sorted(model["infos"][player], key=lambda key: (key[1], key[2])):
            hand, history = info[1], info[2]
            node_info = model["infos"][player][info]
            row = {
                "player": "oop" if player == 0 else "ip",
                "hand": hand,
                "street": "turn" if len(node_info["board"]) == 4 else "river",
                "board": list(node_info["board"]),
                "history": list(history),
                "actions": [],
            }
            probabilities = policies[(player, hand, history)]
            if len(probabilities) != len(node_info["actions"]) or sum(probabilities, Fraction(0)) != 1:
                raise ValueError(f"Invalid rational policy row at {(player, hand, history)}")
            for action, probability in zip(node_info["actions"], probabilities):
                row["actions"].append({
                    "name": action.name, "amount": float(action.amount),
                    "raise_to": float(action.raise_to), "history_key": action.token,
                    "probability": float(probability),
                })
            rows.append(row)
    return rows


def _policy_mapping_from_rational_rows(model, rational_rows):
    mapping = {}
    for row in rational_rows:
        player = 0 if row["player"] == "oop" else 1
        key = (player, row["hand"], tuple(row["history"]))
        values = []
        for action in row["actions"]:
            if "probability_fraction" not in action:
                raise ValueError("Rational policy row is missing exact action probabilities")
            values.append(Fraction(action["probability_fraction"]))
        if key in mapping:
            raise ValueError("Duplicate rational policy identity")
        mapping[key] = tuple(values)
    expected = {
        (player, info[1], info[2])
        for player in (0, 1) for info in model["infos"][player]
    }
    if set(mapping) != expected:
        raise ValueError("Rational strategy does not cover every information set")
    return mapping


def _rational_rows(model, policies):
    rows = []
    for player in (0, 1):
        for info in sorted(model["infos"][player], key=lambda key: (key[1], key[2])):
            hand, history = info[1], info[2]
            node_info = model["infos"][player][info]
            probabilities = policies[(player, hand, history)]
            actions = []
            for action, probability in zip(node_info["actions"], probabilities):
                actions.append({
                    "name": action.name, "amount": float(action.amount),
                    "raise_to": float(action.raise_to), "history_key": action.token,
                    "probability_fraction": str(probability),
                    "probability": float(probability),
                })
            rows.append({
                "player": "oop" if player == 0 else "ip", "hand": hand,
                "street": "turn" if len(node_info["board"]) == 4 else "river",
                "board": list(node_info["board"]), "history": list(history),
                "actions": actions,
            })
    return rows


def _complete_replay_result(model, policies, expected_bounds=None):
    """Create rows, compute a float projection, then require full public replay."""
    strategy = _policies_to_rows(model, policies)
    config_dict = model["config"].to_dict()
    pairs = {(world["hands"][0], world["hands"][1]) for world in model["worlds"]}
    result = {
        "board": list(model["board"]),
        "runouts": list(model["selected_runouts"]),
        "runout_mode": "conditioned-subset",
        "reachable_runouts": list(model["selected_runouts"]),
        "config": config_dict,
        "turn_config": config_dict,
        "river_config": config_dict,
        "street_configs": {"turn": config_dict, "river": config_dict},
        "strategy": strategy,
        "info_sets": len(strategy),
        "compatible_world_count": len(model["worlds"]),
        "worlds": len(model["worlds"]),
        "compatible_pairs": len(pairs),
        "deals": len(pairs),
    }
    validated = rules._validate_policy(
        result, model["root"], model["nodes"], model["worlds"],
        model["board"], model["selected_runouts"], runouts_were_omitted=False,
    )
    value = rules._profile(model["root"], model["worlds"], validated, model["config"].pot)
    br_oop = rules._best_response(model["root"], model["worlds"], validated, 0, model["config"].pot)
    br_ip = rules._best_response(model["root"], model["worlds"], validated, 1, model["config"].pot)
    value = float(value)
    br_oop, br_ip = float(br_oop), float(br_ip)
    if expected_bounds is not None:
        lower_value, profile_value, upper_value = expected_bounds
        value = float(profile_value)
        br_oop = float(upper_value)
        br_ip = -float(lower_value)
    gain_oop = max(0.0, br_oop - value)
    gain_ip = max(0.0, br_ip + value)
    result.update({
        "value_oop": value, "value_ip": -value,
        "oop_best_response_value": br_oop,
        "ip_best_response_value": br_ip,
        "oop_best_response_gain": gain_oop,
        "ip_best_response_gain": gain_ip,
        "nash_conv": gain_oop + gain_ip,
        "exploitability": (gain_oop + gain_ip) / 2.0,
        "public_node_count": len(model["nodes"]),
        "selected_runouts": list(model["selected_runouts"]),
    })
    oracle = rules.replay_policy(
        result, FIXTURE["oop"], FIXTURE["ip"], board=FIXTURE["board"],
        config=FIXTURE["config"], river_config=FIXTURE["config"],
        runouts=FIXTURE["runouts"],
    )
    differences = rules.compare_result(result, oracle, tolerance=1e-9)
    return result, oracle, differences, validated


def _independent_exact(model, rational_policies, serialized):
    return exact_helper.evaluate_exact(
        model["root"], model["worlds"], rational_policies, model["config"].pot,
        max_work=100000, max_depth=64, max_bits=65536, result=serialized,
    )


def _fraction_metric_map(exact):
    return {name: str(value) for name, value in exact["metrics"].items()}


def _flow_residual_rows(residuals):
    return [residuals["oop"], residuals["ip"]]


def _check_lp_proof(model, lower, x, q, lower_slacks, upper, y, p, upper_slacks):
    lower_value = q[0]
    upper_value = p[0]
    value = sequence._matrix_profile(model, x, y)
    if not lower_value == value == upper_value:
        raise ValueError("Primal/dual sequence-form bounds do not meet exactly")
    if any(value < 0 for value in (*x, *y, *lower_slacks, *upper_slacks)):
        raise ValueError("Negative realization or inequality slack")
    if len(lower_slacks) != len(model["sequences"][1]):
        raise ValueError("Lower LP slack vector has wrong sequence coverage")
    if len(upper_slacks) != len(model["sequences"][0]):
        raise ValueError("Upper LP slack vector has wrong sequence coverage")
    if any(a * b for a, b in zip(y, lower_slacks)):
        raise ValueError("Lower LP complementarity failed")
    if any(a * b for a, b in zip(x, upper_slacks)):
        raise ValueError("Upper LP complementarity failed")
    residuals = {
        "oop": sequence._flow_residuals(model, [x, y], 0),
        "ip": sequence._flow_residuals(model, [x, y], 1),
    }
    return lower_value, value, upper_value, residuals


def _assert_rational_projection(rational_rows, serialized, validated):
    """Tie exact fractions to rows accepted by the independent float validator."""
    raw = {}
    for row in serialized["strategy"]:
        player = 0 if row["player"] == "oop" else 1
        key = (player, row["hand"], tuple(row["history"]))
        if key in raw:
            raise ValueError("Duplicate serialized row in policy projection")
        raw[key] = row["actions"]
    expected = set(validated)
    if set(raw) != expected:
        raise ValueError("Validated serialized rows have incomplete coverage")
    seen = set()
    for row in rational_rows:
        player = 0 if row["player"] == "oop" else 1
        key = (player, row["hand"], tuple(row["history"]))
        if key in seen or key not in raw or key not in validated:
            raise ValueError("Rational row is not a unique validated policy identity")
        seen.add(key)
        actions = row["actions"]
        raw_actions = raw[key]
        if len(actions) != len(raw_actions) or len(validated[key]) != len(actions):
            raise ValueError("Rational/float policy action counts differ")
        exact_values = []
        for index, (action, raw_action) in enumerate(zip(actions, raw_actions)):
            probability = Fraction(action["probability_fraction"])
            projection = float(probability)
            if (action["probability"] != projection or
                    raw_action["probability"] != projection or
                    validated[key][index] != projection):
                raise ValueError("Exact fraction differs from its validated serialized probability")
            exact_values.append(probability)
        if sum(exact_values, Fraction(0)) != 1:
            raise ValueError("Rational row probabilities do not sum to one")
    if seen != expected:
        raise ValueError("Rational policy does not cover all validated rows")


def _profile_candidate(model):
    uniform_realizations, uniform_policies = sequence._uniform_realizations(model)
    uniform_matrix_value = sequence._matrix_profile(
        model, uniform_realizations[0], uniform_realizations[1],
    )
    uniform_recursive_value = _reference_profile(
        model["root"], model["worlds"], uniform_policies,
    )
    if uniform_matrix_value != uniform_recursive_value:
        raise ValueError("Independent world recursion disagrees with uniform sequence profile")
    if uniform_recursive_value != EXPECTED["uniform_value"]:
        raise ValueError("Uniform reference value changed")

    uniform_serialized, uniform_oracle, uniform_diff, uniform_validated = _complete_replay_result(
        model, uniform_policies, expected_bounds=(
            EXPECTED["uniform_lower"], uniform_recursive_value, EXPECTED["uniform_upper"],
        ),
    )
    uniform_rational_rows = _rational_rows(model, uniform_policies)
    _assert_rational_projection(uniform_rational_rows, uniform_serialized, uniform_validated)
    uniform_exact_policies = _policy_mapping_from_rational_rows(model, uniform_rational_rows)
    uniform_serialized["rational_strategy"] = uniform_rational_rows
    uniform_exact = _independent_exact(model, uniform_exact_policies, uniform_serialized)
    for field, expected in (
        ("value_oop", EXPECTED["uniform_value"]),
        ("lower_value_bound", EXPECTED["uniform_lower"]),
        ("upper_value_bound", EXPECTED["uniform_upper"]),
        ("nash_conv", EXPECTED["uniform_nash_conv"]),
    ):
        actual = (uniform_exact["metrics"][field] if field in uniform_exact["metrics"]
                  else uniform_exact[field])
        if actual != expected:
            raise ValueError(f"Frozen uniform reference changed at {field}: {actual}")
    if any(abs(value) > 1e-9 for value in uniform_diff.values()):
        raise ValueError("Uniform float replay projection did not match its oracle")

    lower, x, q, lower_slacks = sequence._solve_lp(model, "oop_guarantee")
    upper, y, p, upper_slacks = sequence._solve_lp(model, "ip_ceiling")
    lower_value, value, upper_value, flow_residuals = _check_lp_proof(
        model, lower, x, q, lower_slacks, upper, y, p, upper_slacks,
    )
    if not lower_value <= value <= upper_value:
        raise ValueError("Sequence LP bounds do not contain the profile value")
    joint_policies = sequence._realization_policies(model, [x, y])
    rational_rows = _rational_rows(model, joint_policies)
    serialized, float_oracle, float_differences, float_policies = _complete_replay_result(
        model, joint_policies, expected_bounds=(lower_value, value, upper_value),
    )
    # Exact replay uses the exact fraction rows just serialized above, after the
    # separate float projection passed complete validator replay.
    _assert_rational_projection(rational_rows, serialized, float_policies)
    exact_policies = _policy_mapping_from_rational_rows(model, rational_rows)
    serialized["rational_strategy"] = rational_rows
    exact = _independent_exact(model, exact_policies, serialized)
    if exact["metrics"]["nash_conv"] != 0:
        raise ValueError("Exact replay did not certify zero NashConv")
    if (exact["metrics"]["oop_best_response_gain"] != 0 or
            exact["metrics"]["ip_best_response_gain"] != 0 or
            exact["lower_value_bound"] != exact["upper_value_bound"] or
            exact["metrics"]["value_oop"] != lower_value):
        raise ValueError("Exact replay does not match sequence-form primal/dual value")
    if value != exact["metrics"]["value_oop"]:
        raise ValueError("Payoff-matrix value differs from exact profile replay")
    if any(abs(diff) > 1e-9 for diff in float_differences.values()):
        raise ValueError("Candidate float projection failed complete replay comparison")

    def realization(plan, player):
        return {
            "sequence_labels": [row["id"] for row in model["sequences"][player]],
            "fractions": [str(value) for value in plan],
        }

    def dual_values(values, player):
        start = 0 if player == 0 else len(model["infos"][0]) + 1
        count = len(model["infos"][player]) + 1
        return {
            "flow_labels": [row["id"] for row in model["flow_labels"][start:start + count]],
            "fractions": [str(value) for value in values],
        }

    lower_record = {
        **lower,
        "own_realization": realization(x, 0),
        "dual_flow_values": dual_values(q, 1),
        "inequality_slacks": {
            "sequence_labels": [row["id"] for row in model["sequences"][1]],
            "fractions": [str(value) for value in lower_slacks],
        },
    }
    upper_record = {
        **upper,
        "own_realization": realization(y, 1),
        "dual_flow_values": dual_values(p, 0),
        "inequality_slacks": {
            "sequence_labels": [row["id"] for row in model["sequences"][0]],
            "fractions": [str(value) for value in upper_slacks],
        },
    }
    return {
        "fixture": FIXTURE,
        "scenario": FIXTURE["id"],
        "payoff_matrix": [[str(value) for value in row] for row in model["A"]],
        "flow_matrix": [[str(value) for value in row] for row in model["flows"]],
        "flow_labels": model["flow_labels"],
        "information_sets": model["information_sets"],
        "sequences": model["sequences"],
        "flow_residuals": _flow_residual_rows(flow_residuals),
        "lower_lp": lower_record,
        "upper_lp": upper_record,
        "rational_strategy": rational_rows,
        "exact": exact,
        "float_projection_oracle": float_oracle,
        "float_projection_compare_differences": float_differences,
        "uniform_crosscheck": {
            "value_fraction": str(uniform_recursive_value),
            "matrix_equals_independent_tree": uniform_matrix_value == uniform_recursive_value,
            "flow_residuals": (
                sequence._flow_residuals(model, uniform_realizations, 0) +
                sequence._flow_residuals(model, uniform_realizations, 1)
            ),
            "lower_value_fraction": str(uniform_exact["lower_value_bound"]),
            "upper_value_fraction": str(uniform_exact["upper_value_bound"]),
            "nash_conv_fraction": str(uniform_exact["metrics"]["nash_conv"]),
        },
    }


def _report(head: str, sources: dict[str, str], candidate: dict) -> dict:
    generator_hash = sources["scripts/turn_sequence_equilibrium.py"]
    return {
        "schema_version": 1,
        "certificate_id": CERTIFICATE_ID,
        "status": "exact-mutual-response-witnesses",
        "baseline_git_commit": head,
        "generator_sha256": generator_hash,
        "source_sha256": sources,
        "model_reference_sha256": REFERENCE_SHA256,
        "python": platform.python_version(),
        "caps": LIMITS,
        "scope": "Exact rational mutual-response witness for one selected-river configured binary64-terminal turn game; no unrestricted Hold'em claim.",
        "limitations": [
            "This is a candidate exact witness for the configured finite game, not a full-deck solution.",
            "The selected river set is conditioned and globally normalized over compatible worlds.",
            "No equilibrium value is asserted unless the exact certificate and independent verifier accept it.",
            "Floating-point replay is reported separately from exact Fraction replay.",
        ],
        "results": [candidate],
    }


def generate():
    """Solve, replay, verify staged bytes, then atomically publish one certificate."""
    head_before, sources_before = _snapshot()
    model = _build_model(FIXTURE)
    candidate = _profile_candidate(model)
    _assert_unchanged(head_before, sources_before)
    report = _report(head_before, sources_before, candidate)
    raw = (json.dumps(sequence._jsonable(report), sort_keys=True, indent=2,
                      ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    verifier = __import__("scripts.verify_turn_sequence", fromlist=["verify_saved_artifact"])
    verify_saved_artifact = verifier.verify_saved_artifact
    descriptor, temp_name = tempfile.mkstemp(
        prefix=".turn-sequence-equilibrium-", suffix=".json.tmp",
        dir=str(OUTPUT.parent),
    )
    temp_path = Path(temp_name)
    previous = OUTPUT.read_bytes() if OUTPUT.exists() else None
    replaced = False
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        verify_saved_artifact(temp_path)
        _assert_unchanged(head_before, sources_before)
        os.replace(temp_path, OUTPUT)
        replaced = True
        verify_saved_artifact(OUTPUT)
        _assert_unchanged(head_before, sources_before)
        return report
    except BaseException:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        if replaced:
            if previous is None:
                OUTPUT.unlink(missing_ok=True)
            else:
                restore_fd, restore_name = tempfile.mkstemp(
                    prefix=".turn-sequence-restore-", suffix=".tmp",
                    dir=str(OUTPUT.parent),
                )
                with os.fdopen(restore_fd, "wb") as stream:
                    stream.write(previous)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(restore_name, OUTPUT)
        raise


if __name__ == "__main__":
    try:
        generate()
    except (sequence._Limit, _BoundedLimit) as exc:
        print(json.dumps({
            "status": "bounded_failure", "fixture": FIXTURE["id"],
            "failure": str(exc), "caps": LIMITS,
            "candidate_report_written": False,
        }, sort_keys=True))
        raise SystemExit(2)
