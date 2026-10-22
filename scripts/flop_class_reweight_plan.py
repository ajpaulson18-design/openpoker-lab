"""Rank-free prior forecast for a proposed fixed-support flop reweighting proof.

This plan computes only hand collisions and exact joint pair priors. It does
not certify a quotient, rank hands, or construct physical worlds or a tree.
"""
from dataclasses import dataclass
from fractions import Fraction
from math import lcm


BOARD = ("2c", "3d", "4h")
OOP_HANDS = ("AsAd", "QsQd")
IP_HANDS = ("AsKh", "KsKd")
RUNOUTS_PER_PAIR = 45 * 44
MAX_COMPONENT_BITS = 128
MAX_CLASS_MASS_BITS = 384


@dataclass(frozen=True)
class ReweightPlan:
    board: tuple
    oop_weights: tuple
    ip_weights: tuple
    compatible_pair_raw_products: tuple
    global_blocker_normalizer: Fraction
    exact_pair_priors: tuple
    ordered_runouts_per_pair: int
    physical_world_forecast: int
    scope: str


def _weights(values, label):
    if type(values) is not tuple or len(values) != 2:
        raise ValueError(f"{label} must be a two-tuple for the fixed hand support")
    result = []
    for value in values:
        if type(value) is int:
            fraction = Fraction(value, 1)
        elif type(value) is Fraction:
            fraction = value
        else:
            raise ValueError(f"{label} entries must be exact integers or Fractions")
        if (fraction <= 0 or fraction.numerator.bit_length() > MAX_COMPONENT_BITS or
                fraction.denominator.bit_length() > MAX_COMPONENT_BITS):
            raise ValueError(f"{label} entries must be positive and within the bit bound")
        result.append(fraction)
    return tuple(result)


def plan_weights(oop_weights, ip_weights):
    """Plan exact positive weights over the literal two-hand supports only."""
    oop = _weights(oop_weights, "OOP weights")
    ip = _weights(ip_weights, "IP weights")
    pairs = []
    for i, oop_hand in enumerate(OOP_HANDS):
        for j, ip_hand in enumerate(IP_HANDS):
            if set((oop_hand[:2], oop_hand[2:])) & set((ip_hand[:2], ip_hand[2:])):
                continue
            pairs.append((oop_hand, ip_hand, oop[i] * ip[j]))
    normalizer = sum((row[2] for row in pairs), Fraction())
    if normalizer <= 0:
        raise ValueError("Fixed ranges have no compatible private pair")
    priors = tuple((oop_hand, ip_hand, raw / normalizer)
                   for oop_hand, ip_hand, raw in pairs)
    # Preserve the frozen candidate/partition integer envelope before any
    # physical preparation. Every class mass is a subset of the joint rows;
    # its denominator divides this common denominator and its value is <=1.
    common_world_denominator = lcm(*(
        (prior / RUNOUTS_PER_PAIR).denominator for _, _, prior in priors))
    if common_world_denominator.bit_length() > MAX_CLASS_MASS_BITS:
        raise ValueError("Derived joint world masses exceed the existing class bit bound")
    worlds = len(pairs) * RUNOUTS_PER_PAIR
    return ReweightPlan(BOARD, oop, ip, tuple(pairs), normalizer, priors,
                        RUNOUTS_PER_PAIR, worlds,
                        "Planning only: no quotient, ranking, tree, policy, or solver certification.")
