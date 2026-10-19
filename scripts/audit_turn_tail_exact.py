"""Exact audit of saved numeric profiles from the fixed raised-turn tail study.

This research-only verifier performs no training. It certifies explicitly
normalized binary64 policies only when the fixed quotient auditor accepts them.
An empty numeric-report digest deliberately disables generation until the
separate full-budget numeric experiment has been completed and pinned.
"""
import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

from scripts import audit_full_deck_raised_exact as quotient


ROOT = quotient.ROOT
BACKENDS = ("materialized", "matrix-free")
WINDOW = ("prefix", "full", "tail")
DISCARD, TOTAL = 1000, 1500
THRESHOLD = 0.001
METRICS = quotient.reference.METRICS
FIXED_WORK_LIMIT = 30_000_000
REFERENCE_PUBLIC_TREE_SHA256 = "70d87064c6d7048b75784b6623a2dc6249f57ac61384a27d1724c3d53563bd61"
NUMERIC_REPORT = ROOT / "benchmarks/results/full-deck-raised-turn-tail-v1.json"
NUMERIC_POLICIES = ROOT / "benchmarks/results/full-deck-raised-turn-tail-policies-v1"
REPORT = ROOT / "benchmarks/results/full-deck-raised-turn-tail-exact-v1.json"
REFERENCE = quotient.reference.REPORT
NUMERIC_REPORT_SHA256 = "9e51cbcf9f031f371806be06e6a23589e0dd27d5e3ffffcf36fc545eed5d6998"
REFERENCE_SHA256 = quotient.REFERENCE_SHA256
MAX_NUMERIC_REPORT_BYTES = 8_000_000
MAX_NUMERIC_POLICY_BYTES = 2_000_000
MAX_REPORT_BYTES = 8_000_000
SCHEMA_VERSION = 1
BENCHMARK_ID = "full-deck-raised-turn-tail-exact-v1"
THRESHOLD_FRACTION = Fraction(1, 1000)
NUMERIC_TOLERANCE = 1e-9
OBSERVATION_TOLERANCE = 1e-12

# The exact certificate depends on the original quotient proof and its sources,
# plus the numeric tail production path whose immutable artifact is audited.
SOURCES = tuple(sorted(set(quotient.SOURCES) | {
    "scripts/benchmark_turn_tail.py", "scripts/turn_tail_capture.py",
    "scripts/river_tail_realization.py", "scripts/audit_turn_tail_exact.py",
    "tests/test_turn_tail_exact.py",
}))


def _policy_name(backend, profile):
    return f"full-deck-raised-turn-tail-v1-{backend}-{profile}.json"


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _valid_sha(value):
    return (type(value) is str and len(value) == 64 and
            all(char in "0123456789abcdef" for char in value))


def _head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                   text=True).strip()


def fingerprints():
    return {path: _sha((ROOT / path).read_bytes().replace(b"\r\n", b"\n"))
            for path in SOURCES}


def _guard(source_map, head):
    _require(fingerprints() == source_map, "Exact tail audit source changed")
    _require(_head() == head, "Exact tail audit HEAD changed")


def _read_capped(path, cap, label):
    path = Path(path)
    _require(path.stat().st_size <= cap, label + " exceeds pre-read byte cap")
    raw = path.read_bytes()
    _require(len(raw) <= cap, label + " exceeds byte cap")
    return raw


