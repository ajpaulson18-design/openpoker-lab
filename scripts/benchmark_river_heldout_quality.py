"""Single fixed-budget held-out river quality batch; never chooses or retries cases."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from fractions import Fraction

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_RELATIVE = "docs/river-heldout-quality-protocol.md"
PREFLIGHT_RELATIVE = "scripts/river_heldout_preflight.py"

from pokerlab import matrix_free_river as matrix_free_module
from pokerlab import postflop_solver as postflop_module
from pokerlab.matrix_free_river import solve_matrix_free_river
from pokerlab.postflop_solver import solve_postflop
from pokerlab.river_config import RiverConfig
from scripts import river_heldout_preflight as preflight
from scripts import turn_rational_certificate as exact
from scripts import turn_river_validation as rules


BENCHMARK_ID = "river-heldout-quality-v1"
ITERATIONS = 10_000
ALGORITHM = "cfrplus"
TARGET_NASH_CONV = Fraction(1, 1000)
FLOAT_TOLERANCE = 1e-9
BACKENDS = ("materialized", "matrix-free")
METRICS = (
    "value_oop", "value_ip", "oop_best_response_value",
    "ip_best_response_value", "oop_best_response_gain",
    "ip_best_response_gain", "nash_conv", "exploitability",
)
LIMITS = {
    "materialized_world_node_work": 30_000_000,
    "matrix_free_hand_state_pass_work": 30_000_000,
    "max_public_decision_nodes": 10_000,
    "max_public_states": 250_000,
    "max_info_action_slots": 1_000_000,
    "max_ranked_fallback_pair_checks": 30_000_000,
    "max_world_count": 200_000,
    "max_oracle_modeled_world_node_work": 8_000_000,
    "exact_work": 100_000,
    "exact_depth": 64,
    "exact_fraction_bits": 65_536,
}
CASES = (
    {
        "id": "river-unpaired-blocker-tie-raise",
        "board": "AhKdQcJs2d",
        "oop": "AsTc:1,3c4c:0.25,9c9d:0.75,5c6c:0.5",
        "ip": "AsKh:0.5,QhTh:0.75,8c8d:0.25,6c7d:1",
        "config": {
            "pot": 100, "effective_stack": [120, 80],
            "bet_sizes": [0.33], "raise_sizes": [0.25],
            "max_raises": 1, "include_all_in": True,
        },
    },
    {
        "id": "river-paired-short-spr-rank-extremes",
        "board": "9h8h7h2c2d",
        "oop": "6h5h:0.75,AhKh:0.25,9c9d:1,2h2s:0.5",
        "ip": "JhTh:0.5,QhKh:1,8c8d:0.75,7c7d:0.25",
        "config": {
            "pot": 100, "effective_stack": [70, 80],
            "bet_sizes": [0.25], "raise_sizes": [0.25],
            "max_raises": 1, "include_all_in": True,
        },
    },
)
_EXPECTED_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
_EXACT_CAP_ERRORS = {
    "Exact rational certificate exceeds its work limit",
    "Exact rational certificate exceeds its depth limit",
    "Exact rational certificate exceeds its node limit",
}


def _canonical_json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def _pretty_json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _normalized_lf(data):
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _source_paths():
    paths = {
        path.relative_to(REPO_ROOT).as_posix(): path
        for path in sorted((REPO_ROOT / "pokerlab").rglob("*.py"))
    }
    for rel in (
        "scripts/turn_river_validation.py",
        "scripts/preflop_validation.py",
        "scripts/turn_rational_certificate.py",
        PREFLIGHT_RELATIVE,
        PROTOCOL_RELATIVE,
        "scripts/benchmark_river_heldout_quality.py",
    ):
        paths[rel] = REPO_ROOT / rel
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise ValueError(f"Frozen source inventory is incomplete: {missing}")
    return paths


def _git_info():
    head = subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        text=True, stderr=subprocess.STDOUT,
    ).strip()
    status = subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain",
         "--untracked-files=all"],
        text=True, stderr=subprocess.STDOUT,
    )
    return head, status


def _capture_source_state(expected_source_commit):
    if type(expected_source_commit) is not str or not _EXPECTED_HEAD_RE.fullmatch(expected_source_commit):
        raise ValueError("--expected-source-commit must be a 40-character lowercase Git hash")
    head, status = _git_info()
    if head != expected_source_commit:
        raise RuntimeError(f"Source HEAD {head} differs from explicit expected commit {expected_source_commit}")
    if status.strip():
        raise RuntimeError("The production checkout must be clean before and during the batch")
    paths = _source_paths()
    committed_inventory = subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), "ls-tree", "-r", "--name-only",
         expected_source_commit, "--", "pokerlab"], text=True,
        stderr=subprocess.STDOUT,
    ).splitlines()
    committed_python = {name for name in committed_inventory if name.endswith(".py")}
    working_python = {name for name in paths if name.startswith("pokerlab/")}
    if committed_python != working_python:
        raise RuntimeError("Production Python source inventory differs from the expected commit")
    names = list(paths)
    request = "".join(f"{expected_source_commit}:{name}\n" for name in names)
    committed_batch = subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), "cat-file", "--batch"],
        input=request.encode("utf-8"), stderr=subprocess.PIPE,
    )
    offset = 0
    files = {}
    for name in names:
        path = paths[name]
        raw = path.read_bytes()
        normalized = _normalized_lf(raw)
        header_end = committed_batch.find(b"\n", offset)
        header = committed_batch[offset:header_end].split()
        if (header_end < 0 or len(header) != 3 or header[1] != b"blob"
                or not header[2].isdigit()):
            raise RuntimeError(f"Expected committed source blob is missing: {name}")
        blob = header[0].decode("ascii")
        size = int(header[2])
        offset = header_end + 1
        committed = committed_batch[offset:offset + size]
        offset += size
        if len(committed) != size or committed_batch[offset:offset + 1] != b"\n":
            raise RuntimeError("Committed source batch has an invalid object boundary")
        offset += 1
        if normalized != _normalized_lf(committed):
            raise RuntimeError(f"Working source differs from expected commit: {name}")
        files[name] = {
            "bytes": len(raw), "raw_sha256": _sha256(raw),
            "normalized_lf_sha256": _sha256(normalized), "git_blob": blob,
        }
    if offset != len(committed_batch):
        raise RuntimeError("Committed source batch has unexpected trailing data")
    return {"head": head, "status": "clean", "files": files}


def _assert_source_pin(state, expected_source_commit):
    if state.get("head") != expected_source_commit or state.get("status") != "clean":
        raise RuntimeError("Production checkout is not at the expected clean frozen source state")
    required = {
        "scripts/turn_river_validation.py", "scripts/preflop_validation.py",
        "scripts/turn_rational_certificate.py", PREFLIGHT_RELATIVE,
        PROTOCOL_RELATIVE, "scripts/benchmark_river_heldout_quality.py",
    }
    required.update(name for name in state.get("files", {}) if name.startswith("pokerlab/"))
    if not required.issubset(state.get("files", {})):
        raise RuntimeError("Frozen source snapshot is missing required model or replay files")
    for name, entry in state["files"].items():
        if not isinstance(entry.get("git_blob"), str) or not entry["git_blob"]:
            raise RuntimeError(f"Frozen Git blob identity is missing for {name}")


def _same_source_state(expected, observed):
    if observed != expected:
        raise RuntimeError("Source, HEAD, or worktree state changed during the held-out batch")


def _canonical_cases(cases):
    return json.loads(_canonical_json_bytes(cases).decode("utf-8"))


def _preflight_all():
    if _canonical_cases(preflight.CASES) != _canonical_cases(CASES):
        raise RuntimeError("Runner board/ranges/config manifest differs from the authenticated preflight helper")
    fresh = preflight.preflight_all()
    if not isinstance(fresh, dict) or fresh.get("schema") != "river-heldout-quality-preflight-v1":
        raise ValueError("Fresh no-training preflight returned an unexpected schema")
    expected_limits = {
        "max_materialized_world_node_work": LIMITS["materialized_world_node_work"],
        "max_matrix_free_hand_state_pass_work": LIMITS["matrix_free_hand_state_pass_work"],
        "max_public_decision_nodes": LIMITS["max_public_decision_nodes"],
        "max_public_states": LIMITS["max_public_states"],
        "max_info_action_slots": LIMITS["max_info_action_slots"],
        "max_ranked_fallback_pair_checks": LIMITS["max_ranked_fallback_pair_checks"],
        "max_world_count": LIMITS["max_world_count"],
        "max_oracle_modeled_world_node_work": LIMITS["max_oracle_modeled_world_node_work"],
        "exact_work": LIMITS["exact_work"], "exact_depth": LIMITS["exact_depth"],
        "exact_fraction_bits": LIMITS["exact_fraction_bits"],
    }
    if fresh.get("limits") != expected_limits:
        raise RuntimeError("Fresh preflight limits differ from the unchanged-cap contract")
    solver_caps = {
        "matrix_free_hand_state_pass_work": matrix_free_module.MAX_HAND_STATE_PASS_WORK,
        "info_action_slots": matrix_free_module.MAX_INFO_ACTION_SLOTS,
        "public_states": matrix_free_module.MAX_PUBLIC_STATES,
        "fallback_pair_checks": matrix_free_module.MAX_FALLBACK_PAIR_CHECKS,
        "public_nodes": postflop_module._MAX_PUBLIC_NODES,
        "postflop_public_states": postflop_module._MAX_PUBLIC_STATES,
        "world_node_work": postflop_module._MAX_WORLD_NODE_WORK,
        "candidate_hand_iterations": postflop_module._MAX_CANDIDATE_HAND_ITERATIONS,
        "world_iterations": postflop_module._MAX_WORLD_ITERATIONS,
        "matrix_free_iterations": matrix_free_module._MAX_ITERATIONS,
    }
    expected_solver_caps = {
        "matrix_free_hand_state_pass_work": LIMITS["matrix_free_hand_state_pass_work"],
        "info_action_slots": LIMITS["max_info_action_slots"],
        "public_states": LIMITS["max_public_states"],
        "fallback_pair_checks": LIMITS["max_ranked_fallback_pair_checks"],
        "public_nodes": LIMITS["max_public_decision_nodes"],
        "postflop_public_states": LIMITS["max_public_states"],
        "world_node_work": LIMITS["materialized_world_node_work"],
        "candidate_hand_iterations": 3_000_000,
        "world_iterations": 3_000_000,
        "matrix_free_iterations": 100_000,
    }
    if solver_caps != expected_solver_caps:
        raise RuntimeError(f"Production solver admission caps changed: {solver_caps}")
    if (exact.MAX_EXACT_WORK != LIMITS["exact_work"] or
            exact.MAX_EXACT_DEPTH != LIMITS["exact_depth"] or
            exact.MAX_FRACTION_BITS != LIMITS["exact_fraction_bits"]):
        raise RuntimeError("Unchanged exact-auditor caps differ from the fixed contract")
    if (rules.MAX_WORLD_COUNT != LIMITS["max_world_count"] or
            rules.MAX_ORACLE_WORK != LIMITS["max_oracle_modeled_world_node_work"]):
        raise RuntimeError("Unchanged independent replay caps differ from the fixed contract")
    census_rows = fresh.get("cases")
    if not isinstance(census_rows, list) or len(census_rows) != len(CASES):
        raise ValueError("Fresh preflight must return census rows for both fixed cases")
    profiles = []
    for case, census in zip(CASES, census_rows):
        if (census.get("id") != case["id"] or
                census.get("board") != list(rules.cards(case["board"], 5)) or
                census.get("ranges") != {"oop": case["oop"], "ip": case["ip"]} or
                _canonical_cases(census.get("config")) != _canonical_cases(case["config"])):
            raise RuntimeError("Fresh census case identity or configuration differs from fixed manifest")
        fixed = census.get("fixed_cfrplus_t10000_preflight")
        if not isinstance(fixed, dict):
            raise ValueError(f"Fresh preflight lacks fixed-budget data for {case['id']}")
        if (fixed.get("iterations") != ITERATIONS or fixed.get("passes_per_iteration") != 3 or
                fixed.get("threshold_nash_conv") != float(TARGET_NASH_CONV) or
                fixed.get("configured_solver_target") is not None):
            raise RuntimeError(f"CFR+ schedule or reporting-only target changed for {case['id']}")
        checks = (
            ("materialized_admitted", "materialized_world_node_work", LIMITS["materialized_world_node_work"], "materialized"),
            ("matrix_free_admitted", "matrix_free_hand_state_pass_work", LIMITS["matrix_free_hand_state_pass_work"], "matrix-free"),
        )
        for admitted_key, work_key, cap, backend in checks:
            work = fixed.get(work_key)
            if fixed.get(admitted_key) is not True or type(work) is not int or work < 0 or work > cap:
                raise RuntimeError(f"Fresh preflight rejects {case['id']} / {backend}")
        for measured, limit_key, expected in (
                ("exact_work", "exact_work_limit", LIMITS["exact_work"]),
                ("exact_tree_depth", "exact_depth_limit", LIMITS["exact_depth"]),
                ("exact_fraction_bits", "exact_fraction_bit_limit", LIMITS["exact_fraction_bits"])):
            caps = fixed.get("other_caps", {})
            observed = caps.get(measured)
            if (caps.get(limit_key) != expected or type(observed) is not int
                    or not 0 <= observed <= expected):
                raise RuntimeError(f"Fresh exact-audit admission {measured} changed for {case['id']}")
        for backend in BACKENDS:
            profiles.append({
                "scenario": case["id"], "backend": backend,
                "algorithm": ALGORITHM, "iterations": ITERATIONS,
                "preflight": {
                    "worlds": census.get("compatible_physical_pairs"),
                    "tree": census.get("tree"), "fixed_budget": fixed,
                },
            })
    if len(profiles) != 4:
        raise RuntimeError("Fresh no-training preflight must admit exactly four fixed profiles")
    return profiles, fresh


def _solve(case, backend, iterations):
    if type(iterations) is not int or iterations != ITERATIONS:
        raise ValueError("Held-out calls are fixed at exactly 10,000 iterations")
    if backend == "materialized":
        return solve_postflop(
            case["board"], case["oop"], case["ip"], case["config"],
            iterations=ITERATIONS, algorithm=ALGORITHM,
            traversal="public-batched", diagnostics="public-batched",
        )
    if backend == "matrix-free":
        return solve_matrix_free_river(
            case["board"], case["oop"], case["ip"], case["config"],
            iterations=ITERATIONS, algorithm=ALGORITHM,
        )
    raise ValueError(f"Unknown frozen backend: {backend}")


def _is_exact_capacity_error(message):
    if message in _EXACT_CAP_ERRORS:
        return True
    prefix, suffix = "Exact rational certificate exceeds the ", "-bit limit"
    return (message.startswith(prefix) and message.endswith(suffix)
            and message[len(prefix):-len(suffix)].isdecimal())


def _exact_result(root, worlds, policies, config, result):
    outcomes = {}
    for mode in ("scan", "partition"):
        try:
            output = exact.evaluate_exact(
                root, worlds, policies, config.pot, result=result,
                max_work=LIMITS["exact_work"],
                max_depth=LIMITS["exact_depth"],
                max_bits=LIMITS["exact_fraction_bits"],
                chance_grouping=mode,
            )
        except ValueError as exc:
            message = str(exc)
            if not _is_exact_capacity_error(message):
                raise
            outcomes[mode] = {"status": "admission-rejected", "reason": message}
        else:
            outcomes[mode] = {"status": "admitted", "output": output}
    admitted = [outcomes[name]["output"] for name in ("scan", "partition")
                if outcomes[name]["status"] == "admitted"]
    summary = {
        "status": ("admitted" if len(admitted) == 2 else "admission-rejected"),
        "chance_groupings": {},
        "metrics_fraction": None,
        "lower_value_bound_fraction": None,
        "upper_value_bound_fraction": None,
        "nash_conv_target_fraction": str(TARGET_NASH_CONV),
        "target_met": None,
    }
    for mode, outcome in outcomes.items():
        if outcome["status"] == "admitted":
            raw = outcome["output"]
            metrics = raw["metrics"]
            summary["chance_groupings"][mode] = {
                "status": "admitted",
                "metrics_fraction": {key: str(metrics[key]) for key in METRICS},
                "lower_value_bound_fraction": str(raw["lower_value_bound"]),
                "upper_value_bound_fraction": str(raw["upper_value_bound"]),
                "nash_conv_target_met": raw["threshold_met"],
                "work": raw["work"], "work_limit": raw["work_limit"],
                "tree_depth": raw["tree_depth"], "depth_limit": raw["depth_limit"],
                "maximum_fraction_bits": raw["maximum_fraction_bits"],
                "fraction_bit_limit": raw["fraction_bit_limit"],
                "work_by_kind": raw["work_by_kind"],
                "normalized_policy_rows": raw["normalized_policy_rows"],
                "normalization_ledger": raw["normalization_ledger"],
                "max_row_adjustment_fraction": str(raw["max_row_adjustment"]),
            }
        else:
            summary["chance_groupings"][mode] = dict(outcome)
    if len(admitted) == 2:
        first, second = admitted
        if first["metrics"] != second["metrics"]:
            raise ValueError("Exact scan and partition metrics disagree")
        lower, upper = first["lower_value_bound"], first["upper_value_bound"]
        value = first["metrics"]["value_oop"]
        expected_lower = -first["metrics"]["ip_best_response_value"]
        expected_upper = first["metrics"]["oop_best_response_value"]
        for output in admitted:
            if (output["lower_value_bound"] != expected_lower or
                    output["upper_value_bound"] != expected_upper or
                    output["threshold_met"] !=
                    (output["metrics"]["nash_conv"] <= TARGET_NASH_CONV)):
                raise ValueError("Exact response interval or threshold differs from its metrics")
        if not lower <= value <= upper:
            raise ValueError("Exact response interval does not contain profile value")
        summary["metrics_fraction"] = {
            key: str(first["metrics"][key]) for key in METRICS
        }
        summary["lower_value_bound_fraction"] = str(lower)
        summary["upper_value_bound_fraction"] = str(upper)
        summary["target_met"] = first["metrics"]["nash_conv"] <= TARGET_NASH_CONV
    return summary, outcomes


def _compare_metric_maps(left, right, label):
    differences = {}
    for name in METRICS:
        if name not in left or name not in right:
            raise ValueError(f"{label} is missing metric {name}")
        a, b = float(left[name]), float(right[name])
        if not math.isfinite(a) or not math.isfinite(b):
            raise ValueError(f"{label} metric {name} is nonfinite")
        difference = abs(a - b)
        if difference > FLOAT_TOLERANCE:
            raise ValueError(f"{label} metric {name} differs by {difference}")
        differences[name] = difference
    return differences


def _audit_policy(result, case):
    if not isinstance(result, dict):
        raise ValueError("Solver result must be a complete object")
    if (result.get("algorithm") != ALGORITHM or
            type(result.get("iterations")) is not int or
            result["iterations"] != ITERATIONS or
            result.get("strategy_schema") != "postflop-strategy-v1" or
            "convergence" in result):
        raise ValueError("Policy is not the requested fixed 10,000-sweep CFR+ profile")
    board = rules.cards(case["board"], 5)
    config = RiverConfig.from_dict(case["config"])
    config_fields = config.to_dict()
    if (result.get("config") != config_fields or
            result.get("river_config") != config_fields or
            result.get("street_configs") != {"river": config_fields} or
            result.get("turn_config") is not None):
        raise ValueError("Serialized policy configuration differs from the frozen river case")
    ranges = (
        rules.expand_range(case["oop"], board),
        rules.expand_range(case["ip"], board),
    )
    worlds, selected = rules._worlds(board, ranges, None)
    if selected:
        raise ValueError("Complete-board held-out cases must have no runout conditioning")
    config_rules = rules._config(config, "config")
    root = rules._public_tree(board, config_rules, config_rules, selected, worlds)
    nodes = rules._collect_nodes(root)

    oracle = rules.replay_policy(
        result, case["oop"], case["ip"], board=board, config=config)
    float_differences = rules.compare_result(
        result, oracle, tolerance=FLOAT_TOLERANCE)
    if set(float_differences) != set(METRICS):
        raise ValueError("Independent numeric replay did not compare all eight metrics")
    _compare_metric_maps(result, oracle, "solver-vs-independent replay")
    policies = rules._validate_policy(
        result, root, nodes, worlds, board, selected,
        runouts_were_omitted=True,
    )
    pair_count = len({
        (world["hands"][0], world["hands"][1]) for world in worlds
    })
    rules._validate_count_metadata(
        result, world_count=len(worlds), pair_count=pair_count,
        info_count=len(policies), board_length=len(board),
    )
    if (oracle["worlds"] != len(worlds) or
            oracle["compatible_pair_count"] != pair_count or
            oracle["checked_information_sets"] != len(policies)):
        raise ValueError("Independent replay counts differ from the reconstructed model")
    exact_summary, exact_outcomes = _exact_result(
        root, worlds, policies, config, result)
    exact_float_differences = None
    exact_result_differences = None
    if exact_summary["status"] == "admitted":
        exact_metrics = exact_outcomes["scan"]["output"]["metrics"]
        exact_float_differences = _compare_metric_maps(
            exact_metrics, oracle, "exact normalized policy-vs-independent replay")
        exact_result_differences = _compare_metric_maps(
            exact_metrics, result, "exact normalized policy-vs-solver result")
    return {
        "metrics": {name: float(oracle[name]) for name in METRICS},
        "float_replay_differences": {
            name: float(float_differences[name]) for name in METRICS
        },
        "worlds": oracle["worlds"],
        "compatible_pairs": oracle["compatible_pair_count"],
        "information_sets": oracle["checked_information_sets"],
        "public_decision_nodes": oracle["public_node_count"],
        "exact": exact_summary,
        "exact_vs_float_replay_differences": exact_float_differences,
        "exact_vs_result_differences": exact_result_differences,
    }


def _write_exclusive(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    return _sha256(data)


def _write_atomic(path, data):
    path = Path(path)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    _write_exclusive(temp, data)
    try:
        os.replace(temp, path)
    except Exception:
        try:
            temp.unlink()
        except OSError:
            pass
        raise
    return _sha256(data)


def _fsync_directory(path):
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _claim_run(attempts_dir, expected_source_commit, profile_plan):
    attempts_dir = Path(attempts_dir).resolve()
    repo = REPO_ROOT.resolve()
    if attempts_dir == repo or repo in attempts_dir.parents:
        raise ValueError("Choose an attempts directory outside the production checkout")
    attempts_dir.mkdir(parents=True, exist_ok=True)
    claim_path = attempts_dir / "run-claim.json"
    if any((attempts_dir / name).exists()
           for name in ("run-status.json", "report.json", "failure.json")):
        raise FileExistsError("Attempt directory already contains batch evidence")
    policy_dir = attempts_dir / "policies"
    if policy_dir.exists() and any(policy_dir.iterdir()):
        raise FileExistsError("Attempt directory already contains raw policy files")
    claim = {
        "schema": "river-heldout-quality-run-claim-v1",
        "benchmark_id": BENCHMARK_ID,
        "claim_id": uuid.uuid4().hex,
        "claimed_at_utc": datetime.now(timezone.utc).isoformat(),
        "expected_source_commit": expected_source_commit,
        "profile_plan": profile_plan,
        "iterations": ITERATIONS,
        "algorithm": ALGORITHM,
        "target_is_reporting_only": True,
        "retry_permitted": False,
    }
    _write_exclusive(claim_path, _pretty_json_bytes(claim))
    _fsync_directory(attempts_dir)
    return claim


def _status_payload(claim, status, profiles, error=None):
    output = {
        "schema": "river-heldout-quality-run-status-v1",
        "claim_id": claim["claim_id"],
        "benchmark_id": BENCHMARK_ID,
        "status": status,
        "profiles": profiles,
        "retry_permitted": False,
    }
    if error is not None:
        output["error"] = error
    return output


def _record_failure(attempts_dir, claim, profiles, profile, error):
    error_payload = {
        "schema": "river-heldout-quality-failure-v1",
        "claim_id": claim["claim_id"],
        "profile": profile,
        "error_type": type(error).__name__,
        "error": str(error),
        "raw_policies_preserved": sorted(
            item.get("policy_file") for item in profiles if item.get("policy_file")),
        "retry_permitted": False,
    }
    failure_path = attempts_dir / "failure.json"
    if not failure_path.exists():
        _write_exclusive(failure_path, _pretty_json_bytes(error_payload))
    _write_atomic(
        attempts_dir / "run-status.json",
        _pretty_json_bytes(_status_payload(
            claim, "failed", profiles, {
                "type": type(error).__name__, "message": str(error),
                "failed_profile": profile,
            })),
    )


def _case_by_id(case_id):
    for case in CASES:
        if case["id"] == case_id:
            return case
    raise ValueError(f"Profile references unknown frozen case {case_id}")


def _assert_same_audit(left, right):
    if left["metrics"] != right["metrics"]:
        raise ValueError("Saved-policy replay changed numeric metrics")
    if left["exact"] != right["exact"]:
        raise ValueError("Saved-policy replay changed exact audit outputs")
    for key in ("worlds", "compatible_pairs", "information_sets",
                "public_decision_nodes"):
        if left[key] != right[key]:
            raise ValueError(f"Saved-policy replay changed count {key}")


def run_batch(attempts_dir, expected_source_commit, *, solver=None,
              source_guard=None, preflight=None):
    if type(expected_source_commit) is not str or not _EXPECTED_HEAD_RE.fullmatch(
            expected_source_commit):
        raise ValueError("--expected-source-commit must be supplied as a 40-character lowercase hash")
    solver = _solve if solver is None else solver
    source_guard = _capture_source_state if source_guard is None else source_guard
    baseline = source_guard(expected_source_commit)
    _assert_source_pin(baseline, expected_source_commit)
    _assert_source_state_valid(baseline, expected_source_commit)

    profile_plan, preflight_receipt = (_preflight_all() if preflight is None else preflight(expected_source_commit))
    if len(profile_plan) != 4:
        raise ValueError("All four frozen backend/case profiles must preflight before training")
    if {(row["scenario"], row["backend"], row["iterations"])
            for row in profile_plan} != {
                (case["id"], backend, ITERATIONS)
                for case in CASES for backend in BACKENDS}:
        raise ValueError("Preflight did not admit the exact frozen four-profile grid")
    after_preflight = source_guard(expected_source_commit)
    _same_source_state(baseline, after_preflight)
    _assert_source_state_valid(after_preflight, expected_source_commit)

    attempts_dir = Path(attempts_dir).resolve()
    claim = _claim_run(attempts_dir, expected_source_commit, profile_plan)
    profiles = []
    try:
        _write_atomic(
            attempts_dir / "run-status.json",
            _pretty_json_bytes(_status_payload(claim, "running", profiles)),
        )
        policy_dir = attempts_dir / "policies"
        policy_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        _record_failure(attempts_dir, claim, profiles, {"stage": "claim-initialization"}, exc)
        raise
    for plan in profile_plan:
        case = _case_by_id(plan["scenario"])
        identity = {
            "scenario": case["id"], "backend": plan["backend"],
            "algorithm": ALGORITHM, "iterations": ITERATIONS,
        }
        policy_name = f'{case["id"]}-{plan["backend"]}-cfrplus-{ITERATIONS}.json'
        policy_path = policy_dir / policy_name
        try:
            before_call = source_guard(expected_source_commit)
            _same_source_state(baseline, before_call)
            _assert_source_state_valid(before_call, expected_source_commit)
            started = time.perf_counter()
            result = solver(case, plan["backend"], ITERATIONS)
            if not isinstance(result, dict):
                raise ValueError("Solver did not return a complete policy object")
            raw_policy = _canonical_json_bytes(result)
            complete_call_seconds = time.perf_counter() - started
            if not math.isfinite(complete_call_seconds) or complete_call_seconds < 0:
                raise ValueError("Complete-call timing is nonfinite")
            policy_sha256 = _write_exclusive(policy_path, raw_policy)
            profiles.append({
                **identity, "status": "raw-policy-saved",
                "policy_file": f"policies/{policy_name}",
                "policy_sha256": policy_sha256,
                "policy_bytes": len(raw_policy),
                "complete_call_seconds": complete_call_seconds,
            })
            _write_atomic(
                attempts_dir / "run-status.json",
                _pretty_json_bytes(_status_payload(claim, "running", profiles)),
            )
            after_call = source_guard(expected_source_commit)
            _same_source_state(baseline, after_call)
            _assert_source_state_valid(after_call, expected_source_commit)

            audit_before = _audit_policy(json.loads(raw_policy.decode("utf-8")), case)
            after_validation = source_guard(expected_source_commit)
            _same_source_state(baseline, after_validation)
            _assert_source_state_valid(after_validation, expected_source_commit)
            profiles[-1].update({
                "status": "numeric-replay-passed",
                "metrics": audit_before["metrics"],
                "float_replay_differences": audit_before["float_replay_differences"],
                "worlds": audit_before["worlds"],
                "compatible_pairs": audit_before["compatible_pairs"],
                "information_sets": audit_before["information_sets"],
                "public_decision_nodes": audit_before["public_decision_nodes"],
                "exact_audit": audit_before["exact"],
                "exact_vs_float_replay_differences": (
                    audit_before["exact_vs_float_replay_differences"]),
                "exact_vs_result_differences": audit_before["exact_vs_result_differences"],
                "nash_conv_target": float(TARGET_NASH_CONV),
                "numeric_target_met": audit_before["metrics"]["nash_conv"] <= float(TARGET_NASH_CONV),
                "target_met": audit_before["exact"].get("target_met"),
            })
            _write_atomic(
                attempts_dir / "run-status.json",
                _pretty_json_bytes(_status_payload(claim, "running", profiles)),
            )
        except Exception as exc:
            _record_failure(attempts_dir, claim, profiles, identity, exc)
            raise

    for profile in profiles:
        case = _case_by_id(profile["scenario"])
        try:
            before_reload = source_guard(expected_source_commit)
            _same_source_state(baseline, before_reload)
            _assert_source_state_valid(before_reload, expected_source_commit)
            path = attempts_dir / profile["policy_file"]
            raw_policy = path.read_bytes()
            if _sha256(raw_policy) != profile["policy_sha256"]:
                raise RuntimeError("Saved raw policy hash changed before reload replay")
            loaded = json.loads(raw_policy.decode("utf-8"))
            reload_audit = _audit_policy(loaded, case)
            _assert_same_audit({
                "metrics": profile["metrics"],
                "exact": profile["exact_audit"],
                "worlds": profile["worlds"],
                "compatible_pairs": profile["compatible_pairs"],
                "information_sets": profile["information_sets"],
                "public_decision_nodes": profile["public_decision_nodes"],
            }, {
                "metrics": reload_audit["metrics"],
                "exact": reload_audit["exact"],
                "worlds": reload_audit["worlds"],
                "compatible_pairs": reload_audit["compatible_pairs"],
                "information_sets": reload_audit["information_sets"],
                "public_decision_nodes": reload_audit["public_decision_nodes"],
            })
            after_reload = source_guard(expected_source_commit)
            _same_source_state(baseline, after_reload)
            _assert_source_state_valid(after_reload, expected_source_commit)
            profile["saved_reload_replay"] = "passed"
        except Exception as exc:
            _record_failure(attempts_dir, claim, profiles, profile, exc)
            raise

    try:
        final_state = source_guard(expected_source_commit)
        _same_source_state(baseline, final_state)
        _assert_source_state_valid(final_state, expected_source_commit)
    except Exception as exc:
        _record_failure(attempts_dir, claim, profiles, {"stage": "final-source-check"}, exc)
        raise
    report = {
        "schema_version": 1,
        "benchmark_id": BENCHMARK_ID,
        "claim_id": claim["claim_id"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_head": expected_source_commit,
        "source_sha256": baseline["files"],
        "fresh_preflight": preflight_receipt,
        "source_snapshot": baseline["files"],
        "fixed_grid": {
            "algorithm": ALGORITHM, "iterations": ITERATIONS,
            "threshold_nash_conv_fraction": str(TARGET_NASH_CONV),
            "threshold_is_reporting_only": True,
            "backends": list(BACKENDS),
        },
        "cases": [dict(case) for case in CASES],
        "preflight": profile_plan,
        "methodology": {
            "training": "Each frozen profile receives exactly one fixed 10,000-iteration CFR+ call; no target stop, retry, tuning, or case substitution.",
            "numeric_validation": "Each complete saved policy is replayed with the independent physical-world/rank/visible-information best-response validator; all eight metrics and independent counts are checked at 1e-9 absolute chips.",
            "exact_audit": "After numeric replay, scan and partition exact Fraction audits use explicitly normalized binary64 policy rows and unchanged 100,000 work / depth 64 / 65,536-bit limits. This audits the normalized policy, not raw floats as exact rationals.",
            "source_guards": "The explicit clean Git HEAD and source snapshot are checked before and after every call, every validation, and every saved-policy reload.",
            "timing": "Single complete-call plus canonical policy serialization host observations only; no speed or memory claim.",
            "quality": "The 1/1000-chip NashConv threshold is reporting-only. Every miss and every exact-admission rejection remains in this report and its raw policy directory.",
            "scope": "Two synthetic fixed-board finite river games with four weighted holdings per player. No unrestricted Hold'em, equilibrium-value, or commercial-solver claim.",
        },
        "runtime": {"python": sys.version, "platform": platform.platform()},
        "results": profiles,
    }
    try:
        _write_exclusive(attempts_dir / "report.json", _pretty_json_bytes(report))
        _write_atomic(
            attempts_dir / "run-status.json",
            _pretty_json_bytes(_status_payload(claim, "completed", profiles)),
        )
        _fsync_directory(attempts_dir)
    except Exception as exc:
        _record_failure(attempts_dir, claim, profiles, {"stage": "report-publication"}, exc)
        raise
    return report


def _assert_source_state_valid(state, expected_source_commit):
    if state.get("head") != expected_source_commit or state.get("status") != "clean":
        raise RuntimeError("Production checkout is not at the expected clean frozen source state")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts-dir", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    args = parser.parse_args(argv)
    try:
        report = run_batch(args.attempts_dir, args.expected_source_commit)
    except Exception as exc:
        print(f"Held-out batch stopped with durable failure evidence: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 2
    print(json.dumps({
        "benchmark_id": report["benchmark_id"],
        "claim_id": report["claim_id"],
        "profiles": len(report["results"]),
        "target_met": [row["target_met"] for row in report["results"]],
        "report": str((args.attempts_dir.resolve() / "report.json")),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
