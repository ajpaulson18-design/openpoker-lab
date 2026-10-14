"""Bounded acceptance evidence for exceptional matrix-free turn conditioning.

This is a development benchmark for two fixed tiny-support cases. It saves full
policies, independently replays them from the original ranges, and does not make
runtime or memory claims.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import time

from pokerlab.matrix_free_turn import solve_matrix_free_turn
from pokerlab.river_config import RiverConfig
from scripts.benchmark_turn_river_independent import ROOT, source_hashes
from scripts.turn_river_validation import compare_result, replay_policy
from scripts.validate_turn_conditioning_parity import (
    BASE as HISTORICAL_BASE,
    EXPECTED as HISTORICAL_EXPECTED,
    _historical,
)


ALGORITHMS = ("vanilla", "dcfr", "cfrplus")
METRIC_FIELDS = (
    "value_oop", "value_ip", "oop_best_response_value",
    "ip_best_response_value", "oop_best_response_gain",
    "ip_best_response_gain", "nash_conv", "exploitability",
)
TARGET_NASH_CONV = 0.001
ITERATIONS = 20


def _cases():
    config_a = RiverConfig(100, 100, (1.0,), (), 0, False)
    config_b = RiverConfig(20, 20, (1.0,), (), 0, False)
    return (
        {
            "id": "selected-one-world-1e-400",
            "board": "2c7d9hJs",
            "oop": "AsAh:1,3c4c:1e-200",
            "ip": "AsKh:1,5c6c:1e-200",
            "runouts": ("As",), "config": config_a,
            "pruned_oop": "3c4c", "pruned_ip": "5c6c",
        },
        {
            "id": "subnormal-root-fold-2p5-7p5",
            "board": "2c5d9hJc",
            "oop": "AhAs:1,KcKd:5e-324",
            "ip": "QhQs",
            "runouts": ("As",), "config": config_b,
            "pruned_oop": "KcKd", "pruned_ip": "QhQs",
        },
    )


def _canonical_json(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _metrics(result):
    return {field: result[field] for field in METRIC_FIELDS}


def _metric_differences(result, oracle):
    return {field: float(result[field]) - float(oracle[field])
            for field in METRIC_FIELDS}


def _is_known_historical_admission_rejection(error):
    return str(error) in {
        "Selected river branch mass is not representable.",
        "Selected runout joint mass is not representable.",
        "A selected river has unrepresentable conditional probability.",
        "Turn range fallback pair-check budget exceeded.",
        "Ranked river fallback pair-check budget exceeded.",
    } or str(error).startswith((
        "Turn range kernel exceeds ",
        "Matrix-free turn exceeds ",
    ))


def _fingerprints(baseline_dir):
    result = source_hashes()
    result[str(Path(__file__).relative_to(ROOT))] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    parity_path = ROOT / "scripts" / "validate_turn_conditioning_parity.py"
    result[str(parity_path.relative_to(ROOT))] = hashlib.sha256(
        parity_path.read_bytes()
    ).hexdigest()
    result["historical/turn_range_kernel.py"] = hashlib.sha256(
        (baseline_dir / "turn_range_kernel.py").read_bytes()
    ).hexdigest()
    result["historical/matrix_free_turn.py"] = hashlib.sha256(
        (baseline_dir / "matrix_free_turn.py").read_bytes()
    ).hexdigest()
    return result


def _solve(case, oop, ip, algorithm):
    return solve_matrix_free_turn(
        case["board"], oop, ip, case["config"],
        runouts=case["runouts"], iterations=ITERATIONS,
        algorithm=algorithm,
    )


def _replay(result, case, oop, ip):
    oracle = replay_policy(
        result, oop, ip, board=case["board"], config=case["config"],
        runouts=case["runouts"],
    )
    differences = compare_result(result, oracle, tolerance=1e-9)
    return oracle, differences


def _policy_record(directory, name, result):
    path = directory / (name + ".json")
    payload = _canonical_json(result)
    path.write_bytes(payload)
    reread = path.read_bytes()
    if reread != payload:
        raise RuntimeError("Saved policy bytes changed during write: " + path.name)
    return {
        "file": path.name,
        "sha256": hashlib.sha256(reread).hexdigest(),
        "size_bytes": len(reread),
    }


def _saved_policy_replay(directory, record, case, oop, ip, *, strict=True):
    path = directory / record["file"]
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != record["sha256"]:
        raise RuntimeError("Saved policy hash mismatch: " + path.name)
    loaded = json.loads(payload.decode("utf-8"))
    if strict:
        oracle, differences = _replay(loaded, case, oop, ip)
    else:
        oracle = replay_policy(
            loaded, oop, ip, board=case["board"], config=case["config"],
            runouts=case["runouts"],
        )
        differences = _metric_differences(loaded, oracle)
    return oracle, differences


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "benchmarks" / "results" / "turn-conditioned-mass-acceptance-v1.json",
    )
    parser.add_argument(
        "--policy-dir", type=Path,
        default=ROOT / "benchmarks" / "results" / "turn-conditioned-mass-acceptance-policies-v1",
    )
    args = parser.parse_args(argv)
    baseline_dir = args.baseline_dir.resolve()
    cases = _cases()
    old_solve = _historical(baseline_dir)
    fingerprints_before = _fingerprints(baseline_dir)

    args.policy_dir.mkdir(parents=True, exist_ok=True)
    (args.policy_dir / ".gitattributes").write_bytes(b"*.json text eol=lf\n")

    profile_results = {}
    case_rows = []
    old_rows = []
    for case in cases:
        case_config = case["config"].to_dict()
        case_record = {
            "id": case["id"], "board": case["board"],
            "oop": case["oop"], "ip": case["ip"],
            "runouts": list(case["runouts"]), "config": case_config,
            "iterations_requested": ITERATIONS,
        }
        current_records = {}
        pruned_records = {}
        case_results = {}
        for algorithm in ALGORITHMS:
            options = {"iterations": ITERATIONS, "algorithm": algorithm}
            started = time.perf_counter()
            try:
                old_result = old_solve(
                    case["board"], case["oop"], case["ip"], case["config"],
                    runouts=case["runouts"], **options,
                )
                old_seconds = time.perf_counter() - started
                old_oracle = replay_policy(
                    old_result, case["oop"], case["ip"],
                    board=case["board"], config=case["config"],
                    runouts=case["runouts"],
                )
                old_differences = _metric_differences(old_result, old_oracle)
                try:
                    compare_result(old_result, old_oracle, tolerance=1e-9)
                    old_replay_within_tolerance = True
                    old_replay_error = None
                except ValueError as exc:
                    old_replay_within_tolerance = False
                    old_replay_error = str(exc)
                old_record = _policy_record(
                    args.policy_dir,
                    f"{case['id']}-{algorithm}-historical-original",
                    old_result,
                )
                # Re-read and independently replay historical output too when
                # the old implementation admitted the case.
                old_saved_oracle, old_saved_differences = _saved_policy_replay(
                    args.policy_dir, old_record, case, case["oop"], case["ip"],
                    strict=False,
                )
                if old_saved_differences != old_differences:
                    raise RuntimeError("Historical saved-policy replay changed metrics.")
                old_rows.append({
                    "scenario": case["id"], "algorithm": algorithm,
                    "status": ("admitted-replay-passed" if old_replay_within_tolerance
                               else "admitted-replay-mismatch"),
                    "completed_iterations": old_result["iterations"],
                    "call_seconds_uncontrolled": old_seconds,
                    "metric_differences": old_differences,
                    "replay_within_1e-9": old_replay_within_tolerance,
                    "replay_comparison_error": old_replay_error,
                    "metrics": _metrics(old_result),
                    "oracle_metrics": _metrics(old_oracle),
                    "verified_worlds": old_oracle["worlds"],
                    "verified_information_sets": old_oracle["checked_information_sets"],
                    "target_nash_conv": TARGET_NASH_CONV,
                    "target_met": old_oracle["nash_conv"] <= TARGET_NASH_CONV,
                    "policy": old_record,
                })
            except Exception as exc:  # Record historical rejection or replay failure.
                old_seconds = time.perf_counter() - started
                old_rows.append({
                    "scenario": case["id"], "algorithm": algorithm,
                    "status": (
                        "admission-rejected"
                        if _is_known_historical_admission_rejection(exc)
                        else "historical-call-or-replay-failed"
                    ),
                    "error_type": type(exc).__name__, "error": str(exc),
                    "call_seconds_uncontrolled": old_seconds,
                })

            started = time.perf_counter()
            current = _solve(case, case["oop"], case["ip"], algorithm)
            current_seconds = time.perf_counter() - started
            if current.get("conditioning_mode") != (
                    "scaled-branch-mass-and-conditioned-folds"):
                raise RuntimeError("Current result lacks exceptional conditioning metadata.")
            if current["compatible_world_count"] != 1:
                raise RuntimeError("Current result did not retain exactly one physical world.")
            oracle, differences = _replay(current, case, case["oop"], case["ip"])
            if oracle["river_probabilities"] != {"As": 1.0}:
                raise RuntimeError("Independent replay found an unexpected river law.")
            current_name = f"{case['id']}-{algorithm}-current-original"
            current_record = _policy_record(args.policy_dir, current_name, current)
            current_records[algorithm] = current_record
            case_results[algorithm] = current

            pruned = _solve(case, case["pruned_oop"], case["pruned_ip"], algorithm)
            pruned_oracle, pruned_differences = _replay(
                pruned, case, case["pruned_oop"], case["pruned_ip"],
            )
            pruned_name = f"{case['id']}-{algorithm}-current-pruned-equivalent"
            pruned_record = _policy_record(args.policy_dir, pruned_name, pruned)
            pruned_records[algorithm] = pruned_record
            strategy_equal = current["strategy"] == pruned["strategy"]
            metric_differences = _metric_differences(current, pruned)
            if not strategy_equal:
                raise RuntimeError("Original-range strategy differs from pruned equivalent.")
            if any(difference != 0.0 for difference in metric_differences.values()):
                raise RuntimeError("Original/pruned diagnostic scalar differs exactly.")
            case_rows.append({
                "scenario": case["id"], "algorithm": algorithm,
                "profile_kind": "current-original-ranges",
                "iterations_completed": current["iterations"],
                "call_seconds_uncontrolled": current_seconds,
                "metrics": _metrics(current), "oracle_metrics": _metrics(oracle),
                "scalar_differences": differences,
                "verified_worlds": oracle["worlds"],
                "verified_compatible_pairs": oracle["compatible_pair_count"],
                "verified_information_sets": oracle["checked_information_sets"],
                "runout_probabilities": oracle["river_probabilities"],
                "policy_metadata": {
                    "solver_version": current["solver_version"],
                    "runout_mode": current["runout_mode"],
                    "runouts": current["runouts"],
                    "reachable_runouts": current["reachable_runouts"],
                    "compatible_world_count": current["compatible_world_count"],
                    "info_sets": current["info_sets"],
                    "worlds_materialized": current["worlds_materialized"],
                },
                "target_nash_conv": TARGET_NASH_CONV,
                "target_met": oracle["nash_conv"] <= TARGET_NASH_CONV,
                "policy": current_record,
                "pruned_equivalent": {
                    "policy": pruned_record,
                    "strategy_equal": strategy_equal,
                    "metric_differences_vs_original": metric_differences,
                    "oracle_scalar_differences": pruned_differences,
                    "metrics": _metrics(pruned),
                    "oracle_metrics": _metrics(pruned_oracle),
                    "target_met": pruned_oracle["nash_conv"] <= TARGET_NASH_CONV,
                },
            })

        profile_results[case["id"]] = {
            "case": case_record,
            "current_policies": current_records,
            "pruned_policies": pruned_records,
            "results_by_algorithm": case_results,
        }

    # Reload every saved current/pruned policy and replay it from disk so the
    # policy-byte hashes correspond to the evidence retained in the report.
    saved_replays = []
    for case in cases:
        entry = profile_results[case["id"]]
        for algorithm in ALGORITHMS:
            for kind, ranges, record in (
                ("original", (case["oop"], case["ip"]),
                 entry["current_policies"][algorithm]),
                ("pruned-equivalent", (case["pruned_oop"], case["pruned_ip"]),
                 entry["pruned_policies"][algorithm]),
            ):
                oracle, differences = _saved_policy_replay(
                    args.policy_dir, record, case, *ranges,
                )
                saved_replays.append({
                    "scenario": case["id"], "algorithm": algorithm,
                    "profile_kind": kind, "policy": record,
                    "verified_worlds": oracle["worlds"],
                    "verified_information_sets": oracle["checked_information_sets"],
                    "scalar_differences": differences,
                })

    if _fingerprints(baseline_dir) != fingerprints_before:
        raise RuntimeError("Source or historical files changed during acceptance run.")

    # Do not serialize in-memory result objects into the report; policies live
    # as separately hashed complete artifacts.
    for entry in profile_results.values():
        del entry["results_by_algorithm"]
    report = {
        "schema_version": 1,
        "benchmark_id": "turn-conditioned-mass-exceptional-acceptance-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "baseline_git_commit": subprocess.check_output(
            ["git", "rev-parse", HISTORICAL_BASE], cwd=ROOT, text=True,
        ).strip(),
        "historical_source_sha256": HISTORICAL_EXPECTED,
        "source_sha256_before_and_after": fingerprints_before,
        "iterations": ITERATIONS,
        "algorithms": list(ALGORITHMS),
        "target_nash_conv": TARGET_NASH_CONV,
        "cases": [profile_results[case["id"]]["case"] for case in cases],
        "current_results": case_rows,
        "historical_results": old_rows,
        "saved_policy_replays": saved_replays,
        "methodology": {
            "correctness": "Every current original-range and pruned-equivalent complete policy is saved as UTF-8 LF JSON, byte-hash checked, reloaded and independently replayed with physical Fraction weighting, numeric betting rules and legal information-set best responses. The eight replay metrics and physical-world/pair/information-set counts are recorded.",
            "historical": "The archived adapter and turn kernel are fingerprinted from the pre-fix baseline. Historical admission errors are retained; admitted policies are independently replayed and all eight metric differences are recorded without requiring validation to pass.",
            "comparison": "Original weighted ranges are compared with their physically equivalent one-world pruned ranges by exact serialized strategy rows and all eight diagnostic scalar differences.",
            "timing": "Single complete-call observations are uncontrolled and descriptive only; no speed, memory, or RSS claim is made.",
            "quality": "The predeclared 0.001-chip NashConv threshold is reported for every profile, including misses.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
