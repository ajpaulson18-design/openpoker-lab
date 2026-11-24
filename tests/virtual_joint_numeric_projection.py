"""Exact shared numerical bytes after the corresponding full verifier passes.

The resource/read/visit schema is intentionally excluded. Both versioned
verifiers must authenticate it independently before this comparison is used.
"""
import struct


def project(raw):
    if type(raw) is not bytes or not 1824 <= len(raw) <= 502752 or raw[:8] not in (b'OPLWEP01', b'OPLSGP01'):
        raise ValueError('joint numerical projection framing')
    output = bytearray(b'joint-fixed-tree-numeric-v1\0uniform-q52\0')
    output.extend(raw[40:48]); output.extend(raw[200:368])  # Q, deck/profile/counts, DR/DA.
    position = 368
    for _epoch in range(2):
        if position > len(raw) - 168:
            raise ValueError('joint numerical projection epoch header')
        header = struct.unpack_from('<20Q', raw, position + 8)
        rows, slots = header[11:13]
        size = 600 + 40 * rows + 144 * slots
        if rows > 868 or slots > 2078 or size != header[19] or size > len(raw) - position:
            raise ValueError('joint numerical projection epoch extent')
        output.extend(raw[position + 8:position + 8 + 13 * 8])
        output.extend(raw[position + 168:position + size - 256])  # Both roots and every row/R/A/unit.
        position += size
    if position + 256 != len(raw):
        raise ValueError('joint numerical projection final frame')
    return bytes(output)
