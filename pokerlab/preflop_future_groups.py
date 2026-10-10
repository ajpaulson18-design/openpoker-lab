"""Bounded sufficient-statistic groups for flop-checkdown physical worlds.

A checkdown world only affects a preflop/flop tree through its private pair,
public flop, joint mass, and final showdown sign. This helper keeps one row per
(first-seen private-pair/flop/sign) group. It does not renormalize mass.

The estimator's reference-slot count is a logical overlap envelope: it charges
the seven fields plus row reference of every retained original world, up to one
four-field map key plus accumulator and mapping references per group, and a
five-field output row plus its output-list reference. It also includes fixed
workspace. It is not a Python allocation, byte, or RSS bound; headers and
allocator overhead are excluded.
"""
import math
from collections.abc import Sequence


MAX_GROUP_ROWS = 3_000_000
MAX_GROUP_REFERENCE_SLOTS = 8_000_000


def _world_count(worlds):
    if isinstance(worlds, (str, bytes)) or not isinstance(worlds, Sequence):
        raise TypeError("worlds must be a sized sequence of physical-world rows")
    count = len(worlds)
    if count < 1:
        raise ValueError("at least one physical world is required")
    return count


def estimate_future_grouping(worlds):
    """Return conservative, JSON-safe copy/work bounds before grouping.

    No per-world or per-group collections are allocated here. Physical rows
    have the solver's seven-field shape; at most one grouped row can result
    from each input row. The scan envelope also charges key creation, lookup,
    accumulation, and output conversion at a generous linear coefficient.
    """
    count = _world_count(worlds)
    if count > MAX_GROUP_ROWS:
        raise ValueError("Flop/sign grouping exceeds the 3,000,000-row cap.")
    grouped_upper = count
    # Original 7 fields + list reference = 8; map key, accumulator and dict
    # references = 8; output tuple plus list reference = 6. Fixed bounded state
    # covers one temporary lookup key and loop bookkeeping.
    reference_slots = 128 + 22 * count
    if reference_slots > MAX_GROUP_REFERENCE_SLOTS:
        raise ValueError("Flop/sign grouping exceeds the logical reference-slot cap.")
    return {
        "physical_world_count": count,
        "grouped_rows_upper_bound": grouped_upper,
        "grouping_reference_slots_upper_bound": reference_slots,
        "grouping_reference_slot_limit": MAX_GROUP_REFERENCE_SLOTS,
        "grouping_loop_entries_upper_bound": 32 + 24 * count,
        "grouping_loop_entry_scope": (
            "Conservative linear validation, hash/group accumulation, and output-copy envelope; "
            "not bytecode, elapsed time, Python-allocation, or RSS prediction."
        ),
    }


def _validated_row(world):
    if not isinstance(world, (tuple, list)) or len(world) != 7:
        raise ValueError("each physical world must contain seven fields")
    sb_index, bb_index, mass, sign, flop, _turn, _river = world
    if (type(sb_index) is not int or not 0 <= sb_index < 1326 or
            type(bb_index) is not int or not 0 <= bb_index < 1326):
        raise ValueError("private-hand indices must be within the Hold'em combo range")
    if isinstance(mass, bool) or not isinstance(mass, (int, float)):
        raise ValueError("physical-world mass must be finite and nonnegative")
    if isinstance(sign, bool) or not isinstance(sign, (int, float)):
        raise ValueError("showdown sign must be -1, 0, or 1")
    try:
        mass, numeric_sign = float(mass), float(sign)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("physical-world mass and sign must be finite real values") from exc
    if not math.isfinite(mass) or mass < 0:
        raise ValueError("physical-world mass must be finite and nonnegative")
    if not math.isfinite(numeric_sign) or numeric_sign not in (-1.0, 0.0, 1.0):
        raise ValueError("showdown sign must be -1, 0, or 1")
    try:
        hash(flop)
    except TypeError as exc:
        raise ValueError("flop keys must be hashable") from exc
    return sb_index, bb_index, float(mass), sign, flop


def group_hidden_futures(worlds):
    """Return five-field grouped rows in deterministic first-seen order.

    Per-key Neumaier accumulation reduces loss from summing unequal positive
    physical masses without retaining a list of constituent worlds. Signs
    remain categorical; a fractional weighted-average sign is never emitted.
    """
    estimate_future_grouping(worlds)
    # Validate the complete input before allocating the group map. The scan is
    # included in the returned linear work envelope.
    for world in worlds:
        _validated_row(world)

    groups = {}
    for world in worlds:
        sb_index, bb_index, mass, sign, flop = _validated_row(world)
        key = (sb_index, bb_index, flop, sign)
        accumulator = groups.get(key)
        if accumulator is None:
            groups[key] = [mass, 0.0]
            continue
        total, compensation = accumulator
        updated = total + mass
        if abs(total) >= abs(mass):
            compensation += (total - updated) + mass
        else:
            compensation += (mass - updated) + total
        if not math.isfinite(updated) or not math.isfinite(compensation):
            raise ValueError("grouped physical-world mass overflowed")
        accumulator[1] = compensation
        accumulator[0] = updated

    # Preserve first-seen map order and fold Neumaier's correction into the
    # single mass field expected by the vector trainer.
    rows = []
    for (sb_index, bb_index, flop, sign), (total, compensation) in groups.items():
        mass = total + compensation
        if not math.isfinite(mass):
            raise ValueError("grouped physical-world mass overflowed")
        rows.append((sb_index, bb_index, mass, sign, flop))
    return rows
