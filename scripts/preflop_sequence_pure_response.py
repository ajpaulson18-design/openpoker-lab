"""Independent legal pure-response audit for the pinned weighted preflop witness.

This module deliberately spells out the twelve terminal betting histories and
their chip transfers. It reads only the frozen benchmark specification, its
three checksum-pinned physical count artifacts, and a serialized candidate
policy. It does not construct or solve an equilibrium.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
from itertools import product
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "benchmarks" / "preflop-weighted-sequence-v1.json"
CANDIDATE_SHA256 = "59d294d41114756053419e0a69e4d3b043be9a900ec678a0668a0f9cf48300ed"
SPEC_SHA256 = "5b4a79d0239a42c3911928b0ca5d0f53a54be228e68c62ad9a5f8a2925719fb3"
MAX_INPUT_BYTES = 256 * 1024
MAX_JSON_DEPTH = 24
MAX_JSON_NODES = 20_000
MAX_JSON_KEY_CHARS = 1024
MAX_JSON_STRING_CHARS = 256 * 1024
MAX_JSON_TOTAL_STRING_CHARS = 1_000_000
MAX_JSON_LIST_ITEMS = 256
MAX_JSON_OBJECT_ITEMS = 64
MAX_INTEGER_BITS = 4096
BOARDS_PER_PAIR = 1_712_304

_CARD = re.compile(r"^[2-9TJQKA][cdhs]$")

SB_ROOT = ("fold", "call", "raise@2", "raise@3", "all_in@4")
SB_RESPONSE = ("fold", "call")
BB_LIMP = ("check", "raise@2", "all_in@3")
BB_RESPONSE = ("fold", "call")


def _canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON object contains a duplicate key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("JSON contains a non-finite numeric constant: " + value)


def _validate_json_envelope(value):
    """Bound caller-supplied Python data before canonical serialization."""
    stack = [(value, 0)]
    node_count = 0
    total_string_chars = 0
    while stack:
        item, depth = stack.pop()
        node_count += 1
        if node_count > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise ValueError("Candidate JSON exceeds structural limits")
        if type(item) is str:
            total_string_chars += len(item)
            if len(item) > MAX_JSON_STRING_CHARS:
                raise ValueError("Candidate JSON contains an oversized string")
        elif type(item) is int:
            if item.bit_length() > MAX_INTEGER_BITS:
                raise ValueError("Candidate JSON contains an oversized integer")
        elif type(item) is float:
            if item != item or item in (float("inf"), float("-inf")):
                raise ValueError("Candidate JSON contains a non-finite number")
        elif type(item) is list:
            if len(item) > MAX_JSON_LIST_ITEMS:
                raise ValueError("Candidate JSON list exceeds its item limit")
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is dict:
            if len(item) > MAX_JSON_OBJECT_ITEMS:
                raise ValueError("Candidate JSON object exceeds its item limit")
            for key, child in item.items():
                if type(key) is not str or len(key) > MAX_JSON_KEY_CHARS:
                    raise ValueError("Candidate JSON contains an invalid or oversized key")
                total_string_chars += len(key)
                stack.append((child, depth + 1))
        elif item is not None and type(item) is not bool:
            raise ValueError("Candidate contains a value that is not JSON data")
        if total_string_chars > MAX_JSON_TOTAL_STRING_CHARS:
            raise ValueError("Candidate JSON exceeds its total string limit")


def _load_json(path, *, maximum=MAX_INPUT_BYTES):
    path = Path(path)
    if path.stat().st_size > maximum:
        raise ValueError("Input exceeds the bounded JSON size limit")
    return json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant)


def _fraction(value, label):
    if type(value) is not str or len(value) > 256:
        raise ValueError(label + " must be a bounded rational string")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError, OverflowError):
        raise ValueError(label + " is not a valid rational") from None
    if result.denominator.bit_length() > 4096 or result.numerator.bit_length() > 4096:
        raise ValueError(label + " exceeds the rational size limit")
    return result


def _hand(value, label):
    if type(value) is not str or len(value) != 4:
        raise ValueError(label + " must contain exactly two card codes")
    cards = (value[:2], value[2:])
    if any(_CARD.fullmatch(card) is None for card in cards) or cards[0] == cards[1]:
        raise ValueError(label + " contains invalid or duplicated cards")
    return "".join(sorted(cards))


def _parse_range(value, label):
    if type(value) is not str or len(value) > 1024:
        raise ValueError(label + " is not a bounded range string")
    rows = {}
    for token in value.split(","):
        fields = token.split(":")
        if len(fields) != 2:
            raise ValueError(label + " has an invalid hand-weight entry")
        hand = _hand(fields[0], label + " hand")
        weight = _fraction(fields[1], label + " weight")
        if weight <= 0 or hand in rows:
            raise ValueError(label + " weights must be positive with unique hands")
        rows[hand] = weight
    if not rows:
        raise ValueError(label + " must contain a hand")
    return rows


def _validate_spec(spec):
    if type(spec) is not dict or hashlib.sha256(_canonical_bytes(spec)).hexdigest() != SPEC_SHA256:
        raise ValueError("The fixed weighted-sequence specification changed")
    if (spec.get("schema_version") != 1
            or spec.get("benchmark_id") != "preflop-weighted-sequence-v1"
            or spec.get("baseline_commit") != "26a3b28bfe566019b3d44b281a24f9497d578ca8"):
        raise ValueError("Unsupported weighted-sequence specification identity")
    fixture = spec.get("fixture")
    expected_config = {"small_blind": 0.5, "big_blind": 1,
                       "starting_stack": [4, 3], "raise_sizes": [0.5, 1],
                       "max_raises": 1, "include_all_in": True}
    if (type(fixture) is not dict
            or fixture.get("id") != "preflop-weighted-three-pair-sequence-equilibrium"
            or fixture.get("sb_range") != "AsAd:1,QsQd:0.5"
            or fixture.get("bb_range") != "AsKh:0.25,KsKd:1"
            or fixture.get("config") != expected_config):
        raise ValueError("Unsupported fixed preflop betting fixture")
    chance = spec.get("chance")
    if (type(chance) is not dict or chance.get("boards_per_pair") != BOARDS_PER_PAIR
            or chance.get("compatible_pairs") != 3 or chance.get("physical_boards") != 5_136_912
            or chance.get("source_commit") != "a5e1b75ab424c97673f5126796b9d7eae14b0706"
            or len(chance.get("source_files", ())) != 3
            or len(chance.get("canonical_artifact_sha256", ())) != 3):
        raise ValueError("Unsupported physical-count source specification")
    return fixture, chance


def _pair_priors(fixture):
    sb = _parse_range(fixture["sb_range"], "SB range")
    bb = _parse_range(fixture["bb_range"], "BB range")
    compatible = {}
    for sb_hand, sb_weight in sb.items():
        for bb_hand, bb_weight in bb.items():
            if set((sb_hand[:2], sb_hand[2:])).isdisjoint((bb_hand[:2], bb_hand[2:])):
                compatible[sb_hand, bb_hand] = sb_weight * bb_weight
    normalizer = sum(compatible.values(), Fraction(0))
    if normalizer <= 0:
        raise ValueError("Fixture has no compatible private-hand pairs")
    return {pair: mass / normalizer for pair, mass in compatible.items()}


def _load_physical_rows(chance, priors):
    rows = {}
    for path, expected_digest in zip(chance["source_files"], chance["canonical_artifact_sha256"]):
        artifact = _load_json(ROOT / path, maximum=64 * 1024)
        if type(artifact) is not dict or "artifact_sha256" not in artifact:
            raise ValueError("Pinned physical-count artifact has an invalid shape")
        unsigned = dict(artifact)
        declared = unsigned.pop("artifact_sha256")
        digest = hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()
        if digest != expected_digest or declared != expected_digest:
            raise ValueError("Pinned physical-count artifact checksum mismatch: " + path)
        if (artifact.get("schema_version") != 1
                or artifact.get("phase") != "independent-full-board-oracle"
                or type(artifact.get("counts")) is not dict):
            raise ValueError("Pinned physical-count artifact has an unsupported schema")
        counts = artifact["counts"]
        pair = (_hand(counts.get("sb_hand"), "SB count hand"),
                _hand(counts.get("bb_hand"), "BB count hand"))
        if pair in rows or pair not in priors:
            raise ValueError("Pinned count artifact has duplicate or incompatible private hands")
        wins, ties, losses, boards = (counts.get(k) for k in ("wins", "ties", "losses", "boards"))
        if (any(type(v) is not int or v < 0 for v in (wins, ties, losses))
                or type(boards) is not int or boards != BOARDS_PER_PAIR
                or wins + ties + losses != boards):
            raise ValueError("Pinned physical counts do not partition the full-board outcomes")
        rows[pair] = {"wins": wins, "ties": ties, "losses": losses,
                      "boards": boards, "showdown_mean": Fraction(wins - losses, boards),
                      "prior": priors[pair], "source": path,
                      "canonical_artifact_sha256": expected_digest}
    if set(rows) != set(priors) or sum((row["prior"] for row in rows.values()), Fraction(0)) != 1:
        raise ValueError("Pinned physical rows do not cover the exact compatible-pair prior")
    if sum(row["boards"] for row in rows.values()) != chance["physical_boards"]:
        raise ValueError("Pinned physical rows do not match the specified total-board census")
    return rows


def _expected_policy_keys(priors):
    sb_hands = sorted({pair[0] for pair in priors})
    bb_hands = sorted({pair[1] for pair in priors})
    expected = {}
    for hand in sb_hands:
        expected[(0, hand, ())] = SB_ROOT
        expected[(0, hand, ("call", "raise@2"))] = SB_RESPONSE
        expected[(0, hand, ("call", "all_in@3"))] = SB_RESPONSE
    for hand in bb_hands:
        expected[(1, hand, ("call",))] = BB_LIMP
        expected[(1, hand, ("raise@2",))] = BB_RESPONSE
        expected[(1, hand, ("raise@3",))] = BB_RESPONSE
        expected[(1, hand, ("all_in@4",))] = BB_RESPONSE
    return expected


def _candidate_policies(witness, priors):
    if type(witness) is not dict:
        raise ValueError("Candidate witness must be a JSON object")
    _validate_json_envelope(witness)
    try:
        encoded = _canonical_bytes(witness)
    except (TypeError, ValueError):
        raise ValueError("Candidate witness is not finite canonical JSON") from None
    if len(encoded) > MAX_INPUT_BYTES:
        raise ValueError("Candidate witness exceeds the bounded input size")
    unsigned = dict(witness)
    declared = unsigned.pop("artifact_sha256", None)
    digest = hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()
    if (type(declared) is not str or re.fullmatch(r"[0-9a-f]{64}", declared) is None
            or digest != declared):
        raise ValueError("Candidate witness self-checksum does not match its content")
    if (witness.get("schema_version") != 1
            or witness.get("status") != "exact-candidate-feasibility"
            or witness.get("certificate_id") != "preflop-weighted-sequence-feasibility-v1"):
        raise ValueError("Candidate witness identity is unsupported")
    expected_rows = _expected_policy_keys(priors)
    parsed = {}
    for row in witness.get("policies", ()):
        if type(row) is not dict or set(row) != {
                "action_tokens", "hand", "history", "player", "probabilities",
                "zero_realization_fallback"}:
            raise ValueError("Candidate policy row has an unsupported shape")
        player_token = row["player"]
        if player_token not in ("sb", "bb"):
            raise ValueError("Candidate policy has an invalid acting player")
        player = 0 if player_token == "sb" else 1
        hand = _hand(row["hand"], "Candidate policy hand")
        history = row["history"]
        if type(history) is not list or len(history) > 2 or any(type(x) is not str for x in history):
            raise ValueError("Candidate policy history is malformed")
        key = (player, hand, tuple(history))
        actions = expected_rows.get(key)
        if actions is None or key in parsed:
            raise ValueError("Candidate policy includes an unknown or duplicate information set")
        if (row["action_tokens"] != list(actions)
                or type(row["probabilities"]) is not list
                or len(row["probabilities"]) != len(actions)
                or type(row["zero_realization_fallback"]) is not bool):
            raise ValueError("Candidate policy actions or probabilities do not match legal history")
        probabilities = tuple(_fraction(value, "Policy probability")
                              for value in row["probabilities"])
        if any(p < 0 or p > 1 for p in probabilities) or sum(probabilities, Fraction(0)) != 1:
            raise ValueError("Candidate action probabilities must be nonnegative and sum exactly to one")
        parsed[key] = dict(zip(actions, probabilities))
    if set(parsed) != set(expected_rows) or len(parsed) != 14:
        raise ValueError("Candidate must contain exactly the fourteen own-hand/public-history rows")
    return parsed


# Each terminal is a public action path and an affine payoff
# constant + matched_wager * (wins-losses)/boards from the SB perspective.
_TERMINALS = (
    ("root-fold", ((0, (), "fold"),), Fraction(-1, 2), 0),
    ("limp-check", ((0, (), "call"), (1, ("call",), "check")), Fraction(0), 1),
    ("limp-raise2-fold", ((0, (), "call"), (1, ("call",), "raise@2"),
                          (0, ("call", "raise@2"), "fold")), Fraction(-1), 0),
    ("limp-raise2-call", ((0, (), "call"), (1, ("call",), "raise@2"),
                          (0, ("call", "raise@2"), "call")), Fraction(0), 2),
    ("limp-allin3-fold", ((0, (), "call"), (1, ("call",), "all_in@3"),
                         (0, ("call", "all_in@3"), "fold")), Fraction(-1), 0),
    ("limp-allin3-call", ((0, (), "call"), (1, ("call",), "all_in@3"),
                         (0, ("call", "all_in@3"), "call")), Fraction(0), 3),
    ("raise2-bbfold", ((0, (), "raise@2"), (1, ("raise@2",), "fold")), Fraction(1), 0),
    ("raise2-bbcall", ((0, (), "raise@2"), (1, ("raise@2",), "call")), Fraction(0), 2),
    ("raise3-bbfold", ((0, (), "raise@3"), (1, ("raise@3",), "fold")), Fraction(1), 0),
    ("raise3-bbcall", ((0, (), "raise@3"), (1, ("raise@3",), "call")), Fraction(0), 3),
    ("shove4-bbfold", ((0, (), "all_in@4"), (1, ("all_in@4",), "fold")), Fraction(1), 0),
    # SB's shove is four chips but BB can match only three; the unmatched chip
    # is refunded, so the called showdown is a three-chip matched wager.
    ("shove4-bbcall-refund", ((0, (), "all_in@4"), (1, ("all_in@4",), "call")), Fraction(0), 3),
)


def _terminal_probability(policy, sb_hand, bb_hand, path, overrides=None):
    probability = Fraction(1)
    for player, history, action in path:
        hand = sb_hand if player == 0 else bb_hand
        key = (player, hand, history)
        if overrides is not None and key in overrides:
            probability *= int(overrides[key] == action)
        else:
            probability *= policy[key][action]
    return probability


def _pair_value(policy, physical_row, pair, overrides=None):
    sb_hand, bb_hand = pair
    showdown_mean = physical_row["showdown_mean"]
    total = Fraction(0)
    for _name, path, constant, matched in _TERMINALS:
        probability = _terminal_probability(policy, sb_hand, bb_hand, path, overrides)
        total += probability * (constant + matched * showdown_mean)
    return total


def _pure_responses(policy, priors, physical_rows, player):
    own_hands = sorted({pair[player] for pair in priors})
    if player == 0:
        rows = (((), SB_ROOT), (("call", "raise@2"), SB_RESPONSE),
                (("call", "all_in@3"), SB_RESPONSE))
        objective = max
    else:
        rows = ((("call",), BB_LIMP), (("raise@2",), BB_RESPONSE),
                (("raise@3",), BB_RESPONSE), (("all_in@4",), BB_RESPONSE))
        objective = min
    hand_results = []
    total = Fraction(0)
    for own_hand in own_hands:
        number = 1
        for _, actions in rows:
            number *= len(actions)
        if number != (20 if player == 0 else 24):
            raise AssertionError("Internal pure-policy census changed")
        scores = []
        for choices in product(*(actions for _, actions in rows)):
            overrides = {(player, own_hand, history): action
                         for (history, _), action in zip(rows, choices)}
            score = Fraction(0)
            for pair, prior in priors.items():
                if pair[player] == own_hand:
                    score += prior * _pair_value(policy, physical_rows[pair], pair, overrides)
            scores.append((score, choices))
        best_score = objective(row[0] for row in scores)
        best = next(row for row in scores if row[0] == best_score)
        total += best_score
        hand_results.append({
            "hand": own_hand,
            "pure_policies_enumerated": number,
            "weighted_best_response_value_fraction": str(best_score),
            "best_actions": [
                {"history": list(history), "action": action}
                for (history, _), action in zip(rows, best[1])],
        })
    return total, hand_results


def _clairvoyant_responses(policy, priors, physical_rows, player):
    """Counterfactual control allowing a responder to see the opponent's hand."""
    if player == 0:
        rows = (((), SB_ROOT), (("call", "raise@2"), SB_RESPONSE),
                (("call", "all_in@3"), SB_RESPONSE))
    else:
        rows = ((("call",), BB_LIMP), (("raise@2",), BB_RESPONSE),
                (("raise@3",), BB_RESPONSE), (("all_in@4",), BB_RESPONSE))
    total = Fraction(0)
    pair_values = []
    for pair, prior in priors.items():
        objective = max if player == 0 else min
        best = None
        for choices in product(*(actions for _, actions in rows)):
            overrides = {(player, pair[player], history): action
                         for (history, _), action in zip(rows, choices)}
            value = _pair_value(policy, physical_rows[pair], pair, overrides)
            if best is None or (value > best if player == 0 else value < best):
                best = value
        total += prior * best
        pair_values.append({"sb_hand": pair[0], "bb_hand": pair[1],
                            "pair_prior_fraction": str(prior),
                            "clairvoyant_value_fraction": str(best)})
    return total, pair_values


