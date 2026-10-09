"""Complete fixed-flop future deck, with a constructive known-value anchor."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
from itertools import combinations
import json
from pathlib import Path
import platform
import statistics
import time
import tracemalloc

from pokerlab.cards import cards
from pokerlab.preflop_solver import solve_preflop
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty
from scripts.preflop_validation import compare_result, physical_worlds, replay_policy

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("pokerlab/preflop_solver.py", "pokerlab/preflop_tree.py",
           "pokerlab/postflop_solver.py", "pokerlab/river_tree.py", "pokerlab/river_config.py",
           "pokerlab/cfr.py", "pokerlab/planned_cfr.py", "pokerlab/cards.py",
           "scripts/preflop_validation.py", "scripts/benchmark_preflop_full_flop.py",
           "scripts/benchmark_turn_solver.py", "benchmarks/preflop-full-flop-v1.json")


def full_future_runouts(fixture):
    """Enumerate each unordered future pair twice, independent of production."""
    flop = cards(fixture["flop"], 3)
    blocked = set(flop + cards(fixture["sb"], 2) + cards(fixture["bb"], 2))
    available = [rank + suit for rank in "23456789TJQKA" for suit in "cdhs"
                 if rank + suit not in blocked]
    assert len(available) == 45
    outcomes = [flop + ordered for a, b in combinations(available, 2)
                for ordered in ((a, b), (b, a))]
    assert len(outcomes) == len(set(outcomes)) == 1980
    return outcomes


def known_equilibrium_profile(result):
    """Explicit AA/KK fixture policy: SB completes then shoves/calls the flop.

    BB checks whenever possible and folds to a wager. Later SB actions are
    unreachable against every BB deviation; set check/fold to complete rows.
    Independent replay verifies every action/row and both legal responses.
    """
    profile = deepcopy(result)
    for row in profile["strategy"]:
        names = [action["name"] for action in row["actions"]]
        if row["player"] == "sb" and row["street"] == "preflop":
            selected = "call"
        elif row["player"] == "sb" and row["street"] == "flop":
            selected = "all_in" if "all_in" in names else "call"
        else:
            selected = "check" if "check" in names else "fold"
        assert selected in names
        for action in row["actions"]:
            action["probability"] = float(action["name"] == selected)
    return profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "benchmarks/preflop-full-flop-v1.json")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/results/preflop-full-flop-v1.json")
    args = parser.parse_args()
    fixture = json.loads(args.config.read_text(encoding="utf-8"))
    outcomes = full_future_runouts(fixture)
    worlds = physical_worlds(fixture["sb"], fixture["bb"], outcomes)
    assert len(worlds) == 1980
    assert all(abs(world[2] - 1 / 1980) < 1e-15 for world in worlds)
    signs = {sign: sum(world[3] == sign for world in worlds) for sign in (-1, 0, 1)}
    signed_mean = Fraction(signs[1] - signs[-1], 1980)
    assert 2 * signed_mean >= 1, "SB flop shove/call must guarantee the known value"
    kwargs = dict(config=fixture["config"], runouts=outcomes)
    records = []
    last = None
    for iterations in fixture["iterations"]:
        samples = []
        for _ in range(fixture["repeats"]):
            started = time.perf_counter()
            last = solve_preflop(fixture["sb"], fixture["bb"], iterations=iterations,
                                 algorithm=fixture["algorithm"], traversal=fixture["traversal"], **kwargs)
            samples.append(time.perf_counter() - started)
        oracle = replay_policy(last, fixture["sb"], fixture["bb"], **kwargs)
        gaps = compare_result(last, oracle)
        assert len(last["private_pair_probabilities"]) == 1
        assert abs(last["private_pair_probabilities"][0]["probability"] - 1) < 1e-12
        records.append({"iterations": iterations, "seconds": samples,
                        "median_seconds": statistics.median(samples),
                        "value_sb": last["value_sb"], "nash_conv": last["nash_conv"],
                        "known_value_error": abs(last["value_sb"] - fixture["known_value_sb"]),
                        "worlds": last["worlds"], "decisions": last["decisions"],
                        "public_states": last["public_states"], "information_sets": last["info_sets"],
                        "independent_replay": oracle, "metric_absolute_gaps": gaps})
        print(f'{iterations} iterations: NashConv={last["nash_conv"]:.8g}, {statistics.median(samples):.3f}s', flush=True)
    assert records[-1]["nash_conv"] < records[0]["nash_conv"]
    assert records[-1]["nash_conv"] <= fixture["final_nash_conv_ceiling"]
    assert records[-1]["known_value_error"] <= fixture["final_nash_conv_ceiling"]
    anchor = replay_policy(known_equilibrium_profile(last), fixture["sb"], fixture["bb"], **kwargs)
    assert abs(anchor["value_sb"] - 1) < 1e-10
    assert abs(anchor["sb_best_response_value"] - 1) < 1e-10
    assert abs(anchor["bb_best_response_value"] + 1) < 1e-10
    assert anchor["nash_conv"] < 1e-10
    print("Constructive pure equilibrium anchor: SB=1, BB=-1, zero legal deviation gap.", flush=True)
    tracemalloc.start()
    try:
        measured = solve_preflop(fixture["sb"], fixture["bb"],
                                 iterations=fixture["memory_iterations"],
                                 algorithm=fixture["algorithm"], traversal=fixture["traversal"], **kwargs)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert measured["worlds"] == 1980
    report = {"schema_version": 1, "benchmark_id": fixture["benchmark_id"],
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "source_revision": git_revision(None), "worktree_dirty": worktree_dirty(),
              "source_hashes": {path: file_sha256(ROOT / path) for path in SOURCES},
              "fixture": fixture, "python": platform.python_version(), "platform": platform.platform(),
              "scope": "Every legal ordered future pair for one fixed flop and one private pair, inside a conditioned preflop game. Not full-deck preflop, full ranges or unrestricted NLHE.",
              "timing_scope": "Three complete calls per checkpoint: construction, training, exact values/BRs and returned policy serialization. Oracle excluded.",
              "memory_scope": "One separate complete call at explicitly recorded memory_iterations under tracemalloc; Python allocations, not RSS. No memory-scaling inference across iterations.",
              "memory_iterations": fixture["memory_iterations"], "peak_traced_python_bytes": peak,
              "physical_outcomes": 1980, "showdown_counts": {str(key): value for key, value in signs.items()},
              "signed_showdown_mean_fraction": str(signed_mean), "all_in_call_mean_fraction": str(2 * signed_mean),
              "known_value_proof": "SB completes and shoves after a flop check or calls a flop shove: BB fold pays +1, a called shove pays 2*mean_sign >=1. BB checks/folds throughout, never adds chips, capping SB at +1. These strategies establish value +1/-1.",
              "constructive_equilibrium_replay": anchor, "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
