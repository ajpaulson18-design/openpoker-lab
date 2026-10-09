"""Measure target exploitability stopping against a fixed turn/river budget.

Runs complete public-batched solves for the four fixtures in
turn-river-quality-v1.json. Exact exploitability is the solver's full
best-response diagnostic at each recorded checkpoint. Timings include that
diagnostic and result construction, but exclude JSON serialization.
"""
import argparse
import gc
import hashlib
import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pokerlab.postflop_solver import solve_postflop
from scripts.benchmark_turn_solver import git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "benchmarks" / "turn-river-quality-v1.json"
ALGORITHMS = ("dcfr", "cfrplus")
REPEATS = 3
MAX_ITERATIONS = 300
CHECK_INTERVAL = 20
TARGET = 0.1


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _solve(scenario, algorithm, *, target=None):
    kwargs = {key: scenario[key] for key in
              ("config", "turn_config", "river_config", "runouts") if key in scenario}
    kwargs.update(iterations=MAX_ITERATIONS, algorithm=algorithm,
                  traversal="public-batched", diagnostics="public-batched")
    if target is not None:
        kwargs.update(target_exploitability=target, check_interval=CHECK_INTERVAL)
    return solve_postflop(scenario["board"], scenario["oop"], scenario["ip"], **kwargs)


def _strategy_delta(left, right):
    a, b = left["strategy"], right["strategy"]
    if len(a) != len(b):
        return {"same_rows": False, "rows": max(len(a), len(b)),
                "max_probability_abs_difference": None}
    maximum = 0.0
    for row_a, row_b in zip(a, b):
        if (row_a["player"], row_a["hand"], row_a["street"], row_a["board"],
                row_a["history"]) != (row_b["player"], row_b["hand"], row_b["street"],
                                       row_b["board"], row_b["history"]):
            return {"same_rows": False, "rows": len(a),
                    "max_probability_abs_difference": None}
        for action_a, action_b in zip(row_a["actions"], row_b["actions"]):
            maximum = max(maximum, abs(action_a["probability"] - action_b["probability"]))
    return {"same_rows": True, "rows": len(a),
            "max_probability_abs_difference": maximum}


def _timed(scenario, algorithm, target):
    gc.collect()
    start = time.perf_counter()
    result = _solve(scenario, algorithm, target=target)
    elapsed = time.perf_counter() - start
    return elapsed, result


