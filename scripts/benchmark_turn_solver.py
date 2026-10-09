"""Reproducible benchmark for the restricted heads-up turn-to-river solver.

Run from the repository root after ``pokerlab.turn_solver`` is available:
    python -m scripts.benchmark_turn_solver --algorithm vanilla
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

from pokerlab.turn_solver import solve_turn_river

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "benchmarks" / "turn-river-v1.json"
SOURCE_MODULES = (
    "turn_solver.py", "postflop_solver.py", "cfr.py", "planned_cfr.py", "public_cfr.py",
    "river_tree.py", "river_config.py", "cards.py",
)


def file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def git_revision(label: str | None) -> str:
    if label:
        return label
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def worktree_dirty() -> bool | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, check=True,
            capture_output=True, text=True, timeout=5,
        )
        return bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None


def source_hashes() -> dict[str, str | None]:
    return {
        name.removesuffix(".py"): file_sha256(ROOT / "pokerlab" / name)
        for name in SOURCE_MODULES
    }


def metric(result: dict, *keys):
    for key in keys:
        if key in result:
            return result[key]
    return None


def run_case(scenario: dict, iterations: int, repeats: int, algorithm: str,
             traversal: str = "recursive") -> dict:
    positional = (scenario["board4"], scenario["oop"], scenario["ip"])
    kwargs = {
        "iterations": iterations,
        "algorithm": algorithm,
        "traversal": traversal,
    }
    for name in ("config", "river_config", "runouts"):
        if name in scenario and scenario[name] is not None:
            kwargs[name] = scenario[name]

    samples = []
    last = None
    for _ in range(repeats):
        started = time.perf_counter()
        last = solve_turn_river(*positional, **kwargs)
        samples.append(time.perf_counter() - started)

    # Peak memory is sampled on a separate call so tracing does not affect time.
    tracemalloc.start()
    try:
        solve_turn_river(*positional, **kwargs)
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert last is not None
    return {
        "scenario_id": scenario["id"],
        "purpose": scenario["purpose"],
        "runout_scope": scenario["runout_scope"],
        "conditioned_subset_only": scenario["runout_scope"] == "selected-conditioned-subset",
        "board4": scenario["board4"],
        "oop_range": scenario["oop"],
        "ip_range": scenario["ip"],
        "iterations": iterations,
        "repeats": repeats,
        "runtime_seconds": {
            "samples": samples,
            "median": statistics.median(samples),
        },
        "peak_tracemalloc_bytes": peak_bytes,
        "game": {
            "config": metric(last, "config", "turn_config"),
            "river_config": metric(last, "river_config", "normalized_river_config"),
            "runouts": metric(last, "runouts", "selected_runouts"),
            "reachable_runouts": metric(last, "reachable_runouts"),
            "runout_mode": metric(last, "runout_mode"),
            "world_count": metric(last, "world_count", "worlds"),
            "deal_count": metric(last, "deal_count", "deals"),
            "public_nodes": metric(last, "public_nodes", "node_count"),
            "chance_nodes": metric(last, "chance_nodes"),
            "world_traversal_nodes": metric(last, "world_traversal_nodes"),
            "information_set_count": metric(last, "info_sets", "infosets", "information_sets"),
            "value_oop": metric(last, "value_oop"),
            "value_ip": metric(last, "value_ip"),
            "oop_best_response_value": metric(last, "oop_best_response_value", "br_oop"),
            "ip_best_response_value": metric(last, "ip_best_response_value", "br_ip"),
            "nash_conv": metric(last, "nash_conv"),
            "exploitability": metric(last, "exploitability"),
            "algorithm": metric(last, "algorithm"),
            "solver_version": metric(last, "solver_version"),
            "backend": metric(last, "backend"),
            "execution_backend": metric(last, "execution_backend"),
            "plan_operation_limit": metric(last, "plan_operation_limit"),
            "scope": metric(last, "scope", "scope_note"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help="Versioned turn/rivers benchmark scenarios.")
    parser.add_argument("--scenario", action="append", dest="scenario_ids",
                        help="Run only this fixture; repeat to select multiple.")
    parser.add_argument("--algorithm", choices=("vanilla", "dcfr"), default="vanilla")
    parser.add_argument("--traversal", choices=("recursive", "planned", "public-batched"), default="recursive")
    parser.add_argument("--iterations", type=int, nargs="+",
                        help="Override checkpoints, for example --iterations 20 100.")
    parser.add_argument("--repeats", type=int, help="Timed repeats per checkpoint; defaults to config.")
    parser.add_argument("--output", type=Path, help="Write JSON here; stdout is also emitted.")
    parser.add_argument("--revision-label", help="Override the Git revision provenance label.")
    args = parser.parse_args(argv)

    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    checkpoints = args.iterations or config["defaults"]["checkpoints"]
    if any(value < 1 for value in checkpoints):
        parser.error("Iteration checkpoints must be positive.")
    repeats = args.repeats if args.repeats is not None else config["defaults"]["repeats"]
    if not 1 <= repeats <= 25:
        parser.error("--repeats must be between 1 and 25.")
    scenarios = config["scenarios"]
    if args.scenario_ids:
        requested = set(args.scenario_ids)
        known = {scenario["id"] for scenario in scenarios}
        unknown = requested - known
        if unknown:
            parser.error("Unknown scenario ID(s): " + ", ".join(sorted(unknown)))
        scenarios = [scenario for scenario in scenarios if scenario["id"] in requested]
    if not scenarios:
        parser.error("At least one scenario must be selected.")

    results = [run_case(scenario, iteration, repeats, args.algorithm, args.traversal)
               for scenario in scenarios for iteration in checkpoints]
    report = {
        "schema_version": 1,
        "benchmark_id": config["benchmark_id"],
        "config_schema_version": config["schema_version"],
        "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "git_revision": git_revision(args.revision_label),
            "worktree_dirty": worktree_dirty(),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "source_sha256": source_hashes(),
        },
        "methodology": {
            "timing": "perf_counter wall time; median of independent solver calls",
            "memory": "tracemalloc peak from a separate untimed solver call",
            "conditional_runouts": "Selected runout fixtures are conditional-subset experiments, not unrestricted physical turn games.",
            "exact_gap": "Uses the solver-reported information-set best responses and NashConv.",
        },
        "results": results,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
