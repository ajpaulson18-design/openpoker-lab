"""Benchmark complete matrix-free river solves against materialized worlds.

Small ranges compare identical finite games and iteration budgets. The full
range probe measures only the matrix-free API; the legacy API is invoked once
at its minimum iteration count to record its existing admission rejection.
"""
import argparse
import gc
import hashlib
import itertools
import json
import math
import platform
import statistics
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

from pokerlab.cards import DECK
from pokerlab.matrix_free_river import solve_matrix_free_river
from pokerlab.postflop_solver import solve_postflop
from pokerlab.river_config import RiverConfig
from scripts.benchmark_turn_solver import git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
BOARD = "2c7d9hJsKd"
CONFIG = {"pot": 100.0, "effective_stack": 200.0,
          "bet_sizes": [0.75], "raise_sizes": [],
          "max_raises": 0, "include_all_in": False}
SMALL_SIZES = (128, 256)
SMALL_ITERATIONS = {128: 50, 256: 40}
ALGORITHMS = ("dcfr", "cfrplus")
BACKENDS = ("materialized-ranked", "matrix-free")
REPEATS = 3
FULL_ITERATIONS = (10, 50, 100)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_case(count):
    board = tuple(BOARD[index:index + 2] for index in range(0, len(BOARD), 2))
    combos = list(itertools.combinations((card for card in DECK if card not in board), 2))
    def side(player):
        stride = 37 if player == 0 else 53
        start = count * 11 + (0 if player == 0 else 19)
        hands = [tuple(sorted(combos[(start + i * stride) % len(combos)]))
                 for i in range(count)]
        cycle = (1.0, 0.5, 0.75, 0.25, 0.125)
        weights = [cycle[(i + 2 * player) % len(cycle)] for i in range(count)]
        tokens = [{"hand": "".join(hand), "weight": weight}
                  for hand, weight in zip(hands, weights)]
        expression = ",".join(item["hand"] + ":" + str(item["weight"])
                               for item in tokens)
        return expression, tokens
    oop, oop_spec = side(0)
    ip, ip_spec = side(1)
    return {"range_size_per_player": count, "board": BOARD,
            "config": CONFIG, "iterations": SMALL_ITERATIONS[count],
            "algorithm": None, "oop": oop, "ip": ip,
            "ranges": {"oop": oop_spec, "ip": ip_spec}}


def _solve(case, backend, algorithm, iterations=None):
    budget = case["iterations"] if iterations is None else iterations
    if backend == "matrix-free":
        return solve_matrix_free_river(case["board"], case["oop"], case["ip"],
                                       RiverConfig.from_dict(case["config"]), iterations=budget,
                                       algorithm=algorithm)
    return solve_postflop(case["board"], case["oop"], case["ip"], case["config"],
                          iterations=budget, algorithm=algorithm,
                          traversal="public-batched", diagnostics="public-batched",
                          terminal_backend="ranked")


def timed_solve(case, backend, algorithm, iterations=None):
    gc.collect()
    started = time.perf_counter()
    result = _solve(case, backend, algorithm, iterations)
    return time.perf_counter() - started, result


def _profile_diff(left, right):
    key = lambda row: (row["player"], row["hand"], row["street"],
                       tuple(row["board"]), tuple(row["history"]))
    rows_left = {key(row): row for row in left["strategy"]}
    rows_right = {key(row): row for row in right["strategy"]}
    if rows_left.keys() != rows_right.keys():
        return {"same_information_sets": False,
                "left_rows": len(rows_left), "right_rows": len(rows_right),
                "max_probability_abs_difference": None}
    gap = 0.0
    for row_key in rows_left:
        actions0, actions1 = rows_left[row_key]["actions"], rows_right[row_key]["actions"]
        if len(actions0) != len(actions1):
            return {"same_information_sets": False,
                    "left_rows": len(rows_left), "right_rows": len(rows_right),
                    "max_probability_abs_difference": None}
        for action0, action1 in zip(actions0, actions1):
            gap = max(gap, abs(action0["probability"] - action1["probability"]))
    return {"same_information_sets": True, "rows": len(rows_left),
            "max_probability_abs_difference": gap}


METRICS = ("value_oop", "oop_best_response_value", "ip_best_response_value",
           "nash_conv", "exploitability")


