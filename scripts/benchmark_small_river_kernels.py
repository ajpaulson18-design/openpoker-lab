"""Compare cached direct-pair and rank-sweep river terminal operators.

This measures payoff-vector phases only: both candidates share one prepared
RankedRiverPayoffs instance and its cached ranks. It does not train CFR or
claim that the quadratic candidate is suitable for large ranges.
"""
import hashlib
import json
import math
import platform
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from pokerlab.cards import DECK
from pokerlab.ranked_river import RankedRiverPayoffs
from pokerlab.river_tree import _Terminal

ROOT = Path(__file__).resolve().parents[1]
BOARD = ("2c", "3d", "4h", "5s", "9c")
COUNTS = (8, 16, 32, 64)
REPEATS = 20
POT = 100.0
CONTRIBUTIONS = (37.0, 53.0)


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case(count):
    rng = random.Random(8617 + count)
    available = [card for card in DECK if card not in BOARD]
    combos = [tuple(sorted((available[i], available[j])))
              for i in range(len(available)) for j in range(i + 1, len(available))]
    hands = (tuple(rng.sample(combos, count)), tuple(rng.sample(combos, count)))
    weights = tuple(tuple((1.0, .5, .75, .25, .125)[(i + player * 2) % 5]
                          for i in range(count)) for player in (0, 1))
    return hands, weights


def direct_values(kernel, node, opponent_reach, player):
    """Reference pair loop using prepared ranks and no compatible-pair list."""
    opponent = 1 - player
    reach = kernel._reach(opponent_reach, len(kernel.hands[opponent]))
    weighted_reach = [kernel.weights[opponent][j] * reach[j]
                      for j in range(len(reach))]
    scale = kernel.pot / 2.0 + min(node.contributions)
    result = []
    for own_index, own_cards in enumerate(kernel.card_ids[player]):
        terms = []
        for opponent_index, other_cards in enumerate(kernel.card_ids[opponent]):
            if own_cards[0] == other_cards[0] or own_cards[0] == other_cards[1] or \
                    own_cards[1] == other_cards[0] or own_cards[1] == other_cards[1]:
                continue
            if node.kind == "fold":
                sign = 1.0 if node.winner == player else -1.0
            else:
                own_rank = kernel._rank_by_index[player][own_index]
                other_rank = kernel._rank_by_index[opponent][opponent_index]
                sign = (own_rank > other_rank) - (own_rank < other_rank)
            terms.append(kernel.weights[player][own_index] * kernel.factor *
                         weighted_reach[opponent_index] * sign * scale)
        result.append(math.fsum(terms))
    return result


def run_case(count):
    hands, weights = _case(count)
    setup_started = time.perf_counter()
    kernel = RankedRiverPayoffs(BOARD, hands, weights, pot=POT)
    setup_seconds = time.perf_counter() - setup_started
    terminals = (_Terminal("fold", CONTRIBUTIONS, winner=0),
                 _Terminal("showdown", CONTRIBUTIONS))
    samples = {"rank_sweep": [], "direct_pair": []}
    max_error = 0.0
    for repeat in range(REPEATS):
        rng = random.Random(99173 + count * 101 + repeat)
        reaches = (
            [rng.random() * (1 + index % 3) for index in range(count)],
            [rng.random() * (1 + index % 4) for index in range(count)],
        )
        jobs = (("rank_sweep", kernel.values), ("direct_pair", direct_values))
        if repeat % 2:
            jobs = tuple(reversed(jobs))
        outputs_by_method = {}
        for method, operator in jobs:
            started = time.perf_counter()
            outputs = []
            for player in (0, 1):
                for terminal in terminals:
                    outputs.append(operator(kernel, terminal, reaches[1 - player], player)
                                   if method == "direct_pair" else
                                   operator(terminal, reaches[1 - player], player))
            samples[method].append(time.perf_counter() - started)
            outputs_by_method[method] = outputs
        for left, right in zip(outputs_by_method["rank_sweep"],
                               outputs_by_method["direct_pair"]):
            max_error = max(max_error,
                            max((abs(a - b) for a, b in zip(left, right)), default=0.0))
    rank_median = statistics.median(samples["rank_sweep"])
    direct_median = statistics.median(samples["direct_pair"])
    return {
        "holdings_per_player": count,
        "compatible_pair_count": kernel.compatible_pair_count,
        "setup_seconds_excluded_from_operator_timing": setup_seconds,
        "repeats": REPEATS,
        "operator_calls_per_repeat": 4,
        "runtime_seconds": samples,
        "median_seconds": {key: statistics.median(value)
                           for key, value in samples.items()},
        "direct_over_rank_speedup": rank_median / direct_median,
        "max_abs_payoff_vector_error": max_error,
    }


def main():
    source_paths = (Path(__file__).resolve(), ROOT / "pokerlab/ranked_river.py",
                    ROOT / "pokerlab/cards.py")
    before = {str(path.relative_to(ROOT)): _hash(path) for path in source_paths}
    results = [run_case(count) for count in COUNTS]
    after = {str(path.relative_to(ROOT)): _hash(path) for path in source_paths}
    if before != after:
        raise RuntimeError("Calculation source changed during measurement; discard run.")
    direct_wins = [row["holdings_per_player"] for row in results
                   if row["direct_over_rank_speedup"] > 1]
    report = {
        "schema_version": 1,
        "benchmark_id": "small-river-kernels-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": {"python": platform.python_version(),
                       "platform": platform.platform(),
                       "source_sha256": before},
        "methodology": {
            "timing": "Interleaved cached operator calls with distinct deterministic nonuniform reaches; 20 repeats per size.",
            "setup": "One RankedRiverPayoffs instance and its rank/card caches are built before timed repetitions and shared by both operators.",
            "direct_candidate": "Nested compatible-pair scan with math.fsum per own holding; no pair-list allocation; reuses cached ranks.",
            "operators": "For each repeat, both players' fold and showdown value vectors (4 calls) are timed together.",
            "threshold_observation": (f"Direct wins at measured sizes {direct_wins}; any dispatch threshold must be chosen from this crossover on the target runtime."),
            "limits": "Synthetic fixed-board ranges only; no training, no earlier streets, and no claim for large ranges.",
        },
        "board": list(BOARD), "pot": POT, "contributions": list(CONTRIBUTIONS),
        "results": results,
    }
    output = ROOT / "benchmarks/results/small-river-kernels-v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
