"""Bounded PE/public-map correspondence; no executable or source-line claims.

Only the AMD64 images with one COFFGRP debug-directory entry are admitted.
The original image must separately be authenticated against its build evidence.
Public names also require authenticated map/link-invocation provenance; address
coherence alone cannot authenticate symbol names. Seed RIP is never decremented.
For an unwound return PC, subtract one from its absolute address before selecting
a module, then use locate_public_function with that module RVA.
"""
from bisect import bisect_right
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

MAX_IMAGE_BYTES = 16 << 20
MAX_MAP_BYTES = 4 << 20
MAX_SYMBOLS = 65536

def need(value, message):
    if not value:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def bounded_read(path, limit):
    path = Path(path)
    need(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= limit,
         "image/map file type or size differs")
    before = path.stat()
    with path.open("rb") as stream:
        raw = stream.read(limit+1)
    after = path.stat()
    need(0 < len(raw) <= limit, "image/map read bound exceeded")
    need(before.st_size == len(raw) == after.st_size and
         (before.st_dev, before.st_ino, before.st_mtime_ns) ==
         (after.st_dev, after.st_ino, after.st_mtime_ns), "image/map extent changed during read")
    return raw

class Image:
    def __init__(self, raw):
        need(type(raw) is bytes and 264 <= len(raw) <= MAX_IMAGE_BYTES, "PE byte bound")
        self.raw = raw
        need(raw[:2] == b"MZ", "DOS signature differs")
        nt = self.u32(0x3c)
        need(64 <= nt <= len(raw)-264 and raw[nt:nt+4] == b"PE\0\0", "PE signature/bounds differ")
        machine, count, _, _, _, size, flags = struct.unpack_from("<HHIIIHH", raw, nt+4)
        op = nt+24
        need(machine == 0x8664 and 1 <= count <= 32 and size >= 240 and
             op+size+40*count <= len(raw) and self.u16(op) == 0x20b, "AMD64 PE32+ shape differs")
        need(self.u32(op+108) == 16, "PE data directory census differs")
        self.coff_stamp_offset = nt+8
        self.timestamp = self.u32(self.coff_stamp_offset)
        self.image_base = self.u64(op+24)
        self.entry = self.u32(op+16)
        self.image_size = self.u32(op+56)
        self.header_size = self.u32(op+60)
        need(self.header_size >= op+size+40*count and self.header_size <= len(raw) and
             0 < self.image_size <= MAX_IMAGE_BYTES, "PE image/header size differs")
        self.directories = [struct.unpack_from("<II", raw, op+112+8*i) for i in range(16)]
        self.sections = []
        for i in range(count):
            p = op+size+40*i
            name = raw[p:p+8].rstrip(b"\0").decode("ascii")
            virtual_size, rva, raw_size, offset = struct.unpack_from("<IIII", raw, p+8)
            characteristics = self.u32(p+36)
            need(virtual_size > 0 and rva >= self.header_size and
                 rva+max(virtual_size, raw_size) <= self.image_size and
                 offset+raw_size <= len(raw), "PE section span differs")
            need(not raw_size or offset >= self.header_size, "PE raw section overlaps header")
            self.sections.append(dict(name=name, rva=rva, virtual_size=virtual_size,
                                      raw_size=raw_size, offset=offset, flags=characteristics))
        for field, length in (("rva", lambda s:max(s["virtual_size"], s["raw_size"])),
                              ("offset", lambda s:s["raw_size"])):
            spans = sorted((s[field], s[field]+length(s)) for s in self.sections if length(s))
            need(all(a[1] <= b[0] for a,b in zip(spans, spans[1:])), "PE sections overlap")
        debug_rva, debug_size = self.directories[6]
        need(debug_size == 28, "one 28-byte debug entry required")
        debug = self.file_offset(debug_rva, 28, readonly=True)
        entry = struct.unpack_from("<IIHHIIII", raw, debug)
        need(entry[0] == 0 and entry[1] == self.timestamp and entry[4] == 13,
             "COFFGRP debug timestamp/type differs")
        payload_offset = self.file_offset(entry[6], entry[5], readonly=True)
        need(entry[5] > 0 and payload_offset == entry[7], "COFFGRP payload mapping differs")
        self.stamp_ranges = ((self.coff_stamp_offset, self.coff_stamp_offset+4),
                             (debug+4, debug+8))
        need(self.stamp_ranges[0][1] <= self.stamp_ranges[1][0], "timestamp masks overlap")
        self.debug_offset = debug

    def u16(self, p):
        need(0 <= p <= len(self.raw)-2, "PE integer read bound")
        return struct.unpack_from("<H", self.raw, p)[0]
    def u32(self, p):
        need(0 <= p <= len(self.raw)-4, "PE integer read bound")
        return struct.unpack_from("<I", self.raw, p)[0]
    def u64(self, p):
        need(0 <= p <= len(self.raw)-8, "PE integer read bound")
        return struct.unpack_from("<Q", self.raw, p)[0]

    def section(self, rva, size):
        need(type(rva) is int and type(size) is int and rva >= 0 and size > 0,
             "invalid RVA span")
        found = [s for s in self.sections
                 if s["rva"] <= rva and rva+size <= s["rva"]+s["virtual_size"]]
        need(len(found) == 1, "RVA not uniquely covered by section")
        return found[0]

    def file_offset(self, rva, size, *, readonly=False):
        section = self.section(rva, size)
        delta = rva-section["rva"]
        need(delta+size <= section["raw_size"], "RVA has no saved file bytes")
        if readonly:
            need(section["flags"] & 0x40000000 and
                 not section["flags"] & (0x20000000 | 0x80000000),
                 "metadata outside immutable non-code section")
        return section["offset"]+delta

    def normalized(self):
        result = bytearray(self.raw)
        for begin,end in self.stamp_ranges:
            result[begin:end] = b"\0"*(end-begin)
        return bytes(result)

    def runtime_functions(self):
        rva, size = self.directories[3]
        need(size > 0 and size % 12 == 0 and size//12 <= MAX_SYMBOLS,
             "AMD64 runtime function census differs")
        start = self.file_offset(rva, size, readonly=True)
        result = []
        for offset in range(start, start+size, 12):
            begin,end,unwind = struct.unpack_from("<III", self.raw, offset)
            need(begin < end and self.section(begin, end-begin)["flags"] & 0x20000000,
                 "runtime function outside executable extent")
            need(0 < unwind < self.image_size, "runtime unwind RVA differs")
            self.file_offset(unwind, 4, readonly=True)
            need(not result or begin >= result[-1]["end_rva"], "runtime function ranges overlap")
            result.append(dict(begin_rva=begin, end_rva=end, unwind_rva=unwind))
        return result

