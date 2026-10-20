"""One fixed 100k direct-tail river experiment; verification never trains."""
from __future__ import annotations

import argparse
import base64
import copy
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import uuid
from fractions import Fraction

from scripts import benchmark_river_direct_tail as base

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks" / "results"
REPORT_NAME = "river-direct-long-tail-v1.json"
POLICY_NAME = "river-direct-long-tail-v1-polarised.json"
SCHEMA = "river-direct-long-tail-v1"
FIXTURE_ID = "river-polarised-bluffcatcher"
ITERATIONS = 100_000
DISCARD = 3_000
V1_VERSION = "research-river-tail-adapter-v1"
LONG_VERSION = "research-river-long-tail-adapter-v1"
TARGET = Fraction(1, 1000)
REPORT_CAP = 4_000_000
POLICY_CAP = 2_000_000
INPUT_REPORT_SHA256 = "68a0fe3ff150c37c47784cc22cfe928f19974f27208ee16dee61c53ee81a35a5"
INPUT_POLICY_SHA256 = "2f558f363f716c0dc67794d329d167254b7b65bcf339cd8480d61e7e8fe53117"
GIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
METRICS = (
    "value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value",
    "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability",
)
FIXTURE = base.FIXTURES[FIXTURE_ID]
PRODUCER_REQUIRED = {
    "pokerlab/river_tail_adapter.py", "tests/test_river_tail_adapter.py",
    "scripts/benchmark_river_direct_long_tail.py",
    "tests/test_benchmark_river_direct_long_tail.py",
    "tests/reference_river_tail_v1.py",
}
VERIFY_PATHS = tuple(sorted(set(base.VERIFY_PATHS) | {
    "scripts/benchmark_river_direct_long_tail.py",
    "tests/test_benchmark_river_direct_long_tail.py",
}))


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _targets(root=ROOT):
    folder = root / "benchmarks" / "results"
    return {"report": folder / REPORT_NAME, "policy": folder / POLICY_NAME}


def _input_paths(root):
    folder = root / "benchmarks" / "results"
    return {"report": folder / "river-direct-tail-v1.json",
            "policy": folder / "river-direct-tail-v1-polarised.json"}


def _read_inputs(root):
    paths = _input_paths(root)
    report_raw = base._read_bounded(paths["report"], REPORT_CAP)
    policy_raw = base._read_bounded(paths["policy"], POLICY_CAP)
    if base._sha(report_raw) != INPUT_REPORT_SHA256:
        raise ValueError("Pinned accepted direct-tail report bytes changed")
    if base._sha(policy_raw) != INPUT_POLICY_SHA256:
        raise ValueError("Pinned accepted direct-tail policy bytes changed")
    report = json.loads(report_raw)
    policy = json.loads(policy_raw)
    if type(report) is not dict or report.get("benchmark_id") != "river-direct-tail-v1":
        raise ValueError("Unexpected accepted direct-tail report identity")
    if type(report.get("schema_version")) is not int or report["schema_version"] != 1:
        raise ValueError("Unexpected accepted report schema version")
    if report.get("fixtures", {}).get(FIXTURE_ID) != FIXTURE:
        raise ValueError("Accepted direct-tail fixture differs from fixed game")
    if (report.get("iterations") != 10_000 or report.get("discard") != 3_000
            or report.get("completed_training_calls") != 2):
        raise ValueError("Accepted direct-tail schedule differs from pinned v1")
    if report.get("policy_sha256", {}).get(FIXTURE_ID) != INPUT_POLICY_SHA256:
        raise ValueError("Accepted report does not bind the pinned policy bytes")
    if (policy.get("solver_version") != V1_VERSION
            or policy.get("iterations") != 10_000 or policy.get("discard") != 3_000
            or policy.get("board") != list(base._cards(FIXTURE_ID))
            or policy.get("config") != base._config_dict(FIXTURE_ID)):
        raise ValueError("Accepted v1 policy metadata differs from fixed input")
    row = report.get("results", {}).get(FIXTURE_ID)
    if type(row) is not dict or type(row.get("exact_metrics_fractions")) is not dict:
        raise ValueError("Accepted report lacks exact policy metrics")
    return {
        "report_path": paths["report"], "policy_path": paths["policy"],
        "report_raw": report_raw, "policy_raw": policy_raw,
        "report_sha256": INPUT_REPORT_SHA256, "policy_sha256": INPUT_POLICY_SHA256,
        "report": report, "policy": policy,
        "accepted_exact_metrics": row["exact_metrics_fractions"],
    }


