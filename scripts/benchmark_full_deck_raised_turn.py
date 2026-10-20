"""Fixed-budget full-deck raised-turn CFR+ experiment and saved-policy verifier.

The six requested profiles are fixed in this module. Verification replays saved
complete policies and never invokes a production trainer.
"""
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
from pathlib import Path

from scripts import full_deck_raised_fixture as fixture
from scripts import full_deck_raised_reference as reference
from scripts.benchmark_turn_river_independent import ROOT, solve
from scripts.turn_river_validation import compare_result, replay_policy


REPORT = ROOT / "benchmarks/results/full-deck-raised-turn-benchmark-v1.json"
POLICIES_DIR = ROOT / "benchmarks/results/full-deck-raised-turn-policies-v1"
REFERENCE_PATH = ROOT / "benchmarks/results/full-deck-raised-turn-reference-v1.json"
REFERENCE_SHA256 = "bff6aaf4d2bf6038503645787d66cff9f57bcb1385e334364f72126a67211165"
ITERATIONS = (100, 1000, 1500)
BACKENDS = ("materialized", "matrix-free")
ALGORITHM = "cfrplus"
THRESHOLD = 0.001
TOLERANCE = 1e-9
MAX_REPORT_BYTES = 1_000_000
MAX_POLICY_BYTES = 2_000_000
METRICS = reference.METRICS
PROFILE_METADATA_FIELDS = (
    "algorithm", "iterations", "execution_backend", "diagnostics_backend",
    "terminal_backend", "board", "runouts", "runout_mode", "reachable_runouts",
    "config", "turn_config", "river_config", "street_configs", "info_sets",
    "public_states", "public_nodes", "training_passes_per_iteration",
    "update_schedule", "average_schedule", "worlds", "compatible_pairs",
    "world_traversal_nodes", "worlds_materialized", "compatible_world_count",
    "public_state_limit", "resource_usage",
)
SCHEMA_VERSION = 1
BENCHMARK_ID = "full-deck-raised-turn-benchmark-v1"