def _load_inputs(report_path, policies_dir, report_sha256):
    _require(_valid_sha(report_sha256),
             "Numeric tail report SHA256 pin is not configured")
    report_raw = _read_capped(report_path, MAX_NUMERIC_REPORT_BYTES,
                              "Numeric tail report")
    _require(_sha(report_raw) == report_sha256,
             "Pinned numeric tail report SHA256 differs")
    _require(b"\r" not in report_raw, "Numeric tail report must use canonical LF")
    report = json.loads(report_raw)
    _require(_canonical(report) == report_raw and type(report) is dict and
             report.get("benchmark_id") == "full-deck-raised-turn-tail-v1" and
             type(report.get("schema_version")) is int and report["schema_version"] == 1 and
             type(report.get("generation_git_commit")) is str and
             len(report["generation_git_commit"]) == 40 and
             all(char in "0123456789abcdef" for char in report["generation_git_commit"]) and
             type(report.get("generation_capture_calls")) is int and
             report["generation_capture_calls"] == 2,
             "Unsupported or noncanonical numeric tail report")
    rows = report.get("results")
    expected_order = [(backend, profile) for backend in BACKENDS for profile in WINDOW]
    _require(type(rows) is list and len(rows) == 6 and
             [(row.get("backend"), row.get("profile")) for row in rows
              if type(row) is dict] == expected_order,
             "Numeric report does not contain the fixed six-profile grid")
    inputs = {"report_path": Path(report_path), "policies_dir": Path(policies_dir),
              "report_raw": report_raw, "report": report,
              "report_sha256": report_sha256, "policies": {}, "rows": {}}
    work_by_backend = {}
    for row in rows:
        backend, profile = row["backend"], row["profile"]
        filename = _policy_name(backend, profile)
        _require(row.get("policy_file") == filename and _valid_sha(row.get("policy_sha256")),
                 "Numeric policy identity or SHA256 is invalid")
        path = Path(policies_dir) / filename
        raw = _read_capped(path, MAX_NUMERIC_POLICY_BYTES, "Numeric tail policy")
        _require(_sha(raw) == row["policy_sha256"], "Numeric policy SHA256 differs")
        _require(b"\r" not in raw, "Numeric tail policy must use canonical LF")
        policy = json.loads(raw)
        _require(_canonical(policy) == raw and type(policy) is dict,
                 "Numeric tail policy is noncanonical")
        _validate_profile_row(row, policy, backend, profile)
        work = row.get("work_charge")
        _require(type(work) is int and 0 < work <= FIXED_WORK_LIMIT and
                 type(row.get("work_limit")) is int and
                 row["work_limit"] == FIXED_WORK_LIMIT,
                 "Numeric profile work admission metadata differs")
        if backend in work_by_backend:
            _require(work_by_backend[backend] == work,
                     "Profiles of one backend have different full-request work charges")
        else:
            work_by_backend[backend] = work
        inputs["policies"][(backend, profile)] = raw
        inputs["rows"][(backend, profile)] = row
    raw_reference = _read_capped(REFERENCE, quotient.reference.MAX_REPORT_BYTES,
                                 "Accepted physical/tree reference")
    _require(_sha(raw_reference) == REFERENCE_SHA256,
             "Accepted physical/tree reference SHA256 differs")
    checked = quotient.reference.verify_saved_artifact(REFERENCE)
    _require(checked["reference"]["public_tree_sha256"] ==
             REFERENCE_PUBLIC_TREE_SHA256,
             "Accepted physical/tree public-tree identity differs")
    inputs["reference_raw"] = raw_reference
    return inputs


