"""Deterministic global-suit remapping for the fixed blocker turn game."""
from __future__ import annotations

from copy import deepcopy
from itertools import permutations
import json
import math
import re

from pokerlab.cards import cards as parse_cards, expand_range

SOURCE_SUITS = "cdhs"
SUIT_PERMUTATIONS = tuple("".join(p) for p in permutations(SOURCE_SUITS))
_CARD = re.compile(r"^[2-9TJQKA][cdhs]$")
_CARD_PAIR = re.compile(r"^(?:[2-9TJQKA][cdhs]){2}$")
_CARD_SEQUENCE = re.compile(r"^(?:[2-9TJQKA][cdhs]){1,7}$")
_RANGE_TOKEN = re.compile(r"^((?:[2-9TJQKA][cdhs]){2})(?::([^:,]+))?$")


def permutation_map(target: str) -> dict[str, str]:
    """Map each source suit in cdhs order to the corresponding target suit."""
    if type(target) is not str or len(target) != len(SOURCE_SUITS) or set(target) != set(SOURCE_SUITS):
        raise ValueError("target must be a bijective permutation of cdhs")
    return dict(zip(SOURCE_SUITS, target))


def inverse_target(target: str) -> str:
    mapping = permutation_map(target)
    return "".join(next(source for source, dest in mapping.items() if dest == suit)
                   for suit in SOURCE_SUITS)


def _parse_canonical_cards(value, count=None):
    """Parse card input only when its written spelling is already canonical."""
    if isinstance(value, str):
        if not _CARD_SEQUENCE.fullmatch(value) or len(value) % 2:
            raise ValueError("card sequence must use canonical rank/suit spelling")
        raw_cards = tuple(value[index:index + 2] for index in range(0, len(value), 2))
    elif type(value) in (list, tuple):
        raw_cards = tuple(value)
        if any(type(card) is not str or not _CARD.fullmatch(card) for card in raw_cards):
            raise ValueError("cards must use canonical rank/suit spelling")
    else:
        raise TypeError("cards must be a card string, list, or tuple")
    parsed = tuple(parse_cards(value, count=count))
    if parsed != raw_cards:
        raise ValueError("card parser changed the supplied card spelling")
    return parsed


def map_card(card: str, target: str) -> str:
    mapping = permutation_map(target)
    parsed = _parse_canonical_cards(card, count=1)[0]
    return parsed[0] + mapping[parsed[1]]


def _shape_like(original, cards):
    if isinstance(original, str):
        return "".join(cards)
    if isinstance(original, tuple):
        return tuple(cards)
    if isinstance(original, list):
        return list(cards)
    raise TypeError("cards must be a card string, list, or tuple")


def map_cards(value, target: str):
    """Map a board/card sequence without changing its card order or container type."""
    permutation_map(target)
    cards = _parse_canonical_cards(value)
    return _shape_like(value, (map_card(card, target) for card in cards))


def map_hand(hand, target: str) -> str:
    """Map one hand and return the parser-canonical two-card identity."""
    cards = _parse_canonical_cards(hand, count=2)
    mapped = "".join(map_card(card, target) for card in cards)
    canonical = expand_range(mapped)
    if len(canonical) != 1:
        raise ValueError("mapped hand did not resolve to one explicit combo")
    combo = next(iter(canonical))
    return "".join(combo)


def map_explicit_range(expression: str, target: str) -> str:
    """Map explicit two-card combo tokens positionally, preserving weight literals.

    Whitespace and abstract range syntax are rejected intentionally. The existing
    range parser canonicalizes each mapped identity for validation; the written
    card positions remain in source order so an inverse map restores the exact
    input range text, including its original weight literals.
    """
    permutation_map(target)
    if type(expression) is not str or not expression or any(ch.isspace() for ch in expression):
        raise ValueError("range must be a nonempty comma-separated explicit range without whitespace")
    mapped_tokens, seen = [], set()
    for token in expression.split(","):
        match = _RANGE_TOKEN.fullmatch(token)
        if match is None:
            raise ValueError("only explicit two-card range combos are supported")
        raw_hand, weight_literal = match.groups()
        original = expand_range(raw_hand)
        if len(original) != 1:
            raise ValueError("range token must identify exactly one combo")
        if weight_literal is not None:
            try:
                weight = float(weight_literal)
            except ValueError as exc:
                raise ValueError("invalid explicit range weight") from exc
            if not math.isfinite(weight) or not 0 <= weight <= 1:
                raise ValueError("range weight must be finite and between zero and one")
        mapped_hand = "".join(map_card(card, target) for card in _parse_canonical_cards(raw_hand, count=2))
        canonical = expand_range(mapped_hand)
        if len(canonical) != 1:
            raise ValueError("mapped range token did not resolve to one combo")
        identity = next(iter(canonical))
        if identity in seen:
            raise ValueError("range contains duplicate canonical combos")
        seen.add(identity)
        mapped_tokens.append(mapped_hand + (":" + weight_literal if weight_literal is not None else ""))
    return ",".join(mapped_tokens)


def _validate_fixture(fixture):
    required = {"id", "board", "oop", "ip", "runouts", "config"}
    if type(fixture) is not dict or set(fixture) != required:
        raise ValueError("unsupported fixture shape")
    board = _parse_canonical_cards(fixture["board"], count=4)
    runouts = tuple(_parse_canonical_cards(card, count=1)[0] for card in fixture["runouts"])
    if not runouts or len(set(board + runouts)) != len(board) + len(runouts):
        raise ValueError("fixture board and selected runouts must be distinct cards")
    for side in ("oop", "ip"):
        expand_range(fixture[side], dead=board)
    return board, runouts


