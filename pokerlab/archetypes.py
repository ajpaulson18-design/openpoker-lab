"""Parameterized, deterministic opponent decision policies for batch simulation.

This module turns the same archetype priors used for Bayesian opponent
modeling (``pokerlab.models.ARCHETYPE_PRIORS``) into a reusable *behavior*:
a function from a legal no-limit Hold'em decision point to a concrete action.
There is exactly one parameterized policy implementation; archetypes only
select its six input numbers. No personality has hard-coded, hand-specific
logic.

Hand-strength inputs are exact poker facts wherever an exact calculation is
cheap enough to run inside a batch loop:

- Preflop strength uses the published Chen formula, a well-known deterministic
  heuristic ranking of the 169 starting-hand classes. It is explicitly a
  heuristic ranking, not an equity calculation.
- Postflop strength uses the engine's own exact ``rank_hand`` category for the
  made hand, plus exact (not sampled) detection of flush and straight draws
  from the visible hole and board cards.

Mapping that strength onto an action is a declared behavioral model, exactly
like the solver's restricted betting tree or the practice checkdown EV model:
useful for simulation and comparison, not a claim about equilibrium or human
play.
"""
from __future__ import annotations

from dataclasses import dataclass
import random

from .cards import RANKS, SUITS, rank_hand
from .models import ARCHETYPE_PRIORS, TENDENCIES, normalize_archetype

# Chen formula per-card point values: A=10, K=8, Q=7, J=6, T=5, 2-9 = rank/2.
_CHEN_HIGH_CARD = {"A": 10.0, "K": 8.0, "Q": 7.0, "J": 6.0, "T": 5.0}


def _chen_value(rank: str) -> float:
    return _CHEN_HIGH_CARD.get(rank, (RANKS.index(rank) + 2) / 2)


def chen_score(hole: tuple[str, str]) -> float:
    """Return the classic Chen-formula preflop strength score (roughly 0-20).

    Public, well-documented heuristic by Bill Chen: score the higher card,
    double it for pairs, add 2 for suited, subtract a gap penalty, add a small
    connectedness bonus for low unpaired cards, then round up to a half point.
    This ranks starting-hand classes; it is not an equity or EV estimate.
    """
    r1, r2 = hole[0][0].upper(), hole[1][0].upper()
    s1, s2 = hole[0][1], hole[1][1]
    i1, i2 = RANKS.index(r1), RANKS.index(r2)
    hi = r1 if i1 >= i2 else r2
    if r1 == r2:
        score = max(_chen_value(r1) * 2, 5.0)
    else:
        score = _chen_value(hi)
        gap = max(i1, i2) - min(i1, i2) - 1
        score -= {0: 0, 1: 1, 2: 2, 3: 4}.get(gap, 5)
        if gap <= 1 and max(i1, i2) + 2 < 12:  # both cards below queen
            score += 1
        if s1 == s2:
            score += 2
    import math
    return math.ceil(score * 2) / 2


def _starting_hand_population():
    """Every canonical starting-hand class with its exact combination count."""
    population = []
    for i, r1 in enumerate(RANKS):
        for r2 in RANKS[:i + 1]:
            if r1 == r2:
                population.append((chen_score((r1 + "s", r1 + "h")), 6))
            else:
                population.append((chen_score((r1 + "s", r2 + "s")), 4))
                population.append((chen_score((r1 + "s", r2 + "h")), 12))
    return population


def _build_percentile_table():
    """Cumulative-weight table over exact starting-hand combination counts."""
    population = sorted(_starting_hand_population())
    scores = [item[0] for item in population]
    total = sum(weight for _, weight in population)
    cumulative, running = [], 0
    for _, weight in population:
        running += weight
        cumulative.append(running)
    return scores, cumulative, total


_CHEN_SCORES, _CHEN_CUMULATIVE, _CHEN_TOTAL_COMBOS = _build_percentile_table()


def preflop_strength(hole: tuple[str, str]) -> float:
    """Return the fraction of starting-hand combinations this hand beats or ties.

    Built from the exact combinatorial population of 1,326 starting hands
    (weighted the same way as ``expand_range``), not a sample. 1.0 is the
    strongest class (AA); near 0 is the weakest. This keeps an archetype's
    ``vpip`` parameter meaningful as "plays roughly the top vpip share of
    starting hands," the standard poker definition of looseness.
    """
    import bisect
    score = chen_score(hole)
    index = bisect.bisect_right(_CHEN_SCORES, score) - 1
    covered = _CHEN_CUMULATIVE[index] if index >= 0 else 0
    return covered / _CHEN_TOTAL_COMBOS


def _has_flush_draw(cards):
    counts = {s: 0 for s in SUITS}
    for c in cards:
        counts[c[1]] += 1
    return any(n == 4 for n in counts.values())


def _has_straight_draw(cards):
    ranks = {RANKS.index(c[0]) + 2 for c in cards}
    if 14 in ranks:
        ranks.add(1)
    for high in range(14, 4, -1):
        window = set(range(high - 4, high + 1))
        if len(window - ranks) == 1:
            return True
    return False


