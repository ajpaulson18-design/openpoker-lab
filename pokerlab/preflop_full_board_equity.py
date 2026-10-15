"""Bounded exact full-board equity preparation for heads-up preflop games.

Counts showdown outcomes over all five-card boards per compatible private
pair. Only win/tie/loss summaries are retained for reuse across checkpoints.
This module prepares chance data; it does not define a betting model.
"""
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
import math

from .cards import DECK, expand_range, rank_hand


BOARDS_PER_PAIR = math.comb(48, 5)
MAX_CANDIDATE_PAIRS = 4_096
MAX_COMPATIBLE_PAIRS = 4
MAX_BOARD_EVALUATIONS = 6_849_216
MAX_RANK_CALLS = 13_698_432
MAX_CATEGORICAL_ROWS = 12
MAX_HANDS_PER_PLAYER = 1_326
_PROGRESS_EVERY = 100_000
_SIGNS = (-1, 0, 1)


def _fractional_weight(value):
    """Interpret the represented binary64 range weight exactly."""
    numerator, denominator = float(value).as_integer_ratio()
    return Fraction(numerator, denominator)


def _board_combinations(remaining_cards):
    return combinations(remaining_cards, 5)


def _as_positive_float(value, label):
    try:
        converted = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"Positive {label} is not representable as binary64.") from exc
    if not math.isfinite(converted) or converted <= 0:
        raise ValueError(f"Positive {label} underflows or is not representable as binary64.")
    return converted


