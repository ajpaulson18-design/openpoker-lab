"""Strict planning-only admission for one fixed second-flop fixture.

This module computes exact blocker-conditioned pair priors. It deliberately
does not prepare physical worlds, rank hands, construct a tree, or assert any
second-board class/tree equivalence.
"""

from dataclasses import dataclass
from fractions import Fraction


BOARD = ("7c", "8d", "9h")
OOP_RANGES = (("AsAd", Fraction(1)), ("QsQd", Fraction(1, 2)))
IP_RANGES = (("AsKh", Fraction(1, 4)), ("KsKd", Fraction(1)))
SCOPE = "fixed-board-range-plan-only"
RUNOUTS_PER_PAIR = 45 * 44
DECK = tuple(rank + suit for rank in "23456789TJQKA" for suit in "cdhs")


@dataclass(frozen=True, slots=True)
class SecondBoardPlan:
    board: tuple[str, ...]
    oop_ranges: tuple[tuple[str, Fraction], ...]
    ip_ranges: tuple[tuple[str, Fraction], ...]
    compatible_pair_raw_products: tuple[tuple[str, str, Fraction], ...]
    global_blocker_normalizer: Fraction
    exact_pair_priors: tuple[tuple[str, str, Fraction], ...]
    canonical_pair_identities: tuple[tuple[str, str, str, str], ...]
    ordered_runouts_per_pair: int
    distinct_turn_card_forecast: int
    physical_world_forecast: int
    scope: str


def _canonical_hand(label: str) -> str:
    cards = (label[:2], label[2:])
    # physical._hand_rows uses lexical ordering for its hand identity key.
    return "".join(sorted(cards))


def _expected_plan() -> SecondBoardPlan:
    board_cards = set(BOARD)
    oop_cards = {label: (label[:2], label[2:]) for label, _ in OOP_RANGES}
    ip_cards = {label: (label[:2], label[2:]) for label, _ in IP_RANGES}
    oop_weights = dict(OOP_RANGES)
    ip_weights = dict(IP_RANGES)
    products = []
    for oop_label, oop_hand in oop_cards.items():
        for ip_label, ip_hand in ip_cards.items():
            used = set(oop_hand + ip_hand)
            if len(used) != 4 or used & board_cards:
                continue
            products.append((oop_label, ip_label,
                             oop_weights[oop_label] * ip_weights[ip_label]))
    normalizer = sum((row[2] for row in products), Fraction())
    priors = tuple((oop, ip, product / normalizer)
                   for oop, ip, product in products)
    identities = tuple((_canonical_hand(oop), _canonical_hand(ip), oop, ip)
                       for oop, ip, _ in products)
    turn_cards = set()
    for oop, ip, _ in products:
        private = set(oop_cards[oop] + ip_cards[ip])
        turn_cards.update(set(DECK) - board_cards - private)
    return SecondBoardPlan(
        board=BOARD,
        oop_ranges=OOP_RANGES,
        ip_ranges=IP_RANGES,
        compatible_pair_raw_products=tuple(products),
        global_blocker_normalizer=normalizer,
        exact_pair_priors=priors,
        canonical_pair_identities=identities,
        ordered_runouts_per_pair=RUNOUTS_PER_PAIR,
        distinct_turn_card_forecast=len(turn_cards),
        physical_world_forecast=len(products) * RUNOUTS_PER_PAIR,
        scope=SCOPE,
    )


def plan_second_board() -> SecondBoardPlan:
    """Return a fresh immutable plan for the one admitted fixture."""
    return _expected_plan()


