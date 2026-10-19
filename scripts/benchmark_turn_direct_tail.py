"""Generate or verify one fixed direct original-weight turn-tail benchmark.

The producer is intentionally fixed to the accepted full-deck raised fixture,
T=1500, D=1000, and the materialized public-vector adapter. Verification never
calls the trainer.
"""
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

from scripts import audit_full_deck_raised_exact as quotient
from scripts import audit_raised_turn_full_physical as fixed
from scripts import full_physical_exact_oracle as physical
from scripts import full_deck_raised_reference as reference
from scripts import river_tail_realization as tail_math
from scripts import turn_river_validation as rules


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks" / "results"
REPORT = RESULTS / "full-deck-raised-turn-direct-tail-v1.json"
POLICY = RESULTS / "full-deck-raised-turn-direct-tail-v1-materialized.json"
SCHEMA = "full-deck-raised-turn-direct-tail-v1"
MAX_REPORT_BYTES = 8_000_000
MAX_POLICY_BYTES = 2_000_000
TOTAL = 1500
DISCARD = 1000
THRESHOLD = Fraction(1, 1000)
METRICS = reference.METRICS
EXPECTED = {
    "worlds": 176, "worlds_materialized": 176, "deals": 4, "compatible_pairs": 4,
    "public_nodes": 1254,
    "public_states": 3039, "chance_nodes": 5, "terminal_nodes": 1780,
    "world_traversal_nodes": 32, "tree_actions": 2798,
    "info_sets": 2404, "public_state_limit": 250_000,
    "public_node_limit": 10_000, "public_batch_edge_limit": 250_000,
}
EXPECTED_USAGE = {"info_action_slots": 5364, "prefix_hand_edges": 180}
LIMITS = {
    "full_requested_world_node_work_limit": 30_000_000,
    "full_requested_dense_hand_state_pass_work_limit": 30_000_000,
    "info_action_slots_limit": 1_000_000,
    "prefix_hand_edge_limit": 250_000,
}


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _head(root):
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                   text=True).strip()


def _digest_file(root, path):
    return _sha((root / path).read_bytes().replace(b"\r\n", b"\n"))


def _training_paths(root):
    pokerlab = sorted(path.relative_to(root).as_posix()
                      for path in (root / "pokerlab").glob("*.py"))
    return tuple(sorted(set(pokerlab) | {
        "tests/test_turn_tail_adapter.py",
        "tests/test_benchmark_turn_direct_tail.py",
        "scripts/benchmark_turn_direct_tail.py",
    }))


def _verification_paths():
    return tuple(sorted(set(fixed.SOURCES) | set(quotient.SOURCES) |
                        set(reference.SOURCE_PATHS) | {
        "scripts/audit_raised_turn_full_physical.py",
        "scripts/audit_full_deck_raised_exact.py",
        "scripts/full_physical_exact_oracle.py",
        "scripts/full_deck_raised_reference.py",
        "scripts/river_tail_realization.py",
        "scripts/turn_river_validation.py",
        "scripts/benchmark_turn_direct_tail.py",
    }))


def _fingerprints(root, paths):
    return {name: _digest_file(root, name) for name in paths}


def _require_committed(root, fingerprints):
    for name, digest in fingerprints.items():
        subprocess.check_output(["git", "ls-files", "--error-unmatch", "--", name],
                                cwd=root, stderr=subprocess.STDOUT)
        committed = subprocess.check_output(["git", "show", f"HEAD:{name}"], cwd=root)
        _need(_sha(committed.replace(b"\r\n", b"\n")) == digest,
              "Required source is not committed at current HEAD: " + name)


def _guard(root, training, verification, initial_head, inputs):
    _need(_head(root) == initial_head, "Current Git HEAD changed during direct-tail operation")
    _need(_fingerprints(root, tuple(training)) == training,
          "A direct-tail producer source changed during operation")
    _need(_fingerprints(root, tuple(verification)) == verification,
          "A direct-tail verification source changed during operation")
    fixed._guard_inputs(root, inputs["accepted"])


