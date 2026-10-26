"""Exact matrix-free mass queries for prefixes of full-deck Hold'em boards.

This is a research-only probability operator. It computes blocker-conditioned
mass for a fixed public prefix; it does not build a game tree or train a policy.
All input binary64 weights are snapshotted as their exact rational values.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
import math
from types import MappingProxyType
from typing import TypeAlias


Hand: TypeAlias = tuple[int, int]
WeightMap: TypeAlias = Mapping[Hand, Fraction]
_CARD_COUNT = 52
_MAX_HANDS = math.comb(_CARD_COUNT, 2)
_FLOP_DENOMINATOR = math.comb(48, 3)


def _hand(value: object, label: str) -> Hand:
    if (not isinstance(value, tuple) or len(value) != 2
            or any(type(card) is not int or not 0 <= card < _CARD_COUNT
                   for card in value)
            or value[0] >= value[1]):
        raise ValueError(f"{label} must be a canonical pair of distinct card IDs in 0..51.")
    return value


def _snapshot_weights(source: object, label: str) -> WeightMap:
    if not isinstance(source, Mapping):
        raise TypeError(f"{label} must be a mapping of canonical hands to weights.")
    if not source:
        raise ValueError(f"{label} must not be empty.")
    if len(source) > _MAX_HANDS:
        raise ValueError(f"{label} cannot contain more than {_MAX_HANDS} hands.")

    copied: dict[Hand, Fraction] = {}
    for raw_hand, raw_weight in source.items():
        hand = _hand(raw_hand, f"{label} hand")
        if isinstance(raw_weight, bool) or not isinstance(raw_weight, (int, float)):
            raise TypeError(f"{label} weights must be integers or binary64 floats, not booleans.")
        try:
            value = float(raw_weight)
        except (OverflowError, ValueError) as exc:
            raise ValueError(f"{label} weights must convert to finite positive binary64 values.") from exc
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"{label} weights must convert to finite positive binary64 values.")
        copied[hand] = Fraction.from_float(value)
    return MappingProxyType(copied)


def _card_totals(weights: WeightMap) -> tuple[Fraction, ...]:
    totals = [Fraction(0) for _ in range(_CARD_COUNT)]
    for hand, weight in weights.items():
        totals[hand[0]] += weight
        totals[hand[1]] += weight
    return tuple(totals)


def _compatible_weight(hand: Hand, total: Fraction,
                       card_totals: tuple[Fraction, ...],
                       same_hand: WeightMap) -> Fraction:
    # The hand's weight appears in both card buckets; add it back once.
    return total - card_totals[hand[0]] - card_totals[hand[1]] + same_hand.get(hand, 0)


def _board_prefix(board: object) -> tuple[int, ...]:
    if isinstance(board, (str, bytes)) or not isinstance(board, Sequence):
        raise TypeError("board must be a sequence of card IDs.")
    cards = tuple(board)
    if len(cards) not in (0, 3, 4, 5):
        raise ValueError("board must contain 0, 3, 4, or 5 cards.")
    if any(type(card) is not int or not 0 <= card < _CARD_COUNT for card in cards):
        raise ValueError("board cards must be integer IDs in 0..51.")
    if len(set(cards)) != len(cards):
        raise ValueError("board cards must be distinct.")
    if len(cards) >= 3:
        cards = tuple(sorted(cards[:3])) + cards[3:]
    return cards


def _chance_divisor(board_length: int) -> int:
    if board_length == 0:
        return 1
    if board_length == 3:
        return _FLOP_DENOMINATOR
    if board_length == 4:
        return _FLOP_DENOMINATOR * 45
    return _FLOP_DENOMINATOR * 45 * 44


@dataclass(frozen=True, slots=True)
class PrefixMass:
    """Immutable mass and per-hand marginals for one public board prefix.

    ``hand_masses`` contains every input hand. A hand blocked by the board has
    exact zero mass. Values and ``total_mass`` share the original root
    normalization; public branches are never locally renormalized.
    """

    board: tuple[int, ...]
    total_mass: Fraction
    hand_masses: tuple[WeightMap, WeightMap]
    _sb_weights: WeightMap = field(repr=False, compare=False)
    _bb_weights: WeightMap = field(repr=False, compare=False)
    _normalizer: Fraction = field(repr=False, compare=False)
    _chance_divisor: int = field(repr=False, compare=False)

    def pair_mass(self, sb_hand: Hand, bb_hand: Hand) -> Fraction:
        """Return one ordered private-pair's absolute mass at this prefix."""
        sb_hand = _hand(sb_hand, "sb_hand")
        bb_hand = _hand(bb_hand, "bb_hand")
        sb_weight = self._sb_weights.get(sb_hand)
        bb_weight = self._bb_weights.get(bb_hand)
        if sb_weight is None or bb_weight is None:
            return Fraction(0)
        if (set(sb_hand) & set(bb_hand)) or (set(sb_hand) & set(self.board)) or (set(bb_hand) & set(self.board)):
            return Fraction(0)
        return sb_weight * bb_weight / (self._normalizer * self._chance_divisor)


