"""Whole-call preflop vector comparison with independent policy replay."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import statistics
import time
import tracemalloc
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty
from scripts.preflop_validation import compare_result, replay_policy

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("pokerlab/preflop_solver.py", "pokerlab/preflop_tree.py",
           "pokerlab/postflop_solver.py", "pokerlab/river_tree.py", "pokerlab/river_config.py",
           "pokerlab/cfr.py", "pokerlab/cfr_plus.py", "pokerlab/planned_cfr.py",
           "pokerlab/public_cfr.py", "pokerlab/cards.py", "pokerlab/analysis.py",
           "scripts/preflop_validation.py", "scripts/benchmark_preflop_public_batched.py",
           "scripts/benchmark_turn_solver.py", "benchmarks/preflop-public-batched-v1.json")


def measured_solve(scenario, iterations, algorithm, traversal):
    phases = {}

    def timed(name, function):
        def run(*args, **kwargs):
            started = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                phases[name] = phases.get(name, 0.0) + time.perf_counter() - started
        return run

    targets = ((solver, "_enumerate_physical_worlds", "enumeration_and_ranking"),
               (solver, "build_preflop_tree", "preflop_tree"),
               (solver, "_merge_preflop_tree", "postflop_templates_and_grafting"),
               (solver.cfr, "train", "training"),
               (solver, "train_public_batched", "training"),
               (solver.cfr, "evaluate", "evaluation"),
               (solver.cfr, "best_response", "both_best_responses"))
    with ExitStack() as stack:
        for module, attribute, name in targets:
            stack.enter_context(patch.object(module, attribute, timed(name, getattr(module, attribute))))
        started = time.perf_counter()
        result = solver.solve_preflop(scenario["sb"], scenario["bb"],
                                     config=scenario["config"], runouts=scenario["runouts"],
                                     iterations=iterations, algorithm=algorithm, traversal=traversal)
        seconds = time.perf_counter() - started
    phases["other_including_serialization_and_training_view"] = max(0.0, seconds - sum(phases.values()))
    return result, seconds, phases


def checked_record(scenario, iterations, repeats, algorithm, traversal, memory_iterations):
    timings, phases = [], []
    result = None
    for _ in range(repeats):
        result, seconds, phase = measured_solve(scenario, iterations, algorithm, traversal)
        timings.append(seconds)
        phases.append(phase)
    oracle = replay_policy(result, scenario["sb"], scenario["bb"],
                           config=scenario["config"], runouts=scenario["runouts"])
    gaps = compare_result(result, oracle)
    produced = {(row["sb_hand"], row["bb_hand"]): row["probability"]
                for row in result["private_pair_probabilities"]}
    expected = {(row["sb"], row["bb"]): row["probability"]
                for row in oracle["private_pair_probabilities"]}
    assert produced.keys() == expected.keys()
    posterior_gap = max(abs(produced[pair] - expected[pair]) for pair in produced)
    assert posterior_gap <= 1e-12
    memory = None
    if iterations == memory_iterations:
        tracemalloc.start()
        try:
            traced = solver.solve_preflop(scenario["sb"], scenario["bb"],
                                         config=scenario["config"], runouts=scenario["runouts"],
                                         iterations=iterations, algorithm=algorithm, traversal=traversal)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert traced["strategy"] == result["strategy"]
        memory = {"iterations": iterations, "peak_traced_python_bytes": peak}
    record = {"scenario": scenario["id"], "iterations": iterations, "algorithm": algorithm,
              "traversal": traversal, "seconds": timings, "median_seconds": statistics.median(timings),
              "phase_seconds": phases,
              "phase_median_seconds": {key: statistics.median(phase[key] for phase in phases)
                                       for key in phases[0]},
              "memory": memory, "worlds": result["worlds"],
              "compatible_private_pairs": result["compatible_private_pairs"],
              "information_sets": result["info_sets"], "public_states": result["public_states"],
              "decisions": result["decisions"],
              "value_sb": result["value_sb"], "nash_conv": result["nash_conv"],
              "sb_best_response_value": result["sb_best_response_value"],
              "bb_best_response_value": result["bb_best_response_value"],
              "independent_replay": oracle, "metric_absolute_gaps": gaps,
              "private_pair_max_probability_gap": posterior_gap}
    return record, result


def policy_gap(left, right):
    largest = 0.0
    assert len(left) == len(right)
    for a, b in zip(left, right):
        for field in ("player", "hand", "street", "revealed_board", "history"):
            assert a[field] == b[field], field
        assert len(a["actions"]) == len(b["actions"])
        for x, y in zip(a["actions"], b["actions"]):
            for field in ("name", "amount", "raise_to", "history_key"):
                assert x[field] == y[field], field
            largest = max(largest, abs(x["probability"] - y["probability"]))
    assert largest <= 1e-10, largest
    return largest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "benchmarks/preflop-public-batched-v1.json")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/results/preflop-public-batched-v1.json")
    args = parser.parse_args()
    specification = json.loads(args.config.read_text(encoding="utf-8"))
    assert specification["repeats"] >= 1 and specification["memory_iterations"] in specification["iterations"]
    records, comparisons = [], []
    for scenario in specification["scenarios"]:
        for algorithm in specification["algorithms"]:
            series = []
            for iterations in specification["iterations"]:
                peers = []
                for traversal in ("recursive", "public-batched"):
                    record, result = checked_record(scenario, iterations, specification["repeats"],
                                                    algorithm, traversal, specification["memory_iterations"])
                    records.append(record)
                    peers.append((record, result))
                    print(f'{scenario["id"]} {algorithm}/{traversal} {iterations}: '
                          f'NashConv={record["nash_conv"]:.8g}, {record["median_seconds"]:.4f}s', flush=True)
                scalar_gaps = {field: abs(peers[0][0][field] - peers[1][0][field]) for field in
                               ("value_sb", "nash_conv", "sb_best_response_value", "bb_best_response_value")}
                assert max(scalar_gaps.values()) <= 1e-10, scalar_gaps
                comparisons.append({"scenario": scenario["id"], "algorithm": algorithm,
                                    "iterations": iterations, "scalar_absolute_gaps": scalar_gaps,
                                    "maximum_policy_probability_gap": policy_gap(peers[0][1]["strategy"], peers[1][1]["strategy"]),
                                    "recursive_over_vector_time_ratio": peers[0][0]["median_seconds"] / peers[1][0]["median_seconds"]})
                series.append(peers[0][0])
            assert series[-1]["nash_conv"] < series[0]["nash_conv"]
    report = {"schema_version": 1, "benchmark_id": specification["benchmark_id"],
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "source_revision": git_revision(None), "worktree_dirty": worktree_dirty(),
              "source_hashes": {path: file_sha256(ROOT / path) for path in SOURCES},
              "python": platform.python_version(), "platform": platform.platform(),
              "repeats": specification["repeats"], "memory_iterations": specification["memory_iterations"],
              "timing_scope": "Three complete calls including construction, training view, training, exact responses and serialization. Phase timers add fixed wrapper overhead; oracle excluded.",
              "phase_scope": "Median inclusive calls for enumeration/ranking, preflop building, grafting, training, evaluation and both responses. Remaining time includes info sets, training view and serialization. Phase medians need not sum to the total median.",
              "memory_scope": "Separate uninstrumented complete 10-iteration calls under tracemalloc; Python allocations, not RSS, no 100-iteration memory measurement.",
              "scope": "Exact backend comparison for tiny conditioned selected-outcome games, including all six AA and all six KK combinations. Not full ranges/full-deck preflop; CFR+ parity tested separately, not timed here.",
              "records": records, "comparisons": comparisons}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
