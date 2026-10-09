"""Compare conditioned preflop methods using independently replayed policies."""
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
           "pokerlab/cfr.py", "pokerlab/cfr_plus.py", "pokerlab/planned_cfr.py",
           "pokerlab/cards.py", "scripts/preflop_validation.py",
           "scripts/benchmark_preflop_cfrplus.py", "scripts/benchmark_turn_solver.py",
           "benchmarks/preflop-cfrplus-v1.json")


def run_case(scenario, iterations, repeats, algorithm, memory_iterations):
    kwargs = {key: scenario[key] for key in
              ("config", "runouts", "flop_config", "turn_config", "river_config")
              if key in scenario}
    positional = scenario["sb"], scenario["bb"]
    samples = []
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = solve_preflop(*positional, iterations=iterations, algorithm=algorithm,
                               traversal="recursive", **kwargs)
        samples.append(time.perf_counter() - started)
    oracle = replay_policy(result, *positional, **kwargs)
    gaps = compare_result(result, oracle)
    production_pairs = {(row["sb_hand"], row["bb_hand"]): row["probability"]
                        for row in result["private_pair_probabilities"]}
    oracle_pairs = {(row["sb"], row["bb"]): row["probability"]
                    for row in oracle["private_pair_probabilities"]}
    assert production_pairs.keys() == oracle_pairs.keys()
    posterior_gap = max(abs(production_pairs[key] - oracle_pairs[key])
                        for key in production_pairs)
    assert posterior_gap <= 1e-12, posterior_gap
    memory = None
    if iterations == memory_iterations:
        tracemalloc.start()
        try:
            traced = solve_preflop(*positional, iterations=iterations, algorithm=algorithm,
                                   traversal="recursive", **kwargs)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert traced["strategy"] == result["strategy"]
        memory = {"iterations": iterations, "peak_traced_python_bytes": peak}
    return {"scenario": scenario["id"], "iterations": iterations, "algorithm": algorithm,
            "traversal": "recursive", "seconds": samples,
            "median_seconds": statistics.median(samples), "memory": memory,
            "training_passes_per_iteration": result.get("training_passes_per_iteration", 1),
            "training_passes": result.get("training_passes", iterations),
            "training_schedule": result.get("training_schedule", "simultaneous updates"),
            "worlds": result["worlds"], "public_states": result["public_states"],
            "decisions": result["decisions"], "information_sets": result["info_sets"],
            "value_sb": result["value_sb"], "nash_conv": result["nash_conv"],
            "sb_best_response_value": result["sb_best_response_value"],
            "bb_best_response_value": result["bb_best_response_value"],
            "independent_replay": oracle, "metric_absolute_gaps": gaps,
            "private_pair_max_probability_gap": posterior_gap}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "benchmarks/preflop-cfrplus-v1.json")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/results/preflop-cfrplus-v1.json")
    args = parser.parse_args()
    specification = json.loads(args.config.read_text(encoding="utf-8"))
    repeats = specification["repeats"]
    checkpoints = specification["iterations"]
    assert repeats >= 1 and len(checkpoints) >= 2 and checkpoints == sorted(set(checkpoints))
    assert specification["memory_iterations"] in checkpoints
    records = []
    for scenario in specification["scenarios"]:
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            series = []
            for iterations in checkpoints:
                record = run_case(scenario, iterations, repeats, algorithm,
                                  specification["memory_iterations"])
                series.append(record)
                records.append(record)
                print(f'{scenario["id"]} {algorithm} {iterations}: '
                      f'NashConv={record["nash_conv"]:.8g}, '
                      f'{record["median_seconds"]:.4f}s', flush=True)
            # Endpoint checks for these fixtures, not a monotonic convergence theorem.
            assert series[-1]["nash_conv"] <= series[0]["nash_conv"] + 1e-12, series
            if algorithm == "cfrplus":
                assert series[-1]["nash_conv"] <= .1, series
                if scenario["id"] == "hidden-flop-forced-big-blind":
                    for record in series:
                        assert abs(record["value_sb"]) <= 1e-12
                        assert abs(record["nash_conv"]) <= 1e-12
                        assert abs(record["sb_best_response_value"]) <= 1e-12
                        assert abs(record["bb_best_response_value"]) <= 1e-12
    report = {"schema_version": 1, "benchmark_id": specification["benchmark_id"],
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "source_revision": git_revision(None), "worktree_dirty": worktree_dirty(),
              "source_hashes": {path: file_sha256(ROOT / path) for path in SOURCES},
              "python": platform.python_version(), "platform": platform.platform(),
              "repeats": repeats, "memory_iterations": specification["memory_iterations"],
              "timing_scope": "Complete call including worlds, tree, training, exact legal best responses and serialization; independent replay excluded.",
              "memory_scope": "Separate 10-iteration complete calls under tracemalloc only. No 100-iteration measurement, RSS or process-memory ceiling.",
              "oracle_scope": "Independent world weights, best-five rankings, numeric betting/history replay and exact legal information-set responses to serialized averages; card/range parsing shared.",
              "comparison_scope": "Recursive methods at equal iteration counts, not equal compute budgets: CFR+ uses three world passes per iteration, vanilla/DCFR one. Tiny conditioned selected-outcome games only; no full-deck preflop or unrestricted NLHE claim.",
              "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