def postflop_strength(hole: tuple[str, str], board: tuple[str, ...]) -> float:
    """Exact made-hand category plus a documented, explicit draw adjustment."""
    cards = tuple(hole) + tuple(board)
    category, *tiebreak = rank_hand(cards)
    base = category / 8
    fine = ((tiebreak[0] - 2) / 12) if tiebreak else 0.0
    strength = base + fine / 9  # keep ordering within a category, never cross one
    if category <= 1 and len(board) in (3, 4):
        if _has_flush_draw(cards):
            strength += 0.18
        elif _has_straight_draw(cards):
            strength += 0.12
    return max(0.0, min(1.0, strength))


def hand_strength(hole: tuple[str, str], board: tuple[str, ...]) -> float:
    """Dispatch to the preflop or postflop exact-input strength heuristic."""
    return preflop_strength(hole) if not board else postflop_strength(hole, board)


@dataclass(frozen=True, slots=True)
class ArchetypeParameters:
    """The six reusable behavior dials; archetypes only choose these numbers."""

    vpip: float
    pfr: float
    three_bet: float
    fold_to_bet: float
    aggression: float
    showdown_bluff: float

    @classmethod
    def from_archetype(cls, archetype: str) -> "ArchetypeParameters":
        name = normalize_archetype(archetype)
        try:
            priors = ARCHETYPE_PRIORS[name]
        except KeyError:
            raise ValueError(f"Unknown opponent archetype: {archetype!r}") from None
        return cls(*(priors[tendency] for tendency in TENDENCIES))


def _clamp_int(value, low, high):
    return max(low, min(high, int(round(value))))


def _choose(legal, order):
    """Return the first legal action in a priority order; always succeeds."""
    for action in order:
        if legal.get(action):
            return action
    return "check" if legal.get("check") else "fold"


class ArchetypePolicy:
    """A deterministic, seeded decision function for one archetype.

    The same six parameters drive every street. There is no per-hand special
    casing: this is one reusable strategy shape, not scripted personalities.
    """

    def __init__(self, archetype: str, rng: random.Random):
        self.archetype = normalize_archetype(archetype)
        self.params = ArchetypeParameters.from_archetype(archetype)
        self.rng = rng

    def decide(self, game, seat: int) -> tuple[str, int | None]:
        legal = game.legal()
        hole = game.hands[seat]
        board = game.board
        strength = hand_strength(hole, board)
        p = self.params
        owe = legal["call"]
        if not board:
            return self._preflop(game, legal, strength, owe)
        return self._postflop(game, legal, strength, owe)

    # -- preflop -----------------------------------------------------
    def _preflop(self, game, legal, strength, owe):
        p = self.params
        facing_raise = game.current_bet > game.big_blind
        if not owe:
            # No outstanding bet beyond what this seat already has in: the
            # big blind getting a walk, or opening the action.
            if legal["raise"] and self.rng.random() < p.pfr and strength >= (1 - p.vpip) * 0.6:
                return "raise", self._open_size(legal, p)
            return "check", None
        threshold = 1 - p.vpip if not facing_raise else min(0.97, 1 - p.vpip * 0.5)
        if strength < threshold:
            return _choose(legal, ("fold", "check")), None
        reraise_rate = p.three_bet if facing_raise else p.pfr
        if legal["raise"] and self.rng.random() < reraise_rate:
            return "raise", self._open_size(legal, p)
        return _choose(legal, ("call", "check")), None

    def _open_size(self, legal, p):
        span = legal["raise_max"] - legal["raise_min"]
        return _clamp_int(legal["raise_min"] + span * 0.25 * p.aggression,
                          legal["raise_min"], legal["raise_max"])

    # -- postflop ------------------------------------------------------
    def _postflop(self, game, legal, strength, owe):
        p = self.params
        if not owe:
            bet_rate = p.aggression if strength >= 0.55 else p.aggression * p.showdown_bluff
            if legal["raise"] and self.rng.random() < bet_rate:
                return "raise", self._bet_size(legal, p)
            return "check", None
        effective_fold = p.fold_to_bet * max(0.0, 1 - strength) ** 0.7
        if strength < 0.12 and self.rng.random() < max(effective_fold, p.fold_to_bet * 0.5):
            return _choose(legal, ("fold", "check")), None
        if self.rng.random() < effective_fold:
            return _choose(legal, ("fold", "check")), None
        raise_rate = p.aggression if strength >= 0.6 else p.aggression * p.showdown_bluff * 0.5
        if legal["raise"] and self.rng.random() < raise_rate:
            return "raise", self._bet_size(legal, p)
        return _choose(legal, ("call", "check")), None

    def _bet_size(self, legal, p):
        span = legal["raise_max"] - legal["raise_min"]
        return _clamp_int(legal["raise_min"] + span * (0.2 + 0.3 * p.aggression),
                          legal["raise_min"], legal["raise_max"])


def play_hand(game, policies: dict[int, ArchetypePolicy]) -> None:
    """Advance a Game to completion using one policy per seat."""
    while not game.done:
        action, amount = policies[game.actor].decide(game, game.actor)
        game.act(action, amount)
