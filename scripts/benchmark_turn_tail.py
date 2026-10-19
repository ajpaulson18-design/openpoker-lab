"""Fixed same-run turn CFR+ tail experiment and no-training saved verifier."""
import argparse
import hashlib
import json
import math
import os
import platform
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

from scripts import full_deck_raised_fixture as fixture
from scripts import full_deck_raised_reference as reference
from scripts import river_tail_realization as realization
from scripts.benchmark_turn_river_independent import ROOT
from scripts.benchmark_full_deck_raised_turn import (
    ALGORITHM, BACKENDS, METRICS, THRESHOLD, TOLERANCE,
    _profile_metadata, _require, _sha, expected_work, frozen_case,
    validate_profile_metadata,
)
from scripts.turn_river_validation import compare_result
from scripts.turn_tail_capture import capture


REPORT = ROOT / "benchmarks/results/full-deck-raised-turn-tail-v1.json"
POLICIES_DIR = ROOT / "benchmarks/results/full-deck-raised-turn-tail-policies-v1"
BASELINE_REPORT = ROOT / "benchmarks/results/full-deck-raised-turn-benchmark-v1.json"
BASELINE_POLICIES = ROOT / "benchmarks/results/full-deck-raised-turn-policies-v1"
BASELINE_REPORT_SHA256 = "4381b2fbb7008572ff0993d005ee6d2d8dd00c6f9a38621d65b9621b469a9669"
REFERENCE_PATH = ROOT / "benchmarks/results/full-deck-raised-turn-reference-v1.json"
REFERENCE_SHA256 = "bff6aaf4d2bf6038503645787d66cff9f57bcb1385e334364f72126a67211165"
REFERENCE_PUBLIC_TREE_SHA256 = "70d87064c6d7048b75784b6623a2dc6249f57ac61384a27d1724c3d53563bd61"
BASELINE_SOURCE_COMMIT = "6541f3da4bc1d71954febb4c0ad70d4a91e2f617"
DISCARD, TOTAL = 1000, 1500
WINDOW = ("prefix", "full", "tail")
SCHEMA_VERSION = 1
BENCHMARK_ID = "full-deck-raised-turn-tail-v1"
MAX_REPORT_BYTES = 8_000_000
MAX_POLICY_BYTES = 2_000_000
REQUIRED_BASELINE_POLICIES = tuple(
    f"full-deck-raised-turn-v1-{backend}-{iteration}.json"
    for backend in BACKENDS for iteration in (100, 1000, 1500)
)
REQUIRED_SOURCES = (
    "pokerlab/cards.py", "pokerlab/matrix_free_turn.py",
    "pokerlab/postflop_solver.py", "pokerlab/river_config.py",
    "scripts/benchmark_turn_river_independent.py",
    "scripts/full_deck_raised_fixture.py", "scripts/full_deck_raised_reference.py",
    "scripts/preflop_validation.py", "scripts/turn_blocker_sequence_fixture.py",
    "scripts/turn_river_validation.py", "scripts/verify_turn_blocker_sequence.py",
    "scripts/benchmark_full_deck_raised_turn.py",
    "tests/test_full_deck_raised_diagnostics.py",
    "scripts/river_tail_realization.py", "scripts/turn_tail_capture.py",
    "scripts/benchmark_turn_tail.py", "tests/test_turn_tail_realization.py",
    "tests/test_turn_tail_capture.py", "tests/test_benchmark_turn_tail.py",
    "tests/test_turn_tail_artifacts.py",
)
PROFILE_METADATA_FIELDS = (
    "algorithm", "iterations", "execution_backend", "diagnostics_backend",
    "terminal_backend", "board", "runouts", "runout_mode", "reachable_runouts",
    "config", "turn_config", "river_config", "street_configs", "info_sets",
    "public_states", "public_nodes", "training_passes_per_iteration",
    "update_schedule", "average_schedule", "worlds", "compatible_pairs",
    "world_traversal_nodes", "worlds_materialized", "compatible_world_count",
    "public_state_limit", "resource_usage",
)


