"""Rank-free, solve-local suit-orbit row plan; no expanded row lookup table.

This module plans storage only. It does not train, merge increments, change
admission caps, or certify a policy. Full row identities are regenerated from
the public graph and exact positive physical support when needed.
"""
from itertools import permutations
from types import MappingProxyType
from weakref import ref

from .cards import DECK
from .exact_selected_kernel import ExactSelectedRunoutKernel
from .preflop_solver import _revealed_board
from .shared_public_topology import DecisionVertex, ChanceVertex

_SUITS = "cdhs"
_ORDER = {card: index for index, card in enumerate(DECK)}
MAX_PLAN_WORK = 500_000_000
MAX_PLAN_ENTRIES = 2_000_000
MAX_PLAN_HISTORY_BYTES = 16_000_000


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) in (tuple, list):
        return tuple(_freeze(item) for item in value)
    return value


def _detached(value):
    if isinstance(value, MappingProxyType):
        return {key: _detached(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_detached(item) for item in value]
    return value


def _card(card, mapping):
    return card[0] + mapping[card[1]]


def _hand(hand, mapping):
    return tuple(sorted(_card(card, mapping) for card in hand))


def _history(history, mapping):
    result = []
    for token in history:
        if token.startswith("flop@"):
            cards = sorted((_card(token[i:i+2], mapping) for i in (5, 7, 9)),
                           key=_ORDER.__getitem__)
            result.append("flop@" + "".join(cards))
        elif token.startswith("turn@"):
            result.append("turn@" + _card(token[5:], mapping))
        elif token.startswith("river@"):
            result.append("river@" + _card(token[6:], mapping))
        else:
            result.append(token)
    return tuple(result)


def _prefix(history):
    board = _revealed_board(history)
    return () if not board else ("".join(board[:3]),) + tuple(board[3:])


def _group(kernel):
    priors = tuple(dict(zip(hands, weights))
                   for hands, weights in zip(kernel.hands, kernel.weights))
    selected = set(kernel.selected)
    result = []
    for image in permutations(_SUITS):
        mapping = dict(zip(_SUITS, image))
        if any({_hand(hand, mapping): weight for hand, weight in prior.items()} != prior
               for prior in priors):
            continue
        transformed = {
            (tuple(sorted((_card(card, mapping) for card in flop), key=_ORDER.__getitem__)),
             _card(turn, mapping), _card(river, mapping))
            for flop, turn, river in selected}
        if transformed == selected:
            result.append(image)
    return tuple(result)


def plan_admission(prepared, iterations, group_size):
    """Additional Q-plan/lookup envelope, retaining every old R-sized cap.

    Whole-solver integration must add these modeled units and entries to its
    existing admission BEFORE constructing a plan. No Q savings are credited.
    """
    if type(iterations) is not int or not 10 <= iterations <= 10_000:
        raise ValueError("Suit row plan requires 10 through 10,000 iterations.")
    if iterations != prepared.iterations:
        raise ValueError("Suit row plan iteration count differs from admitted preparation.")
    if type(group_size) is not int or not 1 <= group_size <= 24:
        raise ValueError("Suit row plan requires a group size from 1 through 24.")
    upper = prepared.layout_upper
    rows = upper["upper_dense_decision_hand_slots"]
    slots = upper["upper_action_slots"]
    tokens = upper["upper_history_token_entries"]
    byte_count = upper["upper_history_token_bytes"]
    hsum = sum(prepared.kernel.hand_counts)
    depth = upper["maximum_depth"] + 1
    prefixes = len(prepared.unique_prefixes)
    # Includes canonicalization, distinct-key sorting/comparison, set/hash
    # scans, bit checks and eventual expanded policy reconstruction. The model
    # counts logical units; it is not a bound on interpreter or allocator CPU.
    lookup = group_size * (128 * tokens + 256 * rows)
    work = ((3 * iterations + 8) * lookup +
            (6 * iterations + 8) * 32 * slots +
            24 * (16 * hsum + 32 * len(prepared.kernel.selected)))
    entries = (prefixes * (2 * hsum + 16) + group_size * (4 * hsum + 32) +
               40 * rows + 3 * tokens + 2 * slots +
               group_size * (8 * depth + 2 * byte_count + 64) + 1024)
    if work > MAX_PLAN_WORK or entries > MAX_PLAN_ENTRIES:
        raise ValueError("Suit row plan additional work/storage admission exceeded before row allocation.")
    if byte_count > MAX_PLAN_HISTORY_BYTES:
        raise ValueError("Suit row plan history-byte admission exceeded before row allocation.")
    return {"version": "suit-quotient-row-plan-admission-v1", "group_size": group_size,
            "iterations": iterations,
            "modeled_work_upper": work, "additional_retained_entries_upper": entries,
            "canonical_lookup_work_upper": lookup,
            "expanded_rows_upper": rows, "expanded_action_slots_upper": slots,
            "history_token_entries_upper": tokens, "history_bytes_upper": byte_count,
            "scope": "Additional modeled Q-plan/lookup units only; unchanged whole-solve and sorted-chance admission must also pass. No storage savings credited before allocation; not CPU, allocator or RSS."}


class SuitQuotientPlan:
    """One retained semantic key per orbit and bounded procedural member IDs.

    Construction streams all supported rows and verifies distinct-member
    coverage using one mask per Q record. It never retains R member identities.
    The kernel is weakly owned and its immutable input identities are bound.
    """
    __slots__ = ("_owner", "_hands", "_weights", "_selected", "_normalizer",
                 "topology", "group", "_maps", "_hand_maps", "_support",
                 "keys", "menus", "sizes", "expected_masks", "offsets",
                 "counts", "locations", "_receipt", "_admission", "_sealed")

    def __setattr__(self, name, value):
        if getattr(self, "_sealed", False):
            raise AttributeError("Suit row plan is immutable after construction.")
        object.__setattr__(self, name, value)

    @property
    def receipt(self):
        return _detached(self._receipt)

    @property
    def admission(self):
        return _detached(self._admission)

    def __init__(self, prepared, iterations):
        kernel = prepared.kernel
        if type(kernel) is not ExactSelectedRunoutKernel:
            raise TypeError("Suit row plan requires the exact selected kernel.")
        if type(iterations) is not int or iterations != prepared.iterations:
            raise ValueError("Suit row plan iteration count differs from admitted preparation.")
        # Bound the small weighted-group search before allocating its inputs.
        group_search = 24 * (16 * sum(kernel.hand_counts) + 32 * len(kernel.selected))
        old = prepared.admission
        group_entries = 32 * sum(kernel.hand_counts) + 16 * len(kernel.selected) + 2048
        if (group_search > MAX_PLAN_WORK or
                old["combined_modeled_work_upper"] + group_search > old["whole_request_limit"]):
            raise ValueError("Suit row plan group-search admission exceeded.")
        if (old["retained_storage"]["whole_request_peak_upper"] + group_entries >
                old["retained_storage"]["entry_limit"]):
            raise ValueError("Suit row plan group-search storage admission exceeded.")
        group = _group(kernel)
        admission = plan_admission(prepared, iterations, len(group))
        old = prepared.admission
        remaining_work = old["whole_request_limit"] - old["combined_modeled_work_upper"] - admission["modeled_work_upper"]
        retained = old["retained_storage"]
        remaining_entries = retained["entry_limit"] - retained["whole_request_peak_upper"] - admission["additional_retained_entries_upper"]
        if remaining_work <= 0:
            raise ValueError("Suit row plan whole-request additional work admission exceeded before support/row allocation.")
        if remaining_entries <= 0:
            raise ValueError("Suit row plan whole-request storage admission exceeded before support/row allocation.")
        from .suit_public_automorphism import (
            verify_public_suit_automorphisms, MAX_MODELED_WORK, MAX_RETAINED_ENTRIES,
        )
        graph = verify_public_suit_automorphisms(prepared.topology, group,
            max_additional_work=min(remaining_work, MAX_MODELED_WORK),
            max_additional_entries=min(remaining_entries, MAX_RETAINED_ENTRIES))
        added_work = admission["modeled_work_upper"] + graph["modeled_work_upper"]
        added_entries = admission["additional_retained_entries_upper"] + graph["additional_retained_entries_upper"]
        self._owner = ref(kernel)
        self._hands, self._weights = kernel.hands, kernel.weights
        self._selected, self._normalizer = kernel.selected, kernel.normalizer
        self.topology, self.group = prepared.topology, group
        self._maps = self._hand_maps = ()
        self._support = self.locations = None
        keys = menus = sizes = masks = offsets = counts = None
        rows = slots = qslots = history_tokens = history_bytes = 0
        try:
            self._admission = _freeze(admission)
            self._maps = tuple(MappingProxyType(dict(zip(_SUITS, image))) for image in group)
            hand_indices = tuple({hand: index for index, hand in enumerate(side)} for side in kernel.hands)
            self._hand_maps = tuple(tuple(tuple(hand_indices[player][_hand(hand, mapping)]
                for hand in kernel.hands[player]) for player in (0, 1)) for mapping in self._maps)
            self._support = {}
            for prefix in prepared.unique_prefixes:
                self._support[prefix] = tuple(frozenset(side) for side in kernel.legal_hands(prefix))
            self.locations = {}
            keys, menus, sizes, masks, offsets, counts = [], [], [], [], [], []
            for key, menu in self.iter_rows():
                representative, member, size = self.canonicalize(key)
                q = self.locations.get(representative)
                if q is None:
                    if len(keys) >= admission["expanded_rows_upper"]:
                        raise RuntimeError("Suit row plan exceeded admitted row envelope.")
                    q = len(keys)
                    self.locations[representative] = q
                    keys.append(representative)
                    menus.append(menu)
                    sizes.append(size)
                    masks.append(0)
                    offsets.append(qslots)
                    counts.append(len(menu))
                    qslots += len(menu)
                    history_tokens += len(representative[2])
                    history_bytes += sum(len(token.encode("utf-8")) for token in representative[2])
                if menus[q] != menu or sizes[q] != size:
                    raise ValueError("Suit orbit changed ordered action menu or distinct-member size.")
                bit = 1 << member
                if masks[q] & bit:
                    raise ValueError("Duplicate supported suit-orbit member occurrence.")
                masks[q] |= bit
                rows += 1
                slots += len(menu)
                if (rows > admission["expanded_rows_upper"] or
                        slots > admission["expanded_action_slots_upper"] or
                        history_tokens > admission["history_token_entries_upper"] or
                        history_bytes > admission["history_bytes_upper"]):
                    raise RuntimeError("Suit row plan exceeded its admitted rows/actions/history.")
            expected = tuple((1 << size) - 1 for size in sizes)
            if tuple(masks) != expected:
                raise ValueError("Suit row plan lost a distinct supported orbit member.")
            self.keys, self.menus, self.sizes = tuple(keys), tuple(menus), tuple(sizes)
            self.offsets, self.counts, self.expected_masks = tuple(offsets), tuple(counts), expected
            self.locations = MappingProxyType(self.locations)
            self._support = MappingProxyType(self._support)
            self._receipt = _freeze({"version": "suit-quotient-row-plan-v1", "expanded_information_rows": rows,
                "iterations": iterations,
                "expanded_action_slots": slots, "quotient_information_rows": len(keys),
                "quotient_action_slots": qslots, "group": ["".join(image) for image in group],
                "group_size": len(group), "quotient_history_token_entries": history_tokens,
                "quotient_history_token_bytes": history_bytes,
                "retained_expanded_row_lookup_entries": 0,
                "supported_member_count": sum(sizes), "public_graph_closure": graph,
                "whole_request_additional_work_upper": added_work,
                "whole_request_additional_entries_upper": added_entries,
                "four_quotient_numeric_buffers_projected_payload_bytes": 32 * qslots,
                "scope": "Rank-free row-storage plan only. Projected numeric payload is not allocated training storage, a solved policy, or a memory/RSS claim."})
            self._sealed = True
        except BaseException:
            if type(self.locations) is dict:
                self.locations.clear()
            if type(self._support) is dict:
                self._support.clear()
            self.locations, self._support = {}, {}
            self.keys = self.menus = self.sizes = self.expected_masks = ()
            self.offsets = self.counts = self._hand_maps = self._maps = ()
            raise
        finally:
            hand_indices = None
            for values in (keys, menus, sizes, masks, offsets, counts):
                if values is not None:
                    values.clear()

    def validate_owner(self):
        kernel = self._owner()
        if (kernel is None or kernel.hands is not self._hands or kernel.weights is not self._weights or
                kernel.selected is not self._selected or kernel.normalizer != self._normalizer):
            raise ValueError("Suit row plan input owner changed or expired.")
        return kernel

    def canonicalize(self, key):
        """Return representative, distinct-member ordinal and orbit size.

        Only at most 24 temporary transformed keys exist for this one lookup;
        deduplication handles nontrivial row stabilizers without coset tables.
        """
        self.validate_owner()
        if (type(key) is not tuple or len(key) != 3 or type(key[0]) is not int or
                key[0] not in (0, 1) or type(key[1]) is not int or
                not 0 <= key[1] < len(self._hands[key[0]]) or type(key[2]) is not tuple or
                any(type(token) is not str for token in key[2])):
            raise ValueError("Malformed suit row identity.")
        player, hand, history = key
        vertex = self._decision_at_history(history)
        if vertex.player != player:
            raise ValueError("Suit row player differs from the public history actor.")
        images = sorted({(player, hand_map[player][hand], _history(history, mapping))
                         for hand_map, mapping in zip(self._hand_maps, self._maps)})
        if key not in images:
            raise ValueError("Suit row group lost original member.")
        for image in images:
            prefix = _prefix(image[2])
            if prefix not in self._support or image[1] not in self._support[prefix][player]:
                raise ValueError("Suit row image lost positive physical support.")
        return images[0], images.index(key), len(images)

    def _decision_at_history(self, history):
        """Authenticate one path using unique edge labels, without a row map."""
        initial = self.topology.initial_history
        if len(history) < len(initial) or history[:len(initial)] != initial:
            raise ValueError("Suit row has a foreign initial public history.")
        index = self.topology.root_id
        for token in history[len(initial):]:
            vertex = self.topology.vertices[index]
            if isinstance(vertex, DecisionVertex):
                branches = ((action.token, child) for action, child in zip(vertex.actions, vertex.child_ids))
            elif isinstance(vertex, ChanceVertex):
                branches = ((vertex.street + "@" + label, child) for label, child in vertex.branches)
            else:
                raise ValueError("Suit row history continues beyond a terminal.")
            for label, child in branches:
                if label == token:
                    index = child
                    break
            else:
                raise ValueError("Suit row has an invalid action or public reveal history.")
        vertex = self.topology.vertices[index]
        if not isinstance(vertex, DecisionVertex):
            raise ValueError("Suit row history does not identify a public decision.")
        return vertex

    def locate(self, key):
        representative, member, size = self.canonicalize(key)
        q = self.locations.get(representative)
        if q is None or self.sizes[q] != size:
            raise ValueError("Suit row is outside admitted quotient support.")
        return q, self.offsets[q], 1 << member

    def supported_hand_indices(self, prefix, player):
        """Immutable positive physical support, independent of current reach."""
        self.validate_owner()
        if type(player) is not int or player not in (0, 1) or type(prefix) is not tuple:
            raise ValueError("Invalid suit row support query.")
        if prefix not in self._support:
            raise ValueError("Suit row prefix is outside admitted decision support.")
        return self._support[prefix][player]

    def iter_rows(self):
        """Stream physical supported row keys and immutable action menus."""
        self.validate_owner()
        for occurrence in self.topology.iter_occurrences():
            vertex = self.topology.vertices[occurrence.vertex_id]
            if isinstance(vertex, DecisionVertex):
                prefix = _prefix(occurrence.history)
                for hand in sorted(self._support[prefix][vertex.player]):
                    yield (vertex.player, hand, occurrence.history), vertex.actions