def _guard_inputs(root, inputs):
    current = _read_inputs(root)
    for key in ("report_raw", "policy_raw"):
        if current[key] != inputs[key]:
            raise RuntimeError(f"Pinned accepted {key} changed during operation")


def _expected_profile(payload, template, iterations, discard):
    if type(iterations) is not int or type(discard) is not int:
        raise ValueError("Iteration metadata must use exact integers")
    if not 0 <= discard < iterations:
        raise ValueError("Invalid fixed tail schedule")
    expected = copy.deepcopy(template)
    worlds = expected["worlds"]
    nodes = expected["world_traversal_nodes"]
    states = expected["public_states"]
    max_hands = 2
    expected["solver_version"] = V1_VERSION if iterations <= 10_000 else LONG_VERSION
    expected.update({
        "iterations": iterations,
        "requested_iterations": iterations,
        "discard": discard,
        "source_iteration_window": [discard + 1, iterations],
        "averaged_sweeps": iterations - discard,
        "average_weight_sum": iterations * (iterations + 1) // 2 - discard * (discard + 1) // 2,
        "requested_regret_passes": 2 * iterations,
        "requested_average_passes": iterations - discard,
        "requested_total_traversal_passes": 3 * iterations - discard,
    })
    resources = expected["resource_usage"]
    resources["full_requested_world_node_work"] = worlds * nodes * iterations * 3
    resources["full_requested_dense_hand_state_pass_work"] = max_hands * states * (3 * iterations + 3)
    # Policy metrics and strategy rows are observations, checked independently below.
    for key in (*METRICS, "strategy"):
        expected[key] = payload.get(key)
    return expected


def _validate_profile_metadata(payload, template, iterations=ITERATIONS, discard=DISCARD):
    if type(payload) is not dict:
        raise ValueError("Policy payload must be a dictionary")
    expected = _expected_profile(payload, template, iterations, discard)
    if base._canonical(payload) != base._canonical(expected):
        raise ValueError("Long-tail policy metadata or complete field set mismatch")
    if type(payload.get("strategy")) is not list or len(payload["strategy"]) != template["info_sets"]:
        raise ValueError("Long-tail policy has incomplete strategy rows")
    for name in METRICS:
        value = payload.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Policy metric {name} is not finite numeric data")


