"""Exact full-board equity remapping under joint poker suit symmetries."""
from fractions import Fraction
from itertools import permutations

from .cards import SUITS
from . import preflop_full_board_equity as equity

_SIGNS = (-1, 0, 1)
_SUIT_PERMUTATIONS = tuple(permutations(SUITS))


def _mapped_hand(hand, suit_map):
    """Map one validated two-card hand and retain canonical card order."""
    return tuple(sorted(card[0] + suit_map[card[1]] for card in hand))


def _mapped_pair_key(pair, permutation):
    suit_map = dict(zip(SUITS, permutation))
    return (_mapped_hand(pair[0], suit_map), _mapped_hand(pair[1], suit_map))


def _canonical_pair_key(pair):
    """Canonicalize both hands using the same one of the 24 suit maps."""
    return min(_mapped_pair_key(pair, permutation)
               for permutation in _SUIT_PERMUTATIONS)


def _permutation_between(source_pair, target_pair):
    """Return a deterministic full suit bijection mapping source to target."""
    for permutation in _SUIT_PERMUTATIONS:
        suit_map = dict(zip(SUITS, permutation))
        if (len(suit_map) == 4 and set(suit_map) == set(SUITS)
                and set(suit_map.values()) == set(SUITS)
                and (_mapped_hand(source_pair[0], suit_map),
                     _mapped_hand(source_pair[1], suit_map)) == target_pair):
            return tuple((suit, suit_map[suit]) for suit in SUITS)
    raise ValueError("No joint suit permutation maps the covered source pair to the requested pair.")


def _resolve_pairs(table, plan):
    """Resolve every planned pair to a consistent source orbit representative."""
    source_orbits = {}
    for (sb_index, bb_index, _), counts in zip(table.pairs, table.counts):
        source_pair = (table.hands[0][sb_index], table.hands[1][bb_index])
        key = _canonical_pair_key(source_pair)
        previous = source_orbits.get(key)
        if previous is None:
            source_orbits[key] = (source_pair, counts)
        elif previous[1] != counts:
            raise ValueError("Source table has inconsistent win/tie/loss counts within a suit orbit.")

    resolved = []
    for sb_index, bb_index, _ in plan.pairs:
        target_pair = (plan.hands[0][sb_index], plan.hands[1][bb_index])
        key = _canonical_pair_key(target_pair)
        source = source_orbits.get(key)
        if source is None:
            raise ValueError("Requested compatible private pair suit orbit is not covered by the source table.")
        source_pair, counts = source
        suit_mapping = _permutation_between(source_pair, target_pair)
        resolved.append((source_pair, counts, suit_mapping))
    return tuple(resolved)


def _inputs(table, sb_range, bb_range):
    if not isinstance(table, equity.FullBoardEquities):
        raise TypeError("table must be a FullBoardEquities instance")
    table.validate()
    plan = equity.plan_preflop_equities(sb_range, bb_range)
    # Resolve every pair before the caller allocates categorical output rows.
    resolved = _resolve_pairs(table, plan)
    return plan, resolved


def preflop_suit_remap_provenance(table, sb_range, bb_range):
    """Return deterministic JSON-safe source-pair/suit-map rows for a remap.

    Each map is a bijection over all four suit labels and maps both source hand
    endpoints to the requested target endpoints, preserving SB/BB roles.
    """
    plan, resolved = _inputs(table, sb_range, bb_range)
    rows = []
    for (sb_index, bb_index, _), (source_pair, _, suit_mapping) in zip(plan.pairs, resolved):
        rows.append({
            "target_sb_hand": "".join(plan.hands[0][sb_index]),
            "target_bb_hand": "".join(plan.hands[1][bb_index]),
            "source_sb_hand": "".join(source_pair[0]),
            "source_bb_hand": "".join(source_pair[1]),
            "suit_permutation": dict(suit_mapping),
        })
    return tuple(rows)


def remap_preflop_equities_by_suit(table, sb_range, bb_range):
    """Reuse covered ordered pair counts through exact joint suit symmetry.

    Counts are copied only when a single bijection of all four suits maps both
    source hands to the requested hands. SB/BB roles remain ordered. The source
    table must cover every requested pair orbit and must agree on counts when
    it contains multiple representatives of the same orbit. This function
    never ranks hands, enumerates boards, persists a cache, or mutates `table`.
    """
    plan, resolved = _inputs(table, sb_range, bb_range)
    counts = tuple(row[1] for row in resolved)
    pairs = tuple(plan.pairs)
    worlds = []
    for (sb_index, bb_index, prior), (wins, ties, losses) in zip(pairs, counts):
        for sign, count in zip(_SIGNS, (losses, ties, wins)):
            if count:
                mass = prior * Fraction(count, equity.BOARDS_PER_PAIR)
                worlds.append((sb_index, bb_index,
                               equity._as_positive_float(mass, "categorical mass"), sign))

    result = equity.FullBoardEquities(
        hands=plan.hands,
        pairs=pairs,
        counts=counts,
        worlds=tuple(worlds),
        _budget_items=plan._budget_items,
    )
    result.validate()
    return result
