"""Interleaved whole-call quality/cost comparisons for turn and river algorithms.

Unlike differential backend benchmarks, algorithms need not produce identical
strategies. Report exact deviation gaps, elapsed time and independent memory
peaks; never rank an algorithm solely by its iteration count.
"""
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
from scripts.benchmark_turn_solver import git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("postflop_solver", "turn_solver", "cfr", "cfr_plus", "public_cfr",
           "public_diagnostics", "planned_cfr", "river_tree", "river_config", "cards")


def hashes(config):
    paths = [ROOT / "pokerlab" / (name + ".py") for name in MODULES]
    paths.extend((config, Path(__file__).resolve()))
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths if path.exists()}


def solve(scenario, iterations, algorithm, diagnostics):
    kwargs = {key: scenario[key] for key in ("config", "river_config", "runouts")
              if key in scenario}
    if diagnostics != "recursive":
        kwargs["diagnostics"] = diagnostics
    result = solve_postflop(scenario["board"], scenario["oop"], scenario["ip"],
                           iterations=iterations, algorithm=algorithm,
                           traversal="public-batched", **kwargs)
    json.dumps(result, allow_nan=False)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
                        default=ROOT / "benchmarks" / "turn-river-quality-v1.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, nargs="+")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--diagnostics", choices=("recursive", "public-batched"),
                        default="recursive")
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 25:
        parser.error("Use 1-25 repeats.")
    config = json.loads(args.config.read_text())
    checkpoints = args.iterations or config["checkpoints"]
    if any(type(value) is not int or not 10 <= value <= 10000 for value in checkpoints):
        parser.error("Use 10-10000 iteration checkpoints.")
    algorithms = ("vanilla", "dcfr", "cfrplus")
    before = hashes(args.config)
    revision = git_revision(None)
    rows = []
    for scenario in config["scenarios"]:
        for checkpoint in checkpoints:
            samples = {algorithm: [] for algorithm in algorithms}
            results = {}
            for repeat in range(args.repeats):
                order = algorithms[repeat % 3:] + algorithms[:repeat % 3]
                for algorithm in order:
                    gc.collect()
                    start = time.perf_counter()
                    result = solve(scenario, checkpoint, algorithm, args.diagnostics)
                    samples[algorithm].append(time.perf_counter() - start)
                    results[algorithm] = result
                    print(scenario["id"], checkpoint, algorithm,
                          f"{samples[algorithm][-1]:.4f}s gap={result['nash_conv']:.8g}",
                          flush=True)
            for algorithm in algorithms:
                gc.collect()
                tracemalloc.start()
                try:
                    solve(scenario, checkpoint, algorithm, args.diagnostics)
                    peak = tracemalloc.get_traced_memory()[1]
                finally:
                    tracemalloc.stop()
                result = results[algorithm]
                for key in ("nash_conv", "value_oop", "oop_best_response_value",
                            "ip_best_response_value"):
                    if not math.isfinite(result[key]):
                        raise RuntimeError("Nonfinite benchmark metric: " + key)
                rows.append({"scenario": scenario["id"], "algorithm": algorithm,
                             "iterations": checkpoint, "runtime_samples": samples[algorithm],
                             "runtime_median": statistics.median(samples[algorithm]),
                             "peak_tracemalloc_bytes": peak,
                             "nash_conv_pot_fraction": result["nash_conv"] / result["pot"],
                             "game": {key: result[key] for key in (
                                 "nash_conv", "exploitability", "value_oop", "pot",
                                 "oop_best_response_value", "ip_best_response_value",
                                 "worlds", "info_sets", "public_nodes", "execution_backend")}})
    if hashes(args.config) != before:
        raise RuntimeError("Source/config changed during measurement; discard this run.")
    report = {"schema_version": 1, "benchmark_id": config["benchmark_id"],
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "provenance": {"revision": revision, "dirty": worktree_dirty(),
                             "python": platform.python_version(), "platform": platform.platform(),
                             "source_sha256": before},
              "methodology": {"timing": "Rotating interleaved whole solves plus JSON serialization",
                              "memory": "Separate untimed whole-call tracemalloc peak; excludes RSS",
                              "diagnostics": args.diagnostics,
                              "comparison": "Exact NashConv in each finite game; alternating CFR+ has two regret passes and one averaging pass per iteration, simultaneous methods have one pass.",
                              "limitations": "Synthetic ranges, conditional subsets where specified, machine-specific timings; no commercial solver equivalence."},
              "fixtures": config, "results": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
