"""Rank-free, exact storage geometry for the fixed PROOF9 private ranges.

This is a structural projection of one unchanged card-free betting template.
It performs no hand ranking, policy evaluation, or training. Decks are nested
deterministically; the nine original private cards are present at every size.
"""

from __future__ import annotations

import json
from itertools import combinations
from math import comb

from tests.full_deck_public_chance_reference import PROOF9, proof_ranges
from tests.virtual_betting_template_reference import build_reference_template
from tests.virtual_frozen_update_reference import _template_case


DECK_SIZES = (9, 10, 13, 26, 52)
STREETS = (0, 3, 4, 5)
VALUE_BITS = 642
VALUE_WIRE_BYTES = 88


def nested_deck(size: int) -> tuple[int, ...]:
    if size not in DECK_SIZES:
        raise ValueError("deck size is outside the declared census")
    additions = tuple(card for card in range(52) if card not in PROOF9)
    deck = tuple(sorted((*PROOF9, *additions[:size - len(PROOF9)])))
    if len(deck) != size or any(card not in deck for card in PROOF9):
        raise ArithmeticError("nested deck lost a private fixture card")
    return deck


def prefix_count(remaining: int, street: int) -> int:
    """Canonical flop followed by ordered turn and river after exclusions."""
    if street == 0:
        return 1
    if remaining < 3:
        return 0
    count = comb(remaining, 3)
    if street >= 4:
        count *= max(remaining - 3, 0)
    if street == 5:
        count *= max(remaining - 4, 0)
    return count


def supported_prefixes(deck: tuple[int, ...], actor: int,
                       own: tuple[int, int], street: int,
                       ranges: tuple) -> int:
    """Union of at most two compatible opponent-pair avoidance events."""
    own_cards = frozenset(own)
    opponents = [frozenset(hand) for hand, _weight in ranges[1 - actor]
                 if not own_cards.intersection(hand)]
    if len(opponents) > 2:
        raise ArithmeticError("fixed fixture exceeds two opponent holdings")
    if not opponents:
        return 0
    value = sum(prefix_count(len(deck) - len(own_cards | opponent), street)
                for opponent in opponents)
    if len(opponents) == 2:
        value -= prefix_count(len(deck) - len(own_cards | opponents[0] | opponents[1]), street)
    if value < 0 or value > prefix_count(len(deck), street):
        raise ArithmeticError("invalid inclusion-exclusion support count")
    return value


def brute_nine(ranges: tuple) -> dict[tuple[int, int, int], int]:
    """Independent board enumeration for the smallest deck only."""
    deck = nested_deck(9)
    found = {(street, actor, hand): set()
             for street in STREETS for actor in (0, 1) for hand in range(2)}
    for flop in combinations(deck, 3):
        for turn in (card for card in deck if card not in flop):
            for river in (card for card in deck if card not in (*flop, turn)):
                board = (*flop, turn, river)
                for street in STREETS:
                    visible = frozenset(board[:street])
                    for actor in (0, 1):
                        for index, (own, _weight) in enumerate(ranges[actor]):
                            own_cards = frozenset(own)
                            if own_cards & visible:
                                continue
                            if any(not (own_cards & frozenset(opp)) and
                                   not (frozenset(opp) & visible)
                                   for opp, _ in ranges[1 - actor]):
                                found[street, actor, index].add(board[:street])
    return {key: len(value) for key, value in found.items()}


def census() -> dict:
    ranges = proof_ranges()
    template = build_reference_template(_template_case())
    receipt = template.receipt
    if (receipt["nodes"], receipt["edges"], receipt["logical_occurrences"]) != (388, 410, 1105):
        raise ArithmeticError("card-free template geometry changed")
    compatible = sum(frozenset(a).isdisjoint(b)
                     for a, _ in ranges[0] for b, _ in ranges[1])
    if compatible != 3:
        raise ArithmeticError("private-pair fixture changed")
    brute = brute_nine(ranges)
    results = []
    for size in DECK_SIZES:
        deck = nested_deck(size)
        support = {(street, actor, hand): supported_prefixes(deck, actor, ranges[actor][hand][0], street, ranges)
                   for street in STREETS for actor in (0, 1) for hand in range(2)}
        if size == 9 and support != brute:
            raise ArithmeticError("nine-card brute-force support disagrees with inclusion-exclusion")
        rows = slots = 0
        by_street = {}
        for street in STREETS:
            street_rows = street_slots = 0
            for node_id, node in enumerate(template.nodes):
                if node.phase != "decision" or node.street != street:
                    continue
                actor = node.state.player
                paths = template.histories[node_id][0]
                count = sum(support[street, actor, hand] for hand in range(2))
                street_rows += paths * count
                street_slots += paths * count * len(node.edges)
            rows += street_rows
            slots += street_slots
            by_street[str(street)] = {"rows": street_rows, "slots": street_slots,
                                      "supported_prefixes_by_hand": [
                                          [support[street, actor, hand] for hand in range(2)]
                                          for actor in (0, 1)]}
        # Exact packed payload of one current-protocol checkpoint: a 24-byte
        # row identity and one fallback byte per row, plus one 8-byte grid unit
        # and two 88-byte raw integer fields per slot. It excludes action text,
        # history, framing, second checkpoint and transient buffers. This is a
        # lower bound for that fixed-width representation, not arbitrary coding.
        checkpoint_bytes = 25 * rows + (8 + 2 * VALUE_WIRE_BYTES) * slots
        # Current native State's explicit modeled reservation, including four
        # integer arrays, one exported raw copy, metadata and scratch allowance.
        state_reservation_bits = ((5 * slots + 256) * (VALUE_BITS + 58)
                                  + 640 * slots + 16 * rows)
        results.append({
            "deck_size": size,
            "deck_ids": list(deck),
            "literal_joint_worlds": compatible * prefix_count(size - 4, 5),
            "unfiltered_prefixes": {str(street): prefix_count(size, street)
                                    for street in STREETS},
            "supported_rows": rows,
            "supported_action_slots": slots,
            "by_street": by_street,
            "one_checkpoint_packed_payload_lower_bound_bytes": checkpoint_bytes,
            "current_state_modeled_reservation_entries": 1024 + 16 * rows + 10 * slots,
            "current_state_modeled_reservation_bits": state_reservation_bits,
        })
    if (results[0]["supported_rows"], results[0]["supported_action_slots"]) != (24420, 58164):
        raise ArithmeticError("accepted nine-card row/slot calibration changed")
    return {
        "scope": "rank-free structural measurement; no expanded-deck training or quality claim",
        "deck_rule": "PROOF9 plus the lowest unused physical card IDs, sorted",
        "private_fixture": {"holdings": [[list(hand) for hand, _ in side] for side in ranges],
                            "compatible_pairs": compatible},
        "symbolic_template": {"states": receipt["nodes"], "edges": receipt["edges"],
                              "literal_occurrences": receipt["logical_occurrences"],
                              "max_depth": receipt["max_depth"]},
        "nine_card_brute_force_check": "all four streets and four own holdings equal inclusion-exclusion",
        "results": results,
    }


if __name__ == "__main__":
    print(json.dumps(census(), sort_keys=True, separators=(",", ":")))
