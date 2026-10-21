"""Canonicalize compact flop policy rows onto an exact binary64 grid.

This is an output-boundary helper. It does not change any training recurrence
or assert orbitwise parity or approximate-chance equivalence.
"""
from fractions import Fraction
import math
import struct


MAX_ROWS = 466
MAX_HISTORY_ITEMS = 32
MAX_HISTORY_TOKEN_CHARS = 64
GRID_BITS = 52
GRID = 1 << GRID_BITS
_SUITS = frozenset("cdhs")
_RANKS = frozenset("23456789TJQKA")
_SUM_TOLERANCE = Fraction(1, 10**12)


def _validate_key(key):
    if type(key) is not tuple or len(key) != 3:
        raise ValueError("Policy key must be (player, canonical hand, history tuple).")
    player, hand, history = key
    if type(player) is not int or player not in (0, 1):
        raise ValueError("Policy player must be integer 0 or 1.")
    if type(hand) is not str or len(hand) != 4:
        raise ValueError("Policy hand must be a canonical two-card string.")
    cards = (hand[:2], hand[2:])
    if (cards[0] == cards[1]
            or any(card[0] not in _RANKS or card[1] not in _SUITS for card in cards)
            or cards != tuple(sorted(cards))):
        raise ValueError("Policy hand must contain distinct canonically ordered cards.")
    if (type(history) is not tuple or len(history) > MAX_HISTORY_ITEMS
            or any(type(item) is not str or len(item) > MAX_HISTORY_TOKEN_CHARS
                   for item in history)):
        raise ValueError("Policy history exceeds its bounded tuple-of-strings shape.")


def _nearest_even_grid(numerator, denominator):
    """Round numerator/denominator to an integer with ties going to even."""
    quotient, remainder = divmod(numerator, denominator)
    twice = remainder * 2
    if twice > denominator or (twice == denominator and quotient % 2):
        quotient += 1
    return quotient


def canonicalize_binary_rows(raw_rows):
    """Return exact-sum binary64 rows and a rational distance audit.

    ``raw_rows`` maps ``(player, hand, history)`` keys to two finite floats.
    The input is copied by construction and is never modified.
    """
    if type(raw_rows) is not dict or len(raw_rows) > MAX_ROWS:
        raise ValueError("Expected a dict containing at most 466 policy rows.")

    # Validate every cheap structural and scalar constraint before Fraction work.
    for key, values in raw_rows.items():
        _validate_key(key)
        if type(values) not in (tuple, list) or len(values) != 2:
            raise ValueError("Each policy row must contain exactly two probabilities.")
        if any(type(value) is not float or not math.isfinite(value)
               or value < 0.0 or value > 1.0 for value in values):
            raise ValueError("Probabilities must be finite binary64 values in [0, 1].")

    canonical = {}
    rows_changed = 0
    zeroed_positive = 0
    max_normalized_distance = Fraction(0)
    max_raw_distance = Fraction(0)
    for key, values in raw_rows.items():
        raw0, raw1 = (Fraction(value) for value in values)
        raw_total = raw0 + raw1
        if raw_total <= 0 or abs(raw_total - 1) > _SUM_TOLERANCE:
            raise ValueError("Raw probabilities must have a positive sum within 1e-12 of one.")

        normalized = raw0 / raw_total
        grid_index = _nearest_even_grid(normalized.numerator * GRID,
                                        normalized.denominator)
        first = float(Fraction(grid_index, GRID))
        second = float(Fraction(GRID - grid_index, GRID))
        row = (first, second)
        canonical[key] = row
        if any(struct.pack(">d", actual) != struct.pack(">d", expected)
               for actual, expected in zip(row, values)):
            rows_changed += 1
        if raw0 > 0 and grid_index == 0:
            zeroed_positive += 1
        if raw1 > 0 and grid_index == GRID:
            zeroed_positive += 1

        exact_first = Fraction(first)
        max_normalized_distance = max(max_normalized_distance,
                                      abs(exact_first - normalized))
        max_raw_distance = max(max_raw_distance, abs(exact_first - raw0),
                               abs(Fraction(second) - raw1))

    audit = {
        "rows_changed": rows_changed,
        "max_normalized_probability_distance": str(max_normalized_distance),
        "max_raw_distance": str(max_raw_distance),
        "zeroed_positive_probabilities": zeroed_positive,
        "grid_bits": GRID_BITS,
    }
    return canonical, audit