def _read_capped(path, cap, label):
    path = Path(path)
    _need(path.stat().st_size <= cap, label + " exceeds pre-read byte cap")
    raw = path.read_bytes()
    _need(len(raw) <= cap and b"\r" not in raw, label + " exceeds cap or is not LF")
    return raw


def _decode(raw, label):
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(label + " is invalid JSON") from error


def _exact_map(metrics):
    _need(type(metrics) is dict and set(metrics) == set(METRICS),
          "Exact evaluator did not return all eight metrics")
    return {key: str(Fraction(value)) for key, value in metrics.items()}


def _check_exact_certificate(exact_metrics, certificate):
    quotient_metrics = certificate.get("metrics") if type(certificate) is dict else None
    _need(type(quotient_metrics) is dict and set(quotient_metrics) == set(METRICS) and
          set(exact_metrics) == set(METRICS) and
          all(Fraction(quotient_metrics[name]) == Fraction(exact_metrics[name])
              for name in METRICS),
          "Exact physical and quotient certificates disagree")
    return quotient.fraction_json(certificate)


def _validate_elapsed(elapsed):
    _need(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0,
          "Training call seconds must be finite and nonnegative")


def _own_flows(rows):
    keyed, order, probabilities, _ = tail_math._snapshot(rows, "candidate")
    reaches = tail_math._own_reaches(keyed, order, probabilities)
    return keyed, order, probabilities, reaches


def _compare_tail_flows(candidate, old_policy):
    current, order, probabilities, reaches = _own_flows(candidate["strategy"])
    old, old_order, old_probabilities, old_reaches = _own_flows(old_policy["strategy"])
    _need(set(current) == set(old), "Tail comparison row keys differ")
    maximum = Fraction(0)
    for key in order:
        _need(tail_math._metadata_without_probabilities(current[key]) ==
              tail_math._metadata_without_probabilities(old[key]),
              "Tail comparison legal row/action metadata differs")
        _need(len(probabilities[key]) == len(old_probabilities[key]),
              "Tail comparison action count differs")
        for index in range(len(probabilities[key])):
            left = reaches[key] * probabilities[key][index]
            right = old_reaches[key] * old_probabilities[key][index]
            maximum = max(maximum, abs(left - right))
    _need(maximum <= Fraction(1, 10**11),
          "Direct tail own-realization flow differs by more than 1e-11")
    return maximum


