"""Candidate-only exact partitioning for supplied physical flop worlds.

This staging module is not an independent physical oracle and does not rank,
train, or certify. The caller must provide a complete trusted physical record
set for the game under study; this module checks only its structure and exact
mass identities.
"""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
import re

RANKS = "23456789TJQKA"
SUITS = "cdhs"
DECK = tuple(rank + suit for rank in RANKS for suit in SUITS)
_DECK_INDEX = {card: index for index, card in enumerate(DECK)}
_MASS_RE = re.compile(r"[0-9]+(?:/[1-9][0-9]*)?\Z")
MAX_MASS_COMPONENT_DIGITS = 128
MAX_MASS_TEXT_CHARS = 2 * MAX_MASS_COMPONENT_DIGITS + 1
MAX_MASS_INTEGER_BITS = 384
MAX_PAIRS = 3
MAX_WORLDS = 5_940
MAX_TURNS = 49


def _fail(condition, message):
    if not condition:
        raise ValueError(message)


def _cards(value, *, count, label):
    _fail(type(value) in (list, tuple) and len(value) == count,
          f"{label} must contain exactly {count} cards")
    cards = tuple(value)
    _fail(all(type(card) is str and card in _DECK_INDEX for card in cards),
          f"{label} contains an invalid card")
    _fail(len(set(cards)) == count, f"{label} contains duplicate cards")
    return cards


def _hand(label, name):
    _fail(type(name) is str and len(name) == 4,
          f"{label} must be a four-character two-card hand")
    cards = (name[:2], name[2:])
    _fail(all(card in _DECK_INDEX for card in cards) and cards[0] != cards[1],
          f"{label} contains invalid or duplicate cards")
    return frozenset(cards)


def _mass(value):
    # Bound text before regex/int parsing so attacker-controlled huge decimal
    # strings never reach Python's arbitrary-precision integer parser.
    _fail(type(value) is str and len(value) <= MAX_MASS_TEXT_CHARS,
          "world mass fraction text exceeds its size limit")
    _fail(_MASS_RE.fullmatch(value) is not None,
          "world mass must be a positive exact fraction string")
    if "/" in value:
        numerator_text, denominator_text = value.split("/", 1)
    else:
        numerator_text, denominator_text = value, "1"
    _fail(len(numerator_text) <= MAX_MASS_COMPONENT_DIGITS
          and len(denominator_text) <= MAX_MASS_COMPONENT_DIGITS,
          "world mass integer exceeds its digit limit")
    numerator, denominator = int(numerator_text), int(denominator_text)
    _fail(numerator.bit_length() <= MAX_MASS_INTEGER_BITS
          and denominator.bit_length() <= MAX_MASS_INTEGER_BITS,
          "world mass integer exceeds its bit limit")
    result = Fraction(numerator, denominator)
    _fail(result > 0, "world mass must be positive")
    return result


def _pair_label(pair):
    return (pair[0], pair[1])


def _fraction_pair(value):
    return [value.numerator, value.denominator]


def _sort_cards(cards):
    return tuple(sorted(cards, key=_DECK_INDEX.__getitem__))