@dataclass(frozen=True, slots=True, init=False)
class FullDeckPrefixMass:
    """Exact full-deck mass operator using O(H0+H1+52) prefix work/storage.

    Inputs are detached at construction. Binary64 values are preserved exactly
    through ``Fraction.from_float``; integer inputs are first converted to
    binary64 as specified by this experiment.
    """

    _sb_weights: WeightMap = field(repr=False)
    _bb_weights: WeightMap = field(repr=False)
    _sb_total: Fraction = field(repr=False)
    _bb_total: Fraction = field(repr=False)
    _sb_cards: tuple[Fraction, ...] = field(repr=False)
    _bb_cards: tuple[Fraction, ...] = field(repr=False)
    root_compatible_mass: Fraction
    input_dimensions: tuple[int, int]

    def __init__(self, sb_weights: Mapping[Hand, int | float],
                 bb_weights: Mapping[Hand, int | float]) -> None:
        sb = _snapshot_weights(sb_weights, "sb_weights")
        bb = _snapshot_weights(bb_weights, "bb_weights")
        sb_total = sum(sb.values(), Fraction(0))
        bb_total = sum(bb.values(), Fraction(0))
        sb_cards = _card_totals(sb)
        bb_cards = _card_totals(bb)
        compatible = sum(
            weight * _compatible_weight(hand, bb_total, bb_cards, bb)
            for hand, weight in sb.items()
        )
        if compatible <= 0:
            raise ValueError("The input ranges must contain positive compatible private-pair mass.")
        object.__setattr__(self, "_sb_weights", sb)
        object.__setattr__(self, "_bb_weights", bb)
        object.__setattr__(self, "_sb_total", sb_total)
        object.__setattr__(self, "_bb_total", bb_total)
        object.__setattr__(self, "_sb_cards", sb_cards)
        object.__setattr__(self, "_bb_cards", bb_cards)
        object.__setattr__(self, "root_compatible_mass", compatible)
        object.__setattr__(self, "input_dimensions", (len(sb), len(bb)))

    def at(self, board: Sequence[int] = ()) -> PrefixMass:
        """Compute exact absolute mass for a canonicalized flop/turn/river prefix."""
        prefix = _board_prefix(board)
        blocked = frozenset(prefix)
        sb = {hand: weight for hand, weight in self._sb_weights.items()
              if not (blocked.intersection(hand))}
        bb = {hand: weight for hand, weight in self._bb_weights.items()
              if not (blocked.intersection(hand))}
        sb_view: WeightMap = MappingProxyType(sb)
        bb_view: WeightMap = MappingProxyType(bb)
        sb_total = sum(sb.values(), Fraction(0))
        bb_total = sum(bb.values(), Fraction(0))
        sb_cards = _card_totals(sb_view)
        bb_cards = _card_totals(bb_view)

        sb_joint = sum(
            weight * _compatible_weight(hand, bb_total, bb_cards, bb_view)
            for hand, weight in sb.items()
        )
        bb_joint = sum(
            weight * _compatible_weight(hand, sb_total, sb_cards, sb_view)
            for hand, weight in bb.items()
        )
        if sb_joint != bb_joint:
            raise ArithmeticError("Exact compatible-mass marginals disagree.")

        divisor = _chance_divisor(len(prefix))
        scale = self.root_compatible_mass * divisor
        sb_masses = {
            hand: (weight * _compatible_weight(hand, bb_total, bb_cards, bb_view) / scale
                   if hand in sb else Fraction(0))
            for hand, weight in self._sb_weights.items()
        }
        bb_masses = {
            hand: (weight * _compatible_weight(hand, sb_total, sb_cards, sb_view) / scale
                   if hand in bb else Fraction(0))
            for hand, weight in self._bb_weights.items()
        }
        return PrefixMass(
            board=prefix,
            total_mass=sb_joint / scale,
            hand_masses=(MappingProxyType(sb_masses), MappingProxyType(bb_masses)),
            _sb_weights=self._sb_weights,
            _bb_weights=self._bb_weights,
            _normalizer=self.root_compatible_mass,
            _chance_divisor=divisor,
        )