def _check_metadata(policy, model, *, total=TOTAL, discard=DISCARD):
    _need(type(policy) is dict, "Candidate policy must be an object")
    _fixture, board, config, _worlds, selected, _tree, _pairs = model
    for name, expected in {
        "method": "Direct original-weight CFR+ tail averaging",
        "algorithm": "cfrplus", "solver_version": "research-turn-tail-adapter-v1",
        "strategy_schema": "postflop-strategy-v1",
        "backend": "exact-public-chance-tree",
        "execution_backend": "direct-original-weight-tail-python",
        "diagnostics_backend": "public-batched-python",
        "board": list(board),
        "runout_mode": "full-deck", "iterations": total,
        "requested_iterations": total, "discard": discard,
        "source_iteration_window": [discard + 1, total],
        "averaged_sweeps": total - discard,
        "average_weight_sum": (total * (total + 1) - discard * (discard + 1)) // 2,
        "average_schedule": "direct-original-linear-sweep-weight-own-reach-tail",
        "update_schedule": "alternating-oop-then-ip",
        "requested_regret_passes": 2 * total,
        "requested_average_passes": total - discard,
        "requested_total_traversal_passes": 3 * total - discard,
        "training_calls": 1,
        "scope": "Research profile for a configured heads-up turn/river game; no preflop, multiway play, rake, or general exact-equilibrium claim.",
        "diagnostic_provenance": "Metrics recomputed from the direct original-weight tail policy using public-batched diagnostics; numeric convergence diagnostics are not an exact equilibrium certificate.",
        **EXPECTED,
    }.items():
        actual = policy.get(name)
        if type(expected) is int:
            _need(type(actual) is int, "Candidate metadata type differs: " + name)
        elif type(expected) is list:
            _need(type(actual) is list, "Candidate metadata type differs: " + name)
            if expected:
                _need(all(type(item) is type(expected[0]) for item in actual),
                      "Candidate metadata item type differs: " + name)
        _need(actual == expected, "Candidate metadata differs: " + name)
    expected_config = config.to_dict()
    _need(_canonical(policy.get("config")) == _canonical(expected_config) and
          _canonical(policy.get("turn_config")) == _canonical(expected_config) and
          _canonical(policy.get("river_config")) == _canonical(expected_config) and
          _canonical(policy.get("street_configs")) ==
          _canonical({"turn": expected_config, "river": expected_config}) and
          policy.get("pot") == config.pot and
          policy.get("effective_stack") == config.effective_stack,
          "Candidate turn/river configuration differs from fixed fixture")
    _need(type(policy.get("runouts")) is list and
          all(type(item) is str for item in policy["runouts"]) and
          set(policy["runouts"]) == set(selected) and len(policy["runouts"]) == 48 and
          type(policy.get("reachable_runouts")) is list and
          all(type(item) is str for item in policy["reachable_runouts"]) and
          set(policy["reachable_runouts"]) == set(selected) and
          len(policy["reachable_runouts"]) == 48,
          "Candidate full-deck runout support differs")
    _need(type(policy.get("resource_usage")) is dict, "Resource usage metadata is missing")
    usage = policy["resource_usage"]
    expected_usage = {
        "full_requested_world_node_work": 176 * 32 * total * 3,
        "full_requested_world_node_work_limit": LIMITS["full_requested_world_node_work_limit"],
        "full_requested_dense_hand_state_pass_work": 2 * 3039 * (3 * total + 3),
        "full_requested_dense_hand_state_pass_work_limit": LIMITS["full_requested_dense_hand_state_pass_work_limit"],
        "info_action_slots": EXPECTED_USAGE["info_action_slots"],
        "info_action_slots_limit": LIMITS["info_action_slots_limit"],
        "prefix_hand_edges": EXPECTED_USAGE["prefix_hand_edges"],
        "prefix_hand_edge_limit": LIMITS["prefix_hand_edge_limit"],
    }
    _need(set(usage) == set(expected_usage), "Candidate resource usage key set differs")
    for key, value in expected_usage.items():
        _need(type(usage.get(key)) is int and usage[key] == value,
              "Candidate resource metadata differs: " + key)
    _need(type(policy.get("strategy")) is list and len(policy["strategy"]) == 2404,
          "Candidate does not contain 2404 legal strategy rows")
    for metric in METRICS:
        value = policy.get(metric)
        _need(type(value) in (int, float) and math.isfinite(value),
              "Candidate numeric metric is absent or nonfinite: " + metric)
    return policy


