"""Compare CFR+ public traversal before and after target-only regret passes.

The old public trainer is loaded from git revision 7553734 at runtime. Timed
intervals include the complete postflop solve and deterministic JSON encoding.
"""
import argparse
import gc
import hashlib
import importlib.util
import json
import platform
import statistics
import subprocess
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from pokerlab import postflop_solver
from pokerlab.postflop_solver import solve_postflop
from scripts.benchmark_public_cfr import _compare, _snapshot, COMPARE_METRICS
from scripts.benchmark_turn_solver import git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "benchmarks" / "turn-river-quality-v1.json"
OLD_REVISION = "7553734"
OLD_BLOB = "90e9e8155f64d73a2850f22bf0bd2ebd82ded937"
ITERATIONS = (100, 300)
REPEATS = 3
MEMORY_ITERATIONS = 20
TOLERANCE = 1e-10


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _source_fingerprints():
    names = (
        "public_cfr.py", "postflop_solver.py", "cfr_plus.py", "cfr.py",
        "river_tree.py", "river_config.py", "cards.py", "public_diagnostics.py",
        "planned_cfr.py", "turn_solver.py",
    )
    hashes = {f"pokerlab/{name}": hashlib.sha256(
        (ROOT / "pokerlab" / name).read_bytes()).hexdigest() for name in names}
    hashes["harness"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    compare_harness = ROOT / "scripts" / "benchmark_public_cfr.py"
    hashes["comparison_harness"] = hashlib.sha256(compare_harness.read_bytes()).hexdigest()
    hashes["config"] = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    return hashes


def _load_old_trainer():
    blob = subprocess.check_output(
        ["git", "rev-parse", f"{OLD_REVISION}:pokerlab/public_cfr.py"],
        cwd=ROOT, text=True,
    ).strip()
    if blob != OLD_BLOB:
        raise RuntimeError(f"Expected old trainer blob {OLD_BLOB}, found {blob}.")
    source = subprocess.check_output(
        ["git", "show", f"{OLD_REVISION}:pokerlab/public_cfr.py"], cwd=ROOT,
    )
    spec = importlib.util.spec_from_loader(
        "pokerlab._public_cfr_old", loader=None,
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "pokerlab"
    exec(compile(source, f"{OLD_REVISION}:pokerlab/public_cfr.py", "exec"),
         module.__dict__)
    return module, _sha256_bytes(source)


def _solve_serialized(scenario, iterations, trainer):
    kwargs = {key: scenario[key] for key in
              ("config", "turn_config", "river_config", "runouts") if key in scenario}
    kwargs.update(iterations=iterations, algorithm="cfrplus", traversal="public-batched")
    with patch.object(postflop_solver, "train_public_batched", trainer):
        result = solve_postflop(scenario["board"], scenario["oop"], scenario["ip"],
                                **kwargs)
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return result, len(payload.encode("utf-8"))


def _timed(scenario, iterations, trainer):
    gc.collect()
    started = time.perf_counter()
    result, size = _solve_serialized(scenario, iterations, trainer)
    return time.perf_counter() - started, result, size


def _peak(scenario, trainer):
    gc.collect()
    tracemalloc.start()
    try:
        _solve_serialized(scenario, MEMORY_ITERATIONS, trainer)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def run(config, old_module, skip_memory):
    trainers = {"old-7553734": old_module.train_public_batched,
                "candidate": postflop_solver.train_public_batched}
    results = []
    memory_by_scenario = {}
    offset = 0
    for scenario in config["scenarios"]:
        for iterations in ITERATIONS:
            samples = {name: [] for name in trainers}
            sizes = {name: [] for name in trainers}
            comparison = {
                "strategy_rows": 0,
                "max_probability_abs_diff": 0.0,
                "metric_abs_differences": {key: 0.0 for key in COMPARE_METRICS},
            }
            final_metrics = {}
            for repeat in range(REPEATS):
                order = list(trainers)
                shift = (offset + repeat) % len(order)
                order = order[shift:] + order[:shift]
                snapshots = {}
                for name in order:
                    elapsed, result, size = _timed(scenario, iterations, trainers[name])
                    samples[name].append(elapsed)
                    sizes[name].append(size)
                    snapshots[name] = _snapshot(result)
                    final_metrics[name] = dict(snapshots[name][1])
                    print(f"{scenario['id']} {iterations} {name} repeat {repeat + 1}: "
                          f"{elapsed:.3f}s", flush=True)
                    del result
                compared = _compare(
                    snapshots["old-7553734"], snapshots["candidate"],
                    f"{scenario['id']}/{iterations}/repeat-{repeat + 1}",
                )
                comparison["strategy_rows"] = compared["strategy_rows"]
                comparison["max_probability_abs_diff"] = max(
                    comparison["max_probability_abs_diff"],
                    compared["max_probability_abs_diff"],
                )
                for key, difference in compared["metric_abs_differences"].items():
                    comparison["metric_abs_differences"][key] = max(
                        comparison["metric_abs_differences"][key], difference,
                    )
                snapshots.clear()
            scenario_id = scenario["id"]
            if not skip_memory and scenario_id not in memory_by_scenario:
                memory_by_scenario[scenario_id] = {
                    name: _peak(scenario, trainer)
                    for name, trainer in trainers.items()
                }
            memory = {} if skip_memory else memory_by_scenario[scenario_id]
            results.append({
                "scenario_id": scenario["id"], "iterations": iterations,
                "repeats": REPEATS,
                "timing_includes_json_serialization": True,
                "whole_call_seconds": {name: {"samples": values,
                    "median": statistics.median(values)} for name, values in samples.items()},
                "serialized_bytes": sizes,
                "memory_peak_tracemalloc_bytes": memory,
                "memory_iterations": None if skip_memory else MEMORY_ITERATIONS,
                "comparison_vs_old": comparison,
                "final_measured_gaps": {
                    name: {key: metrics[key] for key in
                           ("value_oop", "value_ip", "oop_best_response_value",
                            "ip_best_response_value", "nash_conv", "exploitability")}
                    for name, metrics in final_metrics.items()
                },
                "comparison_tolerance": TOLERANCE,
            })
            offset += REPEATS
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-memory", action="store_true")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/results/cfrplus-target-v1.json")
    args = parser.parse_args(argv)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    old_module, old_sha = _load_old_trainer()
    before = _source_fingerprints()
    result = run(config, old_module, args.skip_memory)
    after = _source_fingerprints()
    if before != after:
        raise RuntimeError("Benchmark source changed during measurement; discard result.")
    report = {
        "schema_version": 1,
        "benchmark_id": "cfrplus-public-target-pass-v1",
        "old_revision": OLD_REVISION,
            "git_revision": git_revision(None),
        "worktree_dirty": worktree_dirty(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "old_source_sha256": old_sha,
        "candidate_source_sha256": before["pokerlab/public_cfr.py"],
        "source_sha256_before": before,
        "source_sha256_after": after,
        "scenario_config_sha256": hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        "results": result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"Wrote {len(result)} cases to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
