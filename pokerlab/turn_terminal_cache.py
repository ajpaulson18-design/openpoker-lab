"""Per-solve bounded cache for matrix-free turn branch terminal values.

The outer :class:`TurnRangePayoffs` kernel remains the original object. This
module temporarily wraps only its private ranked-river branch kernels and
restores every branch reference before returning from the context.
"""
from collections import OrderedDict
from dataclasses import dataclass
import struct


MAX_CACHE_ENTRIES = 16_384
MAX_CACHE_SLOT_WORK = 30_000_000
CACHE_SLOTS_PER_CALL = 20
# Conservative setup ledger: 16 logical reference/control slots per branch
# (original kernel, proxy/runtime/ordinal references, and installation-plan
# entry), plus 64 fixed slots (the 7-field admission, 13-field runtime, 5-field
# installer, owner, and bounded preflight/constructor/loop bookkeeping). These
# are accounting units, not Python allocation or instruction counts.
SETUP_SLOTS_PER_BRANCH = 16
FIXED_SETUP_SLOTS = 64
MAX_CACHE_ITERATIONS = 10_000
MAX_CACHE_HANDS_PER_PLAYER = 2
MAX_CACHE_BRANCHES = 48


@dataclass(frozen=True)
class CacheAdmission:
    terminal_count: int
    branch_count: int
    requested_iterations: int
    reserved_calls: int
    setup_slots: int
    reserved_slots: int
    slot_limit: int = MAX_CACHE_SLOT_WORK


def admit_cache(terminal_count, branch_count, iterations, *,
                slot_limit=MAX_CACHE_SLOT_WORK):
    """Pre-admit full requested training, diagnostics, and setup work.

    This is a logical cache-work envelope, not a count of Python instructions,
    bytes, or allocator operations. Test callers may lower ``slot_limit`` but
    cannot raise the production ceiling or shorten the requested call bound.
    """
    if type(terminal_count) is not int or terminal_count < 1:
        raise ValueError("Terminal count must be a positive exact integer.")
    if (type(branch_count) is not int or
            not 1 <= branch_count <= MAX_CACHE_BRANCHES):
        raise ValueError("Ranked terminal cache supports 1 through 48 branches.")
    if (type(iterations) is not int or
            not 10 <= iterations <= MAX_CACHE_ITERATIONS):
        raise ValueError("Ranked terminal cache supports 10 through 10000 iterations.")
    if (type(slot_limit) is not int or
            not 0 <= slot_limit <= MAX_CACHE_SLOT_WORK):
        raise ValueError("Cache slot limit must be an exact integer up to 30000000.")
    calls = terminal_count * (2 * iterations + 4)
    setup = SETUP_SLOTS_PER_BRANCH * branch_count + FIXED_SETUP_SLOTS
    reserved = calls * CACHE_SLOTS_PER_CALL + setup
    if reserved > slot_limit:
        raise ValueError("Full requested ranked terminal cache reservation exceeds 30 million slots.")
    return CacheAdmission(
        terminal_count=terminal_count,
        branch_count=branch_count,
        requested_iterations=iterations,
        reserved_calls=calls,
        setup_slots=setup,
        reserved_slots=reserved,
        slot_limit=slot_limit,
    )


def _validated_admission(admission):
    if type(admission) is not CacheAdmission:
        raise TypeError("A canonical ranked terminal cache admission is required.")
    integer_fields = (
        "terminal_count", "branch_count", "requested_iterations",
        "reserved_calls", "setup_slots", "reserved_slots", "slot_limit",
    )
    if any(type(getattr(admission, field)) is not int for field in integer_fields):
        raise ValueError("Ranked terminal cache admission fields must be exact integers.")
    expected = admit_cache(
        admission.terminal_count,
        admission.branch_count,
        admission.requested_iterations,
        slot_limit=admission.slot_limit,
    )
    if admission != expected:
        raise ValueError("Ranked terminal cache admission fields are inconsistent.")
    return expected


def _float_bits(value):
    return struct.pack(">d", value)


