from collections.abc import Mapping
from itertools import combinations, permutations

from scripts.preflop_validation import independent_rank

RANKS = "23456789TJQKA"
SUITS = "cdhs"
TOY_RANKS = "2345"


def _validate_mapping(mapping):
    if not isinstance(mapping, Mapping):
        raise TypeError("suit mapping must be a mapping from all four source suits")
    if set(mapping) != set(SUITS) or any(
            type(key) is not str or type(value) is not str
            or value not in SUITS for key, value in mapping.items()):
        raise ValueError("suit mapping must map exactly c, d, h, and s")
    if set(mapping.values()) != set(SUITS):
        raise ValueError("suit mapping must be a bijection over c, d, h, and s")
    return {suit: mapping[suit] for suit in SUITS}


def _map_card(card, mapping):
    if (not isinstance(card, str) or len(card) != 2
            or card[0] not in RANKS or card[1] not in SUITS):
        raise ValueError("cards must use canonical rank+suit strings")
    return card[0] + mapping[card[1]]


def _hand_cards(value):
    if isinstance(value, str):
        if len(value) != 4:
            raise ValueError("hand text must contain exactly two cards")
        hand = (value[:2], value[2:])
    else:
        try:
            hand = tuple(value)
        except TypeError as exc:
            raise ValueError("hand must be a two-card string or sequence") from exc
    if len(hand) != 2 or hand[0] == hand[1]:
        raise ValueError("hand must contain two distinct cards")
    for card in hand:
        if not isinstance(card, str) or len(card) != 2 or card[0] not in RANKS or card[1] not in SUITS:
            raise ValueError("hand contains a noncanonical card")
    return tuple(sorted(hand))


def mapped_counts(counts, mapping):
    """Map published pair-count rows through one global suit bijection.

    Player roles and all numeric W/T/L/board-count fields are preserved. The
    function is an independent audit utility and does not call the production
    suit-remap or canonicalization implementation.
    """
    suit_map = _validate_mapping(mapping)
    rows = []
    seen = set()
    for source in counts:
        if not isinstance(source, Mapping):
            raise TypeError("count rows must be mappings")
        if not {"sb_hand", "bb_hand", "wins", "ties", "losses"} <= set(source):
            raise ValueError("count row is missing a role hand or W/T/L count")
        sb = tuple(sorted(_map_card(card, suit_map) for card in _hand_cards(source["sb_hand"])))
        bb = tuple(sorted(_map_card(card, suit_map) for card in _hand_cards(source["bb_hand"])))
        if set(sb) & set(bb):
            raise ValueError("mapped private hands collide")
        key = (sb, bb)
        if key in seen:
            raise ValueError("suit mapping produced duplicate ordered pair rows")
        seen.add(key)
        row = dict(source)
        row["sb_hand"] = "".join(sb)
        row["bb_hand"] = "".join(bb)
        for field in ("wins", "ties", "losses"):
            if type(row[field]) is not int or row[field] < 0:
                raise ValueError("W/T/L counts must be nonnegative integers")
        if "boards" in row and (type(row["boards"]) is not int
                                 or row["boards"] != row["wins"] + row["ties"] + row["losses"]):
            raise ValueError("board count must equal W/T/L total")
        rows.append(row)
    return tuple(rows)


def _toy_rank(hand):
    return independent_rank(hand)


