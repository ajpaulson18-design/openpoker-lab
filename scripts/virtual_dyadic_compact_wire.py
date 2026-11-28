"""Bounded codec for the compact N10 retained numerical stream.

The decoder expands one authenticated compact stream to the legacy N10 split
stream. It holds only one row's policy units and fixed-size I/O blocks.
"""
from __future__ import annotations

import struct

MAGIC = b'OPLDTC01'
LEGACY_MAGIC = b'OPLDTP01'
LEGACY_END = b'OPLDTP02'
U64 = struct.Struct('<Q')
HEADER_WORDS = 16
INT_WORDS = 11
VALUE_BITS = 644
DENOMINATOR = 3480 << 625
ROWS = 119_196
SLOTS = 281_066
LITERAL_COUNT = 1105
FOOTER_BYTES = 520
BLOCK_BYTES = 1 << 16
UNITS = 1 << 52


def retained_segments(rows=ROWS, slots=SLOTS, literal_count=LITERAL_COUNT):
    """Return named byte extents in the expanded legacy retained stream."""
    _positive(rows, slots, literal_count)
    prelude = 8 + HEADER_WORDS * 8 + INT_WORDS * 8 + literal_count * 96 + rows * 24
    sweep = slots * 8 + 4 * (1 + INT_WORDS) * 8
    final = slots * 8 + rows + FOOTER_BYTES
    return (('prelude', prelude), ('sweep1_policy_roots', sweep),
            ('sweep2_policy_roots', sweep), ('average_and_footer', final))


def retained_layout(rows=ROWS, slots=SLOTS, literal_count=LITERAL_COUNT):
    """Return absolute offsets and total extent for expanded legacy segments."""
    offset = 0
    result = {}
    for name, size in retained_segments(rows, slots, literal_count):
        result[name] = (offset, size)
        offset += size
    result['total_bytes'] = offset
    return result


