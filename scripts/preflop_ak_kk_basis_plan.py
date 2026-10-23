"""Rank-free full-request plan for three blocker-sensitive AK/KK sources.

This admits a future experiment, not count provenance. No executable, compiler,
saved source, board enumeration, ranker, tree, LP or trainer is used here.
"""
from fractions import Fraction
from itertools import combinations, permutations

from pokerlab import preflop_covered_equity as covered
from pokerlab import preflop_full_board_equity as ordinary
from scripts import preflop_five_count_reference as reference
from scripts import validate_preflop_five_reference as five

SUITS = "cdhs"
DECK = tuple(rank + suit for rank in "23456789TJQKA" for suit in SUITS)
QUERIES = (
    ("aa-calibration", "AdAs", "KdKs,KcKd,KcKh", 3),
    ("ak-suited", "KcAc", "KdKh", 1),
    ("ak-offsuit", "KcAd", "KdKh,KhKs", 2),
)


def expected_request():
    return {"schema_version": 1, "benchmark_id": "preflop-ak-kk-basis-plan-v1",
            "reference_protocol": "PREFLOP_FIVE_REFERENCE_V2",
            "count_requests": [{"id": name, "sb_range": sb, "bb_range": bb,
                                "compatible_pairs": count}
                               for name, sb, bb, count in QUERIES]}


def _typed_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(
            _typed_equal(left[key], value) for key, value in right.items())
    if type(left) is list:
        return len(left) == len(right) and all(_typed_equal(a, b) for a, b in zip(left, right))
    return left == right


def _caps():
    actual = {"reference_pairs": reference.MAX_PAIRS, "reference_boards": reference.MAX_BOARDS,
              "reference_seven": reference.MAX_SEVEN_CALLS, "reference_five": reference.MAX_FIVE_CALLS,
              "ordinary_pairs": ordinary.MAX_COMPATIBLE_PAIRS,
              "ordinary_boards": ordinary.MAX_BOARD_EVALUATIONS,
              "ordinary_ranks": ordinary.MAX_RANK_CALLS,
              "boards_per_pair": ordinary.BOARDS_PER_PAIR,
              "covered_pairs": covered.MAX_PAIRS, "covered_hands": covered.MAX_HANDS,
              "covered_candidates": covered.MAX_CANDIDATES, "covered_sources": covered.MAX_SOURCES,
              "five_tuples": five.FIVE_TOTAL, "five_bytes": five.FIVE_BYTES}
    expected = {"reference_pairs": 4, "reference_boards": 6_849_216,
                "reference_seven": 13_698_432, "reference_five": 287_667_072,
                "ordinary_pairs": 4, "ordinary_boards": 6_849_216,
                "ordinary_ranks": 13_698_432, "boards_per_pair": 1_712_304,
                "covered_pairs": 128, "covered_hands": 128,
                "covered_candidates": 4096, "covered_sources": 32,
                "five_tuples": 2_598_960, "five_bytes": 15_593_760}
    if not _typed_equal(actual, expected):
        raise ValueError("Existing count, conformance or prepared-pool caps changed")
    return actual


def _hand(cards):
    return tuple(sorted(cards, key=DECK.index))


def _orbit(sb, bb):
    forms = []
    for images in permutations(SUITS):
        mapping = dict(zip(SUITS, images))
        forms.append(tuple("".join(_hand(card[0] + mapping[card[1]] for card in hand))
                           for hand in (sb, bb)))
    return min(forms)


def _pool_forecast():
    aa = tuple(_hand(pair) for pair in combinations(tuple("A" + suit for suit in SUITS), 2))
    kk = tuple(_hand(pair) for pair in combinations(tuple("K" + suit for suit in SUITS), 2))
    ak = tuple(_hand(("A" + a, "K" + k)) for a in SUITS for k in SUITS)
    counts = {"AA": 0, "AKs": 0, "AKo": 0}
    orbits = {}
    for sb in (*aa, *ak):
        kind = "AA" if sb[0][0] == sb[1][0] else ("AKs" if sb[0][1] == sb[1][1] else "AKo")
        for bb in kk:
            if not set(sb).isdisjoint(bb):
                continue
            counts[kind] += 1
            key = (kind, *_orbit(sb, bb))
            orbits[key] = orbits.get(key, 0) + 1
    if counts != {"AA": 36, "AKs": 12, "AKo": 36} or len(orbits) != 6:
        raise ValueError("Literal blocker-sensitive support or suit-orbit census changed")
    total = sum(counts.values())
    if total > covered.MAX_PAIRS:
        raise ValueError("Proposed 84-pair pool exceeds its unchanged cap")
    return {"sb_hands": 22, "bb_hands": 6, "raw_candidates": 132,
            "compatible_pairs": total, "blocked_candidates": 48,
            "type_pair_counts": counts, "exact_prior_per_pair": "1/84",
            "type_prior_masses": {key: str(Fraction(value, total)) for key, value in counts.items()},
            "source_suit_orbits": [{"type": key[0], "sb_hand": key[1], "bb_hand": key[2],
                                   "physical_members": value} for key, value in sorted(orbits.items())],
            "all_aa_qq_jj_plus_ak_pairs": 156,
            "all_four_group_support_exceeds_existing_pair_cap": True}


def admit_plan(request=None):
    request = expected_request() if request is None else request
    if not _typed_equal(request, expected_request()):
        raise ValueError("Requires the entire literal AK/KK count schedule")
    caps = _caps()
    requests = []
    for name, sb, bb, expected_count in QUERIES:
        pairs, admission = reference.pair_admission(sb, bb)
        if len(pairs) != expected_count or admission["compatible_pairs"] != expected_count:
            raise ValueError("Ordinary count request changed its physical pair census")
        requests.append({"id": name, "sb_range": sb, "bb_range": bb,
                         "ordered_pairs": [["".join(a), "".join(b)] for a, b in pairs],
                         "admission": admission})
    total_pairs = sum(len(row["ordered_pairs"]) for row in requests)
    boards = total_pairs * 1_712_304
    # One all-five dump, then AA/reference/native, AKs/reference/native and
    # AKo/reference/native. Every ordinary request is admitted independently.
    aggregate = {"version": "preflop-ak-kk-complete-count-work-v1",
                 "numerical_subprocesses": 7, "reference_requests": 3, "native_requests": 3,
                 "five_card_conformance_tuples": 2_598_960,
                 "five_card_dump_bytes": 15_593_760,
                 "reference_boards": boards, "reference_seven_calls": 2 * boards,
                 "reference_five_calls": 42 * boards,
                 "native_boards": boards, "native_seven_calls": 2 * boards}
    if (total_pairs, boards, aggregate["reference_five_calls"]) != (6, 10_273_824, 431_500_608):
        raise ValueError("Complete named count-work schedule changed")
    return {"status": "admitted-plan-only", "request": expected_request(),
            "existing_caps": caps, "count_requests": requests, "aggregate": aggregate,
            "future_pool_forecast": _pool_forecast(),
            "prerequisites": ["authenticate published AA/KK basis before counting",
                              "build unchanged project-owned counters in fresh external directories",
                              "complete current-build all-five and AA calibration before AK queries",
                              "retain all seven raw outputs/errors and source/build identities",
                              "independently authenticate counts before any transport or strategy use"],
            "counts_generated": False, "equities_claimed": False,
            "solver_or_training_claimed": False,
            "scope": "Named work and private-card census only; no physical counts, CPU, runtime or RSS guarantee"}
