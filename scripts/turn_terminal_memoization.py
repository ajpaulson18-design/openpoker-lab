"""Research-only, bounded memoization for controlled matrix-free turn solves.

The wrapper is deliberately private to the two pinned CFR+ research fixtures.
It is not a production solver mode or a general cache for mutable evaluator
objects. Every result is still produced by the existing RankedRiverPayoffs
implementation on cache misses.
"""
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
import math
import struct

from pokerlab import matrix_free_turn, turn_range_kernel


MAX_CACHE_ENTRIES = 16_384
MAX_CACHE_SLOT_WORK = 30_000_000
CACHE_SLOTS_PER_CALL = 20
MAX_ITERATIONS = 1_000
MAX_HANDS_PER_PLAYER = 2
MAX_BRANCHES = 48

_ORIGINAL_RANKED_CLASS = turn_range_kernel.RankedRiverPayoffs
_ORIGINAL_TURN_CLASS = matrix_free_turn.TurnRangePayoffs

TERMINAL_COUNTS = {
    "two-conditioned-runouts-asymmetric-multisize": 96,
    "full44-blocked-runouts": 720,
}


def call_ceiling(model_id, iterations):
    """Conservative complete-call upper bound, including final profile and BRs."""
    if model_id not in TERMINAL_COUNTS:
        raise ValueError("The turn memoizer accepts only its two pinned fixtures.")
    if type(iterations) is not int or not 10 <= iterations <= MAX_ITERATIONS:
        raise ValueError("Memoized iterations must be an exact integer from 10 through 1000.")
    return TERMINAL_COUNTS[model_id] * (2 * iterations + 4)


@dataclass
class MemoizationStats:
    """Deterministic logical counters; these are not CPU or memory measures."""

    calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    evictions: int = 0
    output_values_copied: int = 0
    maximum_entries: int = 0
    logical_slot_work: int = 0
    reserved_call_ceiling: int = 0
    cache_entry_limit: int = MAX_CACHE_ENTRIES
    cache_slot_limit: int = MAX_CACHE_SLOT_WORK
    entries_before_cleanup: int = 0
    entries_after_cleanup: int = 0
    current_entries: int = 0

    def to_dict(self):
        return {
            "inner_values_calls": self.calls,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "evictions": self.evictions,
            "output_values_copied": self.output_values_copied,
            "maximum_entries": self.maximum_entries,
            "current_entries": self.current_entries,
            "entries_before_cleanup": self.entries_before_cleanup,
            "entries_after_cleanup": self.entries_after_cleanup,
            "cache_entry_limit": self.cache_entry_limit,
            "logical_slot_work": self.logical_slot_work,
            "logical_slot_limit": self.cache_slot_limit,
            "logical_slots_per_call": CACHE_SLOTS_PER_CALL,
            "reserved_call_ceiling": self.reserved_call_ceiling,
            "logical_payload_bytes_upper_bound": (
                self.cache_entry_limit * (2 + 2 + 1) * 8
            ),
            "logical_payload_scope": (
                "Numeric slots only: at most two reach floats, two output floats, "
                "and one matched-contribution float per retained entry; excludes "
                "Python object/container/LRU headers, references, fixed key fields, "
                "temporary copies, and allocator overhead."
            ),
        }


