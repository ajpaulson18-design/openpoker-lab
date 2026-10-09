"""Compare whole-call recursive, planned, and public-batched postflop solves."""

import argparse
import gc
import hashlib
import json
import math
import platform
import statistics
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

from pokerlab.postflop_solver import solve_postflop
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "benchmarks" / "public-batched-v1.json"
SOLVER_MODULES = (
    "postflop_solver.py", "turn_solver.py", "cfr.py", "planned_cfr.py",
    "public_cfr.py", "river_tree.py", "river_config.py", "cards.py",
)
COMPARE_METRICS = (
    "value_oop", "value_ip", "oop_best_response_value",
    "ip_best_response_value", "nash_conv", "exploitability",
)
GAME_METRICS = (
    "solver_version", "strategy_schema", "backend", "execution_backend",
    "iterations", "deals", "compatible_pairs", "worlds", "info_sets",
    "public_nodes", "chance_nodes", "terminal_nodes", "public_states",
    "public_state_limit", "world_traversal_nodes", "tree_actions",
    "plan_operation_limit", "public_batch_edge_limit", *COMPARE_METRICS,
    "oop_best_response_gain", "ip_best_response_gain", "scope",
)
TOLERANCE = 1e-10


def _scenario_inputs(scenario, iterations, algorithm, traversal):
    kwargs = {
        key: scenario[key]
        for key in ("config", "turn_config", "river_config", "runouts")
        if key in scenario
    }
    kwargs.update(iterations=iterations, algorithm=algorithm, traversal=traversal)
    return (scenario["board"], scenario["oop"], scenario["ip"]), kwargs


def _solve_and_serialize(scenario, iterations, algorithm, traversal):
    positional, kwargs = _scenario_inputs(scenario, iterations, algorithm, traversal)
    result = solve_postflop(*positional, **kwargs)
    serialized = json.dumps(result, sort_keys=True, separators=(",", ":"),
                            allow_nan=False)
    return result, len(serialized.encode("utf-8"))


def _snapshot(result):
    rows = []
    for row in result["strategy"]:
        row_identity = (
            row["player"], row["hand"], row["street"],
            tuple(row["board"]), tuple(row["history"]),
        )
        actions = tuple((
            action["name"], action["amount"], action["raise_to"],
            action["history_key"], action["probability"],
        ) for action in row["actions"])
        rows.append((row_identity, actions))
    metrics = {key: result[key] for key in COMPARE_METRICS}
    return rows, metrics


def _compare(reference, candidate, label):
    ref_rows, ref_metrics = reference
    rows, metrics = candidate
    if len(ref_rows) != len(rows):
        raise RuntimeError(f"{label}: strategy row count differs from recursive reference.")

    max_probability_diff = 0.0
    for row_index, (left, right) in enumerate(zip(ref_rows, rows)):
        left_identity, left_actions = left
        right_identity, right_actions = right
        if left_identity != right_identity:
            raise RuntimeError(f"{label}: strategy row {row_index} identity differs.")
        if len(left_actions) != len(right_actions):
            raise RuntimeError(f"{label}: action count differs at row {row_index}.")
        for action_index, (left_action, right_action) in enumerate(
                zip(left_actions, right_actions)):
            if left_action[:4] != right_action[:4]:
                raise RuntimeError(
                    f"{label}: action identity differs at row {row_index}, "
                    f"action {action_index}."
                )
            difference = abs(left_action[4] - right_action[4])
            max_probability_diff = max(max_probability_diff, difference)
            if difference > TOLERANCE:
                raise RuntimeError(
                    f"{label}: strategy probability differs by {difference:.3g} "
                    f"at row {row_index}, action {action_index}."
                )

    metric_differences = {}
    for key in COMPARE_METRICS:
        left, right = ref_metrics[key], metrics[key]
        difference = abs(left - right)
        metric_differences[key] = difference
        if not math.isfinite(difference) or difference > TOLERANCE:
            raise RuntimeError(
                f"{label}: {key} differs by {difference:.3g} from recursive reference."
            )
    return {
        "strategy_rows": len(rows),
        "max_probability_abs_diff": max_probability_diff,
        "metric_abs_differences": metric_differences,
    }


