"""Rank-free admission plan for a future three-class JJ/KK count source.

This module validates literal query shape and forecasts named work only. It
does not locate a compiler, resolve a binary, enumerate boards, or authenticate
physical counts.
"""
from dataclasses import dataclass
from itertools import combinations

from pokerlab.cards import DECK, SUITS
from pokerlab.preflop_full_board_equity import (
    BOARDS_PER_PAIR,
    MAX_BOARD_EVALUATIONS,
    MAX_CANDIDATE_PAIRS,
    MAX_COMPATIBLE_PAIRS,
    MAX_CATEGORICAL_ROWS,
    MAX_HANDS_PER_PLAYER,
    MAX_RANK_CALLS,
)
from pokerlab import preflop_covered_equity as covered
from scripts import preflop_five_count_reference as reference
from scripts import validate_preflop_five_reference as five


_BENCHMARK_ID = "preflop-jj-kk-basis-plan-v1"
_REFERENCE_PROTOCOL = "PREFLOP_FIVE_REFERENCE_V2"
_FIXED_PAIR_QUERIES = (
    ("JdJs", "KdKs"),
    ("JdJs", "KcKd"),
    ("JdJs", "KcKh"),
)
_AGGREGATE_CAP_VERSION = "preflop-jj-kk-basis-admission-v1"
_MAX_COUNT_REQUESTS = 2
_MAX_AGGREGATE_REFERENCE_BOARDS = 10_273_824
_MAX_AGGREGATE_REFERENCE_SEVEN_CALLS = 20_547_648
_MAX_AGGREGATE_REFERENCE_FIVE_CALLS = 431_500_608
_MAX_AGGREGATE_NATIVE_BOARDS = 10_273_824
_MAX_AGGREGATE_NATIVE_RANK_CALLS = 20_547_648

_EXPECTED_SHARED_SUITS = (2, 1, 0)
_EXPECTED_REFERENCE_CAPS = {
    "pairs": 4,
    "boards": 6_849_216,
    "seven_card_rank_calls": 13_698_432,
    "five_card_rank_calls": 287_667_072,
}
_EXPECTED_AGGREGATE_CAPS = {
    "requests": 2,
    "five_card_conformance_tuples": 2_598_960,
    "reference_boards": 10_273_824,
    "reference_seven": 20_547_648,
    "reference_five": 431_500_608,
    "native_boards": 10_273_824,
    "native_seven": 20_547_648,
}


def expected_request():
    """Return a fresh copy of the fixed request; globals cannot redefine it."""
    return {
        "schema_version": 1,
        "benchmark_id": _BENCHMARK_ID,
        "reference_protocol": _REFERENCE_PROTOCOL,
        "pairs": [{"sb_hand": sb, "bb_hand": bb} for sb, bb in _FIXED_PAIR_QUERIES],
    }


# Convenience example only. Admission compares against immutable constants via
# expected_request(), never against this caller-mutable object.
REQUEST = expected_request()


def _typed_equal(left, right):
    """Equality that does not let bool/int or other Python aliases pass."""
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return (left.keys() == right.keys()
                and all(type(key) is str and _typed_equal(left[key], right[key])
                        for key in left))
    if type(left) is list:
        return len(left) == len(right) and all(_typed_equal(a, b) for a, b in zip(left, right))
    return left == right