class _Runtime:
    def __init__(self, *, max_entries, slot_limit, call_limit,
                 reserved_call_ceiling):
        self.cache = OrderedDict()
        self.stats = MemoizationStats(
            reserved_call_ceiling=reserved_call_ceiling,
            cache_entry_limit=max_entries,
            cache_slot_limit=slot_limit,
        )
        self.max_entries = max_entries
        self.slot_limit = slot_limit
        self.call_limit = call_limit
        self.kernel_instances = 0

    def reserve_call(self):
        proposed_calls = self.stats.calls + 1
        proposed_work = self.stats.logical_slot_work + CACHE_SLOTS_PER_CALL
        if proposed_calls > self.call_limit:
            raise ValueError("Memoizer exceeded its pre-admitted inner-call ceiling.")
        if proposed_work > self.slot_limit:
            raise ValueError("Turn memoizer exceeds its 30 million logical cache-slot work cap.")
        self.stats.calls = proposed_calls
        self.stats.logical_slot_work = proposed_work

    def insert(self, key, values):
        if self.max_entries == 0:
            return
        if key in self.cache:
            self.cache.move_to_end(key)
            return
        if len(self.cache) >= self.max_entries:
            self.cache.popitem(last=False)
            self.stats.evictions += 1
        # The bounded slot was reserved by the public shape/cap preflight.
        copied = tuple(values)
        self.stats.output_values_copied += len(copied)
        self.cache[key] = copied
        self.stats.current_entries = len(self.cache)
        self.stats.maximum_entries = max(self.stats.maximum_entries, len(self.cache))

    def clear(self):
        self.stats.entries_before_cleanup = len(self.cache)
        self.cache.clear()
        self.stats.current_entries = 0
        self.stats.entries_after_cleanup = len(self.cache)


def _float_bits(value):
    return struct.pack(">d", value)


