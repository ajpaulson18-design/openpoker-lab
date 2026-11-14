"""Independent exact own-hand response audit for the fixed AA/AK versus KK game.

This module consumes only saved, authenticated physical count rows. It does not
build a betting tree, invoke the candidate, or call a solver/ranker.
"""
from __future__ import annotations

import re
from copy import deepcopy
from fractions import Fraction
from itertools import combinations, product

from scripts import preflop_aa_ak_transport_validation as sources
from scripts import preflop_mixed_pure_response as rules


SUITS = "cdhs"
RANKS = "23456789TJQKA"
BOARD_COUNT = 1_712_304
MAX_ROWS = 112
MAX_STRING = 256
MAX_FRACTION_BITS = 4096
_RATIONAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:/(?:[1-9][0-9]*))?\Z")

_AA_SOURCES = {0: ("AdAs", "KcKh"), 1: ("AdAs", "KcKd"), 2: ("AdAs", "KdKs")}
_AKS_SOURCE = ("AcKc", "KdKh")
_AKO_SOURCES = {0: ("AdKc", "KhKs"), 1: ("AdKc", "KdKh")}


def _hand(cards):
    """Return a lexical two-card label, rejecting cards outside the deck."""
    deck = {rank + suit for rank in RANKS for suit in SUITS}
    if (type(cards) not in (tuple, list) or len(cards) != 2
            or any(type(card) is not str or card not in deck for card in cards)
            or cards[0] == cards[1]):
        raise ValueError("Invalid two-card hand")
    return "".join(sorted(cards))


def _literal_support():
    aces = tuple("A" + suit for suit in SUITS)
    kings = tuple("K" + suit for suit in SUITS)
    sb_hands = tuple(sorted({"".join(sorted(pair)) for pair in combinations(aces, 2)} |
                            {"".join(sorted((ace, king))) for ace in aces for king in kings}))
    bb_hands = tuple(sorted("".join(sorted(pair)) for pair in combinations(kings, 2)))
    pairs = []
    type_counts = {"AA": 0, "AKs": 0, "AKo": 0}
    for sb in sb_hands:
        for bb in bb_hands:
            sb_cards = (sb[:2], sb[2:])
            bb_cards = (bb[:2], bb[2:])
            if set(sb_cards) & set(bb_cards):
                continue
            kind = _hand_type(sb)
            type_counts[kind] += 1
            pairs.append({"sb_hand": sb, "bb_hand": bb, "type": kind,
                          "prior": Fraction(1, 84)})
    if (len(sb_hands), len(bb_hands), len(pairs), type_counts) != (
            22, 6, 84, {"AA": 36, "AKs": 12, "AKo": 36}):
        raise ValueError("Literal physical support census changed")
    if sum((pair["prior"] for pair in pairs), Fraction()) != 1:
        raise AssertionError("Literal global pair prior is not normalized")
    return sb_hands, bb_hands, pairs, type_counts


def _hand_type(hand):
    ranks = (hand[0], hand[2])
    if ranks == ("A", "A"):
        return "AA"
    if set(ranks) != {"A", "K"}:
        raise ValueError("Unexpected SB hand rank")
    return "AKs" if hand[1] == hand[3] else "AKo"


def _pair_source(pair):
    sb, bb, kind = pair["sb_hand"], pair["bb_hand"], pair["type"]
    overlap = len({sb[1], sb[3]} & {bb[1], bb[3]})
    if kind == "AA":
        return _AA_SOURCES[overlap]
    if kind == "AKs":
        if overlap != 0:
            raise ValueError("Suited AK/KK source overlap changed")
        return _AKS_SOURCE
    if overlap not in _AKO_SOURCES:
        raise ValueError("Offsuit AK/KK source overlap changed")
    return _AKO_SOURCES[overlap]


def _build_game(source_rows=None):
    """Build the fixed literal payoff game from six saved source rows.

    `source_rows` is a private test seam mapping source hand-pairs to
    (wins, ties, losses, boards, artifact_sha256). Normal callers authenticate
    the six rows through the independent saved-publication reader.
    """
    sb_hands, bb_hands, pairs, type_counts = _literal_support()
    if source_rows is None:
        source_rows = sources._source_rows()
    if type(source_rows) is not dict or len(source_rows) != 6:
        raise ValueError("Exactly six authenticated physical source rows are required")
    expected_sources = set(_AA_SOURCES.values()) | {_AKS_SOURCE} | set(_AKO_SOURCES.values())
    if set(source_rows) != expected_sources:
        raise ValueError("Authenticated physical source identities differ")

    enriched = []
    for pair in pairs:
        source_key = _pair_source(pair)
        source = source_rows.get(source_key)
        if (type(source) not in (tuple, list) or len(source) != 5
                or any(type(value) is not int or value < 0 for value in source[:4])
                or source[3] != BOARD_COUNT or sum(source[:3]) != BOARD_COUNT
                or type(source[4]) is not str or len(source[4]) != 64
                or any(char not in "0123456789abcdef" for char in source[4])):
            raise ValueError("Malformed or unauthenticated physical source row")
        enriched.append({**pair, "counts": tuple(source[:4]),
                         "showdown_mean": Fraction(source[0] - source[2], source[3]),
                         "source_identity_sha256": source[4]})
    return {"sb_hands": sb_hands, "bb_hands": bb_hands,
            "pairs": tuple(enriched),
            "pair_map": {(p["sb_hand"], p["bb_hand"]): p for p in enriched},
            "type_pair_counts": type_counts,
            "raw_compatible_pair_weight_normalizer": Fraction(84)}