def _validate_profile_row(row, policy, backend, profile):
    _require(row.get("algorithm") == "cfrplus" and
             row.get("target_exploitability") is None and
             type(row.get("threshold")) is float and row["threshold"] == THRESHOLD and
             type(row.get("iterations_completed")) is int and
             row["iterations_completed"] == TOTAL and
             row.get("capture_callback_iterations") == [DISCARD, TOTAL] and
             type(row.get("capture_trainer_calls")) is int and
             row["capture_trainer_calls"] == 1 and
             row.get("final_snapshot_matches_returned_profile") is True,
             "Numeric profile does not record the fixed same-run CFR+ experiment")
    expected_iterations = DISCARD if profile == "prefix" else TOTAL
    expected_window = ([1, DISCARD] if profile == "prefix" else
                       [DISCARD + 1, TOTAL] if profile == "tail" else None)
    _require(type(row.get("iterations")) is int and row["iterations"] == expected_iterations and
             type(row.get("source_requested_iterations")) is int and
             row["source_requested_iterations"] == TOTAL and
             type(row.get("work_charge")) is int and
             type(row.get("work_limit")) is int and
             row["work_limit"] == FIXED_WORK_LIMIT and
             row.get("worlds") == 176 and row.get("compatible_pairs") == 4 and
             row.get("information_rows") == 2404,
             "Numeric profile iteration provenance differs")
    if profile == "full":
        _require(policy.get("iterations") == TOTAL and
                 policy.get("algorithm") == "cfrplus" and
                 policy.get("solver_version") == "configured-postflop-v1" and
                 policy.get("strategy_schema") == "postflop-strategy-v1" and
                 policy.get("average_schedule") == "linear-post-sweep-own-reach" and
                 "research_profile" not in policy,
                 "Full policy is not the original complete production profile")
    else:
        schedule = "linear-prefix-own-reach" if profile == "prefix" else "linear-tail-own-realization"
        sweeps = DISCARD if profile == "prefix" else TOTAL - DISCARD
        _require(policy.get("research_profile") == profile and
                 policy.get("source_requested_iterations") == TOTAL and
                 policy.get("source_iteration_window") == expected_window and
                 policy.get("iterations") == (DISCARD if profile == "prefix" else TOTAL) and
                 policy.get("averaged_sweeps") == sweeps and
                 policy.get("average_schedule") == schedule and
                 type(policy.get("source_solver_version")) is str and
                 policy.get("solver_version") == "research-raised-turn-tail-v1",
                 "Derived policy window or solver provenance differs")
    if profile == "tail":
        _require(type(row.get("ledger")) is dict,
                 "Tail numeric report omits its exact reconstruction ledger")
    else:
        _require(row.get("ledger") is None,
                 "Only the tail profile may carry the reconstruction ledger")
    _require(row.get("backend") == backend and backend in BACKENDS,
             "Numeric profile backend differs")


def _json_exact(value):
    return quotient.fraction_json(value)


def _numeric_metrics_match(observed, expected):
    return (type(observed) is dict and set(observed) == set(METRICS) and
            all(type(observed[name]) in (int, float) and math.isfinite(observed[name]) and
                abs(observed[name] - expected[name]) <= NUMERIC_TOLERANCE
                for name in METRICS))


def _audit_profile(inputs, backend, profile, model):
    row = inputs["rows"][(backend, profile)]
    filename = row["policy_file"]
    result = json.loads(inputs["policies"][(backend, profile)])
    audited = quotient.audit_policy(result, model=model)
    numeric = audited["full_numeric_metrics"]
    _require(_numeric_metrics_match(row.get("metrics"), numeric) and
             _numeric_metrics_match(row.get("independent_metrics"), numeric),
             "Numeric report metrics differ from independent full-policy replay")
    _require(type(row.get("threshold_met")) is bool and
             row["threshold_met"] is (numeric["nash_conv"] <= THRESHOLD),
             "Numeric report target marker differs from full-policy replay")
    certificate = audited["certificate"]
    exact_metrics = certificate["metrics"]
    return {
        "backend": backend, "profile": profile, "policy_file": filename,
        "policy_sha256": row["policy_sha256"], "status": "accepted",
        "numeric_threshold_met": row["threshold_met"],
        "exact_threshold_fraction": str(THRESHOLD_FRACTION),
        "exact_threshold_met": exact_metrics["nash_conv"] <= THRESHOLD_FRACTION,
        "numeric_tail_ledger": deepcopy(row.get("ledger")),
        **_json_exact(audited),
    }