def public_pure_response(witness):
    """Audit the pinned policy by enumerating legal own-hand pure responses."""
    spec = _load_json(SPEC_PATH, maximum=64 * 1024)
    fixture, chance = _validate_spec(spec)
    priors = _pair_priors(fixture)
    physical_rows = _load_physical_rows(chance, priors)
    policy = _candidate_policies(witness, priors)
    expected_summaries = [
        {"sb_hand": sb, "bb_hand": bb, "prior_fraction": str(priors[(sb, bb)]),
         "showdown_mean_fraction": str(physical_rows[(sb, bb)]["showdown_mean"])}
        for sb, bb in priors
    ]
    if witness.get("fixture") != fixture or witness.get("pair_priors") != expected_summaries:
        raise ValueError("Candidate fixture or recorded pair summaries differ from pinned inputs")

    profile_value = sum((prior * _pair_value(policy, physical_rows[pair], pair)
                         for pair, prior in priors.items()), Fraction(0))
    sb_response, sb_hands = _pure_responses(policy, priors, physical_rows, 0)
    bb_response, bb_hands = _pure_responses(policy, priors, physical_rows, 1)
    sb_clairvoyant, sb_pair_controls = _clairvoyant_responses(policy, priors, physical_rows, 0)
    bb_clairvoyant, bb_pair_controls = _clairvoyant_responses(policy, priors, physical_rows, 1)
    sb_gain = sb_response - profile_value
    bb_gain = profile_value - bb_response
    nash_conv = sb_response - bb_response
    claimed = witness.get("equilibrium")
    if type(claimed) is not dict:
        raise ValueError("Candidate has no claimed equilibrium summary")
    claimed_value = _fraction(claimed.get("profile_value_fraction"), "Candidate profile value")
    claimed_nash = _fraction(claimed.get("nash_conv_fraction"), "Candidate NashConv")
    legal_equilibrium = nash_conv == 0 and sb_gain == 0 and bb_gain == 0
    candidate_matches = claimed_value == profile_value and claimed_nash == nash_conv
    response_controls_hold = sb_clairvoyant >= sb_response and bb_clairvoyant <= bb_response
    passed = legal_equilibrium and candidate_matches and response_controls_hold
    return {
        "schema_version": 1,
        "status": "passed" if passed else "failed",
        "oracle": "independent-explicit-12-terminal-history-pure-response-v1",
        "candidate_artifact_sha256": witness["artifact_sha256"],
        "expected_original_candidate_sha256": CANDIDATE_SHA256,
        "spec_sha256": SPEC_SHA256,
        "pair_priors": [
            {"sb_hand": sb, "bb_hand": bb, "prior_fraction": str(priors[(sb, bb)]),
             "wins": physical_rows[(sb, bb)]["wins"],
             "ties": physical_rows[(sb, bb)]["ties"],
             "losses": physical_rows[(sb, bb)]["losses"],
             "boards": physical_rows[(sb, bb)]["boards"],
             "showdown_mean_fraction": str(physical_rows[(sb, bb)]["showdown_mean"])}
            for sb, bb in priors],
        "terminal_history_count": len(_TERMINALS),
        "information_set_row_count": len(policy),
        "pure_response_policies_per_hand": {"sb": 20, "bb": 24},
        "profile_value_fraction": str(profile_value),
        "sb_best_response_value_fraction": str(sb_response),
        "bb_minimum_sb_value_fraction": str(bb_response),
        "bb_best_response_value_fraction_sb_perspective": str(bb_response),
        "sb_best_response_gain_fraction": str(sb_gain),
        "bb_best_response_gain_fraction": str(bb_gain),
        "nash_conv_fraction": str(nash_conv),
        "legal_equilibrium_verified": legal_equilibrium,
        "candidate_profile_value_fraction": str(claimed_value),
        "candidate_nash_conv_fraction": str(claimed_nash),
        "candidate_claimed_value_matches": claimed_value == profile_value,
        "candidate_claimed_nash_conv_matches": claimed_nash == nash_conv,
        "sb_by_hand": sb_hands,
        "bb_by_hand": bb_hands,
        "illegal_clairvoyant_control": {
            "scope": "Illegal counterfactual: responder may condition a pure policy on the opponent's private hand.",
            "sb_value_fraction": str(sb_clairvoyant),
            "sb_value_weakly_at_least_legal": sb_clairvoyant >= sb_response,
            "sb_pair_values": sb_pair_controls,
            "bb_sb_perspective_value_fraction": str(bb_clairvoyant),
            "bb_value_weakly_at_most_legal": bb_clairvoyant <= bb_response,
            "bb_pair_values": bb_pair_controls,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="Pinned saved candidate witness JSON")
    parser.add_argument("--output", type=Path, required=True,
                        help="Path for the concise independent response summary")
    args = parser.parse_args(argv)
    witness = _load_json(args.input)
    result = public_pure_response(witness)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8", newline="\n")
    print(json.dumps({"candidate_artifact_sha256": result["candidate_artifact_sha256"],
                      "status": result["status"],
                      "profile_value_fraction": result["profile_value_fraction"],
                      "sb_best_response_value_fraction": result["sb_best_response_value_fraction"],
                      "bb_minimum_sb_value_fraction": result["bb_minimum_sb_value_fraction"],
                      "nash_conv_fraction": result["nash_conv_fraction"],
                      "legal_equilibrium_verified": result["legal_equilibrium_verified"]},
                     sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
