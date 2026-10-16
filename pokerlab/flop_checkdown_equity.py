"""Reusable exact private-pair equity counts for fixed-flop checkdown games.

The table stores ordered-outcome win/tie/loss counts alongside the exact priors
for its prepared ranges. Reweighting changes globally conditioned pair masses
while reusing those counts; it does not rank cards or enumerate future boards.
"""
from dataclasses import dataclass
from fractions import Fraction

from .cards import DECK
from .flop_checkdown_worlds import (
    MAX_CANDIDATE_PAIRS,
    MAX_COMPATIBLE_PAIRS,
    MAX_UNORDERED_BOARD_EVALUATIONS,
    ORDERED_OUTCOMES_PER_PAIR,
    UNORDERED_BOARDS_PER_PAIR,
    prepare_flop_worlds,
)

_DECK_ORDER = {card: index for index, card in enumerate(DECK)}
_BUDGET_SCOPE = (
    "Logical exact ranking work and grouped output rows; not elapsed time, "
    "allocated bytes or RSS."
)
_BUDGET_KEYS = (
    "candidate_pairs", "compatible_pairs", "physical_worlds", "unordered_boards",
    "rank_calls_upper_bound", "grouped_rows_upper_bound", "candidate_pair_limit",
    "compatible_pair_limit", "unordered_board_evaluation_limit", "scope",
)


@dataclass(frozen=True, slots=True)
class FlopCheckdownEquities:
    """Deeply immutable exact fixed-flop showdown counts.

    ``pairs`` contains ``(oop_index, ip_index, exact_prior)`` rows. ``counts``
    aligns with it and contains ordered ``(wins, ties, losses)`` integer counts.
    Structural validation cannot authenticate that the counts came from actual
    board enumeration; callers should retain trusted preparation provenance.
    """

    board: tuple
    hands: tuple
    pairs: tuple
    counts: tuple
    _budget_items: tuple

    @property
    def budget(self):
        """Return a fresh flat budget mapping."""
        return dict(self._budget_items)

    def validate(self):
        """Validate immutable structure, pair support, counts, and exact caps."""
        if type(self.board) is not tuple or len(self.board) != 3:
            raise ValueError("Flop equity board must be an immutable three-card tuple.")
        if (any(type(card) is not str or card not in _DECK_ORDER for card in self.board)
                or len(set(self.board)) != 3
                or tuple(sorted(self.board, key=_DECK_ORDER.__getitem__)) != self.board):
            raise ValueError("Flop equity board must contain three canonical distinct cards.")
        if type(self.hands) is not tuple or len(self.hands) != 2:
            raise ValueError("Flop equity hands must be an immutable OOP/IP pair.")
        board_cards = set(self.board)
        for player_hands in self.hands:
            if type(player_hands) is not tuple or not player_hands:
                raise ValueError("Each player must have a nonempty immutable hand tuple.")
            if len(player_hands) > len(DECK) * (len(DECK) - 1) // 2:
                raise ValueError("Flop equity hand count exceeds the physical combo limit.")
            seen = set()
            for hand in player_hands:
                if (type(hand) is not tuple or len(hand) != 2
                        or any(type(card) is not str or card not in _DECK_ORDER for card in hand)
                        or hand[0] == hand[1]
                        or tuple(sorted(hand)) != hand
                        or board_cards.intersection(hand)
                        or hand in seen):
                    raise ValueError("Flop equity hands must be canonical unique board-legal combos.")
                seen.add(hand)
        candidate_pairs = len(self.hands[0]) * len(self.hands[1])
        if candidate_pairs > MAX_CANDIDATE_PAIRS:
            raise ValueError("Flop equity candidate-pair limit exceeded.")
        if type(self.pairs) is not tuple or type(self.counts) is not tuple:
            raise ValueError("Flop equity pairs and counts must be immutable tuples.")
        expected_indices = tuple(
            (oop_index, ip_index)
            for oop_index, oop_hand in enumerate(self.hands[0])
            for ip_index, ip_hand in enumerate(self.hands[1])
            if set(oop_hand).isdisjoint(ip_hand)
        )
        if len(expected_indices) > MAX_COMPATIBLE_PAIRS:
            raise ValueError("Flop equity compatible-pair limit exceeded.")
        if len(self.pairs) != len(expected_indices) or len(self.counts) != len(expected_indices):
            raise ValueError("Flop equity pair/count coverage is incomplete.")
        total_prior = Fraction(0)
        for pair, expected, counts in zip(self.pairs, expected_indices, self.counts):
            if (type(pair) is not tuple or len(pair) != 3
                    or type(pair[0]) is not int or type(pair[1]) is not int
                    or pair[:2] != expected or type(pair[2]) is not Fraction
                    or pair[2] <= 0 or pair[2] > 1):
                raise ValueError("Flop equity pairs must cover every compatible pair in order.")
            if float(pair[2]) == 0.0:
                raise ValueError("Positive private-pair probability underflows binary64.")
            total_prior += pair[2]
            if (type(counts) is not tuple or len(counts) != 3
                    or any(type(count) is not int or count < 0 or count % 2 for count in counts)
                    or sum(counts) != ORDERED_OUTCOMES_PER_PAIR):
                raise ValueError("Each pair requires nonnegative even W/T/L counts totaling 1,980.")
            for count in counts:
                if count and float(pair[2] * Fraction(count, ORDERED_OUTCOMES_PER_PAIR)) == 0.0:
                    raise ValueError("Positive terminal chance mass underflows binary64.")
        if total_prior != 1:
            raise ValueError("Flop equity pair priors must sum exactly to one.")
        unordered_boards = len(expected_indices) * UNORDERED_BOARDS_PER_PAIR
        if unordered_boards > MAX_UNORDERED_BOARD_EVALUATIONS:
            raise ValueError("Flop equity board-evaluation limit exceeded.")
        expected_budget = {
            "candidate_pairs": candidate_pairs,
            "compatible_pairs": len(expected_indices),
            "physical_worlds": len(expected_indices) * ORDERED_OUTCOMES_PER_PAIR,
            "unordered_boards": unordered_boards,
            "rank_calls_upper_bound": 2 * unordered_boards,
            "grouped_rows_upper_bound": 3 * len(expected_indices),
            "candidate_pair_limit": MAX_CANDIDATE_PAIRS,
            "compatible_pair_limit": MAX_COMPATIBLE_PAIRS,
            "unordered_board_evaluation_limit": MAX_UNORDERED_BOARD_EVALUATIONS,
            "scope": _BUDGET_SCOPE,
        }
        if (type(self._budget_items) is not tuple
                or len(self._budget_items) != len(_BUDGET_KEYS)
                or any(type(item) is not tuple or len(item) != 2 for item in self._budget_items)
                or tuple(item[0] for item in self._budget_items) != _BUDGET_KEYS
                or any(type(item[0]) is not str for item in self._budget_items)
                or dict(self._budget_items) != expected_budget
                or any(type(dict(self._budget_items)[key]) is not type(value)
                       for key, value in expected_budget.items())):
            raise ValueError("Flop equity budget metadata does not match immutable data.")
        return None

    def build(self):
        """Return fresh categorical worlds and familiar per-pair count rows."""
        self.validate()
        worlds, rows = [], []
        for (oop_index, ip_index, prior), (wins, ties, losses) in zip(self.pairs, self.counts):
            oop_hand = self.hands[0][oop_index]
            ip_hand = self.hands[1][ip_index]
            rows.append({
                "oop_hand": "".join(oop_hand), "ip_hand": "".join(ip_hand),
                "wins": wins, "ties": ties, "losses": losses,
                "ordered_outcomes": ORDERED_OUTCOMES_PER_PAIR,
                "pair_probability": float(prior),
            })
            for sign, count in ((-1, losses), (0, ties), (1, wins)):
                if not count:
                    continue
                mass = prior * Fraction(count, ORDERED_OUTCOMES_PER_PAIR)
                converted = float(mass)
                if converted == 0.0:
                    raise ValueError("Positive terminal chance mass underflows binary64.")
                worlds.append((oop_index, ip_index, converted, sign))
        return worlds, rows