def run(config, repeats=REPEATS):
    rows = []
    for scenario in config["scenarios"]:
        for algorithm in ALGORITHMS:
            variants = ("fixed-300", "target-0.1", "target-0-checkpoint-overhead")
            samples = {variant: [] for variant in variants}
            latest = {}
            for repeat in range(repeats):
                # Rotate order to reduce systematic warm-up and load bias.
                order = list(variants)
                shift = repeat % len(order)
                order = order[shift:] + order[:shift]
                for variant in order:
                    target = {"fixed-300": None, "target-0.1": TARGET,
                              "target-0-checkpoint-overhead": 0.0}[variant]
                    elapsed, result = _timed(scenario, algorithm, target)
                    samples[variant].append(elapsed)
                    latest[variant] = result
                    print(f"{scenario['id']} {algorithm} {variant} repeat {repeat + 1}: "
                          f"{elapsed:.3f}s, iterations={result['iterations']}, "
                          f"exploitability={result['exploitability']:.8g}", flush=True)
            adaptive = latest["target-0.1"]
            actual = adaptive["iterations"]
            # Strategy equality is meaningful only at the same iteration count.
            if actual == MAX_ITERATIONS:
                reference = latest["fixed-300"]
                strategy_comparison = _strategy_delta(reference, adaptive)
                strategy_reference = "fixed-300"
            else:
                # Fixed API has no arbitrary cap; for a shorter-budget reference,
                # call the shared solver explicitly at that iteration count.
                kwargs = {key: scenario[key] for key in
                          ("config", "turn_config", "river_config", "runouts") if key in scenario}
                kwargs.update(iterations=actual, algorithm=algorithm,
                              traversal="public-batched", diagnostics="public-batched")
                gc.collect()
                reference = solve_postflop(scenario["board"], scenario["oop"], scenario["ip"], **kwargs)
                strategy_comparison = _strategy_delta(reference, adaptive)
                strategy_reference = f"fixed-{actual}"
            rows.append({
                "scenario_id": scenario["id"], "algorithm": algorithm,
                "target_chips": TARGET, "pot_chips": 100,
                "target_percent_of_pot": TARGET,
                "max_iterations": MAX_ITERATIONS, "check_interval": CHECK_INTERVAL,
                "repeats": repeats,
                "variants": {
                    variant: {
                        "whole_call_seconds": samples[variant],
                        "median_seconds": statistics.median(samples[variant]),
                        "iterations": latest[variant]["iterations"],
                        "exploitability_chips": latest[variant]["exploitability"],
                        "nash_conv_chips": latest[variant]["nash_conv"],
                        "convergence": latest[variant].get("convergence"),
                    } for variant in variants
                },
                "target_result": "achieved" if adaptive["convergence"]["stop_reason"] == "target-reached" else "budget-miss",
                "strategy_comparison_to_same_iteration_fixed_run": {
                    "reference": strategy_reference, **strategy_comparison,
                },
                "speedup_vs_fixed_300": (
                    statistics.median(samples["fixed-300"]) /
                    statistics.median(samples["target-0.1"])),
                "checkpoint_overhead_vs_fixed_300": (
                    statistics.median(samples["target-0-checkpoint-overhead"]) /
                    statistics.median(samples["fixed-300"]) - 1.0),
            })
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/results/turn-river-accuracy-v1.json")
    parser.add_argument("--repeats", type=int, default=REPEATS)
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 10:
        parser.error("Use 1-10 repeats.")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    source_paths = (Path(__file__).resolve(), ROOT / "pokerlab/postflop_solver.py",
                    ROOT / "pokerlab/public_cfr.py", ROOT / "pokerlab/public_diagnostics.py",
                    CONFIG)
    hashes_before = {str(path.relative_to(ROOT)): _sha256(path) for path in source_paths}
    rows = run(config, args.repeats)
    hashes_after = {str(path.relative_to(ROOT)): _sha256(path) for path in source_paths}
    if hashes_before != hashes_after:
        raise RuntimeError("Source or fixture changed during benchmark; discard this run.")
    report = {
        "schema_version": 1,
        "benchmark_id": "turn-river-accuracy-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "python": sys.version,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "revision": git_revision(None),
            "worktree_dirty": worktree_dirty(),
            "configuration": {"algorithms": ALGORITHMS, "iterations": MAX_ITERATIONS,
                              "target_exploitability_chips": TARGET,
                              "check_interval": CHECK_INTERVAL, "repeats": args.repeats,
                              "traversal": "public-batched", "diagnostics": "public-batched"},
            "input_fixture": str(CONFIG.relative_to(ROOT)),
            "input_sha256": _sha256(CONFIG),
            "command": "python -m scripts.benchmark_turn_river_accuracy",
            "source_sha256": hashes_before,
        },
        "methodology": {
            "timing": "Complete solve_postflop call; includes exact public-batched best-response checks and result assembly, excludes JSON serialization.",
            "target_units": "Absolute exploitability in chips; fixture pot is 100, so 0.1 chips is 0.1% pot.",
            "checkpoint_overhead": "target=0 forces checks every 20 iterations and ordinarily runs to cap; compared with an otherwise identical fixed 300 solve.",
            "strategy_comparison": "Adaptive strategy compared with a fixed-budget solve at the same actual iteration count; probability absolute difference.",
            "limitations": "Four synthetic turn/river fixtures, machine-specific timings, conditional runout subsets as specified by fixture; no claim of general equilibrium accuracy.",
        },
        "fixtures": config,
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(f"Wrote {len(rows)} cases to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