@contextmanager
def patched_turn_memoizer(model_id, iterations, *, max_entries=MAX_CACHE_ENTRIES,
                          slot_limit=MAX_CACHE_SLOT_WORK, call_limit=None):
    """Install one isolated, per-solve memoizer and always restore both modules.

    The caller must freeze and validate the exact fixture before entering this
    context. This routine independently enforces the iteration/model envelope
    and call/slot caps before changing module identities.
    """
    if model_id not in TERMINAL_COUNTS:
        raise ValueError("The turn memoizer accepts only its two pinned fixtures.")
    ceiling = call_ceiling(model_id, iterations)
    if type(max_entries) is not int or not 0 <= max_entries <= MAX_CACHE_ENTRIES:
        raise ValueError("Memoizer entry limit must be an exact integer from 0 through 16384.")
    if type(slot_limit) is not int or not 0 <= slot_limit <= MAX_CACHE_SLOT_WORK:
        raise ValueError("Memoizer slot limit must be an exact integer from 0 through 30000000.")
    if call_limit is not None and (
            type(call_limit) is not int or not 0 <= call_limit <= ceiling):
        raise ValueError("Memoizer test call limit must be an exact integer no greater than its ceiling.")
    runtime_call_limit = ceiling if call_limit is None else call_limit
    reserved_slots = ceiling * CACHE_SLOTS_PER_CALL
    if reserved_slots > slot_limit:
        raise ValueError("Full requested memoizer call ceiling exceeds its logical slot cap.")

    if (turn_range_kernel.RankedRiverPayoffs is not _ORIGINAL_RANKED_CLASS or
            matrix_free_turn.TurnRangePayoffs is not _ORIGINAL_TURN_CLASS):
        raise RuntimeError("A foreign or nested turn memoizer patch is already active.")

    runtime = _Runtime(max_entries=max_entries, slot_limit=slot_limit,
                       call_limit=runtime_call_limit,
                       reserved_call_ceiling=ceiling)
    original_ranked = turn_range_kernel.RankedRiverPayoffs
    original_turn_kernel = matrix_free_turn.TurnRangePayoffs

    class MemoizedRankedRiverPayoffs(original_ranked):
        def __init__(self, board, hands, weights, *, pot, fallback_pair_limit=None):
            try:
                hand_counts = tuple(len(side) for side in hands)
            except (TypeError, AttributeError) as exc:
                raise ValueError("Memoizer requires sized two-hand ranked ranges.") from exc
            if len(hand_counts) != 2 or any(
                    type(count) is not int or count < 1 or count > MAX_HANDS_PER_PLAYER
                    for count in hand_counts):
                raise ValueError("Memoizer supports at most two ranked hands per player.")
            # Identity numbers are scoped to one solve and cannot be
            # recycled while any branch kernel in that solve is alive.
            if runtime.kernel_instances >= MAX_BRANCHES:
                raise ValueError("Memoizer supports at most 48 branch kernels per solve.")
            runtime.kernel_instances += 1
            self._memo_branch_identity = runtime.kernel_instances
            super().__init__(board, hands, weights, pot=pot,
                             fallback_pair_limit=fallback_pair_limit)

        def values(self, node, opponent_reach, player):
            runtime.reserve_call()

            # Repeat precisely the original input validation before every lookup.
            if type(player) is not int or player not in (0, 1):
                raise ValueError("player must be 0 (OOP) or 1 (IP).")
            matched, _contributions = self._terminal(node)
            opponent = 1 - player
            reach = self._reach(opponent_reach, len(self.hands[opponent]))
            key = (
                self._memo_branch_identity, node.kind, _float_bits(matched),
                node.winner if node.kind == "fold" else None,
                player, tuple(_float_bits(value) for value in reach),
            )
            cached = runtime.cache.get(key)
            if cached is not None:
                runtime.cache.move_to_end(key)
                runtime.stats.cache_hits += 1
                runtime.stats.output_values_copied += len(cached)
                return list(cached)

            runtime.stats.cache_misses += 1
            before = self.fallback_pair_checks
            result = super().values(node, reach, player)
            added = self.fallback_pair_checks - before
            if added < 0:
                raise RuntimeError("Ranked river fallback counter moved backwards.")
            if added == 0:
                runtime.insert(key, result)
            return result

    class MemoizedTurnRangePayoffs(original_turn_kernel):
        def __init__(self, board, hands, weights, *, pot, runouts=None,
                     fallback_pair_limit=30_000_000,
                     stable_root_pair_limit=100_000):
            # Reject excess shape before the original constructor allocates
            # branch kernels or rank tables.
            try:
                hand_counts = tuple(len(side) for side in hands)
            except (TypeError, AttributeError) as exc:
                raise ValueError("Memoizer requires sized two-hand turn ranges.") from exc
            if len(hand_counts) != 2 or any(
                    type(count) is not int or count < 1 or count > MAX_HANDS_PER_PLAYER
                    for count in hand_counts):
                raise ValueError("Memoizer supports at most two original hands per player.")
            if runouts is None:
                branch_count = 48
            else:
                try:
                    branch_count = len(runouts)
                except TypeError as exc:
                    raise ValueError("Memoizer runouts must be a sized sequence.") from exc
            if type(branch_count) is not int or not 1 <= branch_count <= MAX_BRANCHES:
                raise ValueError("Memoizer supports from 1 through 48 selected branches.")
            super().__init__(
                board, hands, weights, pot=pot, runouts=runouts,
                fallback_pair_limit=fallback_pair_limit,
                stable_root_pair_limit=stable_root_pair_limit,
            )
            if self.exceptional_conditioning:
                raise ValueError("Memoization research excludes exceptional conditioning.")
            if self.stable_root_fold_calls != 0:
                raise ValueError("Memoization research excludes stable root-fold evaluation.")
            if any(len(branch["indexes"][side]) > MAX_HANDS_PER_PLAYER
                   for branch in self._branches.values() for side in (0, 1)):
                raise ValueError("Memoizer filtered branch exceeds its hand-shape envelope.")

        def values(self, node, opponent_reach, player, prefix=()):
            if self.exceptional_conditioning or self.stable_root_fold_calls:
                raise ValueError("Memoization research excludes exceptional turn kernel paths.")
            before = self.stable_root_fold_calls
            result = super().values(node, opponent_reach, player, prefix)
            if self.exceptional_conditioning or self.stable_root_fold_calls != before:
                raise ValueError("Turn evaluation activated excluded root-fold stability logic.")
            return result

    turn_range_kernel.RankedRiverPayoffs = MemoizedRankedRiverPayoffs
    matrix_free_turn.TurnRangePayoffs = MemoizedTurnRangePayoffs
    try:
        yield runtime.stats
    finally:
        # Capture the high-water occupancy before clearing all per-solve values.
        runtime.clear()
        matrix_free_turn.TurnRangePayoffs = original_turn_kernel
        turn_range_kernel.RankedRiverPayoffs = original_ranked

