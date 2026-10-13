"""Exact full-future chance rows for a fixed flop followed by checkdown.

This bounded helper prepares a direct flop-start game, not a preflop solver.
It integrates all unordered turn/river boards into win/tie/loss terminal rows.
"""

from fractions import Fraction
from itertools import combinations

from .cards import DECK, cards, expand_range, rank_hand

MAX_CANDIDATE_PAIRS = 4_096
MAX_COMPATIBLE_PAIRS = 128
MAX_UNORDERED_BOARD_EVALUATIONS = 126_720
UNORDERED_BOARDS_PER_PAIR = 990
ORDERED_OUTCOMES_PER_PAIR = 1_980
_DECK_ORDER = {card: index for index, card in enumerate(DECK)}


class FlopCheckdownPlan:
    """Prepared fixed-flop weighted equity groups with bounded exact ranking."""

    __slots__ = ("board", "hands", "pairs", "budget", "_pair_weights")

    def __init__(self, board, hands, pairs, budget, pair_weights):
        self.board = board
        self.hands = hands
        self.pairs = pairs
        self.budget = budget
        self._pair_weights = pair_weights

    def build(self):
        """Return normalized four-field worlds and per-compatible-pair counts."""
        remaining = tuple(card for card in DECK if card not in self.board)
        worlds, counts = [], []
        for oop_index, ip_index, pair_probability in self._pair_weights:
            oop_hand, ip_hand = self.hands[0][oop_index], self.hands[1][ip_index]
            wins = ties = losses = 0
            private = set(oop_hand + ip_hand)
            available = tuple(card for card in remaining if card not in private)
            if len(available) != 45:
                raise AssertionError("A compatible private pair must leave 45 cards.")
            for turn, river in combinations(available, 2):
                final_board = self.board + (turn, river)
                oop_rank = rank_hand(oop_hand + final_board)
                ip_rank = rank_hand(ip_hand + final_board)
                if oop_rank > ip_rank:
                    wins += 2
                elif oop_rank < ip_rank:
                    losses += 2
                else:
                    ties += 2
            if wins + ties + losses != ORDERED_OUTCOMES_PER_PAIR:
                raise AssertionError("Exact turn/river outcome count changed.")
            counts.append({
                "oop_hand": "".join(oop_hand), "ip_hand": "".join(ip_hand),
                "wins": wins, "ties": ties, "losses": losses,
                "ordered_outcomes": ORDERED_OUTCOMES_PER_PAIR,
                "pair_probability": float(pair_probability),
            })
            for sign, count in ((-1, losses), (0, ties), (1, wins)):
                if not count:
                    continue
                mass = pair_probability * Fraction(count, ORDERED_OUTCOMES_PER_PAIR)
                converted = float(mass)
                if converted == 0.0:
                    raise ValueError("Positive terminal chance mass underflows binary64.")
                worlds.append((oop_index, ip_index, converted, sign))
        return worlds, counts


def prepare_flop_worlds(board, oop_range, ip_range):
    """Prepare exact fixed-flop/checkdown chance groups under hard work caps.

    Range expansion preserves repository hand order and removes hands blocked
    by the flop. Private-card collisions are excluded before pair priors are
    normalized. All weight products and normalization use exact represented
    binary64 fractions; conversion happens only in returned rows.
    """
    flop = tuple(sorted(cards(board, 3), key=_DECK_ORDER.__getitem__))
    oop_expanded = expand_range(oop_range, flop)
    ip_expanded = expand_range(ip_range, flop)
    hands = (list(oop_expanded), list(ip_expanded))
    candidate_pairs = len(hands[0]) * len(hands[1])
    if candidate_pairs > MAX_CANDIDATE_PAIRS:
        raise ValueError("Flop checkdown candidate pair limit exceeded before ranking.")

    compatible, total = [], Fraction(0)
    for oop_index, oop_hand in enumerate(hands[0]):
        oop_cards = set(oop_hand)
        oop_weight = Fraction.from_float(oop_expanded[oop_hand])
        for ip_index, ip_hand in enumerate(hands[1]):
            if not oop_cards.isdisjoint(ip_hand):
                continue
            weight = oop_weight * Fraction.from_float(ip_expanded[ip_hand])
            if weight <= 0:
                continue
            compatible.append((oop_index, ip_index, weight))
            total += weight
            if len(compatible) > MAX_COMPATIBLE_PAIRS:
                raise ValueError("Flop checkdown compatible pair limit exceeded before ranking.")
    if not compatible or total <= 0:
        raise ValueError("Ranges contain no compatible positive-weight private pairs.")

    unordered_evaluations = len(compatible) * UNORDERED_BOARDS_PER_PAIR
    if unordered_evaluations > MAX_UNORDERED_BOARD_EVALUATIONS:
        raise ValueError("Flop checkdown unordered board evaluation limit exceeded before ranking.")

    pair_weights, pairs = [], []
    for oop_index, ip_index, weight in compatible:
        probability = weight / total
        if float(probability) == 0.0:
            raise ValueError("Positive private-pair probability underflows binary64.")
        pair_weights.append((oop_index, ip_index, probability))
        pairs.append((oop_index, ip_index, probability))

    budget = {
        "candidate_pairs": candidate_pairs,
        "compatible_pairs": len(compatible),
        "physical_worlds": len(compatible) * ORDERED_OUTCOMES_PER_PAIR,
        "unordered_boards": unordered_evaluations,
        "rank_calls_upper_bound": 2 * unordered_evaluations,
        "grouped_rows_upper_bound": 3 * len(compatible),
        "candidate_pair_limit": MAX_CANDIDATE_PAIRS,
        "compatible_pair_limit": MAX_COMPATIBLE_PAIRS,
        "unordered_board_evaluation_limit": MAX_UNORDERED_BOARD_EVALUATIONS,
        "scope": "Logical exact ranking work and grouped output rows; not elapsed time, allocated bytes or RSS.",
    }
    return FlopCheckdownPlan(flop, hands, pairs, budget, pair_weights)
