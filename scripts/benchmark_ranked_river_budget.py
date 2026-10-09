"""Probe ranked versus sparse river solving at a higher admitted budget.

Runs only the 256-hands-per-player synthetic case at 40 iterations. It measures
complete solve calls with three interleaved repeats and leaves solver resource
guards unchanged; rejected calls are recorded as such.
"""
import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts import benchmark_ranked_river_solver as base
from scripts.benchmark_turn_solver import git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
REPEATS = 3
ITERATIONS = 40
BACKENDS = ("sparse", "ranked")
ALGORITHMS = ("dcfr", "cfrplus")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(case):
    case = dict(case)
    case["iterations"] = ITERATIONS
    rows = []
    for algorithm in ALGORITHMS:
        samples = {backend: [] for backend in BACKENDS}
        latest = {}
        rejected = {}
        for repeat in range(REPEATS):
            order = list(BACKENDS)
            if repeat % 2:
                order.reverse()
            for backend in order:
                try:
                    elapsed, result = base.timed_solve(case, algorithm, backend)
                except ValueError as exc:
                    rejected[backend] = str(exc)
                    print(f"{algorithm} {backend} rejected: {exc}", flush=True)
                    continue
                samples[backend].append(elapsed)
                latest[backend] = result
                print(f"{algorithm} {backend} repeat {repeat + 1}: {elapsed:.4f}s "
                      f"worlds={result['worlds']} "
                      f"exploitability={result['exploitability']:.8g}", flush=True)
        statuses = {backend: ("admitted" if len(samples[backend]) == REPEATS else "rejected")
                    for backend in BACKENDS}
        row = {"range_size_per_player": case["range_size_per_player"],
               "iterations": ITERATIONS, "algorithm": algorithm,
               "repeat_count": REPEATS,
               "status": statuses,
               "rejection_reasons": rejected,
               "whole_call_seconds": {
                   backend: ({"samples": samples[backend],
                              "median": statistics.median(samples[backend])}
                             if samples[backend] else None)
                   for backend in BACKENDS}}
        if all(status == "admitted" for status in statuses.values()):
            row["speedup_ranked_vs_sparse"] = (
                statistics.median(samples["sparse"]) /
                statistics.median(samples["ranked"]))
            row["solver_counts"] = {
                backend: {field: latest[backend][field] for field in
                          ("deals", "worlds", "public_states", "public_nodes",
                           "info_sets", "chance_nodes", "world_traversal_nodes",
                           "tree_actions", "iterations")}
                for backend in BACKENDS}
            row["work_guard_usage"] = {
                backend: {
                    "candidate_pair_iteration_work": (
                        case["range_size_per_player"] ** 2 * ITERATIONS),
                    "world_iteration_work": latest[backend]["worlds"] * ITERATIONS,
                    "world_node_iteration_work": (
                        latest[backend]["worlds"] * latest[backend]["world_traversal_nodes"] *
                        ITERATIONS * (3 if algorithm == "cfrplus" else 1)),
                    "limits": {"candidate_pairs_times_iterations": 3_000_000,
                               "worlds_times_iterations": 3_000_000,
                               "worlds_nodes_iterations_passes": 30_000_000},
                } for backend in BACKENDS}
            row["gap_metrics"] = {
                backend: {field: latest[backend][field] for field in base.METRICS}
                for backend in BACKENDS}
            row["metric_comparison"] = base.metric_diffs(latest["sparse"], latest["ranked"])
            row["policy_comparison"] = base.strategy_diff(latest["sparse"], latest["ranked"])
        rows.append(row)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/results/ranked-river-budget-v1.json")
    args = parser.parse_args(argv)
    case = base.make_case(256)
    case["iterations"] = ITERATIONS
    sources = [Path(__file__).resolve(), Path(base.__file__).resolve(),
               ROOT / "scripts/benchmark_turn_solver.py"]
    sources.extend(ROOT / "pokerlab" / (name + ".py") for name in (
        "postflop_solver", "cards", "cfr", "cfr_plus", "planned_cfr",
        "public_cfr", "public_diagnostics", "ranked_river", "river_config", "river_tree"))
    before = {str(path.relative_to(ROOT)): sha256(path) for path in sources}
    rows = run(case)
    after = {str(path.relative_to(ROOT)): sha256(path) for path in sources}
    if before != after:
        raise RuntimeError("Calculation source changed during benchmark; discard measurements.")
    inputs = {key: case[key] for key in
              ("board", "range_size_per_player", "range_spec", "config", "iterations")}
    report = {
        "schema_version": 1,
        "benchmark_id": "ranked-river-budget-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "metadata": {"revision": git_revision(None), "worktree_dirty": worktree_dirty(),
                     "python": sys.version, "python_version": platform.python_version(),
                     "platform": platform.platform(),
                     "command": "python -m scripts.benchmark_ranked_river_budget",
                     "source_sha256": before,
                     "input_sha256": hashlib.sha256(json.dumps(
                         inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                     "configuration": {"algorithms": ALGORITHMS,
                                       "backends": BACKENDS,
                                       "iterations": ITERATIONS,
                                       "repeats": REPEATS,
                                       "tracemalloc": "skipped"}},
        "input": inputs,
        "methodology": {
            "timing": "Three interleaved complete solve_postflop calls per backend and algorithm, including enumeration, training, exact diagnostics, and result assembly.",
            "memory": "Skipped to avoid repeating traced profiling; peak memory is not measured in this probe.",
            "guards": "Normal solver admission guards remain enabled. Rejected calls are recorded with the error and are not retimed or capped.",
            "accuracy": "Finite-iteration values and best-response diagnostics; no equilibrium or commercial-solver parity claim.",
        },
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(f"Wrote {len(rows)} cases to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
