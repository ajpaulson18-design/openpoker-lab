"""Retain a bounded, no-training full-deck prefix representation experiment."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

from pokerlab.full_deck_prefix_mass import FullDeckPrefixMass


ROOT = Path(__file__).resolve().parents[1]
PREFIXES = ((), (7, 19, 31), (7, 19, 31, 42), (7, 19, 31, 42, 50))
SOURCES = ("pokerlab/full_deck_prefix_mass.py",
           "scripts/benchmark_foundation_prefix_mass.py",
           "tests/test_full_deck_prefix_mass.py",
           "tests/test_full_deck_prefix_independent.py")


def _sources():
    return {name: hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name in SOURCES}


def _literal_total(sb, bb, board):
    """Small-support pair-first reference using sequential physical deals."""
    root, surviving = Fraction(0), Fraction(0)
    for own, own_weight in sb.items():
        for other, other_weight in bb.items():
            if set(own).intersection(other):
                continue
            product = Fraction.from_float(own_weight) * Fraction.from_float(other_weight)
            root += product
            if not set(own + other).intersection(board):
                surviving += product
    chance = Fraction(1)
    if board:
        chance *= Fraction(math.factorial(3), 48 * 47 * 46)
    if len(board) >= 4:
        chance /= 45
    if len(board) == 5:
        chance /= 44
    return surviving * chance / root


def measure():
    before = _sources()
    all_hands = list(combinations(range(52), 2))
    cases = []
    for count in (2, 16, 128, 1326):
        # Deterministic support samples; the complete control is uniform so
        # independent deck-symmetry anchors do not scan 1.6 million pairs.
        indices = [index * len(all_hands) // count for index in range(count)]
        sb = {all_hands[index]: (1.0 if count == 1326 else float(1 + i % 3))
              for i, index in enumerate(indices)}
        bb = {all_hands[-1 - index]: (1.0 if count == 1326 else float(1 + i % 4))
              for i, index in enumerate(indices)}
        samples, masses = [], None
        for _ in range(3):
            start = time.perf_counter()
            operator = FullDeckPrefixMass(sb, bb)
            prefixes = [operator.at(board) for board in PREFIXES]
            samples.append(time.perf_counter() - start)
            current = [item.total_mass for item in prefixes]
            if masses is not None and masses != current:
                raise ArithmeticError("Repeated exact queries changed")
            masses = current
        if count == 1326:
            expected = [Fraction(1), Fraction(1, math.comb(52, 3)),
                        Fraction(1, math.comb(52, 3) * 49),
                        Fraction(1, math.comb(52, 3) * 49 * 48)]
            reference = "uniform-complete-range-deck-symmetry"
        else:
            expected = [_literal_total(sb, bb, board) for board in PREFIXES]
            reference = "independent-literal-pairs-sequential-deal"
        if masses != expected:
            raise ArithmeticError("Independent prefix probability mismatch")
        cases.append({"hands_per_player": count, "repetitions_seconds": samples,
                      "median_seconds": statistics.median(samples),
                      "timed_work": "construct exact operator and query four prefixes",
                      "reference_outside_timer": reference,
                      "prefixes": [list(x) for x in PREFIXES],
                      "exact_prefix_masses": [str(x) for x in masses],
                      "independent_exact_match": True})
    after = _sources()
    if before != after:
        raise RuntimeError("Experiment sources changed during measurement")
    pairs = math.comb(52, 2) * math.comb(50, 2)
    outcomes = math.comb(48, 3) * 45 * 44
    # Hypothetical unabstracted two-action check-through decision at each
    # board depth; betting-history branching and all other arrays are excluded.
    own_board_rows = {"preflop": 1326,
                      "flop": 1326 * math.comb(50, 3),
                      "turn": 1326 * math.comb(50, 3) * 47,
                      "river": 1326 * math.comb(50, 3) * 47 * 46}
    return {"schema": "foundation-prefix-mass-v1", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "source_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "source_lf_sha256_before": before, "source_lf_sha256_after": after,
            "source_status": subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines(),
            "python": sys.version, "platform": platform.platform(),
            "cases": cases,
            "structural_counts": {"full_range_hands_per_player": 1326,
                                  "compatible_ordered_private_pairs": pairs,
                                  "ordered_public_outcomes_per_pair": outcomes,
                                  "literal_complete_world_rows": pairs * outcomes,
                                  "one_8_byte_mass_per_world_payload_bytes": 8 * pairs * outcomes,
                                  "own_hand_public_board_rows_per_seat": own_board_rows,
                                  "two_seat_river_two_action_regret_average_payload_bytes":
                                      2 * own_board_rows["river"] * 2 * 2 * 8,
                                  "strategy_payload_assumption":
                                      "one two-action decision per seat per river own-hand/public-board history; double regret plus average only; no betting-history multiplicity"},
            "limits": ["No training, ranking, tree, action values or native invocation",
                       "No baseline speedup, RSS, allocation or full-solver latency claim",
                       "Linear rational-operation/entry count is not bit complexity",
                       "Full-deck law differs from selected-outcome conditional law"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be a fresh file")
    report = measure()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"output": str(args.output), "cases": len(report["cases"]),
                      "all_independent_checks_pass": True}))


if __name__ == "__main__":
    main()
