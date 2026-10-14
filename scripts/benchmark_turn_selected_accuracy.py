"""Fixed-budget independent quality replay for the selected-runout turn game.

Six complete CFR+ calls compare the two existing backends. This records
accuracy in one finite conditional game; it is not a convergence theorem,
speed comparison, memory measurement, or unrestricted Hold'em claim.
"""
import argparse
import hashlib
import json
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from pokerlab.river_config import RiverConfig
from scripts.benchmark_turn_river_independent import CONFIG, ROOT, solve, source_hashes
from scripts.turn_river_validation import compare_result, replay_policy


ITERATIONS = (1_000, 3_000, 10_000)
BACKENDS = ("materialized", "matrix-free")
BENCHMARK_NASH_CONV_THRESHOLD = 0.001
EXPECTED_CASE = {
    "id": "two-conditioned-runouts-asymmetric-multisize",
    "board": "Js8d4c2h",
    "oop": "AsAh:0.5,KsKh:1",
    "ip": "AcAd:1,KcKd:0.75",
    "config": {
        "pot": 100, "effective_stack": [220, 120],
        "bet_sizes": [0.5, 1.0], "raise_sizes": [0.5],
        "max_raises": 1, "include_all_in": True,
    },
    "river_config": {
        "pot": 100, "effective_stack": [220, 120],
        "bet_sizes": [0.75, 1.25], "raise_sizes": [0.5],
        "max_raises": 1, "include_all_in": True,
    },
    "runouts": ["3c", "5h"],
}
EXPECTED_WORLDS = 8
EXPECTED_COMPATIBLE_PAIRS = 4
EXPECTED_INFORMATION_SETS = 138
EXPECTED_PUBLIC_STATES = 188
EXPECTED_MATERIALIZED_TRAVERSAL_NODES = 41
MAX_MATERIALIZED_WORLD_NODE_WORK = 30_000_000


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def frozen_case():
    specification = json.loads(CONFIG.read_text(encoding="utf-8"))
    matches = [case for case in specification["scenarios"]
               if case.get("id") == EXPECTED_CASE["id"]]
    if len(matches) != 1:
        raise ValueError("Expected exactly one frozen selected-turn fixture")
    case = matches[0]
    for field, value in EXPECTED_CASE.items():
        if case.get(field) != value:
            raise ValueError("Selected-turn fixture changed from the predeclared case: " + field)
    return case


def _fingerprints():
    values = source_hashes()
    runner = Path(__file__).resolve()
    values[runner.relative_to(ROOT).as_posix()] = _sha256(runner.read_bytes())
    return values


def _expected_work(backend, iterations):
    """Return the fixed-call structural work charge for this exact fixture."""
    if backend == "matrix-free":
        # max hand count 2, kernel public states 188, three CFR+ passes,
        # and one final diagnostic (three modeled passes).
        return 2 * EXPECTED_PUBLIC_STATES * (iterations * 3 + 3)
    if backend == "materialized":
        return (EXPECTED_WORLDS * EXPECTED_MATERIALIZED_TRAVERSAL_NODES *
                iterations * 3)
    raise ValueError("Unknown selected-turn backend")


