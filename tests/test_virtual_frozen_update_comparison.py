from fractions import Fraction as F
from types import SimpleNamespace as S
from dataclasses import replace
import unittest
from tests.test_virtual_frozen_probe_protocol import fixture, BOARD
from tests.virtual_frozen_sample_reference import SampledUpdateRow
from tests.virtual_frozen_update_comparison import compare_saved_update, FORECAST


def reference():
    row = SampledUpdateRow(0, (43,48), ('call',), ('fold','call'), (1,1),
                          (F(-1,5),F(1,5)), F(2,5), (F(1,5),F(1,5)), 1, 1)
    return S(admission=S(board=BOARD,proposal_law='uniform'),rows={row.key:row})

class ComparisonTests(unittest.TestCase):
    def test_complete_exact_values_and_unreduced_representation(self):
        raw = fixture()
        _, receipt = compare_saved_update(raw, reference())
        self.assertEqual(receipt['exact_scalar_comparisons'],5)
        self.assertEqual(receipt['native_producer_calls'],0)
        scaled = raw.replace(b'regret_denominator a',b'regret_denominator 14').replace(
            b'average a 4',b'average 14 8').replace(
            b'fold -2 2',b'fold -4 4').replace(b'call 2 2',b'call 4 4')
        compare_saved_update(scaled, reference())
    def test_semantic_mutations_that_pass_local_wire_invariants(self):
        raw = fixture()
        mutations = [
            raw.replace(b'fold -2 2',b'fold -4 2').replace(b'call 2 2',b'call 4 2'),
            raw.replace(b'average a 4',b'average a 8').replace(b'fold -2 2',b'fold -2 4').replace(b'call 2 2',b'call 2 4'),
            raw.replace(b'action 1 1 call',b'action 1 1 check'),
            raw.replace(b'token call',b'token check'),
            fixture(rows=False),
            raw.replace(b'row 0 0 43 48',b'row 0 1 24 37'),
        ]
        from tests.virtual_frozen_probe_protocol import parse
        for raw in mutations:
            with self.subTest(raw=raw[-160:]):
                parse(raw)
                with self.assertRaises(ValueError):
                    compare_saved_update(raw, reference())
    def test_admission_before_parsing_and_numeric_input_limit(self):
        with self.assertRaisesRegex(ValueError,'work admission'):
            compare_saved_update(b'bad', reference(),limits={'work':1})
        ref=reference();row=next(iter(ref.rows.values()))
        ref.rows[row.key]=replace(row,average_mass=F(1<<4096))
        with self.assertRaisesRegex(ValueError,'input bounds'):
            compare_saved_update(fixture(),ref)

if __name__ == '__main__':unittest.main()