def verify_correspondence(original, mapped):
    left, right = Image(original), Image(mapped)
    need(len(original) == len(mapped) and left.stamp_ranges == right.stamp_ranges and
         left.sections == right.sections and left.directories == right.directories,
         "PE image structures differ")
    need(left.normalized() == right.normalized(), "PE bytes differ outside timestamp fields")
    differing = [i for i,(a,b) in enumerate(zip(original, mapped)) if a != b]
    return dict(status="public_map_image_correspondence_verified",
                original_sha256=sha(original), mapped_sha256=sha(mapped),
                normalized_sha256=sha(left.normalized()), image_base=left.image_base,
                entry_rva=left.entry, image_size=left.image_size,
                timestamp_ranges=[list(p) for p in left.stamp_ranges],
                original_timestamp=left.timestamp, mapped_timestamp=right.timestamp,
                differing_offsets=differing,
                limits="Only public RVA labels; no PDB, source-line, inline, or owner-cost inference")

SYMBOL = re.compile(r"^\s*([0-9A-Fa-f]{4}):([0-9A-Fa-f]{8,16})\s+(\S+)\s+([0-9A-Fa-f]{16})\s+(.+?)\s*$")
BASE = re.compile(r"^\s*Preferred load address is ([0-9A-Fa-f]{16})\s*$")
ENTRY = re.compile(r"^\s*entry point at\s+([0-9A-Fa-f]{4}):([0-9A-Fa-f]{8,16})\s*$")

