"""Verify bounded deeper full-fixed-flop training and report unmet accuracy targets."""
import argparse
from datetime import datetime, timezone
import gc
from itertools import permutations
import json
from pathlib import Path
import platform
import time
import tracemalloc
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty
from scripts.preflop_validation import compare_result, replay_policy

ROOT = Path(__file__).resolve().parents[1]
SOURCES = tuple("pokerlab/" + name + ".py" for name in (
    "preflop_solver", "preflop_tree", "preflop_vector_budget", "postflop_solver",
    "river_tree", "river_config", "cfr", "cfr_plus", "planned_cfr",
    "public_cfr", "public_diagnostics", "cards", "analysis")) + (
    "scripts/preflop_validation.py", "scripts/benchmark_turn_solver.py",
    "scripts/benchmark_preflop_vector_resources.py",
    "tests/test_preflop_vector_budget.py", "tests/test_preflop_vector_resources.py")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
                        default=ROOT / "benchmarks/preflop-vector-resources-v1.json")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/results/preflop-vector-resources-v1.json")
    args = parser.parse_args()
    spec = json.loads(args.config.read_text(encoding="utf-8"))
    config_hash = file_sha256(args.config)
    hashes = {path: file_sha256(ROOT / path) for path in SOURCES}
    revision, dirty = git_revision(None), worktree_dirty()
    flop = tuple(spec["flop"])
    public_deck = [rank + suit for rank in "23456789TJQKA" for suit in "cdhs"
                   if rank + suit not in flop]
    runouts = tuple(flop + future for future in permutations(public_deck, 2))
    assert len(runouts) == 49 * 48
    kwargs = {"config": spec["config"], "runouts": runouts}
    historical = spec["historical_baseline"]
    historical_path = ROOT / historical["report"]
    historical_hash = file_sha256(historical_path)
    prior = json.loads(historical_path.read_text(encoding="utf-8"))
    matching = [row for row in prior["records"] if
                row["scenario"] == historical["scenario"] and
                row["iterations"] == historical["iterations"] and
                row["algorithm"] == historical["algorithm"] and
                row["diagnostics"] == historical["diagnostics"]]
    assert len(matching) == 1
    baseline = matching[0]
    assert baseline["worlds"] == spec["worlds"]
    assert baseline["compatible_private_pairs"] == spec["private_pairs"]
    # Earlier evidence stays frozen. It is not a remeasurement on this source.
    baseline_reference = {"path": historical["report"], "sha256": historical_hash,
                          "source_revision": prior["source_revision"],
                          "iterations": baseline["iterations"], "algorithm": baseline["algorithm"],
                          "nash_conv": baseline["metrics"]["nash_conv"],
                          "scope": "Previously independently verified finite-game baseline; not new timing or memory evidence."}
    records = []
    original_estimator = solver.estimate_vector_budget
    for checkpoint in spec["checkpoints"]:
        algorithm, iterations = checkpoint["algorithm"], checkpoint["iterations"]
        legacy_rejection = None
        if checkpoint["legacy_rejection_required"]:
            with patch.object(solver, "train_public_batched") as trainer:
                try:
                    solver.solve_preflop(
                        spec["sb"], spec["bb"], **kwargs, iterations=iterations,
                        algorithm=algorithm, traversal="public-batched",
                        diagnostics="public-batched")
                except ValueError as error:
                    assert "30 million world-decision iterations" in str(error), error
                    legacy_rejection = str(error)
                else:
                    raise AssertionError("Expected legacy traversal guard did not reject")
                trainer.assert_not_called()
        preflight = {}

        def instrumented_estimator(*values, **options):
            start = time.perf_counter()
            tracemalloc.start()
            try:
                result = original_estimator(*values, **options)
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            preflight.update({"seconds_with_tracing": time.perf_counter() - start,
                              "peak_traced_python_bytes": peak})
            return result

        gc.collect()
        print(f'{algorithm} {iterations}: start complete solve; '
              'tracing resource preflight only', flush=True)
        with patch.object(solver, "estimate_vector_budget", instrumented_estimator):
            start = time.perf_counter()
            candidate = solver.solve_preflop(
                spec["sb"], spec["bb"], **kwargs, iterations=iterations,
                algorithm=algorithm, traversal="public-batched",
                diagnostics="public-batched", resource_model="public-vector")
            json.dumps(candidate)
            complete_seconds = time.perf_counter() - start
        assert candidate["worlds"] == spec["worlds"]
        assert candidate["compatible_private_pairs"] == spec["private_pairs"]
        assert len(candidate["reachable_runouts"]) == 2336
        assert candidate["info_sets"] == 17620
        assert candidate["public_states"] == 30920
        assert candidate["decisions"] == 9546
        estimate = candidate["vector_work_budget"]
        assert estimate["total_loop_entries_upper_bound"] <= estimate["total_loop_entry_limit"]
        assert estimate["information_sets"] == candidate["info_sets"]
        assert estimate["decision_nodes"] == candidate["decisions"]
        assert sum(estimate[key] for key in ("decision_nodes", "chance_nodes", "terminal_nodes")) == candidate["public_states"]
        assert abs(sum(row["probability"] for row in candidate["private_pair_probabilities"]) - 1.0) <= 1e-12
        assert all(abs(row["probability"] - .25) <= 1e-12
                   for row in candidate["private_pair_probabilities"])
        oracle_start = time.perf_counter()
        oracle = replay_policy(candidate, spec["sb"], spec["bb"], **kwargs)
        gaps = compare_result(candidate, oracle)
        assert oracle["checked_information_sets"] == len(candidate["strategy"])
        assert oracle["worlds"] == spec["worlds"]
        pairs = {(row["sb_hand"], row["bb_hand"]): row["probability"]
                 for row in candidate["private_pair_probabilities"]}
        expected = {(row["sb"], row["bb"]): row["probability"]
                    for row in oracle["private_pair_probabilities"]}
        assert pairs.keys() == expected.keys()
        assert max(abs(pairs[key] - expected[key]) for key in pairs) <= 1e-12
        # Independently computed legal BRs bracket the zero-sum minimax value.
        # Numerical padding is explicit, not a formal rational-arithmetic proof.
        lower = -oracle["bb_best_response_value"] - 1e-10
        upper = oracle["sb_best_response_value"] + 1e-10
        assert lower <= oracle["value_sb"] <= upper
        target_reached = oracle["nash_conv"] + 1e-10 <= spec["target_nash_conv"]
        record = {"algorithm": algorithm, "iterations": iterations,
                  "resource_model": candidate["resource_model"],
                  "complete_seconds_including_preflight_tracing": complete_seconds,
                  "preflight_memory": preflight,
                  "independent_replay_seconds": time.perf_counter() - oracle_start,
                  "legacy_rejection": legacy_rejection,
                  "reference_world_decision_work": candidate["world_decision_work"],
                  "worlds": candidate["worlds"], "public_states": candidate["public_states"],
                  "decisions": candidate["decisions"], "information_sets": candidate["info_sets"],
                  "postflop_action_configs": candidate["postflop_action_configs"],
                  "vector_work_budget": estimate, "configured_replay": oracle,
                  "metric_absolute_gaps": gaps,
                  "finite_game_value_interval": {"lower": lower, "upper": upper,
                                                   "width": upper - lower, "numerical_padding": 1e-10},
                  "target_nash_conv": spec["target_nash_conv"], "target_reached": target_reached}
        records.append(record)
        print(f'{algorithm} {iterations}: all rows independently verified; '
              f'gap={oracle["nash_conv"]:.8g}; target reached={target_reached}', flush=True)
    assert hashes == {path: file_sha256(ROOT / path) for path in SOURCES}
    assert config_hash == file_sha256(args.config)
    assert historical_hash == file_sha256(historical_path)
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "source_revision": revision, "worktree_dirty_at_start": dirty,
              "source_hashes": hashes, "specification": spec,
              "configuration_sha256": config_hash,
              "python": platform.python_version(), "platform": platform.platform(),
              "historical_baseline": baseline_reference,
              "timing_scope": "One complete call per checkpoint including JSON serialization and preflight-only allocation tracing; not uninstrumented medians or a controlled backend speed comparison. Independent replay and pre-call garbage collection excluded.",
              "memory_scope": "Resource-estimator-only tracemalloc peak; excludes already-built worlds/tree/infos, subsequent training/diagnostics/serialization and RSS. No full-call or high-iteration memory measurement is claimed.",
              "accuracy_scope": "Independent configured numeric replay, all visible-information legal best responses, and padded zero-sum value bounds in this finite conditioned full-fixed-flop game. Accuracy target is reported even when unmet; no full-deck preflop or unrestricted equilibrium claim.",
              "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
