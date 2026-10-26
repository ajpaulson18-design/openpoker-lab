"""One fixed three-hand TURN direct-tail experiment and read-only verifier."""
from __future__ import annotations

import argparse
import base64
import copy
import json
import math
import os
from pathlib import Path
from scripts.historical_foundation_sources import compatible_exact_source_maps, foundation_source_accepts, operation_fingerprints
import re
import subprocess
import sys
import time
import uuid
from fractions import Fraction

from scripts import benchmark_river_direct_tail as base
from scripts import turn_three_hand_reference as reference
from scripts import turn_three_hand_exact_oracle as exact_oracle
from scripts import turn_river_validation as validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "turn-three-hand-direct-tail-v1"
REPORT_NAME = "turn-three-hand-direct-tail-v1.json"
POLICY_NAME = "turn-three-hand-direct-tail-v1-policy.json"
ITERATIONS = 750
DISCARD = 250
AVERAGED_SWEEPS = 500
AVERAGE_WEIGHT_SUM = 250_250
REGRET_PASSES = 1_500
AVERAGE_PASSES = 500
TOTAL_PASSES = 2_000
WORLD_WORK = 28_512_000
DENSE_WORK = 20_540_601
TARGET = Fraction(1, 1000)
BYTE_CAP = 4_000_000
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_RE = re.compile(r"^[0-9a-f]{40}$")
METRICS = reference.METRICS
FIXTURE = copy.deepcopy(reference.FIXTURE)
REQUIRED_PRODUCER = {
    "pokerlab/turn_tail_adapter.py",
    "tests/test_turn_tail_adapter.py",
    "scripts/benchmark_turn_three_hand_tail.py",
    "tests/test_benchmark_turn_three_hand_tail.py",
    "tests/test_turn_three_hand_physical.py",
}
VERIFY_PATHS = tuple(sorted({
    "pokerlab/cards.py",
    "scripts/preflop_validation.py",
    "scripts/turn_river_validation.py",
    "scripts/turn_three_hand_reference.py",
    "scripts/turn_three_hand_exact_oracle.py",
    "scripts/benchmark_river_direct_tail.py",
    "scripts/benchmark_turn_three_hand_tail.py",
    "tests/test_turn_three_hand_physical.py",
    "tests/test_benchmark_turn_three_hand_tail.py",
    "tests/test_benchmark_turn_three_hand_tail_adversarial.py",
}))
HISTORICAL_PRODUCER_REQUIRED = set(REQUIRED_PRODUCER) | set(VERIFY_PATHS)
PROFILE_FIELDS = (
    "method", "algorithm", "solver_version", "strategy_schema", "backend",
    "execution_backend", "diagnostics_backend", "board", "config",
    "street_configs", "turn_config", "river_config", "runouts",
    "reachable_runouts", "runout_mode", "chance_note", "iterations",
    "requested_iterations", "discard", "source_iteration_window",
    "averaged_sweeps", "average_weight_sum", "average_schedule",
    "update_schedule", "requested_regret_passes", "requested_average_passes",
    "requested_total_traversal_passes", "deals", "compatible_pairs", "worlds",
    "worlds_materialized", "info_sets", "public_nodes", "public_states",
    "terminal_nodes", "chance_nodes", "world_traversal_nodes", "tree_actions",
    "public_state_limit", "public_node_limit", "public_batch_edge_limit",
    "resource_usage", "pot", "effective_stack", "training_calls",
)


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _targets(root=ROOT):
    folder = root / "benchmarks" / "results"
    return {"policy": folder / POLICY_NAME, "report": folder / REPORT_NAME}


def _source_paths(root, producer):
    names = {path.relative_to(root).as_posix()
             for path in (root / "pokerlab").glob("*.py")}
    names.update(REQUIRED_PRODUCER)
    names.update(VERIFY_PATHS)
    return tuple(sorted(names))


def _hash_paths(root, paths):
    result = {}
    for name in paths:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(path)
        raw = path.read_bytes()
        if path.suffix == ".py":
            raw = raw.replace(b"\r\n", b"\n")
        result[name] = base._sha(raw)
    return result


