from fractions import Fraction as F
from types import SimpleNamespace as S
from dataclasses import replace
import unittest
from tests.test_virtual_frozen_probe_protocol import fixture, BOARD
from tests.test_virtual_frozen_update_comparison import reference
from tests.virtual_frozen_expectation import ExactExpectation, FORECAST

SECOND = (16,17,24,32,35)

def case(board=BOARD,law='uniform',regret_den=10,average_scale=1):
    raw=fixture().replace(b'board 16 17 24 32 33', ('board '+' '.join(map(str,board))).encode())
    raw=raw.replace(b'regret_denominator a',('regret_denominator '+format(regret_den,'x')).encode())
    if law=='river_weighted':raw=raw.replace(b'proposal UNIFORM',b'proposal RIVER_WEIGHTED')
    ref=reference();row=next(iter(ref.rows.values()))
    row=replace(row,regret_masses=(F(-2,regret_den),F(2,regret_den)))
    if average_scale!=1:
        raw=raw.replace(b'average a 4',('average '+format(10*average_scale,'x')+' '+format(4*average_scale,'x')).encode())
        raw=raw.replace(b'fold -2 2',('fold -2 '+format(2*average_scale,'x')).encode()).replace(b'call 2 2',('call 2 '+format(2*average_scale,'x')).encode())
    ref=S(admission=S(board=board,proposal_law=law),rows={row.key:row})
    return raw,ref

class ExpectationTests(unittest.TestCase):
    def test_uniform_partial_sum_is_exact_and_not_complete(self):
        owner=ExactExpectation('uniform')
        owner.add(*case());owner.add(*case(SECOND))
        row=next(iter(owner._rows.values()))
        self.assertEqual(F(row.regret[0],owner._regret_denominator),F(-1,6300))
        self.assertEqual(F(row.mass,row.denominator),F(1,3150))
        self.assertEqual(F(row.average[0],row.denominator),F(1,6300))
        with self.assertRaisesRegex(ValueError,'coverage incomplete'):owner.finish(S(rows={}))
        with self.assertRaisesRegex(ValueError,'consumed or failed'):owner.add(*case())
    def test_weighted_board_numerator_cancels_from_regret_denominator(self):
        owner=ExactExpectation('river_weighted')
        owner.add(*case(law='river_weighted',regret_den=10))
        owner.add(*case(SECOND,law='river_weighted',regret_den=12))
        row=next(iter(owner._rows.values()))
        self.assertEqual(F(row.regret[0],owner._regret_denominator),F(-1,6300))
        self.assertEqual(F(row.mass,row.denominator),F(11,31500))
    def test_duplicate_and_denominator_drift_poison_owner(self):
        for problem in ('duplicate','regret','average'):
            with self.subTest(problem=problem):
                owner=ExactExpectation('uniform');owner.add(*case())
                other=case() if problem=='duplicate' else case(SECOND,regret_den=20) if problem=='regret' else case(SECOND,average_scale=2)
                with self.assertRaises(ValueError):owner.add(*other)
                with self.assertRaisesRegex(ValueError,'consumed or failed'):owner.add(*case(SECOND))
    def test_reduce_only_whole_batch_admission(self):
        for field in FORECAST:
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError,'admission exceeded'):
                    ExactExpectation('uniform',limits={field:FORECAST[field]-1})
        with self.assertRaises(ValueError):ExactExpectation('selected')

if __name__ == '__main__':unittest.main()