def _metrics(left, right):
    differences = {field: abs(left[field] - right[field]) for field in METRICS}
    return {"absolute_differences": differences,
            "max_absolute_difference_chips": max(differences.values()),
            "tolerance_chips": 1e-8,
            "within_tolerance": all(math.isfinite(value) and value <= 1e-8
                                     for value in differences.values())}


def _counts(result):
    fields = ("deals", "compatible_pairs", "worlds", "worlds_materialized",
              "public_states", "public_nodes", "info_sets", "chance_nodes",
              "world_traversal_nodes", "iterations", "resource_usage")
    return {field: result[field] for field in fields if field in result}


def _trace(case, backend, algorithm):
    gc.collect()
    tracemalloc.start()
    try:
        result = _solve(case, backend, algorithm, iterations=10)
        peak = tracemalloc.get_traced_memory()[1]
        return {"peak_tracemalloc_bytes": peak, "iterations": 10,
                "counts": _counts(result)}
    finally:
        tracemalloc.stop()


def small_runs(cases, skip_memory):
    rows = []
    for case in cases:
        for algorithm in ALGORITHMS:
            samples = {backend: [] for backend in BACKENDS}
            last = {}
            rejected = {}
            for repeat in range(REPEATS):
                order = list(BACKENDS)
                if repeat % 2:
                    order.reverse()
                for backend in order:
                    try:
                        seconds, result = timed_solve(case, backend, algorithm)
                    except ValueError as exc:
                        rejected[backend] = str(exc)
                        print(f"{case['range_size_per_player']} {algorithm} {backend} "
                              f"rejected: {exc}", flush=True)
                        continue
                    samples[backend].append(seconds)
                    last[backend] = result
                    print(f"{case['range_size_per_player']} {algorithm} {backend} "
                          f"repeat {repeat + 1}: {seconds:.3f}s "
                          f"gap={result['exploitability']:.8g}", flush=True)
            status = {backend: ("admitted" if len(samples[backend]) == REPEATS else "rejected")
                      for backend in BACKENDS}
            row = {"range_size_per_player": case["range_size_per_player"],
                   "iterations": case["iterations"], "algorithm": algorithm,
                   "status": status, "rejection_reasons": rejected,
                   "whole_call_seconds": {
                       backend: ({"samples": samples[backend],
                                  "median": statistics.median(samples[backend])}
                                 if samples[backend] else None)
                       for backend in BACKENDS},
                   "peak_memory": None if skip_memory else {}}
            if all(value == "admitted" for value in status.values()):
                row["speedup_matrix_free_vs_materialized"] = (
                    statistics.median(samples["materialized-ranked"]) /
                    statistics.median(samples["matrix-free"]))
                row["counts"] = {backend: _counts(last[backend]) for backend in BACKENDS}
                row["gap_metrics"] = {backend: {field: last[backend][field] for field in METRICS}
                                      for backend in BACKENDS}
                row["metric_comparison"] = _metrics(last["materialized-ranked"],
                                                      last["matrix-free"])
                row["policy_comparison"] = _profile_diff(last["materialized-ranked"],
                                                          last["matrix-free"])
                if not skip_memory:
                    row["peak_memory"] = {
                        backend: _trace(case, backend, algorithm) for backend in BACKENDS}
            rows.append(row)
    return rows