def _head(root):
    value = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if not GIT_RE.fullmatch(value):
        raise ValueError("Malformed current Git HEAD")
    return value


def _committed_map(root, head, mapping):
    for name, digest in mapping.items():
        committed = subprocess.check_output(["git", "show", f"{head}:{name}"], cwd=root)
        if name.endswith(".py"):
            committed = committed.replace(b"\r\n", b"\n")
        if base._sha(committed) != digest:
            raise RuntimeError(f"Source is not committed at frozen HEAD: {name}")


def _source_context(root):
    head = _head(root)
    producer = _hash_paths(root, _source_paths(root, True))
    verification = _hash_paths(root, VERIFY_PATHS)
    _committed_map(root, head, producer)
    _committed_map(root, head, verification)
    return head, producer, verification


def _verification_context(root):
    head = _head(root)
    verification = _hash_paths(root, VERIFY_PATHS)
    _committed_map(root, head, verification)
    return head, verification


def _guard_generation(root, head, producer, verification):
    if _head(root) != head:
        raise RuntimeError("Git HEAD changed during generation")
    if set(_source_paths(root, True)) != set(producer):
        raise RuntimeError("Producer source set changed during generation")
    if _hash_paths(root, _source_paths(root, True)) != producer:
        raise RuntimeError("Producer source bytes changed during generation")
    if _hash_paths(root, VERIFY_PATHS) != verification:
        raise RuntimeError("Verification source bytes changed during generation")


def _guard_replay(root, head, verification):
    if _head(root) != head:
        raise RuntimeError("Git HEAD changed during saved verification")
    if _hash_paths(root, VERIFY_PATHS) != verification:
        raise RuntimeError("Verification source bytes changed during saved verification")
    _committed_map(root, head, verification)


def _validate_historical_map(value, required, *, producer=False):
    if type(value) is not dict or not required.issubset(value):
        raise ValueError("Historical source map omits required paths")
    if not producer and set(value) != set(required):
        raise ValueError("Historical verification map path set differs")
    for name, digest in value.items():
        allowed = bool(re.fullmatch(r"pokerlab/[A-Za-z_][A-Za-z_0-9]*\.py", name)) if type(name) is str else False
        allowed = allowed or name in required
        if not allowed or type(digest) is not str or not SHA_RE.fullmatch(digest):
            raise ValueError("Malformed historical source fingerprint")


def _config_dict():
    return {"pot": 100.0, "effective_stack": 220.0, "bet_sizes": [0.5],
            "raise_sizes": [0.5], "max_raises": 1, "include_all_in": False}


def _expected_resources():
    return {
        "full_requested_world_node_work": WORLD_WORK,
        "full_requested_world_node_work_limit": 30_000_000,
        "full_requested_dense_hand_state_pass_work": DENSE_WORK,
        "full_requested_dense_hand_state_pass_work_limit": 30_000_000,
        "info_action_slots": 8_046,
        "info_action_slots_limit": 1_000_000,
        "prefix_hand_edges": 405,
        "prefix_hand_edge_limit": 250_000,
    }


def _expected_metadata():
    config = _config_dict()
    board = list(reference.rules.cards(FIXTURE["board"]))
    runouts = [card for card in reference.rules.DECK if card not in board]
    return {
        "method": "Direct original-weight CFR+ tail averaging",
        "algorithm": "cfrplus", "solver_version": "research-turn-tail-adapter-v1",
        "strategy_schema": "postflop-strategy-v1", "backend": "exact-public-chance-tree",
        "execution_backend": "direct-original-weight-tail-python",
        "diagnostics_backend": "public-batched-python", "board": board,
        "config": config, "street_configs": {"turn": config, "river": config},
        "turn_config": config, "river_config": config, "runouts": runouts,
        "reachable_runouts": list(runouts), "runout_mode": "full-deck",
        "chance_note": "Joint private-pair/river physical worlds normalized once; selected river outcomes condition the joint mass.",
        "iterations": ITERATIONS, "requested_iterations": ITERATIONS,
        "discard": DISCARD, "source_iteration_window": [251, 750],
        "averaged_sweeps": AVERAGED_SWEEPS, "average_weight_sum": AVERAGE_WEIGHT_SUM,
        "average_schedule": "direct-original-linear-sweep-weight-own-reach-tail",
        "update_schedule": "alternating-oop-then-ip",
        "requested_regret_passes": REGRET_PASSES,
        "requested_average_passes": AVERAGE_PASSES,
        "requested_total_traversal_passes": TOTAL_PASSES,
        "deals": 9, "compatible_pairs": 9,
        "worlds": 396,
        "worlds_materialized": 396, "info_sets": 3_606, "public_nodes": 1_254,
        "public_states": 3_039, "terminal_nodes": 1_780, "chance_nodes": 5,
        "world_traversal_nodes": 32, "tree_actions": 2_798,
        "public_state_limit": 250_000, "public_node_limit": 10_000,
        "public_batch_edge_limit": 250_000, "resource_usage": _expected_resources(),
        "pot": 100.0, "effective_stack": 220.0, "training_calls": 1,
    }