def _canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                   text=True).strip()


def fingerprints():
    paths = {p.relative_to(ROOT).as_posix() for p in (ROOT / "pokerlab").glob("*.py")}
    paths.update(REQUIRED_SOURCES)
    result = {}
    for relative in sorted(paths):
        raw = (ROOT / relative).read_bytes()
        if relative.endswith(".py"):
            raw = raw.replace(b"\r\n", b"\n")
        result[relative] = _sha(raw)
    return result


def _guard(source_map, expected_head):
    _require(fingerprints() == source_map, "Pinned source changed during tail operation")
    _require(_head() == expected_head, "Git HEAD changed during tail operation")


def _valid_sha(value):
    return (type(value) is str and len(value) == 64 and
            all(c in "0123456789abcdef" for c in value))


def _read_capped(path, cap, label):
    path = Path(path)
    _require(path.stat().st_size <= cap, label + " exceeds byte cap")
    raw = path.read_bytes()
    _require(len(raw) <= cap, label + " exceeds byte cap")
    return raw


def _baseline_pins():
    """Read and validate immutable 1000/1500 trajectory comparison anchors."""
    raw = _read_capped(BASELINE_REPORT, 1_000_000, "Baseline report")
    _require(_valid_sha(BASELINE_REPORT_SHA256) and
             _sha(raw) == BASELINE_REPORT_SHA256,
             "Frozen baseline report SHA256 pin is not configured or differs")
    report = json.loads(raw)
    _require(b"\r" not in raw and _canonical(report) == raw,
             "Baseline report is not canonical LF JSON")
    _require(type(report) is dict and report.get("benchmark_id") ==
             "full-deck-raised-turn-benchmark-v1", "Unexpected baseline report")
    rows = report.get("results")
    _require(type(rows) is list and len(rows) == 6, "Baseline must contain six rows")
    result = {"report_sha256": _sha(raw), "report_bytes": raw, "policies": {}}
    for backend in BACKENDS:
        for iteration in (100, 1000, 1500):
            filename = f"full-deck-raised-turn-v1-{backend}-{iteration}.json"
            row = next((x for x in rows if x.get("backend") == backend and
                        x.get("iterations_requested") == iteration), None)
            _require(type(row) is dict and row.get("policy_file") == filename,
                     "Baseline row or policy identity differs")
            raw_policy = _read_capped(BASELINE_POLICIES / filename,
                                      MAX_POLICY_BYTES, "Baseline policy")
            _require(_sha(raw_policy) == row.get("policy_sha256"),
                     "Baseline policy hash differs from its report")
            _require(b"\r" not in raw_policy and
                     _canonical(json.loads(raw_policy)) == raw_policy,
                     "Baseline policy is not canonical LF JSON")
            result["policies"][(backend, iteration)] = raw_policy
    return result


def _reference_bytes():
    raw = _read_capped(REFERENCE_PATH, reference.MAX_REPORT_BYTES, "Accepted reference")
    _require(_sha(raw) == REFERENCE_SHA256, "Accepted reference hash differs")
    return raw


def _guard_artifacts(baseline, reference_raw):
    """Reject accepted-input drift before spending another complete call."""
    _require(_read_capped(BASELINE_REPORT, 1_000_000, "Baseline report") ==
             baseline["report_bytes"], "Baseline report changed during operation")
    for (backend, iteration), expected in baseline["policies"].items():
        name = f"full-deck-raised-turn-v1-{backend}-{iteration}.json"
        _require(_read_capped(BASELINE_POLICIES / name, MAX_POLICY_BYTES, "Baseline policy") == expected,
                 "Baseline policy changed during operation")
    _require(_reference_bytes() == reference_raw, "Accepted reference changed during operation")


