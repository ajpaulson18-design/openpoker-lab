"""Whole-request refusal ordering and the coupled-policy retention invariant."""
from itertools import product
import unittest
from unittest.mock import patch
from tests.virtual_role_walk_reference import Context,plan,Q
from tests.virtual_role_walk_wire_reference import verify
from tests.opponent_role_epoch_reference import allocate


class RoleWalkAdmissionTests(unittest.TestCase):
    def test_each_complete_reference_limit_refuses_before_physical_preparation(self):
        args=(0,((0,0),(0,0)),'first');reservation=plan(*args)['complete']
        with patch('tests.virtual_role_walk_reference.build_law',side_effect=AssertionError('physical preparation entered')):
            for name,amount in reservation.items():
                with self.subTest(limit=name),self.assertRaisesRegex(ValueError,'reference admission rejected'):
                    Context(*args,limits={name:amount-1})

    def test_all_foreign_domains_refuse_before_physical_preparation(self):
        with patch('tests.virtual_role_walk_reference.build_law',side_effect=AssertionError('physical preparation entered')):
            for args in ((True,((0,0),(0,0)),'first'),(2,((0,0),(0,0)),'first'),
                (0,((1624350,0),(0,0)),'first'),(0,((0,34246080),(0,0)),'first'),
                (0,((0,0),(0,0)),'random'),(0,((0,0),(0,0)),'first',{'work':500000001})):
                with self.subTest(args=args),self.assertRaises(ValueError):Context(*args)

    def test_invalid_wire_refuses_before_reference_context(self):
        with patch('tests.virtual_role_walk_wire_reference.Context',side_effect=AssertionError('unadmitted math entered')):
            for raw,request in ((b'',b''),(b'OPLROW01',b'OPLRIN01'+b'\0'*88),(b'\0'*549281,b'')):
                with self.subTest(length=len(raw)),self.assertRaises(ValueError):
                    verify(raw,request,0,((0,0),(0,0)),'first')

    def test_nonzero_regrets_cannot_cancel_under_their_own_centered_matching_policy(self):
        # If a centered update erased R, it would be -R. The matching-policy
        # dot product below proves that update is not centered. This is a
        # finite independent control of the general sign/support argument,
        # including Q52 rounding; it is not a lifetime admission.
        checked=0
        for k in (2,3,4):
            for regrets in product(range(-2,3),repeat=k):
                units=allocate(regrets);self.assertEqual(sum(units),Q)
                if not any(regrets):continue
                dot=sum(r*u for r,u in zip(regrets,units))
                if any(r>0 for r in regrets):
                    self.assertGreater(dot,0)
                    self.assertTrue(all(u==0 for r,u in zip(regrets,units) if r<=0))
                else:self.assertLess(dot,0)
                checked+=1
        self.assertEqual(checked,772)
        # Arbitrary policies do not establish this theorem: uniform with
        # R=(1,-1) admits a centered erasing update. Coupling is essential.
        self.assertEqual(sum(r*u for r,u in zip((1,-1),(Q//2,Q//2))),0)


if __name__=='__main__':unittest.main()