def _reconstruct(inputs, source_map, head):
    model = quotient.reference.model()
    accepted, rejected, profiles = 0, 0, []
    for backend in BACKENDS:
        for profile in WINDOW:
            _guard(source_map, head)
            _guard_inputs(inputs)
            try:
                item = _audit_profile(inputs, backend, profile, model)
            except (ValueError, TypeError, ZeroDivisionError) as exc:
                rejected += 1
                item = {
                    "backend": backend, "profile": profile,
                    "policy_file": inputs["rows"][(backend, profile)]["policy_file"],
                    "policy_sha256": inputs["rows"][(backend, profile)]["policy_sha256"],
                    "status": "rejected", "numeric_tail_ledger": deepcopy(
                        inputs["rows"][(backend, profile)].get("ledger")),
                    "rejection_type": type(exc).__name__, "rejection_reason": str(exc),
                    "exact_threshold_fraction": str(THRESHOLD_FRACTION),
                    "exact_threshold_met": None,
                }
            else:
                accepted += 1
            _guard(source_map, head)
            _guard_inputs(inputs)
            profiles.append(item)
    return {"profile_order": [[backend, profile] for backend, profile in
                              ((b, p) for b in BACKENDS for p in WINDOW)],
            "accepted_profiles": accepted, "rejected_profiles": rejected,
            "profiles": profiles,
            "scope": ("Exact explicitly normalized binary64 policy certificates for the "
                      "fixed full-deck raised turn game; rejected profiles have no certificate."),
            "numeric_report_sha256": inputs["report_sha256"],
            "numeric_generation_git_commit": inputs["report"].get("generation_git_commit")}


def _same_numeric_observations(actual, expected):
    if type(actual) is not dict or type(expected) is not dict or set(actual) != set(expected):
        return False
    return all(type(actual[name]) in (int, float) and math.isfinite(actual[name]) and
               abs(actual[name] - expected[name]) <= OBSERVATION_TOLERANCE
               for name in expected)


def _compare_reconstructions(saved, expected):
    if type(saved) is not dict or type(expected) is not dict or set(saved) != set(expected):
        return False
    for saved_row, expected_row in zip(saved["profiles"], expected["profiles"]):
        if type(saved_row) is not dict or type(expected_row) is not dict or \
                set(saved_row) != set(expected_row):
            return False
        for field in ("full_numeric_metrics", "exact_minus_numeric"):
            if saved_row.get("status") == "accepted":
                if not _same_numeric_observations(saved_row.pop(field), expected_row.pop(field)):
                    return False
        if _canonical(saved_row) != _canonical(expected_row):
            return False
    return _canonical(saved) == _canonical(expected)


def _input_guard(inputs):
    _require(_read_capped(inputs["report_path"], MAX_NUMERIC_REPORT_BYTES,
                          "Numeric tail report") == inputs["report_raw"],
             "Numeric tail report changed during exact audit")
    for identity, expected in inputs["policies"].items():
        backend, profile = identity
        path = inputs["policies_dir"] / _policy_name(backend, profile)
        _require(_read_capped(path, MAX_NUMERIC_POLICY_BYTES,
                              "Numeric tail policy") == expected,
                 "Numeric tail policy changed during exact audit")
    _require(_read_capped(REFERENCE, quotient.reference.MAX_REPORT_BYTES,
                          "Accepted physical/tree reference") == inputs["reference_raw"],
             "Accepted physical/tree reference changed during exact audit")


def _guard_inputs(inputs):
    _input_guard(inputs)


def _envelope(inputs, source_map, head, audit_result):
    return {"schema_version": SCHEMA_VERSION, "benchmark_id": BENCHMARK_ID,
            "generation_git_commit": head,
            "numeric_report_sha256": inputs["report_sha256"],
            "reference_sha256": REFERENCE_SHA256,
            "source_sha256": source_map, "audit": audit_result}


