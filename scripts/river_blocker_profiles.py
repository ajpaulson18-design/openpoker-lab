"""Exact normalized response bounds for six blocker-correlated river profiles.

Verification independently replays complete saved policies and never trains.
Exactness concerns configured binary64 terminals and row-normalized policies.
"""
import argparse
import hashlib
import json
import math
import subprocess
import time
import uuid
from datetime import datetime, timezone
from fractions import Fraction as F
from pathlib import Path

from scripts import audit_river_rational_certificate as audit
from scripts import turn_rational_certificate as exact
from scripts import turn_river_validation as rules
from scripts.benchmark_turn_river_independent import solve
from scripts.river_blocker_fixture import FIXTURE
from scripts.river_sequence_form import _jsonable
from scripts.verify_river_blocker_equilibrium import verify_saved_artifact as verify_equilibrium

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "benchmarks/results/river-blocker-profiles-v1.json"
POLICY_DIR = ROOT / "benchmarks/results/river-blocker-policies-v1"
GRID = tuple((b, n) for b in ("materialized", "matrix-free") for n in (1000, 3000, 10000))
TARGET = F(1, 1000)
MAX_REPORT_BYTES, MAX_POLICY_BYTES = 2_000_000, 1_000_000
SCOPE = "Six fixed-iteration CFR+ profiles for one finite blocker-correlated configured river game."
LIMITATIONS = (
    "Exact response bounds apply to exactly row-normalized saved binary64 policies "
    "and configured binary64 terminal constants. Single-call solve-plus-JSON and "
    "replay timings establish no general speed, memory, RSS or unrestricted Hold'em claim."
)
REQUIRED = (
    "pokerlab/cards.py", "scripts/preflop_validation.py",
    "scripts/turn_river_validation.py", "scripts/turn_rational_certificate.py",
    "scripts/audit_river_rational_certificate.py",
    "scripts/benchmark_turn_river_independent.py", "scripts/river_sequence_form.py",
    "scripts/river_blocker_fixture.py", "scripts/river_blocker_equilibrium.py",
    "scripts/verify_river_blocker_equilibrium.py", "scripts/river_blocker_profiles.py",
    "tests/test_river_blocker_equilibrium.py", "tests/test_river_blocker_profiles.py",
    "benchmarks/results/river-blocker-model-v1.json",
    "benchmarks/results/river-blocker-equilibrium-v1.json",
)


