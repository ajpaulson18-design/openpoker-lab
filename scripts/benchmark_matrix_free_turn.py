"""Measure matrix-free turn solving and root-fold kernel scaling.

The full-call comparison uses exact physical river runouts at a fixed iteration
budget. A separate phase compares the current root-fold accumulator to the
immutable pre-optimization TurnRangePayoffs source loaded in memory from git.
"""
import argparse
import gc
import hashlib
import importlib.util
import itertools
import json
import math
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

from pokerlab.cards import DECK
from pokerlab.matrix_free_turn import solve_matrix_free_turn
from pokerlab import postflop_solver
from pokerlab.postflop_solver import solve_postflop
from pokerlab.public_diagnostics import evaluate_profile
from pokerlab.river_config import RiverConfig
from pokerlab.river_tree import _Terminal
from pokerlab.turn_range_kernel import TurnRangePayoffs
from scripts.benchmark_turn_solver import git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
BOARD = "2c7d9hJs"
CONFIG = {"pot": 100.0, "effective_stack": 200.0,
          "bet_sizes": [0.75], "raise_sizes": [],
          "max_raises": 0, "include_all_in": False}
SIZES = (8, 16, 32)
ITERATIONS = {8: 40, 16: 20, 32: 10}
ALGORITHMS = ("dcfr", "cfrplus")
BACKENDS = ("materialized", "matrix-free")
REPEATS = 3
ROOTFOLD_SIZES = (8, 32, 128)
ROOTFOLD_REPEATS = 10
PROTOTYPE_BLOB = "710b60b5070a4014eebfdbbd1cd04a7c2c15a76d"
FULL_RUNOUTS = ("3c", "4d")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _range_side(count, side, *, offset_multiplier=11):
    board = tuple(BOARD[index:index + 2] for index in range(0, len(BOARD), 2))
    combos = list(itertools.combinations((card for card in DECK if card not in board), 2))
    stride = 37 if side == 0 else 53
    start = count * offset_multiplier + (0 if side == 0 else 19)
    hands = [tuple(sorted(combos[(start + index * stride) % len(combos)]))
             for index in range(count)]
    weight_cycle = (1.0, 0.5, 0.75, 0.25, 0.125)
    weights = [weight_cycle[(index + 2 * side) % len(weight_cycle)]
               for index in range(count)]
    tokens = [{"hand": "".join(hand), "weight": weight}
              for hand, weight in zip(hands, weights)]
    expression = ",".join(item["hand"] + ":" + str(item["weight"])
                           for item in tokens)
    return expression, tokens, tuple(hands), tuple(weights)


def make_small_case(count):
    oop, oop_spec, hands0, weights0 = _range_side(count, 0)
    ip, ip_spec, hands1, weights1 = _range_side(count, 1)
    return {"range_size_per_player": count, "board": BOARD,
            "config": CONFIG, "iterations": ITERATIONS[count],
            "oop": oop, "ip": ip,
            "range_spec": {"oop": oop_spec, "ip": ip_spec}}


def _solver_call(case, backend, algorithm, iterations=None):
    budget = case["iterations"] if iterations is None else iterations
    config = RiverConfig.from_dict(case["config"])
    if backend == "matrix-free":
        return solve_matrix_free_turn(case["board"], case["oop"], case["ip"],
                                      config, iterations=budget, algorithm=algorithm)
    return solve_postflop(case["board"], case["oop"], case["ip"], config,
                          iterations=budget, algorithm=algorithm,
                          traversal="public-batched", diagnostics="public-batched")


def _timed_solver_call(case, backend, algorithm, iterations=None):
    gc.collect()
    start = time.perf_counter()
    result = _solver_call(case, backend, algorithm, iterations)
    return time.perf_counter() - start, result


METRICS = ("value_oop", "oop_best_response_value", "ip_best_response_value",
           "nash_conv", "exploitability")


