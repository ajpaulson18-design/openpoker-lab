"""Small fixed conformance controls for the compiled configured-river API.

This is a correctness harness, not a search or quality benchmark. It keeps raw
Python/native returns and checks policy structure, probability parity, and
independent physical/numeric/exact replay under the repository's existing caps.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import traceback
from fractions import Fraction


FLOAT_POLICY_TOLERANCE = 1e-9
METRIC_TOLERANCE = 1e-8
EXACT_LIMITS = {"work": 100_000, "depth": 64, "fraction_bits": 65_536}
BASE_CASES = (
    {
        "id": "river-unpaired-blocker-tie-raise",
        "board": "AhKdQcJs2d",
        "oop": "AsTc:1,3c4c:0.25,9c9d:0.75,5c6c:0.5",
        "ip": "AsKh:0.5,QhTh:0.75,8c8d:0.25,6c7d:1",
        "config": {"pot": 100, "effective_stack": [120, 80],
                   "bet_sizes": [0.33], "raise_sizes": [0.25],
                   "max_raises": 1, "include_all_in": True},
    },
    {
        "id": "river-paired-short-spr-rank-extremes",
        "board": "9h8h7h2c2d",
        "oop": "6h5h:0.75,AhKh:0.25,9c9d:1,2h2s:0.5",
        "ip": "JhTh:0.5,QhKh:1,8c8d:0.75,7c7d:0.25",
        "config": {"pot": 100, "effective_stack": [70, 80],
                   "bet_sizes": [0.25], "raise_sizes": [0.25],
                   "max_raises": 1, "include_all_in": True},
    },
)
FRESH_CASE = {
    "id": "river-weighted-8x8-blocker-tie-short-refund",
    "board": "AhKdQcJs2d",
    "oop": "AsTc:1,3c4c:0.25,9c9d:0.75,5c6c:0.5,JcTh:0.4,2c3d:0.2,7h8h:0.6,KsQh:0.3",
    "ip": "AsKh:0.5,QhTh:0.75,8c8d:0.25,6c7d:1,3h4h:0.35,5h6h:0.65,9h9s:0.8,KcKs:0.45",
    "config": {"pot": 17.3, "effective_stack": [29.1, 11.2],
               "bet_sizes": [0.33], "raise_sizes": [0.33],
               "max_raises": 1, "include_all_in": True},
}
CHECK_ONLY = {
    "id": "river-royal-flush-tie-anchor",
    "board": "AcKcQcJcTc",
    "oop": "AsAh:1,3d4d:0.25",
    "ip": "QhTh:0.5,8c8d:0.25",
    "config": {"pot": 100, "effective_stack": [120, 80],
               "bet_sizes": [0.33], "raise_sizes": [0.25],
               "max_raises": 1, "include_all_in": True},
    "expected_value_oop_fraction": "0",
}
ITERATIONS = (10, 100)
METRICS = (
    "value_oop", "value_ip", "oop_best_response_value",
    "ip_best_response_value", "oop_best_response_gain",
    "ip_best_response_gain", "nash_conv", "exploitability",
)
SOURCE_HELPERS = (
    "scripts/turn_river_validation.py",
    "scripts/preflop_validation.py",
    "scripts/turn_rational_certificate.py",
    "scripts/benchmark_river_heldout_quality.py",
    "pokerlab/river_tail_adapter.py",
    "pokerlab/river_config.py",
    "pokerlab/river_tree.py",
    "pokerlab/postflop_solver.py",
    "pokerlab/public_cfr.py",
    "pokerlab/public_diagnostics.py",
    "pokerlab/ranked_river.py",
    "pokerlab/native_river_solver.py",
    "scripts/build_native_train.py",
)
NATIVE_SOURCE = "native/fixed_street_train.c"
RUNNER_PATH = Path(__file__).resolve()


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _lf(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _json_bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _write_json(path: Path, value) -> None:
    _write_exclusive(path, _json_bytes(value))


def _atomic_json(path: Path, value) -> None:
    raw = _json_bytes(value)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def _source_inventory(root: Path):
    files = {path.relative_to(root).as_posix(): path
             for path in (root / "pokerlab").rglob("*.py")}
    for relative in SOURCE_HELPERS:
        path = root / relative
        if not path.is_file():
            raise ValueError(f"Required source helper is missing: {relative}")
        files[relative] = path
    files.update({path.relative_to(root).as_posix(): path
                  for path in (root / "native").glob("*.c")})
    return files


def _source_snapshot(root: Path, baseline):
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                   text=True, stderr=subprocess.STDOUT).strip()
    # Reuse the reviewed held-out source authenticator: it checks clean status,
    # the complete pokerlab Python inventory, and committed Git blobs (so
    # assume-unchanged edits cannot evade this snapshot).
    if baseline.REPO_ROOT.resolve() != root.resolve():
        raise RuntimeError("Held-out source authenticator resolved another checkout")
    state = baseline._capture_source_state(head)
    entries = dict(state["files"])

    native_inventory = subprocess.check_output(
        ["git", "-C", str(root), "ls-tree", "-r", "--name-only", head, "--", "native"],
        text=True, stderr=subprocess.STDOUT,
    ).splitlines()
    native_c = {name for name in native_inventory if name.endswith(".c")}
    working_c = {path.relative_to(root).as_posix()
                 for path in (root / "native").glob("*.c")}
    if native_c != working_c:
        raise RuntimeError("Native C source inventory differs from committed HEAD")
    extras = sorted(native_c | {"scripts/build_native_train.py"})
    request = "".join(f"{head}:{name}\n" for name in extras)
    committed_batch = subprocess.check_output(
        ["git", "-C", str(root), "cat-file", "--batch"], input=request.encode("utf-8"),
        stderr=subprocess.PIPE,
    )
    offset = 0
    for name in extras:
        path = root / name
        if not path.is_file():
            raise RuntimeError(f"Required source file is missing: {name}")
        header_end = committed_batch.find(b"\n", offset)
        header = committed_batch[offset:header_end].split()
        if (header_end < 0 or len(header) != 3 or header[1] != b"blob" or
                not header[2].isdigit()):
            raise RuntimeError(f"Committed source blob is missing: {name}")
        blob = header[0].decode("ascii")
        size = int(header[2])
        offset = header_end + 1
        committed = committed_batch[offset:offset + size]
        offset += size
        if len(committed) != size or committed_batch[offset:offset + 1] != b"\n":
            raise RuntimeError("Committed native source batch has an invalid boundary")
        offset += 1
        raw = path.read_bytes()
        if _lf(raw) != _lf(committed):
            raise RuntimeError(f"Working source differs from committed HEAD: {name}")
        entries[name] = {"bytes": len(raw), "raw_sha256": _sha(raw),
                         "normalized_lf_sha256": _sha(_lf(raw)), "git_blob": blob}
    if offset != len(committed_batch):
        raise RuntimeError("Committed native source batch has trailing data")

    runner_raw = RUNNER_PATH.read_bytes()
    return {"head": state["head"], "status": state["status"], "files": entries,
            "runner": {"path": str(RUNNER_PATH), "bytes": len(runner_raw),
                       "raw_sha256": _sha(runner_raw),
                       "normalized_lf_sha256": _sha(_lf(runner_raw))}}


@contextmanager
def _production_helpers_forbidden():
    """Fail loudly if independent audits reach production solve/model helpers."""
    modules = [module for name, module in list(sys.modules.items())
               if name.startswith("pokerlab.") and module is not None]
    forbidden = set()
    class_methods = []
    for module in modules:
        for name, value in vars(module).items():
            if not (callable(value) or isinstance(value, type)):
                continue
            lowered = name.lower()
            if any(token in lowered for token in (
                    "solve", "train", "evaluate", "rank", "build_postflop_tree",
                    "enumerate_worlds", "prefix_hand_index", "cfrplus_target_deltas")):
                forbidden.add(value)
            if isinstance(value, type) and any(token in name for token in (
                    "RankedRiverPayoffs", "TurnRangePayoffs", "MemoizedRankedRiver")):
                forbidden.add(value)
                for method_name in ("values", "joint_marginals"):
                    method = getattr(value, method_name, None)
                    if callable(method):
                        forbidden.add(method)
                        class_methods.append((value, method_name, method))

    calls = []
    replacements = []

    def fail(name):
        def blocked(*args, **kwargs):
            calls.append(name)
            raise RuntimeError(f"Independent audit called blocked production helper: {name}")
        return blocked

    identities = {id(value) for value in forbidden}
    for owner, name, value in class_methods:
        replacements.append((owner, name, value))
        setattr(owner, name, fail(f"{owner.__module__}.{owner.__name__}.{name}"))
    for module in modules:
        for name, value in list(vars(module).items()):
            if id(value) in identities:
                replacements.append((module, name, value))
                setattr(module, name, fail(f"{module.__name__}.{name}"))
    try:
        yield calls
    finally:
        for module, name, value in reversed(replacements):
            setattr(module, name, value)


def _build_snapshot(build: Path, root: Path):
    if not build.is_dir():
        raise ValueError("--build-dir must be an existing directory")
    inventory = sorted(path for path in build.rglob("*") if path.is_file())
    if not inventory:
        raise ValueError("Native build directory is empty")
    files = {}
    for path in inventory:
        rel = path.relative_to(build).as_posix()
        raw = path.read_bytes()
        files[rel] = {"bytes": len(raw), "sha256": _sha(raw)}
    manifests = [path for path in inventory if path.name == "native-train-manifest.json"]
    if len(manifests) != 1:
        raise ValueError("Expected exactly one native-train-manifest.json")
    manifest_path = manifests[0]
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw.decode("utf-8"))
    executable = manifest.get("executable")
    exe_rel = (manifest_path.parent / executable).relative_to(build).as_posix()
    exe_entry = files.get(exe_rel)
    if not isinstance(executable, str) or not exe_entry:
        raise ValueError("Build manifest executable is absent from build directory")
    if manifest.get("executable_sha256") != exe_entry["sha256"]:
        raise ValueError("Native executable hash differs from its build manifest")
    native_raw = (root / NATIVE_SOURCE).read_bytes()
    if (manifest.get("source_sha256") != _sha(native_raw) or
            manifest.get("source_lf_sha256") != _sha(_lf(native_raw))):
        raise ValueError("Build manifest does not match current native C source")
    return {"files": files, "manifest": manifest,
            "manifest_sha256": _sha(manifest_raw)}


def _assert_same(left, right, label):
    if left != right:
        raise RuntimeError(f"{label} changed during conformance controls")


def _load_modules(root: Path):
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    native_module = importlib.import_module("pokerlab.native_river_solver")
    solver = getattr(native_module, "solve_native_river", None)
    if not callable(solver):
        raise RuntimeError("Native API solve_native_river is not callable")
    from pokerlab import river_tail_adapter as python_tail
    from pokerlab.river_config import RiverConfig
    from scripts import benchmark_river_heldout_quality as baseline
    from scripts import preflop_validation as rank_reference
    from scripts import turn_river_validation as rules
    return solver, python_tail, RiverConfig, baseline, rank_reference, rules


def _canonical_case(case):
    # JSON round-trip fixes a stable copy and rejects accidental non-JSON inputs.
    return json.loads(_json_bytes(case).decode("utf-8"))


def _fixed_grid():
    for case in (*BASE_CASES, FRESH_CASE, CHECK_ONLY):
        for iterations in ITERATIONS:
            yield case, iterations


def _strategy_metadata_and_probabilities(native, python_result, tolerance):
    native_rows = native.get("strategy")
    python_rows = python_result.get("strategy")
    if type(native_rows) is not list or type(python_rows) is not list:
        raise ValueError("Both policies must contain complete strategy row lists")
    if len(native_rows) != len(python_rows):
        raise ValueError("Native and Python policies contain different row counts")
    max_probability_delta = 0.0
    for index, (nrow, prow) in enumerate(zip(native_rows, python_rows)):
        if not isinstance(nrow, dict) or not isinstance(prow, dict):
            raise ValueError("Strategy rows must be objects")
        if set(nrow) != {"player", "hand", "street", "board", "history", "actions"}:
            raise ValueError(f"Native strategy row leaks or omits identity fields at {index}")
        if set(prow) != set(nrow):
            raise ValueError(f"Python/native strategy row schemas differ at {index}")
        for field in ("player", "hand", "street", "board", "history"):
            if nrow[field] != prow[field]:
                raise ValueError(f"Strategy row metadata differs at row {index}, {field}")
        nactions, pactions = nrow["actions"], prow["actions"]
        if type(nactions) is not list or type(pactions) is not list or len(nactions) != len(pactions):
            raise ValueError(f"Action row shape differs at strategy row {index}")
        for action_index, (naction, paction) in enumerate(zip(nactions, pactions)):
            if set(naction) != {"name", "amount", "raise_to", "history_key", "probability"}:
                raise ValueError(f"Native action metadata is incomplete at row {index}")
            if set(paction) != set(naction):
                raise ValueError(f"Python/native action fields differ at row {index}")
            for field in ("name", "amount", "raise_to", "history_key"):
                if naction[field] != paction[field]:
                    raise ValueError(f"Legal action metadata differs: row {index}, {field}")
            np, pp = naction["probability"], paction["probability"]
            if (isinstance(np, bool) or not isinstance(np, (int, float)) or
                    isinstance(pp, bool) or not isinstance(pp, (int, float)) or
                    not math.isfinite(float(np)) or not math.isfinite(float(pp))):
                raise ValueError("Policy probabilities must be finite numbers")
            delta = abs(float(np) - float(pp))
            max_probability_delta = max(max_probability_delta, delta)
            if delta > tolerance:
                raise ValueError(f"Policy probability differs above tolerance at row {index}")
    shared_fields = (
        "board", "config", "street_configs", "turn_config", "river_config",
        "runouts", "reachable_runouts", "runout_mode", "iterations",
        "requested_iterations", "discard", "strategy_schema",
    )
    for field in shared_fields:
        if native.get(field) != python_result.get(field):
            raise ValueError(f"Native and Python result metadata differs: {field}")
    return max_probability_delta


def _check_case_result(policy, case, rules, baseline, tolerance):
    board = rules.cards(case["board"], 5)
    config = baseline.RiverConfig.from_dict(case["config"])
    oracle = rules.replay_policy(policy, case["oop"], case["ip"],
                                 board=board, config=config)
    differences = rules.compare_result(policy, oracle, tolerance=tolerance)
    if set(differences) != set(METRICS):
        raise ValueError("Independent replay did not compare all eight diagnostics")
    return oracle, differences


def _manual_check_value(case, rules, rank_reference):
    board = rules.cards(case["board"], 5)
    ranges = (rules.expand_range(case["oop"], board),
              rules.expand_range(case["ip"], board))
    total = numerator = Fraction(0)
    for hand0, weight0 in ranges[0].items():
        for hand1, weight1 in ranges[1].items():
            if set(hand0) & set(hand1):
                continue
            mass = (Fraction.from_float(float(weight0)) *
                    Fraction.from_float(float(weight1)))
            rank0 = rank_reference.independent_rank(board + hand0)
            rank1 = rank_reference.independent_rank(board + hand1)
            sign = (rank0 > rank1) - (rank0 < rank1)
            total += mass
            numerator += mass * sign
    if total <= 0:
        raise ValueError("Check-only control has no compatible physical deals")
    expected = numerator / total * Fraction.from_float(float(case["config"]["pot"])) / 2
    return expected


def _check_only_control_core(case, rules, baseline, rank_reference):
    board = rules.cards(case["board"], 5)
    config = baseline.RiverConfig.from_dict(case["config"])
    ranges = (rules.expand_range(case["oop"], board),
              rules.expand_range(case["ip"], board))
    worlds, selected = rules._worlds(board, ranges, None)
    root = rules._public_tree(board, rules._config(config, "config"),
                              rules._config(config, "config"), selected, worlds)
    nodes = rules._collect_nodes(root)
    expected_rows = {}
    for node in nodes:
        for world in worlds:
            if world["board"][:len(node.board)] != node.board:
                continue
            hand = world["hands"][node.player]
            key = ("oop" if node.player == 0 else "ip", "".join(hand), node.history)
            expected_rows[key] = node
    rows = []
    for (player_name, hand, history), node in sorted(expected_rows.items()):
        actions = rules._row_actions(node)
        check_index = next((i for i, action in enumerate(node.actions)
                            if action.name == "check"), 0)
        row_actions = []
        for index, action in enumerate(actions):
            row_actions.append({**action, "probability": 1.0 if index == check_index else 0.0})
        rows.append({"player": player_name, "hand": hand, "street": "river",
                     "board": list(node.board), "history": list(history),
                     "actions": row_actions})
    pair_count = len({(world["hands"][0], world["hands"][1]) for world in worlds})
    policy = {"board": list(board), "runouts": [], "runout_mode": "none",
              "reachable_runouts": [], "strategy": rows,
              "info_sets": len(expected_rows), "worlds": len(worlds),
              "compatible_pairs": pair_count, "deals": pair_count}
    replay = rules.replay_policy(policy, case["oop"], case["ip"],
                                 board=board, config=config)
    manual = _manual_check_value(case, rules, rank_reference)
    expected = Fraction(case["expected_value_oop_fraction"])
    if manual != expected:
        raise AssertionError(f"Manual check-only rank enumeration changed: {manual}")
    if abs(replay["value_oop"] - float(expected)) > METRIC_TOLERANCE:
        raise AssertionError("Independent check-only replay differs from manual rank anchor")
    validated = rules._validate_policy(policy, root, nodes, worlds, board, selected,
                                       runouts_were_omitted=True)
    exact, _ = baseline._exact_result(root, worlds, validated, config, policy)
    if exact.get("status") != "admitted":
        raise ValueError("Check-only manual anchor must fit the unchanged exact-oracle caps")
    exact_metrics = {name: Fraction(value)
                     for name, value in exact["metrics_fraction"].items()}
    lower = Fraction(exact["lower_value_bound_fraction"])
    upper = Fraction(exact["upper_value_bound_fraction"])
    if (lower != -exact_metrics["ip_best_response_value"] or
            upper != exact_metrics["oop_best_response_value"] or
            not lower <= expected <= upper or
            exact_metrics["oop_best_response_value"] < 0 or
            exact_metrics["ip_best_response_value"] < 0):
        raise ValueError("Check-only manual anchor exact legal BR interval is inconsistent")
    return {"fixture": _canonical_case(case),
            "expected_value_oop_fraction": str(expected),
            "replay_value_oop": replay["value_oop"],
            "replay_value_ip": replay["value_ip"],
            "exact_metrics_fraction": {
                name: str(exact_metrics[name]) for name in METRICS
            },
            "lower_value_bound_fraction": str(lower),
            "upper_value_bound_fraction": str(upper),
            "worlds": replay["worlds"],
            "compatible_pairs": replay["compatible_pair_count"],
            "checked_information_sets": replay["checked_information_sets"],
            "policy": policy}


def _check_only_control(case, rules, baseline, rank_reference):
    with _production_helpers_forbidden() as blocked_calls:
        result = _check_only_control_core(case, rules, baseline, rank_reference)
    if blocked_calls:
        raise RuntimeError(f"Check-only control reached production helpers: {blocked_calls}")
    result["blocked_production_helper_calls"] = blocked_calls
    return result


def _case_structure(case, rules, baseline):
    """No-training independent case/rules census and short-stack control."""
    board = rules.cards(case["board"], 5)
    config = baseline.RiverConfig.from_dict(case["config"])
    ranges = (rules.expand_range(case["oop"], board),
              rules.expand_range(case["ip"], board))
    worlds, selected = rules._worlds(board, ranges, None)
    root = rules._public_tree(board, rules._config(config, "config"),
                              rules._config(config, "config"), selected, worlds)
    nodes = rules._collect_nodes(root)
    action_names = sorted({action.name for node in nodes
                           for action in getattr(node, "actions", ())})
    pending, terminals = [root], []
    while pending:
        node = pending.pop()
        if isinstance(node, rules._Decision):
            pending.extend(node.children)
        elif isinstance(node, rules._Chance):
            pending.extend(node.branches.values())
        elif isinstance(node, rules._Terminal):
            terminals.append(node)
    refund_showdowns = sum(
        node.kind == "showdown" and node.contributions[0] != node.contributions[1]
        for node in terminals
    )
    if case["id"] == FRESH_CASE["id"]:
        if (case["config"]["bet_sizes"] != [0.33] or
                case["config"]["raise_sizes"] != [0.33]):
            raise ValueError("Fresh weighted control must retain configured 0.33 bet/raise sizes")
        if not {"all_in", "raise"}.issubset(action_names) or refund_showdowns == 0:
            raise ValueError("Fresh weighted control lost short all-in/refund/raise coverage")
    return {
        "identity": case["id"], "board": list(board),
        "range_hand_counts": [len(ranges[0]), len(ranges[1])],
        "physical_worlds": len(worlds),
        "compatible_pairs": len({(world["hands"][0], world["hands"][1]) for world in worlds}),
        "public_decision_nodes": len(nodes), "public_action_names": action_names,
        "unequal_showdown_refund_terminals": refund_showdowns,
        "config": config.to_dict(),
    }


def _audit_policy_core(policy, case, modules):
    _, _, RiverConfig, baseline, _, rules = modules
    board = rules.cards(case["board"], 5)
    config = RiverConfig.from_dict(case["config"])
    worlds, selected = rules._worlds(
        board,
        (rules.expand_range(case["oop"], board), rules.expand_range(case["ip"], board)),
        None,
    )
    if selected:
        raise ValueError("River conformance case unexpectedly has future runouts")
    root = rules._public_tree(board, rules._config(config, "config"),
                              rules._config(config, "config"), selected, worlds)
    nodes = rules._collect_nodes(root)
    policies = rules._validate_policy(policy, root, nodes, worlds, board, selected,
                                      runouts_were_omitted=True)
    numeric, differences = _check_case_result(policy, case, rules, baseline, METRIC_TOLERANCE)
    exact, _ = baseline._exact_result(root, worlds, policies, config, policy)
    if exact.get("status") == "admitted":
        groupings = exact.get("chance_groupings", {})
        if set(groupings) != {"scan", "partition"}:
            raise ValueError("Exact oracle must complete both scan and partition modes")
        if groupings["scan"]["metrics_fraction"] != groupings["partition"]["metrics_fraction"]:
            raise ValueError("Exact scan and partition metric maps differ")
        exact_metrics = {name: Fraction(value)
                         for name, value in exact["metrics_fraction"].items()}
        if set(exact_metrics) != set(METRICS):
            raise ValueError("Exact replay did not provide all eight metrics")
        for metric in METRICS:
            if abs(float(exact_metrics[metric]) - float(numeric[metric])) > METRIC_TOLERANCE:
                raise ValueError(f"Exact and numeric replay disagree: {metric}")
            if abs(float(exact_metrics[metric]) - float(policy[metric])) > METRIC_TOLERANCE:
                raise ValueError(f"Exact and serialized policy metric disagree: {metric}")
        lower = Fraction(exact["lower_value_bound_fraction"])
        upper = Fraction(exact["upper_value_bound_fraction"])
        if (lower != -exact_metrics["ip_best_response_value"] or
                upper != exact_metrics["oop_best_response_value"] or
                not lower <= exact_metrics["value_oop"] <= upper or
                exact_metrics["value_ip"] != -exact_metrics["value_oop"] or
                exact_metrics["oop_best_response_gain"] != upper - exact_metrics["value_oop"] or
                exact_metrics["ip_best_response_gain"] != exact_metrics["value_oop"] - lower or
                exact_metrics["nash_conv"] != upper - lower or
                exact_metrics["exploitability"] != exact_metrics["nash_conv"] / 2):
            raise ValueError("Exact response interval or metric identities are inconsistent")
    elif exact.get("status") != "admission-rejected":
        raise ValueError("Exact oracle returned an unknown admission outcome")
    return {
        "numeric_metrics": {name: float(numeric[name]) for name in METRICS},
        "serialized_metric_differences": {name: float(differences[name]) for name in METRICS},
        "worlds": numeric["worlds"],
        "compatible_pairs": numeric["compatible_pair_count"],
        "information_sets": numeric["checked_information_sets"],
        "public_decision_nodes": numeric["public_node_count"],
        "exact_audit": exact,
    }


def _audit_policy(policy, case, modules):
    with _production_helpers_forbidden() as blocked_calls:
        result = _audit_policy_core(policy, case, modules)
    if blocked_calls:
        raise RuntimeError(f"Independent replay reached production helpers: {blocked_calls}")
    result["blocked_production_helper_calls"] = blocked_calls
    return result


def run(source_root: Path, build_dir: Path, output: Path):
    source_root = source_root.resolve()
    build_dir = build_dir.resolve()
    output = output.resolve()
    if output.is_relative_to(source_root) or output.is_relative_to(build_dir):
        raise ValueError("Output directory must be outside source and build directories")
    modules = _load_modules(source_root)
    native_solver, python_tail, RiverConfig, baseline, rank_reference, rules = modules
    source_before = _source_snapshot(source_root, baseline)
    build_before = _build_snapshot(build_dir, source_root)
    check_control = _check_only_control(CHECK_ONLY, rules, baseline, rank_reference)
    case_census = [_case_structure(case, rules, baseline)
                   for case in (*BASE_CASES, FRESH_CASE, CHECK_ONLY)]
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True, exist_ok=False)
    claim = {
        "schema": "compiled-river-conformance-claim-v1",
        "claim_id": hashlib.sha256(
            f"{source_before['head']}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:32],
        "source_head": source_before["head"],
        "source_snapshot": source_before,
        "runner_snapshot": source_before["runner"],
        "build_manifest_sha256": build_before["manifest_sha256"],
        "fixed_cases": [_canonical_case(case)
                        for case in (*BASE_CASES, FRESH_CASE, CHECK_ONLY)],
        "check_only_control": _canonical_case(CHECK_ONLY),
        "independent_case_census": case_census,
        "iterations": list(ITERATIONS),
        "algorithm": "cfrplus", "discard": 0,
        "policy_probability_tolerance": FLOAT_POLICY_TOLERANCE,
        "metric_tolerance": METRIC_TOLERANCE,
        "exact_limits": EXACT_LIMITS,
        "quality_search": False, "retry_permitted": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    profiles = []
    saved_policy_receipts = []
    active_identity = None
    try:
        _write_json(output / "claim.json", claim)
        status = {"claim_id": claim["claim_id"], "status": "running",
                  "completed_profiles": []}
        _atomic_json(output / "status.json", status)
        _write_json(output / "check-only-control.json", check_control)
        for case, iterations in _fixed_grid():
            identity = {"scenario": case["id"], "iterations": iterations,
                        "algorithm": "cfrplus", "discard": 0}
            active_identity = identity
            status = {"claim_id": claim["claim_id"], "status": "running",
                      "active_profile": identity,
                      "completed_profiles": [
                          {"scenario": row["scenario"], "iterations": row["iterations"]}
                          for row in profiles
                      ], "saved_policy_files": saved_policy_receipts}
            _atomic_json(output / "status.json", status)
            before_source = _source_snapshot(source_root, baseline)
            before_build = _build_snapshot(build_dir, source_root)
            _assert_same(source_before, before_source, "Source snapshot")
            _assert_same(build_before, before_build, "Native build snapshot")

            config = RiverConfig.from_dict(case["config"])
            python_result = python_tail.solve_river_tail(
                case["board"], case["oop"], case["ip"], config,
                iterations=iterations, discard=0,
            )
            if not isinstance(python_result, dict):
                raise ValueError("Python reference API must return a complete result object")
            python_name = f"{case['id']}-python-T{iterations}.json"
            native_name = f"{case['id']}-native-T{iterations}.json"
            python_raw = _json_bytes(python_result)
            _write_exclusive(output / "policies" / python_name, python_raw)
            saved_policy_receipts.append({"file": f"policies/{python_name}",
                                          "bytes": len(python_raw),
                                          "sha256": _sha(python_raw), "backend": "python"})
            python_saved = (output / "policies" / python_name).read_bytes()
            if _sha(python_saved) != _sha(python_raw) or python_saved != _json_bytes(
                    json.loads(python_saved.decode("utf-8"))):
                raise RuntimeError("Saved Python policy failed canonical hash reload")
            python_result = json.loads(python_saved.decode("utf-8"))
            after_python_source = _source_snapshot(source_root, baseline)
            after_python_build = _build_snapshot(build_dir, source_root)
            _assert_same(source_before, after_python_source, "Source snapshot")
            _assert_same(build_before, after_python_build, "Native build snapshot")

            native_result = native_solver(
                case["board"], case["oop"], case["ip"], config,
                iterations=iterations, build_directory=build_dir,
            )
            if not isinstance(native_result, dict):
                raise ValueError("Native API must return a complete result object")
            native_raw = _json_bytes(native_result)
            _write_exclusive(output / "policies" / native_name, native_raw)
            saved_policy_receipts.append({"file": f"policies/{native_name}",
                                          "bytes": len(native_raw),
                                          "sha256": _sha(native_raw), "backend": "native"})
            native_saved = (output / "policies" / native_name).read_bytes()
            if _sha(native_saved) != _sha(native_raw) or native_saved != _json_bytes(
                    json.loads(native_saved.decode("utf-8"))):
                raise RuntimeError("Saved native policy failed canonical hash reload")
            native_result = json.loads(native_saved.decode("utf-8"))

            post_source = _source_snapshot(source_root, baseline)
            post_build = _build_snapshot(build_dir, source_root)
            _assert_same(source_before, post_source, "Source snapshot")
            _assert_same(build_before, post_build, "Native build snapshot")

            python_audit = _audit_policy(python_result, case, modules)
            native_audit = _audit_policy(native_result, case, modules)
            if case["id"] == CHECK_ONLY["id"]:
                for backend, audit in (("Python", python_audit), ("native", native_audit)):
                    exact = audit["exact_audit"]
                    if exact.get("status") != "admitted":
                        raise ValueError(f"{backend} royal-flush anchor exceeded exact audit caps")
                    metrics = {name: Fraction(value)
                               for name, value in exact["metrics_fraction"].items()}
                    lower = Fraction(exact["lower_value_bound_fraction"])
                    upper = Fraction(exact["upper_value_bound_fraction"])
                    if (not lower <= 0 <= upper or
                            metrics["oop_best_response_value"] < 0 or
                            metrics["ip_best_response_value"] < 0):
                        raise ValueError(f"{backend} royal-flush exact BR interval excludes zero")
            max_probability_delta = _strategy_metadata_and_probabilities(
                native_result, python_result, FLOAT_POLICY_TOLERANCE)
            metric_deltas = {}
            for metric in METRICS:
                delta = float(native_audit["numeric_metrics"][metric] -
                              python_audit["numeric_metrics"][metric])
                metric_deltas[metric] = delta
                if abs(delta) > METRIC_TOLERANCE:
                    raise ValueError(f"Native/Python metric differs above tolerance: {metric}")
            after_audit_source = _source_snapshot(source_root, baseline)
            after_audit_build = _build_snapshot(build_dir, source_root)
            _assert_same(source_before, after_audit_source, "Source snapshot")
            _assert_same(build_before, after_audit_build, "Native build snapshot")
            if ((output / "policies" / python_name).read_bytes() != python_raw or
                    (output / "policies" / native_name).read_bytes() != native_raw):
                raise RuntimeError("Saved policies changed during independent replay")
            profile = {
                **identity,
                "native_policy": {"file": f"policies/{native_name}",
                                  "bytes": len(native_raw), "sha256": _sha(native_raw)},
                "python_policy": {"file": f"policies/{python_name}",
                                  "bytes": len(python_raw), "sha256": _sha(python_raw)},
                "max_policy_probability_delta": max_probability_delta,
                "native_vs_python_metric_deltas": metric_deltas,
                "native_audit": native_audit,
                "python_audit": python_audit,
            }
            profiles.append(profile)
            status = {"claim_id": claim["claim_id"], "status": "running",
                      "completed_profiles": [
                          {"scenario": row["scenario"], "iterations": row["iterations"]}
                          for row in profiles
                      ]}
            _atomic_json(output / "status.json", status)
        final_source = _source_snapshot(source_root, baseline)
        final_build = _build_snapshot(build_dir, source_root)
        _assert_same(source_before, final_source, "Source snapshot")
        _assert_same(build_before, final_build, "Native build snapshot")
        for saved in saved_policy_receipts:
            raw = (output / saved["file"]).read_bytes()
            if len(raw) != saved["bytes"] or _sha(raw) != saved["sha256"]:
                raise RuntimeError("A saved policy changed before the final receipt")
        report = {
            "schema": "compiled-river-conformance-report-v1",
            "claim_id": claim["claim_id"], "status": "completed",
            "source_snapshot": source_before, "build_snapshot": build_before,
            "check_only_control": check_control,
            "independent_case_census": case_census,
            "profiles": profiles,
            "scope": "Fixed small correctness controls; not a convergence or performance study.",
            "limitations": [
                "No quality search, stopping target, runtime comparison, or performance claim.",
                "Finite river configurations only; source/build identity is required for reproduction.",
            ],
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        _write_json(output / "report.json", report)
        status = {"claim_id": claim["claim_id"], "status": "completed",
                  "completed_profiles": [
                      {"scenario": row["scenario"], "iterations": row["iterations"]}
                      for row in profiles
                  ], "retry_permitted": False}
        _atomic_json(output / "status.json", status)
        return report
    except BaseException as exc:
        failure = {
            "schema": "compiled-river-conformance-failure-v1",
            "claim_id": claim["claim_id"], "status": "failed",
            "failure_type": type(exc).__name__, "failure": str(exc),
            "traceback": traceback.format_exc(),
            "completed_profiles": profiles,
            "saved_policy_files": saved_policy_receipts,
            "active_profile": active_identity,
            "retry_permitted": False,
        }
        try:
            _write_json(output / "failure.json", failure)
        except BaseException:
            pass
        try:
            _atomic_json(output / "status.json", {
                "claim_id": claim["claim_id"], "status": "failed",
                "completed_profiles": [
                    {"scenario": row["scenario"], "iterations": row["iterations"]}
                    for row in profiles
                ], "failure_type": type(exc).__name__,
                "failure": str(exc), "retry_permitted": False,
            })
        except BaseException:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = run(args.source_root, args.build_dir, args.output)
    print(json.dumps({"status": report["status"], "profiles": len(report["profiles"]),
                      "output": str(args.output.resolve())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
