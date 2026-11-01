"""Literal physical-pair reference for native public-chance controls only.

This deliberately quadratic test oracle shares no candidate mass/bucket/rank
arithmetic. It is not a production representation or a solver.
"""
from fractions import Fraction
from itertools import combinations, permutations
from math import comb

from scripts.preflop_validation import independent_rank


FULL52 = tuple(range(52))
# Letters a..i map to actual physical IDs; deck iteration remains canonical.
# The three compatible pairs independently yield tie/loss/win for SB.
PROOF_LABELS = (43, 48, 32, 24, 37, 16, 33, 35, 17)
PROOF9 = tuple(sorted(PROOF_LABELS))


def card_name(card):
    return "23456789TJQKA"[card // 4] + "cdhs"[card % 4]


def exact(value):
    return Fraction.from_float(float(value))


def chance_divisor(deck_size, prefix_length):
    if prefix_length == 0:
        return 1
    count = comb(deck_size - 4, 3)
    if prefix_length >= 4:
        count *= deck_size - 7
    if prefix_length == 5:
        count *= deck_size - 8
    return count


def proof_ranges():
    a, b, c, d, e, f, *_ = PROOF_LABELS
    return (((tuple(sorted((a, b))), 0.25), (tuple(sorted((a, c))), 1.5)),
            ((tuple(sorted((d, e))), 0.75), (tuple(sorted((c, f))), 2.0)))


class LiteralChance:
    def __init__(self, ranges, deck=FULL52):
        self.deck = tuple(deck)
        self.ranges = tuple(tuple((tuple(hand), exact(weight)) for hand, weight in side)
                            for side in ranges)
        self.normalizer = sum((w0 * w1 for h0, w0 in self.ranges[0]
                               for h1, w1 in self.ranges[1]
                               if not set(h0).intersection(h1)), Fraction(0))
        if self.normalizer <= 0:
            raise ValueError("reference requires compatible positive mass")

    def prefix(self, board):
        board = tuple(board)
        denominator = self.normalizer * chance_divisor(len(self.deck), len(board))
        masses = []
        for player in (0, 1):
            side = []
            for own, own_weight in self.ranges[player]:
                total = Fraction(0)
                if not set(own).intersection(board):
                    for opp, opp_weight in self.ranges[1-player]:
                        if not (set(opp).intersection(board) or set(opp).intersection(own)):
                            total += own_weight * opp_weight
                side.append(total / denominator)
            masses.append(side)
        if sum(masses[0]) != sum(masses[1]):
            raise ArithmeticError("literal seat marginal disagreement")
        return {"hand_masses": masses, "total_mass": sum(masses[0]),
                "physical_support": [[value > 0 for value in side] for side in masses]}

    def terminal(self, player, board, kind, payoff, opponent_reach, proposal):
        if kind not in ("FOLD", "SHOWDOWN"):
            raise ValueError("unknown literal terminal kind")
        board = tuple(board)
        denominator = (self.normalizer * chance_divisor(len(self.deck), 5) * proposal)
        answer = []
        for own, own_weight in self.ranges[player]:
            value = Fraction(0)
            if not set(own).intersection(board):
                for (opp, opp_weight), reach in zip(self.ranges[1-player], opponent_reach):
                    if set(opp).intersection(board) or set(opp).intersection(own):
                        continue
                    sign = 1
                    if kind == "SHOWDOWN":
                        own_rank = independent_rank(tuple(card_name(card) for card in (*own, *board)))
                        opp_rank = independent_rank(tuple(card_name(card) for card in (*opp, *board)))
                        sign = (own_rank > opp_rank) - (own_rank < opp_rank)
                    value += own_weight * opp_weight * exact(reach) * exact(payoff) * sign
            answer.append(value / denominator)
        return answer


def all_public_boards(deck):
    """Bounded finite-reference enumeration; never used by candidate native code."""
    for flop in combinations(deck, 3):
        remaining = [card for card in deck if card not in flop]
        for turn, river in permutations(remaining, 2):
            yield (*flop, turn, river)


def target_boards(ranges, deck):
    """Union of complete physical boards for the declared small reference."""
    accepted = set()
    for h0, _ in ranges[0]:
        for h1, _ in ranges[1]:
            if set(h0).intersection(h1):
                continue
            remaining = tuple(card for card in deck if card not in (*h0, *h1))
            accepted.update(all_public_boards(remaining))
    return accepted
