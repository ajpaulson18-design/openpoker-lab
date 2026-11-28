"""Normalize xperf CSV from one pinned standard-trainer capture.

The output retains only relative addresses and times from the trainer.
Supply the linker map from a relink whose .text bytes match the captured image.
"""

from argparse import ArgumentParser
from bisect import bisect_right
from collections import defaultdict
import csv
import gzip
import json
from pathlib import Path
import re


IMAGE = "native-virtual-dyadic-training-probe.exe"
TEXT_START = 0x1000
TEXT_END = 0x81E94
LINK_BASE = 0x140000000


def events(path):
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
        yield from csv.reader(stream, skipinitialspace=True)


def normalize(trace, linker_map):
    bases, threads = set(), set()
    samples = {}
    for row in events(trace):
        if len(row) < 7 or not row[2].startswith(IMAGE + " ("):
            continue
        if row[0].strip() == "ImageId" and row[6].strip(' "') == IMAGE:
            bases.add(int(row[3], 16))
        if row[0].strip() == "SampledProfile":
            stamp, thread = int(row[1]), int(row[3])
            threads.add(thread)
            key = (stamp, thread)
            if key in samples:
                raise ValueError("duplicate timestamp and trainer thread")
            samples[key] = (int(row[4], 16), int(row[8]))
    if len(bases) != 1 or not samples:
        raise ValueError("missing or ambiguous trainer image identity")
    image_base, = bases

    def in_trainer(address):
        return TEXT_START <= address - image_base < TEXT_END

    stacks = defaultdict(list)
    for row in events(trace):
        if len(row) < 5 or row[0].strip() != "Stack" or not row[1].isdigit():
            continue
        stamp, thread = int(row[1]), int(row[2])
        key = (stamp, thread)
        if thread in threads and key in samples:
            stacks[key].append((int(row[3]), int(row[4], 16)))

    names = defaultdict(list)
    for line in linker_map.read_text().splitlines():
        fields = line.split()
        if len(fields) >= 4 and re.fullmatch(r"0001:[0-9a-f]{8}", fields[0]) and fields[3] == "f":
            address = int(fields[2], 16) - LINK_BASE
            if fields[1] not in names[address]:
                names[address].append(fields[1])
    starts = sorted(names)
    if not starts or starts[0] != TEXT_START:
        raise ValueError("linker map is missing the pinned code section")
    used = set()
    profiles = []
    origin = min(samples)[0]
    for key, (pc, weight) in sorted(samples.items()):
        leaf = pc - image_base if in_trainer(pc) else None
        # Return addresses point after the call. The sampled instruction is already exact.
        stack = [address - image_base - (address != pc)
                 for _, address in sorted(stacks[key]) if in_trainer(address)]
        for address in stack + ([] if leaf is None else [leaf]):
            index = bisect_right(starts, address) - 1
            if index < 0:
                raise ValueError("stack address precedes the linker map")
            used.add(starts[index])
        profiles.append([key[0] - origin, weight, leaf, stack])
    return {"format": "trainer-process-samples-v1", "profiles": profiles,
            "symbols": {str(address): names[address] for address in sorted(used)},
            "section_rva": TEXT_START, "section_end_rva": TEXT_END}


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("trace_csv", type=Path)
    parser.add_argument("linker_map", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    normalized = normalize(args.trace_csv, args.linker_map)
    with args.output.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(normalized, separators=(",", ":")).encode(), mtime=0))
