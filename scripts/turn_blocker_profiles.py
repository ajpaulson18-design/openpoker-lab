"""Generate and independently replay six fixed CFR+ profiles for the blocker turn game.

The saved policy files are complete immutable solver outputs. Verification never
trains and exact metrics apply to row-normalized serialized binary64 policies.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from fractions import Fraction as F
from pathlib import Path
from scripts.historical_foundation_sources import BRIDGE_INPUTS, foundation_source_accepts

from scripts import turn_river_validation as rules
from scripts import turn_rational_certificate as exact_helper
from scripts import verify_turn_blocker_sequence as witness_verifier
from scripts.benchmark_turn_river_independent import solve as solve_materialized
from scripts.turn_blocker_sequence_fixture import FIXTURE
from scripts.river_sequence_form import _jsonable
from scripts.verify_turn_blocker_sequence import REQUIRED_SOURCES as WITNESS_SOURCES
from pokerlab.matrix_free_turn import solve_matrix_free_turn

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "benchmarks/results/turn-blocker-cfrplus-profiles-v1.json"
POLICY_DIR = ROOT / "benchmarks/results/turn-blocker-cfrplus-policies-v1"
GRID = tuple((backend, count) for backend in ("materialized", "matrix-free")
             for count in (1000, 3000, 10000))
TARGET = F(1, 1000)
MAX_REPORT_BYTES, MAX_POLICY_BYTES = 2_000_000, 1_000_000
METRICS = (
    "value_oop", "value_ip", "oop_best_response_value",
    "ip_best_response_value", "oop_best_response_gain",
    "ip_best_response_gain", "nash_conv", "exploitability",
)
SCOPE = "Six fixed-iteration CFR+ profiles for one blocker-conditioned selected-river configured turn game."
LIMITATIONS = (
    "Exact response bounds apply to row-normalized saved binary64 policies and configured binary64 terminal constants. "
    "One complete solve-plus-JSON and replay observation makes no general runtime, memory, RSS or unrestricted Hold'em claim.",
)
# Pin the independent compact equilibrium witness, fixed physical model, legacy
# rejection receipt and replay dependencies used by this profile report.
REQUIRED = tuple(dict.fromkeys((
    *WITNESS_SOURCES,
    "scripts/benchmark_turn_river_independent.py",
    "scripts/turn_blocker_sequence_equilibrium.py",
    "scripts/turn_blocker_profiles.py",
    "tests/test_turn_blocker_profiles.py",
    "benchmarks/results/turn-blocker-sequence-equilibrium-v1.json",
    "benchmarks/results/turn-blocker-sequence-model-v1.json",
    "benchmarks/results/turn-blocker-sequence-hidden-information-v1.json",
    "benchmarks/results/turn-blocker-sequence-legacy-preflight.json",
)))


def canonical(value):
    return (json.dumps(_jsonable(value), sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def head():
    value = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Could not read a full Git HEAD")
    return value


def read_bounded(path, cap):
    path = Path(path)
    if path.stat().st_size > cap:
        raise ValueError("Saved artifact exceeds file admission")
    raw = path.read_bytes()
    if len(raw) > cap:
        raise ValueError("Saved artifact changed beyond file admission")
    return raw


def hash_candidates(path):
    raw = Path(path).read_bytes()
    values = {sha(raw)}
    if Path(path).suffix == ".py":
        lf = raw.replace(b"\r\n", b"\n")
        values.add(sha(lf))
        values.add(sha(lf.replace(b"\n", b"\r\n")))
    return values


def inputs():
    inventory = set(REQUIRED)
    inventory.update(path.relative_to(ROOT).as_posix() for path in BRIDGE_INPUTS)
    inventory.update(path.relative_to(ROOT).as_posix()
                     for path in (ROOT / "pokerlab").glob("*.py"))
    result = {}
    for relative in sorted(inventory):
        path = ROOT / relative
        if not path.is_file():
            raise ValueError("Required profile provenance input is missing: " + relative)
        result[relative] = sha(read_bounded(path, MAX_REPORT_BYTES))
    return result


def assert_unchanged(saved_head, saved_sources):
    if head() != saved_head:
        raise RuntimeError("Git HEAD changed during blocker profile operation")
    if inputs() != saved_sources:
        raise RuntimeError("Pinned source or witness changed during blocker profile operation")


def source_pins(saved, current):
    if type(saved) is not dict or not set(REQUIRED) <= set(saved):
        raise ValueError("Blocker profile source inventory is missing a required pin")
    for name, digest in saved.items():
        if (type(name) is not str or not name or "\\" in name
                or Path(name).is_absolute() or Path(name).drive
                or any(part in ("", ".", "..") for part in name.split("/"))):
            raise ValueError("Unsafe source inventory path")
        if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Malformed source digest")
        # Extra entries describe the training inventory at generation time.
        # Keep their shape safe, while replay guards every current input before
        # and after verification. Required proof inputs remain exact pins.
        if name not in REQUIRED:
            continue
        if name not in current:
            raise ValueError("Pinned source disappeared: " + name)
        if name.endswith(".py"):
            if not foundation_source_accepts(ROOT / name, digest, hash_candidates(ROOT / name)):
                raise ValueError("Pinned source differs: " + name)
        elif digest != current[name]:
            raise ValueError("Pinned mathematical artifact differs: " + name)


def model():
    board = rules.cards(FIXTURE["board"])
    config = rules._config(FIXTURE["config"], "config")
    worlds, selected = rules._worlds(
        board, tuple(rules.expand_range(FIXTURE[player], board)
                     for player in ("oop", "ip")), FIXTURE["runouts"])
    if selected != tuple(FIXTURE["runouts"]) or len(worlds) != 6:
        raise ValueError("Expected six blocker-conditioned worlds on the fixed two-river subset")
    root = rules._public_tree(board, config, config, selected, worlds)
    pending, seen = [root], []
    while pending:
        node = pending.pop()
        seen.append(node)
        if isinstance(node, rules._Decision):
            pending.extend(node.children)
        elif isinstance(node, rules._Chance):
            pending.extend(node.branches.values())
        elif not isinstance(node, rules._Terminal):
            raise TypeError("Unknown blocker public-tree node")
    if len(seen) != 63:
        raise ValueError("Fixed blocker public tree census differs")
    pair_count = len({(world["hands"][0], world["hands"][1]) for world in worlds})
    if pair_count != 3:
        raise ValueError("Fixed blocker fixture must retain three compatible private pairs")
    return board, config, worlds, root


def policies_from_result(result):
    """Keep binary64 row values intact; exact evaluator normalizes these rows."""
    policies = {}
    rows = result.get("strategy")
    if type(rows) is not list:
        raise ValueError("Complete serialized policy rows are missing")
    for row in rows:
        if type(row) is not dict:
            raise ValueError("Malformed serialized policy row")
        player = {"oop": 0, "ip": 1}.get(row.get("player"))
        if player is None:
            raise ValueError("Unknown serialized policy player")
        key = player, row.get("hand"), tuple(row.get("history", ()))
        if key in policies:
            raise ValueError("Duplicate serialized policy identity")
        actions = row.get("actions")
        if type(actions) is not list:
            raise ValueError("Serialized actions are missing")
        probabilities = tuple(action.get("probability") for action in actions)
        if any(type(value) is not float or not math.isfinite(value) for value in probabilities):
            raise ValueError("Policy probabilities must be finite serialized binary64 values")
        policies[key] = probabilities
    return policies


def float_view(exact):
    try:
        return {name: float(value) for name, value in exact["metrics"].items()}
    except (OverflowError, ValueError) as exc:
        raise ValueError("Exact metric has no finite binary64 projection") from exc


def recompute(backend, iterations, result, policy_file, policy_digest, game):
    if type(result) is not dict or result.get("algorithm") != "cfrplus":
        raise ValueError("Saved complete policy must use CFR+")
    if type(result.get("iterations")) is not int or result["iterations"] != iterations:
        raise ValueError("Actual complete-call iteration count differs from fixed grid")
    board, config, worlds, root = game
    oracle = rules.replay_policy(
        result, FIXTURE["oop"], FIXTURE["ip"], board=FIXTURE["board"],
        config=FIXTURE["config"], river_config=FIXTURE["config"],
        runouts=FIXTURE["runouts"])
    differences = rules.compare_result(result, oracle, tolerance=1e-9)
    if (len(worlds) != 6 or oracle.get("world_count") != 6
            or oracle.get("checked_information_sets") != 56
            or oracle.get("compatible_pair_count") != 3
            or oracle.get("public_node_count") != 28
            or len(result.get("strategy", ())) != 56):
        raise ValueError("Expected six worlds, three pairs, 56 policy rows and 28 public decision nodes")
    exact = exact_helper.evaluate_exact(
        root, worlds, policies_from_result(result), config.pot, result=result)
    # Refuse nonfinite projections and gate every exact metric, including the
    # normalized exact policy result, against the independent float replay.
    exact_float = float_view(exact)
    exact_float_differences = {}
    for name in METRICS:
        value, expected = exact_float[name], oracle[name]
        if not math.isfinite(value) or not math.isfinite(expected):
            raise ValueError("Exact/float replay metric is not finite: " + name)
        delta = value - expected
        if abs(delta) > 1e-9:
            raise ValueError("Exact normalized policy differs from float replay: " + name)
        exact_float_differences[name] = delta
    known = F(115, 7)
    lower, upper = exact["lower_value_bound"], exact["upper_value_bound"]
    if not lower <= known <= upper:
        raise ValueError("Exact response interval excludes independently proved value 115/7")
    canonical_rows = exact["normalized_policy_rows"]
    if not canonical_rows:
        raise ValueError("Exact normalization ledger produced no canonical policy rows")
    misses = exact["metrics"]["nash_conv"] > TARGET
    return dict(
        backend=backend, algorithm="cfrplus", iterations_requested=iterations,
        iterations_completed=iterations, policy_file=policy_file,
        policy_sha256=policy_digest, policy_bytes=len(canonical(result)),
        policy_identity_sha256=sha(canonical(result["strategy"])),
        worlds=len(worlds), information_sets=oracle["checked_information_sets"],
        compatible_pairs=oracle["compatible_pair_count"], policy_rows=len(result["strategy"]),
        total_public_nodes=63, public_decision_nodes=oracle["public_node_count"],
        known_game_value_fraction=str(known),
        float_projection_oracle=oracle,
        serialized_vs_float_replay_differences=differences,
        exact=exact, exact_normalized_float_projection=exact_float,
        exact_vs_float_replay_differences=exact_float_differences,
        target_met=not misses,
        threshold_miss=misses,
    )


def verify_profiles(path=REPORT):
    path = Path(path)
    sources_before, head_before = inputs(), head()
    raw = read_bounded(path, MAX_REPORT_BYTES)
    report = json.loads(raw)
    if (type(report) is not dict or type(report.get("schema_version")) is not int
            or report["schema_version"] != 1
            or report.get("certificate_id") != "turn-blocker-cfrplus-profiles-v1"):
        raise ValueError("Unsupported blocker profile report")
    if (type(report.get("python")) is not str or not report["python"]
            or type(report.get("platform")) is not str or not report["platform"]):
        raise ValueError("Missing generation interpreter or platform observation")
    if report.get("fixture") != FIXTURE or report.get("grid") != [
            {"backend": backend, "iterations": count} for backend, count in GRID]:
        raise ValueError("Fixture or predeclared six-profile grid differs")
    if (report.get("target_nash_conv_fraction") != "1/1000"
            or report.get("scope") != SCOPE or report.get("limitations") != list(LIMITATIONS)):
        raise ValueError("Threshold or scope differs")
    baseline = report.get("baseline_git_commit")
    if type(baseline) is not str or len(baseline) != 40 or any(c not in "0123456789abcdef" for c in baseline):
        raise ValueError("Invalid generation HEAD")
    if report.get("known_game_value_fraction") != "115/7":
        raise ValueError("Independent compact witness value must be recorded as 115/7")
    source_pins(report.get("source_sha256"), sources_before)
    witness = witness_verifier.verify_saved_artifact()
    if witness["results"][0]["exact"]["metrics"]["value_oop"] != "115/7":
        raise ValueError("Independent compact witness no longer proves value 115/7")
    rows = report.get("results")
    if type(rows) is not list or len(rows) != len(GRID):
        raise ValueError("Expected all six fixed profiles, including threshold misses")
    seen, observations = set(), [(path, sha(raw), MAX_REPORT_BYTES)]
    game = model()
    for row in rows:
        key = row.get("backend"), row.get("iterations_requested")
        if key not in GRID or key in seen:
            raise ValueError("Duplicate or unexpected fixed-grid profile")
        seen.add(key)
        if type(row.get("iterations_requested")) is not int:
            raise ValueError("Iteration grid must not accept bool values")
        expected_name = "turn-blocker-%s-%d.json" % key
        if row.get("policy_file") != (POLICY_DIR / expected_name).relative_to(ROOT).as_posix():
            raise ValueError("Policy filename differs from fixed grid")
        policy_path = ROOT / row["policy_file"]
        payload = read_bounded(policy_path, MAX_POLICY_BYTES)
        digest = sha(payload)
        if digest != row.get("policy_sha256"):
            raise ValueError("Complete policy hash differs")
        result = json.loads(payload)
        if canonical(result) != payload:
            raise ValueError("Policy bytes must use canonical LF JSON")
        expected = recompute(*key, result, row["policy_file"], digest, game)
        saved = {name: value for name, value in row.items()
                 if name not in ("timing_seconds", "replay_seconds")}
        if canonical(saved) != canonical(expected):
            raise ValueError("Saved row differs from fresh full-policy replay")
        for timing_name in ("timing_seconds", "replay_seconds"):
            value = row.get(timing_name)
            if (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                raise ValueError("Invalid single-call timing observation")
        observations.append((policy_path, digest, MAX_POLICY_BYTES))
    if seen != set(GRID):
        raise ValueError("Fixed profile grid is incomplete")
    assert_unchanged(head_before, sources_before)
    if any(sha(read_bounded(file, cap)) != digest for file, digest, cap in observations):
        raise RuntimeError("Saved report or policy changed during verification")
    return report


def _exclusive_policy(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _atomic_replace(path, payload, prefix):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def generate():
    sources_before, head_before = inputs(), head()
    witness = witness_verifier.verify_saved_artifact()
    if witness["results"][0]["exact"]["metrics"]["value_oop"] != "115/7":
        raise ValueError("Pinned exact witness does not establish value 115/7")
    game = model()
    results, outputs = [], []
    for backend, iterations in GRID:
        started = time.perf_counter()
        if backend == "materialized":
            # This existing public-batched benchmark path is the selected
            # materialized trainer and diagnostics implementation.
            materialized_fixture = {**FIXTURE, "river_config": FIXTURE["config"]}
            result = solve_materialized(materialized_fixture, backend, "cfrplus", iterations)
        else:
            result = solve_matrix_free_turn(
                FIXTURE["board"], FIXTURE["oop"], FIXTURE["ip"], FIXTURE["config"],
                river_config=FIXTURE["config"], iterations=iterations,
                algorithm="cfrplus", runouts=FIXTURE["runouts"])
        payload = canonical(result)
        solve_seconds = time.perf_counter() - started
        if len(payload) > MAX_POLICY_BYTES:
            raise ValueError("Generated complete policy exceeds 1MB admission")
        filename = "turn-blocker-%s-%d.json" % (backend, iterations)
        path = POLICY_DIR / filename
        digest = sha(payload)
        if path.exists() and read_bounded(path, MAX_POLICY_BYTES) != payload:
            raise ValueError("Refusing to rewrite differing immutable policy bytes")
        replay_started = time.perf_counter()
        row = recompute(backend, iterations, result, path.relative_to(ROOT).as_posix(), digest, game)
        replay_seconds = time.perf_counter() - replay_started
        row["timing_seconds"] = solve_seconds
        row["replay_seconds"] = replay_seconds
        results.append(row)
        outputs.append((path, payload))
        print(f"{backend} {iterations}: normalized exact NashConv="
              f"{float(F(row['exact']['metrics']['nash_conv'])):.12g}; "
              f"target_met={row['target_met']}", flush=True)
    report = dict(
        schema_version=1, certificate_id="turn-blocker-cfrplus-profiles-v1",
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        baseline_git_commit=head_before, source_sha256=sources_before,
        python=platform.python_version(), platform=platform.platform(),
        fixture=FIXTURE,
        grid=[{"backend": backend, "iterations": count} for backend, count in GRID],
        target_nash_conv_fraction=str(TARGET), known_game_value_fraction="115/7",
        scope=SCOPE,
        limitations=list(LIMITATIONS), results=results)
    report_payload = canonical(report)
    if len(report_payload) > MAX_REPORT_BYTES:
        raise ValueError("Generated report exceeds 2MB admission")
    for path, payload in outputs:
        if path.exists() and read_bounded(path, MAX_POLICY_BYTES) != payload:
            raise ValueError("Refusing to rewrite differing immutable policy bytes")
    assert_unchanged(head_before, sources_before)

    created_policies, candidate = [], REPORT.with_name(REPORT.name + "." + uuid.uuid4().hex + ".candidate")
    previous = read_bounded(REPORT, MAX_REPORT_BYTES) if REPORT.exists() else None
    replaced = False
    try:
        for path, payload in outputs:
            if not path.exists():
                _exclusive_policy(path, payload)
                created_policies.append(path)
        with candidate.open("xb") as stream:
            stream.write(report_payload)
            stream.flush()
            os.fsync(stream.fileno())
        verify_profiles(candidate)
        assert_unchanged(head_before, sources_before)
        os.replace(candidate, REPORT)
        replaced = True
        verify_profiles(REPORT)
        assert_unchanged(head_before, sources_before)
    except BaseException:
        candidate.unlink(missing_ok=True)
        if replaced:
            if previous is None:
                REPORT.unlink(missing_ok=True)
            else:
                _atomic_replace(REPORT, previous, ".turn-blocker-profile-restore-")
        for path in created_policies:
            path.unlink(missing_ok=True)
        raise
    finally:
        candidate.unlink(missing_ok=True)
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify_profiles()
    else:
        generate()