# Pins every proof/fixture/test/runner input required by this experiment. Extra
# historical source entries in an accepted report are allowed during verify.
REQUIRED_SOURCES = (
    "pokerlab/cards.py", "pokerlab/matrix_free_turn.py",
    "pokerlab/postflop_solver.py", "pokerlab/river_config.py",
    "scripts/benchmark_turn_river_independent.py",
    "scripts/full_deck_raised_fixture.py",
    "scripts/full_deck_raised_reference.py",
    "scripts/preflop_validation.py", "scripts/turn_blocker_sequence_fixture.py",
    "scripts/turn_river_validation.py", "scripts/verify_turn_blocker_sequence.py",
    "scripts/benchmark_full_deck_raised_turn.py",
    "tests/test_full_deck_raised_fixture.py",
    "tests/test_full_deck_raised_reference.py",
    "tests/test_full_deck_raised_diagnostics.py",
    "tests/test_benchmark_full_deck_raised_turn.py",
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _guard(expected_sources, expected_head):
    _require(fingerprints() == expected_sources, "Source fingerprints changed during operation")
    _require(_head() == expected_head, "Git HEAD changed during operation")


def fingerprints():
    paths = {p.relative_to(ROOT).as_posix() for p in (ROOT / "pokerlab").glob("*.py")}
    paths.update(REQUIRED_SOURCES)
    hashes = {}
    for relative in sorted(paths):
        path = ROOT / relative
        raw = path.read_bytes()
        if path.suffix == ".py":
            raw = raw.replace(b"\r\n", b"\n")
        hashes[relative] = _sha(raw)
    return hashes


def _validate_fingerprint_map(saved, current, strict):
    _require(type(saved) is dict, "Source fingerprint map must be an object")
    required = set(REQUIRED_SOURCES)
    _require(required.issubset(saved), "Saved source fingerprints omit required current sources")
    if strict:
        _require(set(saved) == required, "Generation source fingerprint set changed")
    for name in required:
        digest = current[name]
        _require(saved.get(name) == digest, "Current source differs from report: " + name)


def frozen_case():
    case = dict(fixture.FIXTURE)
    case["river_config"] = dict(case["config"])
    # Validate immutable fixture identity, including absence of selected rivers.
    _require(case == {**fixture.FIXTURE, "river_config": fixture.FIXTURE["config"]},
             "Raised fixture changed")
    _require("runouts" not in case, "Fixed full-deck case must omit runouts")
    return case


def expected_work(backend, iterations, census=None):
    if type(iterations) is not int or iterations <= 0:
        raise ValueError("iterations must be a positive exact integer")
    census = fixture.census() if census is None else census
    return fixture.forecast_work(backend, iterations, census.worlds,
                                 census.visited_decisions_per_world,
                                 census.public_nodes, census.max_private_hands)


def validate_profile_metadata(result, case, backend, iterations, census=None, *, allow_probe=False):
    _require(backend in BACKENDS, "Unsupported fixed benchmark backend")
    _require(type(iterations) is int and iterations > 0 and
             (iterations in ITERATIONS or (allow_probe and iterations == 10)),
             "Iteration count is not in the frozen benchmark grid")
    _require(type(result) is dict, "Complete policy result must be an object")
    _require(result.get("algorithm") == ALGORITHM, "Profile must use CFR+")
    _require(type(result.get("iterations")) is int and result["iterations"] == iterations,
             "Profile did not complete the requested iterations")
    _require("convergence" not in result and "target_exploitability" not in result,
             "Fixed-budget profile must not configure a stopping target")
    case = frozen_case() if case is None else case
    census = fixture.census() if census is None else census
    board = [case["board"][i:i + 2] for i in range(0, len(case["board"]), 2)]
    candidates = [card for card in __import__("pokerlab.cards", fromlist=["DECK"]).DECK
                  if card not in board]
    _require(result.get("board") == board, "Policy board differs from frozen fixture")
    _require(result.get("runouts") == candidates and result.get("runout_mode") == "full-deck",
             "Policy must include the canonical complete runout set")
    reachable = result.get("reachable_runouts")
    _require(type(reachable) is list and len(reachable) == 48 and
             len(set(reachable)) == 48 and set(reachable) == set(candidates),
             "Reachable river set differs from full-deck physical support")
    from pokerlab.river_config import RiverConfig
    turn = RiverConfig.from_dict(case["config"]).to_dict()
    river = RiverConfig.from_dict(case["river_config"]).to_dict()
    _require(result.get("config") == turn and result.get("turn_config") == turn and
             result.get("river_config") == river and
             result.get("street_configs") == {"turn": turn, "river": river},
             "Turn or river configuration metadata differs")
    for key, expected in (("info_sets", 2404), ("public_states", census.public_nodes),
                          ("public_nodes", census.decisions),
                          ("training_passes_per_iteration", 3)):
        _require(type(result.get(key)) is int and result[key] == expected,
                 "Production census metadata differs: " + key)
    _require(result.get("update_schedule") == "alternating-oop-then-ip" and
             result.get("average_schedule") == "linear-post-sweep-own-reach",
             "CFR+ schedule metadata differs")
    work = expected_work(backend, iterations, census)
    _require(work <= fixture.REFERENCE_WORK_CAP, "Requested work exceeds unchanged 30m cap")
    if backend == "materialized":
        _require(result.get("execution_backend") == "public-batched-python" and
                 result.get("diagnostics_backend") == "public-batched-python" and
                 "terminal_backend" not in result,
                 "Materialized backend identity differs")
        _require(result.get("worlds") == 176 and result.get("compatible_pairs") == 4 and
                 result.get("world_traversal_nodes") == census.visited_decisions_per_world,
                 "Materialized physical counts or visit census differ")
        _require(result.get("public_state_limit") == 250000,
                 "Materialized public-state cap metadata differs")
    elif backend == "matrix-free":
        _require(result.get("execution_backend") == "matrix-free-ranked-python" and
                 result.get("terminal_backend") == "ranked-turn-python",
                 "Matrix-free backend identity differs")
        _require(result.get("compatible_world_count") == 176 and
                 type(result.get("worlds_materialized")) is int and
                 result.get("worlds_materialized") == 0,
                 "Matrix-free physical counts differ")
        usage = result.get("resource_usage")
        _require(type(usage) is dict and usage.get("hand_state_pass_work") == work,
                 "Matrix-free work charge differs")
        _require(usage.get("hand_slots") == 184 and
                 usage.get("kernel_public_states") == census.public_nodes and
                 usage.get("turn_fold_terminals") == 4 and
                 usage.get("info_action_slots") == 5364 and
                 usage.get("fallback_pair_checks") == 0 and
                 usage.get("compatible_world_count") == 176 and
                 usage.get("hand_counts") == [2, 2] and
                 usage.get("limits") == {
                     "hand_state_pass_work": fixture.REFERENCE_WORK_CAP,
                     "info_action_slots": 1_000_000,
                     "fallback_pair_checks": 30_000_000,
                     "hand_slots": 120_000,
                     "public_states": 250_000,
                     "public_nodes": 10_000,
                 },
                 "Matrix-free resource metadata differs")
    else:
        raise ValueError("Unsupported backend")
    for metric in METRICS:
        value = result.get(metric)
        _require(type(value) in (int, float) and math.isfinite(value),
                 "Policy metric must be finite: " + metric)
    return work


def _replay(result, case):
    # runouts deliberately omitted to preserve the entire remaining deck.
    return replay_policy(result, case["oop"], case["ip"], board=case["board"],
                        config=case["config"], river_config=case["river_config"])


def replay_profile(result, case, backend, iterations, census=None, *, allow_probe=False):
    validate_profile_metadata(result, case, backend, iterations, census,
                              allow_probe=allow_probe)
    original = _canonical(result)
    oracle = _replay(result, case)
    differences = compare_result(result, oracle, tolerance=TOLERANCE)
    _require(oracle.get("worlds") == 176 and oracle.get("compatible_pair_count") == 4 and
             oracle.get("checked_information_sets") == 2404 and
             oracle.get("public_node_count") == 1254,
             "Independent full-deck replay counts differ")
    _require(_canonical(result) == original, "Replay mutated policy payload")
    return {name: oracle[name] for name in METRICS}, differences, oracle


def _policy_name(backend, iterations):
    return f"full-deck-raised-turn-v1-{backend}-{iterations}.json"


def _profile_metadata(result):
    return {name: result[name] for name in PROFILE_METADATA_FIELDS if name in result}


def _verify_reference_pin():
    _require(REFERENCE_PATH.stat().st_size <= reference.MAX_REPORT_BYTES,
             "Accepted physical/tree reference exceeds byte cap")
    raw = REFERENCE_PATH.read_bytes()
    _require(_sha(raw) == REFERENCE_SHA256,
             "Accepted physical/tree reference SHA256 differs from frozen pin")
    report = reference.verify_saved_artifact(REFERENCE_PATH)
    _require(report["reference"].get("public_tree_sha256") ==
             "70d87064c6d7048b75784b6623a2dc6249f57ac61384a27d1724c3d53563bd61",
             "Accepted physical/tree public-tree identity differs")
    return _sha(raw)


def verify_saved_artifact(report_path=REPORT, policies_dir=POLICIES_DIR):
    """Replay a complete saved report. This function never calls a trainer."""
    report_path = Path(report_path)
    _require(report_path.stat().st_size <= MAX_REPORT_BYTES, "Benchmark report exceeds byte cap")
    raw_report = report_path.read_bytes()
    _require(len(raw_report) <= MAX_REPORT_BYTES, "Benchmark report exceeds byte cap")
    before, before_head = fingerprints(), _head()
    reference_sha = _verify_reference_pin()
    report = json.loads(raw_report)
    _require(type(report) is dict and type(report.get("schema_version")) is int and
             report.get("schema_version") == SCHEMA_VERSION and
             report.get("benchmark_id") == BENCHMARK_ID,
             "Unsupported benchmark report envelope")
    _validate_fingerprint_map(report.get("source_sha256"), before, strict=False)
    _require(report.get("reference_sha256") == reference_sha,
             "Report physical/tree reference pin differs")
    baseline = report.get("baseline_git_commit")
    _require(type(baseline) is str and len(baseline) == 40 and
             all(char in "0123456789abcdef" for char in baseline),
             "Saved historical generation commit is invalid")
    case = frozen_case()
    _require(report.get("fixture") == case, "Saved report fixture differs")
    census = fixture.census()
    expected_census = json.loads(json.dumps(fixture.to_jsonable(census)))
    _require(_canonical(report.get("census")) == _canonical(expected_census),
             "Saved full-deck census differs")
    _require(report.get("methodology") == _methodology(), "Saved benchmark methodology differs")
    rows = report.get("results")
    expected_jobs = [(i, backend) for i in ITERATIONS for backend in BACKENDS]
    _require(type(rows) is list and len(rows) == len(expected_jobs),
             "Report must retain all six fixed profiles")
    replay_seconds = []
    for row, (iterations, backend) in zip(rows, expected_jobs):
        _guard(before, before_head)
        _require(row.get("iterations_requested") == iterations and row.get("backend") == backend,
                 "Report result order or fixed job differs")
        _require(row.get("algorithm") == ALGORITHM and
                 row.get("target_exploitability") is None and
                 row.get("threshold") == THRESHOLD,
                 "Saved algorithm, target or threshold metadata differs")
        work = expected_work(backend, iterations, census)
        _require(row.get("work_charge") == work and
                 row.get("work_limit") == fixture.REFERENCE_WORK_CAP,
                 "Saved fixed-work forecast differs")
        _require(row.get("worlds") == 176 and row.get("compatible_pairs") == 4 and
                 row.get("information_rows") == 2404 and
                 row.get("independent_public_decisions") == census.decisions and
                 row.get("public_states") == census.public_nodes,
                 "Saved result physical or tree counts differ")
        solve_seconds = row.get("complete_call_seconds_uncontrolled")
        replay_seconds_saved = row.get("independent_replay_seconds")
        _require(type(solve_seconds) in (int, float) and math.isfinite(solve_seconds) and
                 solve_seconds >= 0 and type(replay_seconds_saved) in (int, float) and
                 math.isfinite(replay_seconds_saved) and replay_seconds_saved >= 0,
                 "Saved timing observations must be finite and nonnegative")
        filename = _policy_name(backend, iterations)
        _require(row.get("policy_file") == filename, "Unexpected immutable policy filename")
        path = Path(policies_dir) / filename
        _require(path.stat().st_size <= MAX_POLICY_BYTES, "Saved policy exceeds byte cap")
        raw = path.read_bytes()
        _require(len(raw) <= MAX_POLICY_BYTES and b"\r" not in raw,
                 "Saved policy is oversized or noncanonical LF")
        _require(_canonical(json.loads(raw)) == raw,
                 "Saved policy bytes are not canonical JSON")
        _require(_sha(raw) == row.get("policy_sha256"), "Saved policy hash differs")
        policy = json.loads(raw)
        start = time.perf_counter()
        metrics, diffs, oracle = replay_profile(policy, case, backend, iterations, census)
        _guard(before, before_head)
        replay_seconds.append(time.perf_counter() - start)
        _require(_metric_map_close(row.get("metrics"), metrics) and
                 _metric_map_close(row.get("oracle_metrics"), metrics),
                 "Saved independent replay metrics differ")
        _require(_differences_close(row.get("scalar_differences"), diffs),
                 "Saved scalar replay differences differ")
        _require(row.get("saved_policy_replayed") is True,
                 "Saved oracle metrics/replay marker differs")
        _require(row.get("iterations_completed") == iterations and
                 row.get("threshold_met") is (metrics["nash_conv"] <= THRESHOLD),
                 "Saved iteration or threshold result differs")
        _require(_canonical(row.get("actual_metadata")) ==
                 _canonical(_profile_metadata(policy)),
                 "Saved production profile metadata differs")
        _require(all(type(metrics[key]) in (int, float) and math.isfinite(metrics[key])
                     for key in METRICS), "Saved metric is non-finite")
    after = fingerprints()
    _require(after == before and _head() == before_head and report_path.read_bytes() == raw_report,
             "Sources, HEAD or report changed during saved replay")
    for row in rows:
        path = Path(policies_dir) / row["policy_file"]
        _require(path.stat().st_size <= MAX_POLICY_BYTES, "Saved policy exceeds byte cap")
        raw = path.read_bytes()
        _require(_sha(raw) == row["policy_sha256"],
                 "A saved policy changed during the full replay pass")
    _guard(before, before_head)
    return {"status": "VERIFIED_SAVED_FULL_DECK_RAISED_TURN", "training_calls": 0,
            "profiles": len(rows), "replay_seconds": replay_seconds,
            "report_sha256": _sha(raw_report)}


def _metric_map_close(saved, expected):
    return (type(saved) is dict and set(saved) == set(METRICS) and
            all(type(saved.get(key)) in (int, float) and math.isfinite(saved[key]) and
                abs(saved[key] - expected[key]) <= TOLERANCE for key in METRICS))


def _differences_close(saved, expected):
    return (type(saved) is dict and set(saved) == set(expected) and
            all(type(saved.get(key)) in (int, float) and math.isfinite(saved[key]) and
                abs(saved[key] - expected[key]) <= TOLERANCE for key in expected))


def _methodology():
    return {
        "design": "Six fixed CFR+ calls in iteration-major materialized then matrix-free order at 100, 1000, and 1500 iterations; no stopping target.",
        "conditioning": "Full-deck chance with omitted runouts: four compatible private pairs, 44 legal rivers per pair, 176 physical worlds.",
        "validation": "Complete policy metadata is checked and all eight metrics independently replayed before and after canonical LF serialization.",
        "threshold": "0.001 NashConv is report-only; every miss is retained.",
        "resources": "Forecasts are advisory and use the unchanged 30,000,000 work caps; the production guards remain authoritative.",
        "timing": "Complete solver call plus canonical JSON encoding and independent replay are timed separately; uncontrolled observations with no memory or RSS claim.",
        "limitations": "Numeric independent replay is not an arbitrary-policy exact certificate. Generic exact audit remains rejected at its existing work limit; no equilibrium or general convergence claim is made.",
    }


def _atomic_exclusive(path, payload, created):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, staging = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        with open(staging, "rb") as stream:
            staged = stream.read()
        _require(staged == payload, "Staged artifact bytes differ")
        try:
            # Hard-link publication is atomic and exclusive on the same volume.
            os.link(staging, path)
            created.append(path)
        except FileExistsError:
            _require(path.read_bytes() == payload, "Refusing to replace differing immutable artifact")
    finally:
        Path(staging).unlink(missing_ok=True)


def generate(report_path=REPORT, policies_dir=POLICIES_DIR):
    """Run the fixed six profiles and publish only verified immutable bytes."""
    before, before_head = fingerprints(), _head()
    report_path, policies_dir = Path(report_path), Path(policies_dir)
    if report_path.exists():
        # Never spend another six solver calls only to collide with an immutable
        # report. Return a complete accepted artifact, or reject before training.
        return verify_saved_artifact(report_path, policies_dir)
    existing_policy_files = [policies_dir / _policy_name(backend, iterations)
                             for iterations in ITERATIONS for backend in BACKENDS]
    _require(not any(path.exists() for path in existing_policy_files),
             "Refusing to train over an existing partial immutable policy set")
    reference_sha = _verify_reference_pin()
    case, census = frozen_case(), fixture.census()
    created = []
    try:
        rows = []
        for iterations in ITERATIONS:
            for backend in BACKENDS:
                _guard(before, before_head)
                print(f"START backend={backend} iterations={iterations}", flush=True)
                started = time.perf_counter()
                result = solve(case, backend, ALGORITHM, iterations)
                payload = _canonical(result)
                complete_seconds = time.perf_counter() - started
                _guard(before, before_head)
                work = validate_profile_metadata(result, case, backend, iterations, census)
                replay_started = time.perf_counter()
                metrics, diffs, oracle = replay_profile(result, case, backend, iterations, census)
                _guard(before, before_head)
                _require(len(payload) <= MAX_POLICY_BYTES, "Complete policy exceeds byte cap")
                filename = _policy_name(backend, iterations)
                path = Path(policies_dir) / filename
                _atomic_exclusive(path, payload, created)
                saved = path.read_bytes()
                _require(_sha(saved) == _sha(payload), "Saved policy differs after publication")
                loaded = json.loads(saved)
                saved_metrics, saved_diffs, _ = replay_profile(
                    loaded, case, backend, iterations, census)
                _guard(before, before_head)
                replay_seconds = time.perf_counter() - replay_started
                _require(loaded == result and saved_metrics == metrics and saved_diffs == diffs,
                         "Replayed saved policy differs from in-memory policy")
                print(f"DONE backend={backend} iterations={iterations} "
                      f"nash_conv={metrics['nash_conv']:.12g} "
                      f"target_met={metrics['nash_conv'] <= THRESHOLD}", flush=True)
                rows.append({
                    "iterations_requested": iterations, "iterations_completed": iterations,
                    "backend": backend, "algorithm": ALGORITHM,
                    "target_exploitability": None, "threshold": THRESHOLD,
                    "threshold_met": metrics["nash_conv"] <= THRESHOLD,
                    "metrics": metrics, "oracle_metrics": metrics,
                    "actual_metadata": _profile_metadata(result),
                    "scalar_differences": diffs, "worlds": oracle["worlds"],
                    "compatible_pairs": oracle["compatible_pair_count"],
                    "information_rows": oracle["checked_information_sets"],
                    "independent_public_decisions": oracle["public_node_count"],
                    "public_states": result["public_states"],
                    "work_charge": work, "work_limit": fixture.REFERENCE_WORK_CAP,
                    "complete_call_seconds_uncontrolled": complete_seconds,
                    "independent_replay_seconds": replay_seconds,
                    "policy_file": filename, "policy_sha256": _sha(saved),
                    "saved_policy_replayed": True,
                })
        after = fingerprints()
        _require(after == before and _head() == before_head,
                 "Source or HEAD changed during training/replay")
        report = {
            "schema_version": SCHEMA_VERSION, "benchmark_id": BENCHMARK_ID,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "baseline_git_commit": before_head, "python": platform.python_version(),
            "platform": platform.platform(), "source_sha256": before,
            "reference_sha256": reference_sha, "fixture": case,
            "census": fixture.to_jsonable(census),
            "methodology": _methodology(),
            "results": rows,
        }
        report_payload = _canonical(report)
        _require(len(report_payload) <= MAX_REPORT_BYTES, "Benchmark report exceeds byte cap")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        # Validate a staged candidate before publishing the report filename.
        fd, staged_name = tempfile.mkstemp(prefix="." + report_path.name + ".",
                                           suffix=".candidate", dir=report_path.parent)
        staged_path = Path(staged_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(report_payload)
                stream.flush()
                os.fsync(stream.fileno())
            verify_saved_artifact(staged_path, policies_dir)
            _atomic_exclusive(report_path, report_payload, created)
        finally:
            staged_path.unlink(missing_ok=True)
        # Re-verify the published report after the exclusive atomic link.
        verified = verify_saved_artifact(report_path, policies_dir)
        _require(fingerprints() == before and _head() == before_head,
                 "Source/HEAD guard changed after saved verification")
        return verified
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true")
    group.add_argument("--verify", action="store_true")
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--policies-dir", type=Path, default=POLICIES_DIR)
    args = parser.parse_args(argv)
    outcome = (generate(args.report, args.policies_dir) if args.generate else
               verify_saved_artifact(args.report, args.policies_dir))
    print(json.dumps(outcome, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