def prepare_flop_checkdown_equities(board, oop_range, ip_range):
    """Rank each compatible pair's 990 final boards once into an immutable table."""
    plan = prepare_flop_worlds(board, oop_range, ip_range)
    _, rows = plan.build()
    table = FlopCheckdownEquities(
        board=tuple(plan.board),
        hands=tuple(tuple(tuple(hand) for hand in player_hands) for player_hands in plan.hands),
        pairs=tuple((oop_index, ip_index, prior)
                    for oop_index, ip_index, prior in plan.pairs),
        counts=tuple((row["wins"], row["ties"], row["losses"]) for row in rows),
        _budget_items=tuple(plan.budget.items()),
    )
    table.validate()
    return table


def reweight_flop_checkdown_equities(table, oop_range, ip_range):
    """Reuse covered pair counts under new exact blocker-conditioned ranges.

    Range expansion, collision conditioning and all existing preparation caps
    come from the no-ranking plan builder. Every requested compatible physical
    pair must have source counts; missing support is rejected before any output
    categorical worlds or rows are built. The source table is never modified.
    """
    if type(table) is not FlopCheckdownEquities:
        raise TypeError("table must be a FlopCheckdownEquities instance.")
    table.validate()
    plan = prepare_flop_worlds(table.board, oop_range, ip_range)
    source_counts = {
        (table.hands[0][oop_index], table.hands[1][ip_index]): counts
        for (oop_index, ip_index, _), counts in zip(table.pairs, table.counts)
    }
    counts = []
    for oop_index, ip_index, _ in plan.pairs:
        hand_pair = (plan.hands[0][oop_index], plan.hands[1][ip_index])
        pair_counts = source_counts.get(hand_pair)
        if pair_counts is None:
            raise ValueError("Requested compatible private pair is not covered by the source table.")
        counts.append(pair_counts)
    result = FlopCheckdownEquities(
        board=tuple(plan.board),
        hands=tuple(tuple(tuple(hand) for hand in player_hands) for player_hands in plan.hands),
        pairs=tuple((oop_index, ip_index, prior)
                    for oop_index, ip_index, prior in plan.pairs),
        counts=tuple(counts),
        _budget_items=tuple(plan.budget.items()),
    )
    result.validate()
    return result
