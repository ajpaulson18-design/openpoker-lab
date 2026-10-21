"""Single fixed T6000/D2000 compact-class TURN experiment."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
import uuid
from fractions import Fraction
from pathlib import Path

from scripts import turn_three_hand_classes as class_audit
from scripts import turn_three_hand_exact_oracle as exact_oracle
from scripts import turn_three_hand_reference as reference
from scripts import turn_river_validation as rules

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "turn-class-tail-T6000-v1"
REPORT_NAME = SCHEMA + ".json"
POLICY_NAME = SCHEMA + "-policy.json"
ATTEMPT_ROOT = "work/turn_class_tail_T6000_attempts"
CLAIM_NAME = "run-claim.json"
ITERATIONS = 6000
DISCARD = 2000
RESOURCE_MODEL = "turn-seven-class-vector-v1"
AVERAGED_SWEEPS = 4000
AVERAGE_WEIGHT_SUM = 16_002_000
REGRET_PASSES = 12_000
AVERAGE_PASSES = 4_000
TOTAL_PASSES = 16_000
BYTE_CAP = 4_000_000
TARGET = Fraction(1, 1000)
VERIFICATION_SCOPE = (
    "Policy mathematics, fixed configuration/admission metadata and committed "
    "source/input identities are independently checked. Runtime, host, call-count "
    "and observed internal ledger entries are producer-reported observations.")
METRICS = tuple(reference.METRICS)
FIXTURE = copy.deepcopy(reference.FIXTURE)
OLD_REPORT = "benchmarks/results/turn-three-hand-direct-tail-v1.json"
OLD_POLICY = "benchmarks/results/turn-three-hand-direct-tail-v1-policy.json"
OLD_REPORT_SHA256 = "1827e2163b897c5a1c5274e4a300ee365d8234fdf38235647772d63300953a7a"
OLD_POLICY_SHA256 = "c02e37dedf886f586e8b0ce9a98e86d079a32322d6e2ba4eb5beaab127dd6789"
OLD_REPORT_BYTES = 33_671
OLD_POLICY_BYTES = 2_541_067
GIT_RE = re.compile(r"^[0-9a-f]{40}$")

# This list must stay identical to the independent verifier's required set.
# Every tracked pokerlab module is added from the frozen commit inventory.
REQUIRED_SOURCES = frozenset({
    ".gitattributes",
    ".gitignore",
    "scripts/benchmark_turn_class_tail.py",
    "scripts/verify_turn_class_tail_experiment.py",
    "scripts/turn_three_hand_reference.py",
    "scripts/turn_three_hand_exact_oracle.py",
    "scripts/turn_three_hand_classes.py",
    "scripts/turn_rational_certificate.py",
    "scripts/turn_river_validation.py",
    "scripts/preflop_validation.py",
    "tests/test_benchmark_turn_class_tail.py",
    "tests/test_verify_turn_class_tail_experiment.py",
    "tests/test_turn_class_adversarial.py",
    "tests/test_turn_class_exact_updates.py",
    "tests/test_turn_class_resource_source.py",
    "tests/test_turn_class_tail_adapter.py",
    "tests/test_turn_class_vector_budget.py",
    "tests/test_turn_three_hand_classes.py",
    "tests/test_turn_three_hand_physical.py",
    "docs/turn-class-tail-T6000-experiment-spec.md",
    OLD_REPORT,
    OLD_POLICY,
})


def need(condition, message):
    if not condition:
        raise ValueError(message)


def jsonable(value):
    if isinstance(value, Fraction):
        return str(value)
    if type(value) is dict:
        if all(type(key) is str for key in value):
            return {key: jsonable(item) for key, item in value.items()}
        entries = [
            {"key": jsonable(key), "value": jsonable(item)}
            for key, item in sorted(
                value.items(), key=lambda pair: canonical(pair[0]))
        ]
        return {"key_value_entries": entries}
    if type(value) in (tuple, list):
        return [jsonable(item) for item in value]
    if type(value) is float:
        need(math.isfinite(value), "Nonfinite JSON float")
    if type(value) in (str, int, float, bool) or value is None:
        return value
    raise TypeError("Unsupported JSON value: " + type(value).__name__)


def canonical(value):
    encoded = json.dumps(
        jsonable(value), sort_keys=True, indent=2,
        ensure_ascii=False, allow_nan=False)
    return (encoded + "\n").encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def targets(root=ROOT):
    folder = root / "benchmarks" / "results"
    return {
        "report": folder / REPORT_NAME,
        "policy": folder / POLICY_NAME,
    }


def _git(root, *arguments):
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise subprocess.CalledProcessError(
            result.returncode,
            ["git", *arguments],
            output=result.stdout,
            stderr=result.stderr,
        )
    return result.stdout.decode("ascii").strip()

def _source_names(root):
    paths = _git(
        root, "ls-tree", "-r", "--name-only", "HEAD", "--", "pokerlab"
    ).splitlines()
    modules = {
        name for name in paths
        if re.fullmatch(r"pokerlab/[A-Za-z_][A-Za-z_0-9]*\.py", name)
    }
    return tuple(sorted(modules | set(REQUIRED_SOURCES)))


def _source_bytes(root, name):
    path = root / name
    if not path.is_file():
        raise FileNotFoundError(path)
    raw = path.read_bytes()
    if path.suffix == ".py":
        raw = raw.replace(b"\r\n", b"\n")
    return raw


def _committed(root, head, pins):
    for name, digest in pins.items():
        raw = subprocess.check_output(
            ["git", "show", f"{head}:{name}"], cwd=root)
        if name.endswith(".py"):
            raw = raw.replace(b"\r\n", b"\n")
        need(sha(raw) == digest,
             "Source is not committed at frozen HEAD: " + name)


def _freeze(root):
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", ATTEMPT_ROOT + "/"],
        cwd=root, check=False)
    need(ignored.returncode == 0,
         "Attempt directory must be Git-ignored before the sole API call")
    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    need(not status, "Generation requires a clean tracked and untracked worktree")
    head = _git(root, "rev-parse", "HEAD")
    need(bool(GIT_RE.fullmatch(head)), "Malformed Git HEAD")
    refs = _git(root, "for-each-ref", "--contains", head, "--format=%(refname)")
    need(bool(refs), "Frozen HEAD must be reachable from a local ref")
    names = _source_names(root)
    pins = {name: sha(_source_bytes(root, name)) for name in names}
    _committed(root, head, pins)
    return head, names, pins


def _guard(root, head, names, pins, allowed=()):
    need(_git(root, "rev-parse", "HEAD") == head, "Git HEAD drift")
    allowed_names = {
        Path(path).resolve().relative_to(root.resolve()).as_posix()
        for path in allowed
    }
    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    for line in status.splitlines():
        need(line.startswith("?? ") and line[3:] in allowed_names,
             "Unowned worktree change during experiment: " + line)
    need(_source_names(root) == names, "Frozen source inventory changed")
    working = {name: sha(_source_bytes(root, name)) for name in names}
    need(working == pins, "Frozen source bytes changed")
    _committed(root, head, pins)


def _read_bounded(path, cap=BYTE_CAP):
    size_before = path.stat().st_size
    need(0 <= size_before <= cap, "Artifact exceeds fixed byte cap")
    with path.open("rb") as stream:
        raw = stream.read(cap + 1)
    need(len(raw) == size_before and len(raw) <= cap,
         "Artifact changed during bounded read")
    return raw


def _exclusive_write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    created = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            current = path.stat()
            if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                path.unlink()
        except FileNotFoundError:
            pass
        raise
    return path


def _refuse_prior_run(root):
    folder = root / ATTEMPT_ROOT
    claim = folder / CLAIM_NAME
    if claim.exists() or (folder.exists() and any(folder.iterdir())):
        raise FileExistsError("A prior T6000 claim or attempt already exists")


def _claim_run(root, head, pins):
    base = root / ATTEMPT_ROOT
    base.mkdir(parents=True, exist_ok=True)
    _refuse_prior_run(root)
    run_id = uuid.uuid4().hex
    claim = base / CLAIM_NAME
    attempt = base / run_id
    claim_record = {
        "schema": SCHEMA + "-run-claim-v1",
        "run_id": run_id,
        "generation_head": head,
        "source_sha256": pins,
        "request": {
            "iterations": ITERATIONS,
            "discard": DISCARD,
            "resource_model": RESOURCE_MODEL,
            "averaged_sweeps": AVERAGED_SWEEPS,
            "average_weight_sum": AVERAGE_WEIGHT_SUM,
            "regret_passes": REGRET_PASSES,
            "average_passes": AVERAGE_PASSES,
            "total_passes": TOTAL_PASSES,
        },
    }
    _exclusive_write(claim, canonical(claim_record))
    attempt.mkdir(exist_ok=False)
    return attempt


def _save_attempt(attempt, head, pins, phase, payload, raw, elapsed):
    if raw is None:
        raw = (repr(payload) + "\n").encode(
            "utf-8", errors="backslashreplace")
        policy_name = "returned-policy-repr.txt"
    else:
        policy_name = "returned-policy.json"
    _exclusive_write(attempt / policy_name, raw)
    record = {
        "schema": SCHEMA + "-attempt-v1",
        "generation_head": head,
        "source_sha256": pins,
        "phase": phase,
        "returned_policy_file": policy_name,
        "returned_policy_sha256": sha(raw),
        "returned_policy_bytes": len(raw),
        "complete_api_json_seconds": elapsed,
        "error": None,
    }
    _exclusive_write(attempt / "attempt.json", canonical(record))


def _save_failure(attempt, head, pins, phase, payload, raw, elapsed, error):
    policy_name = None
    digest = None
    size = None
    if raw is not None:
        policy_name = "returned-policy.json"
        returned_path = attempt / policy_name
        if returned_path.exists():
            need(_read_bounded(returned_path, cap=max(len(raw), 1)) == raw,
                 "Preserved returned policy bytes differ from canonical response")
        else:
            _exclusive_write(returned_path, raw)
        digest = sha(raw)
        size = len(raw)
    elif payload is not None:
        fallback = (repr(payload) + "\n").encode(
            "utf-8", errors="backslashreplace")
        policy_name = "returned-policy-repr.txt"
        digest = sha(fallback)
        size = len(fallback)
        if not (attempt / policy_name).exists():
            _exclusive_write(attempt / policy_name, fallback)
    record = {
        "schema": SCHEMA + "-failure-v1",
        "generation_head": head,
        "source_sha256": pins,
        "phase": phase,
        "returned_policy_file": policy_name,
        "returned_policy_sha256": digest,
        "returned_policy_bytes": size,
        "complete_api_json_seconds": elapsed,
        "error": type(error).__name__ + ": " + str(error),
    }
    _exclusive_write(attempt / "failure-receipt.json", canonical(record))


def _fraction(value):
    if type(value) is Fraction:
        return value
    if type(value) is str:
        result = Fraction(value)
        need(str(result) == value, "Noncanonical exact metric")
        return result
    raise ValueError("Exact metric must be a Fraction or canonical string")


def _metrics(audit):
    values = audit.get("full_physical_exact_metrics")
    need(type(values) is dict and set(values) == set(METRICS),
         "Full physical exact metric set differs")
    return {name: _fraction(values[name]) for name in METRICS}


def _numeric_gate(payload, audit):
    numeric = rules.replay_policy(
        payload, FIXTURE["oop"], FIXTURE["ip"],
        board=FIXTURE["board"], config=FIXTURE["config"])
    exact = _metrics(audit)
    differences = {}
    for name in METRICS:
        observed = numeric.get(name)
        api_value = payload.get(name)
        need(type(observed) in (int, float) and type(observed) is not bool
             and math.isfinite(observed),
             "Invalid independent numeric metric: " + name)
        need(type(api_value) in (int, float) and type(api_value) is not bool
             and math.isfinite(api_value) and abs(float(api_value) - observed) <= 1e-9,
             "API metric differs from independent numeric replay: " + name)
        difference = float(exact[name]) - float(observed)
        need(math.isfinite(difference) and abs(difference) <= 1e-9,
             "Exact/numeric metric disagreement: " + name)
        differences[name] = difference
    need(audit.get("training_calls") == 0,
         "Mathematical audit must not train")
    need(audit.get("max_full_numeric_difference", math.inf) <= 1e-9,
         "Class audit full-physical numeric gate failed")
    return numeric, differences


def _audit_old_baseline(root, model):
    report_path = root / OLD_REPORT
    policy_path = root / OLD_POLICY
    report_raw = _read_bounded(report_path)
    policy_raw = _read_bounded(policy_path)
    need(len(report_raw) == OLD_REPORT_BYTES
         and sha(report_raw) == OLD_REPORT_SHA256,
         "Frozen T750 report identity changed")
    need(len(policy_raw) == OLD_POLICY_BYTES
         and sha(policy_raw) == OLD_POLICY_SHA256,
         "Frozen T750 policy identity changed")
    report = json.loads(report_raw)
    payload = json.loads(policy_raw)
    need(report.get("policy_sha256") == OLD_POLICY_SHA256
         and report.get("iterations") == 750 and report.get("discard") == 250,
         "Frozen T750 report metadata differs")
    exact_result = exact_oracle.audit_policy(payload, model)
    exact = exact_result["metrics"]
    numeric = rules.replay_policy(
        payload, FIXTURE["oop"], FIXTURE["ip"],
        board=FIXTURE["board"], config=FIXTURE["config"])
    for name in METRICS:
        need(type(numeric.get(name)) in (int, float)
             and math.isfinite(numeric[name])
             and abs(float(exact[name]) - numeric[name]) <= 1e-9,
             "T750 exact/numeric replay differs: " + name)
    exact_saved = {name: str(exact[name]) for name in METRICS}
    need(report.get("results", {}).get("exact_metrics_fractions") == exact_saved,
         "T750 exact replay differs from its frozen report")
    need(exact["nash_conv"] > TARGET,
         "T750 is no longer independently a target miss")
    return {
        "report_file": OLD_REPORT,
        "report_sha256": sha(report_raw),
        "policy_file": OLD_POLICY,
        "policy_sha256": sha(policy_raw),
        "exact_metrics_fractions": exact_saved,
        "threshold_miss": True,
        "numeric_metrics": numeric,
        "exact_counters": jsonable(exact_result["counters"]),
    }


def _validate_payload(payload):
    need(type(payload) is dict
         and payload.get("resource_model") == RESOURCE_MODEL,
         "Wrong explicit resource model or result type")
    need(payload.get("algorithm") == "cfrplus"
         and payload.get("iterations") == ITERATIONS
         and payload.get("requested_iterations") == ITERATIONS
         and payload.get("discard") == DISCARD,
         "Fixed training schedule differs")
    schedule = {
        "averaged_sweeps": AVERAGED_SWEEPS,
        "average_weight_sum": AVERAGE_WEIGHT_SUM,
        "requested_regret_passes": REGRET_PASSES,
        "requested_average_passes": AVERAGE_PASSES,
        "requested_total_traversal_passes": TOTAL_PASSES,
    }
    for name, expected in schedule.items():
        need(payload.get(name) == expected,
             "Fixed training schedule differs: " + name)
    strategy = payload.get("strategy")
    need(type(strategy) is list and len(strategy) == 3_606,
         "Complete physical policy row census differs")
    for name in METRICS:
        value = payload.get(name)
        need(type(value) in (int, float) and type(value) is not bool
             and math.isfinite(value),
             "Returned diagnostic is not finite numeric data: " + name)
    usage = payload.get("resource_usage")
    need(type(usage) is dict, "Resource usage metadata is missing")
    expected_usage = {
        "physical_world_iterations": 2_376_000,
        "candidate_pair_iterations": 54_000,
        "compact_world_proxy": 25_920_000,
        "compact_dense_proxy": 24_628_104,
        "trainer_vector_work": 450_960_288,
        "complete_vector_work": 452_960_288,
    }
    for name, expected in expected_usage.items():
        need(usage.get(name) == expected,
             "Resource admission differs: " + name)


def _build_report(head, pins, payload, audit, numeric, differences,
                  old_baseline, policy_raw, api_seconds, math_seconds):
    metrics = _metrics(audit)
    lower = -metrics["ip_best_response_value"]
    upper = metrics["oop_best_response_value"]
    need(lower <= metrics["value_oop"] <= upper,
         "Profile value is outside its legal response interval")
    old_metrics = {
        name: _fraction(value)
        for name, value in old_baseline["exact_metrics_fractions"].items()
    }
    overlap_lower = max(lower, -old_metrics["ip_best_response_value"])
    overlap_upper = min(upper, old_metrics["oop_best_response_value"])
    need(overlap_lower <= overlap_upper,
         "Old and new legal response intervals do not overlap")
    target_met = metrics["nash_conv"] <= TARGET
    return {
        "schema": SCHEMA,
        "schema_version": 1,
        "generation_head": head,
        "training_source_git_commit": head,
        "source_sha256": pins,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "fixture_id": FIXTURE["id"],
        "fixture": FIXTURE,
        "request": {
            "iterations": ITERATIONS,
            "discard": DISCARD,
            "resource_model": RESOURCE_MODEL,
            "averaged_sweeps": AVERAGED_SWEEPS,
            "average_weight_sum": AVERAGE_WEIGHT_SUM,
            "regret_passes": REGRET_PASSES,
            "average_passes": AVERAGE_PASSES,
            "total_passes": TOTAL_PASSES,
        },
        "completed_training_calls": 1,
        "policy_file": POLICY_NAME,
        "policy_sha256": sha(policy_raw),
        "policy_bytes": len(policy_raw),
        "numeric_oracle_metrics": numeric,
        "exact_numeric_differences": differences,
        "class_audit": jsonable(audit),
        "exact_metrics_fractions": {
            name: str(value) for name, value in metrics.items()
        },
        "exact_value_interval": {
            "lower": str(lower), "upper": str(upper),
        },
        "target_nash_conv_fraction": str(TARGET),
        "target_met": target_met,
        "threshold_miss": not target_met,
        "old_baseline": old_baseline,
        "complete_api_json_seconds": api_seconds,
        "independent_math_audit_seconds": math_seconds,
        "scope": (
            "One fixed 396-world configured three-hand TURN CFR+ tail policy "
            "trained through seven exact public-river classes; exact evidence "
            "is for the serialized binary64 policy, with no assumed "
            "equilibrium value or general convergence claim."
        ),
        "verification_scope": VERIFICATION_SCOPE,
    }


def _identity(path):
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size


def _remove_owned(path, identity):
    try:
        if _identity(path) == identity:
            path.unlink()
    except FileNotFoundError:
        pass


def _publish(root, report_raw, policy_raw, head, names, pins):
    fixed = targets(root)
    if any(path.exists() for path in fixed.values()):
        raise FileExistsError("Refusing to overwrite fixed experiment outputs")
    stage = fixed["report"].with_name(
        "." + REPORT_NAME + "." + uuid.uuid4().hex + ".stage")
    owned = {}
    try:
        _exclusive_write(fixed["policy"], policy_raw)
        owned[fixed["policy"]] = _identity(fixed["policy"])
        _exclusive_write(stage, report_raw)
        owned[stage] = _identity(stage)
        _guard(root, head, names, pins, allowed=(stage, fixed["policy"]))
        need(_read_bounded(stage) == report_raw
             and _read_bounded(fixed["policy"]) == policy_raw,
             "Staged bundle bytes changed before acceptance")
        checker = __import__(
            "scripts.verify_turn_class_tail_experiment",
            fromlist=["verify_saved_artifact"])
        checker.verify_saved_artifact(path=stage, root=root)
        _guard(root, head, names, pins, allowed=(stage, fixed["policy"]))
        need(_identity(stage) == owned[stage]
             and _identity(fixed["policy"]) == owned[fixed["policy"]]
             and _read_bounded(stage) == report_raw
             and _read_bounded(fixed["policy"]) == policy_raw,
             "Staged bundle changed during independent acceptance")
        need(not fixed["report"].exists(),
             "Fixed report appeared while the stage was being checked")
        # Hard-link promotion is atomic and refuses an existing destination;
        # unlike os.replace it cannot clobber a report created in the race window.
        os.link(stage, fixed["report"])
        owned[fixed["report"]] = _identity(fixed["report"])
        _remove_owned(stage, owned.pop(stage))
        checker.verify_saved_artifact(path=fixed["report"], root=root)
        _guard(root, head, names, pins,
               allowed=(fixed["report"], fixed["policy"]))
        need(_identity(fixed["report"]) == owned[fixed["report"]]
             and _identity(fixed["policy"]) == owned[fixed["policy"]]
             and _read_bounded(fixed["report"]) == report_raw
             and _read_bounded(fixed["policy"]) == policy_raw,
             "Published bundle changed during independent acceptance")
    except BaseException:
        for path, identity in reversed(list(owned.items())):
            _remove_owned(path, identity)
        raise
    finally:
        if stage in owned:
            _remove_owned(stage, owned[stage])


def generate(root=ROOT):
    fixed = targets(root)
    if any(path.exists() for path in fixed.values()):
        raise FileExistsError("Refusing to repeat or overwrite fixed outputs")
    _refuse_prior_run(root)
    head, names, pins = _freeze(root)
    _guard(root, head, names, pins)

    game = reference.model()
    reference.validate_model(game)
    old_started = time.perf_counter()
    old_baseline = _audit_old_baseline(root, game)
    old_math_seconds = time.perf_counter() - old_started
    _guard(root, head, names, pins)

    # A durable claim is committed before the solver module is imported or
    # the single production call is dispatched. The claim is never removed.
    attempt = _claim_run(root, head, pins)
    payload = None
    policy_raw = None
    call_started = None
    phase = "claim-created-before-import"
    try:
        _guard(root, head, names, pins)
        from pokerlab.turn_class_tail_adapter import solve_turn_class_tail
        _guard(root, head, names, pins)

        phase = "single-api-call"
        call_started = time.perf_counter()
        payload = solve_turn_class_tail(
            iterations=ITERATIONS,
            discard=DISCARD,
            resource_model=RESOURCE_MODEL,
        )
        phase = "canonical-policy-serialization"
        policy_raw = canonical(payload)
        api_seconds = time.perf_counter() - call_started
        _save_attempt(
            attempt, head, pins, phase, payload, policy_raw, api_seconds)
        need(len(policy_raw) <= BYTE_CAP,
             "Returned complete policy exceeds four-megabyte cap")
        _guard(root, head, names, pins)

        phase = "schedule-and-metadata-validation"
        _validate_payload(payload)
        math_started = time.perf_counter()
        game = reference.model()
        reference.validate_model(game)
        compact_model = class_audit.build_model(game)
        audit = class_audit.audit_policy(
            payload, compact_model, chance_grouping="both")
        numeric, differences = _numeric_gate(payload, audit)
        math_seconds = old_math_seconds + time.perf_counter() - math_started
        _guard(root, head, names, pins)

        report = _build_report(
            head, pins, payload, audit, numeric, differences,
            old_baseline, policy_raw, api_seconds, math_seconds)
        report_raw = canonical(report)
        need(len(report_raw) <= BYTE_CAP,
             "Report exceeds fixed four-megabyte cap")
        _guard(root, head, names, pins)
        _publish(root, report_raw, policy_raw, head, names, pins)
        print(
            "ACCEPTED attempt=" + str(attempt)
            + " nash_conv=" + report["exact_metrics_fractions"]["nash_conv"]
            + " target_met=" + str(report["target_met"]),
            flush=True,
        )
        return report
    except BaseException as error:
        elapsed = (None if call_started is None
                   else time.perf_counter() - call_started)
        try:
            _save_failure(
                attempt, head, pins, phase, payload, policy_raw, elapsed, error)
        except BaseException as preservation_error:
            print(
                "Could not preserve one-shot attempt context: "
                + repr(preservation_error),
                file=sys.stderr,
            )
        raise


def verify(root=ROOT):
    checker = __import__(
        "scripts.verify_turn_class_tail_experiment",
        fromlist=["verify_saved_artifact"])
    return checker.verify_saved_artifact(path=targets(root)["report"], root=root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true")
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    report = generate() if args.generate else verify()
    sys.stdout.write(canonical(report).decode("utf-8"))


if __name__ == "__main__":
    main()