def _audit_math(payload, inputs, *, iterations=ITERATIONS, discard=DISCARD, guard=None):
    from scripts import turn_river_validation as validator
    from scripts.turn_rational_certificate import (
        MAX_EXACT_DEPTH, MAX_EXACT_WORK, MAX_FRACTION_BITS, evaluate_exact,
    )

    checkpoint = guard or (lambda: None)
    template = inputs["policy"]
    checkpoint()
    _validate_profile_metadata(payload, template, iterations, discard)
    checkpoint()
    numeric = validator.replay_policy(payload, FIXTURE["oop"], FIXTURE["ip"],
                                      board=FIXTURE["board"], config=FIXTURE["config"])
    deltas = validator.compare_result(payload, numeric, tolerance=1e-9)
    if any(not math.isfinite(delta) or abs(delta) > 1e-9 for delta in deltas.values()):
        raise ValueError("Independent numeric replay differs from saved policy")
    checkpoint()
    model = base._independent_model(payload, FIXTURE_ID)
    _board, config, worlds, game_root, _nodes, policies = model
    checkpoint()
    exact = evaluate_exact(game_root, worlds, policies, config.pot, result=payload,
                           max_work=100_000, max_depth=64, max_bits=65_536)
    checkpoint()
    if (exact["work_limit"], exact["depth_limit"], exact["fraction_bit_limit"]) != (
            MAX_EXACT_WORK, MAX_EXACT_DEPTH, MAX_FRACTION_BITS):
        raise RuntimeError("Exact auditor limits changed")
    metrics = exact["metrics"]
    lower, upper = base._assert_exact_identities(metrics)
    exact_numeric_deltas = {key: float(metrics[key]) - float(numeric[key]) for key in METRICS}
    if any(abs(value) > 1e-9 for value in exact_numeric_deltas.values()):
        raise ValueError("Exact and numeric replay differ")
    known = Fraction(25)
    if not lower <= known <= upper:
        raise ValueError("Known 25-chip value falls outside exact response interval")
    from scripts.replay_river_accuracy_extension import rational_polarised
    witness = rational_polarised(payload, FIXTURE)
    witness_value = Fraction(witness["value_oop_fraction"])
    witness_oop = Fraction(witness["oop_br_fraction"])
    witness_ip = Fraction(witness["ip_br_fraction"])
    witness_metrics = {
        "value_oop": witness_value, "value_ip": -witness_value,
        "oop_best_response_value": witness_oop, "ip_best_response_value": witness_ip,
        "oop_best_response_gain": witness_oop - witness_value,
        "ip_best_response_gain": witness_value + witness_ip,
        "nash_conv": witness_oop + witness_ip,
        "exploitability": (witness_oop + witness_ip) / 2,
    }
    if witness_metrics != metrics:
        raise ValueError("Independent 16/4 exact-history oracle differs on exact metrics")
    checkpoint()
    old_exact = inputs["accepted_exact_metrics"]
    if iterations == 10_000 and discard == 3_000:
        if {key: str(metrics[key]) for key in METRICS} != {key: old_exact[key] for key in METRICS}:
            raise ValueError("Accepted v1 policy exact metrics differ from its report")
    return {
        "numeric_replay_deltas": deltas,
        "exact_numeric_replay_deltas": exact_numeric_deltas,
        "exact_metrics_fractions": {key: str(metrics[key]) for key in METRICS},
        "exact_threshold_fraction": str(TARGET),
        "exact_threshold_met": metrics["nash_conv"] <= TARGET,
        "exact_nash_conv_zero": metrics["nash_conv"] == 0,
        "known_value_fraction": str(known),
        "known_value_in_response_interval": True,
        "lower_value_bound_fraction": str(lower),
        "upper_value_bound_fraction": str(upper),
        "exact_certificate": base._jsonable({
            "work": exact["work"], "work_by_kind": exact["work_by_kind"],
            "tree_nodes": exact["tree_nodes"], "tree_depth": exact["tree_depth"],
            "worlds": exact["worlds"], "maximum_fraction_bits": exact["maximum_fraction_bits"],
            "work_limit": exact["work_limit"], "depth_limit": exact["depth_limit"],
            "fraction_bit_limit": exact["fraction_bit_limit"],
            "max_row_adjustment": exact["max_row_adjustment"],
            "normalization_ledger": exact["normalization_ledger"],
        }),
        "polarized_16x4_witness": witness,
    }


def _read_source_map(root, paths):
    return {name: base._sha(base._py_source_bytes(root / name)) for name in paths}


def _producer_paths(root):
    names = {path.relative_to(root).as_posix() for path in (root / "pokerlab").glob("*.py")}
    names.update(PRODUCER_REQUIRED)
    return tuple(sorted(names))


def _verification_hashes(root):
    return _read_source_map(root, VERIFY_PATHS)


def _source_context(root):
    head = base._head(root)
    producer = _read_source_map(root, _producer_paths(root))
    verification = _verification_hashes(root)
    base._require_committed(root, producer, head=head)
    base._require_committed(root, verification, head=head)
    return head, producer, verification


def _verification_context(root):
    """Current committed math context; saved replay does not pin producers."""
    head = base._head(root)
    verification = _verification_hashes(root)
    base._require_committed(root, verification, head=head)
    return head, verification