def validate_plan(plan: object) -> SecondBoardPlan:
    """Reject every plan other than the exact, correctly typed fixture plan."""
    if type(plan) is not SecondBoardPlan:
        raise ValueError("Expected an exact SecondBoardPlan")
    expected = _expected_plan()
    # Check fixed container sizes before scanning any attacker-supplied rows.
    if (type(plan.board) is not tuple or len(plan.board) != 3
            or type(plan.oop_ranges) is not tuple or len(plan.oop_ranges) != 2
            or type(plan.ip_ranges) is not tuple or len(plan.ip_ranges) != 2
            or type(plan.compatible_pair_raw_products) is not tuple
            or len(plan.compatible_pair_raw_products) != 3
            or type(plan.exact_pair_priors) is not tuple or len(plan.exact_pair_priors) != 3
            or type(plan.canonical_pair_identities) is not tuple
            or len(plan.canonical_pair_identities) != 3):
        raise ValueError("Plan container lengths differ from the fixed fixture")
    # Exact field-type checks prevent bool/int and tuple/list equality aliases.
    if (type(plan.board) is not tuple
            or any(type(card) is not str for card in plan.board)
            or type(plan.oop_ranges) is not tuple
            or type(plan.ip_ranges) is not tuple
            or type(plan.compatible_pair_raw_products) is not tuple
            or type(plan.exact_pair_priors) is not tuple
            or type(plan.canonical_pair_identities) is not tuple
            or type(plan.global_blocker_normalizer) is not Fraction
            or type(plan.ordered_runouts_per_pair) is not int
            or type(plan.distinct_turn_card_forecast) is not int
            or type(plan.physical_world_forecast) is not int
            or type(plan.scope) is not str):
        raise ValueError("Plan fields have noncanonical types")
    for rows, width in ((plan.oop_ranges, 2), (plan.ip_ranges, 2),
                        (plan.compatible_pair_raw_products, 3),
                        (plan.exact_pair_priors, 3)):
        for row in rows:
            if (type(row) is not tuple or len(row) != width
                    or any(type(value) is not str for value in row[:-1])
                    or type(row[-1]) is not Fraction):
                raise ValueError("Plan contains a malformed typed row")
    for row in plan.canonical_pair_identities:
        if (type(row) is not tuple or len(row) != 4
                or any(type(value) is not str for value in row)):
            raise ValueError("Plan contains a malformed canonical identity row")
    if plan != expected:
        raise ValueError("Plan does not match the fixed second-board fixture")
    return plan


def admit_plan(plan: object | None = None) -> dict:
    """Validate and report exact support forecast plus existing hard caps.

    The returned capacity references are not a second-board tree/class census.
    """
    checked = validate_plan(plan_second_board() if plan is None else plan)
    from scripts import flop_multistreet_validation as physical
    from scripts import flop_public_classes_candidate as candidate

    pair_count = len(checked.compatible_pair_raw_products)
    if pair_count > physical.MAX_PAIRS or pair_count > candidate.MAX_PAIRS:
        raise ValueError("Fixed fixture exceeds a current pair cap")
    if (checked.physical_world_forecast > physical.MAX_WORLDS
            or checked.physical_world_forecast > candidate.MAX_WORLDS):
        raise ValueError("Fixed fixture exceeds a current world cap")
    if checked.distinct_turn_card_forecast > candidate.MAX_TURNS:
        raise ValueError("Fixed fixture exceeds the current candidate turn-card cap")

    return {
        "scope": checked.scope,
        "board": list(checked.board),
        "literal_ranges": {
            "oop": [[label, f"{weight.numerator}/{weight.denominator}"]
                    for label, weight in checked.oop_ranges],
            "ip": [[label, f"{weight.numerator}/{weight.denominator}"]
                   for label, weight in checked.ip_ranges],
        },
        "compatible_pair_count": len(checked.compatible_pair_raw_products),
        "compatible_pair_raw_products": [
            [oop, ip, f"{mass.numerator}/{mass.denominator}"]
            for oop, ip, mass in checked.compatible_pair_raw_products],
        "global_blocker_normalizer":
            f"{checked.global_blocker_normalizer.numerator}/"
            f"{checked.global_blocker_normalizer.denominator}",
        "exact_pair_priors": [
            [oop, ip, f"{mass.numerator}/{mass.denominator}"]
            for oop, ip, mass in checked.exact_pair_priors],
        "canonical_pair_identities": [list(row)
                                       for row in checked.canonical_pair_identities],
        "ordered_runouts_per_pair": checked.ordered_runouts_per_pair,
        "distinct_turn_card_forecast": checked.distinct_turn_card_forecast,
        "physical_world_forecast": checked.physical_world_forecast,
        "existing_limits_reference_only": {
            "physical_oracle": {
                "max_pairs": physical.MAX_PAIRS,
                "max_worlds": physical.MAX_WORLDS,
                "max_decisions": physical.MAX_DECISIONS,
                "max_public_states": physical.MAX_PUBLIC_STATES,
            },
            "candidate_partition": {
                "max_pairs": candidate.MAX_PAIRS,
                "max_worlds": candidate.MAX_WORLDS,
                "max_turns": candidate.MAX_TURNS,
            },
        },
        "class_tree_equivalence_claim": False,
    }
