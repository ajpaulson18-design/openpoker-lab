import io
import struct
import unittest

from scripts import virtual_dyadic_compact_wire as codec


class CompactWireTests(unittest.TestCase):
    def test_compact_policy_rejects_overfull_entries_and_rows(self):
        for raw in ((codec.UNITS + 1).to_bytes(7, 'little') + bytes(7),
                    codec.UNITS.to_bytes(7, 'little') + (1).to_bytes(7, 'little')):
            with self.assertRaisesRegex(ValueError, '52 bits|unit mass'):
                codec._units_from_compact(io.BytesIO(raw), io.BytesIO(), 3)

    def test_row_inventory_rejects_wrong_slot_sum(self):
        destination = io.BytesIO()
        with self.assertRaisesRegex(ValueError, 'slot sum'):
            codec._decode_rows(io.BytesIO((0).to_bytes(6, 'little')),
                               destination, rows=1, slots=2)

    def test_public_layout_matches_retained_n10_extent(self):
        layout = codec.retained_layout()
        self.assertEqual(layout['total_bytes'], 9_833_076)
        self.assertEqual(layout['prelude'][1], 2_967_008)
        self.assertEqual(codec.compact_size(), 3_103_848)
        self.assertEqual(codec.compact_layout()['total_bytes'], 3_103_848)
        self.assertEqual(codec.retained_segments(2, 3, 1)[0], ('prelude', 8+128+88+96+48))

    def test_rejects_non_n10_compact_header_before_touching_destination(self):
        source = io.BytesIO(codec.MAGIC + bytes(16 * 8))
        destination = io.BytesIO(b'preserve')
        with self.assertRaisesRegex(ValueError, 'header'):
            codec.expand_compact(source, destination, source_size=codec.compact_size())
        self.assertEqual(destination.getvalue(), b'preserve')

    def test_compact_extent_is_fixed_and_bounded(self):
        # Omitted canonical sweep-1 policy saves exactly one 8-byte unit per slot;
        # each compact policy stores seven bytes for every non-final menu entry.
        expected = (8 + 128 + 88 + 96*1105 + 6*codec.ROWS + 384
                    + 7*(codec.SLOTS-codec.ROWS) + 384
                    + 7*(codec.SLOTS-codec.ROWS) + (codec.ROWS+7)//8 + 520)
        self.assertEqual(codec.compact_size(), expected)
        self.assertLess(codec.BLOCK_BYTES, codec.SLOTS * 8)

    def test_expands_a_complete_compact_shape_and_reconstructs_dense_offsets(self):
        source = io.BytesIO()
        header = (1, 52, 11, codec.ROWS, codec.SLOTS, 1105, 2, 12, 1, 637,
                  644, codec.compact_size(), 2, 2, 29, 120)
        source.write(codec.MAGIC + struct.pack('<16Q', *header))
        source.write(codec.DENOMINATOR.to_bytes(88, 'little'))
        source.write(bytes(1105 * 96))
        long_rows = 80_935
        for i in range(codec.ROWS):
            menu = 3 if i < long_rows else 1
            history = (1 << 44) - 1 if i == codec.ROWS - 1 else i
            word = (history << 4) | (menu - 1)
            source.write(word.to_bytes(6, 'little'))
        self.assertEqual(long_rows * 3 + (codec.ROWS-long_rows), codec.SLOTS)
        # The first sweep is omitted. Four signed zero roots follow it.
        source.write(bytes(384))
        for sweep in range(2):
            for _ in range(long_rows):
                source.write((codec.UNITS if sweep == 0 else 1).to_bytes(7, 'little'))
                source.write((0 if sweep == 0 else 2).to_bytes(7, 'little'))
            if sweep == 0:
                source.write(bytes(384))
        source.write(bytes((codec.ROWS + 7) // 8))
        source.write(codec.LEGACY_END + bytes(512))
        compact = source.getvalue()
        self.assertEqual(len(compact), codec.compact_size())
        source.seek(0)
        output = io.BytesIO()
        result = codec.expand_compact(source, output, source_size=len(compact))
        expanded = output.getvalue()
        self.assertEqual(result['legacy_bytes'], 9_833_076)
        self.assertEqual(len(expanded), 9_833_076)
        self.assertEqual(expanded[:8], codec.LEGACY_MAGIC)
        self.assertEqual(struct.unpack_from('<Q', expanded, 8 + 11*8)[0], 9_833_076)
        self.assertEqual(struct.unpack_from('<QQQ', expanded, result['row_metadata_offset']), (0, 3 << 16, 0))
        self.assertEqual(struct.unpack_from('<QQQ', expanded, result['row_metadata_offset'] + 24), (1, 3 << 16, 3))
        # Canonical 3-way uniform policy puts remainder units at earliest slots.
        policy_at = result['row_metadata_offset'] + codec.ROWS * 24
        canonical_third_row = policy_at + 6 * 8
        self.assertEqual(struct.unpack_from('<3Q', expanded, canonical_third_row),
                         (codec.UNITS//3+1, codec.UNITS//3, codec.UNITS//3))
        compact_third_row = policy_at + codec.SLOTS * 8 + 384 + 6 * 8
        self.assertEqual(struct.unpack_from('<3Q', expanded, compact_third_row),
                         (codec.UNITS, 0, 0))
        self.assertEqual(struct.unpack_from('<Q', expanded, result['row_metadata_offset'] + (codec.ROWS-1)*24)[0],
                         (1 << 44) - 1)
        self.assertEqual(expanded[-520:], codec.LEGACY_END + bytes(512))
        flags_at = len(compact) - 520 - ((codec.ROWS + 7) // 8)
        bad_padding = bytearray(compact)
        bad_padding[flags_at + (codec.ROWS // 8)] |= 1 << (codec.ROWS % 8)
        bad_footer = bytearray(compact)
        bad_footer[-520] ^= 1
        for malformed, message in ((bytes(bad_padding), 'padding'),
                                   (bytes(bad_footer), 'footer magic'),
                                   (compact[:-1], 'truncated')):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                codec.expand_compact(io.BytesIO(malformed), io.BytesIO(),
                                     source_size=len(compact))


if __name__ == '__main__':
    unittest.main()