class CacheRuntime:
    """One solve's private LRU and deterministic accounting."""

    __slots__ = (
        "admission", "cache", "entry_limit", "call_limit", "calls",
        "hits", "misses", "evictions", "output_values_copied",
        "maximum_entries", "entries_before_cleanup", "entries_after_cleanup",
        "cleaned",
    )

    def __init__(self, admission, *, entry_limit=MAX_CACHE_ENTRIES,
                 call_limit=None):
        admission = _validated_admission(admission)
        if (type(entry_limit) is not int or
                not 0 <= entry_limit <= MAX_CACHE_ENTRIES):
            raise ValueError("Cache entry limit must be an exact integer up to 16384.")
        if call_limit is not None and (
                type(call_limit) is not int or
                not 0 <= call_limit <= admission.reserved_calls):
            raise ValueError("Test call limit must be an exact integer within the reservation.")
        self.admission = admission
        self.cache = OrderedDict()
        self.entry_limit = entry_limit
        self.call_limit = admission.reserved_calls if call_limit is None else call_limit
        self.calls = 0
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.output_values_copied = 0
        self.maximum_entries = 0
        self.entries_before_cleanup = 0
        self.entries_after_cleanup = 0
        self.cleaned = False

    @property
    def actual_slots(self):
        return self.admission.setup_slots + self.calls * CACHE_SLOTS_PER_CALL

    def reserve_call(self):
        if self.cleaned:
            raise RuntimeError("A cleaned terminal cache cannot accept calls.")
        proposed = self.calls + 1
        if proposed > self.call_limit or proposed > self.admission.reserved_calls:
            raise ValueError("Ranked terminal cache exceeded its pre-admitted call ceiling.")
        if self.admission.setup_slots + proposed * CACHE_SLOTS_PER_CALL > self.admission.slot_limit:
            raise ValueError("Ranked terminal cache exceeded its logical slot-work limit.")
        self.calls = proposed

    def _ensure_open(self):
        if self.cleaned:
            raise RuntimeError("A cleaned terminal cache is closed.")

    def get(self, key):
        self._ensure_open()
        if key not in self.cache:
            return None
        value = self.cache.pop(key)
        self.cache[key] = value
        self.hits += 1
        self.output_values_copied += len(value)
        return list(value)

    def insert(self, key, values):
        self._ensure_open()
        if self.entry_limit == 0:
            return
        if key in self.cache:
            self.cache.pop(key)
            copied = tuple(values)
            self.output_values_copied += len(copied)
            self.cache[key] = copied
            return
        if len(self.cache) >= self.entry_limit:
            self.cache.popitem(last=False)
            self.evictions += 1
        copied = tuple(values)
        self.output_values_copied += len(copied)
        self.cache[key] = copied
        self.maximum_entries = max(self.maximum_entries, len(self.cache))

    def clear(self):
        if self.cleaned:
            return
        self.entries_before_cleanup = len(self.cache)
        self.cache.clear()
        self.entries_after_cleanup = len(self.cache)
        self.cleaned = True

    def to_dict(self):
        if not self.cleaned:
            raise RuntimeError("Cache accounting is final only after cleanup.")
        return {
            "mode": "ranked-lru",
            "version": "turn-terminal-cache-v1",
            "reserved_calls": self.admission.reserved_calls,
            "actual_calls": self.calls,
            "setup_slots": self.admission.setup_slots,
            "reserved_slots": self.admission.reserved_slots,
            "actual_slots": self.actual_slots,
            "logical_slot_limit": self.admission.slot_limit,
            "logical_slots_per_call": CACHE_SLOTS_PER_CALL,
            "terminal_count": self.admission.terminal_count,
            "branch_count": self.admission.branch_count,
            "requested_iterations": self.admission.requested_iterations,
            "cache_entry_limit": self.entry_limit,
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "output_values_copied": self.output_values_copied,
            "maximum_entries": self.maximum_entries,
            "entries_before_cleanup": self.entries_before_cleanup,
            "entries_after_cleanup": self.entries_after_cleanup,
            "current_entries": len(self.cache),
            "logical_payload_bytes_upper_bound": self.entry_limit * 5 * 8,
            "logical_payload_scope": (
                "Numeric slots only: at most two normalized reach floats, two output "
                "floats, and one matched-contribution float per entry. Excludes Python "
                "headers, references, key-container representation, temporary objects "
                "and allocator overhead; "
                "this is not an RSS or runtime bound."
            ),
        }