def _live_caps():
    """Read current project-owned caps and reject silent cap drift."""
    reference_caps = {
        "pairs": reference.MAX_PAIRS,
        "boards": reference.MAX_BOARDS,
        "seven_card_rank_calls": reference.MAX_SEVEN_CALLS,
        "five_card_rank_calls": reference.MAX_FIVE_CALLS,
    }
    if not _typed_equal(reference_caps, _EXPECTED_REFERENCE_CAPS):
        raise ValueError("Generic reference caps changed from the existing bounded contract")
    live_other_caps = {
        "boards_per_pair": BOARDS_PER_PAIR,
        "compatible_pairs": MAX_COMPATIBLE_PAIRS,
        "board_evaluations": MAX_BOARD_EVALUATIONS,
        "rank_calls": MAX_RANK_CALLS,
        "categorical_rows": MAX_CATEGORICAL_ROWS,
        "candidate_pairs": MAX_CANDIDATE_PAIRS,
        "ordinary_hands": MAX_HANDS_PER_PLAYER,
        "covered_pairs": covered.MAX_PAIRS,
        "covered_candidates": covered.MAX_CANDIDATES,
        "covered_hands": covered.MAX_HANDS,
    }
    expected_other_caps = {
        "boards_per_pair": 1_712_304,
        "compatible_pairs": 4,
        "board_evaluations": 6_849_216,
        "rank_calls": 13_698_432,
        "categorical_rows": 12,
        "candidate_pairs": 4_096,
        "ordinary_hands": 1_326,
        "covered_pairs": 128,
        "covered_candidates": 4_096,
        "covered_hands": 128,
    }
    if not _typed_equal(live_other_caps, expected_other_caps):
        raise ValueError("Existing physical/pooling caps changed; plan needs review")
    if (five.FIVE_TOTAL != 2_598_960 or five.FIVE_BYTES != 15_593_760):
        raise ValueError("Exhaustive five-card conformance dimensions changed")
    return reference_caps


def _aggregate_caps():
    values = {
        "requests": _MAX_COUNT_REQUESTS,
        "five_card_conformance_tuples": five.FIVE_TOTAL,
        "reference_boards": _MAX_AGGREGATE_REFERENCE_BOARDS,
        "reference_seven": _MAX_AGGREGATE_REFERENCE_SEVEN_CALLS,
        "reference_five": _MAX_AGGREGATE_REFERENCE_FIVE_CALLS,
        "native_boards": _MAX_AGGREGATE_NATIVE_BOARDS,
        "native_seven": _MAX_AGGREGATE_NATIVE_RANK_CALLS,
    }
    if not _typed_equal(values, _EXPECTED_AGGREGATE_CAPS):
        raise ValueError("Versioned aggregate named-work caps changed")
    return values


def _validate_literal_pairs(pairs):
    if type(pairs) is not list or len(pairs) != 3:
        raise ValueError("Exactly three canonical JJ/KK pair queries are required")
    card_order = {card: index for index, card in enumerate(DECK)}
    observed = []
    shared = []
    for row in pairs:
        if type(row) is not dict or set(row) != {"sb_hand", "bb_hand"}:
            raise ValueError("Each query must contain only ordered SB and BB hands")
        sb, bb = row["sb_hand"], row["bb_hand"]
        if type(sb) is not str or type(bb) is not str or len(sb) != 4 or len(bb) != 4:
            raise ValueError("Hands must be exact four-character card-token strings")
        sb_cards, bb_cards = (sb[:2], sb[2:]), (bb[:2], bb[2:])
        if any(card not in card_order for card in (*sb_cards, *bb_cards)):
            raise ValueError("Query contains a card outside the project deck")
        if sb_cards[0] == sb_cards[1] or bb_cards[0] == bb_cards[1]:
            raise ValueError("A private hand cannot repeat a card")
        if tuple(sorted(sb_cards, key=card_order.__getitem__)) != sb_cards:
            raise ValueError("SB hand card order is not canonical")
        if tuple(sorted(bb_cards, key=card_order.__getitem__)) != bb_cards:
            raise ValueError("BB hand card order is not canonical")
        if set(sb_cards) & set(bb_cards):
            raise ValueError("Private pair query contains a blocker collision")
        if tuple(card[0] for card in sb_cards) != ("J", "J"):
            raise ValueError("Every SB query must be a pocket-jack hand")
        if tuple(card[0] for card in bb_cards) != ("K", "K"):
            raise ValueError("Every BB query must be a pocket-king hand")
        observed.append((sb, bb))
        shared.append(len({card[1] for card in sb_cards} & {card[1] for card in bb_cards}))
    if tuple(shared) != _EXPECTED_SHARED_SUITS:
        raise ValueError("Queries must cover two-, one-, then zero-shared-suit classes")
    if tuple(observed) != _FIXED_PAIR_QUERIES:
        raise ValueError("Ordered canonical JJ/KK query identities changed")
    return tuple(observed), tuple(shared)