def canonical(value):
    return json.dumps(_jsonable(value), sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def read_bounded(path, cap):
    if path.stat().st_size > cap:
        raise ValueError("Saved artifact exceeds file admission")
    raw = path.read_bytes()
    if len(raw) > cap:
        raise ValueError("Saved artifact changed beyond file admission")
    return raw


def inputs():
    values = audit._source_fingerprints()
    for relative in REQUIRED:
        values[relative] = sha(read_bounded(ROOT / relative, MAX_REPORT_BYTES))
    return dict(sorted(values.items()))


def _sources(saved, current):
    if type(saved) is not dict or not set(REQUIRED) <= set(saved):
        raise ValueError("Missing required source pin")
    for relative, digest in saved.items():
        if (type(relative) is not str or not relative or "\\" in relative
                or Path(relative).drive or Path(relative).is_absolute()
                or any(p in ("", ".", "..") for p in relative.split("/"))):
            raise ValueError("Unsafe source inventory path")
        if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Malformed source digest")
        # Unrelated training inventory is historical context. Current proof
        # dependencies stay pinned; all current sources are guarded per call.
        if relative not in REQUIRED:
            continue
        if relative not in current:
            raise ValueError("Required source disappeared")
        if relative.startswith("benchmarks/"):
            if digest != current[relative]:
                raise ValueError("Pinned mathematical artifact differs")
        elif digest not in audit._source_hash_candidates(ROOT / relative):
            raise ValueError("Pinned replay source differs at " + relative)


def game():
    board = rules.cards(FIXTURE["board"])
    config = rules._config(FIXTURE["config"], "config")
    worlds, selected = rules._worlds(
        board, tuple(rules.expand_range(FIXTURE[p], board) for p in ("oop", "ip")), None)
    if selected != () or len(worlds) != 3:
        raise ValueError("Physical river census differs")
    return config, worlds, rules._public_tree(board, config, config, selected, worlds)


def recompute(backend, iterations, result, filename, digest, model, known):
    if type(result) is not dict or result.get("algorithm") != "cfrplus":
        raise ValueError("Saved complete policy must use CFR+")
    if type(result.get("iterations")) is not int or result["iterations"] != iterations:
        raise ValueError("Saved iteration budget differs")
    config, worlds, root = model
    oracle = rules.replay_policy(result, FIXTURE["oop"], FIXTURE["ip"],
                                board=FIXTURE["board"], config=FIXTURE["config"])
    delta = rules.compare_result(result, oracle, tolerance=1e-9)
    # Full replay has validated these serialized legal own-hand/history rows.
    policies = {(0 if row["player"] == "oop" else 1, row["hand"], tuple(row["history"])):
                tuple(action["probability"] for action in row["actions"])
                for row in result["strategy"]}
    if len(policies) != len(result["strategy"]):
        raise ValueError("Duplicate serialized policy identity")
    certificate = exact.evaluate_exact(root, worlds, policies, config.pot, result=result)
    if not certificate["lower_value_bound"] <= known <= certificate["upper_value_bound"]:
        raise ValueError("Exact interval excludes independently proved value")
    metrics = certificate["metrics"]
    return dict(
        backend=backend, algorithm="cfrplus", iterations=iterations,
        policy_file=filename, policy_sha256=digest, known_game_value_fraction=str(known),
        float_projection_oracle=_jsonable(oracle),
        serialized_vs_float_replay_differences=delta, exact=_jsonable(certificate),
        exact_vs_float_replay_differences={n: float(v) - oracle[n] for n, v in metrics.items()},
        target_met=metrics["nash_conv"] <= TARGET, exact_zero_gap=metrics["nash_conv"] == 0)


def verify_profiles(path=REPORT):
    path = Path(path)
    before, git_before = inputs(), head()
    raw = read_bounded(path, MAX_REPORT_BYTES)
    report = json.loads(raw)
    if (type(report) is not dict or type(report.get("schema_version")) is not int
            or report["schema_version"] != 1 or report.get("certificate_id") != "river-blocker-profiles-v1"):
        raise ValueError("Unsupported blocker profile report")
    baseline = report.get("baseline_git_commit")
    if type(baseline) is not str or len(baseline) != 40 or any(c not in "0123456789abcdef" for c in baseline):
        raise ValueError("Invalid historical generation commit")
    if (report.get("fixture") != FIXTURE or report.get("target_nash_conv_fraction") != "1/1000"
            or report.get("scope") != SCOPE or report.get("limitations") != LIMITATIONS
            or type(report.get("created_at_utc")) is not str):
        raise ValueError("Fixture, threshold or scope differs")
    _sources(report.get("source_sha256"), before)
    witness = verify_equilibrium()
    known = F(witness["results"][0]["exact"]["metrics"]["value_oop"])
    if report.get("known_game_value_fraction") != str(known):
        raise ValueError("Saved game value differs from proved equilibrium")
    rows = report.get("results")
    if type(rows) is not list or len(rows) != 6:
        raise ValueError("Expected all six predeclared profiles")
    model, seen, observations = game(), set(), [(path, sha(raw), MAX_REPORT_BYTES)]
    for row in rows:
        key = row.get("backend"), row.get("iterations")
        if key not in GRID or key in seen or type(key[1]) is not int:
            raise ValueError("Invalid or repeated grid entry")
        seen.add(key)
        policy_path = POLICY_DIR / ("river-blocker-%s-%d.json" % key)
        relative = policy_path.relative_to(ROOT).as_posix()
        if row.get("policy_file") != relative:
            raise ValueError("Policy path differs from fixed grid")
        payload = read_bounded(policy_path, MAX_POLICY_BYTES)
        digest = sha(payload)
        if digest != row.get("policy_sha256"):
            raise ValueError("Complete policy hash differs")
        result = json.loads(payload)
        if canonical(result) != payload:
            raise ValueError("Complete policy must be canonical LF JSON")
        expected = recompute(*key, result, relative, digest, model, known)
        data = {n: v for n, v in row.items() if n != "timing_seconds"}
        if canonical(data) != canonical(expected):
            raise ValueError("Saved row differs from fresh complete independent replay")
        timing = row.get("timing_seconds")
        if (type(timing) is not dict or set(timing) != {"solve_plus_json", "float_plus_exact_replay"}
                or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in timing.values())):
            raise ValueError("Invalid single-call timing observation")
        observations.append((policy_path, digest, MAX_POLICY_BYTES))
    if seen != set(GRID):
        raise ValueError("Missing grid entries")
    if inputs() != before or head() != git_before:
        raise RuntimeError("Source or HEAD changed during saved profile verification")
    if any(sha(read_bounded(p, cap)) != digest for p, digest, cap in observations):
        raise RuntimeError("Saved profile inputs changed during verification")
    return report


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_bytes(payload)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def generate():
    before, git_before = inputs(), head()
    witness = verify_equilibrium()
    known = F(witness["results"][0]["exact"]["metrics"]["value_oop"])
    rows, outputs, model = [], [], game()
    for backend, iterations in GRID:
        started = time.perf_counter()
        result = solve(FIXTURE, backend, "cfrplus", iterations)
        payload = canonical(result)
        solve_seconds = time.perf_counter() - started
        if len(payload) > MAX_POLICY_BYTES:
            raise ValueError("Generated policy exceeds file admission")
        path = POLICY_DIR / ("river-blocker-%s-%d.json" % (backend, iterations))
        started = time.perf_counter()
        row = recompute(backend, iterations, result, path.relative_to(ROOT).as_posix(), sha(payload), model, known)
        row["timing_seconds"] = dict(solve_plus_json=solve_seconds, float_plus_exact_replay=time.perf_counter() - started)
        rows.append(row)
        outputs.append((path, payload))
        print(backend, iterations, "exact NC", float(F(row["exact"]["metrics"]["nash_conv"])),
              "target", row["target_met"], flush=True)
    report = dict(schema_version=1, certificate_id="river-blocker-profiles-v1",
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        baseline_git_commit=git_before, source_sha256=before, fixture=FIXTURE,
        known_game_value_fraction=str(known), target_nash_conv_fraction="1/1000",
        scope=SCOPE, limitations=LIMITATIONS, results=rows)
    payload = canonical(report)
    if len(payload) > MAX_REPORT_BYTES:
        raise ValueError("Generated report exceeds file admission")
    for path, raw in outputs:
        if path.exists() and read_bounded(path, MAX_POLICY_BYTES) != raw:
            raise ValueError("Refusing to rewrite differing immutable policy")
    if inputs() != before or head() != git_before:
        raise RuntimeError("Source or HEAD changed during generation")
    candidate = REPORT.with_name(REPORT.name + "." + uuid.uuid4().hex + ".candidate")
    created = []
    try:
        for path, raw in outputs:
            if not path.exists():
                atomic_write(path, raw)
                created.append(path)
        atomic_write(candidate, payload)
        verify_profiles(candidate)
        if inputs() != before or head() != git_before:
            raise RuntimeError("Source or HEAD changed before publication")
        candidate.replace(REPORT)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    finally:
        candidate.unlink(missing_ok=True)
    print("SAVED SIX VERIFIED PROFILES", len(payload), sha(payload), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    if parser.parse_args().verify:
        verify_profiles()
        print("SIX SAVED PROFILES INDEPENDENTLY VERIFIED", flush=True)
    else:
        generate()


if __name__ == "__main__":
    main()