def _validate_profile_metadata(payload):
    if type(payload) is not dict:
        raise ValueError("Returned policy must be a dictionary")
    expected = _expected_metadata()
    if set(payload) != set(PROFILE_FIELDS) | set(METRICS) | {"scope", "diagnostic_provenance", "strategy"}:
        raise ValueError("Returned policy complete field set differs")
    for key, value in expected.items():
        if key not in payload or type(payload[key]) is not type(value) \
                or _canonical(payload[key]) != _canonical(value):
            raise ValueError(f"Returned policy metadata differs: {key}")
    _need(type(payload["strategy"]) is list and len(payload["strategy"]) == 3_606,
          "Returned policy row count differs")
    _need(payload["scope"] == "Research profile for a configured heads-up turn/river game; no preflop, multiway play, rake, or general exact-equilibrium claim.",
          "Returned policy scope differs from the API literal")
    _need(payload["diagnostic_provenance"] == "Metrics recomputed from the direct original-weight tail policy using public-batched diagnostics; numeric convergence diagnostics are not an exact equilibrium certificate.",
          "Returned diagnostic provenance differs from the API literal")
    for key in METRICS:
        value = payload[key]
        if type(value) not in (float, int) or not math.isfinite(value):
            raise ValueError(f"Returned diagnostic {key} is not finite numeric data")
    return {key: payload[key] for key in PROFILE_FIELDS}


def _control(root, guard=None):
    checkpoint = guard or (lambda: None)
    game = reference.model()
    checkpoint()
    reference.validate_model(game)
    checkpoint()
    policy = reference.make_check_call_policy(game)
    exact = exact_oracle.audit_policy(policy, game)
    checkpoint()
    numeric = validator.replay_policy(policy, FIXTURE["oop"], FIXTURE["ip"],
                                      board=FIXTURE["board"], config=FIXTURE["config"])
    _compare_exact_numeric(exact["metrics"], numeric)
    expected = {
        "value_oop": Fraction(-9_500, 891), "value_ip": Fraction(9_500, 891),
        "oop_best_response_value": Fraction(6_925, 891),
        "ip_best_response_value": Fraction(57_550, 891),
        "oop_best_response_gain": Fraction(16_425, 891),
        "ip_best_response_gain": Fraction(48_050, 891),
        "nash_conv": Fraction(64_475, 891),
        "exploitability": Fraction(64_475, 1_782),
    }
    _need(exact["metrics"] == expected, "Pretraining check/call anchor differs")
    checkpoint()
    return {"metrics_fractions": {key: str(value) for key, value in exact["metrics"].items()},
            "counters": exact["counters"], "training_calls": 0}


