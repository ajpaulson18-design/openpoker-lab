"""Independent wire-format and failure guards for checkpoint page transport."""
import hashlib
import io
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
import zlib

from scripts.dyadic_checkpoint_transport import MAGIC, PAGE_BYTES, PageReader, pack_pages
from scripts.verify_virtual_dyadic_training import authenticated_packed_reader


HEADER = struct.Struct('<8sQ')
WORD = struct.Struct('<Q')
FORMAT_ERRORS = (ValueError, EOFError, OSError, zlib.error)


def compressed(data):
    encoder = zlib.compressobj(level=6, wbits=-15)
    return encoder.compress(data) + encoder.flush()


def wire(raw_bytes, frames):
    """Construct the specified offset-table format without the writer."""
    start = HEADER.size + WORD.size * (len(frames) + 1)
    offsets = [start]
    for frame in frames:
        offsets.append(offsets[-1] + len(frame))
    return (HEADER.pack(b'OPLPGZ01', raw_bytes)
            + b''.join(WORD.pack(offset) for offset in offsets)
            + b''.join(frames))


def reader(data, raw_bytes):
    return PageReader(io.BytesIO(data), raw_bytes, len(data))


class CheckpointTransportTests(unittest.TestCase):
    def test_constants_and_independent_raw_compressed_short_final(self):
        self.assertEqual((MAGIC, PAGE_BYTES), (b'OPLPGZ01', 32768))
        # A raw frame may contain arbitrary bytes. The two following pages are
        # constructed independently of pack_pages, including a short tail.
        raw = bytes((i * 73 + i // 251) & 255 for i in range(PAGE_BYTES))
        middle = b'B' * PAGE_BYTES
        tail = b'last-page!' * 84
        frames = (raw, compressed(middle), compressed(tail))
        self.assertLess(len(frames[1]), PAGE_BYTES)
        self.assertLess(len(frames[2]), len(tail))
        original = raw + middle + tail
        instance = reader(wire(len(original), frames), len(original))
        self.assertEqual(instance.read_page(0), raw)
        self.assertEqual(instance.read_page(1), middle)
        self.assertEqual(instance.read_page(2), tail)
        self.assertEqual(instance.decoded_sha256(), hashlib.sha256(original).hexdigest())
        self.assertEqual(instance.read(17), original[:17])
        self.assertEqual(instance.read(PAGE_BYTES), original[17:17 + PAGE_BYTES])
        # Digest checks do not alter the sequential cursor.
        self.assertEqual(instance.decoded_sha256(), hashlib.sha256(original).hexdigest())
        self.assertEqual(instance.read(23), original[17 + PAGE_BYTES:40 + PAGE_BYTES])

    def test_writer_round_trip_and_actual_raw_fallback(self):
        # SHA-derived bytes are deterministic and effectively incompressible.
        raw = b''.join(hashlib.sha256(i.to_bytes(8, 'little')).digest()
                       for i in range(PAGE_BYTES // 32))
        original = raw + b'Q' * 72
        stream = io.BytesIO()
        digest = pack_pages(io.BytesIO(original), stream, len(original))
        self.assertEqual(digest, hashlib.sha256(original).hexdigest())
        payload = stream.getvalue()
        magic, length = HEADER.unpack_from(payload)
        self.assertEqual((magic, length), (b'OPLPGZ01', len(original)))
        offsets = struct.unpack_from('<3Q', payload, HEADER.size)
        self.assertEqual(offsets[1] - offsets[0], PAGE_BYTES)
        self.assertEqual(payload[offsets[0]:offsets[1]], raw)
        instance = reader(payload, len(original))
        self.assertEqual(instance.read_page(0), raw)
        self.assertEqual(instance.read_page(1), b'Q' * 72)
        self.assertEqual(instance.read(PAGE_BYTES), raw)
        self.assertEqual(instance.read(72), b'Q' * 72)
        self.assertEqual(instance.read(1), b'')

    def test_offsets_magic_and_trailing_bytes_rejected(self):
        raw = b'Z' * PAGE_BYTES
        valid = bytearray(wire(len(raw), [compressed(raw)]))
        start, end = struct.unpack_from('<2Q', valid, HEADER.size)
        bad = []
        wrong_magic = valid.copy(); wrong_magic[0] ^= 1; bad.append(wrong_magic)
        wrong_size = valid.copy(); struct.pack_into('<Q', wrong_size, 8, len(raw) + 1); bad.append(wrong_size)
        bad_start = valid.copy(); struct.pack_into('<Q', bad_start, HEADER.size, start - 1); bad.append(bad_start)
        reversed_offsets = valid.copy(); struct.pack_into('<Q', reversed_offsets, HEADER.size + 8, start - 1); bad.append(reversed_offsets)
        past_end = valid.copy(); struct.pack_into('<Q', past_end, HEADER.size + 8, end + 1); bad.append(past_end)
        zero_frame = valid.copy(); struct.pack_into('<Q', zero_frame, HEADER.size + 8, start); bad.append(zero_frame)
        bad.append(valid + b'X')
        for content in bad:
            with self.subTest(data=bytes(content[:32])):
                with self.assertRaises(FORMAT_ERRORS):
                    item = reader(bytes(content), len(raw))
                    item.read_page(0)

    def test_bad_deflate_and_oversized_inflation_rejected(self):
        # Both frames are shorter than a decoded page, forcing DEFLATE mode.
        for frame in (b'\xff\xff\xff', compressed(b'X' * (PAGE_BYTES + 1)),
                      compressed(b'Y' * PAGE_BYTES) + b'extra'):
            with self.subTest(length=len(frame)):
                self.assertLess(len(frame), PAGE_BYTES)
                with self.assertRaises(FORMAT_ERRORS):
                    item = reader(wire(PAGE_BYTES, [frame]), PAGE_BYTES)
                    item.read_page(0)

    def test_invalid_read_bounds_rejected(self):
        content = wire(8, [b'abcdefgh'])
        for operation in (lambda r: r.read_page(-1), lambda r: r.read_page(1),
                          lambda r: r.read(-1), lambda r: r.read(PAGE_BYTES + 1)):
            with self.subTest(operation=operation):
                with self.assertRaises((ValueError, IndexError, EOFError, OSError)):
                    operation(reader(content, 8))

    def test_packed_reader_requires_independent_stored_and_decoded_pins(self):
        decoded = b'12345678'
        payload = wire(len(decoded), [decoded])
        raw_hash = hashlib.sha256(decoded).hexdigest()
        packed_hash = hashlib.sha256(payload).hexdigest()
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as directory:
            path = Path(directory) / 'image.pgi'
            path.write_bytes(payload)
            for supplied_packed, supplied_raw, message in (
                ('0' * 64, raw_hash, 'saved input sha256'),
                (packed_hash, '0' * 64, 'decoded checkpoint sha256'),
            ):
                with self.subTest(message=message):
                    with self.assertRaisesRegex(ValueError, message):
                        with authenticated_packed_reader(path, supplied_packed, supplied_raw, len(decoded), 644):
                            self.fail('unauthenticated checkpoint reader entered')
            with authenticated_packed_reader(path, packed_hash, raw_hash, len(decoded), 644) as (item, _, size):
                self.assertEqual(size, len(payload))
                self.assertEqual(item.read(len(decoded)), decoded)
                item.finish(raw_hash)


if __name__ == '__main__':
    unittest.main()