def _rotate(values, offset):
    offset %= len(values)
    return values[offset:] + values[:offset]


def _timed_call(scenario, iterations, algorithm, traversal):
    # Collection is intentionally outside the interval so a previous solve's
    # cycles do not unpredictably tax only the next backend.
    gc.collect()
    started = time.perf_counter()
    result, serialized_bytes = _solve_and_serialize(
        scenario, iterations, algorithm, traversal,
    )
    elapsed = time.perf_counter() - started
    return elapsed, result, serialized_bytes


def _memory_call(scenario, iterations, algorithm, traversal):
    gc.collect()
    tracemalloc.start()
    try:
        _result, _serialized_bytes = _solve_and_serialize(
            scenario, iterations, algorithm, traversal,
        )
        _current, peak = tracemalloc.get_traced_memory()
        return peak
    finally:
        tracemalloc.stop()


def run_case(scenario, iterations, repeats, algorithm, traversals, order_offset):
    samples = {backend: [] for backend in traversals}
    serialized_bytes = {backend: [] for backend in traversals}
    max_differences = {
        backend: {
            "max_probability_abs_diff": 0.0,
            "metric_abs_differences": {key: 0.0 for key in COMPARE_METRICS},
            "strategy_rows": 0,
        }
        for backend in traversals if backend != "recursive"
    }
    final_game = {}

    for repeat in range(repeats):
        order = _rotate(traversals, order_offset + repeat)
        snapshots = {}
        for backend in order:
            elapsed, result, byte_count = _timed_call(
                scenario, iterations, algorithm, backend,
            )
            samples[backend].append(elapsed)
            print(f"{scenario.get('id', 'fixture')} {algorithm} {iterations} "
                  f"{backend} repeat {repeat + 1}: {elapsed:.3f}s", flush=True)
            serialized_bytes[backend].append(byte_count)
            snapshots[backend] = _snapshot(result)
            if repeat == repeats - 1:
                final_game[backend] = {
                    key: result.get(key) for key in GAME_METRICS
                }
            del result

        reference = snapshots["recursive"]
        for backend in traversals:
            if backend == "recursive":
                continue
            comparison = _compare(
                reference, snapshots[backend],
                f"{scenario.get('id', 'fixture')}/{iterations}/{backend}/repeat-{repeat + 1}",
            )
            previous = max_differences[backend]
            previous["strategy_rows"] = comparison["strategy_rows"]
            previous["max_probability_abs_diff"] = max(
                previous["max_probability_abs_diff"],
                comparison["max_probability_abs_diff"],
            )
            for key, value in comparison["metric_abs_differences"].items():
                previous["metric_abs_differences"][key] = max(
                    previous["metric_abs_differences"][key], value,
                )
        snapshots.clear()
        gc.collect()

    peaks = {}
    for backend in traversals:
        print(f"Tracing whole-call memory: {backend}", flush=True)
        peaks[backend] = _memory_call(scenario, iterations, algorithm, backend)
        print(f"{backend} traced peak: {peaks[backend]} bytes", flush=True)
    return {
        "scenario_id": scenario.get("id", "fixture"),
        "purpose": scenario.get("purpose"),
        "fixture": scenario,
        "algorithm": algorithm,
        "iterations": iterations,
        "repeats": repeats,
        "whole_call": {
            backend: {
                "runtime_seconds": {
                    "samples": samples[backend],
                    "median": statistics.median(samples[backend]),
                },
                "serialized_result_bytes": serialized_bytes[backend],
                "peak_tracemalloc_bytes": peaks[backend],
                "game": final_game[backend],
                "reported_gap": {
                    "nash_conv": final_game[backend]["nash_conv"],
                    "exploitability": final_game[backend]["exploitability"],
                    "oop_best_response_gain": final_game[backend]["oop_best_response_gain"],
                    "ip_best_response_gain": final_game[backend]["ip_best_response_gain"],
                },
            }
            for backend in traversals
        },
        "max_abs_differences_vs_recursive": max_differences,
        "comparison_tolerance": TOLERANCE,
    }