def verify_toy_suit_invariance():
    """Exhaustively verify one 16-card toy deal under all 24 suit images.

    The toy deck has ranks 2–5 in all four suits. It is deliberately not a
    substitute for the physical 52-card, 1,712,304-board-per-pair evidence.
    The only rank oracle is scripts.preflop_validation.independent_rank.
    """
    toy_deck = tuple(rank + suit for rank in TOY_RANKS for suit in SUITS)
    sb = ("5c", "5d")
    bb = ("4c", "4d")
    private = set(sb + bb)
    if not private <= set(toy_deck):
        raise AssertionError("toy private cards are outside the toy deck")
    remaining = tuple(card for card in toy_deck if card not in private)
    boards = tuple(combinations(remaining, 5))
    if len(boards) != 792:
        raise AssertionError("toy board census changed")

    base = {"wins": 0, "ties": 0, "losses": 0}
    base_signs = []
    for board in boards:
        sb_rank = _toy_rank(sb + board)
        bb_rank = _toy_rank(bb + board)
        sign = (sb_rank > bb_rank) - (sb_rank < bb_rank)
        base_signs.append(sign)
        base[{1: "wins", 0: "ties", -1: "losses"}[sign]] += 1

    full_deck = tuple(rank + suit for rank in RANKS for suit in SUITS)
    if len(full_deck) != 52 or len(set(full_deck)) != 52:
        raise AssertionError("independent standard deck definition is invalid")

    images = []
    comparisons = 0
    for permutation in permutations(SUITS):
        suit_map = _validate_mapping(dict(zip(SUITS, permutation)))
        mapped_full_deck = tuple(_map_card(card, suit_map) for card in full_deck)
        if len(set(mapped_full_deck)) != 52 or set(mapped_full_deck) != set(full_deck):
            raise AssertionError("suit image is not bijective over the 52-card deck")
        mapped_private = {_map_card(card, suit_map) for card in private}
        mapped_remaining = {_map_card(card, suit_map) for card in full_deck if card not in private}
        if (len(mapped_private) != 4 or len(mapped_remaining) != 48
                or mapped_private & mapped_remaining
                or mapped_private | mapped_remaining != set(full_deck)):
            raise AssertionError("private dead cards and remaining 48-card deck do not map exactly")

        mapped_sb = tuple(_map_card(card, suit_map) for card in sb)
        mapped_bb = tuple(_map_card(card, suit_map) for card in bb)
        mapped_toy_remaining = {_map_card(card, suit_map) for card in remaining}
        if mapped_toy_remaining != set(toy_deck) - set(mapped_sb) - set(mapped_bb):
            raise AssertionError("toy-deck dead-card complement did not map exactly")

        image_counts = {"wins": 0, "ties": 0, "losses": 0}
        for base_sign, board in zip(base_signs, boards):
            mapped_board = tuple(_map_card(card, suit_map) for card in board)
            if len(set(mapped_board)) != 5 or not set(mapped_board) <= mapped_toy_remaining:
                raise AssertionError("mapped board is not a legal toy-deck subset")
            sb_rank = _toy_rank(mapped_sb + mapped_board)
            bb_rank = _toy_rank(mapped_bb + mapped_board)
            image_sign = (sb_rank > bb_rank) - (sb_rank < bb_rank)
            if image_sign != base_sign:
                raise AssertionError("independent hand ordering changed under suit image")
            image_counts[{1: "wins", 0: "ties", -1: "losses"}[image_sign]] += 1
            comparisons += 1
        if image_counts != base:
            raise AssertionError("toy W/T/L measure changed under suit image")
        images.append({
            "suit_permutation": suit_map,
            "sb_hand": "".join(sorted(mapped_sb)),
            "bb_hand": "".join(sorted(mapped_bb)),
            **image_counts,
        })

    if len(images) != 24 or comparisons != 19_008:
        raise AssertionError("toy suit-image census changed")
    return {
        "model": "synthetic-16-card-deck-ranks-2-through-5",
        "physical_52_card_evidence": False,
        "rank_oracle": "scripts.preflop_validation.independent_rank",
        "source_sb_hand": "".join(sorted(sb)),
        "source_bb_hand": "".join(sorted(bb)),
        "toy_deck_cards": len(toy_deck),
        "toy_remaining_cards": len(remaining),
        "toy_boards_per_image": len(boards),
        "suit_images": len(images),
        "mapped_board_comparisons": comparisons,
        "source_counts": base,
        "all_images_match_source_counts": True,
        "standard_deck_cards_checked": len(full_deck),
        "standard_remaining_cards_checked": 48,
        "images": images,
    }
