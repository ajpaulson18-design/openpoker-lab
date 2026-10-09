"""Benchmark ranked river terminal values against sparse pair enumeration.

Only evaluator setup and terminal value calls are measured. This does not
measure traversal or full solver speedups. Pair ranks are prepared once for
the sparse reference so it exercises the same rank-sweep setup boundary.
"""
import argparse
import gc
import hashlib
import itertools
import json
import math
import platform
import statistics
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

from pokerlab.cards import DECK, rank_hand
from pokerlab.ranked_river import RankedRiverPayoffs
from pokerlab.river_tree import _Terminal
from scripts.benchmark_turn_solver import git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
BOARD = ("2c", "7d", "9h", "Js", "Kd")
RANGE_SIZES = (64, 128, 256, 512)
REPEATS = 10
POT = 100.0
TERMINALS = (_Terminal("showdown", (0.0, 40.0)),
             _Terminal("fold", (0.0, 40.0), winner=0))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_hands(count, offset, side):
    available = tuple(card for card in DECK if card not in BOARD)
    combos = list(itertools.combinations(available, 2))
    stride = 37 if side == 0 else 53
    start = offset + (0 if side == 0 else 19)
    selected = tuple(tuple(sorted(combos[(start + index * stride) % len(combos)]))
                     for index in range(count))
    # Positive, nonuniform static range weights; reaches below are separate.
    cycle = (1.0, 0.5, 0.75, 0.25, 0.0)
    weights = tuple(cycle[(index + 2 * side) % len(cycle)] or 0.125
                    for index in range(count))
    return selected, weights


def make_reach(count, side):
    cycle = (0.0, 0.125, 0.375, 0.625, 0.875, 1.0)
    return tuple(cycle[(index * 5 + side) % len(cycle)] for index in range(count))


def make_case(count):
    hands = (make_hands(count, count * 11, 0)[0],
             make_hands(count, count * 11, 1)[0])
    weights = (make_hands(count, count * 11, 0)[1],
               make_hands(count, count * 11, 1)[1])
    reaches = (make_reach(count, 0), make_reach(count, 1))
    ranks = tuple(tuple(rank_hand(BOARD + hand) for hand in player_hands)
                  for player_hands in hands)
    normalized_weights = tuple(tuple(w / math.fsum(side) for w in side)
                               for side in weights)
    compatible_mass = math.fsum(
        normalized_weights[0][i] * normalized_weights[1][j]
        for i, hand0 in enumerate(hands[0])
        for j, hand1 in enumerate(hands[1])
        if not (set(hand0) & set(hand1)))
    return {"range_size": count, "board": BOARD, "hands": hands,
            "weights": weights, "normalized_weights": normalized_weights,
            "reaches": reaches, "ranks": ranks,
            "compatible_pair_count": sum(
                1 for hand0 in hands[0] for hand1 in hands[1]
                if not (set(hand0) & set(hand1))),
            "compatible_mass": compatible_mass,
            "input": {"oop": ["".join(hand) + ":" + str(weight)
                              for hand, weight in zip(hands[0], weights[0])],
                      "ip": ["".join(hand) + ":" + str(weight)
                             for hand, weight in zip(hands[1], weights[1])],
                      "reach_oop": reaches[0], "reach_ip": reaches[1]}}


def pair_reference(case, node, opponent_reach, player):
    """Independent joint-mass pair loop with ranks already prepared once."""
    own = player
    opponent = 1 - player
    scale = POT / 2.0 + min(node.contributions)
    if node.kind == "fold":
        payoff_sign = 1.0 if node.winner == player else -1.0
    else:
        payoff_sign = None
    answer = []
    factor = 1.0 / case["compatible_mass"]
    for own_index, own_hand in enumerate(case["hands"][own]):
        terms = []
        for opponent_index, opponent_hand in enumerate(case["hands"][opponent]):
            if set(own_hand) & set(opponent_hand):
                continue
            if node.kind == "fold":
                sign = payoff_sign
            else:
                cmp = ((case["ranks"][own][own_index] > case["ranks"][opponent][opponent_index]) -
                       (case["ranks"][own][own_index] < case["ranks"][opponent][opponent_index]))
                sign = cmp
            terms.append(case["normalized_weights"][opponent][opponent_index] *
                         opponent_reach[opponent_index] * sign)
        answer.append(case["normalized_weights"][own][own_index] * factor *
                      math.fsum(terms) * scale)
    return answer