def _guard_generation(root, head, producer, verification, inputs):
    if base._head(root) != head:
        raise RuntimeError("Git HEAD changed during generation")
    if set(_producer_paths(root)) != set(producer) or _read_source_map(root, producer) != producer:
        raise RuntimeError("Producer source bytes changed during generation")
    if _verification_hashes(root) != verification:
        raise RuntimeError("Verification source bytes changed during generation")
    _guard_inputs(root, inputs)


def _guard_replay(root, head, verification, inputs):
    if base._head(root) != head:
        raise RuntimeError("Git HEAD changed during saved verification")
    if _verification_hashes(root) != verification:
        raise RuntimeError("Committed verification source bytes changed during saved verification")
    base._require_committed(root, verification, head=head)
    _guard_inputs(root, inputs)


def _validate_historical_map(value, required, *, producer=False):
    if type(value) is not dict or not required.issubset(value):
        raise ValueError("Historical source map is missing required source paths")
    for name, digest in value.items():
        parts = name.split("/") if isinstance(name, str) else []
        allowed = (isinstance(name, str)
                   and re.fullmatch(r"pokerlab/[A-Za-z_][A-Za-z_0-9]*\.py", name) is not None)
        allowed |= name in required
        if (not allowed or ".." in parts or not isinstance(digest, str)
                or not SHA_RE.fullmatch(digest)):
            raise ValueError("Malformed historical source map")
    if not producer and set(value) != set(required):
        raise ValueError("Historical verification source map path set mismatch")


def _metadata_snapshot(payload):
    keys = ("solver_version", "iterations", "requested_iterations", "discard",
            "source_iteration_window", "averaged_sweeps", "average_weight_sum",
            "requested_regret_passes", "requested_average_passes",
            "requested_total_traversal_passes", "worlds", "compatible_pairs",
            "info_sets", "public_nodes", "public_states", "world_traversal_nodes",
            "tree_actions", "resource_usage")
    return {key: payload[key] for key in keys}


def _build_report(head, producer, verification, inputs, payload, audit, elapsed, policy_raw):
    if (isinstance(elapsed, bool) or not isinstance(elapsed, (int, float))
            or not math.isfinite(elapsed) or elapsed < 0):
        raise ValueError("Complete-call timing must be finite nonnegative numeric data")
    if type(policy_raw) is not bytes or len(policy_raw) > POLICY_CAP:
        raise ValueError("Policy bytes are invalid or exceed the fixed byte cap")
    old = inputs["accepted_exact_metrics"]
    new = audit["exact_metrics_fractions"]
    observed = {
        "old_value_oop_fraction": old["value_oop"],
        "new_value_oop_fraction": new["value_oop"],
        "value_oop_delta_fraction": str(Fraction(new["value_oop"]) - Fraction(old["value_oop"])),
        "old_oop_gain_fraction": old["oop_best_response_gain"],
        "new_oop_gain_fraction": new["oop_best_response_gain"],
        "oop_gain_delta_fraction": str(Fraction(new["oop_best_response_gain"]) - Fraction(old["oop_best_response_gain"])),
        "old_ip_gain_fraction": old["ip_best_response_gain"],
        "new_ip_gain_fraction": new["ip_best_response_gain"],
        "ip_gain_delta_fraction": str(Fraction(new["ip_best_response_gain"]) - Fraction(old["ip_best_response_gain"])),
        "old_nash_conv_fraction": old["nash_conv"],
        "new_nash_conv_fraction": new["nash_conv"],
        "nash_conv_delta_fraction": str(Fraction(new["nash_conv"]) - Fraction(old["nash_conv"])),
    }
    return {
        "benchmark_id": SCHEMA,
        "schema_version": 1,
        "generation_head": head,
        "historical_producer_source_sha256": producer,
        "verification_source_sha256": verification,
        "accepted_input_sha256": {"report": inputs["report_sha256"], "policy": inputs["policy_sha256"]},
        "fixture_id": FIXTURE_ID,
        "fixture": FIXTURE,
        "iterations": ITERATIONS,
        "discard": DISCARD,
        "averaged_sweeps": 97_000,
        "average_weight_sum": 4_995_548_500,
        "target_nash_conv_fraction": str(TARGET),
        "completed_training_calls": 1,
        "actual_complete_call_seconds": elapsed,
        "policy_file": POLICY_NAME,
        "policy_sha256": base._sha(policy_raw),
        "policy_metadata": _metadata_snapshot(payload),
        "results": {**audit, **observed},
        "scope": "One fixed configured river CFR+ direct-tail profile; exact evidence applies to the exact row-normalized interpretation of this serialized binary64 policy and does not establish general convergence.",
    }