@dataclass(frozen=True)
class FullBoardEquities:
    """Immutable categorical showdown data prepared for repeated solver runs."""

    hands: tuple
    pairs: tuple
    counts: tuple
    worlds: tuple
    _budget_items: tuple

    @property
    def budget(self):
        """Return a fresh JSON-safe budget dictionary."""
        result = {}
        for key, value in self._budget_items:
            result[key] = dict(value) if key == "limits" else value
        return result

    def validate(self):
        """Check bounded immutable structure before a solver consumes this table."""
        if type(self.hands) is not tuple or len(self.hands) != 2:
            raise ValueError("Full-board hands must be a two-player tuple.")
        if type(self._budget_items) is not tuple:
            raise ValueError("Full-board budget must be immutable.")
        if any(type(player_hands) is not tuple
               or len(player_hands) > MAX_HANDS_PER_PLAYER
               for player_hands in self.hands):
            raise ValueError("Full-board hand collection exceeds its 1,326-hand cap.")
        candidate_pairs = len(self.hands[0]) * len(self.hands[1])
        if candidate_pairs > MAX_CANDIDATE_PAIRS:
            raise ValueError("Full-board candidate pair limit exceeded (4,096).")
        for player_hands in self.hands:
            if any(type(hand) is not tuple or len(hand) != 2
                   or hand != tuple(sorted(hand))
                   or hand[0] == hand[1] or any(card not in DECK for card in hand)
                   for hand in player_hands):
                raise ValueError("Full-board private hands have an invalid shape or card.")
            if len(set(player_hands)) != len(player_hands):
                raise ValueError("Full-board private hand collections contain duplicates.")
        if (type(self.pairs) is not tuple or not self.pairs
                or len(self.pairs) > MAX_COMPATIBLE_PAIRS):
            raise ValueError("Full-board compatible-pair count exceeds its cap.")
        if (type(self.counts) is not tuple or len(self.counts) != len(self.pairs)
                or type(self.worlds) is not tuple
                or len(self.worlds) > 3 * len(self.pairs)):
            raise ValueError("Full-board counts or categorical rows exceed their caps.")

        priors = []
        pair_keys = set()
        pair_order = []
        expected_rows = []
        for pair_index, pair in enumerate(self.pairs):
            if type(pair) is not tuple or len(pair) != 3:
                raise ValueError("Each full-board pair must contain indices and a Fraction prior.")
            sb_index, bb_index, prior = pair
            if (type(sb_index) is not int or type(bb_index) is not int
                    or not 0 <= sb_index < len(self.hands[0])
                    or not 0 <= bb_index < len(self.hands[1])):
                raise ValueError("Full-board pair index is outside the hand tables.")
            if not set(self.hands[0][sb_index]).isdisjoint(self.hands[1][bb_index]):
                raise ValueError("Full-board pair contains colliding private cards.")
            if type(prior) is not Fraction or prior <= 0:
                raise ValueError("Full-board pair priors must be positive exact Fractions.")
            key = (sb_index, bb_index)
            if key in pair_keys:
                raise ValueError("Full-board pair table contains duplicates.")
            pair_keys.add(key)
            pair_order.append(key)
            priors.append(prior)

            count_row = self.counts[pair_index]
            if (type(count_row) is not tuple or len(count_row) != 3
                    or any(type(value) is not int or value < 0 for value in count_row)
                    or sum(count_row) != BOARDS_PER_PAIR):
                raise ValueError("Pair outcome counts must cover every full board.")
            wins, ties, losses = count_row
            for sign, count in zip(_SIGNS, (losses, ties, wins)):
                if count:
                    mass = _as_positive_float(prior * Fraction(count, BOARDS_PER_PAIR),
                                              "categorical mass")
                    expected_rows.append((sb_index, bb_index, mass, sign))
        expected_pair_keys = {(i, j) for i, sb_hand in enumerate(self.hands[0])
                              for j, bb_hand in enumerate(self.hands[1])
                              if set(sb_hand).isdisjoint(bb_hand)}
        if pair_keys != expected_pair_keys:
            raise ValueError("Full-board table omits or adds a compatible private pair.")
        if pair_order != sorted(pair_order):
            raise ValueError("Full-board pair order is not deterministic.")
        if sum(priors, Fraction()) != 1:
            raise ValueError("Full-board pair priors must sum exactly to one.")
        for row in self.worlds:
            if (type(row) is not tuple or len(row) != 4
                    or type(row[0]) is not int or type(row[1]) is not int
                    or type(row[2]) is not float or not math.isfinite(row[2]) or row[2] <= 0
                    or type(row[3]) is not int or row[3] not in _SIGNS):
                raise ValueError("Categorical rows must contain bounded integer indices/signs and positive finite float mass.")
        if self.worlds != tuple(expected_rows):
            raise ValueError("Categorical rows differ from their priors and outcome counts.")

        budget = self.budget
        board_evaluations = len(self.pairs) * BOARDS_PER_PAIR
        if (budget.get("candidate_pairs") != candidate_pairs
                or candidate_pairs > MAX_CANDIDATE_PAIRS
                or budget.get("compatible_pairs") != len(self.pairs)
                or budget.get("boards_per_pair") != BOARDS_PER_PAIR
                or budget.get("physical_worlds_upper_bound") != board_evaluations
                or budget.get("board_evaluations_upper_bound") != board_evaluations
                or budget.get("rank_calls_upper_bound") != 2 * board_evaluations
                or budget.get("categorical_rows_upper_bound") != MAX_CATEGORICAL_ROWS
                or budget.get("limits") != {
                    "candidate_pairs": MAX_CANDIDATE_PAIRS,
                    "compatible_pairs": MAX_COMPATIBLE_PAIRS,
                    "board_evaluations": MAX_BOARD_EVALUATIONS,
                    "rank_calls": MAX_RANK_CALLS,
                    "categorical_rows": MAX_CATEGORICAL_ROWS}):
            raise ValueError("Full-board budget metadata does not match immutable data.")
        return None


    def metadata(self):
        """Return JSON-safe pair count details alongside the structural budget."""
        self.validate()
        details = []
        for (sb_index, bb_index, prior), (wins, ties, losses) in zip(self.pairs, self.counts):
            details.append({
                "sb_hand": "".join(self.hands[0][sb_index]),
                "bb_hand": "".join(self.hands[1][bb_index]),
                "wins": wins,
                "ties": ties,
                "losses": losses,
                "board_outcomes": self.budget["boards_per_pair"],
                "pair_probability": float(prior),
            })
        return {"budget": self.budget, "counts": details}