def _json_fraction(value):
    if isinstance(value, dict):
        return {str(k): _json_fraction(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_fraction(v) for v in value]
    if isinstance(value, Fraction):
        return f"{value.numerator}/{value.denominator}"
    return value


def _policy_name(backend, kind):
    return f"full-deck-raised-turn-tail-v1-{backend}-{kind}.json"


def _metric_close(actual, expected):
    return (type(actual) is dict and set(actual) == set(METRICS) and
            all(type(actual[k]) in (int, float) and math.isfinite(actual[k]) and
                abs(actual[k] - expected[k]) <= TOLERANCE for k in METRICS))


def _diff_close(actual, expected):
    return (type(actual) is dict and type(expected) is dict and
            set(actual) == set(expected) and
            all(type(actual[k]) in (int, float) and math.isfinite(actual[k]) and
                abs(actual[k] - expected[k]) <= TOLERANCE for k in expected))


def _strategy_bytes(policy):
    return _canonical(policy["strategy"])


def _derived_payload(source, kind, probabilities, *,
                     discard=DISCARD, total=TOTAL):
    result = json.loads(json.dumps(source))
    _require(len(probabilities) == len(result.get("strategy", ())),
             "Derived strategy row count changed")
    for row, values in zip(result["strategy"], probabilities):
        _require(len(values) == len(row["actions"]), "Derived action count changed")
        for action, probability in zip(row["actions"], values):
            action["probability"] = float(probability)
    result.update({
        "solver_version": "research-raised-turn-tail-v1",
        "source_solver_version": source.get("solver_version"),
        "method": "Same-run CFR+ realization-flow subtraction",
        "diagnostic_provenance": "Independent numeric-rule replay; derived policy, not production trainer output",
        "research_profile": kind,
        "source_requested_iterations": total,
        "source_iteration_window": [1, discard] if kind == "prefix" else
                                   [discard + 1, total] if kind == "tail" else [1, total],
        "averaged_sweeps": discard if kind == "prefix" else total - discard if kind == "tail" else total,
        "iterations": discard if kind == "prefix" else total,
        "average_schedule": "linear-prefix-own-reach" if kind == "prefix" else
                            "linear-tail-own-realization" if kind == "tail" else
                            source.get("average_schedule"),
        "resource_metadata_scope": f"Admission/resource metadata and full-request work charge cover the original complete {total}-sweep call; derived policy contains its labeled window only.",
        "scope": "Fixed full-deck raised turn/river CFR+ research profile.",
    })
    return result


def _normalize_rows(rows):
    return [[float(action["probability"]) for action in row["actions"]] for row in rows]


def _reconstruct(prefix, full, discard=DISCARD, total=TOTAL):
    tail_rows, ledger = realization.reconstruct_tail(
        prefix["strategy"], full["strategy"], discard, total)
    return _derived_payload(full, "tail", _normalize_rows(tail_rows),
                            discard=discard, total=total), ledger


def _replay(policy, backend, kind, case, oracle=None):
    oracle = _independent_oracle(policy, case) if oracle is None else oracle
    metrics = {name: oracle[name] for name in METRICS}
    _require(_metric_close({name: policy.get(name) for name in METRICS}, metrics),
             "Saved policy metrics differ from independent replay")
    differences = compare_result(policy, oracle, tolerance=TOLERANCE)
    return metrics, differences, oracle


def _independent_oracle(policy, case):
    from scripts.turn_river_validation import replay_policy
    oracle = replay_policy(policy, case["oop"], case["ip"], board=case["board"],
                          config=case["config"], river_config=case["river_config"])
    _require(oracle.get("worlds") == 176 and oracle.get("compatible_pair_count") == 4 and
             oracle.get("checked_information_sets") == 2404,
             "Independent replay did not cover all physical rows")
    _require(all(type(oracle.get(metric)) in (int, float) and
                 math.isfinite(oracle[metric]) for metric in METRICS),
             "Independent replay returned nonfinite metrics")
    return oracle


def process_capture(case, backend, discard, total, interval=None):
    """Capture and convert one call; supports only cheap 10-sweep probes or the fixed grid."""
    full, prefix, evidence = capture(case, backend, discard, total, interval=interval)
    census = fixture.census()
    validate_profile_metadata(full, case, backend, total, census,
                              allow_probe=(total == 10))
    prefix = _derived_payload(full, "prefix", _normalize_rows(prefix["strategy"]),
                              discard=discard, total=total)
    tail, ledger = _reconstruct(prefix, full, discard, total)
    policies = {"prefix": prefix, "full": full, "tail": tail}
    oracles = {}
    for kind, policy in policies.items():
        oracle = _independent_oracle(policy, case)
        metrics = {name: oracle[name] for name in METRICS}
        if kind != "full":
            policy.update(metrics)
        metrics, differences, oracle = _replay(policy, backend, kind, case, oracle=oracle)
        oracles[kind] = {"metrics": metrics, "differences": differences,
                         "worlds": oracle["worlds"],
                         "compatible_pairs": oracle["compatible_pair_count"],
                         "information_rows": oracle["checked_information_sets"]}
    return policies, evidence, oracles, ledger


def _check_report_envelope(report, sources, current_head, baseline):
    _require(type(report) is dict and type(report.get("schema_version")) is int and
             report["schema_version"] == SCHEMA_VERSION and
             report.get("benchmark_id") == BENCHMARK_ID, "Unsupported report envelope")
    _require(type(report.get("generation_git_commit")) is str and
             len(report["generation_git_commit"]) == 40 and
             all(c in "0123456789abcdef" for c in report["generation_git_commit"]),
             "Historical generation commit is invalid")
    _require(report.get("baseline_report_sha256") == baseline["report_sha256"],
             "Baseline report pin differs")
    _require(report.get("reference_sha256") == REFERENCE_SHA256,
             "Accepted physical/tree reference pin differs")
    _require(type(report.get("generation_capture_calls")) is int and
             report["generation_capture_calls"] == 2, "Generation capture count differs")
    saved_sources = report.get("source_sha256")
    _require(type(saved_sources) is dict and set(REQUIRED_SOURCES).issubset(saved_sources),
             "Saved source fingerprints omit required proof sources")
    _require(all(saved_sources[name] == sources[name] for name in REQUIRED_SOURCES),
             "A required proof source fingerprint differs")
    for name, digest in saved_sources.items():
        _require(type(name) is str and (name in REQUIRED_SOURCES or
                 (name.startswith("pokerlab/") and name.count("/") == 1 and
                  name.endswith(".py") and ".." not in name)) and _valid_sha(digest),
                 "Malformed historical source context")
    _require(report.get("baseline_source_commit") == BASELINE_SOURCE_COMMIT,
             "Historical baseline source revision differs")
    saved_head = report.get("current_head_at_generation")
    _require(type(saved_head) is str and len(saved_head) == 40 and
             all(c in "0123456789abcdef" for c in saved_head),
             "Historical generation HEAD is invalid")
    _require(report.get("generation_git_commit") == saved_head,
             "Generation HEAD fields disagree")


def _verify_saved(report_path, policies_dir, *, baseline=None, expected_sources=None,
                  expected_head=None):
    report_path = Path(report_path)
    raw_report = _read_capped(report_path, MAX_REPORT_BYTES, "Tail report")
    _require(b"\r" not in raw_report and
             _canonical(json.loads(raw_report)) == raw_report,
             "Tail report is not canonical LF JSON")
    source_map = fingerprints() if expected_sources is None else expected_sources
    current_head = _head() if expected_head is None else expected_head
    _guard(source_map, current_head)
    baseline = _baseline_pins() if baseline is None else baseline
    raw_reference = _read_capped(REFERENCE_PATH, reference.MAX_REPORT_BYTES,
                                 "Accepted physical/tree reference")
    _require(_sha(raw_reference) == REFERENCE_SHA256,
             "Accepted physical/tree reference hash differs")
    checked_reference = reference.verify_saved_artifact(REFERENCE_PATH)
    _require(checked_reference["reference"].get("public_tree_sha256") ==
             REFERENCE_PUBLIC_TREE_SHA256,
             "Accepted public-tree reference identity differs")
    report = json.loads(raw_report)
    _check_report_envelope(report, source_map, current_head, baseline)
    case = frozen_case()
    census = fixture.to_jsonable(fixture.census())
    _require(_canonical(report.get("fixture")) == _canonical(case) and
             _canonical(report.get("census")) == _canonical(census),
             "Saved fixture or census differs")
    _require(report.get("methodology") == _methodology(), "Saved methodology differs")
    results = report.get("results")
    _require(type(results) is list and len(results) == 6, "Expected six derived profiles")
    expected_order = [(backend, kind) for backend in BACKENDS for kind in WINDOW]
    _require([(row.get("backend"), row.get("profile")) for row in results
              if type(row) is dict] == expected_order,
             "Report fixed result order differs")
    bykey = {(row.get("backend"), row.get("profile")): row for row in results
             if type(row) is dict}
    _require(len(bykey) == 6 and set(bykey) ==
             {(backend, kind) for backend in BACKENDS for kind in WINDOW},
             "Fixed backend/window grid differs")
    replayed = []
    for backend in BACKENDS:
        _guard(source_map, current_head)
        prefix = full = None
        loaded = {}
        pinned_full_metadata = _profile_metadata(
            json.loads(baseline["policies"][(backend, TOTAL)]))
        for kind in WINDOW:
            _guard(source_map, current_head)
            row = bykey[(backend, kind)]
            expected_file = _policy_name(backend, kind)
            _require(row.get("policy_file") == expected_file and
                     row.get("backend") == backend and row.get("profile") == kind,
                     "Unexpected saved profile identity")
            iterations = DISCARD if kind == "prefix" else TOTAL
            census = fixture.census()
            work_forecast = expected_work(backend, TOTAL, census)
            _require(type(row.get("iterations")) is int and row["iterations"] == iterations and
                     type(row.get("source_requested_iterations")) is int and
                     row["source_requested_iterations"] == TOTAL and
                     row.get("algorithm") == ALGORITHM and
                     row.get("target_exploitability") is None and
                     type(row.get("threshold")) is float and row["threshold"] == THRESHOLD and
                     type(row.get("work_charge")) is int and row["work_charge"] == work_forecast and
                     type(row.get("work_limit")) is int and
                     row.get("work_limit") == fixture.REFERENCE_WORK_CAP and
                     type(row.get("iterations_completed")) is int and
                     row.get("iterations_completed") == TOTAL and
                     row.get("capture_callback_iterations") == [DISCARD, TOTAL] and
                     type(row.get("capture_trainer_calls")) is int and row["capture_trainer_calls"] == 1 and
                     row.get("final_snapshot_matches_returned_profile") is True and
                     row.get("worlds") == 176 and row.get("compatible_pairs") == 4 and
                     row.get("information_rows") == 2404 and
                     row.get("public_decisions") == census.decisions and
                     row.get("independent_public_decisions") == census.decisions and
                     row.get("public_states") == census.public_nodes,
                     "Saved fixed workload, algorithm, target, or counters differ")
            timing_fields = ("full_call_seconds_uncontrolled", "conversion_seconds",
                             "full_policy_json_seconds",
                             "independent_replay_seconds", "saved_policy_replay_seconds",
                             "capture_validation_replay_seconds")
            _require(all(type(row.get(name)) in (int, float) and
                         math.isfinite(row[name]) and row[name] >= 0
                         for name in timing_fields),
                     "Saved timing observations must be finite and nonnegative")
            _require(row.get("source_requested_iterations") == TOTAL and
                     row.get("work_charge") == work_forecast,
                     "Saved complete-request work forecast differs")
            path = Path(policies_dir) / expected_file
            raw = _read_capped(path, MAX_POLICY_BYTES, "Saved tail policy")
            _require(b"\r" not in raw and _canonical(json.loads(raw)) == raw,
                     "Saved policy is not canonical LF JSON")
            _require(_sha(raw) == row.get("policy_sha256"), "Saved policy hash differs")
            policy = json.loads(raw)
            loaded[kind] = policy
            if kind == "prefix":
                prefix = policy
            elif kind == "full":
                full = policy
            else:
                _require(type(row.get("ledger")) is dict, "Tail ledger missing")
            # Derived profiles inherit full-request production metadata. Validate
            # that unchanged full payload before separately replaying derived rows.
            if kind != "full":
                _require(policy.get("source_requested_iterations") == TOTAL,
                         "Derived payload omits full source-call cost")
            if kind == "full":
                validate_profile_metadata(policy, case, backend, TOTAL, fixture.census())
            _guard(source_map, current_head)
            metrics, diffs, oracle = _replay(policy, backend, kind, case)
            _guard(source_map, current_head)
            _require(_metric_close(row.get("independent_metrics"), metrics) and
                     _metric_close(row.get("metrics"), metrics) and
                     _diff_close(row.get("scalar_differences"), diffs) and
                     row.get("threshold_met") is (metrics["nash_conv"] <= THRESHOLD),
                     "Saved metrics or threshold marker differ")
            _require(oracle["worlds"] == 176 and oracle["compatible_pair_count"] == 4 and
                     oracle["checked_information_sets"] == 2404,
                     "Replay did not cover complete physical game")
            _require(row.get("independent_replay") is True,
                     "Independent replay marker missing")
            _require(_canonical(row.get("actual_metadata")) ==
                     _canonical(pinned_full_metadata),
                     "Saved full-request production metadata differs")
            replayed.append((backend, kind, metrics))
        baseline_prefix = json.loads(baseline["policies"][(backend, DISCARD)])
        baseline_full_bytes = baseline["policies"][(backend, TOTAL)]
        _require(_canonical(full) == baseline_full_bytes,
                 "Current same-run full result differs from immutable baseline bytes")
        _require(_strategy_bytes(prefix) == _strategy_bytes(baseline_prefix),
                 "Same-run prefix strategy differs from immutable prefix baseline")
        expected_prefix = _derived_payload(
            full, "prefix", _normalize_rows(prefix["strategy"]))
        expected_prefix.update({name: bykey[(backend, "prefix")]["metrics"][name]
                                for name in METRICS})
        _require(_canonical(expected_prefix) == _canonical(prefix),
                 "Saved derived prefix metadata/provenance differs from reconstruction")
        expected_tail, ledger = _reconstruct(prefix, full)
        expected_tail.update({name: bykey[(backend, "tail")]["metrics"][name]
                              for name in METRICS})
        _require(_canonical(bykey[(backend, "tail")].get("ledger")) ==
                 _canonical(_json_fraction(ledger)),
                 "Saved exact tail correction ledger differs")
        _require(_canonical(expected_tail) == _canonical(loaded["tail"]),
                 "Saved derived tail or exact correction ledger differs from reconstruction")
    _guard(source_map, current_head)
    _require(report_path.read_bytes() == raw_report, "Report changed during verification")
    for row in results:
        raw = _read_capped(Path(policies_dir) / row["policy_file"], MAX_POLICY_BYTES,
                           "Saved tail policy")
        _require(_sha(raw) == row["policy_sha256"], "Policy changed during verification")
    _guard_artifacts(baseline, raw_reference)
    _guard(source_map, current_head)
    return {"status": "VERIFIED_SAVED_TURN_TAIL", "training_calls": 0,
            "profiles": len(results), "report_sha256": _sha(raw_report),
            "replayed": replayed}


def _methodology():
    return {
        "design": "One same-run CFR+ call per backend at T=1500, capturing D=1000 and T=1500; fixed D/T tail extraction.",
        "conditioning": "Full-deck chance, no selected runouts; four compatible private pairs, 44 rivers each, 176 physical worlds.",
        "threshold": "NashConv <= 0.001 chips is report-only; every miss is retained.",
        "timing": "One complete solve plus callback observation; conversion and independent saved-profile replay timed separately. Uncontrolled wall-time only.",
        "limitation": "Derived numeric replay is not an arbitrary-policy exact certificate. No equilibrium claim; generic exact audit remains at its existing rejected work limit.",
        "resources": "The original complete 1500-sweep request retains the unchanged production 30,000,000 work admission; forecasts do not authorize admission.",
    }


def _atomic_exclusive(path, payload, created):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp",
                                     dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _require(Path(temp_name).read_bytes() == payload, "Staged policy bytes differ")
        try:
            os.link(temp_name, path)
            created.append(path)
        except FileExistsError as exc:
            raise ValueError("Refusing to replace an immutable tail artifact") from exc
    finally:
        Path(temp_name).unlink(missing_ok=True)


def generate(report_path=REPORT, policies_dir=POLICIES_DIR, *, allow_training=False):
    """Run only when explicitly enabled; tests must never run the fixed grid."""
    _require(allow_training is True, "Long fixed training is disabled in this draft")
    report_path, policies_dir = Path(report_path), Path(policies_dir)
    if report_path.exists():
        return _verify_saved(report_path, policies_dir)
    names = [policies_dir / _policy_name(b, k) for b in BACKENDS for k in WINDOW]
    _require(not any(path.exists() for path in names),
             "Partial immutable policy set exists; refusing training")
    baseline = _baseline_pins()
    reference_raw = _reference_bytes()
    source_map, head = fingerprints(), _head()
    case, census = frozen_case(), fixture.census()
    created = []
    try:
        results = []
        for backend in BACKENDS:
            _guard(source_map, head)
            _guard_artifacts(baseline, reference_raw)
            work = expected_work(backend, TOTAL, census)
            _require(work <= fixture.REFERENCE_WORK_CAP,
                     "Full requested call exceeds the unchanged work cap")
            print(f"START backend={backend} iterations={TOTAL}", flush=True)
            full, prefix, capture_meta = capture(case, backend, DISCARD, TOTAL,
                                                 interval=DISCARD)
            _guard(source_map, head)
            _guard_artifacts(baseline, reference_raw)
            _require(type(capture_meta.get("trainer_calls")) is int and capture_meta["trainer_calls"] == 1 and
                     capture_meta.get("final_snapshot_exactly_matches_returned_profile") is True,
                     "Capture did not establish one unchanged training trajectory")
            validate_profile_metadata(full, case, backend, TOTAL, census)
            json_started = time.perf_counter()
            full_raw = _canonical(full)
            full_json_seconds = time.perf_counter() - json_started
            _guard(source_map, head)
            baseline_full = baseline["policies"][(backend, TOTAL)]
            _require(full_raw == baseline_full,
                     "Same-run full call differs from immutable baseline bytes")
            baseline_prefix = json.loads(baseline["policies"][(backend, DISCARD)])
            _require(_strategy_bytes(prefix) == _strategy_bytes(baseline_prefix),
                     "Same-run prefix strategy differs from immutable baseline")
            _guard(source_map, head)
            convert_started = time.perf_counter()
            tail, ledger = _reconstruct(prefix, full)
            prefix = _derived_payload(full, "prefix", _normalize_rows(prefix["strategy"]))
            conversion_seconds = time.perf_counter() - convert_started
            _guard(source_map, head)
            profile_payloads = {"prefix": prefix, "full": full, "tail": tail}
            for kind in WINDOW:
                policy = profile_payloads[kind]
                _guard(source_map, head)
                profile_replay_started = time.perf_counter()
                oracle = _independent_oracle(policy, case)
                metrics = {name: oracle[name] for name in METRICS}
                if kind != "full":
                    policy.update(metrics)
                metrics, diffs, oracle = _replay(policy, backend, kind, case, oracle=oracle)
                profile_replay_seconds = time.perf_counter() - profile_replay_started
                _guard(source_map, head)
                filename = _policy_name(backend, kind)
                payload = full_raw if kind == "full" else _canonical(policy)
                _require(len(payload) <= MAX_POLICY_BYTES, "Policy exceeds byte cap")
                _atomic_exclusive(policies_dir / filename, payload, created)
                saved = _read_capped(policies_dir / filename, MAX_POLICY_BYTES,
                                     "Published tail policy")
                _require(saved == payload, "Published policy bytes differ")
                _guard(source_map, head)
                saved_replay_started = time.perf_counter()
                reread_metrics, reread_diffs, reread_oracle = _replay(
                    json.loads(saved), backend, kind, case)
                saved_replay_seconds = time.perf_counter() - saved_replay_started
                _guard(source_map, head)
                _require(_metric_close({k: reread_metrics[k] for k in METRICS}, metrics) and
                         reread_diffs == diffs, "Saved replay differs from in-memory replay")
                results.append({
                    "backend": backend, "profile": kind,
                    "iterations": DISCARD if kind == "prefix" else TOTAL,
                    "source_requested_iterations": TOTAL, "algorithm": ALGORITHM,
                    "target_exploitability": None, "threshold": THRESHOLD,
                    "threshold_met": metrics["nash_conv"] <= THRESHOLD,
                    "metrics": metrics, "independent_metrics": metrics,
                    "scalar_differences": diffs,
                    "worlds": oracle["worlds"], "compatible_pairs": oracle["compatible_pair_count"],
                    "information_rows": oracle["checked_information_sets"],
                    "public_decisions": census.decisions,
                    "independent_public_decisions": oracle["public_node_count"],
                    "public_states": census.public_nodes,
                    "work_charge": expected_work(backend, TOTAL, census),
                    "work_limit": fixture.REFERENCE_WORK_CAP,
                    "iterations_completed": TOTAL,
                    "capture_callback_iterations": capture_meta["callback_iterations"],
                    "capture_trainer_calls": capture_meta["trainer_calls"],
                    "final_snapshot_matches_returned_profile": capture_meta["final_snapshot_exactly_matches_returned_profile"],
                    "full_call_seconds_uncontrolled": capture_meta["complete_call_with_observations_seconds"],
                    "full_policy_json_seconds": full_json_seconds,
                    "conversion_seconds": conversion_seconds if kind == "tail" else 0.0,
                    "independent_replay_seconds": profile_replay_seconds,
                    "saved_policy_replay_seconds": saved_replay_seconds,
                    "capture_validation_replay_seconds": capture_meta["independent_replay_seconds"],
                    "policy_file": filename, "policy_sha256": _sha(saved),
                    "independent_replay": True,
                    "actual_metadata": _profile_metadata(full),
                    "ledger": _json_fraction(ledger) if kind == "tail" else None,
                })
                print(f"DONE backend={backend} profile={kind} "
                      f"nash_conv={metrics['nash_conv']:.12g} "
                      f"target_met={metrics['nash_conv'] <= THRESHOLD}", flush=True)
        _guard(source_map, head)
        report = {
            "schema_version": SCHEMA_VERSION, "benchmark_id": BENCHMARK_ID,
            "generation_capture_calls": 2,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "baseline_source_commit": BASELINE_SOURCE_COMMIT,
            "generation_git_commit": head,
            "current_head_at_generation": head,
            "python": platform.python_version(), "platform": platform.platform(),
            "source_sha256": source_map,
            "baseline_report_sha256": baseline["report_sha256"],
            "reference_sha256": _sha(_read_capped(
                REFERENCE_PATH, reference.MAX_REPORT_BYTES, "Accepted reference")),
            "fixture": case, "census": fixture.to_jsonable(census),
            "methodology": _methodology(), "results": results,
        }
        report_bytes = _canonical(report)
        _require(len(report_bytes) <= MAX_REPORT_BYTES, "Report exceeds byte cap")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        fd, staged_name = tempfile.mkstemp(prefix="." + report_path.name + ".",
                                           suffix=".candidate", dir=report_path.parent)
        staged = Path(staged_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(report_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            _verify_saved(staged, policies_dir, baseline=baseline,
                          expected_sources=source_map, expected_head=head)
            _atomic_exclusive(report_path, report_bytes, created)
        finally:
            staged.unlink(missing_ok=True)
        verified = _verify_saved(report_path, policies_dir, baseline=baseline,
                                 expected_sources=source_map, expected_head=head)
        return verified
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--verify", action="store_true")
    group.add_argument("--generate", action="store_true")
    args = parser.parse_args(argv)
    result = (_verify_saved(REPORT, POLICIES_DIR) if args.verify else
              generate(allow_training=True))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
