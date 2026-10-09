"""Measure published delay weights without changing the conditioned poker game."""
import argparse
from datetime import datetime, timezone
import gc
from itertools import permutations
import json
from pathlib import Path
import platform
import time
import tracemalloc

from pokerlab.preflop_solver import solve_preflop
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty
from scripts.preflop_validation import compare_result, replay_policy

ROOT = Path(__file__).resolve().parents[1]
SOURCES = tuple("pokerlab/" + name + ".py" for name in (
    "preflop_solver", "preflop_tree", "preflop_vector_budget", "preflop_delayed_cfrplus",
    "postflop_solver", "river_tree", "river_config", "cfr", "cfr_plus", "planned_cfr",
    "public_cfr", "public_diagnostics", "cards", "analysis")) + (
    "scripts/preflop_validation.py", "scripts/benchmark_turn_solver.py",
    "scripts/benchmark_preflop_averaging_delay.py",
    "tests/test_preflop_delayed_cfrplus.py", "tests/test_preflop_averaging_delay.py")


def _independently_verify(candidate, sb, bb, kwargs):
    start = time.perf_counter()
    oracle = replay_policy(candidate, sb, bb, **kwargs)
    gaps = compare_result(candidate, oracle)
    assert oracle["checked_information_sets"] == len(candidate["strategy"])
    pairs = {(row["sb_hand"], row["bb_hand"]): row["probability"]
             for row in candidate["private_pair_probabilities"]}
    expected = {(row["sb"], row["bb"]): row["probability"]
                for row in oracle["private_pair_probabilities"]}
    assert pairs.keys() == expected.keys()
    assert max(abs(pairs[key] - expected[key]) for key in pairs) <= 1e-12
    return {"configured_replay": oracle, "metric_absolute_gaps": gaps,
            "independent_replay_seconds": time.perf_counter() - start}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
                        default=ROOT / "benchmarks/preflop-averaging-delay-v1.json")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/results/preflop-averaging-delay-v1.json")
    args = parser.parse_args()
    spec = json.loads(args.config.read_text(encoding="utf-8"))
    config_hash = file_sha256(args.config)
    hashes = {path: file_sha256(ROOT / path) for path in SOURCES}
    revision, dirty = git_revision(None), worktree_dirty()
    prior_path = ROOT / spec["prior_report"]
    prior_hash = file_sha256(prior_path)
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    matching = [row for row in prior["records"] if row["algorithm"] == "cfrplus"
                and row["iterations"] == spec["full_flop"]["iterations"]]
    assert len(matching) == 1
    prior_baseline = matching[0]
    full = spec["full_flop"]
    assert prior["specification"]["sb"] == full["sb"]
    assert prior["specification"]["bb"] == full["bb"]
    assert prior["specification"]["flop"] == full["flop"]
    assert prior["specification"]["config"] == full["config"]
    flop = tuple(full["flop"])
    deck = [rank + suit for rank in "23456789TJQKA" for suit in "cdhs"
            if rank + suit not in flop]
    runouts = tuple(flop + future for future in permutations(deck, 2))
    assert len(runouts) == 2352
    kwargs = {"config": full["config"], "runouts": runouts}
    records = []
    baseline = None
    for delay in full["delays"]:
        print(f'complete fixed-flop CFR+ {full["iterations"]}, delay {delay}: start', flush=True)
        gc.collect()
        start = time.perf_counter()
        candidate = solve_preflop(
            full["sb"], full["bb"], **kwargs, iterations=full["iterations"],
            algorithm="cfrplus", traversal="public-batched", diagnostics="public-batched",
            resource_model="public-vector", averaging_delay=delay)
        json.dumps(candidate)
        seconds = time.perf_counter() - start
        assert candidate["worlds"] == full["worlds"]
        assert candidate["compatible_private_pairs"] == full["private_pairs"]
        assert candidate["info_sets"] == full["information_sets"]
        assert len(candidate["reachable_runouts"]) == 2336
        assert candidate["training_passes"] == 3 * full["iterations"]
        if delay:
            assert candidate["averaging_delay"] == delay
            assert candidate["averaging_positive_sweeps"] == full["iterations"] - delay
        else:
            assert "averaging_delay" not in candidate
        verification = _independently_verify(candidate, full["sb"], full["bb"], kwargs)
        oracle = verification["configured_replay"]
        lower, upper = -oracle["bb_best_response_value"] - 1e-10, oracle["sb_best_response_value"] + 1e-10
        assert lower <= oracle["value_sb"] <= upper
        if delay == 0:
            baseline = oracle["nash_conv"]
            assert abs(baseline - prior_baseline["configured_replay"]["nash_conv"]) <= 1e-10
        record = {"scenario": "complete-four-private-pair-fixed-flop", "iterations": full["iterations"],
                  "averaging_delay": delay, "positive_average_sweeps": full["iterations"] - delay,
                  "complete_uninstrumented_seconds": seconds,
                  "worlds": candidate["worlds"], "information_sets": candidate["info_sets"],
                  "postflop_action_configs": candidate["postflop_action_configs"],
                  "vector_work_budget": candidate["vector_work_budget"], **verification,
                  "finite_game_value_interval": {"lower": lower, "upper": upper,
                                                  "width": upper - lower, "numerical_padding": 1e-10},
                  "target_nash_conv": full["target_nash_conv"],
                  "target_reached": oracle["nash_conv"] + 1e-10 <= full["target_nash_conv"]}
        records.append(record)
        print(f'delay {delay}: all rows verified; NashConv={oracle["nash_conv"]:.9g}; '
              f'target reached={record["target_reached"]}', flush=True)
    assert baseline is not None
    for record in records:
        record["improved_over_zero_delay"] = record["configured_replay"]["nash_conv"] < baseline
    selected = spec["selected_game"]
    selected_kwargs = {key: selected[key] for key in ("config", "runouts", "flop_config")}
    memory_records = []
    for delay in selected["delays"]:
        gc.collect()
        tracemalloc.start()
        try:
            candidate = solve_preflop(
                selected["sb"], selected["bb"], **selected_kwargs,
                iterations=selected["iterations"], algorithm="cfrplus",
                traversal="public-batched", diagnostics="public-batched",
                resource_model="public-vector", averaging_delay=delay)
            json.dumps(candidate)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        verification = _independently_verify(candidate, selected["sb"], selected["bb"], selected_kwargs)
        memory_records.append({"scenario": "weighted-selected-outcomes",
                               "iterations": selected["iterations"], "averaging_delay": delay,
                               "worlds": candidate["worlds"], "information_sets": candidate["info_sets"],
                               "complete_peak_traced_python_bytes": peak, **verification})
        print(f'selected delay {delay}: full-call traced peak {peak}; independently verified', flush=True)
    assert hashes == {path: file_sha256(ROOT / path) for path in SOURCES}
    assert config_hash == file_sha256(args.config)
    assert prior_hash == file_sha256(prior_path)
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
              "generated_at": datetime.now(timezone.utc).isoformat(), "source_revision": revision,
              "worktree_dirty_at_start": dirty, "source_hashes": hashes,
              "configuration_sha256": config_hash, "specification": spec,
              "python": platform.python_version(), "platform": platform.platform(),
              "method_source": "https://arxiv.org/pdf/1407.5042",
              "method_scope": "Published max(t-delay,0) weights with the repository's established completed-alternating-sweep own-reach averaging; not a verbatim Algorithm 1 reproduction.",
              "prior_baseline": {"path": spec["prior_report"], "sha256": prior_hash,
                                 "source_revision": prior["source_revision"],
                                 "nash_conv": prior_baseline["configured_replay"]["nash_conv"],
                                 "scope": "Historical independently replayed accuracy only; timing/memory not compared."},
              "timing_scope": "One complete uninstrumented solve plus JSON serialization per full-flop delay, including resource preflight. Pre-call garbage collection and independent replay excluded. Single observed calls on a shared host, not medians, equal-time trials, statistical speedup or universal delay superiority.",
              "memory_scope": "Separate complete calls plus JSON serialization under tracemalloc only on the small weighted selected-outcome game at 20 iterations. Python allocation peaks, not RSS; no complete-fixed-flop 120-iteration memory claim.",
              "accuracy_scope": "Independent configured binary64 numeric policy replay, all legal visible-information best responses and physical private-pair probabilities. Target flags report misses without changing the target; finite conditioned game only.",
              "records": records, "memory_records": memory_records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