@dataclass(frozen=True)
class PreflopEquityPlan:
    """Validated range pairs and bounded work estimate for exact board counting."""

    hands: tuple
    pairs: tuple
    _budget_items: tuple

    @property
    def budget(self):
        """Return a fresh JSON-safe estimate; no board evaluation has occurred."""
        result = {}
        for key, value in self._budget_items:
            result[key] = dict(value) if key == "limits" else value
        return result

    def validate(self):
        """Check pair, hand, and work metadata before any board enumeration."""
        if type(self.hands) is not tuple or len(self.hands) != 2:
            raise ValueError("Full-board plan hands must be a two-player tuple.")
        if any(type(player_hands) is not tuple
               or len(player_hands) > MAX_HANDS_PER_PLAYER
               for player_hands in self.hands):
            raise ValueError("Full-board plan hand collection exceeds its 1,326-hand cap.")
        candidate_pairs = len(self.hands[0]) * len(self.hands[1])
        if candidate_pairs > MAX_CANDIDATE_PAIRS:
            raise ValueError("Full-board candidate pair limit exceeded (4,096).")
        for player_hands in self.hands:
            if any(type(hand) is not tuple or len(hand) != 2
                   or hand != tuple(sorted(hand))
                   or hand[0] == hand[1] or any(card not in DECK for card in hand)
                   for hand in player_hands):
                raise ValueError("Full-board plan has an invalid private-hand shape or card.")
            if len(set(player_hands)) != len(player_hands):
                raise ValueError("Full-board plan hand collections contain duplicates.")
        if (type(self.pairs) is not tuple or not self.pairs
                or len(self.pairs) > MAX_COMPATIBLE_PAIRS):
            raise ValueError("Full-board compatible pair limit exceeded (4).")
        if type(self._budget_items) is not tuple:
            raise ValueError("Full-board plan budget must be immutable.")

        seen = set()
        pair_order = []
        priors = []
        for pair in self.pairs:
            if type(pair) is not tuple or len(pair) != 3:
                raise ValueError("Each plan pair must have two indices and an exact prior.")
            sb_index, bb_index, prior = pair
            if (type(sb_index) is not int or type(bb_index) is not int
                    or not 0 <= sb_index < len(self.hands[0])
                    or not 0 <= bb_index < len(self.hands[1])):
                raise ValueError("Full-board plan pair index is outside the hand tables.")
            if not set(self.hands[0][sb_index]).isdisjoint(self.hands[1][bb_index]):
                raise ValueError("Full-board plan pair contains colliding private cards.")
            if type(prior) is not Fraction or prior <= 0:
                raise ValueError("Full-board plan priors must be positive exact Fractions.")
            if (sb_index, bb_index) in seen:
                raise ValueError("Full-board plan contains duplicate private pairs.")
            seen.add((sb_index, bb_index))
            pair_order.append((sb_index, bb_index))
            _as_positive_float(prior, "pair probability")
            priors.append(prior)
        expected_pairs = {(i, j) for i, sb_hand in enumerate(self.hands[0])
                          for j, bb_hand in enumerate(self.hands[1])
                          if set(sb_hand).isdisjoint(bb_hand)}
        if seen != expected_pairs:
            raise ValueError("Full-board plan omits or adds a compatible pair.")
        if pair_order != sorted(pair_order):
            raise ValueError("Full-board plan pair order is not deterministic.")
        if sum(priors, Fraction()) != 1:
            raise ValueError("Full-board plan pair priors must sum exactly to one.")

        budget = self.budget
        board_evaluations = len(self.pairs) * BOARDS_PER_PAIR
        if (budget.get("candidate_pairs") != candidate_pairs
                or budget.get("compatible_pairs") != len(self.pairs)
                or budget.get("boards_per_pair") != BOARDS_PER_PAIR
                or budget.get("physical_worlds_upper_bound") != board_evaluations
                or budget.get("board_evaluations_upper_bound") != board_evaluations
                or budget.get("rank_calls_upper_bound") != 2 * board_evaluations
                or budget.get("categorical_rows_upper_bound") != MAX_CATEGORICAL_ROWS
                or budget.get("limits") != {
                    "candidate_pairs": MAX_CANDIDATE_PAIRS,
                    "compatible_pairs": MAX_COMPATIBLE_PAIRS,
                    "board_evaluations": MAX_BOARD_EVALUATIONS,
                    "rank_calls": MAX_RANK_CALLS,
                    "categorical_rows": MAX_CATEGORICAL_ROWS}):
            raise ValueError("Full-board plan budget does not match its bounded structure.")
        return None


    def build(self, progress=None):
        """Enumerate all boards per pair and retain only categorical sign totals.

        progress(pair_number, processed_boards, total_boards) is called at
        pair start, each 100,000 boards, and pair completion. Callback work is
        caller-owned and excluded from the rank-call budget.
        """
        if progress is not None and not callable(progress):
            raise TypeError("progress must be callable or None.")

        self.validate()
        budget = dict(self._budget_items)
        rank_calls_limit = budget["rank_calls_upper_bound"]
        ranks_used = 0
        all_counts = []
        rows = []
        for pair_number, (sb_index, bb_index, pair_prior) in enumerate(self.pairs, 1):
            sb_hand = self.hands[0][sb_index]
            bb_hand = self.hands[1][bb_index]
            dead = set(sb_hand + bb_hand)
            remaining = tuple(card for card in DECK if card not in dead)
            wins = ties = losses = processed = 0
            if progress is not None:
                progress(pair_number, 0, BOARDS_PER_PAIR)

            for board in _board_combinations(remaining):
                if processed >= BOARDS_PER_PAIR:
                    raise ValueError("Board enumeration exceeded its admitted count.")
                if ranks_used + 2 > rank_calls_limit:
                    raise ValueError("Full-board rank-call budget exceeded before ranking.")
                sb_rank = rank_hand(sb_hand + board)
                bb_rank = rank_hand(bb_hand + board)
                ranks_used += 2
                processed += 1
                if sb_rank > bb_rank:
                    wins += 1
                elif sb_rank < bb_rank:
                    losses += 1
                else:
                    ties += 1
                if progress is not None and processed % _PROGRESS_EVERY == 0:
                    progress(pair_number, processed, BOARDS_PER_PAIR)

            if processed != BOARDS_PER_PAIR:
                raise ValueError(
                    f"Board enumeration produced {processed}; expected {BOARDS_PER_PAIR}."
                )
            if wins + ties + losses != BOARDS_PER_PAIR:
                raise AssertionError("Showdown outcome counts do not cover every board.")
            all_counts.append((wins, ties, losses))
            for sign, count in zip(_SIGNS, (losses, ties, wins)):
                if count == 0:
                    continue
                mass = pair_prior * Fraction(count, BOARDS_PER_PAIR)
                rows.append((sb_index, bb_index, _as_positive_float(mass, "categorical mass"), sign))
            if progress is not None and processed % _PROGRESS_EVERY:
                progress(pair_number, processed, BOARDS_PER_PAIR)

        expected_boards = len(self.pairs) * BOARDS_PER_PAIR
        if ranks_used != expected_boards * 2:
            raise AssertionError("Actual rank work did not match the admitted total.")
        if len(rows) > budget["categorical_rows_upper_bound"]:
            raise AssertionError("Categorical rows exceeded their structural bound.")
        result = FullBoardEquities(
            hands=self.hands,
            pairs=self.pairs,
            counts=tuple(all_counts),
            worlds=tuple(rows),
            _budget_items=self._budget_items,
        )
        result.validate()
        return result


