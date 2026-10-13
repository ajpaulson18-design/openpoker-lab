"""Source-frozen turn/river quality measurements with independent policy replay.

The oracle is outside the complete-solve timing interval. Every measured policy
is replayed; algorithm convergence is a separate question from scalar agreement.
"""
import argparse
import gc
import hashlib
import json
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from pokerlab.matrix_free_river import solve_matrix_free_river
from pokerlab.matrix_free_turn import solve_matrix_free_turn
from pokerlab.postflop_solver import solve_postflop
from scripts.turn_river_validation import compare_result, replay_policy

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "benchmarks" / "turn-river-quality-v1.json"
ALGORITHMS = ("vanilla", "dcfr", "cfrplus")
BACKENDS = ("materialized", "matrix-free")


def source_hashes():
    paths = list((ROOT / "pokerlab").glob("*.py"))
    paths += [ROOT / "scripts" / name for name in (
        "turn_river_validation.py", "preflop_validation.py",
        "benchmark_turn_river_independent.py")]
    paths.append(CONFIG)
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}


def solve(case, backend, algorithm, iterations):
    options = {key: case[key] for key in ("river_config", "runouts") if key in case}
    if backend == "materialized":
        solver = solve_postflop
        options.update(traversal="public-batched", diagnostics="public-batched")
    else:
        solver = solve_matrix_free_turn if len(case["board"]) == 8 else solve_matrix_free_river
    return solver(case["board"], case["oop"], case["ip"], case["config"],
                  iterations=iterations, algorithm=algorithm, **options)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", nargs="+", type=int, default=[20, 100, 300])
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 10 or any(not 10 <= n <= 10000 for n in args.iterations):
        parser.error("Use 1-10 repeats and iteration ceilings from 10 through 10000.")
    specification = json.loads(CONFIG.read_text(encoding="utf-8"))
    before = source_hashes()
    jobs = tuple((backend, algorithm) for backend in BACKENDS for algorithm in ALGORITHMS)
    rows = []
    for case in specification["scenarios"]:
        for iterations in args.iterations:
            samples = {job: [] for job in jobs}
            replay_samples = {job: [] for job in jobs}
            payloads = {}
            checks = {}
            for repeat in range(args.repeats):
                ordered = jobs[repeat % len(jobs):] + jobs[:repeat % len(jobs)]
                for backend, algorithm in ordered:
                    job = (backend, algorithm)
                    gc.collect()
                    started = time.perf_counter()
                    result = solve(case, backend, algorithm, iterations)
                    payload = json.dumps(result, sort_keys=True, allow_nan=False)
                    samples[job].append(time.perf_counter() - started)
                    if job in payloads and payloads[job] != payload:
                        raise RuntimeError("Repeated solve changed the complete payload.")
                    payloads[job] = payload
                    replay_started = time.perf_counter()
                    oracle = replay_policy(
                        result, case["oop"], case["ip"], board=case["board"],
                        config=case["config"],
                        **{key: case[key] for key in ("river_config", "runouts") if key in case},
                    )
                    differences = compare_result(result, oracle, tolerance=1e-9)
                    replay_samples[job].append(time.perf_counter() - replay_started)
                    checks[job] = (result, oracle, differences)
                    print(case["id"], iterations, backend, algorithm,
                          f"{samples[job][-1]:.4f}s gap={oracle['nash_conv']:.9g}", flush=True)
            for backend, algorithm in jobs:
                job = (backend, algorithm)
                result, oracle, differences = checks[job]
                rows.append({
                    "scenario": case["id"], "backend": backend,
                    "algorithm": algorithm, "iterations": iterations,
                    "complete_call_seconds": samples[job],
                    "complete_call_median_seconds": statistics.median(samples[job]),
                    "independent_replay_seconds": replay_samples[job],
                    "scalar_differences": differences,
                    "metrics": {field: result[field] for field in (
                        "value_oop", "value_ip", "oop_best_response_value",
                        "ip_best_response_value", "nash_conv", "exploitability")},
                    "verified_worlds": oracle["worlds"],
                    "verified_information_sets": oracle["checked_information_sets"],
                    "quality_target_nash_conv": 0.001,
                    "quality_target_met": oracle["nash_conv"] <= 0.001,
                    "oracle": {key: oracle[key] for key in (
                        "value_oop", "oop_best_response_value", "ip_best_response_value",
                        "nash_conv", "exploitability")},
                })
    if source_hashes() != before:
        raise RuntimeError("Source/specification changed during measurement; discard the run.")
    report = {
        "schema_version": 1,
        "benchmark_id": "turn-river-independent-replay-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": platform.platform(),
        "source_sha256": before, "fixtures": specification,
        "methodology": {
            "timing": "Rotating repeated complete solve plus deterministic JSON encoding; independent replay timed separately.",
            "memory": "Not measured; no memory/RSS or storage performance claim.",
            "correctness": "Every full serialized policy replayed from independent physical deals, numeric betting rules, best-five ranks and legal information-set BRs, absolute tolerance 1e-9 chips.",
            "quality": "Predeclared 0.001-chip NashConv target for each finite fixture; all misses retained. Equal iterations are not equal computation budgets.",
            "limitations": "Synthetic small ranges and finite actions; conditioned rivers are not unconditional deck results. Binary64 arithmetic agreement is not an interval proof or commercial parity.",
        },
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
