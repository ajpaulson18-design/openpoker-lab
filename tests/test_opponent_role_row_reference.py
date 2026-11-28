"""Arithmetic homogeneity and exact input centering, independent of native code."""
import unittest
from tests.opponent_role_row_reference import allocate,synthetic_rows,request_rows,encode,Q


class OpponentRoleRowReferenceTests(unittest.TestCase):
    def test_named_transcript_inventory_and_bounded_protocol(self):
        rows=request_rows();self.assertEqual(len(rows),97);self.assertLessEqual(len(encode(rows)),116000)
        for row in rows:
            current=row['initial'];cumulative=[0]*len(current)
            for r,a in row['steps']:
                self.assertEqual(sum(u*x for u,x in zip(current,r)),0)
                self.assertTrue(not any(a) or tuple(a)==current)
                cumulative=[x+y for x,y in zip(cumulative,r)]
                if any(r):current=allocate(cumulative)
    def test_homogeneity_signs_ties_and_tiny_positive_zero(self):
        for weights in ((1,1,1),(-7,0,2),(0,0),(1,Q*4,1),(7,11,0,3)):
            for shift in (0,52,260,312):self.assertEqual(allocate(weights),allocate([w<<shift for w in weights]))
        self.assertEqual(allocate((1,1,1)),(Q//3+1,Q//3,Q//3))
        self.assertEqual(allocate((1,Q*4,1)),(0,Q,0))
    def test_two_step_signed_cumulative_and_zero_update_cases(self):
        rows=synthetic_rows();self.assertEqual(len(rows),12)
        self.assertEqual(rows[-3]['steps'][0][0],(1,-1))
        self.assertEqual(tuple(sum(step[0][i] for step in rows[-3]['steps']) for i in (0,1)),(1,-2))
        self.assertEqual(rows[-2]['steps'][0],((0,0),(0,0)))
        cumulative=tuple(sum(step[0][i] for step in rows[-1]['steps']) for i in range(4))
        self.assertEqual(max(abs(r).bit_length() for r in cumulative),370)
        self.assertEqual(allocate(cumulative)[1],0);self.assertGreater(cumulative[1],0)


if __name__=='__main__':unittest.main()