def _compare_exact_numeric(exact, numeric):
    _need(type(exact) is dict and set(exact) == set(METRICS)
          and all(type(exact[key]) is Fraction for key in METRICS),
          "Exact replay must supply all eight rational metrics")
    deltas = {key: float(exact[key]) - float(numeric[key]) for key in METRICS}
    if any(not math.isfinite(value) or abs(value) > 1e-9 for value in deltas.values()):
        raise ValueError("Exact replay differs from independent numeric replay")
    if exact["oop_best_response_gain"] < 0 or exact["ip_best_response_gain"] < 0:
        raise ValueError("Exact best-response gains must be nonnegative")
    _need(exact["value_oop"] + exact["value_ip"] == 0,
          "Exact zero-sum metric identity differs")
    _need(exact["nash_conv"] == exact["oop_best_response_gain"] + exact["ip_best_response_gain"],
          "Exact NashConv metric identity differs")
    _need(exact["oop_best_response_gain"] == exact["oop_best_response_value"] - exact["value_oop"]
          and exact["ip_best_response_gain"] == exact["ip_best_response_value"] - exact["value_ip"],
          "Exact best-response gain identities differ")
    _need(exact["exploitability"] * 2 == exact["nash_conv"],
          "Exact half-gap exploitability identity differs")
    return deltas


def _audit(payload, *, guard=None):
    checkpoint = guard or (lambda: None)
    metadata = _validate_profile_metadata(payload)
    checkpoint()
    numeric = validator.replay_policy(payload, FIXTURE["oop"], FIXTURE["ip"],
                                      board=FIXTURE["board"], config=FIXTURE["config"])
    numeric_deltas = validator.compare_result(payload, numeric, tolerance=1e-9)
    if any(not math.isfinite(value) or abs(value) > 1e-9 for value in numeric_deltas.values()):
        raise ValueError("Independent numeric replay differs from API diagnostics")
    checkpoint()
    game = reference.model()
    reference.validate_model(game)
    checkpoint()
    exact = exact_oracle.audit_policy(payload, game)
    checkpoint()
    exact_numeric_deltas = _compare_exact_numeric(exact["metrics"], numeric)
    gains = (exact["metrics"]["oop_best_response_gain"],
             exact["metrics"]["ip_best_response_gain"])
    lower = -exact["metrics"]["ip_best_response_value"]
    upper = exact["metrics"]["oop_best_response_value"]
    profile = exact["metrics"]["value_oop"]
    if not lower <= profile <= upper:
        raise ValueError("Profile value falls outside legal response interval")
    checkpoint()
    return {
        "policy_metadata": metadata,
        "api_numeric_replay_deltas": numeric_deltas,
        "exact_numeric_replay_deltas": exact_numeric_deltas,
        "exact_metrics_fractions": {key: str(exact["metrics"][key]) for key in METRICS},
        "exact_counters": exact["counters"],
        "target_nash_conv_fraction": str(TARGET),
        "exact_threshold_met": exact["metrics"]["nash_conv"] <= TARGET,
        "exact_nash_conv_zero": exact["metrics"]["nash_conv"] == 0,
        "oop_response_gain_fraction": str(gains[0]),
        "ip_response_gain_fraction": str(gains[1]),
        "legal_response_interval_fraction": [str(lower), str(upper)],
        "profile_value_fraction": str(profile),
        "profile_strictly_inside_response_interval": lower < profile < upper,
    }


def _canonical(payload):
    return base._canonical(payload)


def _safe_repr(value):
    try:
        return repr(value)
    except BaseException as error:
        return f"<repr failed: {type(error).__name__}: {error}>"


def _preserve_rejected(root, payload, raw, head, producer, verification, elapsed,
                       call_completed, error):
    folder = root / "work" / "turn_three_hand_tail_rejected"
    folder.mkdir(parents=True, exist_ok=True)
    elapsed_ok = (type(elapsed) in (float, int) and math.isfinite(elapsed) and elapsed >= 0)
    record = {
        "scope": "Rejected returned policy preservation; not accepted benchmark evidence",
        "schema": SCHEMA, "generation_head": head,
        "historical_producer_source_sha256": producer,
        "verification_source_sha256": verification,
        "iterations": ITERATIONS, "discard": DISCARD,
        "call_completed": bool(call_completed),
        "actual_complete_call_seconds": elapsed if elapsed_ok else None,
        "invalid_elapsed_repr": None if elapsed_ok else _safe_repr(elapsed),
        "rejection": _safe_repr(error),
        "raw_policy_sha256": base._sha(raw) if type(raw) is bytes else None,
        "raw_policy_base64": base64.b64encode(raw).decode("ascii") if type(raw) is bytes else None,
        "unserialized_returned_policy_repr": None if type(raw) is bytes else _safe_repr(payload),
    }
    try:
        encoded = _canonical(record)
    except BaseException:
        encoded = (json.dumps(record, indent=2, sort_keys=True, allow_nan=True,
                              default=_safe_repr) + "\n").encode("utf-8")
    target = folder / f"rejected-{uuid.uuid4().hex}.json"
    with target.open("xb") as stream:
        identity = os.fstat(stream.fileno())
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return target


