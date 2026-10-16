"""Exact fixed-flop equity transfer under global suit permutations.

For each transferred role-ordered private-hand pair, one bijection of all four
suits maps the source board and both hands to the target. Different target
pairs may use different bijections. No cards are ranked here.
"""
from itertools import permutations

from .cards import DECK, SUITS
from .flop_checkdown_equity import FlopCheckdownEquities
from .flop_checkdown_worlds import prepare_flop_worlds

_DECK_ORDER = {card: index for index, card in enumerate(DECK)}
_SUIT_PERMUTATIONS = tuple(permutations(SUITS))


def _map_hand(hand, suit_map):
    """Apply one global suit bijection and restore range-hand order."""
    return tuple(sorted(card[0] + suit_map[card[1]] for card in hand))


def _map_board(board, suit_map):
    """Apply one global suit bijection and restore canonical board order."""
    return tuple(sorted((card[0] + suit_map[card[1]] for card in board),
                        key=_DECK_ORDER.__getitem__))


def _map_joint(board, pair, permutation):
    """Map the board and ordered private hands using one constructed map."""
    suit_map = dict(zip(SUITS, permutation))
    return (_map_board(board, suit_map),
            _map_hand(pair[0], suit_map),
            _map_hand(pair[1], suit_map))


def _canonical_joint_key(board, pair):
    """Canonicalize board and ordered OOP/IP hands under one of 24 suit maps."""
    return min(_map_joint(board, pair, permutation)
               for permutation in _SUIT_PERMUTATIONS)


def _source_orbits(table):
    """Index source representatives and reject inconsistent count orbits."""
    orbits = {}
    for (oop_index, ip_index, _), counts in zip(table.pairs, table.counts):
        pair = (table.hands[0][oop_index], table.hands[1][ip_index])
        key = _canonical_joint_key(table.board, pair)
        previous = orbits.get(key)
        if previous is None:
            orbits[key] = (pair, counts)
        elif previous[1] != counts:
            raise ValueError(
                "Source table has inconsistent win/tie/loss counts within a joint suit orbit."
            )
    return orbits


def _permutation_between(source_board, source_pair, target_board, target_pair):
    """Return the first full SUITS-order bijection mapping all source endpoints."""
    for permutation in _SUIT_PERMUTATIONS:
        suit_map = dict(zip(SUITS, permutation))
        if (len(suit_map) == 4 and set(suit_map) == set(SUITS)
                and set(suit_map.values()) == set(SUITS)
                and _map_board(source_board, suit_map) == target_board
                and _map_hand(source_pair[0], suit_map) == target_pair[0]
                and _map_hand(source_pair[1], suit_map) == target_pair[1]):
            return tuple((suit, suit_map[suit]) for suit in SUITS)
    raise ValueError("No global suit permutation maps source board and private hands to target.")


def _resolve(table, target_board, oop_range, ip_range):
    if type(table) is not FlopCheckdownEquities:
        raise TypeError("table must be a FlopCheckdownEquities instance.")
    table.validate()
    # This performs exact target-board range expansion and all existing pair/
    # board-work caps; it does not enumerate future boards or rank hands.
    plan = prepare_flop_worlds(target_board, oop_range, ip_range)
    orbits = _source_orbits(table)
    resolved = []
    for oop_index, ip_index, _ in plan.pairs:
        target_pair = (plan.hands[0][oop_index], plan.hands[1][ip_index])
        key = _canonical_joint_key(plan.board, target_pair)
        source = orbits.get(key)
        if source is None:
            raise ValueError(
                "Requested compatible board/private-hand suit orbit is not covered by the source table."
            )
        source_pair, counts = source
        suit_map = _permutation_between(table.board, source_pair, plan.board, target_pair)
        resolved.append((source_pair, counts, suit_map))
    return plan, tuple(resolved)


def flop_suit_remap_provenance(table, target_board, oop_range, ip_range):
    """Return fresh JSON-safe source/target endpoints and full suit bijections.

    Rows are returned in target compatible-pair order, with source selection by
    the first matching table pair and mapping selection by ``SUITS`` permutation
    order. OOP/IP roles are retained and never swapped.
    """
    plan, resolved = _resolve(table, target_board, oop_range, ip_range)
    rows = []
    for (oop_index, ip_index, _), (source_pair, _, suit_map) in zip(plan.pairs, resolved):
        rows.append({
            "source_board": list(table.board),
            "target_board": list(plan.board),
            "source_oop_hand": "".join(source_pair[0]),
            "source_ip_hand": "".join(source_pair[1]),
            "target_oop_hand": "".join(plan.hands[0][oop_index]),
            "target_ip_hand": "".join(plan.hands[1][ip_index]),
            "suit_permutation": dict(suit_map),
        })
    return tuple(rows)


def remap_flop_checkdown_equities_by_suit(table, target_board, oop_range, ip_range):
    """Reuse pair counts when each target pair has a global suit mapping.

    The target board and range plan are validated under the same existing
    resource caps as ordinary fixed-flop preparation. For each target pair, a
    single four-suit permutation must map the full source board and ordered
    source OOP/IP hands to the target board and that target pair. The mapping
    may differ between target pairs. Every target pair is resolved before
    output construction, and source-orbit count disagreements reject rather
    than choosing an arbitrary count.
    """
    plan, resolved = _resolve(table, target_board, oop_range, ip_range)
    result = FlopCheckdownEquities(
        board=tuple(plan.board),
        hands=tuple(tuple(tuple(hand) for hand in player_hands) for player_hands in plan.hands),
        pairs=tuple((oop_index, ip_index, prior)
                    for oop_index, ip_index, prior in plan.pairs),
        counts=tuple(counts for _, counts, _ in resolved),
        _budget_items=tuple(plan.budget.items()),
    )
    result.validate()
    return result