def _reconstruct(policy, *, root, training, guard_training, verification,
                 generation_head, current_head, inputs, old_tail, elapsed=None,
                 bundle_guard=None):
    model = reference.model()
    fixture, _board, _config, _worlds, _selected, _tree, _pairs = model
    _check_metadata(policy, model)
    def guard():
        _guard(root, guard_training, verification, current_head, inputs)
        if bundle_guard is not None:
            bundle_guard()

    guard()
    numeric = rules.replay_policy(
        policy, fixture["oop"], fixture["ip"], board=fixture["board"],
        config=fixture["config"])
    rules.compare_result(policy, numeric, tolerance=1e-9)
    guard()
    exact = physical.audit_policy(policy, model)
    exact_metrics = _exact_map(exact["metrics"])
    guard()
    # Keep the optional quotient gate unchanged and mandatory for this fixed game.
    quotient_result = quotient.audit_policy(policy, model=model)
    quotient_certificate = _check_exact_certificate(
        exact["metrics"], quotient_result["certificate"])
    guard()
    max_flow = _compare_tail_flows(policy, old_tail)
    guard()
    for name in METRICS:
        _need(abs(float(policy[name]) - numeric[name]) <= 1e-9,
              "Saved diagnostics disagree with independent numeric replay: " + name)
    _validate_elapsed(elapsed)
    gap = Fraction(exact_metrics["nash_conv"])
    return {
        "schema_version": 1,
        "benchmark_id": SCHEMA,
        "fixture_id": fixture["id"],
        "generation_git_commit": generation_head,
        "training_source_sha256": training,
        "verification_source_sha256": verification,
        "accepted_input_sha256": {key: _sha(raw) for key, raw in inputs["accepted"].items()},
        "policy_file": POLICY.name,
        "policy_sha256": _sha(_canonical(policy)),
        "backend": "materialized-public-vector",
        "iterations": TOTAL,
        "discard": DISCARD,
        "averaged_sweeps": TOTAL - DISCARD,
        "average_weight_sum": policy["average_weight_sum"],
        "completed_adapter_training_calls": 1,
        "numeric_full_replay_metrics": {k: numeric[k] for k in METRICS},
        "numeric_replay_minus_policy_metrics": {
            k: numeric[k] - policy[k] for k in METRICS},
        "exact_full_physical_metrics": exact_metrics,
        "exact_threshold": "1/1000",
        "exact_1_over_1000_met": gap <= THRESHOLD,
        "exact_nash_conv_zero": gap == 0,
        "exact_counters": exact["counters"],
        "quotient_certificate": quotient_certificate,
        "quotient_full_numeric_metrics": quotient_result["full_numeric_metrics"],
        "old_tail_own_realization_max_abs_error_fraction": str(max_flow),
        "old_tail_own_realization_max_abs_error": float(max_flow),
        "old_tail_flow_gate_fraction": str(Fraction(1, 10**11)),
        "completed_call_seconds": elapsed,
        "scope": "One fixed full-deck raised turn/river game; direct original-weight CFR+ tail profile. Exact audit uses Fraction-normalized binary64 probabilities and certifies only this represented policy; numeric threshold and zero are observed outcomes, not generation gates or a general equilibrium guarantee.",
    }


def _load_old_tail(root):
    loaded = fixed._load_inputs(root)
    old = loaded["policies"][("tail", "materialized")]["policy"]
    return loaded, old


def _preserve_rejected(policy, error):
    """Keep an unaccepted raw result outside the repository on audit failure."""
    directory = Path(tempfile.gettempdir()) / "openpoker-direct-tail-rejected"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / ("full-deck-raised-turn-direct-tail-rejected-" +
                            uuid.uuid4().hex + ".json")
        try:
            raw = _canonical(policy)
        except (TypeError, ValueError):
            raw = (json.dumps(policy, sort_keys=True, indent=2, default=repr,
                              allow_nan=True) + "\n").encode("utf-8")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        print(f"REJECTED policy preserved at {path}: {error}", file=sys.stderr,
              flush=True)
        return path
    except OSError as save_error:
        print(f"REJECTED policy preservation failed: {save_error}", file=sys.stderr,
              flush=True)
        return None


def generate():
    root = Path(ROOT).resolve()
    _need(not REPORT.exists() and not POLICY.exists(),
          "Direct-tail accepted output already exists; immutable publication refused before training")
    initial_head = _head(root)
    training_paths = _training_paths(root)
    verification_paths = _verification_paths()
    training = _fingerprints(root, training_paths)
    verification = _fingerprints(root, verification_paths)
    _require_committed(root, training)
    _require_committed(root, verification)
    inputs, old_tail = _load_old_tail(root)
    _guard(root, training, verification, initial_head, inputs)

    fixture, _board, config, _worlds, _selected, _tree, _pairs = reference.model()
    print("START direct-tail backend=materialized T=1500 D=1000", flush=True)
    policy = None
    try:
        started = time.perf_counter()
        try:
            from pokerlab.turn_tail_adapter import solve_turn_tail
            policy = solve_turn_tail(
                fixture["board"], fixture["oop"], fixture["ip"],
                fixture["config"], iterations=TOTAL, discard=DISCARD)
            elapsed = time.perf_counter() - started
        finally:
            _guard(root, training, verification, initial_head, inputs)
        report = _reconstruct(policy, root=root, training=training,
                              guard_training=training,
                              verification=verification, generation_head=initial_head,
                              current_head=initial_head, inputs=inputs,
                              old_tail=old_tail, elapsed=elapsed)
        print("DONE direct-tail backend=materialized T=1500 D=1000 "
              f"nash_conv={report['exact_full_physical_metrics']['nash_conv']} "
              f"target_met={report['exact_1_over_1000_met']}", flush=True)
        policy_raw = _canonical(policy)
        report_raw = _canonical(report)
        _need(len(policy_raw) <= MAX_POLICY_BYTES, "Candidate policy exceeds byte cap")
        _need(len(report_raw) <= MAX_REPORT_BYTES, "Candidate report exceeds byte cap")
        _publish(policy_raw, report_raw, root, training, verification,
                 initial_head, inputs, old_tail)
        return report
    except BaseException as error:
        if policy is not None:
            _preserve_rejected(policy, error)
        raise


