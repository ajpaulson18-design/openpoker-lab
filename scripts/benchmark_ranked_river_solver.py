"""Compare complete river solver calls using sparse versus ranked diagnostics.

Training, exact best responses, and result assembly all remain inside the
timed ``solve_postflop`` call. The benchmark is not a whole-solver GTO or
commercial-solver accuracy claim.
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
from pokerlab.postflop_solver import solve_postflop
from scripts.benchmark_turn_solver import git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
BOARD = "2c7d9hJsKd"
RANGE_SIZES = (64, 128, 256)
ITERATIONS = {64: 50, 128: 50, 256: 10}
ALGORITHMS = ("dcfr", "cfrplus")
BACKENDS = ("sparse", "ranked")
REPEATS = 3
CONFIG = {"pot": 100.0, "effective_stack": 200.0,
          "bet_sizes": [0.75], "raise_sizes": [],
          "max_raises": 0, "include_all_in": False}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_case(count):
    board = tuple(BOARD[i:i + 2] for i in range(0, len(BOARD), 2))
    available = tuple(card for card in DECK if card not in board)
    combos = list(itertools.combinations(available, 2))
    # Same deterministic board-excluded spread used by the terminal microbench.
    def side(player):
        stride = 37 if player == 0 else 53
        start = count * 11 + (0 if player == 0 else 19)
        hands = [tuple(sorted(combos[(start + i * stride) % len(combos)]))
                 for i in range(count)]
        cycle = (1.0, 0.5, 0.75, 0.25, 0.125)
        weights = [cycle[(i + 2 * player) % len(cycle)] for i in range(count)]
        return ",".join("".join(hand) + ":" + str(weight)
                        for hand, weight in zip(hands, weights)), [
                            {"hand": "".join(hand), "weight": weight}
                            for hand, weight in zip(hands, weights)]
    oop, oop_spec = side(0)
    ip, ip_spec = side(1)
    return {"range_size_per_player": count, "oop": oop, "ip": ip,
            "range_spec": {"oop": oop_spec, "ip": ip_spec},
            "board": BOARD, "iterations": ITERATIONS[count],
            "config": CONFIG}


def solve(case, algorithm, backend, iterations=None):
    return solve_postflop(
        case["board"], case["oop"], case["ip"], config=case["config"],
        iterations=case["iterations"] if iterations is None else iterations,
        algorithm=algorithm, traversal="public-batched", diagnostics="public-batched",
        terminal_backend=backend)


def timed_solve(case, algorithm, backend, iterations=None):
    gc.collect()
    start = time.perf_counter()
    result = solve(case, algorithm, backend, iterations)
    return time.perf_counter() - start, result


def peak_memory(case, algorithm, backend):
    gc.collect()
    tracemalloc.start()
    try:
        result = solve(case, algorithm, backend, iterations=10)
        peak = tracemalloc.get_traced_memory()[1]
        return peak, result
    finally:
        tracemalloc.stop()


def strategy_diff(sparse, ranked):
    def key(row):
        return (row["player"], row["hand"], row["street"], tuple(row["board"]),
                tuple(row["history"]))
    left = {key(row): row for row in sparse["strategy"]}
    right = {key(row): row for row in ranked["strategy"]}
    if left.keys() != right.keys():
        return {"same_information_sets": False, "sparse_rows": len(left),
                "ranked_rows": len(right), "max_probability_abs_difference": None}
    max_diff = 0.0
    for row_key in left:
        left_actions = left[row_key]["actions"]
        right_actions = right[row_key]["actions"]
        if len(left_actions) != len(right_actions):
            return {"same_information_sets": False, "sparse_rows": len(left),
                    "ranked_rows": len(right), "max_probability_abs_difference": None}
        for a, b in zip(left_actions, right_actions):
            max_diff = max(max_diff, abs(a["probability"] - b["probability"]))
    return {"same_information_sets": True, "rows": len(left),
            "max_probability_abs_difference": max_diff}


METRICS = ("value_oop", "oop_best_response_value", "ip_best_response_value",
           "nash_conv", "exploitability")


def metric_diffs(sparse, ranked):
    diffs = {field: abs(sparse[field] - ranked[field]) for field in METRICS}
    return {"absolute_differences": diffs,
            "max_absolute_difference_chips": max(diffs.values(), default=0.0),
            "tolerance_chips": 1e-8,
            "within_tolerance": all(math.isfinite(value) and value <= 1e-8
                                     for value in diffs.values())}


def run(cases, *, skip_memory=False):
    rows = []
    for case in cases:
        for algorithm in ALGORITHMS:
            samples = {backend: [] for backend in BACKENDS}
            last = {}
            for repeat in range(REPEATS):
                order = list(BACKENDS)
                if repeat % 2:
                    order.reverse()
                for backend in order:
                    seconds, result = timed_solve(case, algorithm, backend)
                    samples[backend].append(seconds)
                    last[backend] = result
                    print(f"{case['range_size_per_player']} {algorithm} {backend} "
                          f"repeat {repeat + 1}: {seconds:.4f}s "
                          f"worlds={result['worlds']} "
                          f"exploitability={result['exploitability']:.8g}", flush=True)
            difference = metric_diffs(last["sparse"], last["ranked"])
            policy = strategy_diff(last["sparse"], last["ranked"])
            memory = None
            if not skip_memory:
                memory = {}
                for backend in BACKENDS:
                    peak, memory_result = peak_memory(case, algorithm, backend)
                    memory[backend] = {"peak_tracemalloc_bytes": peak,
                                       "iterations": 10,
                                       "worlds": memory_result["worlds"],
                                       "public_states": memory_result["public_states"]}
            rows.append({
                "range_size_per_player": case["range_size_per_player"],
                "algorithm": algorithm, "iterations": case["iterations"],
                "timing_repeats": REPEATS,
                "whole_call_seconds": {
                    backend: {"samples": samples[backend],
                              "median": statistics.median(samples[backend])}
                    for backend in BACKENDS},
                "speedup_ranked_vs_sparse": (
                    statistics.median(samples["sparse"]) /
                    statistics.median(samples["ranked"])),
                "peak_memory": memory,
                "solver_counts": {
                    backend: {field: last[backend][field] for field in
                              ("deals", "worlds", "public_states", "public_nodes",
                               "info_sets", "chance_nodes", "world_traversal_nodes",
                               "tree_actions", "iterations")}
                    for backend in BACKENDS},
                "final_gap_metrics": {
                    backend: {field: last[backend][field] for field in METRICS}
                    for backend in BACKENDS},
                "metric_comparison": difference,
                "policy_comparison": policy,
                "accuracy_note": "Finite-iteration diagnostics only; policy differences in tied/near-tied actions are reported and do not alone establish a defect.",
            })
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/results/ranked-river-solver-v1.json")
    parser.add_argument("--skip-memory", action="store_true",
                        help="Skip separate traced calls and record null memory measurements.")
    args = parser.parse_args(argv)
    cases = [make_case(count) for count in RANGE_SIZES]
    module_names = ("postflop_solver", "cards", "cfr", "cfr_plus", "planned_cfr",
                    "public_cfr", "public_diagnostics", "ranked_river",
                    "river_config", "river_tree")
    sources = [Path(__file__).resolve(), ROOT / "scripts/benchmark_turn_solver.py"]
    sources.extend(ROOT / "pokerlab" / (name + ".py") for name in module_names)
    before = {str(path.relative_to(ROOT)): sha256(path) for path in sources}
    rows = run(cases, skip_memory=args.skip_memory)
    after = {str(path.relative_to(ROOT)): sha256(path) for path in sources}
    if before != after:
        raise RuntimeError("Calculation source changed during benchmark; discard these measurements.")
    input_bytes = json.dumps(cases, sort_keys=True, separators=(",", ":")).encode()
    report = {
        "schema_version": 1, "benchmark_id": "ranked-river-solver-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "metadata": {"revision": git_revision(None), "worktree_dirty": worktree_dirty(),
                     "python": sys.version, "python_version": platform.python_version(),
                     "platform": platform.platform(),
                     "command": "python -m scripts.benchmark_ranked_river_solver",
                     "source_sha256": before,
                     "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
                     "configuration": {"board": BOARD, "pot": 100,
                                       "effective_stack": 200, "bet_size": 0.75,
                                       "raises": False, "algorithms": ALGORITHMS,
                                       "terminal_backends": BACKENDS,
                                       "traversal": "public-batched",
                                       "diagnostics": "public-batched",
                                       "iterations_by_range_size": ITERATIONS,
                                       "timing_repeats": REPEATS,
                                       "memory_iterations": None if args.skip_memory else 10,
                                       "memory_skipped": args.skip_memory}},
        "methodology": {
            "timing": "Complete solve_postflop call including world enumeration, training, exact diagnostics, and result assembly; no JSON serialization.",
            "memory": ("Skipped; peak memory is null." if args.skip_memory else
                       "Separate one-call tracemalloc measurement per backend/case at 10 iterations; includes solver construction and result assembly, excludes process RSS."),
            "comparison": "Same algorithm, ranges, action tree, and iteration count; the selected terminal payoff backend is passed to both public-batched training and public-batched diagnostics.",
            "limitations": "Synthetic nonuniform ranges with blockers, tiny finite iteration budgets, machine-specific timings. No equilibrium or commercial-solver equivalence claim. Results reflect diagnostic backend changes only if training is shared.",
            "guard_policy": "All cases in this run completed under the configured solver guards; no rejected cases were observed.",
        },
        "cases": cases, "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(f"Wrote {len(rows)} benchmark rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