def verify_saved_artifact(path=REPORT, *, numeric_report_path=NUMERIC_REPORT,
                          policies_dir=NUMERIC_POLICIES,
                          numeric_report_sha256=NUMERIC_REPORT_SHA256):
    path = Path(path)
    raw = _read_capped(path, MAX_REPORT_BYTES, "Exact tail report")
    _require(b"\r" not in raw, "Exact tail report must use canonical LF")
    saved = json.loads(raw)
    _require(_canonical(saved) == raw and type(saved) is dict and
             set(saved) == {"schema_version", "benchmark_id", "generation_git_commit",
                            "numeric_report_sha256", "reference_sha256", "source_sha256", "audit"} and
             type(saved.get("schema_version")) is int and
             saved["schema_version"] == SCHEMA_VERSION and
             saved.get("benchmark_id") == BENCHMARK_ID,
             "Unsupported or noncanonical exact tail report")
    generation = saved.get("generation_git_commit")
    _require(type(generation) is str and len(generation) == 40 and
             all(char in "0123456789abcdef" for char in generation),
             "Historical exact generation HEAD is invalid")
    inputs = _load_inputs(numeric_report_path, policies_dir, numeric_report_sha256)
    source_map, head = fingerprints(), _head()
    _require(saved.get("source_sha256") == source_map,
             "Exact audit source fingerprints differ")
    _require(saved.get("numeric_report_sha256") == inputs["report_sha256"] and
             saved.get("reference_sha256") == REFERENCE_SHA256,
             "Exact audit input-artifact pins differ")
    _guard(source_map, head)
    _guard_inputs(inputs)
    reconstructed = _reconstruct(inputs, source_map, head)
    _require(_compare_reconstructions(deepcopy(saved["audit"]),
                                      deepcopy(reconstructed)),
             "Saved exact tail audit differs from reconstruction")
    _guard(source_map, head)
    _guard_inputs(inputs)
    _require(_read_capped(path, MAX_REPORT_BYTES, "Exact tail report") == raw,
             "Exact tail report changed during verification")
    return {"status": "VERIFIED_EXACT_TURN_TAIL", "training_calls": 0,
            "accepted_profiles": reconstructed["accepted_profiles"],
            "rejected_profiles": reconstructed["rejected_profiles"],
            "report_sha256": _sha(raw)}


def _atomic_exclusive(path, payload, created, verify_candidate):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".candidate",
                                dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _require(_read_capped(staged, MAX_REPORT_BYTES, "Staged exact report") == payload,
                 "Staged exact report bytes differ")
        verify_candidate(staged)
        try:
            os.link(staged, path)
            created.append(path)
        except FileExistsError as exc:
            raise ValueError("Refusing to replace an immutable exact report") from exc
    finally:
        staged.unlink(missing_ok=True)


def generate(path=REPORT, *, numeric_report_path=NUMERIC_REPORT,
             policies_dir=NUMERIC_POLICIES,
             numeric_report_sha256=NUMERIC_REPORT_SHA256):
    """Audit only pinned saved numeric policies; this function never trains."""
    path = Path(path)
    if path.exists():
        return verify_saved_artifact(path, numeric_report_path=numeric_report_path,
                                     policies_dir=policies_dir,
                                     numeric_report_sha256=numeric_report_sha256)
    inputs = _load_inputs(numeric_report_path, policies_dir, numeric_report_sha256)
    source_map, head = fingerprints(), _head()
    audit_result = _reconstruct(inputs, source_map, head)
    payload = _canonical(_envelope(inputs, source_map, head, audit_result))
    _require(len(payload) <= MAX_REPORT_BYTES, "Exact tail report exceeds byte cap")
    _guard(source_map, head)
    _guard_inputs(inputs)
    created = []
    try:
        _atomic_exclusive(
            path, payload, created,
            lambda candidate: verify_saved_artifact(
                candidate, numeric_report_path=numeric_report_path,
                policies_dir=policies_dir,
                numeric_report_sha256=numeric_report_sha256))
        return verify_saved_artifact(path, numeric_report_path=numeric_report_path,
                                     policies_dir=policies_dir,
                                     numeric_report_sha256=numeric_report_sha256)
    except BaseException:
        for owned in reversed(created):
            owned.unlink(missing_ok=True)
        raise


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--verify", action="store_true")
    group.add_argument("--generate", action="store_true")
    parser.add_argument("--numeric-report", type=Path, default=NUMERIC_REPORT)
    parser.add_argument("--numeric-policies", type=Path, default=NUMERIC_POLICIES)
    parser.add_argument("--output", type=Path, default=REPORT)
    args = parser.parse_args(argv)
    result = verify_saved_artifact(args.output, numeric_report_path=args.numeric_report,
                                   policies_dir=args.numeric_policies) if args.verify else \
        generate(args.output, numeric_report_path=args.numeric_report,
                 policies_dir=args.numeric_policies)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