def _historical_map(value, required):
    _need(type(value) is dict and required <= set(value), "Historical source map lacks required files")
    for path, digest in value.items():
        parts = Path(path).parts if type(path) is str else ()
        allowed_pokerlab = (len(parts) == 2 and parts[0] == "pokerlab" and
                            parts[1].endswith(".py"))
        _need(type(path) is str and (allowed_pokerlab or path in required) and
              ".." not in parts and path.endswith(".py"),
              "Unexpected historical producer path")
        _need(type(digest) is str and len(digest) == 64 and
              all(char in "0123456789abcdef" for char in digest),
              "Invalid historical source digest")


def _verify_payload(report_raw, policy_raw, *, root, verification,
                    current_head, inputs, old_tail, bundle_guard=None):
    _need(_canonical(_decode(report_raw, "Report")) == report_raw,
          "Report is not canonical JSON")
    _need(_canonical(_decode(policy_raw, "Policy")) == policy_raw,
          "Policy is not canonical JSON")
    report = _decode(report_raw, "Report")
    policy = _decode(policy_raw, "Policy")
    _need(type(report) is dict and report.get("schema_version") == 1 and
          type(report.get("schema_version")) is int and report.get("benchmark_id") == SCHEMA,
          "Unsupported report envelope")
    source_required = {"pokerlab/turn_tail_adapter.py", "tests/test_turn_tail_adapter.py",
                       "tests/test_benchmark_turn_direct_tail.py",
                       "scripts/benchmark_turn_direct_tail.py"}
    _historical_map(report.get("training_source_sha256"), source_required)
    value = report.get("generation_git_commit")
    _need(type(value) is str and len(value) == 40 and
          all(char in "0123456789abcdef" for char in value),
          "Invalid historical generation commit")
    _need(report.get("verification_source_sha256") == verification,
          "Verification source fingerprints differ")
    _need(report.get("policy_file") == POLICY.name and report.get("policy_sha256") == _sha(policy_raw),
          "Report policy identity differs")
    rebuilt = _reconstruct(policy, root=root,
                           training=report["training_source_sha256"],
                           guard_training=verification,
                           verification=verification,
                           generation_head=report["generation_git_commit"],
                           current_head=current_head, inputs=inputs,
                           old_tail=old_tail,
                           elapsed=report.get("completed_call_seconds"),
                           bundle_guard=bundle_guard)
    _need(_canonical(rebuilt) == report_raw,
          "Saved report differs from full no-training reconstruction")
    return report


def _read_bundle(report_path, policy_path):
    report_raw = _read_capped(report_path, MAX_REPORT_BYTES, "Report")
    policy_raw = _read_capped(policy_path, MAX_POLICY_BYTES, "Policy")
    return report_raw, policy_raw


def verify_bundle():
    root = Path(ROOT).resolve()
    report_path, policy_path = REPORT, POLICY
    initial_head = _head(root)
    verification = _fingerprints(root, _verification_paths())
    _require_committed(root, verification)
    inputs, old_tail = _load_old_tail(root)
    report_raw, policy_raw = _read_bundle(report_path, policy_path)
    def bundle_guard():
        _need(_read_capped(report_path, MAX_REPORT_BYTES, "Guarded report") == report_raw and
              _read_capped(policy_path, MAX_POLICY_BYTES, "Guarded policy") == policy_raw,
              "Saved direct-tail report or policy changed during replay")
    report = _verify_payload(report_raw, policy_raw, root=root,
                             verification=verification, current_head=initial_head,
                             inputs=inputs, old_tail=old_tail,
                             bundle_guard=bundle_guard)
    _need(_read_capped(report_path, MAX_REPORT_BYTES, "Final report") == report_raw and
          _read_capped(policy_path, MAX_POLICY_BYTES, "Final policy") == policy_raw,
          "Saved direct-tail bundle changed during verification")
    _guard(root, verification, verification, initial_head, inputs)
    bundle_guard()
    return report