def _scenarios(config):
    scenarios = config.get("scenarios")
    if scenarios is None:
        fixture = config.get("fixture", config)
        scenarios = fixture if isinstance(fixture, list) else [fixture]
    if not scenarios:
        raise ValueError("Benchmark config must provide at least one scenario or fixture.")
    for scenario in scenarios:
        if not isinstance(scenario, dict) or not all(
                key in scenario for key in ("board", "oop", "ip")):
            raise ValueError("Each benchmark fixture needs board, oop, and ip fields.")
    return scenarios


def _source_hashes(config_path):
    result = {
        f"pokerlab/{name}": file_sha256(ROOT / "pokerlab" / name)
        for name in SOLVER_MODULES
    }
    result["config"] = file_sha256(config_path)
    result["harness"] = file_sha256(Path(__file__).resolve())
    helper = ROOT / "scripts" / "benchmark_turn_solver.py"
    result["benchmark_helper"] = file_sha256(helper)
    return result


def _iteration_values(config, requested):
    if requested is not None:
        values = requested
    else:
        defaults = config.get("defaults", {})
        values = defaults.get("iterations", defaults.get("checkpoints", [20]))
    if type(values) is int:
        values = [values]
    if (not isinstance(values, list) or not values or
            any(type(value) is not int or not 10 <= value <= 10_000
                for value in values)):
        raise ValueError("Use one or more iteration counts from 10 through 10,000.")
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--algorithm", choices=("vanilla", "dcfr"), default="vanilla")
    parser.add_argument("--traversals", nargs="+",
                        choices=("recursive", "planned", "public-batched"))
    parser.add_argument("--iterations", type=int, nargs="+")
    parser.add_argument("--repeats", type=int)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision-label")
    args = parser.parse_args(argv)

    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    try:
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        scenarios = _scenarios(config)
        iterations = _iteration_values(config, args.iterations)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    repeats = args.repeats if args.repeats is not None else \
        config.get("defaults", {}).get("repeats", 3)
    if type(repeats) is not int or not 1 <= repeats <= 25:
        parser.error("Use 1-25 timed repeats.")
    traversals = args.traversals or config.get(
        "traversals", ["recursive", "public-batched"],
    )
    if (not traversals or len(set(traversals)) != len(traversals) or
            "recursive" not in traversals):
        parser.error("Traversals must be unique and include recursive as the reference.")
    if any(value not in ("recursive", "planned", "public-batched")
           for value in traversals):
        parser.error("Unknown traversal backend in benchmark config.")

    before_hashes = _source_hashes(config_path)
    revision = git_revision(args.revision_label)
    results = []
    order_offset = 0
    for scenario in scenarios:
        for iteration_count in iterations:
            results.append(run_case(
                scenario, iteration_count, repeats, args.algorithm,
                traversals, order_offset,
            ))
            order_offset += repeats
    after_hashes = _source_hashes(config_path)
    if before_hashes != after_hashes:
        raise RuntimeError("Benchmark source/config changed during measurement; discard this run.")

    report = {
        "schema_version": 1,
        "benchmark_id": config.get("benchmark_id", "public-batched-cfr-v1"),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "git_revision": revision,
            "worktree_dirty": worktree_dirty(),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "source_sha256": before_hashes,
        },
        "methodology": {
            "timing": (
                "Whole solve_postflop call plus JSON serialization; raw samples "
                "are interleaved by rotating backend order. gc.collect runs "
                "before, outside each timed interval."
            ),
            "memory": (
                "Separate whole-call tracemalloc peak including construction, "
                "training, exact evaluate/best responses, and JSON serialization; "
                "garbage collection runs before tracing."
            ),
            "correctness": (
                "Every run compares serialized strategy row identity and action "
                "tokens exactly, probabilities and value/BR/NashConv metrics "
                f"within {TOLERANCE:g}; divergence aborts report generation."
            ),
            "limitations": (
                "Finite configured heads-up postflop abstraction only. Selected "
                "runouts condition joint physical deal weights. Measurements are "
                "machine- and source-revision-specific."
            ),
        },
        "results": results,
    }
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(f"Wrote {len(results)} benchmark cases to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