def _mixed_pool_forecast():
    sb_hands = tuple(tuple(sorted(hand, key=DECK.index))
                     for rank in ("A", "Q", "J")
                     for hand in combinations(tuple(rank + suit for suit in SUITS), 2))
    bb_hands = tuple(tuple(sorted(hand, key=DECK.index))
                     for hand in combinations(tuple("K" + suit for suit in SUITS), 2))
    compatible = sum(set(sb).isdisjoint(bb) for sb in sb_hands for bb in bb_hands)
    if (len(sb_hands), len(bb_hands), compatible) != (18, 6, 108):
        raise ValueError("Rank-free mixed-range hand/pair forecast changed")
    if compatible > covered.MAX_PAIRS:
        raise ValueError("Future covered-pair forecast exceeds the existing 128-pair cap")
    return {
        "sb_hands": len(sb_hands),
        "bb_hands": len(bb_hands),
        "compatible_pairs": compatible,
        "maximum_positive_sign_rows": 3 * compatible,
        "covered_pair_cap": covered.MAX_PAIRS,
        "status": "forecast-only; no pair counts/equities or game certificate",
    }


@dataclass(frozen=True, slots=True)
class JJKKBasisPlan:
    benchmark_id: str
    reference_protocol: str
    ordered_pairs: tuple
    shared_suits_by_pair: tuple
    five_card_conformance: tuple
    best_five_reference: tuple
    native_seven_card_recount: tuple
    aggregate_admission: tuple
    source_basis_prerequisite: tuple
    future_mixed_pool: tuple
    provenance: tuple

    def to_record(self):
        """Return a fresh JSON-safe planning record with no count claims."""
        return {
            "status": "admitted-plan-only",
            "benchmark_id": self.benchmark_id,
            "reference_protocol": self.reference_protocol,
            "ordered_pairs": [list(pair) for pair in self.ordered_pairs],
            "shared_suits_by_pair": list(self.shared_suits_by_pair),
            "five_card_conformance": dict(self.five_card_conformance),
            "best_five_reference": dict(self.best_five_reference),
            "native_seven_card_recount": dict(self.native_seven_card_recount),
            "aggregate_admission": dict(self.aggregate_admission),
            "source_basis_prerequisite": list(self.source_basis_prerequisite),
            "future_mixed_pool": dict(self.future_mixed_pool),
            "provenance": dict(self.provenance),
        }