def build_candidate(physical_worlds, *, board=("2c", "3d", "4h")):
    """Build exact candidate classes from supplied ordered physical records.

    Each record is ``[oop_hand, ip_hand, mass_fraction_string, sign, board5]``.
    Cards in each private hand are kept as supplied for display, while their
    physical identity is a sorted card pair. Signatures include absent pair
    outcomes explicitly. Equality is exact; no proportional-mass relaxation
    or rank/suit heuristic is used.
    """
    board = _cards(board, count=3, label="flop board")
    _fail(type(physical_worlds) in (list, tuple),
          "physical_worlds must be a list or tuple of records")
    _fail(0 < len(physical_worlds) <= MAX_WORLDS,
          "physical-world count must be in [1, 5940]")

    parsed = []
    pair_display = {}
    seen = set()
    for index, record in enumerate(physical_worlds):
        _fail(type(record) in (list, tuple) and len(record) == 5,
              f"physical world {index} must have five fields")
        oop_name, ip_name, raw_mass, sign, full_board = record
        oop_cards = _hand("OOP hand", oop_name)
        ip_cards = _hand("IP hand", ip_name)
        _fail(oop_cards.isdisjoint(ip_cards), "private hands overlap")
        _fail(oop_cards.isdisjoint(board) and ip_cards.isdisjoint(board),
              "private hand overlaps the flop")
        _fail(type(sign) is int and sign in (-1, 0, 1),
              "showdown sign must be integer -1, 0, or 1")
        full_board = _cards(full_board, count=5, label="full board")
        _fail(full_board[:3] == board, "full board must begin with the supplied flop")
        turn, river = full_board[3:]
        _fail(oop_cards.isdisjoint((turn, river)) and
              ip_cards.isdisjoint((turn, river)),
              "private hand overlaps a future board card")
        mass = _mass(raw_mass)
        pair = (_sort_cards(oop_cards), _sort_cards(ip_cards))
        labels = (oop_name, ip_name)
        previous = pair_display.setdefault(pair, labels)
        _fail(previous == labels,
              "one physical private pair has inconsistent hand labels")
        key = (pair, turn, river)
        _fail(key not in seen, "duplicate ordered private-pair/turn/river world")
        seen.add(key)
        parsed.append({"pair": pair, "turn": turn, "river": river,
                       "mass": mass, "sign": sign, "board": full_board})

    pairs = tuple(sorted(pair_display, key=lambda p: (p[0], p[1])))
    _fail(0 < len(pairs) <= MAX_PAIRS,
          "candidate input supports at most three private pairs")
    _fail(sum((row["mass"] for row in parsed), Fraction(0)) == 1,
          "physical world masses must sum globally to one")
    pair_marginals = {pair: Fraction(0) for pair in pairs}
    for row in parsed:
        pair_marginals[row["pair"]] += row["mass"]
    _fail(all(mass > 0 for mass in pair_marginals.values()),
          "each private pair must have positive physical support")

    turns = tuple(sorted({row["turn"] for row in parsed}, key=_DECK_INDEX.__getitem__))
    _fail(len(turns) <= MAX_TURNS, "candidate input exceeds 49 turn cards")
    pair_index = {pair: index for index, pair in enumerate(pairs)}

    # For each (turn, river), make one ordered signature over all physical
    # private pairs. A missing pair outcome is a first-class signature value.
    by_turn_river = defaultdict(dict)
    turn_mass = {turn: {pair: Fraction(0) for pair in pairs} for turn in turns}
    for row in parsed:
        pair, turn, river = row["pair"], row["turn"], row["river"]
        by_turn_river[(turn, river)][pair] = row
        turn_mass[turn][pair] += row["mass"]

    river_signatures = {}
    for turn in turns:
        rivers = sorted({river for t, river in by_turn_river if t == turn},
                        key=_DECK_INDEX.__getitem__)
        for river in rivers:
            present = by_turn_river[(turn, river)]
            signature = tuple(
                (1, present[pair]["mass"].numerator,
                 present[pair]["mass"].denominator, present[pair]["sign"])
                if pair in present else (0, 0, 0, 0)
                for pair in pairs
            )
            river_signatures[(turn, river)] = signature

    # Give globally identical exact vectors stable IDs in first-seen deck order.
    signature_ids = {}
    river_classes = []
    river_class_by_member = {}
    for turn in turns:
        rivers = sorted({river for t, river in river_signatures if t == turn},
                        key=_DECK_INDEX.__getitem__)
        for river in rivers:
            signature = river_signatures[(turn, river)]
            if signature not in signature_ids:
                class_id = len(signature_ids)
                signature_ids[signature] = class_id
                river_classes.append({
                    "id": class_id,
                    "signature": [
                        {"oop_hand": pair_display[pair][0],
                         "ip_hand": pair_display[pair][1],
                         "present": bool(item[0]),
                         "mass": [item[1], item[2]] if item[0] else None,
                         "sign": item[3] if item[0] else None}
                        for pair, item in zip(pairs, signature)
                    ],
                    "members": [],
                })
            class_id = signature_ids[signature]
            river_class_by_member[(turn, river)] = class_id
            river_classes[class_id]["members"].append({"turn": turn, "river": river})

    turn_keys = {}
    for turn in turns:
        turn_vector = tuple(turn_mass[turn][pair] for pair in pairs)
        river_multiset = tuple(sorted(
            river_class_by_member[(turn, river)]
            for t, river in river_class_by_member if t == turn
        ))
        turn_keys[turn] = (turn_vector, river_multiset)

    turn_key_ids = {}
    turn_classes = []
    turn_class_by_member = {}
    for turn in turns:
        key = turn_keys[turn]
        if key not in turn_key_ids:
            class_id = len(turn_key_ids)
            turn_key_ids[key] = class_id
            turn_classes.append({
                "id": class_id,
                "representative": turn,
                "members": [],
                "turn_mass_by_pair": [
                    {"oop_hand": pair_display[pair][0],
                     "ip_hand": pair_display[pair][1],
                     "mass": _fraction_pair(turn_mass[turn][pair])}
                    for pair in pairs
                ],
                "river_transports": [],
            })
        class_id = turn_key_ids[key]
        turn_class_by_member[turn] = class_id
        turn_classes[class_id]["members"].append(turn)

    # Construct deterministic per-turn river bijections to each class
    # representative, matching members only within identical signatures.
    for turn_class in turn_classes:
        representative = turn_class["representative"]
        representative_rivers = defaultdict(list)
        for (turn, river), river_class_id in river_class_by_member.items():
            if turn == representative:
                representative_rivers[river_class_id].append(river)
        for turn in turn_class["members"]:
            member_rivers = defaultdict(list)
            for (candidate_turn, river), river_class_id in river_class_by_member.items():
                if candidate_turn == turn:
                    member_rivers[river_class_id].append(river)
            _fail(set(member_rivers) == set(representative_rivers),
                  "turn-class river supports differ")
            for river_class_id in sorted(representative_rivers):
                source = sorted(member_rivers[river_class_id], key=_DECK_INDEX.__getitem__)
                target = sorted(representative_rivers[river_class_id], key=_DECK_INDEX.__getitem__)
                _fail(len(source) == len(target), "turn-class river multiplicities differ")
                turn_class["river_transports"].extend(
                    {"turn": turn, "river": source_river,
                     "representative_turn": representative,
                     "representative_river": target_river,
                     "river_class_id": river_class_id}
                    for source_river, target_river in zip(source, target)
                )
        turn_class["river_transports"].sort(
            key=lambda row: (_DECK_INDEX[row["turn"]], _DECK_INDEX[row["river"]]))

    aggregate = {}
    coverage = defaultdict(int)
    for row in parsed:
        pair = row["pair"]
        turn_class_id = turn_class_by_member[row["turn"]]
        river_class_id = river_class_by_member[(row["turn"], row["river"])]
        key = (pair, turn_class_id, river_class_id)
        if key not in aggregate:
            aggregate[key] = {"mass": Fraction(0), "sign": row["sign"], "source_worlds": 0}
        _fail(aggregate[key]["sign"] == row["sign"],
              "an aggregate class world combines different showdown signs")
        aggregate[key]["mass"] += row["mass"]
        aggregate[key]["source_worlds"] += 1
        coverage[(row["pair"], row["turn"], row["river"])] += 1
    _fail(len(coverage) == len(parsed) and all(value == 1 for value in coverage.values()),
          "not every original physical world maps exactly once")

    class_worlds = []
    for (pair, turn_class_id, river_class_id), value in sorted(
            aggregate.items(), key=lambda item: (pair_index[item[0][0]], item[0][1], item[0][2])):
        class_worlds.append({
            "oop_hand": pair_display[pair][0],
            "ip_hand": pair_display[pair][1],
            "turn_class_id": turn_class_id,
            "river_class_id": river_class_id,
            "mass": _fraction_pair(value["mass"]),
            "sign": value["sign"],
            "physical_world_count": value["source_worlds"],
        })

    output_marginals = {pair: Fraction(0) for pair in pairs}
    for row in class_worlds:
        pair = next(pair for pair in pairs
                    if pair_display[pair] == (row["oop_hand"], row["ip_hand"]))
        output_marginals[pair] += Fraction(*row["mass"])
    _fail(output_marginals == pair_marginals,
          "candidate classes changed a private-pair marginal")
    _fail(sum((Fraction(*row["mass"]) for row in class_worlds), Fraction(0)) == 1,
          "candidate class masses do not sum globally to one")
    _fail(sum(row["physical_world_count"] for row in class_worlds) == len(parsed),
          "candidate classes do not cover every original world exactly once")

    return {
        "schema_version": "flop-public-classes-candidate-v1",
        "board": list(board),
        "candidate_only": True,
        "input_completeness": "unverified-caller-supplied-records",
        "physical_provenance": False,
        "physical_world_count": len(parsed),
        "compatible_pair_count": len(pairs),
        "turn_card_count": len(turns),
        "river_class_count": len(river_classes),
        "turn_class_count": len(turn_classes),
        "physical_mass": [1, 1],
        "pairs": [
            {"oop_hand": pair_display[pair][0], "ip_hand": pair_display[pair][1],
             "marginal_mass": _fraction_pair(pair_marginals[pair])}
            for pair in pairs
        ],
        "river_classes": river_classes,
        "turn_classes": turn_classes,
        "class_worlds": class_worlds,
        "scope": (
            "Exact candidate partition of supplied structural records only. No ranking, "
            "physical provenance, full-tree equivalence, policy projection/lifting, "
            "best-response equality, or training has been certified."
        ),
    }
