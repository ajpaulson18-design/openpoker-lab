"""Stream physical flop/checkdown rows after exact structural admission.

Shape rows carry a placeholder sign and are only for admission. They must never
reach a trainer or evaluator. Ranked rows are generated once, in the original
pair/selected-outcome order, directly into bounded first-seen sign groups.
"""
from itertools import chain, repeat
from math import fsum, isfinite

from .preflop_future_groups import estimate_future_grouping_count, group_hidden_future_stream
from .preflop_vector_budget import MAX_TOTAL_LOOP_ENTRIES

MAX_STREAM_REFERENCE_SLOTS = 8_000_000


def estimate_streamed_construction(world_count, selected_count, pair_count):
    """Reserve source summaries in addition to the unchanged grouping envelope.

    Logical reference slots, not bytes/RSS: pair records, first-seen pair/flop
    and flop summaries, selected-flop key lookup, and fixed generator workspace.
    Packed blocker postings/flags are reported separately; the existing selected
    input/index bound remains enforced before this helper is reached.
    """
    if any(type(n) is not int or n < 1 for n in (world_count, selected_count, pair_count)):
        raise ValueError("streamed construction dimensions must be positive integers")
    if world_count > 300_000 or selected_count > 300_000 or pair_count > world_count:
        raise ValueError("streamed construction dimensions exceed physical input caps")
    old = estimate_future_grouping_count(world_count)
    extra = 256 + 8 * world_count + 24 * pair_count + 6 * selected_count
    combined = old["grouping_reference_slots_upper_bound"] + extra
    if combined > MAX_STREAM_REFERENCE_SLOTS:
        raise ValueError("Streamed world summaries exceed the logical reference-slot cap")
    packed_bytes = (selected_count + 7) // 8
    scan_byte_visits = 4 * pair_count * packed_bytes
    scan_loops = 4 * scan_byte_visits
    extra_loops = 128 + 40 * world_count + 8 * selected_count + 16 * pair_count + scan_loops
    if extra_loops > MAX_TOTAL_LOOP_ENTRIES:
        raise ValueError("Streamed construction exceeds the logical loop-entry cap before scans")
    return {
        "budget_version": "preflop-streamed-world-construction-v2",
        "physical_world_count": world_count,
        "selected_runouts": selected_count,
        "compatible_private_pairs": pair_count,
        "additional_reference_slots_upper_bound": extra,
        "combined_grouping_reference_slots_upper_bound": combined,
        "combined_reference_slot_limit": MAX_STREAM_REFERENCE_SLOTS,
        "additional_loop_entries_upper_bound": extra_loops,
        "blocker_scan_passes": 4,
        "blocker_scan_byte_visits_upper_bound": scan_byte_visits,
        "blocker_scan_loop_entries_upper_bound": scan_loops,
        "retained_posting_payload_bytes": 52 * packed_bytes,
        "reachable_flag_payload_bytes": selected_count,
        "scope": "Additional bounded source summaries, repeated shape-row construction and grouping orchestration. Full original-world vector and grouping envelopes remain charged. Reference counts and packed payloads exclude Python headers/allocator overhead and are not allocation or RSS bounds.",
    }


class StreamedPhysicalWorlds:
    """Prepared physical shape and output summaries; no retained world rows."""
    __slots__ = ("world_count", "construction_budget", "flop_world_counts",
                 "reachable_indices", "_private_flops", "_hands", "_selected",
                 "_index", "_pairs", "_flop_keys", "pair_probabilities")

    def __init__(self, ranges, hands, selected, index, counts, world_count, denominator):
        self.world_count = world_count
        self.construction_budget = estimate_streamed_construction(world_count, len(selected), len(counts))
        self._hands, self._selected, self._index = hands, selected, index
        masses = [(sb, bb, count, ranges[0][hands[0][sb]] * ranges[1][hands[1][bb]] / denominator)
                  for sb, bb, count in counts]
        # Exactly the original fsum input order, including each repeated mass.
        normalizer = fsum(chain.from_iterable(repeat(mass, count) for _, _, count, mass in masses))
        if not isfinite(normalizer) or normalizer <= 0:
            raise ValueError("Selected ranges and runouts have no positive joint mass.")
        self._pairs = [(sb, bb, count, mass / normalizer) for sb, bb, count, mass in masses]
        self.pair_probabilities = [
            {"sb_hand": "".join(hands[0][sb]), "bb_hand": "".join(hands[1][bb]),
             "probability": mass * count / normalizer}
            for sb, bb, count, mass in masses]
        masses = None
        self._flop_keys = {flop: "".join(flop) for flop, _, _ in selected}
        self.flop_world_counts = {}
        self._private_flops = {}
        self.reachable_indices = bytearray(len(selected))
        observed = 0
        for sb, bb, _count, _mass in self._pairs:
            for selected_index in index.iter_valid_indices(hands[0][sb] + hands[1][bb]):
                if observed >= world_count:
                    raise AssertionError("Prepared streamed worlds exceed preflight before summary insertion")
                flop = selected[selected_index][0]
                key = self._flop_keys[flop]
                self.flop_world_counts[key] = self.flop_world_counts.get(key, 0) + 1
                self._private_flops[(sb, bb, key)] = flop
                self.reachable_indices[selected_index] = 1
                observed += 1
        if observed != world_count:
            raise AssertionError("Prepared streamed world count differs from preflight")

    def __len__(self):
        return self.world_count

    def shape_rows(self):
        if self._index is None:
            raise RuntimeError("Streamed construction inputs have been released")
        for sb, bb, _count, mass in self._pairs:
            private = self._hands[0][sb] + self._hands[1][bb]
            for selected_index in self._index.iter_valid_indices(private):
                flop, turn, river = self._selected[selected_index]
                yield sb, bb, mass, 0, self._flop_keys[flop], turn, river

    def legal_hands(self):
        legal = {(player, ()): set() for player in (0, 1)}
        for (sb, bb, _key), flop in self._private_flops.items():
            for player, hand in enumerate((sb, bb)):
                legal[(player, ())].add(hand)
                legal.setdefault((player, flop), set()).add(hand)
        return legal

    def grouped_rows(self, rank_world):
        if self._index is None:
            raise RuntimeError("Streamed construction inputs have been released")
        cache = {}

        def rows():
            for sb, bb, _count, mass in self._pairs:
                sb_hand, bb_hand = self._hands[0][sb], self._hands[1][bb]
                for selected_index in self._index.iter_valid_indices(sb_hand + bb_hand):
                    flop, turn, river = self._selected[selected_index]
                    sign = rank_world(sb_hand, bb_hand, (flop, turn, river), cache)
                    yield sb, bb, mass, sign, self._flop_keys[flop], turn, river
        try:
            return group_hidden_future_stream(rows(), self.world_count)
        finally:
            cache.clear()
            self._hands = self._selected = self._index = self._pairs = self._flop_keys = None
            self._private_flops = None
            rows = None
