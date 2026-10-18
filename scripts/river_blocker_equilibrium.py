"""Bounded exact sequence-form LP feasibility for one blocker-correlated fixed river game."""
from __future__ import annotations

import hashlib
import json
import sys
import subprocess
import platform
from fractions import Fraction
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from pokerlab.cards import expand_range  # noqa: E402
from scripts import audit_river_rational_certificate as audit  # noqa: E402
from scripts import turn_rational_certificate as exact_helper  # noqa: E402
from scripts import turn_river_validation as validator  # noqa: E402

OUTPUT = REPO / "benchmarks/results/river-blocker-equilibrium-v1.json"
PRIOR_CERTIFICATE_SHA256 = '5acb6b4a0f1fa9a05af36feb2c010ac0b005be0bf29629571d99738b7ba34a34'
CAPS = {"rows": 96, "columns": 256, "cells": 25_000, "pivots": 512,
        "updates": 10_000_000, "bits": 4096, "exact_work": 100_000,
        "exact_depth": 64, "exact_bits": 65_536}


from scripts.river_blocker_fixture import FIXTURE
from scripts.river_sequence_form import (
    _Limit, _solve_lp, _uniform_realizations, _realization_policies,
    _flow_residuals, _matrix_profile, _profile_recursion, _result_object,
    _metric_profile, _jsonable,
)

REFERENCE = REPO / "benchmarks/results/river-blocker-model-v1.json"