def _validate_report(report, root):
    if type(report) is not dict or report.get("schema") != SCHEMA:
        raise ValueError("Unexpected saved report schema")
    if type(report.get("schema_version")) is not int or report["schema_version"] != 1:
        raise ValueError("Invalid saved schema version")
    head = report.get("generation_head")
    if type(head) is not str or not GIT_RE.fullmatch(head):
        raise ValueError("Invalid historical producer commit")
    _validate_historical_map(report.get("historical_producer_source_sha256"),
                             HISTORICAL_PRODUCER_REQUIRED, producer=True)
    _validate_historical_map(report.get("verification_source_sha256"), set(VERIFY_PATHS))
    for path, digest in report["verification_source_sha256"].items():
        _need(report["historical_producer_source_sha256"].get(path) == digest,
              "Historical producer and verification source identities disagree")
    elapsed = report.get("actual_complete_call_seconds")
    if type(elapsed) not in (float, int) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("Saved complete-call timing must be finite and nonnegative")
    return elapsed


def _build_report(head, producer, verification, payload, audit, elapsed, policy_raw, control):
    if type(elapsed) not in (float, int) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("Complete-call timing must be finite, nonnegative, nonbool numeric data")
    if type(policy_raw) is not bytes or len(policy_raw) > BYTE_CAP:
        raise ValueError("Policy bytes exceed fixed four-megabyte cap")
    return {
        "schema": SCHEMA, "schema_version": 1, "generation_head": head,
        "historical_producer_source_sha256": producer,
        "verification_source_sha256": verification,
        "fixture_id": FIXTURE["id"], "fixture": FIXTURE,
        "iterations": ITERATIONS, "discard": DISCARD,
        "averaged_sweeps": AVERAGED_SWEEPS,
        "average_weight_sum": AVERAGE_WEIGHT_SUM,
        "requested_regret_passes": REGRET_PASSES,
        "requested_average_passes": AVERAGE_PASSES,
        "requested_total_traversal_passes": TOTAL_PASSES,
        "full_requested_world_node_work": WORLD_WORK,
        "full_requested_world_node_work_limit": 30_000_000,
        "full_requested_dense_hand_state_pass_work": DENSE_WORK,
        "full_requested_dense_hand_state_pass_work_limit": 30_000_000,
        "info_action_slots": 8_046, "info_action_slots_limit": 1_000_000,
        "prefix_hand_edges": 405, "prefix_hand_edge_limit": 250_000,
        "actual_complete_call_seconds": elapsed,
        "timing_scope": "Lazy import, immediate frozen-source guard and complete API call; independent mathematical audits are excluded.",
        "completed_training_calls": 1,
        "control_before_training": control,
        "policy_file": POLICY_NAME, "policy_sha256": base._sha(policy_raw),
        "policy_metadata": audit["policy_metadata"],
        "results": audit,
        "scope": "One fixed 396-world configured three-hand TURN CFR+ direct-tail profile. Exact evidence applies to exact row-normalized binary64 probabilities for this serialized policy; it does not establish a known equilibrium value or general convergence.",
    }