def validate_profile_metadata(result, case, backend, iterations):
    """Hard gates for the selected game and the backend-specific work model."""
    if result.get("algorithm") != "cfrplus":
        raise ValueError("Selected-turn profile must use CFR+")
    if result.get("iterations") != iterations:
        raise ValueError("Selected-turn profile did not complete the requested fixed sweeps")
    if "convergence" in result:
        raise ValueError("Fixed-budget selected-turn profile unexpectedly has a stop target")
    expected_board = [case["board"][index:index + 2]
                      for index in range(0, len(case["board"]), 2)]
    if result.get("board") != expected_board:
        raise ValueError("Selected-turn result board differs from the fixture")
    expected_runouts = list(case["runouts"])
    if result.get("runouts") != expected_runouts:
        raise ValueError("Selected-turn result runouts differ from the fixture")
    if result.get("runout_mode") != "conditioned-subset":
        raise ValueError("Selected-turn result must preserve conditioned-subset semantics")
    if result.get("reachable_runouts") != expected_runouts:
        raise ValueError("Selected-turn reachable runouts differ from the physical fixture")

    turn = RiverConfig.from_dict(case["config"]).to_dict()
    river = RiverConfig.from_dict(case["river_config"]).to_dict()
    if result.get("config") != turn or result.get("turn_config") != turn:
        raise ValueError("Selected-turn serialized turn configuration changed")
    if result.get("river_config") != river:
        raise ValueError("Selected-turn serialized river configuration changed")
    if result.get("street_configs") != {"turn": turn, "river": river}:
        raise ValueError("Selected-turn street configurations lost their distinct river sizing")

    if ("compatible_pairs" in result and
            result["compatible_pairs"] != EXPECTED_COMPATIBLE_PAIRS):
        raise ValueError("Selected-turn compatible-pair count differs from the fixture")
    if result.get("info_sets") != EXPECTED_INFORMATION_SETS:
        raise ValueError("Selected-turn information-set count differs from the fixture")
    if result.get("public_states") != EXPECTED_PUBLIC_STATES:
        raise ValueError("Selected-turn public-state count differs from the fixture")

    if backend == "matrix-free":
        if result.get("execution_backend") != "matrix-free-ranked-python":
            raise ValueError("Matrix-free profile reports the wrong backend")
        if result.get("compatible_world_count") != EXPECTED_WORLDS:
            raise ValueError("Matrix-free compatible-world count differs from the fixture")
        if result.get("worlds_materialized") != 0:
            raise ValueError("Matrix-free profile materialized physical worlds")
        usage = result.get("resource_usage")
        if not isinstance(usage, dict):
            raise ValueError("Matrix-free resource usage is missing")
        if usage.get("hand_counts") != [2, 2]:
            raise ValueError("Matrix-free hand counts differ from the fixture")
        if usage.get("compatible_world_count") != EXPECTED_WORLDS:
            raise ValueError("Matrix-free resource world count differs from the fixture")
        if usage.get("kernel_public_states") != EXPECTED_PUBLIC_STATES:
            raise ValueError("Matrix-free kernel public-state count differs from the fixture")
        expected = _expected_work(backend, iterations)
        if usage.get("hand_state_pass_work") != expected:
            raise ValueError("Matrix-free full-request work charge differs from its declared model")
        limits = usage.get("limits")
        if not isinstance(limits, dict):
            raise ValueError("Matrix-free resource limits are missing")
        if limits.get("hand_state_pass_work") != 30_000_000:
            raise ValueError("Matrix-free hand-state work cap differs from the fixed 30 million limit")
        counts = dict(usage)
        counts["public_states"] = result.get("public_states")
        counts["public_nodes"] = result.get("public_nodes")
        for name in ("hand_state_pass_work", "info_action_slots", "fallback_pair_checks",
                     "hand_slots", "public_states", "public_nodes"):
            if type(counts.get(name)) is not int or type(limits.get(name)) is not int:
                raise ValueError("Matrix-free resource count/limit is invalid: " + name)
            if counts[name] < 0 or counts[name] > limits[name]:
                raise ValueError("Matrix-free resource cap exceeded: " + name)
        if "stable_root_fold_pair_checks" in usage:
            checks = usage.get("stable_root_fold_pair_checks")
            limit = usage.get("stable_root_fold_pair_limit")
            if (type(checks) is not int or checks < 0 or
                    type(limit) is not int or limit < 0 or checks > limit):
                raise ValueError("Matrix-free stable-root pair cap exceeded")
    elif backend == "materialized":
        if result.get("execution_backend") != "public-batched-python":
            raise ValueError("Materialized profile must use public-batched traversal")
        if result.get("diagnostics_backend") != "public-batched-python":
            raise ValueError("Materialized profile must use public-batched diagnostics")
        if result.get("worlds") != EXPECTED_WORLDS:
            raise ValueError("Materialized physical-world count differs from the fixture")
        if result.get("compatible_pairs") != EXPECTED_COMPATIBLE_PAIRS:
            raise ValueError("Materialized compatible-pair count differs from the fixture")
        if result.get("world_traversal_nodes") != EXPECTED_MATERIALIZED_TRAVERSAL_NODES:
            raise ValueError("Materialized per-world traversal-node count differs from the fixture")
        if result.get("public_state_limit") != 250_000:
            raise ValueError("Materialized public-state limit changed")
        if result["public_states"] > result["public_state_limit"]:
            raise ValueError("Materialized public-state cap exceeded")
        if _expected_work(backend, iterations) > MAX_MATERIALIZED_WORLD_NODE_WORK:
            raise ValueError("Materialized full-request world-node budget exceeds 30 million")
    else:
        raise ValueError("Unknown selected-turn backend")


