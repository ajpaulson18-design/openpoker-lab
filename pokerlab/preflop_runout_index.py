"""Bounded per-card bitsets for blocker queries over selected runouts.

Runouts use the solver's canonical shape ``(sorted_flop, turn, river)``. The
index stores only one posting bitset per card; callers can query a private
four-card blocker set without retaining per-pair masks.
"""

from itertools import islice


MAX_SELECTED_RUNOUTS = 300_000
_DECK = tuple(rank + suit for rank in "23456789TJQKA" for suit in "cdhs")
_CARD_INDEX = {card: index for index, card in enumerate(_DECK)}


def _checked_runouts(selected):
    if isinstance(selected, (str, bytes)):
        raise ValueError("selected runouts must be a nonempty sequence")
    try:
        iterator = iter(selected)
    except TypeError as exc:
        raise ValueError("selected runouts must be iterable") from exc

    result = []
    seen = set()
    for runout in iterator:
        if len(result) >= MAX_SELECTED_RUNOUTS:
            raise ValueError("selected runouts exceed the configured outcome limit")
        try:
            parts = tuple(islice(iter(runout), 4))
        except TypeError as exc:
            raise ValueError("runouts must be (flop, turn, river) triples") from exc
        if len(parts) != 3:
            raise ValueError("runouts must be (flop, turn, river) triples")
        try:
            flop = tuple(islice(iter(parts[0]), 4))
        except TypeError as exc:
            raise ValueError("each flop must contain three cards") from exc
        if len(flop) != 3:
            raise ValueError("each flop must contain three cards")
        cards = flop + (parts[1], parts[2])
        if any(not isinstance(card, str) or card not in _CARD_INDEX for card in cards):
            raise ValueError("runout contains an invalid card")
        if len(set(cards)) != 5:
            raise ValueError("runout cards must be distinct")
        if tuple(sorted(flop, key=_CARD_INDEX.__getitem__)) != flop:
            raise ValueError("flop cards must be in canonical deck order")
        if cards in seen:
            raise ValueError("duplicate canonical ordered runout")
        seen.add(cards)
        result.append(cards)
    if not result:
        raise ValueError("at least one selected runout is required")
    return tuple(result)


def _build_postings(runouts):
    """Build bytearray postings, then compact each into a single integer."""
    byte_count = (len(runouts) + 7) // 8
    buffers = [bytearray(byte_count) for _ in _DECK]
    for runout_index, runout in enumerate(runouts):
        byte_index, bit = divmod(runout_index, 8)
        bit_value = 1 << bit
        for card in runout:
            buffers[_CARD_INDEX[card]][byte_index] |= bit_value
    postings = tuple(int.from_bytes(buffer, "little") for buffer in buffers)
    buffers = None
    return postings


class RunoutBlockerIndex:
    """Index canonical selected outcomes for bounded blocker queries.

    ``posting_payload_bytes`` reports the compact logical bit payload.
    ``estimated_conversion_payload_bytes`` counts two logical payloads for the
    bytearray/integer conversion overlap. It excludes Python integer limb
    padding and headers, runout normalization/duplicate-check storage, masks,
    query scratch, and all other object overhead; it is not an allocation/RSS
    bound.
    """

    __slots__ = ("_selected_count", "_postings", "_all_mask", "_byte_count")

    def __init__(self, selected):
        runouts = _checked_runouts(selected)
        self._selected_count = len(runouts)
        self._byte_count = (self._selected_count + 7) // 8
        self._postings = _build_postings(runouts)
        self._all_mask = (1 << self._selected_count) - 1
        runouts = None

    @property
    def selected_count(self):
        return self._selected_count

    @property
    def posting_payload_bytes(self):
        return len(_DECK) * self._byte_count

    @property
    def estimated_conversion_payload_bytes(self):
        """Logical bytearray-plus-integer payload overlap, not a memory bound."""
        return 2 * self.posting_payload_bytes

    def _blocked_mask(self, private_cards):
        if isinstance(private_cards, (str, bytes)):
            raise ValueError("private_cards must contain four distinct cards")
        try:
            cards = tuple(islice(iter(private_cards), 5))
        except TypeError as exc:
            raise ValueError("private_cards must contain four distinct cards") from exc
        if (len(cards) != 4 or
                any(not isinstance(card, str) or card not in _CARD_INDEX
                    for card in cards) or len(set(cards)) != 4):
            raise ValueError("private_cards must contain four distinct valid cards")
        postings = self._postings
        blocked = postings[_CARD_INDEX[cards[0]]] | postings[_CARD_INDEX[cards[1]]]
        blocked |= postings[_CARD_INDEX[cards[2]]]
        blocked |= postings[_CARD_INDEX[cards[3]]]
        return self._all_mask & ~blocked

    def valid_mask(self, private_cards):
        """Return an integer mask whose set bits are unblocked runout indexes."""
        return self._blocked_mask(private_cards)

    def valid_count(self, private_cards):
        """Count selected outcomes disjoint from the four private cards."""
        return self._blocked_mask(private_cards).bit_count()

    def iter_valid_indices(self, private_cards):
        """Yield valid selected-outcome indexes in ascending input order.

        A single packed byte string is scanned once, avoiding repeated large
        integer clearing/copying for every yielded world.
        """
        packed = self._blocked_mask(private_cards).to_bytes(self._byte_count, "little")
        for byte_index, byte in enumerate(packed):
            while byte:
                low_bit = byte & -byte
                bit_index = low_bit.bit_length() - 1
                runout_index = byte_index * 8 + bit_index
                if runout_index < self.selected_count:
                    yield runout_index
                byte ^= low_bit

