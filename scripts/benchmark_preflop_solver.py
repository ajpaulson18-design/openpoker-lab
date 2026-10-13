"""Whole-call timings, separate traced allocations and independent legal BRs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import statistics
import time
import tracemalloc

from pokerlab.preflop_solver import solve_preflop
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty
from scripts.preflop_validation import compare_result, replay_policy

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("pokerlab/preflop_solver.py", "pokerlab/preflop_tree.py",
           "pokerlab/postflop_solver.py", "pokerlab/river_tree.py", "pokerlab/river_config.py",
           "pokerlab/cfr.py", "pokerlab/planned_cfr.py", "pokerlab/cards.py",
           "scripts/preflop_validation.py", "scripts/benchmark_preflop_solver.py",
           "scripts/benchmark_turn_solver.py", "benchmarks/preflop-solver-v1.json")


def run_case(scenario, iterations, repeats, algorithm, traversal):
    kwargs = {key: scenario[key] for key in ("config", "runouts", "flop_config", "turn_config", "river_config") if key in scenario}
    positional = scenario["sb"], scenario["bb"]
    samples = []
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = solve_preflop(*positional, iterations=iterations, algorithm=algorithm, traversal=traversal, **kwargs)
        samples.append(time.perf_counter() - started)
    oracle = replay_policy(result, *positional, **kwargs)
    gaps = compare_result(result, oracle)
    production_pairs = {(item["sb_hand"], item["bb_hand"]): item["probability"] for item in result["private_pair_probabilities"]}
    oracle_pairs = {(item["sb"], item["bb"]): item["probability"] for item in oracle["private_pair_probabilities"]}
    assert production_pairs.keys() == oracle_pairs.keys()
    assert max(abs(production_pairs[key] - oracle_pairs[key]) for key in production_pairs) < 1e-12
    tracemalloc.start()
    try:
        traced = solve_preflop(*positional, iterations=iterations, algorithm=algorithm, traversal=traversal, **kwargs)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert traced["strategy"] == result["strategy"]
    return {"scenario": scenario["id"], "iterations": iterations, "algorithm": algorithm,
            "traversal": traversal, "seconds": samples, "median_seconds": statistics.median(samples),
            "peak_traced_python_bytes": peak,
            "worlds": result["worlds"], "public_states": result["public_states"],
            "decisions": result["decisions"], "information_sets": result["info_sets"],
            "value_sb": result["value_sb"], "nash_conv": result["nash_conv"],
            "sb_best_response_value": result["sb_best_response_value"],
            "bb_best_response_value": result["bb_best_response_value"],
            "independent_replay": oracle, "metric_absolute_gaps": gaps}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "benchmarks/preflop-solver-v1.json")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/results/preflop-solver-v1.json")
    parser.add_argument("--repeats", type=int)
    args = parser.parse_args()
    specification = json.loads(args.config.read_text(encoding="utf-8"))
    repeats = args.repeats if args.repeats is not None else specification["repeats"]
    if repeats < 1:
        parser.error("repeats must be positive")
    records = []
    for scenario in specification["scenarios"]:
        for algorithm in ("vanilla", "dcfr"):
            for iterations in specification["iterations"]:
                peers = []
                for traversal in ("recursive", "planned"):
                    record = run_case(scenario, iterations, repeats, algorithm, traversal)
                    records.append(record)
                    peers.append(record)
                    print(f'{scenario["id"]} {algorithm}/{traversal} {iterations}: NashConv={record["nash_conv"]:.8g}, {record["median_seconds"]:.4f}s', flush=True)
                for field in ("value_sb", "nash_conv", "sb_best_response_value", "bb_best_response_value"):
                    assert abs(peers[0][field] - peers[1][field]) <= 1e-10, (field, peers)
            checkpoints = [record for record in records if record["scenario"] == scenario["id"] and record["algorithm"] == algorithm]
            for traversal in ("recursive", "planned"):
                series = [record for record in checkpoints if record["traversal"] == traversal]
                assert series[-1]["nash_conv"] < series[0]["nash_conv"], series
                # Fixed gates for these tiny fixtures; no global CFR guarantee.
                assert series[-1]["nash_conv"] <= {"vanilla": .02, "dcfr": .001}[algorithm], series
    report = {"schema_version": 1, "benchmark_id": specification["benchmark_id"],
              "generated_at": datetime.now(timezone.utc).isoformat(), "source_revision": git_revision(None),
              "worktree_dirty": worktree_dirty(), "source_hashes": {path: file_sha256(ROOT / path) for path in SOURCES},
              "python": platform.python_version(), "platform": platform.platform(), "repeats": repeats,
              "timing_scope": "Complete call: physical-world enumeration, public tree, training, exact legal best responses and serialization. Independent replay excluded from timing.",
              "memory_scope": "Separate complete call under tracemalloc; traced Python allocations, not RSS or a universal process-memory ceiling.",
              "oracle_scope": "Independent physical-world weights, enumerated best-five rankings, numeric betting/history replay and exact legal information-set responses to serialized average policies; card/range parsing shared.",
              "scope": "Tiny conditioned selected-outcome games. No full-deck preflop, unrestricted NLHE, multiway, rake or performance scaling claim.",
              "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