def _build_model(fixture):
    board = validator.cards(fixture["board"])
    config = validator._config(fixture["config"], "config")
    ranges = tuple(expand_range(value, board) for value in (fixture["oop"], fixture["ip"]))
    ranges = tuple({h: w for h, w in side.items() if w > 0} for side in ranges)
    worlds, selected = validator._worlds(board, ranges, None)
    if selected:
        raise ValueError("fixed river unexpectedly has future runouts")
    root = validator._public_tree(board, config, config, selected, worlds)
    pending = [(root, 1)]
    seen = set()
    while pending:
        node, depth = pending.pop()
        if id(node) in seen:
            raise ValueError("fixed model must be a tree")
        seen.add(id(node))
        if len(seen) > 51 or depth > 6:
            raise _Limit("fixed-model public-node/depth cap")
        if isinstance(node, validator._Decision):
            if len(node.actions) != len(node.children) or not node.children:
                raise ValueError("incomplete public decision")
            pending.extend((child, depth + 1) for child in node.children)
        elif not isinstance(node, validator._Terminal):
            raise ValueError("chance or unknown node in fixed river model")
    nodes = validator._collect_nodes(root)
    empty = ("oop:empty", "ip:empty")
    sequences = [{empty[p]: {"id": empty[p], "player": p, "hand": None,
                            "history": [], "action_token": None, "parent": None}}
                 for p in (0, 1)]
    infos, parents, children_by_info = [{}, {}], [{}, {}], [{}, {}]

    def seq_id(player, hand, history, token):
        return f"{('oop','ip')[player]}|{hand}|{'/'.join(history) or 'root'}|{token}"

    def collect(node, current, world):
        if isinstance(node, validator._Terminal):
            return
        if isinstance(node, validator._Chance):
            raise ValueError("chance node in sequence construction")
        p = node.player
        hand = "".join(world["hands"][p])
        info = (p, hand, tuple(node.history))
        if info in parents[p] and parents[p][info] != current[p]:
            raise ValueError(f"perfect-recall violation at {info}")
        parents[p][info] = current[p]
        tokens = tuple(action.token for action in node.actions)
        if len(set(tokens)) != len(tokens):
            raise ValueError(f"duplicate legal action token at {info}")
        record = infos[p].get(info)
        if record and record["tokens"] != tokens:
            raise ValueError(f"inconsistent repeated information set {info}")
        infos[p][info] = {"tokens": tokens, "actions": tuple(node.actions)}
        seq_children = []
        for token, child in zip(tokens, node.children):
            sid = seq_id(p, hand, tuple(node.history), token)
            sequence = {"id": sid, "player": p, "hand": hand,
                        "history": list(node.history), "action_token": token,
                        "parent": current[p]}
            if sid in sequences[p] and sequences[p][sid] != sequence:
                raise ValueError("own sequence token identity collision")
            sequences[p][sid] = sequence
            seq_children.append(sid)
            nxt = list(current); nxt[p] = sid
            collect(child, tuple(nxt), world)
        if info in children_by_info[p] and children_by_info[p][info] != tuple(seq_children):
            raise ValueError("inconsistent repeated information-set children")
        children_by_info[p][info] = tuple(seq_children)

    for world in worlds:
        collect(root, empty, world)

    ordered, index = [], []
    for p in (0, 1):
        names = [empty[p]] + sorted(k for k in sequences[p] if k != empty[p])
        ordered.append([sequences[p][k] for k in names])
        index.append({k: i for i, k in enumerate(names)})

    flows, flow_labels = [], []
    for p in (0, 1):
        row = [Fraction(0)] * len(ordered[p]); row[0] = Fraction(1)
        flows.append(row)
        flow_labels.append({"id": f"{('oop','ip')[p]}:empty=1", "player": p,
                            "kind": "root", "parent_sequence": empty[p],
                            "child_sequences": [], "rhs": "1"})
        for info in sorted(infos[p], key=lambda k: (k[1], k[2])):
            row = [Fraction(0)] * len(ordered[p])
            for child in children_by_info[p][info]:
                row[index[p][child]] += 1
            parent = parents[p][info]
            row[index[p][parent]] -= 1
            flows.append(row)
            flow_labels.append({"id": f"{('oop','ip')[p]}:flow:{info[1]}:{'/'.join(info[2]) or 'root'}",
                                "player": p, "kind": "information_set",
                                "parent_sequence": parent,
                                "child_sequences": list(children_by_info[p][info]),
                                "rhs": "0"})

    expected = (3, 18, (16, 20), (49, 53), 17, 21, 6)
    def tree_depth(node):
        if isinstance(node, validator._Terminal):
            return 1
        if isinstance(node, validator._Chance):
            return 1 + max(map(tree_depth, node.branches.values()))
        return 1 + max(map(tree_depth, node.children))
    observed = (len(worlds), len(nodes), (len(infos[0]), len(infos[1])),
                (len(ordered[0]), len(ordered[1])), len(infos[0]) + 1,
                len(infos[1]) + 1, tree_depth(root))
    if observed != expected:
        raise ValueError(f"fixed-fixture sequence census changed: {observed}")

    # Only after the fixed shape census passes do we allocate dense A.
    payoff = [[Fraction(0) for _ in ordered[1]] for _ in ordered[0]]

    def utility(node, world):
        matched = min(node.contributions)
        sign = (1 if node.winner == 0 else -1) if node.kind == "fold" else world["sign"]
        return Fraction.from_float(float(sign * (config.pot / 2 + matched)))

    def payoffs(node, current, world):
        if isinstance(node, validator._Terminal):
            i, j = index[0][current[0]], index[1][current[1]]
            payoff[i][j] += world["weight"] * utility(node, world)
            return
        if isinstance(node, validator._Chance):
            raise ValueError("chance node in payoff construction")
        p = node.player; hand = "".join(world["hands"][p])
        info = (p, hand, tuple(node.history))
        for token, child in zip(infos[p][info]["tokens"], node.children):
            sid = seq_id(p, hand, tuple(node.history), token)
            nxt = list(current); nxt[p] = sid
            payoffs(child, tuple(nxt), world)

    for world in worlds:
        payoffs(root, empty, world)
    info_labels = [{"player": p, "hand": info[1], "history": list(info[2]),
                    "action_tokens": list(infos[p][info]["tokens"]),
                    "parent_sequence": parents[p][info],
                    "child_sequences": list(children_by_info[p][info])}
                   for p in (0, 1)
                   for info in sorted(infos[p], key=lambda k: (k[1], k[2]))]
    return {"fixture": fixture, "board": board, "config": config, "worlds": worlds,
            "root": root, "nodes": nodes, "empty": empty,
            "sequences": ordered, "index": index, "infos": infos,
            "parents": parents, "children_by_info": children_by_info,
            "flows": flows, "flow_labels": flow_labels,
            "information_sets": info_labels, "A": payoff,
            "seq_id": seq_id}


def _validate_uniform(model):
    realization, policies = _uniform_realizations(model)
    _flow_residuals(model, realization, 0)
    _flow_residuals(model, realization, 1)
    matrix_value = _matrix_profile(model, realization[0], realization[1])
    tree_value = _profile_recursion(model, policies)
    if matrix_value != tree_value:
        raise ValueError("uniform sequence payoff fails independent recursive cross-check")
    expected = Fraction(json.loads(REFERENCE.read_bytes())[0]["uniform_metrics"]["value"])
    if matrix_value != expected:
        raise ValueError(f"uniform matrix EV differs from frozen independent reference: {matrix_value}")
    residuals = (_flow_residuals(model, realization, 0) +
                 _flow_residuals(model, realization, 1))
    return {"value_fraction": str(matrix_value), "matrix_equals_independent_tree": True,
            "flow_residuals": residuals}


def _inputs():
    values = audit._source_fingerprints()
    for name in ('scripts/river_sequence_form.py', 'scripts/verify_river_sequence.py', 'tests/test_river_sequence_form.py', 'benchmarks/results/river-rational-certificate-v1.json', 'scripts/river_blocker_fixture.py', 'scripts/river_blocker_equilibrium.py', 'scripts/verify_river_blocker_equilibrium.py', 'tests/test_river_blocker_equilibrium.py', 'benchmarks/results/river-blocker-model-v1.json'):
        values[name] = hashlib.sha256((REPO/name).read_bytes()).hexdigest()
    return dict(sorted(values.items()))


