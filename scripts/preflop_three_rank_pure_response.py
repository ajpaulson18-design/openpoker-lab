"""Independent exact pure-response audit for the fixed AA/QQ/JJ-versus-KK game.

The game ends in the existing finite preflop betting tree and then forces a
hidden full-board checkdown. This module consumes authenticated saved physical
count classes; it neither pools candidate rows nor builds a production tree.
"""
from fractions import Fraction
from itertools import combinations, product
import hashlib
import json
import math
from pathlib import Path
import re

from scripts import preflop_mixed_pure_response as rules
from scripts import preflop_three_rank_transport_validation as sources


SUITS = "cdhs"
RANKS = "23456789TJQKA"
BOARD_COUNT = 1_712_304
SB_WEIGHT = {"A": Fraction(1), "Q": Fraction(1, 2), "J": Fraction(1, 4)}
EXPECTED_NORMALIZER = Fraction(63)
MAX_POLICY_ROWS = 96
MAX_FRACTION_CHARS = 256
MAX_FRACTION_BITS = 4096
_FRACTION_TOKEN = re.compile(r"-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?\Z")
MAX_CANDIDATE_BYTES = 512 * 1024
REQUEST_SHA256 = "8bc482c3867f3e53e1bc6fc03723ae569f5401a66aeb5e1b86cf6bb12d5c9b25"
TRANSPORT_ARTIFACT_SHA256 = "fc98072bef74e1570a13db5c876d36226bcec1b3a2f7959c361872feb3abdbb9"
CERTIFICATE_ID = "preflop-three-rank-physical-exact-v1"
_CANDIDATE_KEYS = {"schema_version", "certificate_id", "status", "request",
                   "transport_artifact_sha256", "value_candidate_fraction", "policies",
                   "candidate_details", "artifact_sha256"}


def _json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate candidate JSON key")
        result[key] = value
    return result


def _json_constant(value):
    raise ValueError(f"Nonfinite JSON constant: {value}")


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _bounded_envelope(value):
    """Bound candidate details before source authentication or policy work."""
    nodes = 0
    edges = 0
    string_bytes = 0
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > 30_000 or depth > 24:
            raise ValueError("Candidate JSON exceeds structural limits")
        if type(item) is dict:
            if len(item) > 256:
                raise ValueError("Candidate object exceeds field limit")
            edges += len(item)
            if edges > 30_000:
                raise ValueError("Candidate edge count exceeds structural limit")
            for key, child in item.items():
                if type(key) is not str or len(key) > 4096:
                    raise ValueError("Candidate JSON key exceeds limit")
                string_bytes += len(key.encode("utf-8"))
                stack.append((child, depth + 1))
        elif type(item) is list:
            if len(item) > 10_000:
                raise ValueError("Candidate array exceeds item limit")
            edges += len(item)
            if edges > 30_000:
                raise ValueError("Candidate edge count exceeds structural limit")
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            if len(item) > MAX_CANDIDATE_BYTES:
                raise ValueError("Candidate string exceeds limit")
            string_bytes += len(item.encode("utf-8"))
        elif type(item) is int:
            if item.bit_length() > MAX_FRACTION_BITS:
                raise ValueError("Candidate integer exceeds exact bit limit")
        elif type(item) is float:
            if not math.isfinite(item):
                raise ValueError("Candidate contains nonfinite number")
        elif item is None or type(item) is bool:
            pass
        else:
            raise ValueError("Candidate contains unsupported JSON value")
        if string_bytes > MAX_CANDIDATE_BYTES:
            raise ValueError("Candidate string data exceeds byte limit")


