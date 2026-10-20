"""Independent exact policy and pure-response replay for the fixed mixed game.

This checker authenticates two pinned physical count reports, remaps only by
joint suit-overlap class, and evaluates a serialized policy with exact
fractions. It does not build or call a poker solver/tree or an LP routine.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from fractions import Fraction
from itertools import combinations, product
from math import isfinite
from pathlib import Path

from scripts.validate_preflop_five_reference import verify_saved as verify_five_saved
from scripts.benchmark_preflop_qq_kk_basis import verify_saved as verify_qq_saved


ROOT = Path(__file__).resolve().parents[1]
FIVE_REPORT = ROOT / "benchmarks/results/preflop-five-basis-v1.json"
QQ_REPORT = ROOT / "benchmarks/results/preflop-qq-kk-basis-v1.json"
FIVE_SHA256 = "2ae377e0af6d55491c667d574f41482f2ea6911ba8565ade3b9c8406b54010f7"
QQ_SHA256 = "d47fcbdca9cb84275adb8902636d8331bca8b6089e1d62e83cc2160ff09503b8"
SPEC_SHA256 = "4307f9590e2f34d568cab929c0401eab572a7c0af0725f6181299a5b6636aa19"
PHYSICAL_GAME_SHA256 = "12debaea49eb6d9ac4b9ab6f49767e1dc25f00e4de6f163e69af5690f51653ca"
BOARD_COUNT = 1_712_304
MAX_SOURCE_BYTES = 1_000_000
MAX_CANDIDATE_BYTES = 512 * 1024
MAX_JSON_NODES = 20_000
MAX_JSON_STRING = 4096
MAX_FRACTION_BITS = 4096

SUITS = "cdhs"
RANKS = "23456789TJQKA"
SB_HAND_WEIGHTS = {"A": Fraction(1), "Q": Fraction(1, 2)}
BB_HAND_WEIGHT = Fraction(1)

# Every row is one public terminal history with the exact SB net-transfer
# payoff coefficient and, for showdown, a multiplier of the physical mean.
TERMINALS = (
    (("fold",), Fraction(-1, 2), 0),
    (("call", "check"), Fraction(0), 1),
    (("call", "raise@2", "fold"), Fraction(-1), 0),
    (("call", "raise@2", "call"), Fraction(0), 2),
    (("call", "raise@2", "all_in@3", "fold"), Fraction(2), 0),
    (("call", "raise@2", "all_in@3", "call"), Fraction(0), 3),
    (("call", "all_in@3", "fold"), Fraction(-1), 0),
    (("call", "all_in@3", "call"), Fraction(0), 3),
    (("raise@2", "fold"), Fraction(1), 0),
    (("raise@2", "call"), Fraction(0), 2),
    (("raise@2", "all_in@3", "fold"), Fraction(-2), 0),
    (("raise@2", "all_in@3", "call"), Fraction(0), 3),
    (("all_in@3", "fold"), Fraction(1), 0),
    (("all_in@3", "call"), Fraction(0), 3),
)

INFO_MENUS = {
    (0, ()): ("fold", "call", "raise@2", "all_in@3"),
    (0, ("call", "raise@2")): ("fold", "call", "all_in@3"),
    (0, ("call", "all_in@3")): ("fold", "call"),
    (0, ("raise@2", "all_in@3")): ("fold", "call"),
    (1, ("call",)): ("check", "raise@2", "all_in@3"),
    (1, ("raise@2",)): ("fold", "call", "all_in@3"),
    (1, ("all_in@3",)): ("fold", "call"),
    (1, ("call", "raise@2", "all_in@3")): ("fold", "call"),
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _pairs_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Nonfinite JSON constant: {value}")


def _check_envelope(value, *, max_string=MAX_JSON_STRING, max_nodes=MAX_JSON_NODES,
                    max_dict=64, max_list=256, max_string_bytes=MAX_CANDIDATE_BYTES):
    counts = {"nodes": 0, "string_bytes": 0}

    def visit(item, depth):
        if depth > 20:
            raise ValueError("JSON nesting exceeds checker limit")
        counts["nodes"] += 1
        if counts["nodes"] > max_nodes:
            raise ValueError("JSON node count exceeds checker limit")
        if type(item) is dict:
            if len(item) > max_dict:
                raise ValueError("JSON object exceeds field limit")
            for key, child in item.items():
                if type(key) is not str or len(key) > max_string:
                    raise ValueError("Invalid or overlong JSON object key")
                counts["string_bytes"] += len(key.encode("utf-8"))
                visit(child, depth + 1)
        elif type(item) is list:
            if len(item) > max_list:
                raise ValueError("JSON array exceeds item limit")
            for child in item:
                visit(child, depth + 1)
        elif type(item) is str:
            if len(item) > max_string:
                raise ValueError("JSON string exceeds length limit")
            counts["string_bytes"] += len(item.encode("utf-8"))
        elif type(item) is int:
            if item.bit_length() > MAX_FRACTION_BITS:
                raise ValueError("JSON integer exceeds bit limit")
        elif type(item) is float:
            if not isfinite(item):
                raise ValueError("Nonfinite JSON number")
        elif item is None or type(item) is bool:
            return
        else:
            raise ValueError("Unsupported JSON value")
        if counts["string_bytes"] > max_string_bytes:
            raise ValueError("JSON string data exceeds byte limit")

    visit(value, 0)


def _bounded_json(path, limit):
    path = Path(path)
    if path.stat().st_size > limit:
        raise ValueError("JSON input exceeds checker byte limit")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("JSON input exceeds checker byte limit")
    try:
        return json.loads(raw, object_pairs_hook=_pairs_no_duplicates,
                          parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Invalid JSON input") from exc


def load_bounded(path):
    """Load a candidate JSON file under the strict input envelope."""
    candidate = _bounded_json(path, MAX_CANDIDATE_BYTES)
    _check_envelope(candidate)
    return candidate


def _read_source(path, expected_sha, expected_id):
    report = _bounded_json(path, MAX_SOURCE_BYTES)
    _check_envelope(report, max_nodes=100_000, max_dict=2_000,
                    max_list=2_000, max_string_bytes=MAX_SOURCE_BYTES)
    if type(report) is not dict:
        raise ValueError("Pinned physical report must be an object")
    digest = report.get("artifact_sha256")
    unsigned = {key: value for key, value in report.items() if key != "artifact_sha256"}
    if (type(digest) is not str or digest != expected_sha
            or hashlib.sha256(_canonical(unsigned)).hexdigest() != expected_sha):
        raise ValueError("Pinned physical report checksum mismatch")
    if report.get("benchmark_id") != expected_id or report.get("status") != "passed":
        raise ValueError("Pinned physical report identity/status mismatch")
    return report


def _cards_for_rank(rank):
    return tuple(rank + suit for suit in SUITS)


def _canonical_hand(cards):
    order = {rank + suit: (rank_index, suit_index)
             for rank_index, rank in enumerate(RANKS)
             for suit_index, suit in enumerate(SUITS)}
    return "".join(sorted(cards, key=order.__getitem__))


def _physical_source_classes():
    five_report = _read_source(FIVE_REPORT, FIVE_SHA256, "preflop-five-basis-v1")
    qq_report = _read_source(QQ_REPORT, QQ_SHA256, "preflop-qq-kk-basis-v1")
    if verify_five_saved(FIVE_REPORT).get("status") != "passed":
        raise ValueError("Pinned AA/KK physical source verification failed")
    if verify_qq_saved(QQ_REPORT).get("status") != "passed":
        raise ValueError("Pinned QQ/KK physical source verification failed")

    classes = {"A": {}, "Q": {}}
    for rank, report in (("A", five_report), ("Q", qq_report)):
        rows = report.get("independent_physical_count_rows")
        if type(rows) is not list or len(rows) != 3:
            raise ValueError("Pinned physical basis must contain three count rows")
        for row in rows:
            if type(row) is not dict:
                raise ValueError("Malformed physical basis row")
            sb_hand, bb_hand = row.get("sb_hand"), row.get("bb_hand")
            if (type(sb_hand) is not str or type(bb_hand) is not str
                    or len(sb_hand) != 4 or len(bb_hand) != 4):
                raise ValueError("Malformed physical hand labels")
            overlap = len(set((sb_hand[1], sb_hand[3])) & set((bb_hand[1], bb_hand[3])))
            if overlap not in (0, 1, 2) or overlap in classes[rank]:
                raise ValueError("Physical basis does not give one row per suit-overlap class")
            counts = tuple(row.get(key) for key in ("wins", "ties", "losses", "boards"))
            if (any(type(value) is not int or value < 0 for value in counts)
                    or sum(counts[:3]) != BOARD_COUNT or counts[3] != BOARD_COUNT):
                raise ValueError("Pinned physical basis count totals are invalid")
            classes[rank][overlap] = counts
        if set(classes[rank]) != {0, 1, 2}:
            raise ValueError("Physical basis is missing an overlap class")
    return classes


def _build_game():
    source_classes = _physical_source_classes()
    sb_hands = tuple(_canonical_hand(pair) for pair in combinations(_cards_for_rank("A"), 2))
    sb_hands += tuple(_canonical_hand(pair) for pair in combinations(_cards_for_rank("Q"), 2))
    bb_hands = tuple(_canonical_hand(pair) for pair in combinations(_cards_for_rank("K"), 2))
    weights = {hand: SB_HAND_WEIGHTS[hand[0]] for hand in sb_hands}
    total_weight = Fraction()
    raw_pairs = []
    class_counts = {"A": {0: 0, 1: 0, 2: 0}, "Q": {0: 0, 1: 0, 2: 0}}
    for sb_hand in sb_hands:
        for bb_hand in bb_hands:
            # Rank-disjoint hands cannot collide physically, but retain the
            # explicit card check so future fixture edits fail closed.
            sb_cards = {sb_hand[:2], sb_hand[2:]}
            bb_cards = {bb_hand[:2], bb_hand[2:]}
            if sb_cards & bb_cards:
                continue
            rank = sb_hand[0]
            overlap = len({sb_hand[1], sb_hand[3]} & {bb_hand[1], bb_hand[3]})
            raw_weight = weights[sb_hand] * BB_HAND_WEIGHT
            total_weight += raw_weight
            class_counts[rank][overlap] += 1
            source = source_classes[rank][overlap]
            raw_pairs.append((sb_hand, bb_hand, raw_weight,
                              Fraction(source[0] - source[2], source[3]), source))
    if (len(sb_hands) != 12 or len(bb_hands) != 6 or len(raw_pairs) != 72
            or total_weight != 54 or class_counts != {
                "A": {0: 6, 1: 24, 2: 6}, "Q": {0: 6, 1: 24, 2: 6}}):
        raise ValueError("Fixed mixed physical hand census changed")
    pairs = []
    for sb_hand, bb_hand, raw_weight, mean, source in raw_pairs:
        prior = raw_weight / total_weight
        expected_prior = Fraction(1, 54 if sb_hand[0] == "A" else 108)
        if prior != expected_prior:
            raise ValueError("Exact mixed private-pair prior changed")
        pairs.append({"sb_hand": sb_hand, "bb_hand": bb_hand, "prior": prior,
                      "showdown_mean": mean, "counts": source})
    return {
        "sb_hands": sb_hands,
        "bb_hands": bb_hands,
        "pairs": tuple(pairs),
        "pair_map": {(row["sb_hand"], row["bb_hand"]): row for row in pairs},
        "class_counts": class_counts,
        "raw_weight_normalizer": total_weight,
    }


def _fraction(value, label):
    if type(value) is not str or not value or len(value) > 256:
        raise ValueError(f"{label} must be a bounded rational string")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(f"Invalid {label}") from exc
    if (str(result) != value or result.numerator.bit_length() > MAX_FRACTION_BITS
            or result.denominator.bit_length() > MAX_FRACTION_BITS):
        raise ValueError(f"Noncanonical or oversized {label}")
    return result


def _policy(candidate, game):
    if type(candidate) is not dict:
        raise ValueError("Candidate must be a JSON object")
    _check_envelope(candidate)
    if len(_canonical(candidate)) > MAX_CANDIDATE_BYTES:
        raise ValueError('Candidate canonical JSON exceeds checker byte limit')
    checksum = candidate.get("artifact_sha256")
    unsigned = {key: value for key, value in candidate.items() if key != "artifact_sha256"}
    if (type(checksum) is not str or len(checksum) != 64
            or hashlib.sha256(_canonical(unsigned)).hexdigest() != checksum):
        raise ValueError("Candidate artifact checksum mismatch")
    if (candidate.get("schema_version") != 1
            or type(candidate.get("schema_version")) is not int
            or candidate.get("certificate_id") != "preflop-mixed-physical-exact-v1"
            or candidate.get("status") != "candidate-only"):
        raise ValueError("Unsupported mixed candidate identity")
    if (candidate.get('spec_sha256') != SPEC_SHA256
            or candidate.get('physical_game_spec_sha256') != PHYSICAL_GAME_SHA256):
        raise ValueError('Candidate declared game specification identity changed')
    rows = candidate.get("policies")
    if type(rows) is not list or len(rows) != 72:
        raise ValueError("Candidate must contain exactly 72 policy rows")

    expected = {}
    for hand in game["sb_hands"]:
        for history, actions in _player_infos(0):
            expected[(0, hand, history)] = actions
    for hand in game["bb_hands"]:
        for history, actions in _player_infos(1):
            expected[(1, hand, history)] = actions

    parsed = {}
    for row in rows:
        if type(row) is not dict or set(row) != {"player", "hand", "history", "actions", "probabilities"}:
            raise ValueError("Unexpected or information-leaking policy row fields")
        player, hand = row["player"], row["hand"]
        if type(player) is not int or player not in (0, 1) or type(hand) is not str:
            raise ValueError("Invalid player or private hand key")
        history = row["history"]
        if type(history) is not list or any(type(token) is not str for token in history):
            raise ValueError("Invalid public history")
        key = (player, hand, tuple(history))
        actions = expected.get(key)
        if actions is None or key in parsed:
            raise ValueError("Unknown or duplicate own-hand information set")
        if row["actions"] != list(actions):
            raise ValueError("Policy action menu differs from independent legal menu")
        probabilities = row["probabilities"]
        if type(probabilities) is not list or len(probabilities) != len(actions):
            raise ValueError("Policy probabilities do not match legal actions")
        exact_probs = tuple(_fraction(p, "policy probability") for p in probabilities)
        if any(probability < 0 or probability > 1 for probability in exact_probs):
            raise ValueError("Policy probability outside [0,1]")
        if sum(exact_probs, Fraction()) != 1:
            raise ValueError("Policy probabilities must sum exactly to one")
        parsed[key] = dict(zip(actions, exact_probs))
    if set(parsed) != set(expected):
        raise ValueError("Candidate misses legal own-hand information sets")
    return parsed


def _player_infos(player):
    return tuple((history, actions) for (owner, history), actions in INFO_MENUS.items()
                 if owner == player)


def _terminal_value(policy, pair):
    sb_hand, bb_hand = pair["sb_hand"], pair["bb_hand"]
    mean = pair["showdown_mean"]
    total = Fraction()
    for path, constant, multiplier in TERMINALS:
        chance = Fraction(1)
        history = []
        for index, token in enumerate(path):
            player = 0 if index % 2 == 0 else 1
            hand = sb_hand if player == 0 else bb_hand
            key = (player, hand, tuple(history))
            probability = policy[key][token]
            chance *= probability
            history.append(token)
            if not chance:
                break
        if chance:
            sb_value = constant + multiplier * mean
            total += chance * sb_value
    return total


def _choices_for(player):
    return _player_infos(player)


def _best_response(policy, game, player):
    own_hands = game["sb_hands"] if player == 0 else game["bb_hands"]
    info_defs = _choices_for(player)
    expected_options = 48 if player == 0 else 36
    response_total = Fraction()
    rows = []
    candidate_count = 0
    for own_hand in own_hands:
        pair_rows = [pair for pair in game["pairs"]
                     if (pair["sb_hand"] if player == 0 else pair["bb_hand"]) == own_hand]
        best_value = None
        best_choices = None
        for choices in product(*(actions for _history, actions in info_defs)):
            candidate_count += 1
            # Each action choice applies to one distinct history for this hand.
            per_history = {history: action for (history, _actions), action in zip(info_defs, choices)}
            score = Fraction()
            for pair in pair_rows:
                local_overrides = {"choices": per_history, "hand": own_hand}
                score += pair["prior"] * _terminal_value_response(
                    policy, pair, player, local_overrides, utility_player=player)
            if best_value is None or score > best_value:
                best_value, best_choices = score, per_history
        response_total += best_value
        rows.append({"hand": own_hand, "pure_policies_enumerated": expected_options,
                     "best_response_own_utility_fraction": str(best_value),
                     "best_actions": [{"history": list(history), "action": best_choices[history]}
                                      for history, _actions in info_defs]})
    if candidate_count != expected_options * len(own_hands):
        raise AssertionError("Pure-response enumeration census changed")
    return response_total, rows, candidate_count


def _terminal_value_response(policy, pair, player, response, *, utility_player):
    sb_hand, bb_hand = pair["sb_hand"], pair["bb_hand"]
    mean = pair["showdown_mean"]
    total = Fraction()
    for path, constant, multiplier in TERMINALS:
        chance = Fraction(1)
        history = []
        for index, token in enumerate(path):
            acting = 0 if index % 2 == 0 else 1
            hand = sb_hand if acting == 0 else bb_hand
            key = (acting, hand, tuple(history))
            if acting == player and hand == response["hand"]:
                probability = Fraction(response["choices"][tuple(history)] == token)
            else:
                probability = policy[key][token]
            chance *= probability
            history.append(token)
            if not chance:
                break
        if chance:
            sb_value = constant + multiplier * mean
            total += chance * (sb_value if utility_player == 0 else -sb_value)
    return total


def _clairvoyant_response(policy, game, player):
    """Illegal control: allow response choices to depend on the opponent hand."""
    total = Fraction()
    controls = 0
    info_defs = _choices_for(player)
    for pair in game["pairs"]:
        best = None
        own_hand = pair["sb_hand"] if player == 0 else pair["bb_hand"]
        for choices in product(*(actions for _history, actions in info_defs)):
            controls += 1
            per_history = {history: action for (history, _actions), action in zip(info_defs, choices)}
            value = _terminal_value_response(
                policy, pair, player, {"choices": per_history, "hand": own_hand},
                utility_player=player)
            if best is None or value > best:
                best = value
        total += pair["prior"] * best
    return total, controls


def verify_candidate(data):
    """Verify candidate profile value and exact legal own-hand pure responses."""
    game = _build_game()
    policy = _policy(data, game)
    claim = _fraction(data.get("value_candidate_fraction"), "candidate value")

    profile = sum((pair["prior"] * _terminal_value(policy, pair)
                   for pair in game["pairs"]), Fraction())
    sb_br, sb_by_hand, sb_count = _best_response(policy, game, 0)
    bb_br, bb_by_hand, bb_count = _best_response(policy, game, 1)
    sb_gain = sb_br - profile
    bb_gain = bb_br + profile
    if sb_gain < 0 or bb_gain < 0:
        raise ValueError('Exact legal response underperforms the supplied profile')
    nash_conv = sb_gain + bb_gain
    bb_sb_ceiling = -bb_br
    if sb_count != 12 * 48 or bb_count != 6 * 36 or sb_count + bb_count != 792:
        raise AssertionError("Pure-response census changed")

    sb_clairvoyant, sb_control_count = _clairvoyant_response(policy, game, 0)
    bb_clairvoyant, bb_control_count = _clairvoyant_response(policy, game, 1)
    if sb_clairvoyant < sb_br or bb_clairvoyant < bb_br:
        raise AssertionError("Illegal clairvoyance control must weakly improve own utility")

    exact_mutual_response = nash_conv == 0 and claim == profile
    return {
        "status": "passed" if exact_mutual_response else "failed",
        "oracle": "independent-mixed-preflop-14-terminal-pure-response-v1",
        "candidate_artifact_sha256": data["artifact_sha256"],
        "source_report_sha256": {"aa_kk": FIVE_SHA256, "qq_kk": QQ_SHA256},
        "physical_pair_count": len(game["pairs"]),
        "physical_board_count": len(game["pairs"]) * BOARD_COUNT,
        "raw_compatible_pair_weight_normalizer": str(game["raw_weight_normalizer"]),
        "overlap_class_pair_counts": {rank: {str(k): v for k, v in counts.items()}
                                      for rank, counts in game["class_counts"].items()},
        "pair_priors": [{"sb_hand": pair["sb_hand"], "bb_hand": pair["bb_hand"],
                         "prior_fraction": str(pair["prior"]),
                         "showdown_mean_fraction": str(pair["showdown_mean"])}
                        for pair in game["pairs"]],
        "terminal_history_count": len(TERMINALS),
        "information_set_count": len(policy),
        "pure_response_policies_enumerated": {"sb": sb_count, "bb": bb_count,
                                               "total": sb_count + bb_count},
        "profile_value_sb_fraction": str(profile),
        "sb_best_response_own_utility_fraction": str(sb_br),
        "bb_best_response_own_utility_fraction": str(bb_br),
        "bb_ceiling_sb_perspective_fraction": str(bb_sb_ceiling),
        "sb_best_response_gain_fraction": str(sb_gain),
        "bb_best_response_gain_fraction": str(bb_gain),
        "nash_conv_fraction": str(nash_conv),
        "value_candidate_fraction": str(claim),
        "claimed_profile_value_matches": claim == profile,
        "exact_mutual_response_verified": exact_mutual_response,
        "sb_by_hand": sb_by_hand,
        "bb_by_hand": bb_by_hand,
        "illegal_clairvoyant_control": {
            "scope": "Illegal control allows a response policy to depend on the opponent's private hand.",
            "sb_own_utility_fraction": str(sb_clairvoyant),
            "sb_at_least_legal_response": sb_clairvoyant >= sb_br,
            "bb_own_utility_fraction": str(bb_clairvoyant),
            "bb_at_least_legal_response": bb_clairvoyant >= bb_br,
            "sb_policies_enumerated": sb_control_count,
            "bb_policies_enumerated": bb_control_count,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    candidate = load_bounded(args.input)
    result = verify_candidate(candidate)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        if args.output.exists():raise FileExistsError('Preserve the existing pure-response observation')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x',encoding='utf-8',newline='\n') as stream:stream.write(rendered)
    print(json.dumps({key: result[key] for key in (
        "status", "candidate_artifact_sha256", "profile_value_sb_fraction",
        "nash_conv_fraction", "pure_response_policies_enumerated",
        "exact_mutual_response_verified")}, sort_keys=True))
    return 0 if result['status']=='passed' else 1


if __name__ == "__main__":
    raise SystemExit(main())