def admit_plan(request=None):
    """Validate the whole fixed query and return a fresh rank-free forecast.

    No source report, build manifest, compiler or executable is opened here.
    A future count runner must call this before any such lookup.
    """
    expected = expected_request()
    supplied = expected if request is None else request
    # Exact full-request comparison is the first operation on caller data.
    # This rejects omitted, extra, reordered, noncanonical and bool/int-alias
    # fields before project binary or source-report lookup can occur.
    if not _typed_equal(supplied, expected):
        raise ValueError("JJ/KK request differs from the complete frozen literal query")
    pairs, shared = _validate_literal_pairs(supplied["pairs"])
    caps = _live_caps()
    aggregate_caps = _aggregate_caps()
    pair_count = len(pairs)
    boards = pair_count * BOARDS_PER_PAIR
    reference_seven = 2 * boards
    reference_five = 42 * boards
    native_seven = 2 * boards
    # The existing all-five conformance helper also recounts the three-pair
    # AA/KK basis with both counters. Admit that separate request together
    # with the new JJ/KK count, keeping each request under its ordinary cap.
    aggregate_boards = 2 * boards
    aggregate_seven = 2 * reference_seven
    aggregate_five = 2 * reference_five
    if (pair_count > caps["pairs"] or boards > caps["boards"]
            or reference_seven > caps["seven_card_rank_calls"]
            or reference_five > caps["five_card_rank_calls"]
            or boards > MAX_BOARD_EVALUATIONS or native_seven > MAX_RANK_CALLS
            or _MAX_COUNT_REQUESTS != aggregate_caps["requests"]
            or aggregate_boards > aggregate_caps["reference_boards"]
            or aggregate_seven > aggregate_caps["reference_seven"]
            or aggregate_five > aggregate_caps["reference_five"]
            or aggregate_boards > aggregate_caps["native_boards"]
            or aggregate_seven > aggregate_caps["native_seven"]):
        raise ValueError("Complete three-pair query exceeds an unchanged existing cap")
    future_pool = _mixed_pool_forecast()
    return JJKKBasisPlan(
        benchmark_id=supplied["benchmark_id"],
        reference_protocol=supplied["reference_protocol"],
        ordered_pairs=pairs,
        shared_suits_by_pair=shared,
        five_card_conformance=(
            ("rank_tuples", five.FIVE_TOTAL),
            ("tuple_width_bytes", 6),
            ("dump_bytes", five.FIVE_BYTES),
            ("required_mismatches", 0),
        ),
        best_five_reference=(
            ("pairs", pair_count),
            ("boards", boards),
            ("seven_card_rank_calls", reference_seven),
            ("five_card_subset_calls", reference_five),
            ("per_pair_board_cap", BOARDS_PER_PAIR),
            ("request_pair_cap", caps["pairs"]),
            ("request_board_cap", caps["boards"]),
            ("request_seven_card_rank_cap", caps["seven_card_rank_calls"]),
            ("request_five_card_subset_cap", caps["five_card_rank_calls"]),
        ),
        native_seven_card_recount=(
            ("pairs", pair_count),
            ("board_evaluations", boards),
            ("rank_calls", native_seven),
            ("compatible_pair_cap", MAX_COMPATIBLE_PAIRS),
            ("board_evaluation_cap", MAX_BOARD_EVALUATIONS),
            ("rank_call_cap", MAX_RANK_CALLS),
        ),
        aggregate_admission=(
            ("budget_version", _AGGREGATE_CAP_VERSION),
            ("reference_count_requests", _MAX_COUNT_REQUESTS),
            ("five_card_conformance_tuples", aggregate_caps["five_card_conformance_tuples"]),
            ("reference_board_evaluations", aggregate_boards),
            ("reference_seven_card_rank_calls", aggregate_seven),
            ("reference_five_card_subset_calls", aggregate_five),
            ("native_board_evaluations", aggregate_boards),
            ("native_seven_card_rank_calls", aggregate_seven),
            ("cap_reference_count_requests", aggregate_caps["requests"]),
            ("cap_reference_board_evaluations", aggregate_caps["reference_boards"]),
            ("cap_reference_seven_card_rank_calls", aggregate_caps["reference_seven"]),
            ("cap_reference_five_card_subset_calls", aggregate_caps["reference_five"]),
            ("cap_native_board_evaluations", aggregate_caps["native_boards"]),
            ("cap_native_seven_card_rank_calls", aggregate_caps["native_seven"]),
            ("scope", "named count stages only; excludes CPU, memory and runtime"),
        ),
        source_basis_prerequisite=(
            "authenticate existing AA/KK and QQ/KK published count bases separately before counting",
            "current-build exhaustive conformance includes its AA/KK three-pair calibration query",
            "that AA/KK stage is calibration, not a new AA/KK source-count claim",
            "no extra AA/KK query beyond conformance is included",
        ),
        future_mixed_pool=tuple(future_pool.items()),
        provenance=(
            ("candidate_only", True),
            ("independently_authenticated", False),
            ("counts_generated", False),
            ("equities_claimed", False),
            ("solver_or_training_claimed", False),
            ("work_scope", "named reference/conformance/native count units only; not CPU, memory or runtime"),
        ),
    )