def _expected_infos(game):
    expected = {}
    for player, hands in ((0, game["sb_hands"]), (1, game["bb_hands"])):
        for hand in hands:
            for (owner, history), actions in rules.INFO_MENUS.items():
                if owner == player:
                    expected[(player, hand, history)] = actions
    if len(expected) != MAX_ROWS:
        raise AssertionError("Literal own-hand information census changed")
    return expected


def _fraction(value, label):
    if (type(value) is not str or not value or len(value) > MAX_STRING
            or _RATIONAL.fullmatch(value) is None):
        raise ValueError(f"{label} must be a bounded canonical rational string")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(f"Invalid {label}") from exc
    if (str(result) != value or result.numerator.bit_length() > MAX_FRACTION_BITS
            or result.denominator.bit_length() > MAX_FRACTION_BITS):
        raise ValueError(f"Noncanonical or oversized {label}")
    return result


def _policy(rows, game):
    if type(rows) is not list or len(rows) != MAX_ROWS:
        raise ValueError("Policy must contain exactly 112 own-hand information rows")
    expected = _expected_infos(game)
    parsed = {}
    for row in rows:
        if type(row) is not dict or set(row) != {
                "player", "hand", "history", "actions", "probabilities"}:
            raise ValueError("Unexpected or private-information-leaking policy fields")
        player, hand, history = row["player"], row["hand"], row["history"]
        if (type(player) is not int or player not in (0, 1)
                or type(hand) is not str or len(hand) != 4
                or type(history) is not list or len(history) > 4
                or any(type(token) is not str or len(token) > 16 for token in history)):
            raise ValueError("Malformed own-hand/public-history information key")
        key = (player, hand, tuple(history))
        actions = expected.get(key)
        if actions is None or key in parsed:
            raise ValueError("Unknown or duplicate own-hand information row")
        if type(row["actions"]) is not list or row["actions"] != list(actions):
            raise ValueError("Policy action menu differs from literal legal menu")
        probs = row["probabilities"]
        if type(probs) is not list or len(probs) != len(actions):
            raise ValueError("Policy probability row differs from legal menu")
        exact = tuple(_fraction(item, "policy probability") for item in probs)
        if any(value < 0 or value > 1 for value in exact) or sum(exact, Fraction()) != 1:
            raise ValueError("Policy probabilities must be in [0,1] and sum exactly to one")
        parsed[key] = dict(zip(actions, exact))
    if set(parsed) != set(expected):
        raise ValueError("Policy omits legal off-path own-hand information rows")
    return parsed


def verify_policy(policies, claimed_value=None):
    """Compute exact profile and legal own-hand BR values for a full policy.

    Each policy row contains only player, own hand, public history, the exact
    legal action menu, and canonical rational-string probabilities.
    """
    # Parse every bounded row before authenticating sources, so malformed input
    # cannot trigger even the saved-report verification path.
    shell_sb, shell_bb, shell_pairs, shell_types = _literal_support()
    shell = {"sb_hands": shell_sb, "bb_hands": shell_bb, "pairs": shell_pairs,
             "type_pair_counts": shell_types}
    parsed = _policy(policies, shell)
    claim = None if claimed_value is None else _fraction(claimed_value, "claimed profile value")

    game = _build_game()
    profile = sum((pair["prior"] * rules._terminal_value(parsed, pair)
                   for pair in game["pairs"]), Fraction())
    sb_br, sb_rows, sb_count = rules._best_response(parsed, game, 0)
    bb_br, bb_rows, bb_count = rules._best_response(parsed, game, 1)
    sb_gain, bb_gain = sb_br - profile, bb_br + profile
    if sb_gain < 0 or bb_gain < 0:
        raise ArithmeticError("A legal pure response underperformed the supplied profile")
    nash_conv = sb_gain + bb_gain
    claim_matches = claim is None or claim == profile
    exact_mutual = nash_conv == 0 and claim_matches
    return {
        "status": "passed" if exact_mutual else "failed",
        "oracle": "independent-aa-ak-kk-preflop-pure-response-v1",
        "physical_private_pair_count": 84,
        "sb_private_hand_count": 22,
        "bb_private_hand_count": 6,
        "type_pair_counts": dict(game["type_pair_counts"]),
        "information_set_count": len(parsed),
        "pure_response_policies_enumerated": {
            "sb": sb_count, "bb": bb_count, "total": sb_count + bb_count},
        "profile_value_sb_fraction": str(profile),
        "sb_best_response_own_utility_fraction": str(sb_br),
        "bb_best_response_own_utility_fraction": str(bb_br),
        "sb_best_response_gain_fraction": str(sb_gain),
        "bb_best_response_gain_fraction": str(bb_gain),
        "nash_conv_fraction": str(nash_conv),
        "claimed_value_fraction": None if claim is None else str(claim),
        "claimed_profile_value_matches": claim_matches,
        "exact_mutual_response_verified": exact_mutual,
        "sb_by_hand": sb_rows,
        "bb_by_hand": bb_rows,
        "source_rows_authenticated": 6,
        "source_basis_pins": deepcopy(sources.SOURCE_PINS),
        "raw_compatible_pair_weight_normalizer": "84",
        "pair_priors": [{"sb_hand": pair["sb_hand"], "bb_hand": pair["bb_hand"],
                         "hand_type": pair["type"], "prior_fraction": str(pair["prior"]),
                         "showdown_mean_fraction": str(pair["showdown_mean"]),
                         "source_counts": dict(zip(("wins", "ties", "losses", "boards"),
                                                   pair["counts"]))}
                        for pair in game["pairs"]],
        "scope": "exact finite preflop betting plus hidden full-board checkdown; not unrestricted NLHE",
    }