def _validate_report_context(report, expected_math):
    if type(report) is not dict or report.get("benchmark_id") != SCHEMA:
        raise ValueError("Unexpected long-tail report identity")
    if type(report.get("schema_version")) is not int or report["schema_version"] != 1:
        raise ValueError("Unexpected long-tail report schema version")
    head = report.get("generation_head")
    if not isinstance(head, str) or not GIT_RE.fullmatch(head):
        raise ValueError("Malformed historical generation commit")
    producer_required = {"pokerlab/river_tail_adapter.py", "tests/test_river_tail_adapter.py",
                         "scripts/benchmark_river_direct_long_tail.py",
                         "tests/test_benchmark_river_direct_long_tail.py",
                         "tests/reference_river_tail_v1.py"}
    _validate_historical_map(report.get("historical_producer_source_sha256"), producer_required,
                             producer=True)
    _validate_historical_map(report.get("verification_source_sha256"), set(VERIFY_PATHS))
    if report["verification_source_sha256"] != expected_math:
        raise ValueError("Saved verification map differs from current committed math sources")
    elapsed = report.get("actual_complete_call_seconds")
    if (isinstance(elapsed, bool) or not isinstance(elapsed, (int, float))
            or not math.isfinite(elapsed) or elapsed < 0):
        raise ValueError("Complete-call timing must be finite nonnegative numeric data")
    return elapsed


def _verify_bundle(report_raw, policy_raw, *, root, expected_math, inputs,
                   current_head, bundle_guard=None):
    if type(report_raw) is not bytes or type(policy_raw) is not bytes:
        raise ValueError("Saved report and policy must be bytes")
    if len(report_raw) > REPORT_CAP or len(policy_raw) > POLICY_CAP:
        raise ValueError("Saved bundle exceeds byte cap")
    report = json.loads(report_raw)
    payload = json.loads(policy_raw)
    if type(report) is not dict or type(payload) is not dict:
        raise ValueError("Saved report and policy must be JSON objects")
    if base._canonical(report) != report_raw or base._canonical(payload) != policy_raw:
        raise ValueError("Saved bundle is not canonical LF JSON")
    elapsed = _validate_report_context(report, expected_math)
    if report.get("fixture_id") != FIXTURE_ID or report.get("fixture") != FIXTURE:
        raise ValueError("Saved report fixed fixture differs")
    if report.get("iterations") != ITERATIONS or report.get("discard") != DISCARD:
        raise ValueError("Saved report fixed schedule differs")
    if report.get("accepted_input_sha256") != {
            "report": inputs["report_sha256"], "policy": inputs["policy_sha256"]}:
        raise ValueError("Saved report accepted input hashes differ")
    if report.get("policy_sha256") != base._sha(policy_raw):
        raise ValueError("Saved policy hash differs from report")
    if report.get("completed_training_calls") != 1:
        raise ValueError("Saved report training call count differs")
    if current_head and base._head(root) != current_head:
        raise RuntimeError("Git HEAD changed during verification")
    if bundle_guard:
        bundle_guard()
    audit = _audit_math(payload, inputs, guard=bundle_guard)
    expected = _build_report(report["generation_head"],
                             report["historical_producer_source_sha256"],
                             report["verification_source_sha256"], inputs,
                             payload, audit, elapsed, policy_raw)
    if base._canonical(expected) != report_raw:
        raise ValueError("Saved report differs from complete independent reconstruction")
    if bundle_guard:
        bundle_guard()
    return expected