def ranked_values(case, evaluator):
    values = []
    for terminal in TERMINALS:
        for player in (0, 1):
            values.append(evaluator.values(terminal, case["reaches"][1 - player], player))
    return values


def reference_values(case):
    values = []
    for terminal in TERMINALS:
        for player in (0, 1):
            values.append(pair_reference(case, terminal, case["reaches"][1 - player], player))
    return values


def compare(left, right):
    maximum_abs = 0.0
    maximum_scaled = 0.0
    entries = 0
    for left_vec, right_vec in zip(left, right):
        if len(left_vec) != len(right_vec):
            raise AssertionError("Terminal payoff vectors differ in length.")
        for a, b in zip(left_vec, right_vec):
            error = abs(a - b)
            maximum_abs = max(maximum_abs, error)
            maximum_scaled = max(maximum_scaled, error / max(abs(a), abs(b), 1.0))
            entries += 1
    return {"entries": entries, "max_abs_difference_chips": maximum_abs,
            "max_scale_aware_difference": maximum_scaled,
            "tolerance_abs": 1e-10, "tolerance_scale_aware": 1e-10,
            "passed": maximum_abs <= 1e-10 and maximum_scaled <= 1e-10}


def timed_setup(case):
    gc.collect()
    start = time.perf_counter()
    evaluator = RankedRiverPayoffs(case["board"], case["hands"], case["weights"], pot=POT)
    elapsed = time.perf_counter() - start
    return evaluator, elapsed


def timed_pair_setup(case):
    # Prepare exactly the compatible pair edges and signed masses that the
    # production public-CFR kernel caches before traversing terminals.
    start = time.perf_counter()
    ranks = tuple(tuple(rank_hand(BOARD + hand) for hand in player_hands)
                  for player_hands in case["hands"])
    normalized = tuple(tuple(weight / math.fsum(side) for weight in side)
                       for side in case["weights"])
    compatible_mass = math.fsum(normalized[0][i] * normalized[1][j]
                                for i, hand0 in enumerate(case["hands"][0])
                                for j, hand1 in enumerate(case["hands"][1])
                                if not (set(hand0) & set(hand1)))
    edges = []
    for i, hand0 in enumerate(case["hands"][0]):
        for j, hand1 in enumerate(case["hands"][1]):
            if set(hand0) & set(hand1):
                continue
            sign = ((ranks[0][i] > ranks[1][j]) - (ranks[0][i] < ranks[1][j]))
            mass = normalized[0][i] * normalized[1][j] / compatible_mass
            edges.append((i, j, mass, mass * sign))
    if not ranks or compatible_mass <= 0:
        raise ValueError("Sparse reference setup produced empty or incompatible ranges.")
    return tuple(edges), time.perf_counter() - start


def time_phase(case, evaluator, kind):
    samples = {"ranked": [], "sparse_pair": []}
    for repeat in range(REPEATS):
        order = ("ranked", "sparse_pair") if repeat % 2 == 0 else ("sparse_pair", "ranked")
        for method in order:
            gc.collect()
            start = time.perf_counter()
            if method == "ranked":
                ranked_values(case, evaluator)
            else:
                cached_sparse_values(case, kind)
            samples[method].append(time.perf_counter() - start)
    return {name: {"samples_seconds": values,
                   "median_seconds": statistics.median(values)}
            for name, values in samples.items()}


def cached_sparse_values(case, edges):
    """Values from cached (i,j,mass,signed_mass), as public_cfr does."""
    answers = []
    scale = POT / 2.0 + min(TERMINALS[0].contributions)
    for terminal in TERMINALS:
        for player in (0, 1):
            answer = [0.0] * len(case["hands"][player])
            opponent_reach = case["reaches"][1 - player]
            if terminal.kind == "fold":
                oop_winner_sign = 1.0 if terminal.winner == 0 else -1.0
                payoff_sign = oop_winner_sign if player == 0 else -oop_winner_sign
                for i, j, mass, _signed_mass in edges:
                    own_index, opponent_index = ((i, j) if player == 0 else (j, i))
                    answer[own_index] += mass * opponent_reach[opponent_index] * payoff_sign * scale
            else:
                for i, j, _mass, signed_mass in edges:
                    own_index, opponent_index = ((i, j) if player == 0 else (j, i))
                    signed_for_player = signed_mass if player == 0 else -signed_mass
                    answer[own_index] += signed_for_player * opponent_reach[opponent_index] * scale
            answers.append(answer)
    return answers


