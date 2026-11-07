"""Independent corruption guards for paged State row wire verification."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from scripts.run_virtual_dyadic_training_cohort import verify_row_directory


class TinyFixture:
    def __init__(self, *, ten_card=False):
        if not ten_card:
            raise ValueError('fixture mode')
        self.paths = [(4,), (5,)]
        self.menus = {'first': ('a', 'b'), 'second': ('a', 'b')}

    def ordered_rows(self):
        return iter(('first', 'second'))

    def compact_key(self, history, actor, holding):
        if (history, actor, holding) == (0, 0, 0):
            return 'first'
        if (history, actor, holding) == (1 << 33, 1, 1):
            return 'second'
        raise ValueError('incorrect independent row identity')


def tiny_trace():
    return {'rows': 2, 'slots': 4, 'page_rows': 128, 'cache_pages': 8,
            'misses': 1, 'logical_reads': 20, 'hits': 19, 'read_bytes': 64,
            'write_calls': 1}


class DirectoryWireTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.rows = self.root / 'rows.bin'
        self.receipt = self.root / 'rows.json'
        self.stream = self.root / 'stream.bin'
        self.admission = {'rows': 2, 'slots': 4, 'row_directory_page_limit': 1,
                          'row_directory_read_call_limit': 20,
                          'packed_average_limbs': 4, 'packed_regret_limbs': 4}
        self.trace_patch = patch('scripts.run_virtual_dyadic_training_cohort.directory_trace', tiny_trace)
        self.fixture_patch = patch('scripts.run_virtual_dyadic_training_cohort.Fixture', TinyFixture)
        self.scales_patch = patch('scripts.run_virtual_dyadic_training_cohort.compact_scales',
                                  lambda fixture: [(640, 639), (640, 639)])
        for helper in (self.trace_patch, self.fixture_patch, self.scales_patch):
            helper.start()
            self.addCleanup(helper.stop)
        self.addCleanup(self.temp.cleanup)
        self.records = [
            (0, 0, (4 << 32) | (640 << 48), 639),
            (1 << 33, 2 | (2 << 32), 2 | (5 << 32) | (640 << 48),
             639 | (1 << 16) | (1 << 24)),
        ]
        self.write_rows()
        self.receipt.write_text(json.dumps(dict(appended_rows=2, build_snapshots=2, read_calls=20,
                                  cache_hits=19, page_reads=1, read_rows=2, write_calls=1, written_rows=2)))
        self.stream.write_bytes(bytes(224 + 1105 * 96) + struct.pack('<3Q', 0, 2 << 16, 0)
                                + struct.pack('<3Q', 1 << 33, 1 | (1 << 8) | (2 << 16), 2))

    def write_rows(self):
        self.rows.write_bytes(b''.join(struct.pack('<4Q', *record) for record in self.records))

    def verify(self):
        return verify_row_directory(self.root, self.stream, self.admission)

    def test_valid_independent_rows(self):
        result = self.verify()
        self.assertEqual((result['rows_bytes'], result['receipt']['read_rows']), (64, 2))

    def test_corrupt_fields_and_overlap_are_rejected(self):
        for index, word, mask in ((0, 0, 1), (0, 1, 1 << 32), (1, 1, 2),
                                  (1, 2, 1), (1, 2, 1 << 48), (1, 3, 1 << 32)):
            with self.subTest(index=index, word=word, mask=mask):
                original = self.records[index]
                changed = list(original); changed[word] ^= mask
                self.records[index] = tuple(changed); self.write_rows()
                with self.assertRaises(ValueError):
                    self.verify()
                self.records[index] = original
        self.write_rows()

    def test_wrong_receipt_and_truncated_file_are_rejected(self):
        data = json.loads(self.receipt.read_text()); data['page_reads'] += 1
        self.receipt.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.verify()
        data['page_reads'] -= 1; self.receipt.write_text(json.dumps(data))
        self.rows.write_bytes(self.rows.read_bytes()[:-1])
        with self.assertRaises(ValueError):
            self.verify()

    def test_receipt_size_is_bounded_before_reading(self):
        self.receipt.write_bytes(b' '*65537)
        original=Path.read_bytes
        def bounded_read(path):
            if path==self.receipt:
                raise AssertionError('oversized receipt was read')
            return original(path)
        with patch.object(Path,'read_bytes',bounded_read):
            with self.assertRaisesRegex(ValueError,'private and bounded'):
                self.verify()


if __name__ == '__main__':
    unittest.main()