def transform_fixture(fixture: dict, target: str) -> dict:
    """Deep-copy and remap the fixed fixture with one global suit bijection."""
    permutation_map(target)
    board, runouts = _validate_fixture(fixture)
    mapped = deepcopy(fixture)
    mapped["board"] = map_cards(fixture["board"], target)
    mapped["oop"] = map_explicit_range(fixture["oop"], target)
    mapped["ip"] = map_explicit_range(fixture["ip"], target)
    mapped["runouts"] = [map_card(card, target) for card in runouts]
    _validate_fixture(mapped)
    for side in ("oop", "ip"):
        before = expand_range(fixture[side], dead=board)
        after_board, _after_runouts = _validate_fixture(mapped)
        after = expand_range(mapped[side], dead=after_board)
        expected = {tuple(_parse_canonical_cards(map_hand("".join(hand), target), count=2)): weight
                    for hand, weight in before.items()}
        if after != expected:
            raise ValueError("global suit map changed explicit range support or weights")
    return mapped


def _map_history(history, target):
    if type(history) is not list or any(type(token) is not str for token in history):
        raise ValueError("strategy history must be a list of action tokens")
    result = []
    for token in history:
        if token.startswith("river@"):
            card = token[len("river@"):]
            if not _CARD.fullmatch(card):
                raise ValueError("malformed future river marker")
            result.append("river@" + map_card(card, target))
        else:
            result.append(token)
    return result


def _validate_strategy_row(row):
    if type(row) is not dict or not {"hand", "board", "history"} <= set(row):
        raise ValueError("strategy row lacks hand, board, or history identity")
    hand = row["hand"]
    if type(hand) is not str or map_hand(hand, SOURCE_SUITS) != hand:
        raise ValueError("strategy hand identity must be parser-canonical")
    board = _parse_canonical_cards(row["board"])
    if len(board) not in (4, 5) or set(hand[i:i+2] for i in (0, 2)) & set(board):
        raise ValueError("strategy board/hand identity is malformed or colliding")
    history = row["history"]
    if type(history) is not list or any(type(token) is not str for token in history):
        raise ValueError("strategy history must be a list of action tokens")
    markers = []
    for token in history:
        if token.startswith("river@"):
            marker = token[len("river@"):]
            if not _CARD.fullmatch(marker):
                raise ValueError("malformed future river marker")
            markers.append(_parse_canonical_cards(marker, count=1)[0])
    if len(markers) > 1 or (len(board) == 5) != (len(markers) == 1):
        raise ValueError("river board and future reveal marker are inconsistent")
    if markers and board[-1] != markers[0]:
        raise ValueError("river history marker does not match the revealed board card")


def transform_rows(rows: list[dict], target: str) -> list[dict]:
    """Deep-copy and remap strategy rows, preserving every action/numeric field."""
    permutation_map(target)
    if type(rows) is not list:
        raise TypeError("strategy rows must be a list")
    copied = deepcopy(rows)
    for row in copied:
        _validate_strategy_row(row)
        row["hand"] = map_hand(row["hand"], target)
        row["board"] = map_cards(row["board"], target)
        row["history"] = _map_history(row["history"], target)
        _validate_strategy_row(row)
    return copied


def _map_card_sequence_field(value, target):
    if type(value) not in (str, list, tuple):
        raise ValueError("card sequence field must be a string, list, or tuple")
    return map_cards(value, target)


def _suspicious_card_string(value):
    return bool(_CARD_SEQUENCE.fullmatch(value) or value.startswith("river@"))


def _check_unhandled_cards(value, path=()):
    """Reject card-bearing data outside the explicitly transformed schema."""
    if type(value) is str:
        if not _suspicious_card_string(value):
            return
        sequence_parents = {
            ("board",), ("runouts",), ("reachable_runouts",), ("selected_runouts",),
            ("fixture", "board"), ("fixture", "runouts"),
        }
        if path in sequence_parents or (
            len(path) == 2 and isinstance(path[1], int) and (path[0],) in sequence_parents
        ):
            return
        if path in (("fixture", "oop"), ("fixture", "ip")):
            return
        if len(path) == 3 and path[0] == "strategy" and path[2] == "hand":
            return
        if len(path) == 4 and path[0] == "strategy" and path[2] == "board":
            return
        if len(path) == 4 and path[0] == "strategy" and path[2] == "history" and value.startswith("river@"):
            return
        raise ValueError("unsupported card-bearing field at " + ".".join(map(str, path)))
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is str and _suspicious_card_string(key):
                raise ValueError("unsupported card-bearing dictionary key at " +
                                 ".".join(map(str, path + (key,))))
            _check_unhandled_cards(child, path + (key,))
    elif type(value) in (list, tuple):
        for index, child in enumerate(value):
            _check_unhandled_cards(child, path + (index,))


def transform_result(result: dict, target: str) -> dict:
    """Deep-copy a complete production result and remap every supported card field."""
    permutation_map(target)
    if type(result) is not dict or "board" not in result or "strategy" not in result:
        raise ValueError("expected a complete production result with board and strategy")
    _check_unhandled_cards(result)
    copied = deepcopy(result)
    for name in ("board", "runouts", "reachable_runouts", "selected_runouts"):
        if name in copied:
            copied[name] = _map_card_sequence_field(copied[name], target)
    if "fixture" in copied:
        copied["fixture"] = transform_fixture(copied["fixture"], target)
    copied["strategy"] = transform_rows(copied["strategy"], target)
    _check_unhandled_cards(copied)
    return copied


def canonical_json(value) -> bytes:
    """Canonical JSON bytes used by archived production policy files."""
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")