def _metric_comparison(left, right):
    differences = {field: abs(left[field] - right[field]) for field in METRICS}
    return {"absolute_differences": differences,
            "max_absolute_difference_chips": max(differences.values()),
            "tolerance_chips": 1e-8,
            "within_tolerance": all(math.isfinite(value) and value <= 1e-8
                                     for value in differences.values())}


def _strategy_comparison(left, right):
    def key(row):
        return (row["player"], row["hand"], row["street"], tuple(row["board"]),
                tuple(row["history"]))
    rows0 = {key(row): row for row in left["strategy"]}
    rows1 = {key(row): row for row in right["strategy"]}
    if rows0.keys() != rows1.keys():
        return {"same_information_sets": False, "rows_left": len(rows0),
                "rows_right": len(rows1), "max_probability_abs_difference": None}
    gap = 0.0
    for row_key in rows0:
        actions0, actions1 = rows0[row_key]["actions"], rows1[row_key]["actions"]
        if len(actions0) != len(actions1):
            return {"same_information_sets": False, "rows_left": len(rows0),
                    "rows_right": len(rows1), "max_probability_abs_difference": None}
        for action0, action1 in zip(actions0, actions1):
            gap = max(gap, abs(action0["probability"] - action1["probability"]))
    return {"same_information_sets": True, "rows": len(rows0),
            "max_probability_abs_difference": gap}


def _counts(result):
    keys = ("deals", "compatible_pairs", "compatible_world_count", "worlds",
            "worlds_materialized", "public_states", "public_nodes", "info_sets",
            "chance_nodes", "world_traversal_nodes", "iterations", "resource_usage")
    return {key: result[key] for key in keys if key in result}


def _materialized_public_vector_replay(case, matrix_result):
    """Replay a candidate policy through the old materialized public evaluator."""
    config = RiverConfig.from_dict(case["config"])
    hands, worlds, _selected, _pairs = postflop_solver._enumerate_worlds(
        case["board"], case["oop"], case["ip"], None, iterations=case["iterations"])
    root, _nodes, _chance, _visited, _plan = postflop_solver._build_postflop_tree(
        case["board"], config, worlds=worlds)
    hand_indices = tuple({"".join(hand): index for index, hand in enumerate(side)}
                         for side in hands)
    profile = {}
    for row in matrix_result["strategy"]:
        player = 0 if row["player"] == "oop" else 1
        key = (player, hand_indices[player][row["hand"]], tuple(row["history"]))
        profile[key] = tuple(action["probability"] for action in row["actions"])
    value, response0, response1 = evaluate_profile(
        root, worlds, profile, pot=config.pot, chance_type=postflop_solver._Chance)
    nash_conv = max(0.0, (response0 - value) + (response1 + value))
    replay = {"replay_method": "materialized public-vector replay",
              "worlds_materialized_for_replay": len(worlds),
              "policy_rows_replayed": len(profile),
              "metrics": {"value_oop": value,
                          "oop_best_response_value": response0,
                          "ip_best_response_value": response1,
                          "nash_conv": nash_conv,
                          "exploitability": nash_conv / 2.0}}
    diffs = {field: abs(matrix_result[field] - replay["metrics"][field])
             for field in METRICS}
    replay.update({"max_metric_abs_difference_chips": max(diffs.values()),
                   "metric_abs_differences": diffs,
                   "tolerance_chips": 1e-8,
                   "passed": all(math.isfinite(value) and value <= 1e-8
                                 for value in diffs.values())})
    if not replay["passed"]:
        raise AssertionError("Matrix-free metrics differ from materialized public-vector replay: "
                             + repr(replay))
    return replay


def _trace_small(case, backend, algorithm):
    gc.collect()
    tracemalloc.start()
    try:
        result = _solver_call(case, backend, algorithm, iterations=10)
        return {"peak_tracemalloc_bytes": tracemalloc.get_traced_memory()[1],
                "iterations": 10, "counts": _counts(result)}
    finally:
        tracemalloc.stop()