def bind_public_map(original, mapped, map_bytes):
    correspondence = verify_correspondence(original, mapped)
    image = Image(mapped)
    need(type(map_bytes) is bytes and 0 < len(map_bytes) <= MAX_MAP_BYTES, "map byte bound")
    lines = map_bytes.decode("ascii").splitlines()
    bases = [int(m.group(1),16) for line in lines if (m := BASE.fullmatch(line))]
    entries = [m for line in lines if (m := ENTRY.fullmatch(line))]
    need(bases == [image.image_base] and len(entries) == 1, "map base or entry census differs")
    segment, offset = (int(x,16) for x in entries[0].groups())
    need(1 <= segment <= len(image.sections) and
         image.sections[segment-1]["rva"]+offset == image.entry, "map entry differs")
    active = False
    groups = {}
    count = 0
    for line in lines:
        if "Publics by Value" in line:
            need(not active and count == 0, "duplicate public symbol section")
            active = True
            continue
        if active and (ENTRY.fullmatch(line) or line.strip() == "Static symbols"):
            active = False
        if not active or not line.strip():
            continue
        match = SYMBOL.fullmatch(line)
        need(match is not None, "malformed public map record")
        seg, off, name, address, tail = match.groups()
        seg, off, address = int(seg,16), int(off,16), int(address,16)
        count += 1
        need(count <= MAX_SYMBOLS and len(name) <= 16384, "public symbol allowance exceeded")
        if seg == 0:
            continue
        need(1 <= seg <= len(image.sections), "public symbol section differs")
        section = image.sections[seg-1]
        need(off <= section["virtual_size"] and
             address == image.image_base+section["rva"]+off, "public symbol RVA differs")
        # Only function flags inside executable sections establish function starts.
        fields = tail.split()
        if "f" not in fields[:-1] or not section["flags"] & 0x20000000:
            continue
        rva = address-image.image_base
        groups.setdefault(rva, []).append(dict(name=name, object=fields[-1],
                                              flags=fields[:-1]))
    need(count > 0 and groups, "map contains no public functions")
    ranges = image.runtime_functions()
    admitted = []
    for record in ranges:
        aliases = groups.get(record["begin_rva"], [])
        if aliases:
            admitted.append(dict(record, aliases=aliases))
    need(admitted, "no public functions have proven runtime extents")
    return dict(version=1, correspondence=correspondence, map_sha256=sha(map_bytes),
                public_symbol_count=count, public_function_starts=len(groups),
                runtime_function_count=len(ranges), proven_function_ranges=admitted,
                public_starts_without_proven_extent=sorted(set(groups) -
                    {r["begin_rva"] for r in admitted}),
                unknown_policy="Offsets outside exact .pdata extents remain unresolved; aliases retained")

def locate_public_function(record, rva, *, return_address=False):
    need(type(rva) is int and 0 <= rva < 1 << 32 and type(return_address) is bool,
         "sample RVA/type differs")
    query = rva-1 if return_address and rva else rva
    ranges = record["proven_function_ranges"]
    index = bisect_right([r["begin_rva"] for r in ranges], query)-1
    if index >= 0 and query < ranges[index]["end_rva"]:
        return ranges[index]
    return None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--original-sha256", required=True)
    parser.add_argument("--mapped", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = bounded_read(args.original, MAX_IMAGE_BYTES)
    need(sha(original) == args.original_sha256, "authenticated original image hash differs")
    record = bind_public_map(original, bounded_read(args.mapped, MAX_IMAGE_BYTES),
                             bounded_read(args.map, MAX_MAP_BYTES))
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(record, output, indent=2, sort_keys=True)
        output.write("\n")
    print(json.dumps({k:record[k] for k in ("public_symbol_count",
                     "public_function_starts", "runtime_function_count")}))
if __name__ == "__main__":
    main()

