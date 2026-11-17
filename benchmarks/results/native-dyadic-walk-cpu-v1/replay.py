"""Recount the named native functions in the sanitized T2 CPU captures."""

from argparse import ArgumentParser
from bisect import bisect_right
from collections import Counter
import gzip
import json
from pathlib import Path


TRACKED = {
    "walk": ("?visit@?$Walk@", ""),
    "state_stage_row": ("??$stage_row_impl@", "@State@virtual_dyadic_state@"),
    "state_stage_direct": ("??$stage_direct_row@", "@State@virtual_dyadic_state@"),
    "pager_stage": ("?stage_impl@Image@", "@virtual_dyadic_paged_image@"),
    "pager_flush_dirty": ("?flush_dirty@Image@", "@virtual_dyadic_paged_image@"),
    "terminal": ("?terminal@?$Walk@", ""),
    "chance_contraction": ("?contraction@PreparedPublicChance@", "@prepared_public_chance@"),
    "chance_contract": ("?contract@PreparedPublicChance@", "@prepared_public_chance@"),
    "history_enter_visit": ("?enter_visit@History@", "@virtual_dyadic_history@"),
    "history_visit_action": ("?visit_action@History@", "@virtual_dyadic_history@"),
    "history_visit_reveal": ("?visit_reveal@History@", "@virtual_dyadic_history@"),
    "history_append_action": ("?append_action@History@", "@virtual_dyadic_history@"),
    "history_append_reveal": ("?append_reveal@History@", "@virtual_dyadic_history@"),
}


def replay(path):
    with gzip.open(path, "rb") as stream:
        data = stream.read((16 << 20) + 1)
    if len(data) > 16 << 20:
        raise ValueError("capture exceeds saved-only replay limit")
    sample = json.loads(data)
    if sample["format"] != "trainer-process-samples-v1":
        raise ValueError("unsupported normalized trainer sample format")
    start, end = sample["section_rva"], sample["section_end_rva"]
    if (start, end) != (0x1000, 0x81E94):
        raise ValueError("unexpected trainer text section")
    starts = sorted(map(int, sample["symbols"]))
    if not starts or not start <= starts[0] <= starts[-1] < end:
        raise ValueError("symbol map falls outside trainer text")
    markers = {
        address: {label for label, (prefix, owner) in TRACKED.items()
                  if any(name.startswith(prefix) and owner in name
                         for name in sample["symbols"][str(address)])}
        for address in starts
    }

    def at(address):
        if type(address) is not int or not starts[0] <= address < end:
            raise ValueError("sample address cannot be resolved")
        return markers[starts[bisect_right(starts, address) - 1]]

    total = outside = previous = 0
    counts = Counter({label: 0 for label in TRACKED})
    counts["terminal_or_state_stage_row"] = 0
    for stamp, weight, leaf, stack in sample["profiles"]:
        if type(stamp) is not int or stamp < previous or type(weight) is not int or weight < 1:
            raise ValueError("invalid timestamp or sample weight")
        previous = stamp
        total += weight
        seen = at(leaf).copy() if leaf is not None else set()
        for address in stack:
            seen.update(at(address))
        if "walk" in seen:
            counts.update({label: weight for label in seen})
            if {"terminal", "state_stage_row"} & seen:
                counts["terminal_or_state_stage_row"] += weight
            outside += weight if leaf is None else 0
    if not total or not counts["walk"]:
        raise ValueError("no trainer walk samples")
    return {"trainer_samples": total, "walk_samples": counts["walk"],
            "walk_sampled_instruction_outside_trainer": outside,
            "walk_inclusive_hits": dict(counts)}


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("captures", type=Path, nargs="+")
    args = parser.parse_args()
    print(json.dumps({path.name: replay(path) for path in args.captures}, indent=2, sort_keys=True))