def full_solver_runs(cases):
    rows = []
    for case in cases:
        for algorithm in ALGORITHMS:
            samples = {backend: [] for backend in BACKENDS}
            final = {}
            rejected = {}
            for repeat in range(REPEATS):
                order = list(BACKENDS)
                if repeat % 2:
                    order.reverse()
                for backend in order:
                    try:
                        elapsed, result = _timed_solver_call(case, backend, algorithm)
                    except ValueError as exc:
                        rejected[backend] = str(exc)
                        print(f"{case['range_size_per_player']} {algorithm} {backend} "
                              f"rejected: {exc}", flush=True)
                        continue
                    samples[backend].append(elapsed)
                    final[backend] = result
                    print(f"{case['range_size_per_player']} {algorithm} {backend} "
                          f"repeat {repeat + 1}: {elapsed:.3f}s "
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
                       for backend in BACKENDS}}
            if all(value == "admitted" for value in status.values()):
                row["speedup_matrix_free_vs_materialized"] = (
                    statistics.median(samples["materialized"]) /
                    statistics.median(samples["matrix-free"]))
                row["counts"] = {backend: _counts(final[backend]) for backend in BACKENDS}
                row["gap_metrics"] = {
                    backend: {field: final[backend][field] for field in METRICS}
                    for backend in BACKENDS}
                row["metric_comparison"] = _metric_comparison(
                    final["materialized"], final["matrix-free"])
                row["policy_comparison"] = _strategy_comparison(
                    final["materialized"], final["matrix-free"])
                row["matrix_free_metric_validation"] = _materialized_public_vector_replay(
                    case, final["matrix-free"])
                row["peak_memory_10_iterations"] = {
                    backend: _trace_small(case, backend, algorithm) for backend in BACKENDS}
            rows.append(row)
    return rows


