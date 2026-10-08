"""Reproducible timing, memory, and exact-gap benchmark for the river solver.

Run from the repository root, for example:
    python -m scripts.benchmark_solver --scenario all-tie-board --iterations 10 --repeats 1
"""
from __future__ import annotations

import argparse
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

from pokerlab.solver import solve as current_solve

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "benchmarks" / "solver-v1.json"


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


def load_solver(path: Path | None):
    if path is None:
        return current_solve
    spec = importlib.util.spec_from_file_location("pokerlab._benchmark_solver", path.resolve())
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load solver source: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.solve


def solver_provenance(path: Path | None) -> dict:
    source = path.resolve() if path is not None else ROOT / "pokerlab" / "solver.py"
    return {
        "source": source.name if path is not None else "pokerlab/solver.py",
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def parse_checkpoints(value: str) -> list[int]:
    try:
        result = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use comma-separated integer checkpoints.") from exc
    if not result or any(n < 10 or n > 10000 for n in result):
        raise argparse.ArgumentTypeError("Checkpoints must be between 10 and 10000.")
    if len(set(result)) != len(result):
        raise argparse.ArgumentTypeError("Checkpoints must be unique.")
    return result


def run_case(scenario: dict, checkpoint: int, repeats: int, pot: float, bet: float,
             algorithm: str, solve_fn) -> dict:
    kwargs = dict(
        board=scenario["board"], oop_range=scenario["oop_range"],
        ip_range=scenario["ip_range"], pot=pot, bet=bet, iterations=checkpoint,
    )
    # Keep the vanilla baseline compatible with the pre-option solver API.
    if algorithm != "vanilla":
        kwargs["algorithm"] = algorithm
    durations = []
    last = None
    for _ in range(repeats):
        started = time.perf_counter()
        last = solve_fn(**kwargs)
        durations.append(time.perf_counter() - started)

    # Memory measurement is intentionally a separate, untimed solver run.
    tracemalloc.start()
    try:
        solve_fn(**kwargs)
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert last is not None
    return {
        "scenario_id": scenario["id"],
        "purpose": scenario["purpose"],
        "board": scenario["board"],
        "oop_range": scenario["oop_range"],
        "ip_range": scenario["ip_range"],
        "iterations": checkpoint,
        "repeats": repeats,
        "runtime_seconds": {
            "samples": durations,
            "median": statistics.median(durations),
        },
        "peak_tracemalloc_bytes": peak_bytes,
        "game": {
            "scope": last["scope"],
            "pot": last["pot"],
            "bet": last["bet"],
            "value_oop": last["value_oop"],
            "value_ip": last["value_ip"],
        },
        "deal_count": last["deals"],
        "information_set_count": last["info_sets"],
        "algorithm": {
            "name": algorithm,
            "method": last["method"],
            "variant": last.get("cfr_variant"),
            "solver_version": last.get("solver_version"),
        },
        "exact_gap": {
            "nash_conv": last["nash_conv"],
            "exploitability": last["exploitability"],
            "oop_best_response_gain": last["oop_best_response_gain"],
            "note": last["gap_note"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help="Versioned scenario JSON (default: benchmarks/solver-v1.json).")
    parser.add_argument("--solver-source", type=Path,
                        help="Load a solver implementation from a Python source file, useful for comparisons.")
    parser.add_argument("--scenario", action="append", dest="scenario_ids",
                        help="Run only this scenario ID; repeat the option to select several.")
    parser.add_argument("--algorithm", choices=("vanilla", "dcfr"), default="vanilla",
                        help="Solver algorithm (default: vanilla). DCFR requires solver support.")
    parser.add_argument("--iterations", type=parse_checkpoints,
                        help="Comma-separated checkpoint(s), e.g. 50 or 50,200,500.")
    parser.add_argument("--repeats", type=int, help="Timed repeats per checkpoint (default: config).")
    parser.add_argument("--output", type=Path, help="Write result JSON here; stdout is always emitted too.")
    parser.add_argument("--revision-label", help="Override the Git revision provenance label.")
    args = parser.parse_args(argv)

    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    try:
        solve_fn = load_solver(args.solver_source)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    defaults = config["defaults"]
    checkpoints = args.iterations or defaults["checkpoints"]
    repeats = args.repeats if args.repeats is not None else defaults["repeats"]
    if repeats < 1 or repeats > 25:
        parser.error("--repeats must be between 1 and 25.")
    selected = config["scenarios"]
    if args.scenario_ids:
        wanted = set(args.scenario_ids)
        known = {item["id"] for item in selected}
        unknown = wanted - known
        if unknown:
            parser.error("Unknown scenario ID(s): " + ", ".join(sorted(unknown)))
        selected = [item for item in selected if item["id"] in wanted]
    if not selected:
        parser.error("At least one scenario is required.")

    results = []
    for scenario in selected:
        pot = scenario.get("pot", defaults["pot"])
        bet = scenario.get("bet", defaults["bet"])
        for checkpoint in checkpoints:
            results.append(run_case(
                scenario, checkpoint, repeats, pot, bet, args.algorithm, solve_fn,
            ))
    report = {
        "schema_version": 1,
        "benchmark_id": config["benchmark_id"],
        "config_schema_version": config["schema_version"],
        "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "git_revision": git_revision(args.revision_label),
            "worktree_dirty": worktree_dirty(),
            "solver": solver_provenance(args.solver_source),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
        },
        "methodology": {
            "timing": "perf_counter wall time; median of independent solver calls",
            "memory": "tracemalloc peak from a separate untimed solver call",
            "exact_gap": "Exact best-response NashConv and exploitability returned by the solver.",
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