def run_feasibility():
    baseline = subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip()
    inputs = _inputs()
    digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    outputs = []
    for scenario, fixture in {FIXTURE["id"]: FIXTURE}.items():
        model = _build_model(fixture)
        uniform = _validate_uniform(model)
        lower_lp, x, q, lower_slacks = _solve_lp(model, "oop_guarantee")
        upper_lp, y, p, upper_slacks = _solve_lp(model, "ip_ceiling")
        realization = [x, y]
        residuals = [_flow_residuals(model, realization, player) for player in (0, 1)]
        measured = _metric_profile(model, realization, q[0], p[0])
        value = measured["value"]
        metrics = measured["exact"]["metrics"]
        if not (q[0] == value == p[0] == metrics["value_oop"] and
                metrics["oop_best_response_value"] == p[0] and
                metrics["ip_best_response_value"] == -q[0]):
            raise ValueError("LP objectives, profile and exact legal responses differ")
        if any(metrics[name] != 0 for name in (
                "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability")):
            raise ValueError("Candidate is not an exact mutual best response")
        if sum((a*b for a,b in zip(x, upper_slacks)), Fraction(0)) != 0 or sum(
                (a*b for a,b in zip(y, lower_slacks)), Fraction(0)) != 0:
            raise ValueError("Complementary slackness failed")
        if lower_lp["objective"] != q[0] or upper_lp["objective"] != -p[0]:
            raise ValueError("Reported LP objective signs differ")
        if scenario == "river-polarised-bluffcatcher" and value != 25:
            raise ValueError("Known polarised game value differs")
        prior_bytes = (REPO / "benchmarks/results/river-rational-certificate-v1.json").read_bytes()
        if hashlib.sha256(prior_bytes).hexdigest() != PRIOR_CERTIFICATE_SHA256:
            raise ValueError("Prior river certificate hash differs")
        prior = json.loads(prior_bytes)
        for row in prior["results"]:
            if row["scenario"] == scenario and not (
                    Fraction(row["lower_value_bound_fraction"]) <= value <=
                    Fraction(row["upper_value_bound_fraction"])):
                raise ValueError("Candidate value is outside a prior exact interval")
        outputs.append(dict(scenario=scenario, fixture=fixture,
            uniform_crosscheck=uniform,
            sequences=model["sequences"], information_sets=model["information_sets"],
            flow_labels=model["flow_labels"], flow_matrix=model["flows"],
            payoff_matrix=model["A"], flow_residuals=residuals,
            lower_lp=lower_lp, upper_lp=upper_lp,
            rational_strategy=measured["rational_strategy"], exact=measured["exact"],
            float_projection_oracle=measured["float_projection_oracle"],
            float_projection_compare_differences=measured["float_projection_compare_differences"]))
        print(scenario, "EXACT value", value, "NashConv", metrics["nash_conv"],
            "pivots", lower_lp["pivots"], upper_lp["pivots"],
            "cell updates", lower_lp["logical_cell_updates"], upper_lp["logical_cell_updates"], flush=True)
    if _inputs() != inputs or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != digest:
        raise RuntimeError("Feasibility inputs/source changed during execution")
    if subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip() != baseline:
        raise RuntimeError("Git HEAD changed during candidate generation")
    report = dict(schema_version=1, certificate_id="river-blocker-equilibrium-v1",
        status="exact-mutual-response-witnesses", caps=CAPS,
        baseline_git_commit=baseline, python=platform.python_version(),
        generator_sha256=digest, prior_certificate_sha256=PRIOR_CERTIFICATE_SHA256, source_sha256=inputs, results=outputs,
        scope="Exact rational mutual-response witness for one blocker-correlated fixed configured binary64-terminal river game; no unrestricted Hold'em claim.")
    payload = json.dumps(_jsonable(report), sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    candidate = OUTPUT.with_suffix(".candidate.json")
    if candidate.exists():
        raise RuntimeError("Unreviewed candidate output already exists")
    try:
        candidate.write_bytes(payload)
        if json.loads(candidate.read_bytes()) != _jsonable(report):
            raise ValueError("Save/reload mismatch")
        from scripts.verify_river_blocker_equilibrium import verify_saved_artifact
        verify_saved_artifact(candidate)
        if _inputs() != inputs or subprocess.check_output(
                ["git","rev-parse","HEAD"],cwd=REPO,text=True).strip() != baseline:
            raise RuntimeError("Sources or HEAD changed during saved-proof verification")
        candidate.replace(OUTPUT)
    finally:
        candidate.unlink(missing_ok=True)
    print("SAVED AND INDEPENDENTLY VERIFIED", len(payload),
          hashlib.sha256(payload).hexdigest(), flush=True)


if __name__ == "__main__":
    run_feasibility()