def _file_identity(path):
    stat = Path(path).stat()
    return stat.st_dev, stat.st_ino


def _write_exclusive(path, raw, owned):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        identity = (os.fstat(fd).st_dev, os.fstat(fd).st_ino)
        owned[Path(path)] = identity
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return identity
    finally:
        os.close(fd)


def _publish(policy_raw, report_raw, root, training, verification,
             initial_head, inputs, old_tail):
    _need(not REPORT.exists() and not POLICY.exists(),
          "Direct-tail publication target appeared during generation")
    RESULTS.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex
    staged_policy = RESULTS / ("." + POLICY.name + "." + suffix + ".stage")
    staged_report = RESULTS / ("." + REPORT.name + "." + suffix + ".stage")
    stage_ids, published_ids = {}, {}
    try:
        _write_exclusive(staged_policy, policy_raw, stage_ids)
        _write_exclusive(staged_report, report_raw, stage_ids)
        _need(_file_identity(staged_policy) == stage_ids[staged_policy] and
              _file_identity(staged_report) == stage_ids[staged_report] and
              _read_capped(staged_policy, MAX_POLICY_BYTES, "Staged policy") == policy_raw and
              _read_capped(staged_report, MAX_REPORT_BYTES, "Staged report") == report_raw,
              "Staged bundle bytes or file identities changed")
        def staged_guard():
            _need(_file_identity(staged_policy) == stage_ids[staged_policy] and
                  _file_identity(staged_report) == stage_ids[staged_report] and
                  _read_capped(staged_policy, MAX_POLICY_BYTES, "Guarded staged policy") == policy_raw and
                  _read_capped(staged_report, MAX_REPORT_BYTES, "Guarded staged report") == report_raw,
                  "Staged bundle changed during replay")
        _verify_payload(report_raw, policy_raw, root=root,
                        verification=verification, current_head=initial_head,
                        inputs=inputs, old_tail=old_tail,
                        bundle_guard=staged_guard)
        _guard(root, training, verification, initial_head, inputs)
        for staged, target in ((staged_policy, POLICY), (staged_report, REPORT)):
            os.link(staged, target)
            published_ids[target] = stage_ids[staged]
            _need(_file_identity(target) == stage_ids[staged],
                  "Published file identity differs from validated stage")
        final_report, final_policy = _read_bundle(REPORT, POLICY)
        def published_guard():
            _need(_file_identity(REPORT) == published_ids[REPORT] and
                  _file_identity(POLICY) == published_ids[POLICY] and
                  _read_capped(REPORT, MAX_REPORT_BYTES, "Guarded final report") == report_raw and
                  _read_capped(POLICY, MAX_POLICY_BYTES, "Guarded final policy") == policy_raw,
                  "Published bundle changed during replay")
        _verify_payload(final_report, final_policy, root=root,
                        verification=verification, current_head=initial_head,
                        inputs=inputs, old_tail=old_tail,
                        bundle_guard=published_guard)
        _need(final_report == report_raw and final_policy == policy_raw and
              _file_identity(REPORT) == published_ids[REPORT] and
              _file_identity(POLICY) == published_ids[POLICY],
              "Published bundle bytes or owned file identities changed during replay")
        _guard(root, training, verification, initial_head, inputs)
        published_guard()
    except BaseException:
        for path, identity in published_ids.items():
            if path.exists() and _file_identity(path) == identity:
                path.unlink()
        raise
    finally:
        for path, identity in stage_ids.items():
            if path.exists() and _file_identity(path) == identity:
                path.unlink()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    outcome = generate() if args.generate else verify_bundle()
    print(json.dumps({"report": REPORT.name, "policy": POLICY.name,
                      "nash_conv": outcome.get("exact_full_physical_metrics", {}).get("nash_conv")},
                     sort_keys=True))
