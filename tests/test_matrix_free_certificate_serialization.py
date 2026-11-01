import hashlib
import json
import math
import unittest
from fractions import Fraction
from unittest.mock import patch

from scripts.matrix_free_certificate_budget import Budget
from scripts.matrix_free_certificate_serialization import clone_json, canonical_hash, FractionText

class SerializationControls(unittest.TestCase):
    def test_canonical_ascii_unicode_and_key_order(self):
        value = {'z': ['a\n\x00', '\U0001f600', '\u00e9'], 'a': {'b': 1, 'a': False}}
        b = Budget()
        snapshot, clone_receipt = clone_json(value, b)
        digest, receipt = canonical_hash(snapshot, b)
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'),ensure_ascii=True).encode('ascii')
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
        self.assertGreaterEqual(receipt['json_bytes_upper'],len(raw))
        self.assertEqual(receipt['ascii_bytes'],len(raw))
        self.assertEqual(receipt['work_delta'],sum(receipt['counters_delta'].values()))
        self.assertGreater(clone_receipt['entry_delta'],0)
        value['z'].append('mutated')
        self.assertEqual(len(snapshot['z']),3)

    def test_custom_input_and_nonfinite_rejected(self):
        class Evil(list):
            def __iter__(self): raise AssertionError('unexpected hook')
        for value in (Evil(), {'a': float('nan')}, {'a': object()}, {'a': 1 << 4096}, {1: 'x'}):
            with self.subTest(value=type(value)), self.assertRaises(ValueError): clone_json(value,Budget())

    def test_hash_rejects_before_json_encoding(self):
        with patch('scripts.matrix_free_certificate_serialization.json.dumps', side_effect=AssertionError('called')) as dumps:
            with self.assertRaises(ValueError): canonical_hash({'x':'x'*200},Budget({'work':100}))
            dumps.assert_not_called()
        with patch('scripts.matrix_free_certificate_serialization.json.dumps', side_effect=AssertionError('called')) as dumps:
            with self.assertRaises(ValueError): canonical_hash({'a':[1,2,3]},Budget({'entries':1}))
            dumps.assert_not_called()

    def test_snapshot_rejects_before_container_walk(self):
        with self.assertRaises(ValueError): clone_json([1,2], Budget({'entries':1}))
        with self.assertRaises(ValueError): clone_json({'x':'x'*4097}, Budget())
        with self.assertRaises(ValueError): clone_json({'x':math.inf}, Budget())

    def test_fraction_exact_and_cumulative_cap(self):
        fmt = FractionText(Budget())
        for f in (Fraction(0),Fraction(-1,3),Fraction(1<<1000,3), Fraction(-123456789)):
            self.assertEqual(fmt.format(f),str(f))
        self.assertEqual(fmt.receipt()['calls'],4)
        self.assertGreaterEqual(fmt.receipt()['bytes_upper'],sum(len(str(f)) for f in
              (Fraction(0),Fraction(-1,3),Fraction(1<<1000,3),Fraction(-123456789))))

    def test_fraction_rejects_before_decimal(self):
        for budget, limit in ((Budget(),1),(Budget({'work':1}),100), (Budget({'entries':1}),100)):
            with self.subTest(limit=limit,entries=budget.limits['entries']):
                if budget.limits['entries'] == 1: budget.entries(1,'exhaust')
                fmt = FractionText(budget,limit)
                with patch('scripts.matrix_free_certificate_serialization.Decimal',side_effect=AssertionError('called')) as dec:
                    with self.assertRaises(ValueError): fmt.format(Fraction(12345,17))
                    dec.assert_not_called()

    def test_fraction_strings_may_exceed_input_field_limit(self):
        value = {'fraction':'1'*4097}
        with self.assertRaises(ValueError): clone_json(value,Budget())
        digest, receipt = canonical_hash(value,Budget())
        self.assertEqual(len(digest),64)
        self.assertGreater(receipt['ascii_bytes'],4097)

if __name__ == '__main__': unittest.main()