def trace_peak(case, evaluator, method, edges):
    gc.collect()
    tracemalloc.start()
    try:
        if method == "ranked":
            ranked_values(case, evaluator)
        else:
            cached_sparse_values(case, edges)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def run(cases):
    rows = []
    for case in cases:
        evaluator, setup_seconds = timed_setup(case)
        edges, sparse_setup_seconds = timed_pair_setup(case)
        expected = reference_values(case)
        actual = ranked_values(case, evaluator)
        correctness = compare(actual, expected)
        if not correctness["passed"]:
            raise AssertionError(f"Ranked terminal values failed: {case['range_size']}: {correctness}")
        sparse_correctness = compare(cached_sparse_values(case, edges), expected)
        if not sparse_correctness["passed"]:
            raise AssertionError(f"Cached sparse terminal values failed: {case['range_size']}: {sparse_correctness}")
        pair_timing = time_phase(case, evaluator, edges)
        ranked_peak = trace_peak(case, evaluator, "ranked", edges)
        pair_peak = trace_peak(case, evaluator, "sparse_pair", edges)
        rows.append({
            "range_size_per_player": case["range_size"],
            "compatible_pair_count": evaluator.compatible_pair_count,
            "cached_sparse_edges": len(edges),
            "compatible_pair_mass": case["compatible_mass"],
            "setup_seconds_ranked_evaluator": setup_seconds,
            "setup_seconds_sparse_reference": sparse_setup_seconds,
            "terminal_value_calls_per_sample": 4,
            "timing_repeats": REPEATS,
            "terminal_value_timing": pair_timing,
            "tracemalloc_peak_bytes": {"ranked": ranked_peak, "sparse_pair": pair_peak},
            "correctness": correctness,
            "cached_sparse_baseline_correctness": sparse_correctness,
            "input": case["input"],
            "scope": "Terminal payoff computation only; sparse baseline caches compatible indexed pairs and signed masses once, matching public_cfr terminal arithmetic. Setup and terminal values are timed separately; no full solver or traversal speed claim.",
        })
        print(f"{case['range_size']}x{case['range_size']} ranked="
              f"{pair_timing['ranked']['median_seconds']:.6g}s sparse="
              f"{pair_timing['sparse_pair']['median_seconds']:.6g}s "
              f"setup={setup_seconds:.6g}s maxdiff="
              f"{correctness['max_abs_difference_chips']:.3g}", flush=True)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/results/ranked-river-v1.json")
    args = parser.parse_args(argv)
    cases = [make_case(size) for size in RANGE_SIZES]
    sources = [Path(__file__).resolve(), ROOT / "scripts/benchmark_turn_solver.py",
               ROOT / "pokerlab/ranked_river.py", ROOT / "pokerlab/cards.py",
               ROOT / "pokerlab/river_tree.py"]
    hashes_before = {str(path.relative_to(ROOT)): sha256(path) for path in sources}
    rows = run(cases)
    hashes_after = {str(path.relative_to(ROOT)): sha256(path) for path in sources}
    if hashes_before != hashes_after:
        raise RuntimeError("Source changed during benchmark; discard this result.")
    encoded_cases = json.dumps([case["input"] for case in cases], sort_keys=True,
                               separators=(",", ":")).encode()
    report = {
        "schema_version": 1, "benchmark_id": "ranked-river-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "metadata": {"revision": git_revision(None), "worktree_dirty": worktree_dirty(),
                     "python": sys.version, "python_version": platform.python_version(),
                     "platform": platform.platform(),
                     "command": "python -m scripts.benchmark_ranked_river",
                     "range_sizes": RANGE_SIZES, "repeats": REPEATS,
                     "source_sha256": hashes_before,
                     "input_sha256": hashlib.sha256(encoded_cases).hexdigest(),
                     "board": BOARD},
        "methodology": {"baseline": "Independent sparse compatible-pair sum using board ranks and range normalization prepared once; no rank_hand call occurs inside timed pair loops.",
                        "timing": "Ten interleaved samples per method, median reported. Four terminal-value vector calls per sample: showdown/fold for both player perspectives. Setup timed separately for RankedRiverPayoffs.",
                        "memory": "Single separate tracemalloc run per method and range size; evaluator setup excluded from values-only peak.",
                        "reach": "Nonuniform reach values in [0,1], including zero entries; static range weights are positive and nonuniform.",
                        "limitations": "Synthetic ranges and one machine; payoff-only comparison does not imply whole-solver speedup. Large cancellation-specific fallback is not benchmarked."},
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(f"Wrote {len(rows)} results to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