def _replay(result, case):
    return replay_policy(
        result, case["oop"], case["ip"], board=case["board"],
        config=case["config"], river_config=case["river_config"],
        runouts=case["runouts"],
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks" / "results" /
                        "turn-selected-accuracy-v1.json")
    parser.add_argument("--policies-dir", type=Path, default=ROOT / "benchmarks" / "results" /
                        "turn-selected-accuracy-policies-v1")
    args = parser.parse_args(argv)

    case = frozen_case()
    before = _fingerprints()
    baseline_commit = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                              cwd=ROOT, text=True).strip()
    args.policies_dir.mkdir(parents=True, exist_ok=True)
    (args.policies_dir / ".gitattributes").write_bytes(b"*.json text eol=lf\n")
    rows = []
    for backend in BACKENDS:
        for iterations in ITERATIONS:
            started = time.perf_counter()
            result = solve(case, backend, "cfrplus", iterations)
            complete_seconds = time.perf_counter() - started
            validate_profile_metadata(result, case, backend, iterations)

            oracle = _replay(result, case)
            differences = compare_result(result, oracle, tolerance=1e-9)
            if (oracle["worlds"] != EXPECTED_WORLDS or
                    oracle["compatible_pair_count"] != EXPECTED_COMPATIBLE_PAIRS or
                    oracle["checked_information_sets"] != EXPECTED_INFORMATION_SETS):
                raise ValueError("Independent replay counts differ from the frozen fixture")

            name = f"{case['id']}-{backend}-{iterations}.json"
            payload = _canonical_json(result)
            path = args.policies_dir / name
            path.write_bytes(payload)
            saved = path.read_bytes()
            policy_hash = _sha256(saved)
            if saved != payload:
                raise RuntimeError("Saved policy bytes differ from the complete solve")
            loaded = json.loads(saved)
            validate_profile_metadata(loaded, case, backend, iterations)
            saved_oracle = _replay(loaded, case)
            saved_differences = compare_result(loaded, saved_oracle, tolerance=1e-9)
            if loaded != result or saved_differences != differences:
                raise ValueError("Post-save replay differs from the accepted in-memory policy")

            rows.append({
                "scenario": case["id"], "backend": backend,
                "algorithm": "cfrplus", "iterations_requested": iterations,
                "iterations_completed": result["iterations"],
                "configured_solver_target_exploitability": None,
                "benchmark_nash_conv_threshold": BENCHMARK_NASH_CONV_THRESHOLD,
                "benchmark_threshold_met": oracle["nash_conv"] <= BENCHMARK_NASH_CONV_THRESHOLD,
                "metrics": {field: oracle[field] for field in (
                    "value_oop", "value_ip", "oop_best_response_value",
                    "ip_best_response_value", "oop_best_response_gain",
                    "ip_best_response_gain", "nash_conv", "exploitability")},
                "scalar_differences": differences,
                "verified_worlds": oracle["worlds"],
                "verified_compatible_pairs": oracle["compatible_pair_count"],
                "verified_information_sets": oracle["checked_information_sets"],
                "public_states": result["public_states"],
                "world_traversal_nodes": result.get("world_traversal_nodes"),
                "worlds_materialized": result.get(
                    "worlds_materialized", result.get("worlds", 0)),
                "work_charge": _expected_work(backend, iterations),
                "complete_call_seconds_uncontrolled": complete_seconds,
                "policy_file": name, "policy_sha256": policy_hash,
                "saved_policy_replayed": True,
            })
            print(backend, iterations,
                  f"nash_conv={oracle['nash_conv']:.12g}", flush=True)

    if _fingerprints() != before:
        raise RuntimeError("Production, helper, oracle, fixture or runner changed during measurement")
    report = {
        "schema_version": 1,
        "benchmark_id": "turn-selected-accuracy-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_git_commit": baseline_commit,
        "python": platform.python_version(), "platform": platform.platform(),
        "source_sha256": before,
        "fixture": case,
        "methodology": {
            "design": "Both existing turn backends, CFR+ only, fixed complete calls at 1000/3000/10000 sweeps; six profiles retained.",
            "conditioning": "The exact two selected rivers condition the full private-pair/runout game jointly. Both the separate turn and river sizing configurations are supplied to solve and replay.",
            "validation": "Every policy is independently replayed from physical worlds, numeric betting rules, independent best-five ranks and exact legal visible-information best responses; eight metrics and core counts are checked before and after saving.",
            "threshold": "The 0.001-chip NashConv value is a predeclared reporting benchmark threshold; fixed calls configure no solver stopping target.",
            "resource_models": "Matrix-free charges max hand count × kernel public states × (three CFR+ passes plus final diagnostics). Materialized charges selected worlds × per-world traversal nodes × three CFR+ passes. Public-state aggregate counts are not substituted for per-world traversal nodes.",
            "limitations": "One selected two-river finite turn game; the result measures these saved policies and does not establish general convergence, a closed-form equilibrium, speed, allocation, RSS, or unrestricted Hold'em quality.",
            "timing": "One complete solve timing per profile on a shared host; uncontrolled and not a performance claim.",
        },
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_json(report))
    print("Verified and saved", len(rows), "selected-turn profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
