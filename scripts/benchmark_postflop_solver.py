"""Versioned exact postflop coverage, convergence and whole-call measurements."""
import argparse
import hashlib
import json
import platform
import statistics
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

from pokerlab.postflop_solver import solve_postflop
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("postflop_solver.py", "turn_solver.py", "cfr.py", "planned_cfr.py",
           "river_tree.py", "river_config.py", "cards.py")
METRICS = ("solver_version", "strategy_schema", "backend", "execution_backend",
           "plan_operation_limit", "runout_mode", "deals", "worlds", "info_sets",
           "public_nodes", "chance_nodes", "world_traversal_nodes", "tree_actions",
           "public_states", "terminal_nodes", "public_state_limit",
           "value_oop", "value_ip", "oop_best_response_value",
           "ip_best_response_value", "nash_conv", "exploitability", "scope")


def run_case(scenario, iterations, repeats, algorithm, traversal):
    kwargs = {key: scenario[key] for key in
              ("config", "turn_config", "river_config", "runouts") if key in scenario}
    kwargs.update(iterations=iterations, algorithm=algorithm, traversal=traversal)
    positional = (scenario["board"], scenario["oop"], scenario["ip"])
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        result = solve_postflop(*positional, **kwargs)
        samples.append(time.perf_counter() - started)
    # A separate solver call includes world/tree construction, training and BRs.
    tracemalloc.start()
    try:
        solve_postflop(*positional, **kwargs)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {
        "scenario_id": scenario["id"], "purpose": scenario["purpose"],
        "board": scenario["board"], "oop_range": scenario["oop"],
        "ip_range": scenario["ip"], "iterations": iterations, "repeats": repeats,
        "runtime_seconds": {"samples": samples, "median": statistics.median(samples)},
        "peak_tracemalloc_bytes": peak,
        "game": {key: result.get(key) for key in METRICS},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "benchmarks/postflop-v1.json")
    parser.add_argument("--algorithm", choices=("vanilla", "dcfr"), default="vanilla")
    parser.add_argument("--traversal", choices=("recursive", "planned"), default="recursive")
    parser.add_argument("--iterations", type=int, nargs="+")
    parser.add_argument("--repeats", type=int)
    parser.add_argument("--scenario", action="append")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision-label")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    iterations = args.iterations or config["defaults"]["checkpoints"]
    repeats = args.repeats if args.repeats is not None else config["defaults"]["repeats"]
    if any(type(n) is not int or not 10 <= n <= 10_000 for n in iterations):
        parser.error("Use 10–10,000 iterations per checkpoint.")
    if not 1 <= repeats <= 25:
        parser.error("Use 1–25 timed repeats.")
    scenarios = config["scenarios"]
    if args.scenario:
        unknown = set(args.scenario) - {s["id"] for s in scenarios}
        if unknown:
            parser.error("Unknown scenarios: " + ", ".join(sorted(unknown)))
        scenarios = [s for s in scenarios if s["id"] in args.scenario]
    source_hashes = {name: file_sha256(ROOT / "pokerlab" / name) for name in MODULES}
    revision = git_revision(args.revision_label)
    results = [run_case(s, n, repeats, args.algorithm, args.traversal)
               for s in scenarios for n in iterations]
    after_hashes = {name: file_sha256(ROOT / "pokerlab" / name) for name in MODULES}
    if source_hashes != after_hashes:
        raise RuntimeError("Solver source changed during measurement; discard this run.")
    report = {
        "schema_version": 1, "benchmark_id": config["benchmark_id"],
        "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": {"git_revision": revision, "worktree_dirty": worktree_dirty(),
                       "python_version": platform.python_version(), "platform": platform.platform(),
                       "source_sha256": source_hashes,
                       "harness_sha256": file_sha256(Path(__file__))},
        "methodology": {
            "timing": "perf_counter whole-call wall time; median of independent calls",
            "memory": "Separate whole-call tracemalloc peak, including exact BR evaluation",
            "quality": "Solver-reported exact information-set BRs for the finite configured game",
            "conditioning": "Selected ordered runouts condition the joint physical deal distribution",
        }, "results": results,
    }
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(results)} measurements to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