def plan_preflop_equities(sb_range, bb_range):
    """Prepare exact normalized private-pair priors under strict work caps.

    Candidate and compatible-pair checks happen before any hand ranking or
    board allocation. Range weights are normalized after private collisions
    are removed, using exact fractions of their represented binary64 values.
    """
    expanded = (expand_range(sb_range), expand_range(bb_range))
    hands = (tuple(expanded[0]), tuple(expanded[1]))
    weights = tuple(
        tuple(_fractional_weight(expanded[player][hand]) for hand in hands[player])
        for player in (0, 1)
    )
    candidate_pairs = len(hands[0]) * len(hands[1])
    if candidate_pairs > MAX_CANDIDATE_PAIRS:
        raise ValueError("Full-board candidate pair limit exceeded (4,096).")

    raw_pairs = []
    for sb_index, sb_hand in enumerate(hands[0]):
        sb_cards = set(sb_hand)
        for bb_index, bb_hand in enumerate(hands[1]):
            if sb_cards.isdisjoint(bb_hand):
                raw_pairs.append((sb_index, bb_index,
                                  weights[0][sb_index] * weights[1][bb_index]))
                if len(raw_pairs) > MAX_COMPATIBLE_PAIRS:
                    raise ValueError("Full-board compatible pair limit exceeded (4).")
    if not raw_pairs:
        raise ValueError("The ranges have no compatible private-hand pair.")

    normalizer = sum((weight for _, _, weight in raw_pairs), Fraction())
    pairs = tuple((sb_index, bb_index, weight / normalizer)
                  for sb_index, bb_index, weight in raw_pairs)
    for _, _, prior in pairs:
        _as_positive_float(prior, "pair probability")

    pair_count = len(pairs)
    board_evaluations = pair_count * BOARDS_PER_PAIR
    rank_calls = 2 * board_evaluations
    if board_evaluations > MAX_BOARD_EVALUATIONS or rank_calls > MAX_RANK_CALLS:
        raise ValueError("Full-board ranking work exceeds its fixed admission cap.")
    budget = {
        "candidate_pairs": candidate_pairs,
        "compatible_pairs": pair_count,
        "boards_per_pair": BOARDS_PER_PAIR,
        "physical_worlds_upper_bound": board_evaluations,
        "board_evaluations_upper_bound": board_evaluations,
        "rank_calls_upper_bound": rank_calls,
        "categorical_rows_upper_bound": MAX_CATEGORICAL_ROWS,
        "limits": {
            "candidate_pairs": MAX_CANDIDATE_PAIRS,
            "compatible_pairs": MAX_COMPATIBLE_PAIRS,
            "board_evaluations": MAX_BOARD_EVALUATIONS,
            "rank_calls": MAX_RANK_CALLS,
            "categorical_rows": MAX_CATEGORICAL_ROWS,
        },
        "scope": "Exact unordered five-card boards per compatible private pair; logical counts, not time or memory guarantees.",
    }
    plan = PreflopEquityPlan(
        hands=hands,
        pairs=pairs,
        _budget_items=tuple((key, tuple(value.items()) if key == "limits" else value)
                             for key, value in budget.items()),
    )
    plan.validate()
    return plan