def _verify_bundle(report_raw, policy_raw, *, root, head, verification, bundle_guard=None):
    operation_before = operation_fingerprints(())
    if type(report_raw) is not bytes or type(policy_raw) is not bytes:
        raise ValueError("Saved report/policy must be bytes")
    if len(report_raw) > BYTE_CAP or len(policy_raw) > BYTE_CAP:
        raise ValueError("Saved report or policy exceeds fixed byte cap")
    report, payload = json.loads(report_raw), json.loads(policy_raw)
    if type(report) is not dict or type(payload) is not dict:
        raise ValueError("Saved report/policy must be JSON objects")
    if _canonical(report) != report_raw or _canonical(payload) != policy_raw:
        raise ValueError("Saved files must be canonical LF JSON")
    elapsed = _validate_report(report, root)
    if report["fixture"] != FIXTURE or report["fixture_id"] != FIXTURE["id"]:
        raise ValueError("Saved report fixed fixture differs")
    if report["iterations"] != ITERATIONS or report["discard"] != DISCARD:
        raise ValueError("Saved report requested schedule differs")
    if report["policy_sha256"] != base._sha(policy_raw):
        raise ValueError("Saved policy hash differs")
    if not compatible_exact_source_maps(report.get("verification_source_sha256"), verification, root):
        raise ValueError("Saved verification source map differs from current committed math")
    if bundle_guard:
        bundle_guard()
    control = _control(root, guard=bundle_guard)
    audit = _audit(payload, guard=bundle_guard)
    saved_results = report.get("results")
    if type(saved_results) is not dict:
        raise ValueError("Saved report results must be an object")
    for name in ("api_numeric_replay_deltas", "exact_numeric_replay_deltas"):
        saved = saved_results.get(name)
        observed = audit[name]
        if type(saved) is not dict or set(saved) != set(METRICS):
            raise ValueError("Saved numeric replay deltas have an invalid field set")
        for metric in METRICS:
            value = saved[metric]
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Saved numeric replay delta is not finite numeric data")
            if abs(value) > 1e-9 or abs(float(value) - float(observed[metric])) > 1e-9:
                raise ValueError("Saved numeric replay observation exceeds fixed tolerance")
        audit[name] = saved
    expected = _build_report(report["generation_head"],
                             report["historical_producer_source_sha256"],
                             report["verification_source_sha256"], payload,
                             audit, elapsed, policy_raw, control)
    if _canonical(expected) != report_raw:
        raise ValueError("Saved report differs from complete independent reconstruction")
    if bundle_guard:
        bundle_guard()
    if operation_fingerprints(()) != operation_before:
        raise RuntimeError("Bridge source changed during saved verification")
    return expected


def _read_bounded(path):
    size = path.stat().st_size
    if size < 0 or size > BYTE_CAP:
        raise ValueError("File exceeds four-megabyte byte cap")
    with path.open("rb") as stream:
        raw = stream.read(BYTE_CAP + 1)
    if len(raw) != size or len(raw) > BYTE_CAP:
        raise ValueError("File changed while reading or exceeded byte cap")
    return raw


def _bundle_guard(targets, owned, report_raw, policy_raw):
    expected = {"report": report_raw, "policy": policy_raw}
    for key, path in targets.items():
        if not path.exists() or base._bundle_identity(path) != owned[path]:
            raise RuntimeError("Bundle inode disappeared or changed")
        if _read_bounded(path) != expected[key]:
            raise RuntimeError("Bundle bytes changed")


def _publish(report_raw, policy_raw, *, root, head, producer, verification):
    if type(report_raw) is not bytes or type(policy_raw) is not bytes:
        raise ValueError("Publication inputs must be bytes")
    if len(report_raw) > BYTE_CAP or len(policy_raw) > BYTE_CAP:
        raise ValueError("Publication inputs exceed fixed byte cap")
    targets = _targets(root)
    existing = [str(path) for path in targets.values() if path.exists()]
    if existing:
        raise FileExistsError("Refusing to overwrite fixed target(s): " + ", ".join(existing))
    stages, owned = {}, {}
    try:
        for key, raw in (("policy", policy_raw), ("report", report_raw)):
            path = targets[key]
            stage = path.with_name(f".{path.name}.{uuid.uuid4().hex}.stage")
            stages[key] = stage
            base._owned_write(stage, raw, owned)

        def stage_guard():
            _guard_generation(root, head, producer, verification)
            _bundle_guard(stages, owned, report_raw, policy_raw)

        stage_guard()
        staged_report, staged_policy = _read_bounded(stages["report"]), _read_bounded(stages["policy"])
        if staged_report != report_raw or staged_policy != policy_raw:
            raise RuntimeError("Stage bytes differ from original validated bytes")
        _verify_bundle(staged_report, staged_policy, root=root, head=head,
                       verification=verification, bundle_guard=stage_guard)
        stage_guard()
        if any(path.exists() for path in targets.values()):
            raise FileExistsError("Fixed target appeared during staging")
        base._publish_staged(stages, targets, owned)

        def published_guard():
            _guard_generation(root, head, producer, verification)
            _bundle_guard(targets, owned, report_raw, policy_raw)

        published_guard()
        final_report, final_policy = _read_bounded(targets["report"]), _read_bounded(targets["policy"])
        _verify_bundle(final_report, final_policy, root=root, head=head,
                       verification=verification, bundle_guard=published_guard)
        _guard_generation(root, head, producer, verification)
        _bundle_guard(targets, owned, report_raw, policy_raw)
    except BaseException:
        base._rollback_owned(owned)
        raise
    finally:
        base._rollback_owned({path: owned[path] for path in stages.values() if path in owned})