def _read_bundle(targets):
    return (base._read_bounded(targets["report"], REPORT_CAP),
            base._read_bounded(targets["policy"], POLICY_CAP))


def _final_bundle_guard(targets, owned, report_raw, policy_raw):
    expected = {"report": report_raw, "policy": policy_raw}
    for key, path in targets.items():
        if not path.exists():
            raise RuntimeError("Published bundle file disappeared")
        identity = owned[path]
        stat = path.stat()
        if (stat.st_dev, stat.st_ino) != identity:
            raise RuntimeError("Published bundle inode changed")
        if base._read_bounded(path, REPORT_CAP if key == "report" else POLICY_CAP) != expected[key]:
            raise RuntimeError("Published bundle bytes changed")


def _publish_bundle(report_raw, policy_raw, *, root, head, producer, verification, inputs):
    if type(report_raw) is not bytes or type(policy_raw) is not bytes:
        raise ValueError("Report and policy must be bytes before staging")
    if len(report_raw) > REPORT_CAP or len(policy_raw) > POLICY_CAP:
        raise ValueError("Report or policy exceeds its fixed byte cap before staging")
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
            _guard_generation(root, head, producer, verification, inputs)
            _final_bundle_guard(stages, owned, report_raw, policy_raw)

        stage_guard()
        actual_report, actual_policy = _read_bundle(stages)
        if actual_report != report_raw or actual_policy != policy_raw:
            raise RuntimeError("Staged bundle differs from original validated bytes")
        _verify_bundle(actual_report, actual_policy, root=root,
                       expected_math=verification, inputs=inputs,
                       current_head=head, bundle_guard=stage_guard)
        stage_guard()
        if any(path.exists() for path in targets.values()):
            raise FileExistsError("Fixed target appeared during staging")
        base._publish_staged(stages, targets, owned)

        def published_guard():
            _guard_generation(root, head, producer, verification, inputs)
            _final_bundle_guard(targets, owned, report_raw, policy_raw)

        published_guard()
        actual_report, actual_policy = _read_bundle(targets)
        _verify_bundle(actual_report, actual_policy, root=root,
                       expected_math=verification, inputs=inputs,
                       current_head=head, bundle_guard=published_guard)
        _guard_generation(root, head, producer, verification, inputs)
        _final_bundle_guard(targets, owned, report_raw, policy_raw)
    except BaseException:
        base._rollback_owned(owned)
        raise
    finally:
        base._rollback_owned({path: owned[path] for path in stages.values() if path in owned})


def _serialize_policy(payload):
    return base._canonical(payload)


def _safe_repr(payload):
    try:
        return repr(payload)
    except BaseException as error:
        return f"<repr failed: {type(error).__name__}: {error}>"


def _preserve_rejected(root, policy_raw, policy_object, head, producer, verification, elapsed, error):
    folder = root / "work" / "river_direct_long_tail_rejected"
    folder.mkdir(parents=True, exist_ok=True)
    valid_elapsed = (not isinstance(elapsed, bool) and isinstance(elapsed, (int, float))
                     and math.isfinite(elapsed) and elapsed >= 0)
    record = {
        "scope": "Rejected raw policy preservation; not accepted benchmark evidence",
        "fixture_id": FIXTURE_ID,
        "iterations": ITERATIONS,
        "discard": DISCARD,
        "generation_head": head,
        "producer_source_sha256": producer,
        "verification_source_sha256": verification,
        "accepted_input_sha256": {"report": INPUT_REPORT_SHA256, "policy": INPUT_POLICY_SHA256},
        "actual_complete_call_seconds": elapsed if valid_elapsed else None,
        "invalid_elapsed_repr": None if valid_elapsed else _safe_repr(elapsed),
        "rejection": str(error),
        "raw_policy_sha256": base._sha(policy_raw) if type(policy_raw) is bytes else None,
        "raw_policy_base64": base64.b64encode(policy_raw).decode("ascii")
            if type(policy_raw) is bytes else None,
        "unserialized_returned_policy_repr": None
            if type(policy_raw) is bytes else _safe_repr(policy_object),
    }
    path = folder / f"rejected-{uuid.uuid4().hex}.json"
    base._owned_write(path, base._canonical(record), {})
    return path


