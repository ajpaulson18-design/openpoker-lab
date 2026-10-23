"""Fixed four-call river CFR+ tail follow-up; no retries or target stopping."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime, timezone
from fractions import Fraction

from pokerlab import postflop_solver as postflop
from pokerlab import public_cfr
from pokerlab import river_tail_adapter as tail
from pokerlab.cards import cards
from pokerlab.river_config import RiverConfig
from scripts import benchmark_river_heldout_quality as base
from scripts import turn_river_validation as rules


ROOT = Path(__file__).resolve().parents[1]
RESULT_ID = "river-heldout-tail-v1"
BASELINE_ID = "river-heldout-quality-v1"
BASELINE_HEAD = "df02381625ce72d7922461b97d7c7d238258523e"
BASELINE_REPORT_SHA256 = "5b26d6e9275b4962df4c67be1822594caa3d46291d196f863fe3b65f4353b578"
BASELINE_CLAIM_SHA256 = "f9a6bdd53d71bb4a995e3c5be5be15faa6f25f7d145dcb75e04e76900256279c"
BASELINE_STATUS_SHA256 = "bdf82626ee381f0e4110b75791e36b7fb7a65f86bc427b798561b901db6da523"
BASELINE_POLICIES = {
    "policies/river-unpaired-blocker-tie-raise-materialized-cfrplus-10000.json":
        "f2e4e2d15ba9f2c65cb11e04ed2644196dd4b1df9ae03abff30a015f9f0e4cad",
    "policies/river-unpaired-blocker-tie-raise-matrix-free-cfrplus-10000.json":
        "ab9e7539cb4f424534c01a630a8f769a834273b286d258b820c976d7a41a5bc3",
    "policies/river-paired-short-spr-rank-extremes-materialized-cfrplus-10000.json":
        "81913dc5389c3f52a33fae67c40dc130c9768d8849835752ea087293b9381bfd",
    "policies/river-paired-short-spr-rank-extremes-matrix-free-cfrplus-10000.json":
        "c29c5a24f0b0a8e3f86849bc1792b2d422155aaa9b51c6815c36ae33b44c490e",
}
TARGET = Fraction(1, 1000)
FLOAT_TOLERANCE = 1e-9
GRID = tuple(
    (case["id"], iterations, discard)
    for case in base.CASES
    for iterations, discard in ((10_000, 5_000), (50_000, 25_000))
)
EXTENSION_PINS = (
    "scripts/benchmark_river_heldout_tail.py",
    "docs/river-heldout-tail-protocol.md",
)
_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _json_bytes(value) -> bytes:
    return base._pretty_json_bytes(value)


def _write_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _write_status(path: Path, value) -> None:
    base._write_atomic(path, _json_bytes(value))


def _identity(case_id, iterations, discard):
    return {"scenario": case_id, "backend": "materialized-tail",
            "algorithm": "cfrplus", "iterations": iterations,
            "discard": discard}


def _git_blob_pin(relative: str, expected_commit: str):
    path = ROOT / relative
    if not path.is_file():
        raise RuntimeError(f"Extension source is missing: {relative}")
    raw = path.read_bytes()
    committed = subprocess.check_output(
        ["git", "-C", str(ROOT), "show", f"{expected_commit}:{relative}"],
        stderr=subprocess.STDOUT,
    )
    blob = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", f"{expected_commit}:{relative}"],
        text=True, stderr=subprocess.STDOUT,
    ).strip()
    if _lf(raw) != _lf(committed):
        raise RuntimeError(f"Extension bytes differ from committed source: {relative}")
    return {"bytes": len(raw), "raw_sha256": _sha(raw),
            "normalized_lf_sha256": _sha(_lf(raw)), "git_blob": blob}


def _source_guard(expected_commit: str):
    base_state = base._capture_source_state(expected_commit)
    base._assert_source_pin(base_state, expected_commit)
    base._assert_source_state_valid(base_state, expected_commit)
    extension = {name: _git_blob_pin(name, expected_commit)
                 for name in EXTENSION_PINS}
    baseline_inputs = _baseline_inputs_pin()
    return {"head": expected_commit, "base": base_state,
            "extension": extension, "baseline_inputs": baseline_inputs}


def _assert_same_sources(expected, observed):
    if observed != expected:
        raise RuntimeError("Committed source, extension inputs, or clean HEAD changed")


def _assert_baseline_sources_compatible(historical, current):
    """Authenticate old source identities across checkout line-ending changes."""
    if set(historical) - set(current):
        raise RuntimeError("Current source inventory omits a frozen baseline dependency")
    for name, old in historical.items():
        now = current[name]
        if (old.get("normalized_lf_sha256") != now.get("normalized_lf_sha256") or
                old.get("git_blob") != now.get("git_blob")):
            raise RuntimeError(f"Frozen baseline model/replay source changed: {name}")


def _baseline_inputs_pin():
    """Recheck immutable v1 evidence on every source guard, not only startup."""
    root = ROOT / "benchmarks" / "results" / BASELINE_ID
    report_raw = (root / "report.json").read_bytes()
    claim_raw = (root / "run-claim.json").read_bytes()
    report = json.loads(report_raw.decode("utf-8"))
    claim = json.loads(claim_raw.decode("utf-8"))
    status_raw = (root / "run-status.json").read_bytes()
    status = json.loads(status_raw.decode("utf-8"))
    if (_sha(report_raw) != BASELINE_REPORT_SHA256 or
            _sha(claim_raw) != BASELINE_CLAIM_SHA256 or
            _sha(status_raw) != BASELINE_STATUS_SHA256):
        raise RuntimeError("Frozen v1 report, claim, or status byte hash changed")
    if (report.get("benchmark_id") != BASELINE_ID or
            report.get("source_head") != BASELINE_HEAD or
            claim.get("expected_source_commit") != BASELINE_HEAD or
            report.get("source_sha256") != report.get("source_snapshot") or
            status.get("status") != "completed" or
            status.get("claim_id") != claim.get("claim_id") or
            claim.get("retry_permitted") is not False):
        raise RuntimeError("Frozen v1 baseline provenance or completion state changed")
    expected_profiles = [
        (row["scenario"], row["backend"], row["iterations"], row["policy_sha256"])
        for row in report["results"]
    ]
    status_profiles = [
        (row.get("scenario"), row.get("backend"), row.get("iterations"),
         row.get("policy_sha256")) for row in status.get("profiles", [])
    ]
    if (status.get("schema") != "river-heldout-quality-run-status-v1" or
            status.get("benchmark_id") != BASELINE_ID or
            status.get("status") != "completed" or
            status.get("claim_id") != claim["claim_id"] or
            status.get("retry_permitted") is not False or
            status_profiles != expected_profiles):
        raise RuntimeError("Frozen v1 terminal status changed")
    policy_digests = {}
    for relative, expected_digest in BASELINE_POLICIES.items():
        raw = (root / relative).read_bytes()
        if (_sha(raw) != expected_digest or b"\r" in raw or not raw.endswith(b"\n")):
            raise RuntimeError(f"Frozen baseline policy changed: {relative}")
        policy_digests[relative] = expected_digest
    return {"report_sha256": _sha(report_raw), "claim_sha256": _sha(claim_raw),
            "status_sha256": BASELINE_STATUS_SHA256, "policy_sha256": policy_digests}


def _baseline_check(source_state):
    root = ROOT / "benchmarks" / "results" / BASELINE_ID
    _baseline_inputs_pin()
    report_raw = (root / "report.json").read_bytes()
    claim_raw = (root / "run-claim.json").read_bytes()
    report = json.loads(report_raw.decode("utf-8"))
    claim = json.loads(claim_raw.decode("utf-8"))
    status = json.loads((root / "run-status.json").read_text(encoding="utf-8"))
    if _sha(report_raw) != BASELINE_REPORT_SHA256 or _sha(claim_raw) != BASELINE_CLAIM_SHA256:
        raise RuntimeError("Frozen v1 report or claim byte hash changed")
    if (report.get("benchmark_id") != BASELINE_ID or
            report.get("source_head") != BASELINE_HEAD or
            claim.get("expected_source_commit") != BASELINE_HEAD or
            report.get("source_sha256") != report.get("source_snapshot") or
            status.get("status") != "completed" or
            status.get("claim_id") != claim.get("claim_id") or
            claim.get("retry_permitted") is not False):
        raise RuntimeError("Frozen v1 baseline provenance or completion state changed")
    _assert_baseline_sources_compatible(
        report["source_snapshot"], source_state["base"]["files"])
    expected = {(case["id"], backend, base.ALGORITHM, base.ITERATIONS)
                for case in base.CASES for backend in base.BACKENDS}
    identities = {(row["scenario"], row["backend"], row["algorithm"], row["iterations"])
                  for row in report["results"]}
    claim_identities = {
        (row["scenario"], row["backend"], row["algorithm"], row["iterations"])
        for row in claim["profile_plan"]
    }
    if (identities != expected or claim_identities != expected or
            len(report["results"]) != 4 or len(claim["profile_plan"]) != 4):
        raise RuntimeError("Frozen v1 baseline no longer has the exact four-call grid")
    for row in report["results"]:
        if (row.get("target_met") is not False or
                row.get("numeric_target_met") is not False or
                row.get("exact_audit", {}).get("target_met") is not False):
            raise RuntimeError("Frozen baseline target misses were altered")
        relative = row["policy_file"]
        if relative not in BASELINE_POLICIES:
            raise RuntimeError("Frozen baseline contains an unexpected policy path")
        raw = (root / relative).read_bytes()
        if (_sha(raw) != BASELINE_POLICIES[relative] or b"\r" in raw or
                row.get("policy_sha256") != BASELINE_POLICIES[relative] or
                not raw.endswith(b"\n") or len(raw) != row["policy_bytes"]):
            raise RuntimeError(f"Frozen baseline policy changed: {relative}")
        policy = json.loads(raw.decode("utf-8"))
        audit = base._audit_policy(policy, base._case_by_id(row["scenario"]))
        if audit["exact"] != row["exact_audit"]:
            raise RuntimeError(f"Frozen baseline exact replay changed: {relative}")
        base._compare_metric_maps(audit["metrics"], row["metrics"], relative)
    return {"report_sha256": _sha(report_raw), "claim_sha256": _sha(claim_raw),
            "policy_sha256": dict(BASELINE_POLICIES), "profiles_replayed": 4}


def _case_preflight(case, iterations, discard):
    board = cards(case["board"])
    config = RiverConfig.from_dict(case["config"])
    ranges = (rules.expand_range(case["oop"], board),
              rules.expand_range(case["ip"], board))
    candidate_work = len(ranges[0]) * len(ranges[1]) * iterations
    if candidate_work > postflop._MAX_CANDIDATE_HAND_ITERATIONS:
        raise ValueError("River-tail candidate hand-pair iteration cap exceeded")
    hands, worlds, selected, pair_count = postflop._enumerate_worlds(
        board, case["oop"], case["ip"], iterations=iterations)
    if selected:
        raise ValueError("Fixed river cases may not contain future runouts")
    counts = {}
    root, nodes, chance_nodes, visited_nodes, _ = postflop._build_postflop_tree(
        board, config, worlds=worlds, allocation_counts=counts)
    world_iterations = len(worlds) * iterations
    world_node_work = len(worlds) * visited_nodes * iterations * 3
    dense_work = max(map(len, hands)) * counts["total"] * (3 * iterations + 3)
    legal_hands = postflop._prefix_hand_index(worlds)
    info_slots = sum(len(node.actions) * len(legal_hands.get((player, ()), ()))
                     for (player, _history), node in nodes.items())
    infos = {}
    for (player, history), node in nodes.items():
        for hand_index in sorted(legal_hands.get((player, ()), ())):
            infos[(player, hand_index, history)] = len(node.actions)
    _, hand_counts = public_cfr._validate_inputs(
        worlds, infos, iterations, "cfrplus", config.pot, postflop._Chance)
    edges, _marginals = public_cfr._aggregate_prefixes(worlds, hand_counts)
    prefix_edges = sum(map(len, edges.values()))
    limits = {
        "candidate_hand_pair_iterations": postflop._MAX_CANDIDATE_HAND_ITERATIONS,
        "world_iterations": postflop._MAX_WORLD_ITERATIONS,
        "world_node_work": tail.MAX_WORLD_NODE_WORK,
        "dense_hand_state_pass_work": tail.MAX_DENSE_HAND_STATE_PASS_WORK,
        "info_action_slots": tail.MAX_INFO_ACTION_SLOTS,
        "prefix_hand_edges": public_cfr.MAX_PREFIX_EDGES,
        "public_states": postflop._MAX_PUBLIC_STATES,
        "public_nodes": postflop._MAX_PUBLIC_NODES,
    }
    fixed_limits = {
        "candidate_hand_pair_iterations": 3_000_000,
        "world_iterations": 3_000_000,
        "world_node_work": 30_000_000,
        "dense_hand_state_pass_work": 30_000_000,
        "info_action_slots": 1_000_000,
        "prefix_hand_edges": 250_000,
        "public_states": 250_000,
        "public_nodes": 10_000,
    }
    if limits != fixed_limits:
        raise RuntimeError("Current solver resource caps differ from the frozen study caps")
    if (tail.MAX_ITERATIONS != 100_000 or tail.STANDARD_MAX_ITERATIONS != 10_000):
        raise RuntimeError("Current river-tail iteration limits differ from the frozen study")
    measured = {
        "candidate_hand_pair_iterations": candidate_work,
        "world_iterations": world_iterations,
        "world_node_work": world_node_work,
        "dense_hand_state_pass_work": dense_work,
        "info_action_slots": info_slots,
        "prefix_hand_edges": prefix_edges,
        "public_states": counts["total"],
        "public_nodes": len(nodes),
        "worlds": len(worlds),
        "compatible_pairs": pair_count,
        "world_traversal_nodes": visited_nodes,
        "terminal_nodes": counts["terminal"],
        "chance_nodes": chance_nodes,
        "information_sets": len(infos),
        "tree_actions": sum(len(node.actions) for node in nodes.values()),
        "discard": discard,
        "source_iteration_window": [discard + 1, iterations],
        "average_weight_sum": (iterations * (iterations + 1) - discard * (discard + 1)) // 2,
        "regret_passes": 2 * iterations,
        "average_passes": iterations - discard,
        "total_traversal_passes": 3 * iterations - discard,
    }
    for key, limit in limits.items():
        if measured[key] > limit:
            raise ValueError(f"River-tail preflight exceeds {key} cap")
    return {"identity": _identity(case["id"], iterations, discard),
            "admitted": True, "counts_and_work": measured, "limits": limits}


def _preflight_all():
    if base._canonical_cases(base.CASES) != base._canonical_cases(base.preflight.CASES):
        raise RuntimeError("v1 runner and authenticated preflight case manifests differ")
    baseline = base._preflight_all()
    calls = []
    for case_id, iterations, discard in GRID:
        calls.append(_case_preflight(base._case_by_id(case_id), iterations, discard))
    expected = [_identity(*row) for row in GRID]
    if (len(calls) != 4 or
            [row.get("identity") for row in calls] != expected or
            any(row.get("admitted") is not True for row in calls)):
        raise RuntimeError("All four tail calls must preflight before execution")
    return {"baseline_v1": baseline, "tail_calls": calls,
            "fixed_target_fraction": str(TARGET), "target_is_reporting_only": True}


def _validate_preflight_receipt(receipt):
    if not isinstance(receipt, dict):
        raise RuntimeError("Four-call resource preflight did not return a receipt")
    calls = receipt.get("tail_calls")
    if not isinstance(calls, list) or len(calls) != len(GRID):
        raise RuntimeError("Four-call resource preflight is incomplete")
    expected = [_identity(*row) for row in GRID]
    if ([row.get("identity") for row in calls] != expected or
            any(row.get("admitted") is not True for row in calls)):
        raise RuntimeError("All four exact fixed calls must be admitted before claim")
    if (receipt.get("fixed_target_fraction") != str(TARGET) or
            receipt.get("target_is_reporting_only") is not True):
        raise RuntimeError("Preflight target provenance differs from the frozen protocol")
    fixed_limits = {
        "candidate_hand_pair_iterations": 3_000_000,
        "world_iterations": 3_000_000,
        "world_node_work": 30_000_000,
        "dense_hand_state_pass_work": 30_000_000,
        "info_action_slots": 1_000_000,
        "prefix_hand_edges": 250_000,
        "public_states": 250_000,
        "public_nodes": 10_000,
    }
    for call in calls:
        counts, limits = call.get("counts_and_work"), call.get("limits")
        if not isinstance(counts, dict) or not isinstance(limits, dict):
            raise RuntimeError("A four-call preflight entry is incomplete")
        if limits != fixed_limits:
            raise RuntimeError("A preflight entry does not use the fixed original caps")
        for name, limit in fixed_limits.items():
            observed = counts.get(name)
            if type(observed) is not int or not 0 <= observed <= limit:
                raise RuntimeError(f"Preflight resource is over cap: {name}")
    return receipt


def _tail_audit_policy(result, case, iterations, discard, *, preflight):
    if (not isinstance(preflight, dict) or
            preflight.get("identity") != _identity(case["id"], iterations, discard)):
        raise ValueError("Preflight identity differs from the requested tail profile")
    config = RiverConfig.from_dict(case["config"])
    config_json = config.to_dict()
    expected_version = (tail.SOLVER_VERSION if iterations <= tail.STANDARD_MAX_ITERATIONS
                        else tail.LONG_SOLVER_VERSION)
    expected = {
        "algorithm": "cfrplus", "iterations": iterations,
        "requested_iterations": iterations, "discard": discard,
        "source_iteration_window": [discard + 1, iterations],
        "averaged_sweeps": iterations - discard,
        "average_weight_sum": (iterations * (iterations + 1) - discard * (discard + 1)) // 2,
        "average_schedule": "direct-original-linear-sweep-weight-own-reach-tail",
        "update_schedule": "alternating-oop-then-ip",
        "requested_regret_passes": 2 * iterations,
        "requested_average_passes": iterations - discard,
        "requested_total_traversal_passes": 3 * iterations - discard,
        "solver_version": expected_version,
        "strategy_schema": "postflop-strategy-v1",
        "config": config_json, "river_config": config_json,
        "street_configs": {"river": config_json}, "turn_config": None,
        "runouts": [], "reachable_runouts": [], "runout_mode": "none",
        "training_calls": 1,
    }
    if not isinstance(result, dict) or "convergence" in result:
        raise ValueError("Tail result must be a complete fixed-CFR+ policy without target stopping")
    for name, value in expected.items():
        observed = result.get(name)
        if type(value) is int:
            valid = type(observed) is int and observed == value
        else:
            valid = observed == value
        if not valid:
            raise ValueError(f"Tail result metadata mismatch: {name}")

    board = rules.cards(case["board"], 5)
    ranges = (rules.expand_range(case["oop"], board),
              rules.expand_range(case["ip"], board))
    worlds, selected = rules._worlds(board, ranges, None)
    if selected:
        raise ValueError("Complete-board tail policy unexpectedly declares runouts")
    root = rules._public_tree(board, rules._config(config, "config"),
                             rules._config(config, "config"), selected, worlds)
    nodes = rules._collect_nodes(root)
    oracle = rules.replay_policy(result, case["oop"], case["ip"],
                                 board=board, config=config)
    differences = rules.compare_result(result, oracle, tolerance=FLOAT_TOLERANCE)
    if set(differences) != set(base.METRICS):
        raise ValueError("Independent numeric replay must compare all eight metrics")
    base._compare_metric_maps(result, oracle, "tail result and independent replay")
    policies = rules._validate_policy(result, root, nodes, worlds, board, selected,
                                      runouts_were_omitted=True)
    pair_count = len({(world["hands"][0], world["hands"][1]) for world in worlds})
    rules._validate_count_metadata(result, world_count=len(worlds), pair_count=pair_count,
                                   info_count=len(policies), board_length=len(board))
    exact_summary, outcomes = base._exact_result(root, worlds, policies, config, result)
    exact_metrics = exact_summary.get("metrics_fraction")
    exact_target_met = exact_summary.get("target_met")
    exact_differences = None
    exact_result_differences = None
    if exact_summary.get("status") == "admitted":
        groupings = exact_summary.get("chance_groupings", {})
        if set(groupings) != {"scan", "partition"}:
            raise ValueError("Exact audit must include scan and partition groupings")
        scan, partition = groupings["scan"], groupings["partition"]
        if scan.get("metrics_fraction") != partition.get("metrics_fraction"):
            raise ValueError("Exact scan and partition metric maps differ")
        if set(exact_metrics or {}) != set(base.METRICS):
            raise ValueError("Exact replay did not provide all eight metrics")
        exact_as_float = {name: float(Fraction(value)) for name, value in exact_metrics.items()}
        exact_differences = base._compare_metric_maps(
            exact_as_float, oracle, "exact tail model and numeric replay")
        exact_result_differences = base._compare_metric_maps(
            exact_as_float, result, "exact tail model and serialized metrics")
    elif exact_summary.get("status") == "admission-rejected":
        if exact_metrics is not None or exact_target_met is not None:
            raise ValueError("A rejected exact audit must not publish partial metrics")
    else:
        raise ValueError("Exact audit returned an invalid status")

    if not isinstance(preflight, dict) or preflight.get("admitted") is not True:
        raise ValueError("A previously admitted independent preflight is required for saved replay")
    expected_counts = preflight.get("counts_and_work")
    expected_limits = preflight.get("limits")
    if not isinstance(expected_counts, dict) or not isinstance(expected_limits, dict):
        raise ValueError("Preflight receipt is malformed")
    count_checks = {
        "worlds": expected_counts["worlds"],
        "worlds_materialized": expected_counts["worlds"],
        "compatible_pairs": expected_counts["compatible_pairs"],
        "deals": expected_counts["compatible_pairs"],
        "info_sets": expected_counts["information_sets"],
        "public_nodes": expected_counts["public_nodes"],
        "public_states": expected_counts["public_states"],
        "terminal_nodes": expected_counts["terminal_nodes"],
        "chance_nodes": expected_counts["chance_nodes"],
        "world_traversal_nodes": expected_counts["world_traversal_nodes"],
        "tree_actions": expected_counts["tree_actions"],
    }
    for field, expected_value in count_checks.items():
        observed = result.get(field)
        if type(observed) is not int or observed != expected_value:
            raise ValueError(f"Serialized tail policy count differs: {field}")
    top_level_limits = {
        "public_state_limit": 250_000,
        "public_node_limit": 10_000,
        "public_batch_edge_limit": 250_000,
    }
    for field, expected_value in top_level_limits.items():
        observed = result.get(field)
        if type(observed) is not int or observed != expected_value:
            raise ValueError(f"Serialized tail policy cap differs: {field}")
    usage = result.get("resource_usage")
    usage_checks = {
        "full_requested_world_node_work": "world_node_work",
        "full_requested_world_node_work_limit": "world_node_work",
        "full_requested_dense_hand_state_pass_work": "dense_hand_state_pass_work",
        "full_requested_dense_hand_state_pass_work_limit": "dense_hand_state_pass_work",
        "info_action_slots": "info_action_slots",
        "info_action_slots_limit": "info_action_slots",
        "prefix_hand_edges": "prefix_hand_edges",
        "prefix_hand_edge_limit": "prefix_hand_edges",
    }
    if not isinstance(usage, dict):
        raise ValueError("Serialized tail policy is missing resource usage")
    for field, resource in usage_checks.items():
        expected_value = (expected_counts[resource] if not field.endswith("_limit")
                          else expected_limits[resource])
        observed = usage.get(field)
        if type(observed) is not int or observed != expected_value:
            raise ValueError(f"Serialized tail resource usage differs: {field}")
    return {
        "metrics": {name: float(oracle[name]) for name in base.METRICS},
        "numeric_differences": {name: float(differences[name]) for name in base.METRICS},
        "worlds": oracle["worlds"], "compatible_pairs": oracle["compatible_pair_count"],
        "information_sets": oracle["checked_information_sets"],
        "public_decision_nodes": oracle["public_node_count"],
        "exact_audit": exact_summary,
        "exact_vs_result_differences": exact_result_differences,
        "exact_vs_numeric_differences": (None if exact_differences is None else {
            name: float(value) for name, value in exact_differences.items()
        }),
        "numeric_target_met": oracle["nash_conv"] <= float(TARGET),
        "exact_target_met": exact_target_met,
    }


def _solve(case, iterations, discard):
    return tail.solve_river_tail(case["board"], case["oop"], case["ip"],
                                 RiverConfig.from_dict(case["config"]),
                                 iterations=iterations, discard=discard)


def run_batch(attempts_dir, expected_source_commit, *,
              _source_guard=None, _baseline_check_fn=None,
              _preflight_fn=None, _solver=None, _auditor=None):
    if type(expected_source_commit) is not str or not _HEAD_RE.fullmatch(expected_source_commit):
        raise ValueError("An explicit 40-character lowercase source commit is required")
    source_guard = _source_guard or _source_guard_default
    baseline_check = _baseline_check_fn or _baseline_check
    preflight = _preflight_fn or _preflight_all
    solver = _solver or _solve
    auditor = _auditor or _tail_audit_policy
    baseline_state = source_guard(expected_source_commit)
    baseline = baseline_check(baseline_state)
    preflight_result = _validate_preflight_receipt(preflight())
    after_preflight = source_guard(expected_source_commit)
    _assert_same_sources(baseline_state, after_preflight)

    output = Path(attempts_dir).resolve()
    if output.is_relative_to(ROOT.resolve()):
        raise ValueError("Attempt directory must be outside the frozen source checkout")
    output.mkdir(parents=True, exist_ok=False)
    claim = {
        "benchmark_id": RESULT_ID, "claim_id": hashlib.sha256(
            f"{expected_source_commit}:{time.time_ns()}".encode("ascii")).hexdigest()[:32],
        "expected_source_commit": expected_source_commit,
        "baseline_report_sha256": BASELINE_REPORT_SHA256,
        "fixed_grid": [_identity(*row) for row in GRID],
        "target_nash_conv_fraction": str(TARGET),
        "target_is_reporting_only": True, "retry_permitted": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    _write_exclusive(output / "run-claim.json", _json_bytes(claim))
    status = {"claim_id": claim["claim_id"], "status": "running", "completed_profiles": []}
    status_path = output / "run-status.json"
    rows = []
    saved_policy_files = []
    policy_dir = output / "policies"
    try:
        _write_status(status_path, status)
        policy_dir.mkdir()
        for index, (case_id, iterations, discard) in enumerate(GRID, 1):
            case = base._case_by_id(case_id)
            current = source_guard(expected_source_commit)
            _assert_same_sources(baseline_state, current)
            result = solver(case, iterations, discard)
            filename = f"{case_id}-T{iterations}-D{discard}.json"
            raw = _json_bytes(result)
            policy_path = policy_dir / filename
            _write_exclusive(policy_path, raw)
            saved_policy_files.append(filename)
            status = {**status, "phase": "saved-before-audit", "current_profile": index,
                      "saved_policy": filename, "saved_policy_sha256": _sha(raw)}
            _write_status(status_path, status)
            current = source_guard(expected_source_commit)
            _assert_same_sources(baseline_state, current)
            case_preflight = preflight_result["tail_calls"][index - 1]
            audit = auditor(result, case, iterations, discard,
                            preflight=case_preflight)
            current = source_guard(expected_source_commit)
            _assert_same_sources(baseline_state, current)
            reload_raw = (policy_dir / filename).read_bytes()
            if _sha(reload_raw) != _sha(raw):
                raise RuntimeError("Saved tail policy changed before reload replay")
            reloaded = json.loads(reload_raw.decode("utf-8"))
            reloaded_audit = auditor(reloaded, case, iterations, discard,
                                     preflight=case_preflight)
            current = source_guard(expected_source_commit)
            _assert_same_sources(baseline_state, current)
            if audit != reloaded_audit:
                raise RuntimeError("Saved reload replay differs from initial tail audit")
            row = {
                **_identity(case_id, iterations, discard),
                "source_iteration_window": [discard + 1, iterations],
                "average_weight_sum": (iterations * (iterations + 1) - discard * (discard + 1)) // 2,
                "metrics": audit["metrics"], "numeric_target_met": audit["numeric_target_met"],
                "exact_target_met": audit["exact_target_met"],
                "policy_file": f"policies/{filename}", "policy_sha256": _sha(raw),
                "policy_bytes": len(raw), "saved_reload_replay": "passed",
                "worlds": audit["worlds"], "compatible_pairs": audit["compatible_pairs"],
                "information_sets": audit["information_sets"],
                "public_decision_nodes": audit["public_decision_nodes"],
                "preflight": preflight_result["tail_calls"][index - 1],
                "exact_audit": audit["exact_audit"],
                "exact_vs_result_differences": audit["exact_vs_result_differences"],
                "numeric_differences": audit["numeric_differences"],
                "exact_vs_numeric_differences": audit["exact_vs_numeric_differences"],
            }
            rows.append(row)
            status = {"claim_id": claim["claim_id"], "status": "running",
                      "completed_profiles": [row["policy_file"] for row in rows]}
            _write_status(status_path, status)
        final_state = source_guard(expected_source_commit)
        _assert_same_sources(baseline_state, final_state)
        report = {
            "benchmark_id": RESULT_ID, "claim_id": claim["claim_id"],
            "source_head": expected_source_commit, "source_state": baseline_state,
            "baseline_authentication": baseline, "preflight": preflight_result,
            "fixed_grid": {"calls": [_identity(*row) for row in GRID],
                           "algorithm": "cfrplus", "threshold_nash_conv_fraction": str(TARGET),
                           "threshold_is_reporting_only": True},
            "results": rows, "status": "completed",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "limitations": [
                "Two existing finite configured river games only.",
                "T=50,000 is five times the baseline full regret budget; not an equal-cost comparison.",
                "The exact 1/1000 NashConv threshold is a reporting threshold, not a stopping rule.",
                "No unrestricted Hold'em, general convergence, runtime, or performance claim.",
            ],
        }
        _write_exclusive(output / "report.json", _json_bytes(report))
        status = {"claim_id": claim["claim_id"], "status": "completed",
                  "completed_profiles": [row["policy_file"] for row in rows],
                  "retry_permitted": False}
        _write_status(status_path, status)
        return report
    except BaseException as exc:
        failure = {"claim_id": claim["claim_id"], "status": "failed",
                   "failure_type": type(exc).__name__, "failure": str(exc),
                   "saved_policy_files": list(saved_policy_files),
                   "completed_profiles": [row["policy_file"] for row in rows],
                   "retry_permitted": False}
        try:
            _write_exclusive(output / "failure.json", _json_bytes(failure))
        except BaseException:
            pass
        status = {"claim_id": claim["claim_id"], "status": "failed",
                  "completed_profiles": [row["policy_file"] for row in rows],
                  "failure_type": type(exc).__name__, "failure": str(exc),
                  "retry_permitted": False}
        try:
            _write_status(status_path, status)
        except BaseException:
            pass
        raise


def _source_guard_default(expected_commit):
    return _source_guard(expected_commit)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--attempts-dir", required=True)
    args = parser.parse_args(argv)
    report = run_batch(args.attempts_dir, args.expected_source_commit)
    print(json.dumps({"status": report["status"], "results": len(report["results"]),
                      "attempts_dir": str(Path(args.attempts_dir).resolve())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