def generate(root=ROOT):
    targets = _targets(root)
    if any(path.exists() for path in targets.values()):
        raise FileExistsError("Refusing to overwrite fixed experiment target")
    head, producer, verification = _source_context(root)
    guard = lambda: _guard_generation(root, head, producer, verification)
    guard()
    control = _control(root, guard=guard)
    guard()
    payload = None
    policy_raw = None
    call_completed = False
    elapsed = None
    try:
        print(f"START fixture={FIXTURE['id']} iterations={ITERATIONS} discard={DISCARD}", flush=True)
        start = time.perf_counter()
        from pokerlab.turn_tail_adapter import solve_turn_tail
        guard()
        payload = solve_turn_tail(FIXTURE["board"], FIXTURE["oop"], FIXTURE["ip"],
                                  FIXTURE["config"], iterations=ITERATIONS,
                                  discard=DISCARD)
        call_completed = True
        elapsed = time.perf_counter() - start
        guard()
        _validate_profile_metadata(payload)
        policy_raw = _canonical(payload)
        if len(policy_raw) > BYTE_CAP:
            raise ValueError("Returned raw policy exceeds fixed four-megabyte cap")
        guard()
        audit = _audit(payload, guard=guard)
        guard()
        report = _build_report(head, producer, verification, payload, audit,
                               elapsed, policy_raw, control)
        report_raw = _canonical(report)
        if len(report_raw) > BYTE_CAP:
            raise ValueError("Report exceeds fixed four-megabyte cap")
        _publish(report_raw, policy_raw, root=root, head=head,
                 producer=producer, verification=verification)
        print(f"DONE fixture={FIXTURE['id']} nash_conv={audit['exact_metrics_fractions']['nash_conv']} target_met={audit['exact_threshold_met']}", flush=True)
        return report
    except BaseException as error:
        if call_completed:
            try:
                if policy_raw is None:
                    try:
                        policy_raw = _canonical(payload)
                    except BaseException:
                        policy_raw = None
                _preserve_rejected(root, payload, policy_raw, head, producer,
                                   verification, elapsed, call_completed, error)
            except BaseException as preserve_error:
                print(f"Could not preserve rejected policy: {_safe_repr(preserve_error)}", file=sys.stderr)
        raise


def verify(root=ROOT):
    head, verification = _verification_context(root)
    guard = lambda: _guard_replay(root, head, verification)
    guard()
    targets = _targets(root)
    owned = {path: base._bundle_identity(path) for path in targets.values()}
    report_raw, policy_raw = _read_bounded(targets["report"]), _read_bounded(targets["policy"])

    def final_guard():
        _guard_replay(root, head, verification)
        _bundle_guard(targets, owned, report_raw, policy_raw)

    final_guard()
    return _verify_bundle(report_raw, policy_raw, root=root, head=head,
                          verification=verification, bundle_guard=final_guard)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true")
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    report = generate() if args.generate else verify()
    result = report["results"]
    print(f"VERIFIED fixture={FIXTURE['id']} iterations={ITERATIONS} discard={DISCARD} "
          f"nash_conv={result['exact_metrics_fractions']['nash_conv']} "
          f"target_met={result['exact_threshold_met']}")


if __name__ == "__main__":
    main()
