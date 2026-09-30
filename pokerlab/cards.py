"""Cards, exact hand rankings, and weighted Hold'em range expansion."""
from collections import Counter
from itertools import combinations
import math
import re

RANKS = "23456789TJQKA"
SUITS = "cdhs"
DECK = tuple(r + s for r in RANKS for s in SUITS)
NAMES = ("High card", "One pair", "Two pair", "Three of a kind", "Straight",
         "Flush", "Full house", "Four of a kind", "Straight flush")


def cards(value, count=None):
    if isinstance(value, str):
        value = value.replace("10", "T")
        for glyph, suit in zip("♣♦♥♠", SUITS):
            value = value.replace(glyph, suit)
        text = re.sub(r"[\s,]+", "", value)
        if len(text) % 2:
            raise ValueError("Use cards such as As Jh 10c.")
        value = [text[i:i+2] for i in range(0, len(text), 2)]
    result = tuple(str(c)[0:1].upper() + str(c)[1:].lower() for c in value)
    if any(c not in DECK for c in result):
        raise ValueError("Unknown card. Use ranks 2–9,T,J,Q,K,A and suits c,d,h,s.")
    if len(set(result)) != len(result):
        raise ValueError("The same card cannot appear twice.")
    if count is not None and len(result) != count:
        raise ValueError(f"Expected {count} cards, received {len(result)}.")
    return result


def straight_high(ranks):
    ranks = set(ranks)
    if 14 in ranks:
        ranks.add(1)
    for high in range(14, 4, -1):
        if all(r in ranks for r in range(high-4, high+1)):
            return high
    return 0


def rank_hand(hand):
    """Comparable best-five rank for 5–7 validated, distinct cards."""
    if not 5 <= len(hand) <= 7:
        raise ValueError("Hand ranking needs 5–7 cards.")
    counts = Counter(RANKS.index(c[0]) + 2 for c in hand)
    ordered = sorted(counts, reverse=True)
    flush = next(([RANKS.index(c[0])+2 for c in hand if c[1] == suit]
                  for suit in SUITS if sum(c[1] == suit for c in hand) >= 5), None)
    if flush and (high := straight_high(flush)):
        return (8, high)
    groups = sorted(((n, r) for r, n in counts.items()), reverse=True)
    if groups[0][0] == 4:
        return (7, groups[0][1], max(r for r in ordered if r != groups[0][1]))
    trips = [r for n, r in groups if n >= 3]
    if trips:
        pairs = [r for n, r in groups if n >= 2 and r != trips[0]]
        if pairs:
            return (6, trips[0], max(pairs))
    if flush:
        return (5, *sorted(flush, reverse=True)[:5])
    if high := straight_high(ordered):
        return (4, high)
    if trips:
        return (3, trips[0], *[r for r in ordered if r != trips[0]][:2])
    pairs = sorted((r for r in ordered if counts[r] == 2), reverse=True)
    if len(pairs) >= 2:
        return (2, *pairs[:2], max(r for r in ordered if r not in pairs[:2]))
    if pairs:
        return (1, pairs[0], *[r for r in ordered if r != pairs[0]][:3])
    return (0, *ordered[:5])


def expand_range(expression="random", dead=()):
    """Return {sorted two-card tuple: weight}; overlaps use the last token.

    Grammar: AA, TT+, AK, AJs+, KQo, AsKh, AA:0.5, comma/space separated.
    Unsuited suffix omitted means both suited and offsuit. No percentage ranges.
    """
    dead = set(dead)
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("Enter a range, or 'random'.")
    result = {}
    for token in re.split(r"[\s,]+", expression.strip()):
        base, sep, weight_text = token.partition(":")
        weight = float(weight_text) if sep else 1.0
        if not math.isfinite(weight) or not 0 <= weight <= 1:
            raise ValueError("Range weights must be between 0 and 1.")
        if base.lower() in ("random", "all", "*"):
            combos = combinations(DECK, 2)
        elif re.fullmatch(r"[2-9TJQKA][cdhs][2-9TJQKA][cdhs]", base, re.I):
            combos = [cards(base, 2)]
        else:
            match = re.fullmatch(r"([2-9TJQKA])([2-9TJQKA])([so]?)(\+?)", base, re.I)
            if not match:
                raise ValueError(f"Unsupported range token: {base}")
            a, b, kind, plus = match.groups()
            a, b, kind = a.upper(), b.upper(), kind.lower()
            ia, ib = RANKS.index(a), RANKS.index(b)
            if ia < ib or (a == b and kind):
                raise ValueError(f"Use high rank first and no suit suffix on pairs: {base}")
            specs = [(a, b)]
            if plus:
                specs = [(r, r) for r in RANKS[ia:]] if a == b else [(a, r) for r in RANKS[ib:ia]]
            combos = []
            for x, y in specs:
                combos.extend((x+s, y+t) for s in SUITS for t in SUITS
                              if (x != y or s < t) and (kind != "s" or s == t)
                              and (kind != "o" or s != t))
        for combo in combos:
            combo = tuple(sorted(combo))
            if not dead.intersection(combo):
                if weight:
                    result[combo] = weight
                else:
                    result.pop(combo, None)
    if not result:
        raise ValueError("No possible hands remain in this range after card removal.")
    return result