def generate(root=ROOT):
    targets = _targets(root)
    existing = [str(path) for path in targets.values() if path.exists()]
    if existing:
        raise FileExistsError("Refusing to overwrite fixed target(s): " + ", ".join(existing))
    inputs = _read_inputs(root)
    head, producer, verification = _source_context(root)
    guard = lambda: _guard_generation(root, head, producer, verification, inputs)
    guard()
    old_audit = _audit_math(inputs["policy"], inputs, iterations=10_000,
                            discard=3_000, guard=guard)
    if old_audit["exact_metrics_fractions"] != inputs["accepted_exact_metrics"]:
        raise ValueError("Accepted v1 exact metrics differ from its pinned report")
    guard()
    returned_policy = None
    call_completed = False
    elapsed = None
    try:
        print(f"START fixture={FIXTURE_ID} iterations={ITERATIONS} discard={DISCARD}", flush=True)
        start = time.perf_counter()
        from pokerlab.river_tail_adapter import solve_river_tail
        returned_policy = solve_river_tail(
            FIXTURE["board"], FIXTURE["oop"], FIXTURE["ip"], FIXTURE["config"],
            iterations=ITERATIONS, discard=DISCARD)
        call_completed = True
        elapsed = time.perf_counter() - start
        policy_raw = _serialize_policy(returned_policy)
        guard()
        audit = _audit_math(returned_policy, inputs, guard=guard)
        guard()
        report = _build_report(head, producer, verification, inputs,
                               returned_policy, audit, elapsed, policy_raw)
        report_raw = base._canonical(report)
        _publish_bundle(report_raw, policy_raw, root=root, head=head,
                        producer=producer, verification=verification, inputs=inputs)
        nash_conv = audit["exact_metrics_fractions"]["nash_conv"]
        print(f"DONE fixture={FIXTURE_ID} nash_conv={nash_conv} target_met={audit['exact_threshold_met']}", flush=True)
        return report
    except BaseException as error:
        if call_completed:
            try:
                raw = policy_raw if "policy_raw" in locals() else None
                _preserve_rejected(root, raw, returned_policy, head, producer,
                                   verification, elapsed, error)
            except BaseException as preserve_error:
                print(f"Could not preserve rejected raw policy: {preserve_error}", file=sys.stderr)
        raise


def verify(root=ROOT):
    inputs = _read_inputs(root)
    head, verification = _verification_context(root)
    replay_guard = lambda: _guard_replay(root, head, verification, inputs)
    replay_guard()
    old_audit = _audit_math(inputs["policy"], inputs, iterations=10_000,
                            discard=3_000, guard=replay_guard)
    if old_audit["exact_metrics_fractions"] != inputs["accepted_exact_metrics"]:
        raise ValueError("Accepted v1 exact metrics differ from its pinned report")
    replay_guard()
    targets = _targets(root)
    report_raw, policy_raw = _read_bundle(targets)
    owned = {path: base._bundle_identity(path) for path in targets.values()}

    def final_guard():
        _guard_replay(root, head, verification, inputs)
        _final_bundle_guard(targets, owned, report_raw, policy_raw)

    result = _verify_bundle(report_raw, policy_raw, root=root,
                            expected_math=verification, inputs=inputs,
                            current_head=head, bundle_guard=final_guard)
    _guard_replay(root, head, verification, inputs)
    _final_bundle_guard(targets, owned, report_raw, policy_raw)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true")
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    result = generate() if args.generate else verify()
    metrics = result["results"]["exact_metrics_fractions"]
    print(f"VERIFIED fixture={FIXTURE_ID} iterations={ITERATIONS} discard={DISCARD} "
          f"nash_conv={metrics['nash_conv']} target_met={result['results']['exact_threshold_met']} "
          f"exact_zero={result['results']['exact_nash_conv_zero']}")


if __name__ == "__main__":
    main()
