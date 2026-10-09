"""Whole-call comparison of optional exact preflop diagnostic backends."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import gc
from itertools import permutations
import json
from pathlib import Path
import platform
import statistics
import time
import tracemalloc
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from scripts.benchmark_preflop_public_batched import policy_gap
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty
from scripts.preflop_validation import compare_result, replay_policy

ROOT = Path(__file__).resolve().parents[1]
SOURCES = tuple("pokerlab/" + name + ".py" for name in (
    "preflop_solver", "preflop_tree", "postflop_solver", "river_tree",
    "river_config", "cfr", "cfr_plus", "planned_cfr", "public_cfr",
    "public_diagnostics", "cards", "analysis")) + (
    "scripts/preflop_validation.py", "scripts/benchmark_turn_solver.py",
    "scripts/benchmark_preflop_public_batched.py",
    "scripts/benchmark_preflop_public_diagnostics.py",
    "benchmarks/preflop-public-diagnostics-v1.json")
FIELDS = ("value_sb", "value_bb", "sb_best_response_value",
          "bb_best_response_value", "nash_conv", "exploitability")


def scenario_kwargs(scenario):
    if "complete_future_flop" in scenario:
        flop = tuple(scenario["complete_future_flop"])
        deck = [rank + suit for rank in "23456789TJQKA" for suit in "cdhs"
                if rank + suit not in flop]
        runouts = tuple(flop + future for future in permutations(deck, 2))
        assert len(runouts) == 49 * 48
    else:
        runouts = scenario["runouts"]
    return {"config": scenario["config"], "runouts": runouts}


def measured_solve(scenario, kwargs, iterations, algorithm, diagnostics):
    phases = {}

    def timed(name, function):
        def run(*args, **options):
            started = time.perf_counter()
            try:
                return function(*args, **options)
            finally:
                phases[name] = phases.get(name, 0.0) + time.perf_counter() - started
        return run

    targets = ((solver, "_enumerate_physical_worlds", "enumeration_and_ranking"),
               (solver, "build_preflop_tree", "preflop_tree"),
               (solver, "_merge_preflop_tree", "templates_and_grafting"),
               (solver, "train_public_batched", "training"),
               (solver.cfr, "evaluate", "exact_diagnostics"),
               (solver.cfr, "best_response", "exact_diagnostics"),
               (solver, "evaluate_public_profile", "exact_diagnostics"))
    gc.collect()  # Outside the timed interval, identically for both backends.
    with ExitStack() as stack:
        for module, attribute, phase in targets:
            stack.enter_context(patch.object(module, attribute,
                                            timed(phase, getattr(module, attribute))))
        start = time.perf_counter()
        result = solver.solve_preflop(
            scenario["sb"], scenario["bb"], **kwargs, iterations=iterations,
            algorithm=algorithm, traversal="public-batched", diagnostics=diagnostics)
        encoded = json.dumps(result)
        seconds = time.perf_counter() - start
    phases["other_including_view_and_serialization"] = max(0.0, seconds - sum(phases.values()))
    return result, seconds, phases, len(encoded.encode("utf-8"))


def check(result, scenario, kwargs):
    oracle = replay_policy(result, scenario["sb"], scenario["bb"], **kwargs)
    gaps = compare_result(result, oracle)
    assert oracle["checked_information_sets"] == len(result["strategy"])
    expected = {(row["sb"], row["bb"]): row["probability"]
                for row in oracle["private_pair_probabilities"]}
    actual = {(row["sb_hand"], row["bb_hand"]): row["probability"]
              for row in result["private_pair_probabilities"]}
    assert expected.keys() == actual.keys()
    posterior_gap = max(abs(expected[key] - actual[key]) for key in expected)
    assert posterior_gap <= 1e-12
    for field, source in (("worlds", "known_worlds"),
                          ("compatible_private_pairs", "known_compatible_private_pairs")):
        if source in scenario:
            assert result[field] == scenario[source]
    return oracle, gaps, posterior_gap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
                        default=ROOT / "benchmarks/preflop-public-diagnostics-v1.json")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/results/preflop-public-diagnostics-v1.json")
    args = parser.parse_args()
    spec = json.loads(args.config.read_text(encoding="utf-8"))
    assert spec["repeats"] >= 2
    hashes = {path: file_sha256(ROOT / path) for path in SOURCES}
    revision, dirty = git_revision(None), worktree_dirty()
    records, comparisons = [], []
    for scenario in spec["scenarios"]:
        kwargs = scenario_kwargs(scenario)
        for iterations in scenario["iterations"]:
            peers = {}
            for repeat in range(spec["repeats"]):
                order = ("recursive", "public-batched")
                if repeat % 2:
                    order = order[::-1]
                for diagnostics in order:
                    result, seconds, phases, payload_bytes = measured_solve(
                        scenario, kwargs, iterations, spec["algorithm"], diagnostics)
                    peer = peers.setdefault(diagnostics, {"seconds": [], "phases": []})
                    peer["result"] = result
                    peer["seconds"].append(seconds)
                    peer["phases"].append(phases)
                    peer["payload_bytes"] = payload_bytes
                    print(f'{scenario["id"]} {iterations} {diagnostics} '
                          f'repeat {repeat + 1}: {seconds:.4f}s', flush=True)
            reference = peers["recursive"]["result"]
            candidate = peers["public-batched"]["result"]
            differences = {field: abs(reference[field] - candidate[field]) for field in FIELDS}
            assert max(differences.values()) <= 1e-10, differences
            policy_difference = policy_gap(reference["strategy"], candidate["strategy"])
            for field in ("worlds", "info_sets", "public_states", "decisions",
                          "private_pair_probabilities", "selected_runouts", "reachable_runouts"):
                assert reference[field] == candidate[field], field
            comparisons.append({"scenario": scenario["id"], "iterations": iterations,
                                "scalar_absolute_gaps": differences,
                                "maximum_policy_probability_gap": policy_difference,
                                "recursive_over_vector_time_ratio":
                                statistics.median(peers["recursive"]["seconds"]) /
                                statistics.median(peers["public-batched"]["seconds"])})
            for diagnostics, peer in peers.items():
                result = peer["result"]
                oracle, gaps, posterior_gap = check(result, scenario, kwargs)
                memory = None
                if iterations == spec["memory_iterations"]:
                    gc.collect()
                    tracemalloc.start()
                    try:
                        traced = solver.solve_preflop(
                            scenario["sb"], scenario["bb"], **kwargs,
                            iterations=iterations, algorithm=spec["algorithm"],
                            traversal="public-batched", diagnostics=diagnostics)
                        json.dumps(traced)
                        _, peak = tracemalloc.get_traced_memory()
                    finally:
                        tracemalloc.stop()
                    assert traced["strategy"] == result["strategy"]
                    assert all(abs(traced[field] - result[field]) <= 1e-12 for field in FIELDS)
                    memory = {"iterations": iterations, "peak_traced_python_bytes": peak}
                    traced = None
                records.append({"scenario": scenario["id"], "iterations": iterations,
                                "algorithm": spec["algorithm"], "training": "public-batched",
                                "diagnostics": diagnostics, "seconds": peer["seconds"],
                                "median_seconds": statistics.median(peer["seconds"]),
                                "phase_seconds": peer["phases"],
                                "phase_median_seconds": {
                                    name: statistics.median(phase.get(name, 0.0) for phase in peer["phases"])
                                    for name in set().union(*peer["phases"])},
                                "memory": memory, "json_payload_bytes": peer["payload_bytes"],
                                "worlds": result["worlds"], "info_sets": result["info_sets"],
                                "compatible_private_pairs": result["compatible_private_pairs"],
                                "public_states": result["public_states"], "decisions": result["decisions"],
                                "metrics": {field: result[field] for field in FIELDS},
                                "independent_replay": oracle, "metric_absolute_gaps": gaps,
                                "private_pair_max_probability_gap": posterior_gap})
            print(f'{scenario["id"]} {iterations}: both complete policies independently verified', flush=True)
    assert hashes == {path: file_sha256(ROOT / path) for path in SOURCES}, "Measured source changed"
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "source_revision": revision, "worktree_dirty_at_start": dirty,
              "source_hashes": hashes, "python": platform.python_version(),
              "platform": platform.platform(), "repeats": spec["repeats"],
              "timing_scope": "Rotating-order complete solves plus JSON serialization, with phase wrapper overhead. Independent replay and explicit pre-call garbage collection excluded. Same public-batched DCFR training for both diagnostic choices.",
              "memory_scope": "Separate complete solves plus JSON serialization at ten iterations only, using tracemalloc after pre-call garbage collection. Python allocations, not RSS; no hundred-iteration memory measurement.",
              "scope": "Exact finite-game value and legal information-set BR comparisons for 18 vs 18 private combinations on selected outcomes, and four private pairs with every fixed-flop future deal. Not unrestricted/full-deck preflop or an equilibrium accuracy certificate.",
              "records": records, "comparisons": comparisons}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