def compact_size(rows=ROWS, slots=SLOTS, literal_count=LITERAL_COUNT):
    """Exact OPLDTC01 extent for the fixed two-sweep N10 profile."""
    _positive(rows, slots, literal_count)
    # header, denominator, literal skeleton, 6-byte rows; sweep-1 roots;
    # compact sweep-2 policy and roots; compact final average; flags/footer.
    return (8 + 8 * HEADER_WORDS + 8 * INT_WORDS + 96 * literal_count + 6 * rows
            + 384 + 7 * (slots - rows) + 384 + 7 * (slots - rows)
            + (rows + 7) // 8 + FOOTER_BYTES)


def compact_segments(rows=ROWS, slots=SLOTS, literal_count=LITERAL_COUNT):
    """Named byte extents in OPLDTC01 order, suitable for stream capture."""
    _positive(rows, slots, literal_count)
    prelude = 8 + HEADER_WORDS * 8 + INT_WORDS * 8 + literal_count * 96 + rows * 6
    policy = 7 * (slots - rows)
    return (('prelude', prelude), ('sweep1_roots', 384),
            ('sweep2_policy_roots', policy + 384), ('average_policy', policy),
            ('fallback_flags', (rows + 7) // 8), ('footer', FOOTER_BYTES))


def compact_layout(rows=ROWS, slots=SLOTS, literal_count=LITERAL_COUNT):
    """Return absolute compact offsets and total extent."""
    offset = 0
    result = {}
    for name, size in compact_segments(rows, slots, literal_count):
        result[name] = (offset, size)
        offset += size
    result['total_bytes'] = offset
    return result


def _positive(*values):
    if any(type(x) is not int or x <= 0 for x in values):
        raise ValueError('positive integer extents required')


def _read_exact(source, size):
    data = source.read(size)
    if len(data) != size:
        raise ValueError('truncated compact stream')
    return data


def _copy(source, dest, size):
    remaining = size
    while remaining:
        data = _read_exact(source, min(BLOCK_BYTES, remaining))
        if dest.write(data) != len(data):
            raise OSError('short expanded stream write')
        remaining -= len(data)


def _decode_rows(source, dest, rows, slots):
    offset = 0
    for _ in range(rows):
        word = int.from_bytes(_read_exact(source, 6), 'little')
        menu = (word & 3) + 1
        holding = (word >> 2) & 1
        actor = (word >> 3) & 1
        history = word >> 4
        if history >= 1 << 44:
            raise ValueError('compact history exceeds legacy row field')
        packed = actor | holding << 8 | menu << 16
        if dest.write(struct.pack('<QQQ', history, packed, offset)) != 24:
            raise OSError('short expanded row metadata write')
        offset += menu
        if offset > slots:
            raise ValueError('compact row slots exceed declared extent')
    if offset != slots:
        raise ValueError('compact row slot sum differs')


def _units_from_compact(source, dest, menu):
    values = []
    total = 0
    for _ in range(menu - 1):
        value = int.from_bytes(_read_exact(source, 7), 'little')
        if value > UNITS:
            raise ValueError('compact policy unit exceeds 52 bits')
        values.append(value)
        total += value
    if total > UNITS:
        raise ValueError('compact policy row exceeds unit mass')
    values.append(UNITS - total)
    for value in values:
        if dest.write(U64.pack(value)) != 8:
            raise OSError('short expanded policy write')


def _expand_policy(source, dest, row_start):
    row_index = 0
    while row_index < ROWS:
        count = min(BLOCK_BYTES // 6, ROWS - row_index)
        payload_at = source.tell()
        source.seek(row_start + row_index * 6)
        records = _read_exact(source, count * 6)
        source.seek(payload_at)
        for i in range(0, len(records), 6):
            _units_from_compact(source, dest, (records[i] & 3) + 1)
        row_index += count


def expand_compact(source, destination, *, source_size=None, block_bytes=BLOCK_BYTES):
    """Expand compact stream into exact legacy N10 retained encoding.

    `source` must be authenticated and seekable by the caller. Destination is
    truncated to zero only after header/profile checks. Returns byte counts.
    """
    if block_bytes != BLOCK_BYTES:
        raise ValueError('codec uses its fixed bounded block size')
    header = _read_exact(source, 8)
    if header != MAGIC:
        raise ValueError('compact magic differs')
    fields = struct.unpack('<16Q', _read_exact(source, 16 * 8))
    expected_prefix = (1, 52, INT_WORDS, ROWS, SLOTS, 1105, 2, 12, 1, 637,
                       VALUE_BITS, compact_size(), 2, 2, 29, 120)
    if fields != expected_prefix:
        raise ValueError('compact header is not the exact N10 profile')
    if source is destination:
        raise ValueError('compact source and expanded destination must differ')
    if source_size is not None and source_size != fields[11]:
        raise ValueError('compact source extent differs from header')
    legacy_bytes = retained_layout()['total_bytes']
    dest_header = struct.pack('<16Q', *fields[:11], legacy_bytes, *fields[12:])
    destination.seek(0)
    destination.truncate(0)
    if destination.write(LEGACY_MAGIC + dest_header) != 8 + len(dest_header):
        raise OSError('short legacy header write')
    denominator = _read_exact(source, INT_WORDS * 8)
    if int.from_bytes(denominator, 'little') != DENOMINATOR:
        raise ValueError('compact N10 denominator differs')
    if destination.write(denominator) != len(denominator):
        raise OSError('short legacy denominator write')
    _copy(source, destination, LITERAL_COUNT * 96)
    row_start = source.tell()
    row_offset = destination.tell()
    _decode_rows(source, destination, ROWS, SLOTS)
    resume = source.tell()
    source.seek(row_start)
    for _ in range(ROWS):
        word = int.from_bytes(_read_exact(source, 6), 'little')
        menu = (word & 3) + 1
        q, rem = divmod(UNITS, menu)
        for i in range(menu):
            value = q + int(i < rem)
            if destination.write(U64.pack(value)) != 8:
                raise OSError('short canonical policy write')
    source.seek(resume)
    _copy(source, destination, 384)  # sweep 1 four signed roots
    _expand_policy(source, destination, row_start)
    _copy(source, destination, 384)
    _expand_policy(source, destination, row_start)
    flags = _read_exact(source, (ROWS + 7) // 8)
    if ROWS % 8 and flags[-1] >> (ROWS % 8):
        raise ValueError('compact fallback flags have nonzero padding')
    flag_blocks = bytearray(min(BLOCK_BYTES, ROWS))
    written = 0
    while written < ROWS:
        count = min(len(flag_blocks), ROWS - written)
        for i in range(count):
            flag_blocks[i] = (flags[(written + i) >> 3] >> ((written + i) & 7)) & 1
        if destination.write(memoryview(flag_blocks)[:count]) != count:
            raise OSError('short expanded fallback flags write')
        written += count
    footer = _read_exact(source, FOOTER_BYTES)
    if footer[:8] != LEGACY_END:
        raise ValueError('compact footer magic differs')
    if destination.write(footer) != FOOTER_BYTES:
        raise OSError('short legacy footer write')
    if source.read(1):
        raise ValueError('compact trailing bytes')
    if destination.tell() != legacy_bytes:
        raise ValueError('expanded legacy extent differs')
    return {'compact_bytes': fields[11], 'legacy_bytes': legacy_bytes,
            'row_metadata_offset': row_offset}