def full_range_run(skip_memory):
    case = {"range_size_per_player": 1081, "board": BOARD, "config": CONFIG,
            "oop": "random", "ip": "random"}
    rows = []
    for iterations in FULL_ITERATIONS:
        gc.collect()
        started = time.perf_counter()
        result = solve_matrix_free_river(BOARD, "random", "random", CONFIG,
                                         iterations=iterations, algorithm="cfrplus")
        elapsed = time.perf_counter() - started
        row = {"iterations": iterations, "algorithm": "cfrplus",
               "status": "admitted", "whole_call_seconds": elapsed,
               "counts": _counts(result),
               "gap_metrics": {field: result[field] for field in METRICS},
               "peak_memory": None}
        # A 10-iteration full-range run is the only permitted legacy probe; its
        # candidate-pair iteration guard rejects before pair/world allocation.
        if iterations == 10:
            try:
                solve_postflop(BOARD, "random", "random", CONFIG,
                               iterations=10, algorithm="cfrplus",
                               traversal="public-batched", diagnostics="public-batched",
                               terminal_backend="ranked")
            except ValueError as exc:
                row["legacy_materialized_status"] = "rejected-by-existing-guard"
                row["legacy_materialized_rejection"] = str(exc)
            else:
                row["legacy_materialized_status"] = "admitted"
                row["legacy_materialized_rejection"] = None
        if iterations == 10 and not skip_memory and elapsed < 15.0:
            gc.collect()
            tracemalloc.start()
            try:
                traced = solve_matrix_free_river(BOARD, "random", "random", CONFIG,
                                                 iterations=10, algorithm="cfrplus")
                row["peak_memory"] = {"peak_tracemalloc_bytes": tracemalloc.get_traced_memory()[1],
                                      "iterations": 10,
                                      "counts": _counts(traced)}
            finally:
                tracemalloc.stop()
        rows.append(row)
        print(f"full-random cfrplus {iterations}: {elapsed:.3f}s "
              f"gap={result['exploitability']:.8g}", flush=True)
    return case, rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/results/matrix-free-river-v1.json")
    parser.add_argument("--skip-memory", action="store_true",
                        help="Skip separate 10-iteration tracemalloc calls.")
    args = parser.parse_args(argv)
    small_cases = [make_case(size) for size in SMALL_SIZES]
    source_names = ("postflop_solver", "matrix_free_river", "cards", "cfr", "cfr_plus",
                    "planned_cfr", "public_cfr", "public_diagnostics", "ranked_river",
                    "river_config", "river_tree")
    sources = [Path(__file__).resolve(), ROOT / "scripts/benchmark_turn_solver.py"]
    sources.extend(ROOT / "pokerlab" / (name + ".py") for name in source_names)
    before = {str(path.relative_to(ROOT)): sha256(path) for path in sources}
    results = small_runs(small_cases, args.skip_memory)
    full_case, full_results = full_range_run(args.skip_memory)
    after = {str(path.relative_to(ROOT)): sha256(path) for path in sources}
    if before != after:
        raise RuntimeError("Calculation source changed during benchmark; discard measurements.")
    all_inputs = small_cases + [{"range_size_per_player": 1081, "board": BOARD,
                                 "ranges": {"oop": "random", "ip": "random"},
                                 "config": CONFIG,
                                 "iterations": list(FULL_ITERATIONS)}]
    report = {
        "schema_version": 1, "benchmark_id": "matrix-free-river-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "metadata": {"revision": git_revision(None), "worktree_dirty": worktree_dirty(),
                     "python": sys.version, "python_version": platform.python_version(),
                     "platform": platform.platform(),
                     "command": "python -m scripts.benchmark_matrix_free_river",
                     "source_sha256": before,
                     "input_sha256": hashlib.sha256(json.dumps(
                         all_inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                     "small_iterations": SMALL_ITERATIONS,
                     "full_range_iterations": FULL_ITERATIONS,
                     "algorithms": ALGORITHMS, "repeats": REPEATS,
                     "memory_skipped": args.skip_memory},
        "configuration": {"board": BOARD, "config": CONFIG,
                          "small_ranges": "Deterministic board-excluded combo spread, independent offsets/strides, weights cycle [1,.5,.75,.25,.125]. Exact holdings and weights are recorded in cases.",
                          "full_range": "Uniform random/random ranges of all 1,081 board-legal combinations per player; CFR+ only."},
        "methodology": {
            "small_case_timing": "Three interleaved complete-call timings per backend/algorithm. Legacy comparison uses traversal=public-batched, diagnostics=public-batched, terminal_backend=ranked; matrix-free calls solve_matrix_free_river.",
            "memory": "Separate 10-iteration whole-call tracemalloc runs for each small case/backend; full-range trace is attempted only when its 10-iteration call takes under 15 seconds. Null means skipped.",
            "full_range": "Matrix-free only at 10, 50, 100 iterations. Legacy solver is called once at 10 iterations, where its pair-candidate guard rejects before materializing pairs; no higher-budget legacy call is attempted.",
            "accuracy": "Finite-iteration EV and exact best-response gaps; strategy and metric differences are reported for small comparisons. No equilibrium or commercial-solver equivalence claim.",
            "limits": "All existing solver resource guards remain active. Full-range admission and measured resource usage are reported from matrix-free results.",
        },
        "small_cases": [{"case": case, "results": [row for row in results
                          if row["range_size_per_player"] == case["range_size_per_player"]]}
                        for case in small_cases],
        "full_range": {"case": full_case, "results": full_results},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(f"Wrote {len(results)} small-case rows and {len(full_results)} full-range cases to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
