"""Exact rational chance and terminal kernel for selected complete runouts.

This is an explicit new chance law (``exact-product-selected-v1``).  Parsed
binary64 range weights are snapshotted as their exact rational values.  Every
compatible private-pair/selected-board occurrence has mass ``wi * wj / Z``;
the common physical-board divisor cancels.  This module does not enumerate
private pairs or worlds, and does not change the legacy selected operator.

Resource counters are conservative modeled work and logical retained/scratch
entries.  They are admission controls, not CPU, allocator-byte, or RSS bounds.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from fractions import Fraction
from itertools import islice
import math
from numbers import Real
from types import MappingProxyType

from .cards import DECK, expand_range, rank_hand
from .preflop_solver import _requested_runouts

_CARD_BIT = {card: 1 << i for i, card in enumerate(DECK)}
_MAX_RANK_CACHE_BOARDS = 64
_MAX_RANGE_TEXT_CHARS = 16_384
_VERSION = "exact-product-selected-v1"


@dataclass(frozen=True, slots=True)
class ExactSelectedKernelLimits:
    """Immutable admission envelope for one exact selected-kernel instance."""

    max_hands_per_side: int = 1326
    max_boards: int = 64
    max_integer_bits: int = 65536
    max_modeled_work: int = 500_000_000
    max_storage_entries: int = 2_000_000

    def __post_init__(self):
        for name in ("max_hands_per_side", "max_boards", "max_integer_bits",
                     "max_modeled_work", "max_storage_entries"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer.")
        if self.max_hands_per_side > 1326 or self.max_boards > 64:
            raise ValueError("Limits cannot exceed 1,326 hands per side or 64 selected boards.")
        if self.max_integer_bits > 65536 or self.max_modeled_work > 500_000_000:
            raise ValueError("Limits cannot exceed 65,536 bits or 500 million modeled work units.")
        if self.max_storage_entries > 2_000_000:
            raise ValueError("max_storage_entries cannot exceed 2,000,000 entries.")


def _range_snapshot(value, label, max_hands):
    parsed = expand_range(value) if isinstance(value, str) else value
    if not hasattr(parsed, "items") or not parsed:
        raise TypeError(f"{label} must be a nonempty range string or hand-to-weight mapping.")
    try:
        declared_count = len(parsed)
        if declared_count > max_hands:
            raise ValueError(f"{label} exceeds the {max_hands}-hand limit.")
        bounded_items = tuple(islice(iter(parsed.items()), declared_count + 1))
    except (TypeError, AttributeError) as exc:
        raise TypeError(f"{label} must be a sized hand-to-weight mapping.") from exc
    if declared_count > max_hands or len(bounded_items) > max_hands:
        raise ValueError(f"{label} exceeds the {max_hands}-hand limit.")
    if len(bounded_items) != declared_count:
        raise ValueError(f"{label} mapping length disagrees with its bounded item iterator.")
    hands, weights, seen = [], [], set()
    for raw_hand, raw_weight in bounded_items:
        if not isinstance(raw_hand, (tuple, list)) or len(raw_hand) != 2:
            raise ValueError(f"{label} hands must contain two cards.")
        # Use the repository parser for canonical card validation and sorting.
        from .cards import cards
        # Keep expand_range's lexical public identity order; deck ordering is
        # used only for internal card indices and flop canonicalization.
        hand = tuple(sorted(cards(raw_hand, 2)))
        if hand in seen:
            raise ValueError(f"{label} contains duplicate hands after card canonicalization.")
        seen.add(hand)
        if isinstance(raw_weight, bool) or not isinstance(raw_weight, Real):
            raise TypeError(f"{label} weights must be real numbers, not booleans.")
        try:
            value = float(raw_weight)
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"{label} weights must be finite and positive.") from exc
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{label} weights must be finite and positive.")
        hands.append(hand)
        weights.append(Fraction.from_float(value))
    return tuple(hands), tuple(weights)


class ExactSelectedRunoutKernel:
    """Exact product-prior kernel over at most 64 selected complete boards.

    ``sb_range`` and ``bb_range`` accept the ordinary range strings or mappings
    from canonical two-card hands to finite positive numeric weights. Input hand
    order is retained. Batched queries use card buckets and never scan private
    pairs; ``pair_probability_exact`` is the explicitly linear-in-boards query.
    """

    _IMMUTABLE_INPUTS = frozenset({"limits", "rank_cache_boards", "hands", "weights",
                                   "hand_counts", "selected", "normalizer", "_hand_masks",
                                   "_board_masks", "_flop_keys", "_hand_indexes", "_weight_maps"})

    def __setattr__(self, name, value):
        if getattr(self, "_initialized", False) and name in self._IMMUTABLE_INPUTS:
            raise AttributeError(f"{name} is an immutable exact-kernel snapshot.")
        object.__setattr__(self, name, value)

    def __init__(self, sb_range, bb_range, runouts, *, rank_cache_boards=1,
                 limits=None):
        if limits is None:
            limits = ExactSelectedKernelLimits()
        if not isinstance(limits, ExactSelectedKernelLimits):
            raise TypeError("limits must be ExactSelectedKernelLimits.")
        if type(rank_cache_boards) is not int or not 1 <= rank_cache_boards <= _MAX_RANK_CACHE_BOARDS:
            raise ValueError("rank_cache_boards must be an integer from 1 through 64.")
        self.limits = limits
        self._work = 0
        self._entries_peak = 0
        self._unsupported = 0
        self._queries = 0
        self._rank_calls = self._rank_sweeps = self._cache_hits = self._cache_misses = 0
        self._cache_evictions = 0
        self._rank_cache = OrderedDict()
        self.rank_cache_boards = rank_cache_boards

        # Bound source cardinality and reserve retained/scratch entries before
        # constructing detached hand, mask, and bucket representations.
        dimensions = []
        range_parse_work = 0
        for source, label in ((sb_range, "sb_range"), (bb_range, "bb_range")):
            if isinstance(source, str):
                bounded_chars = min(len(source), _MAX_RANGE_TEXT_CHARS)
                # Each whitespace-delimited token may expand to the entire
                # 1,326-combo deck (repeated "random" tokens are legal input).
                token_bound = (bounded_chars + 1) // 2
                range_parse_work += 1326 * token_bound + 8 * bounded_chars + 512
                dimensions.append(1326)
            else:
                try:
                    count = len(source)
                except Exception as exc:
                    raise TypeError(f"{label} must be a range string or sized mapping.") from exc
                if count > limits.max_hands_per_side:
                    raise ValueError(f"{label} exceeds the {limits.max_hands_per_side}-hand limit.")
                dimensions.append(1326)
        if isinstance(runouts, (str, bytes)):
            raise ValueError("runouts must be a nonempty sequence of five-card outcomes.")
        try:
            runout_count = len(runouts)
        except TypeError:
            runout_count = None
        preliminary_boards = limits.max_boards
        preliminary_entries = 18 * sum(dimensions) + 3 * preliminary_boards + 512
        cache_entries = (rank_cache_boards + 1) * sum(dimensions)
        self._reserve_entries(preliminary_entries + cache_entries)
        self._reserve_work(range_parse_work)
        for source, label in ((sb_range, "sb_range"), (bb_range, "bb_range")):
            if isinstance(source, str) and len(source) > _MAX_RANGE_TEXT_CHARS:
                self._unsupported += 1
                raise ValueError(f"{label} exceeds the {_MAX_RANGE_TEXT_CHARS}-character parse limit.")
        self._reserve_work(16 * sum(dimensions) + 512)
        self._reserve_work(8 * (limits.max_boards + 1))
        self._reserve_work(preliminary_boards * (16 * sum(dimensions) + 512))
        try:
            runout_take_limit = limits.max_boards + 1 if runout_count is None else min(
                limits.max_boards, runout_count) + 1
            bounded_runouts = tuple(islice(iter(runouts), runout_take_limit))
        except TypeError as exc:
            raise ValueError("runouts must be a nonempty sequence of five-card outcomes.") from exc
        if len(bounded_runouts) > limits.max_boards:
            self._unsupported += 1
            raise ValueError(f"Selected runouts exceed the {limits.max_boards}-board limit.")
        if runout_count is not None and len(bounded_runouts) != runout_count:
            self._unsupported += 1
            raise ValueError("runouts length disagrees with its bounded iterator.")
        runouts = bounded_runouts
        sb_hands, sb_weights = _range_snapshot(sb_range, "sb_range", limits.max_hands_per_side)
        bb_hands, bb_weights = _range_snapshot(bb_range, "bb_range", limits.max_hands_per_side)
        self.hands = (sb_hands, bb_hands)
        self.weights = (sb_weights, bb_weights)
        self.hand_counts = tuple(map(len, self.hands))
        if any(n > limits.max_hands_per_side for n in self.hand_counts):
            raise ValueError("Range exceeds the per-side hand limit.")
        selected = _requested_runouts(runouts)
        if len(selected) > limits.max_boards:
            raise ValueError(f"Selected runouts exceed the {limits.max_boards}-board limit.")
        self.selected = tuple(selected)
        term_count = self.hand_counts[0] * self.hand_counts[1] * len(self.selected)
        max_num = max(w.numerator.bit_length() for side in self.weights for w in side)
        max_den = max(w.denominator.bit_length() for side in self.weights for w in side)
        dyadic_sum_bits = 2 * max(max_num, max_den) + math.ceil(math.log2(max(1, term_count))) + 2
        if dyadic_sum_bits > limits.max_integer_bits:
            self._unsupported += 1
            raise ValueError("Exact selected-kernel integer-bit preflight exceeded.")
        self._hand_masks = tuple(tuple(_CARD_BIT[c[0]] | _CARD_BIT[c[1]] for c in side)
                                 for side in self.hands)
        self._board_masks = tuple(sum(_CARD_BIT[c] for c in flop + (turn, river))
                                  for flop, turn, river in self.selected)
        self._flop_keys = tuple("".join(flop) for flop, _turn, _river in self.selected)
        base_entries = 18 * sum(self.hand_counts) + 3 * len(self.selected) + 512
        cache_entries = (rank_cache_boards + 1) * sum(self.hand_counts)

        self._hand_indexes = tuple(MappingProxyType({h: i for i, h in enumerate(side)})
                                   for side in self.hands)
        self._weight_maps = tuple(MappingProxyType({h: w for h, w in zip(hs, ws)})
                                  for hs, ws in zip(self.hands, self.weights))
        self.normalizer = Fraction(0)
        self._support_count = [0, 0]
        self._support_pair_board_occurrences = 0
        for board_mask in self._board_masks:
            visible = tuple(tuple((i, h, w) for i, (h, w) in enumerate(zip(self.hands[p], self.weights[p]))
                                  if not (board_mask & self._hand_masks[p][i]))
                            for p in (0, 1))
            totals = self._bucket(visible[1])
            unit_totals = self._bucket(visible[1], unit=True)
            board_mass = Fraction(0)
            for i, hand, weight in visible[0]:
                compatible = self._compatible(hand, totals)
                self._support_pair_board_occurrences += int(self._compatible(hand, unit_totals))
                if compatible:
                    self._support_count[0] += 1
                    board_mass = self._add(board_mass, self._mul(weight, compatible))
            totals0 = self._bucket(visible[0], unit=True)
            for _j, hand, _weight in visible[1]:
                if self._compatible(hand, totals0):
                    self._support_count[1] += 1
            self.normalizer = self._add(self.normalizer, board_mass)
        if self.normalizer <= 0:
            raise ValueError("Selected runouts contain no positive compatible physical deals.")
        self._input_entries = base_entries
        self._cache_reserved_entries = cache_entries
        self._initialized = True

    def _reserve_work(self, amount):
        if type(amount) is not int or amount < 0 or self._work + amount > self.limits.max_modeled_work:
            self._unsupported += 1
            raise ValueError("Exact selected-kernel modeled-work limit exceeded.")
        self._work += amount

    def _reserve_entries(self, amount):
        if type(amount) is not int or amount < 0 or amount > self.limits.max_storage_entries:
            self._unsupported += 1
            raise ValueError("Exact selected-kernel retained-plus-scratch entry limit exceeded.")
        self._entries_peak = max(self._entries_peak, amount)

    def _check_bits(self, *values):
        bound = max((max(abs(v.numerator).bit_length(), v.denominator.bit_length())
                     for v in values), default=1)
        if bound > self.limits.max_integer_bits:
            self._unsupported += 1
            raise ValueError("Exact selected-kernel integer-bit limit exceeded.")

    def _add(self, left, right):
        if not left:
            return right
        if not right:
            return left
        # gcd-based exact forecast avoids constructing an over-limit Fraction.
        g = math.gcd(left.denominator, right.denominator)
        left_factor = right.denominator // g
        right_factor = left.denominator // g
        den_bits = right_factor.bit_length() + right.denominator.bit_length()
        num_bound = max(abs(left.numerator).bit_length() + left_factor.bit_length(),
                        abs(right.numerator).bit_length() + right_factor.bit_length()) + 1
        if max(den_bits, num_bound) > self.limits.max_integer_bits:
            self._unsupported += 1
            raise ValueError("Exact selected-kernel integer-bit forecast exceeded.")
        result = left + right
        self._check_bits(result)
        return result

    def _mul(self, left, right):
        if not left or not right:
            return Fraction(0)
        # Cross-cancel before multiplying; forecast the reduced result first.
        a = math.gcd(abs(left.numerator), right.denominator)
        b = math.gcd(abs(right.numerator), left.denominator)
        left_num_bits = (abs(left.numerator) // a).bit_length()
        right_num_bits = (abs(right.numerator) // b).bit_length()
        left_den_bits = (left.denominator // b).bit_length()
        right_den_bits = (right.denominator // a).bit_length()
        nbits = left_num_bits + right_num_bits
        dbits = left_den_bits + right_den_bits
        if max(nbits, dbits) > self.limits.max_integer_bits:
            self._unsupported += 1
            raise ValueError("Exact selected-kernel integer-bit forecast exceeded.")
        result = left * right
        self._check_bits(result)
        return result

    def _bucket(self, rows, *, unit=False):
        total = Fraction(0)
        card = [Fraction(0) for _ in range(52)]
        exact = {}
        for _i, hand, weight in rows:
            value = Fraction(1) if unit else weight
            total = self._add(total, value)
            card[DECK.index(hand[0])] = self._add(card[DECK.index(hand[0])], value)
            card[DECK.index(hand[1])] = self._add(card[DECK.index(hand[1])], value)
            exact[hand] = value
        return total, tuple(card), exact

    def _compatible(self, hand, bucket):
        total, card_sums, exact = bucket
        return self._add(self._sub(self._sub(total, card_sums[DECK.index(hand[0])]),
                                   card_sums[DECK.index(hand[1])]), exact.get(hand, 0))

    def _sub(self, left, right):
        return self._add(left, -right)

    def _prefix_indexes(self, prefix):
        self._queries += 1
        # Charge token validation and a complete selected-board lookup before
        # validation failures or zero-support paths can return.
        self._reserve_work(64 + 8 * len(self.selected))
        self._reserve_entries(self._input_entries + self._cache_reserved_entries + 64)
        if isinstance(prefix, (str, bytes)):
            self._unsupported += 1
            raise ValueError("Prefix must be empty, a flop, flop plus turn, or a complete runout.")
        try:
            prefix = tuple(islice(iter(prefix), 4))
        except TypeError as exc:
            self._unsupported += 1
            raise ValueError("Invalid selected-runout prefix.") from exc
        if len(prefix) > 3:
            self._unsupported += 1
            raise ValueError("Prefix must be empty, a flop, flop plus turn, or a complete runout.")
        if not prefix:
            return tuple(range(len(self.selected)))
        if (not isinstance(prefix[0], str) or len(prefix[0]) != 6 or
                any(card not in DECK for card in (prefix[0][i:i+2] for i in range(0, 6, 2)))):
            self._unsupported += 1
            raise ValueError("Flop prefix must be a six-character three-card token.")
        try:
            flop_cards = (prefix[0][0:2], prefix[0][2:4], prefix[0][4:6])
            if len(set(flop_cards)) != 3:
                raise ValueError
            if tuple(sorted(flop_cards, key=DECK.index)) != flop_cards:
                raise ValueError
            if len(prefix) >= 2 and prefix[1] not in DECK:
                raise ValueError
            if len(prefix) >= 3 and prefix[2] not in DECK:
                raise ValueError
            if len(prefix) >= 2 and prefix[1] in flop_cards:
                raise ValueError
            if len(prefix) >= 3 and prefix[2] in (*flop_cards, prefix[1]):
                raise ValueError
        except (TypeError, ValueError) as exc:
            self._unsupported += 1
            raise ValueError("Malformed or colliding selected-runout prefix.") from exc
        if len(prefix) == 1:
            return tuple(i for i, value in enumerate(self._flop_keys) if value == prefix[0])
        if len(prefix) == 2:
            return tuple(i for i, (flop, turn, _river) in enumerate(self.selected)
                         if "".join(flop) == prefix[0] and turn == prefix[1])
        return tuple(i for i, (flop, turn, river) in enumerate(self.selected)
                     if "".join(flop) == prefix[0] and turn == prefix[1] and river == prefix[2])

    def prefix_mass_exact(self, prefix=()):
        indexes = self._prefix_indexes(prefix)
        bound = len(indexes) * (20 * sum(self.hand_counts) + 260)
        self._reserve_work(bound)
        self._reserve_entries(self._input_entries + self._cache_reserved_entries +
                              12 * sum(self.hand_counts) + 600)
        mass = Fraction(0)
        for k in indexes:
            blocked = self._board_masks[k]
            rows0 = tuple((i, h, w) for i, (h, w) in enumerate(zip(self.hands[0], self.weights[0]))
                          if not (blocked & self._hand_masks[0][i]))
            rows1 = tuple((i, h, w) for i, (h, w) in enumerate(zip(self.hands[1], self.weights[1]))
                          if not (blocked & self._hand_masks[1][i]))
            bucket1 = self._bucket(rows1)
            board_mass = Fraction(0)
            for _i, hand, weight in rows0:
                board_mass = self._add(board_mass, self._mul(weight, self._compatible(hand, bucket1)))
            mass = self._add(mass, board_mass)
        return self._divide(mass, self.normalizer)

    def joint_marginals_exact(self, prefix=()):
        indexes = self._prefix_indexes(prefix)
        work = len(indexes) * (20 * sum(self.hand_counts) + 260)
        self._reserve_work(work)
        self._reserve_entries(self._input_entries + self._cache_reserved_entries +
                              12 * sum(self.hand_counts) + 600)
        out = [[Fraction(0) for _ in self.hands[p]] for p in (0, 1)]
        for k in indexes:
            blocked = self._board_masks[k]
            rows = tuple(tuple((i, h, w) for i, (h, w) in enumerate(zip(self.hands[p], self.weights[p]))
                               if not (blocked & self._hand_masks[p][i])) for p in (0, 1))
            buckets = (self._bucket(rows[0]), self._bucket(rows[1]))
            for p in (0, 1):
                for i, hand, weight in rows[p]:
                    value = self._mul(weight, self._compatible(hand, buckets[1-p]))
                    out[p][i] = self._add(out[p][i], value)
        return tuple(tuple(self._divide(x, self.normalizer) for x in side) for side in out)

    def _divide(self, a, b):
        # Division by a Fraction is multiplication by its reciprocal, forecasted.
        return self._mul(a, Fraction(b.denominator, b.numerator))

    def pair_probability_exact(self, i, j, prefix=()):
        self._reserve_work(16)
        if type(i) is not int or type(j) is not int or not (0 <= i < self.hand_counts[0]) or not (0 <= j < self.hand_counts[1]):
            self._unsupported += 1
            raise ValueError("Pair indexes are outside the input hand dimensions.")
        indexes = self._prefix_indexes(prefix)
        self._reserve_work(len(indexes) * 4 + 2)
        self._reserve_entries(self._input_entries + self._cache_reserved_entries + 64)
        mask = self._hand_masks[0][i] | self._hand_masks[1][j]
        if self._hand_masks[0][i] & self._hand_masks[1][j]:
            return Fraction(0)
        count = sum(not (self._board_masks[k] & mask) for k in indexes)
        return self._divide(self._mul(self._mul(self.weights[0][i], self.weights[1][j]), Fraction(count)), self.normalizer)

    def legal_hands(self, prefix=()):
        indexes = self._prefix_indexes(prefix)
        self._reserve_work(len(indexes) * (24 * sum(self.hand_counts) + 104))
        self._reserve_entries(self._input_entries + self._cache_reserved_entries +
                              12 * sum(self.hand_counts) + 600)
        supported = [set(), set()]
        for k in indexes:
            blocked = self._board_masks[k]
            rows = tuple(tuple((i, h, w) for i, (h, w) in enumerate(zip(self.hands[p], self.weights[p]))
                               if not (blocked & self._hand_masks[p][i])) for p in (0, 1))
            b0, b1 = self._bucket(rows[0], unit=True), self._bucket(rows[1], unit=True)
            for p in (0, 1):
                for i, h, _w in rows[p]:
                    if self._compatible(h, (b1, b0)[p]):
                        supported[p].add(i)
        return tuple(frozenset(x) for x in supported)

    def reachable_selected(self):
        # Rank-free support of complete selected boards.
        self._reserve_work(len(self.selected) * (24 * sum(self.hand_counts) + 104))
        self._reserve_entries(self._input_entries + self._cache_reserved_entries +
                              12 * sum(self.hand_counts) + 600)
        result = []
        for k, blocked in enumerate(self._board_masks):
            rows = tuple(tuple((i, h, w) for i, (h, w) in enumerate(zip(self.hands[p], self.weights[p]))
                               if not (blocked & self._hand_masks[p][i])) for p in (0, 1))
            buckets = (self._bucket(rows[0], unit=True), self._bucket(rows[1], unit=True))
            if any(self._compatible(h, buckets[1-p])
                   for p in (0, 1) for _i, h, _w in rows[p]):
                result.append(self.selected[k])
        return tuple(result)

    def _rank_vectors(self, k):
        if k in self._rank_cache:
            self._cache_hits += 1
            self._rank_cache.move_to_end(k)
            return self._rank_cache[k]
        self._cache_misses += 1
        self._reserve_entries(self._input_entries + self._cache_reserved_entries)
        board = self.selected[k][0] + self.selected[k][1:]
        vectors = []
        for p in (0, 1):
            ranked = []
            for i, hand in enumerate(self.hands[p]):
                if self._board_masks[k] & self._hand_masks[p][i]:
                    ranked.append(None)
                else:
                    ranked.append(rank_hand(hand + board))
                    self._rank_calls += 1
            vectors.append(tuple(ranked))
        vectors = tuple(vectors)
        if len(self._rank_cache) >= self.rank_cache_boards:
            self._rank_cache.popitem(last=False)
            self._cache_evictions += 1
        self._rank_cache[k] = vectors
        self._rank_sweeps += 1
        return vectors

    def terminal_values_exact(self, prefix, *, kind, payoff, player, opponent_reach):
        self._reserve_work(16)
        if kind not in ("fold", "showdown"):
            self._unsupported += 1
            raise ValueError("kind must be 'fold' or 'showdown'.")
        if type(player) is not int or player not in (0, 1):
            self._unsupported += 1
            raise ValueError("player must be 0 or 1.")
        if isinstance(payoff, bool) or not isinstance(payoff, Real):
            if not isinstance(payoff, Fraction):
                raise TypeError("payoff must be numeric.")
        scale = self._snapshot_nonnegative(payoff, "payoff", allow_signed=kind == "fold")
        if kind == "showdown" and scale < 0:
            raise ValueError("showdown payoff scale must be nonnegative.")
        try:
            reach_count = len(opponent_reach)
        except TypeError as exc:
            self._unsupported += 1
            raise ValueError("Opponent reach must be a sized sequence.") from exc
        if isinstance(opponent_reach, (str, bytes)) or reach_count != self.hand_counts[1-player]:
            raise ValueError("Opponent reach must match the opponent hand count.")
        # Reserve complete query work and reach/output/sort scratch before any
        # per-query vectors, buckets, or rank vectors are created.
        indexes = self._prefix_indexes(prefix)
        rank_sort_work = sum(self.hand_counts) * (math.ceil(math.log2(max(2, sum(self.hand_counts)))) + 1)
        self._reserve_work(len(indexes) * (200 * sum(self.hand_counts) + 520 + rank_sort_work) +
                           4 * self.hand_counts[1-player])
        self._reserve_entries(self._input_entries + self._cache_reserved_entries +
                              140 * sum(self.hand_counts) + 800)
        # A sized user object can lie about its length or yield indefinitely.
        # Consume at most one sentinel beyond the opponent dimension, after
        # reserving the full query envelope and before any reach snapshot,
        # cache lookup, rank call, or per-board bucket allocation.
        try:
            raw_reach = tuple(islice(iter(opponent_reach), self.hand_counts[1-player] + 1))
        except TypeError as exc:
            self._unsupported += 1
            raise ValueError("Opponent reach must be a bounded sized sequence.") from exc
        if len(raw_reach) != self.hand_counts[1-player]:
            self._unsupported += 1
            raise ValueError("Opponent reach length disagrees with its bounded iterator.")
        reach = tuple(self._snapshot_nonnegative(x, "opponent_reach") for x in raw_reach)
        self._preflight_terminal_bits(reach, scale, player, len(indexes))
        answer = [Fraction(0) for _ in self.hands[player]]
        own_side, opp_side = player, 1-player
        sign = 1 if player == 0 else -1
        for k in indexes:
            blocked = self._board_masks[k]
            opp_rows = [(j, hand, self._mul(self.weights[opp_side][j], reach[j]))
                        for j, hand in enumerate(self.hands[opp_side])
                        if not (blocked & self._hand_masks[opp_side][j])]
            if kind == "fold":
                bucket = self._bucket(opp_rows)
                own_rows = ((i, h, w) for i, (h, w) in enumerate(zip(self.hands[own_side], self.weights[own_side]))
                            if not (blocked & self._hand_masks[own_side][i]))
                for i, hand, own_weight in own_rows:
                    compatible = self._compatible(hand, bucket)
                    value = self._mul(self._mul(own_weight, compatible), scale)
                    answer[i] = self._add(answer[i], value if player == 0 else -value)
            else:
                if not any(weighted for _j, _hand, weighted in opp_rows):
                    continue
                ranks = self._rank_vectors(k)
                # One sorted opponent stream and one sorted own stream are
                # merged by rank. Only all/lower/current-equal card buckets
                # are retained; no 52-card snapshot is kept per rank.
                opponent_sorted = sorted(
                    ((ranks[opp_side][j], hand, weighted)
                     for j, hand, weighted in opp_rows), key=lambda row: row[0])
                own_sorted = sorted(
                    ((ranks[own_side][i], i, hand, weight)
                     for i, (hand, weight) in enumerate(zip(self.hands[own_side], self.weights[own_side]))
                     if not (blocked & self._hand_masks[own_side][i])), key=lambda row: row[0])
                all_total, all_cards, _unused = self._bucket(
                    tuple((q, hand, weighted) for q, (_rank, hand, weighted) in enumerate(opponent_sorted)))
                lower_total = Fraction(0)
                lower_cards = [Fraction(0) for _ in range(52)]
                opponent_pos = 0
                own_pos = 0
                while own_pos < len(own_sorted):
                    rank = own_sorted[own_pos][0]
                    while opponent_pos < len(opponent_sorted) and opponent_sorted[opponent_pos][0] < rank:
                        _orank, ohand, weighted = opponent_sorted[opponent_pos]
                        lower_total = self._add(lower_total, weighted)
                        lower_cards[DECK.index(ohand[0])] = self._add(lower_cards[DECK.index(ohand[0])], weighted)
                        lower_cards[DECK.index(ohand[1])] = self._add(lower_cards[DECK.index(ohand[1])], weighted)
                        opponent_pos += 1
                    equal_total = Fraction(0)
                    equal_cards = [Fraction(0) for _ in range(52)]
                    equal_end = opponent_pos
                    while equal_end < len(opponent_sorted) and opponent_sorted[equal_end][0] == rank:
                        _orank, ohand, weighted = opponent_sorted[equal_end]
                        equal_total = self._add(equal_total, weighted)
                        equal_cards[DECK.index(ohand[0])] = self._add(equal_cards[DECK.index(ohand[0])], weighted)
                        equal_cards[DECK.index(ohand[1])] = self._add(equal_cards[DECK.index(ohand[1])], weighted)
                        equal_end += 1
                    own_end = own_pos
                    while own_end < len(own_sorted) and own_sorted[own_end][0] == rank:
                        _rank, i, hand, own_weight = own_sorted[own_end]
                        a, b = DECK.index(hand[0]), DECK.index(hand[1])
                        lower = self._sub(self._sub(lower_total, lower_cards[a]), lower_cards[b])
                        higher_total = self._sub(self._sub(all_total, lower_total), equal_total)
                        higher_a = self._sub(self._sub(all_cards[a], lower_cards[a]), equal_cards[a])
                        higher_b = self._sub(self._sub(all_cards[b], lower_cards[b]), equal_cards[b])
                        higher = self._sub(self._sub(higher_total, higher_a), higher_b)
                        signed = self._sub(lower, higher)
                        value = self._mul(self._mul(own_weight, signed), scale)
                        # Exact same-hand mass is in the equal-rank bucket and
                        # ties contribute zero, so it cannot leak into strict
                        # lower/higher comparisons.
                        answer[i] = self._add(answer[i], value)
                        own_end += 1
                    # Move the equal bucket into the running lower bucket only
                    # after all own hands at this rank have been evaluated.
                    while opponent_pos < equal_end:
                        _orank, ohand, weighted = opponent_sorted[opponent_pos]
                        lower_total = self._add(lower_total, weighted)
                        lower_cards[DECK.index(ohand[0])] = self._add(lower_cards[DECK.index(ohand[0])], weighted)
                        lower_cards[DECK.index(ohand[1])] = self._add(lower_cards[DECK.index(ohand[1])], weighted)
                        opponent_pos += 1
                    own_pos = own_end
        return tuple(self._divide(value, self.normalizer) for value in answer)

    def _snapshot_nonnegative(self, value, label, allow_signed=False):
        if isinstance(value, bool):
            raise TypeError(f"{label} must be numeric, not boolean.")
        if isinstance(value, Fraction):
            result = value
            self._check_bits(result)
        elif isinstance(value, Real):
            try:
                number = float(value)
            except (ValueError, OverflowError) as exc:
                raise ValueError(f"{label} must be finite.") from exc
            if not math.isfinite(number):
                raise ValueError(f"{label} must be finite.")
            result = Fraction.from_float(number)
        else:
            raise TypeError(f"{label} must be numeric.")
        if result < 0 and not allow_signed:
            raise ValueError(f"{label} must be nonnegative.")
        if not allow_signed and result > 1 and label == "opponent_reach":
            raise ValueError("opponent_reach entries must not exceed one.")
        return result

    def _preflight_terminal_bits(self, reach, payoff, player, board_count):
        """Forecast the largest exact terminal intermediate before rank work."""
        limit = self.limits.max_integer_bits

        def checked_product_bits(a_bits, b_bits):
            if a_bits + b_bits > limit:
                self._unsupported += 1
                raise ValueError("Exact terminal integer-bit product forecast exceeded.")
            return a_bits + b_bits

        def lcm_bounded(left, right):
            factor = left // math.gcd(left, right)
            if factor.bit_length() + right.bit_length() > limit:
                self._unsupported += 1
                raise ValueError("Exact terminal denominator-growth preflight exceeded.")
            return factor * right

        opp = 1 - player
        product_denominators = []
        product_numerator_bits = []
        for weight, reach_value in zip(self.weights[opp], reach):
            # Cross-cancel before forecasting, without forming a product.
            g1 = math.gcd(abs(weight.numerator), reach_value.denominator)
            g2 = math.gcd(abs(reach_value.numerator), weight.denominator)
            wn = abs(weight.numerator) // g1
            rn = abs(reach_value.numerator) // g2
            wd = weight.denominator // g2
            rd = reach_value.denominator // g1
            product_numerator_bits.append(checked_product_bits(wn.bit_length(), rn.bit_length()))
            if wd.bit_length() + rd.bit_length() > limit:
                self._unsupported += 1
                raise ValueError("Exact terminal denominator-product forecast exceeded.")
            product_denominators.append(wd * rd)

        opponent_denominator = 1
        for denominator in product_denominators:
            opponent_denominator = lcm_bounded(opponent_denominator, denominator)
        opponent_sum_numerator = (max(product_numerator_bits, default=1) +
                                  opponent_denominator.bit_length() +
                                  math.ceil(math.log2(max(1, len(reach)))) + 2)
        own_denominator = 1
        own_side = player
        for weight in self.weights[own_side]:
            own_denominator = lcm_bounded(own_denominator, weight.denominator)
        raw_denominator_bits = (opponent_denominator.bit_length() + own_denominator.bit_length() +
                                payoff.denominator.bit_length())
        raw_numerator_bits = (opponent_sum_numerator +
                              max(w.numerator.bit_length() for w in self.weights[own_side]) +
                              payoff.numerator.bit_length() +
                              math.ceil(math.log2(max(1, board_count))) + 3)
        final_numerator_bits = raw_numerator_bits + self.normalizer.denominator.bit_length()
        final_denominator_bits = raw_denominator_bits + self.normalizer.numerator.bit_length()
        if max(opponent_sum_numerator, raw_denominator_bits, raw_numerator_bits,
               final_numerator_bits, final_denominator_bits) > limit:
            self._unsupported += 1
            raise ValueError("Exact terminal integer-bit preflight exceeded.")

    def statistics(self):
        return {
            "contract": _VERSION,
            "hands": self.hand_counts,
            "boards": len(self.selected),
            "support_hand_board_counts": tuple(self._support_count),
            "support_pair_board_occurrences": self._support_pair_board_occurrences,
            "work_units_cumulative": self._work,
            "storage_entries_peak": self._entries_peak,
            "queries": self._queries,
            "unsupported_requests": self._unsupported,
            "rank_calls": self._rank_calls,
            "rank_sweeps": self._rank_sweeps,
            "rank_cache_hits": self._cache_hits,
            "rank_cache_misses": self._cache_misses,
            "rank_cache_evictions": self._cache_evictions,
        }

    def clear_rank_cache(self):
        """Release solve-local rank vectors after terminal diagnostics finish."""
        self._rank_cache.clear()

    def receipt(self):
        return MappingProxyType(self.statistics())