def verify_candidate(candidate_or_path):
    """Authenticate a candidate envelope, then independently score its policy.

    This verifier never imports the candidate producer. File inputs are bounded,
    duplicate/nonfinite JSON is rejected, and bytes are checked again after the
    exact physical response audit.
    """
    saved_path = None
    saved_raw = None
    if isinstance(candidate_or_path, (str, Path)):
        saved_path = Path(candidate_or_path)
        if (saved_path.is_symlink() or not saved_path.is_file()
                or saved_path.stat().st_size > MAX_CANDIDATE_BYTES):
            raise ValueError("Candidate file is missing, symlinked, or oversized")
        with saved_path.open("rb") as stream:
            saved_raw = stream.read(MAX_CANDIDATE_BYTES + 1)
        if len(saved_raw) > MAX_CANDIDATE_BYTES:
            raise ValueError("Candidate file exceeds byte limit")
        try:
            candidate = json.loads(saved_raw, object_pairs_hook=_json_pairs,
                                   parse_constant=_json_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            raise ValueError("Candidate file is not bounded strict JSON") from exc
    else:
        candidate = candidate_or_path

    if type(candidate) is not dict or set(candidate) != _CANDIDATE_KEYS:
        raise ValueError("Candidate top-level schema differs")
    if (type(candidate["schema_version"]) is not int or candidate["schema_version"] != 1
            or type(candidate["certificate_id"]) is not str
            or candidate["certificate_id"] != CERTIFICATE_ID
            or type(candidate["status"]) is not str or candidate["status"] != "candidate-only"
            or type(candidate["transport_artifact_sha256"]) is not str
            or candidate["transport_artifact_sha256"] != TRANSPORT_ARTIFACT_SHA256):
        raise ValueError("Candidate identity or provenance pin differs")
    _bounded_envelope(candidate)
    if type(candidate["request"]) is not dict:
        raise ValueError("Candidate request is malformed")
    request_sha = hashlib.sha256(_canonical_json(candidate["request"])).hexdigest()
    if request_sha != REQUEST_SHA256:
        raise ValueError("Candidate request digest differs from the fixed request")
    if type(candidate["candidate_details"]) is not dict:
        raise ValueError("Candidate detail envelope is malformed")
    artifact = candidate["artifact_sha256"]
    if (type(artifact) is not str or len(artifact) != 64
            or any(char not in "0123456789abcdef" for char in artifact)
            or hashlib.sha256(_canonical_json({key: value for key, value in candidate.items()
                                               if key != "artifact_sha256"})).hexdigest() != artifact):
        raise ValueError("Candidate canonical artifact checksum differs")

    receipt = verify_policy(candidate["policies"], candidate["value_candidate_fraction"])
    result = {**receipt, "candidate_artifact_sha256": artifact,
              "candidate_request_sha256": request_sha,
              "status": "passed" if receipt["exact_mutual_response_verified"] else "failed"}
    if saved_path is not None:
        if saved_path.is_symlink() or not saved_path.is_file():
            raise ValueError("Candidate file path changed during verification")
        with saved_path.open("rb") as stream:
            final_raw = stream.read(MAX_CANDIDATE_BYTES + 1)
        if final_raw != saved_raw or len(final_raw) > MAX_CANDIDATE_BYTES:
            raise ValueError("Candidate file changed during verification")
    return result


def _canonical_hand(cards):
    order = {rank + suit: (rank_index, suit_index)
             for rank_index, rank in enumerate(RANKS)
             for suit_index, suit in enumerate(SUITS)}
    return "".join(sorted(cards, key=order.__getitem__))


def _source_classes():
    """Read only the independently authenticated nine saved physical rows."""
    rows_by_rank = sources._source_rows()
    result = {rank: {} for rank in "AQJ"}
    expected_source_sb = {"A": "AdAs", "Q": "QdQs", "J": "JdJs"}
    expected_bb = ("KdKs", "KcKd", "KcKh")
    for rank in "AQJ":
        rows = rows_by_rank[rank]
        if type(rows) is not dict or len(rows) != 3:
            raise ValueError("Authenticated source must contain three rows per rank")
        for bb_hand in expected_bb:
            row = rows.get((expected_source_sb[rank], bb_hand))
            if type(row) is not dict or set(row) != {"wins", "ties", "losses", "boards"}:
                raise ValueError("Authenticated source row identity or fields changed")
            counts = tuple(row[key] for key in ("wins", "ties", "losses", "boards"))
            if (any(type(value) is not int or value < 0 for value in counts)
                    or counts[3] != BOARD_COUNT or sum(counts[:3]) != BOARD_COUNT):
                raise ValueError("Authenticated source W/T/L count is malformed")
            overlap = len({expected_source_sb[rank][i] for i in (1, 3)} &
                          {bb_hand[i] for i in (1, 3)})
            if overlap not in (0, 1, 2) or overlap in result[rank]:
                raise ValueError("Source rows do not cover each suit-overlap class once")
            result[rank][overlap] = counts
        if set(result[rank]) != {0, 1, 2}:
            raise ValueError("Authenticated source overlap classes are incomplete")
    return result


def _build_game():
    source_classes = _source_classes()
    sb_hands = tuple(_canonical_hand(pair)
                     for rank in "AQJ"
                     for pair in combinations(tuple(rank + suit for suit in SUITS), 2))
    bb_hands = tuple(_canonical_hand(pair)
                     for pair in combinations(tuple("K" + suit for suit in SUITS), 2))
    raw_pairs = []
    classes = {rank: {0: 0, 1: 0, 2: 0} for rank in "AQJ"}
    normalizer = Fraction()
    for sb_hand in sb_hands:
        sb_cards = {sb_hand[:2], sb_hand[2:]}
        rank = sb_hand[0]
        for bb_hand in bb_hands:
            bb_cards = {bb_hand[:2], bb_hand[2:]}
            if sb_cards & bb_cards:
                continue
            overlap = len({sb_hand[1], sb_hand[3]} & {bb_hand[1], bb_hand[3]})
            counts = source_classes[rank].get(overlap)
            if counts is None:
                raise ValueError("No authenticated source row for physical pair class")
            raw_weight = SB_WEIGHT[rank]
            normalizer += raw_weight
            classes[rank][overlap] += 1
            mean = Fraction(counts[0] - counts[2], counts[3])
            raw_pairs.append((sb_hand, bb_hand, rank, overlap, raw_weight, mean, counts))
    expected_classes = {rank: {0: 6, 1: 24, 2: 6} for rank in "AQJ"}
    if (len(sb_hands), len(bb_hands), len(raw_pairs)) != (18, 6, 108):
        raise ValueError("Literal private-hand support changed")
    if normalizer != EXPECTED_NORMALIZER or classes != expected_classes:
        raise ValueError("Exact global range normalizer or overlap census changed")
    pairs = []
    for sb, bb, rank, overlap, raw_weight, mean, counts in raw_pairs:
        prior = raw_weight / normalizer
        expected_prior = {"A": Fraction(1, 63), "Q": Fraction(1, 126),
                          "J": Fraction(1, 252)}[rank]
        if prior != expected_prior:
            raise ValueError("Physical pair prior differs from global conditioning")
        pairs.append({"sb_hand": sb, "bb_hand": bb, "rank": rank,
                      "overlap": overlap, "prior": prior,
                      "showdown_mean": mean, "counts": counts})
    if sum((pair["prior"] for pair in pairs), Fraction()) != 1:
        raise ValueError("Joint physical pair priors do not sum exactly to one")
    return {"sb_hands": sb_hands, "bb_hands": bb_hands,
            "pairs": tuple(pairs), "class_counts": classes,
            "raw_weight_normalizer": normalizer}


def _fraction(value, label):
    if type(value) is not str or not value or len(value) > MAX_FRACTION_CHARS:
        raise ValueError(f"{label} must be a bounded canonical fraction string")
    if _FRACTION_TOKEN.fullmatch(value) is None:
        raise ValueError(f"{label} must use a bounded integer/rational token")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(f"Invalid {label}") from exc
    if (str(result) != value or result.numerator.bit_length() > MAX_FRACTION_BITS
            or result.denominator.bit_length() > MAX_FRACTION_BITS):
        raise ValueError(f"Noncanonical or oversized {label}")
    return result


def _policy(rows, game):
    if type(rows) is not list or len(rows) != MAX_POLICY_ROWS:
        raise ValueError("Policy must contain all 96 private-hand information rows")
    expected = {}
    for hand in game["sb_hands"]:
        for (player, history), actions in rules.INFO_MENUS.items():
            if player == 0:
                expected[(0, hand, history)] = actions
    for hand in game["bb_hands"]:
        for (player, history), actions in rules.INFO_MENUS.items():
            if player == 1:
                expected[(1, hand, history)] = actions
    if len(expected) != MAX_POLICY_ROWS:
        raise AssertionError("Independent legal own-hand information census changed")
    parsed = {}
    for row in rows:
        if type(row) is not dict or set(row) != {
                "player", "hand", "history", "actions", "probabilities"}:
            raise ValueError("Unexpected or private-information-leaking policy fields")
        player, hand = row["player"], row["hand"]
        history = row["history"]
        if (type(player) is not int or player not in (0, 1) or type(hand) is not str
                or len(hand) != 4 or type(history) is not list
                or len(history) > 4 or any(type(token) is not str or len(token) > 16
                                           for token in history)):
            raise ValueError("Malformed own-hand/public-history information key")
        key = (player, hand, tuple(history))
        actions = expected.get(key)
        if actions is None or key in parsed:
            raise ValueError("Unknown or duplicate private-hand information row")
        if type(row["actions"]) is not list or row["actions"] != list(actions):
            raise ValueError("Policy action menu differs from the literal legal menu")
        probs = row["probabilities"]
        if type(probs) is not list or len(probs) != len(actions):
            raise ValueError("Policy probability row does not match its legal menu")
        exact = tuple(_fraction(item, "policy probability") for item in probs)
        if any(item < 0 or item > 1 for item in exact) or sum(exact, Fraction()) != 1:
            raise ValueError("Policy probabilities must be normalized in [0,1]")
        parsed[key] = dict(zip(actions, exact))
    if set(parsed) != set(expected):
        raise ValueError("Policy omits legal off-path own-hand information rows")
    return parsed


def _terminal_value(policy, pair):
    total = Fraction()
    for path, constant, multiplier in rules.TERMINALS:
        reach, history = Fraction(1), []
        for index, action in enumerate(path):
            player = index % 2
            hand = pair["sb_hand"] if player == 0 else pair["bb_hand"]
            reach *= policy[(player, hand, tuple(history))][action]
            history.append(action)
            if not reach:
                break
        if reach:
            total += reach * (constant + multiplier * pair["showdown_mean"])
    return total


def _terminal_response(policy, pair, player, own_hand, choices):
    total = Fraction()
    for path, constant, multiplier in rules.TERMINALS:
        reach, history = Fraction(1), []
        for index, action in enumerate(path):
            acting = index % 2
            hand = pair["sb_hand"] if acting == 0 else pair["bb_hand"]
            if acting == player and hand == own_hand:
                probability = Fraction(choices[tuple(history)] == action)
            else:
                probability = policy[(acting, hand, tuple(history))][action]
            reach *= probability
            history.append(action)
            if not reach:
                break
        if reach:
            sb_value = constant + multiplier * pair["showdown_mean"]
            total += reach * (sb_value if player == 0 else -sb_value)
    return total


def _best_response(policy, game, player):
    own_hands = game["sb_hands"] if player == 0 else game["bb_hands"]
    info_defs = tuple((history, actions) for (owner, history), actions in rules.INFO_MENUS.items()
                      if owner == player)
    expected_options = 48 if player == 0 else 36
    response_total, rows, candidate_count = Fraction(), [], 0
    for own_hand in own_hands:
        pair_rows = [pair for pair in game["pairs"]
                     if pair["sb_hand" if player == 0 else "bb_hand"] == own_hand]
        best_value, best_choices = None, None
        for selected in product(*(actions for _, actions in info_defs)):
            candidate_count += 1
            choices = {history: action for (history, _), action in zip(info_defs, selected)}
            value = sum((pair["prior"] * _terminal_response(
                policy, pair, player, own_hand, choices) for pair in pair_rows), Fraction())
            if best_value is None or value > best_value:
                best_value, best_choices = value, choices
        response_total += best_value
        rows.append({"hand": own_hand, "pure_policies_enumerated": expected_options,
                     "best_response_own_utility_fraction": str(best_value),
                     "best_actions": [{"history": list(history), "action": best_choices[history]}
                                      for history, _ in info_defs]})
    if candidate_count != expected_options * len(own_hands):
        raise AssertionError("Complete own-hand pure-response census changed")
    return response_total, rows, candidate_count


def verify_policy(policies, claimed_value=None):
    """Verify the profile and legal own-hand best responses with exact fractions.

    `policies` is a list of 96 rows containing only player, own hand, public
    history, exact legal actions, and canonical fraction-string probabilities.
    A supplied `claimed_value` must also be a canonical fraction string.
    """
    game = _build_game()
    policy = _policy(policies, game)
    claim = None if claimed_value is None else _fraction(claimed_value, "claimed profile value")
    profile = sum((pair["prior"] * _terminal_value(policy, pair)
                   for pair in game["pairs"]), Fraction())
    sb_br, sb_by_hand, sb_count = _best_response(policy, game, 0)
    bb_br, bb_by_hand, bb_count = _best_response(policy, game, 1)
    sb_gain, bb_gain = sb_br - profile, bb_br + profile
    if sb_gain < 0 or bb_gain < 0:
        raise ArithmeticError("Legal pure response underperformed the supplied profile")
    nash_conv = sb_gain + bb_gain
    exact_value_matches = claim is None or claim == profile
    exact_mutual = nash_conv == 0 and exact_value_matches
    return {
        "status": "passed" if exact_mutual else "failed",
        "oracle": "independent-three-rank-preflop-pure-response-v1",
        "physical_private_pair_count": len(game["pairs"]),
        "sb_private_hand_count": len(game["sb_hands"]),
        "bb_private_hand_count": len(game["bb_hands"]),
        "source_rows_authenticated": 9,
        "source_basis_pins": dict(sources.SOURCE_PINS),
        "board_outcomes_per_pair": BOARD_COUNT,
        "raw_compatible_pair_weight_normalizer": str(game["raw_weight_normalizer"]),
        "overlap_class_pair_counts": {
            rank: {str(overlap): count for overlap, count in classes.items()}
            for rank, classes in game["class_counts"].items()},
        "pair_priors": [{"sb_hand": pair["sb_hand"], "bb_hand": pair["bb_hand"],
                         "prior_fraction": str(pair["prior"]),
                         "showdown_mean_fraction": str(pair["showdown_mean"]),
                         "source_counts": {key: value for key, value in zip(
                             ("wins", "ties", "losses", "boards"), pair["counts"])}}
                        for pair in game["pairs"]],
        "information_set_count": len(policy),
        "pure_response_policies_enumerated": {"sb": sb_count, "bb": bb_count,
                                               "total": sb_count + bb_count},
        "profile_value_sb_fraction": str(profile),
        "sb_best_response_own_utility_fraction": str(sb_br),
        "bb_best_response_own_utility_fraction": str(bb_br),
        "bb_ceiling_sb_perspective_fraction": str(-bb_br),
        "sb_best_response_gain_fraction": str(sb_gain),
        "bb_best_response_gain_fraction": str(bb_gain),
        "nash_conv_fraction": str(nash_conv),
        "claimed_value_fraction": None if claim is None else str(claim),
        "claimed_profile_value_matches": exact_value_matches,
        "exact_mutual_response_verified": exact_mutual,
        "sb_by_hand": sb_by_hand,
        "bb_by_hand": bb_by_hand,
        "scope": "exact finite preflop betting plus hidden full-board checkdown; not unrestricted NLHE",
    }