class _BranchValuesProxy:
    """Delegate a branch kernel while caching validated zero-fallback values."""

    __slots__ = ("_original", "_runtime", "_branch_ordinal")

    def __init__(self, original, runtime, branch_ordinal):
        object.__setattr__(self, "_original", original)
        object.__setattr__(self, "_runtime", runtime)
        object.__setattr__(self, "_branch_ordinal", branch_ordinal)

    def __getattr__(self, name):
        return getattr(self._original, name)

    @property
    def fallback_pair_limit(self):
        return self._original.fallback_pair_limit

    @fallback_pair_limit.setter
    def fallback_pair_limit(self, value):
        self._original.fallback_pair_limit = value

    def __setattr__(self, name, value):
        if name == "fallback_pair_limit":
            self._original.fallback_pair_limit = value
        else:
            raise AttributeError("Branch proxy permits no model mutation except fallback_pair_limit.")

    def values(self, node, opponent_reach, player):
        runtime = self._runtime

        # Mirror the original validation order before even consulting the LRU.
        if type(player) is not int or player not in (0, 1):
            raise ValueError("player must be 0 (OOP) or 1 (IP).")
        matched, _contributions = self._original._terminal(node)
        opponent = 1 - player
        reach = self._original._reach(
            opponent_reach, len(self._original.hands[opponent]))
        runtime.reserve_call()
        key = (
            self._branch_ordinal,
            node.kind,
            _float_bits(matched),
            node.winner if node.kind == "fold" else None,
            player,
            tuple(_float_bits(value) for value in reach),
        )
        cached = runtime.get(key)
        if cached is not None:
            return cached

        runtime.misses += 1
        before = self._original.fallback_pair_checks
        result = self._original.values(node, reach, player)
        added = self._original.fallback_pair_checks - before
        if added < 0:
            raise RuntimeError("Ranked river fallback counter moved backwards.")
        if added == 0:
            runtime.insert(key, result)
        return result


class InstalledBranchCache:
    """Install branch proxies transactionally and restore on every exit."""

    __slots__ = ("kernel", "runtime", "_installed", "_entered", "_closed")

    def __init__(self, kernel, admission, *, entry_limit=MAX_CACHE_ENTRIES,
                 call_limit=None):
        admission = _validated_admission(admission)
        from .ranked_river import RankedRiverPayoffs
        from .turn_range_kernel import TurnRangePayoffs

        if type(kernel) is not TurnRangePayoffs:
            raise TypeError("Ranked terminal cache requires the original turn kernel type.")
        if getattr(kernel, "exceptional_conditioning", True):
            raise ValueError("Ranked terminal cache does not support exceptional conditioning.")
        if any(not 1 <= len(side) <= MAX_CACHE_HANDS_PER_PLAYER
               for side in kernel.hands):
            raise ValueError("Ranked terminal cache supports at most two original hands per player.")
        branches = kernel._branches
        if len(branches) != admission.branch_count:
            raise ValueError("Ranked terminal cache branch count changed after admission.")
        if not 1 <= len(branches) <= MAX_CACHE_BRANCHES:
            raise ValueError("Ranked terminal cache supports 1 through 48 branches.")
        for branch in branches.values():
            original = branch.get("kernel")
            if type(original) is not RankedRiverPayoffs:
                raise ValueError("Nested or foreign ranked branch kernel cannot be cached.")
            if any(not 1 <= len(side) <= MAX_CACHE_HANDS_PER_PLAYER
                   for side in original.hands):
                raise ValueError("Ranked terminal cache branch exceeds its one-to-two-hand shape envelope.")
        self.kernel = kernel
        self.runtime = CacheRuntime(
            admission, entry_limit=entry_limit, call_limit=call_limit)
        self._installed = []
        self._entered = False
        self._closed = False

    def __enter__(self):
        if self._entered or self._closed or self.runtime.cleaned:
            raise RuntimeError("A branch-cache installation cannot be re-entered.")
        self._entered = True
        try:
            for branch_ordinal, branch in enumerate(self.kernel._branches.values()):
                original = branch["kernel"]
                proxy = _BranchValuesProxy(original, self.runtime, branch_ordinal)
                # Record restoration first so any later setup exception rolls
                # back every reference that was successfully installed.
                self._installed.append((branch, original, proxy))
                branch["kernel"] = proxy
        except BaseException:
            self.close()
            raise
        return self.runtime

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            for branch, original, _proxy in reversed(self._installed):
                branch["kernel"] = original
        finally:
            self._installed.clear()
            self.runtime.clear()

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False


def install_branch_cache(kernel, admission, *, entry_limit=MAX_CACHE_ENTRIES,
                         call_limit=None):
    """Return a cleanup-safe branch-cache context for an admitted solve."""
    return InstalledBranchCache(
        kernel, admission, entry_limit=entry_limit, call_limit=call_limit)