def _load_prototype(blob):
    spec = importlib.util.spec_from_loader("pokerlab._turn_range_kernel_prototype", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "pokerlab"
    exec(compile(blob, "git:turn-range-kernel-prototype", "exec"), module.__dict__)
    return module.TurnRangePayoffs


def _rootfold_data(count):
    _, _, hands0, weights0 = _range_side(count, 0, offset_multiplier=7)
    _, _, hands1, weights1 = _range_side(count, 1, offset_multiplier=7)
    reach0_cycle = (0.0, 0.125, 0.375, 0.625, 0.875, 1.0)
    reach1_cycle = (1.0, 0.75, 0.5, 0.25, 0.125, 0.0)
    reach0 = tuple(reach0_cycle[index % len(reach0_cycle)] for index in range(count))
    reach1 = tuple(reach1_cycle[index % len(reach1_cycle)] for index in range(count))
    return hands0, weights0, hands1, weights1, reach0, reach1


def _rootfold_values(kernel, terminal, reach0, reach1):
    return (kernel.values(terminal, reach1, 0),
            kernel.values(terminal, reach0, 1))


def _vector_gap(left, right):
    if tuple(map(len, left)) != tuple(map(len, right)):
        return None
    return max((abs(a - b) for x, y in zip(left, right) for a, b in zip(x, y)),
               default=0.0)


def rootfold_benchmark(Prototype):
    rows = []
    terminal = _Terminal("fold", (0.0, 0.0), winner=0)
    runouts = None  # all 44 legal rivers from the four-card board
    for count in ROOTFOLD_SIZES:
        hands0, weights0, hands1, weights1, reach0, reach1 = _rootfold_data(count)
        args = (BOARD, (hands0, hands1), (weights0, weights1))
        setup_samples = {"current": [], "prototype": []}
        kernels = {}
        for repeat in range(3):
            for name, cls in (("current", TurnRangePayoffs), ("prototype", Prototype)):
                gc.collect()
                start = time.perf_counter()
                kernel = cls(*args, pot=100.0, runouts=runouts)
                setup_samples[name].append(time.perf_counter() - start)
                kernels[name] = kernel
        expected = _rootfold_values(kernels["prototype"], terminal, reach0, reach1)
        actual = _rootfold_values(kernels["current"], terminal, reach0, reach1)
        gap = _vector_gap(actual, expected)
        samples = {"current": [], "prototype": []}
        for repeat in range(ROOTFOLD_REPEATS):
            order = ("current", "prototype") if repeat % 2 == 0 else ("prototype", "current")
            for name in order:
                gc.collect()
                started = time.perf_counter()
                _rootfold_values(kernels[name], terminal, reach0, reach1)
                samples[name].append(time.perf_counter() - started)
        rows.append({
            "range_size_per_player": count,
            "runout_count": 44,
            "timing_repeats": ROOTFOLD_REPEATS,
            "setup_timing_repeats": 3,
            "setup_seconds": {name: {"samples": values,
                                     "median": statistics.median(values)}
                              for name, values in setup_samples.items()},
            "prepared_rootfold_values_seconds": {
                name: {"samples": values, "median": statistics.median(values)}
                for name, values in samples.items()},
            "speedup_current_vs_prototype": (
                statistics.median(samples["prototype"]) /
                statistics.median(samples["current"])),
            "max_absolute_vector_difference": gap,
            "reach_note": "Both players are evaluated; each opponent reach vector is nonuniform and contains zero entries.",
            "scope": "Prepared root-fold values only; no solver or equilibrium speed claim.",
        })
        print(f"rootfold {count}: current={statistics.median(samples['current']):.6g}s "
              f"prototype={statistics.median(samples['prototype']):.6g}s "
              f"gap={gap:.3g}", flush=True)
    return rows


def full_random_run():
    runouts = FULL_RUNOUTS
    config = RiverConfig.from_dict(CONFIG)
    started = time.perf_counter()
    result = solve_matrix_free_turn(BOARD, "random", "random", config,
                                    runouts=runouts, iterations=10, algorithm="vanilla")
    elapsed = time.perf_counter() - started
    row = {"status": "admitted", "algorithm": "vanilla", "iterations": 10,
           "runouts": runouts, "whole_call_seconds": elapsed,
           "counts": {key: result[key] for key in (
               "compatible_world_count", "worlds_materialized", "public_states",
               "public_nodes", "info_sets", "resource_usage", "iterations")
                      if key in result},
           "gap_metrics": {field: result[field] for field in METRICS},
           "peak_memory": None}
    try:
        solve_postflop(BOARD, "random", "random", config, runouts=runouts,
                       iterations=10, algorithm="vanilla", traversal="public-batched",
                       diagnostics="public-batched")
    except ValueError as exc:
        row["legacy_status"] = "rejected-by-existing-guard"
        row["legacy_rejection"] = str(exc)
    else:
        row["legacy_status"] = "admitted"
        row["legacy_rejection"] = None
    if elapsed < 15:
        gc.collect()
        tracemalloc.start()
        try:
            traced = solve_matrix_free_turn(BOARD, "random", "random", config,
                                            runouts=runouts, iterations=10,
                                            algorithm="vanilla")
            row["peak_memory"] = {"peak_tracemalloc_bytes": tracemalloc.get_traced_memory()[1],
                                  "iterations": 10,
                                  "counts": {key: traced[key] for key in (
                                      "compatible_world_count", "worlds_materialized",
                                      "resource_usage") if key in traced}}
        finally:
            tracemalloc.stop()
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/results/matrix-free-turn-v1.json")
    args = parser.parse_args(argv)
    small_cases = [make_small_case(size) for size in SIZES]
    prototype_source = subprocess.check_output(
        ["git", "cat-file", "blob", PROTOTYPE_BLOB], cwd=ROOT)
    Prototype = _load_prototype(prototype_source)
    source_names = ("postflop_solver", "matrix_free_turn", "turn_range_kernel",
                    "public_cfr", "public_diagnostics", "ranked_river", "cards",
                    "river_tree", "river_config", "cfr", "cfr_plus", "planned_cfr")
    sources = [Path(__file__).resolve(), ROOT / "scripts/benchmark_turn_solver.py"]
    sources.extend(ROOT / "pokerlab" / (name + ".py") for name in source_names)
    source_hashes = {str(path.relative_to(ROOT)): sha256(path) for path in sources}
    prototype_hash = sha256_bytes(prototype_source)
    small_results = full_solver_runs(small_cases)
    rootfold_results = rootfold_benchmark(Prototype)
    full_random = full_random_run()
    hashes_after = {str(path.relative_to(ROOT)): sha256(path) for path in sources}
    if hashes_after != source_hashes:
        raise RuntimeError("Calculation source changed during benchmark; discard measurements.")
    input_spec = {"board": BOARD, "config": CONFIG,
                  "small_cases": small_cases,
                  "rootfold_sizes": ROOTFOLD_SIZES,
                  "rootfold_weight_cycle": [1.0, 0.5, 0.75, 0.25, 0.125],
                  "full_random_runouts": FULL_RUNOUTS}
    report = {
        "schema_version": 1, "benchmark_id": "matrix-free-turn-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "metadata": {"revision": git_revision(None), "worktree_dirty": worktree_dirty(),
                     "python": sys.version, "python_version": platform.python_version(),
                     "platform": platform.platform(),
                     "command": "python -m scripts.benchmark_matrix_free_turn",
                     "source_sha256": source_hashes,
                     "prototype_blob": PROTOTYPE_BLOB,
                     "prototype_sha256": prototype_hash,
                     "input_sha256": sha256_bytes(json.dumps(
                         input_spec, sort_keys=True, separators=(",", ":")).encode()),
                     "small_iterations": ITERATIONS, "algorithms": ALGORITHMS,
                     "timing_repeats": REPEATS,
                     "rootfold_timing_repeats": ROOTFOLD_REPEATS},
        "configuration": {"board": BOARD, "config": CONFIG,
                          "small_range_selection": "Concrete board-excluded combinations selected with deterministic coprime strides 37/53 and offsets count*11/count*11+19; nonuniform weights repeat [1,.5,.75,.25,.125]. Exact hands/weights appear in cases.",
                          "full_random": "Uniform full ranges with two selected rivers (3c,4d), 10 iterations, vanilla; legacy admission probe is attempted once at the same minimum budget."},
        "methodology": {"complete_call": "Interleaved full solve_postflop public-batched training/diagnostics versus solve_matrix_free_turn; calls include setup, enumeration, training, exact BR diagnostics, and result assembly.",
                        "rootfold": "Current and immutable prototype TurnRangePayoffs are separately prepared; then ten interleaved timings per implementation call values for both players, each using a distinct nonuniform reach vector with zeros. No equilibrium claim.",
                        "memory": "Separate 10-iteration tracemalloc calls for admitted small solver comparisons; selected-runout full-range trace is attempted only if its untraced call is under 15 seconds.",
                        "limitations": "Synthetic ranges, tiny finite iteration budgets, machine-specific timings. Matrix-free outputs are independently replayed through the materialized public-vector evaluator; finite-iteration matrix-free versus legacy policy/gap differences are reported without a parity claim. Full-range solver call is descriptive and no old solver is called beyond its existing guard."},
        "cases": [{"input": case, "results": [row for row in small_results
                    if row["range_size_per_player"] == case["range_size_per_player"]]}
                  for case in small_cases],
        "rootfold_phase": rootfold_results,
        "full_random_selected_runouts": full_random,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(f"Wrote {len(small_results)} solver comparisons, "
          f"{len(rootfold_results)} root-fold cases, and full-range probe to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
