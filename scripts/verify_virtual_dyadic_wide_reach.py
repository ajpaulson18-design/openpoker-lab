"""Verify every saved row in the full-width 12-river prepared-reach study."""

from argparse import ArgumentParser
import gzip
from hashlib import sha256
from itertools import combinations
import json
from math import comb
from pathlib import Path

from scripts.preflop_validation import independent_rank
from tests.full_deck_public_chance_reference import card_name


def verify(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as stream:
        raw = stream.read(2_100_001)
    if len(raw) > 2_100_000:
        raise ValueError("full-width study capture exceeds its bound")
    lines = raw.decode("ascii").splitlines()
    hands = tuple(combinations(range(52), 2))
    masks = tuple((1 << a) | (1 << b) for a, b in hands)
    weights = (tuple(1 + i % 5 for i in range(len(hands))),
               tuple(1 + (3 * i + 1) % 7 for i in range(len(hands))))
    normalizer = sum(weights[0][i] * weights[1][j] for i, a in enumerate(masks)
                     for j, b in enumerate(masks) if not a & b)
    if len(lines) != 25 or lines[0].split() != [
            "WIDE_REACH_STUDY_V1", "16", "12", "212", format(normalizer, "x")]:
        raise ValueError("full-width study fixture header differs")
    reach_mass = tuple(tuple(weight * ((i + 2 * player) % 9) for i, weight in enumerate(side))
                       for player, side in enumerate(weights))
    divisor = comb(48, 3) * 45 * 44
    for river in range(12):
        board = (17, 24, 33, 35, river)
        mask = sum(1 << card for card in board)
        live = [row for row, hand_mask in enumerate(masks) if not hand_mask & mask]
        ranks = {i: independent_rank(tuple(map(card_name, (*hands[i], *board)))) for i in live}
        for player in range(2):
            fields = lines[1 + 2 * river + player].split()
            if fields[:4] != ["RIVER", str(river), str(player), str(divisor)]:
                raise ValueError("full-width showdown row header differs")
            opposing = reach_mass[1-player]
            actual = [int(value, 16) for value in fields[4:]]
            if len(actual) != len(hands):
                raise ValueError("full-width showdown row count differs")
            rows = [0] * len(hands)
            for i in live:
                rank = ranks[i]
                disjoint = masks[i]
                score = sum(((rank > ranks[j]) - (rank < ranks[j])) * opposing[j]
                            for j in live if not disjoint & masks[j])
                rows[i] = (weights[player][i] * score) << 209
            if actual != rows:
                raise ValueError(f"literal showdown differs at river {river}, seat {player}")
    return {"status": "exact", "rivers": 12, "holdings_per_seat": len(hands),
            "row_values": 24 * len(hands), "native_producer_calls": 0,
            "raw_sha256": sha256(raw).hexdigest()}


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.capture), indent=2, sort_keys=True))
