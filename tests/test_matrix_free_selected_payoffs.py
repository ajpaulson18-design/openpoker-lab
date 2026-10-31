import math
import unittest
from fractions import Fraction as F
from unittest.mock import patch
from types import MappingProxyType

from scripts.matrix_free_certificate_budget import Budget
from scripts.matrix_free_selected_payoffs import PayoffModel
from scripts.preflop_validation import independent_rank


class PayoffControls(unittest.TestCase):
    def setUp(self):
        self.ranges = ({('Ac','Ad'): 0.7, ('Ks','Kh'): 0.3, ('2c','2d'): 5e-324},
                       {('Ac','Ad'): 0.4, ('Qs','Qh'): 0.6, ('Kc','Kd'): 0.2})
        self.boards = (('3c','4d','5h','9s','Tc'), ('3c','4d','5h','9s','Jc'),
                       ('2c','4d','5h','9s','Tc'))
        self.model = PayoffModel(self.ranges, self.boards, Budget())

    def literal(self, player, reach, prefix, matched, winner):
        hs, ws = self.model.hands, self.model.weights
        z = F(0); out = [F(0)] * len(hs[player])
        for board in self.boards:
            for i, a in enumerate(hs[0]):
                for j, c in enumerate(hs[1]):
                    if len(set(a + c + board)) != 9: continue
                    mass = ws[0][i] * ws[1][j]
                    z += mass
                    if board[:len(prefix)] != prefix: continue
                    sign = ((1 if winner == player else -1) if winner is not None else
                            ((independent_rank(a + board) > independent_rank(c + board)) -
                             (independent_rank(a + board) < independent_rank(c + board))) * (1 if player == 0 else -1))
                    own = i if player == 0 else j
                    other = j if player == 0 else i
                    out[own] += mass * F(reach[other]) * F(matched) * sign
        return tuple(x / z for x in out), z

    def test_literal_all_prefixes_seats_and_signs(self):
        for prefix in ((), self.boards[0][:3], self.boards[0][:4], self.boards[0], ('Ah','Kh','Qh')):
            for player in (0,1):
                for winner in (None,0,1):
                    for reach in ((0.0,0.5,1.0), (1.0,1.0,1.0)):
                        with self.subTest(prefix=prefix,player=player,winner=winner,reach=reach):
                            actual = self.model.terminal(player, reach, prefix, 0.1, winner)
                            expected,z = self.literal(player,reach,prefix,0.1,winner)
                            self.assertEqual(actual,expected)
                            self.assertEqual(self.model.normalizerZ,z)

    def test_support_independent_of_reach_and_blockers(self):
        support = self.model.prefix_support(self.boards[2])
        self.assertFalse(support[0][2])
        self.assertEqual(self.model.prefix_support(('Ah','Kh','Qh')), ((False,)*3,(False,)*3))
        self.assertEqual(self.model.terminal(0,(0.,0.,0.),(),1.,None),(F(0),)*3)

    def test_tie_and_identical_holding_addback(self):
        model=PayoffModel(({('2c','3c'):1.0,('4c','5c'):1.0},
                           {('2c','3c'):1.0,('6c','7c'):1.0}),
                          (('Ts','Js','Qs','Ks','As'),),Budget())
        self.assertEqual(model.terminal(0,(1.,1.),(),1.,None),(F(0),F(0)))
        self.assertEqual(model.terminal(0,(1.,1.),(),1.,0),(F(1,3),F(2,3)))

    def test_duplicate_flop_order_is_not_a_second_outcome(self):
        board = self.boards[0]
        with self.assertRaises(ValueError):
            PayoffModel(self.ranges, (board, (board[1], board[0], *board[2:])), Budget())

    def test_legacy_hand_order_and_bounded_rank_cache(self):
        model = PayoffModel((MappingProxyType({('Ad','Ks'): 1.0}),
                             {('Qc','Qh'): 1.0}), (self.boards[0],), Budget())
        from pokerlab.cards import expand_range
        self.assertEqual(model.hands[0], tuple(expand_range('AdKs')))
        self.assertEqual(model.hands[0], (('Ad','Ks'),))
        first = model.terminal(0,(1.0,),(),1.0,None)
        receipt = model.receipt()
        self.assertEqual((receipt['rank_calls'],receipt['rank_cache_entries']), (2,2))
        self.assertEqual(model.terminal(0,(0.5,),(),1.0,None), tuple(x / 2 for x in first))
        self.assertEqual(model.receipt()['rank_calls'],2)
        self.assertEqual(model.terminal(1,(1.0,),(),1.0,None), tuple(-x for x in first))
        self.assertEqual(model.receipt()['rank_calls'],2)

    def test_custom_mapping_rejected_without_hook_execution(self):
        from collections.abc import Mapping
        class Untrusted(Mapping):
            def __getitem__(self,key): raise AssertionError('hook')
            def __iter__(self): raise AssertionError('hook')
            def __len__(self): raise AssertionError('hook')
        with self.assertRaises(ValueError):
            PayoffModel((Untrusted(), self.ranges[1]), self.boards, Budget())

    def test_physical_metadata_matches_literal_deals(self):
        worlds = []
        for a in self.model.hands[0]:
            for b in self.model.hands[1]:
                for board in self.boards:
                    if len(set(a+b+board)) == 9:
                        worlds.append((a,b,board))
        self.assertEqual(self.model.physical_worlds, len(worlds))
        self.assertEqual(self.model.compatible_pairs, len({(a,b) for a,b,_ in worlds}))
        self.assertEqual(self.model.reachable_boards, tuple(x for x in self.boards if any(w[2] == x for w in worlds)))
        self.model.prefix_support(())
        self.model.terminal(0,(1.,1.,1.),(),1.,None)
        receipt = self.model.receipt()
        self.assertEqual((receipt['support_queries'], receipt['terminal_calls']), (1,1))
        self.assertGreater(receipt['rank_calls'],0)
        self.assertEqual((receipt['stored_pairs'], receipt['stored_worlds']), (0,0))

    def test_canonical_flop_and_invalid_boolean_before_arithmetic(self):
        board = self.boards[0]
        other = (board[1], board[0], *board[2:])
        model = PayoffModel(self.ranges, (other,), Budget())
        self.assertEqual(model.boards, (board,))
        self.assertEqual(model.prefix_support(other[:3]), model.prefix_support(board[:3]))
        budget = Budget()
        with self.assertRaises(ValueError):
            PayoffModel(({('Ac','Ad'): True}, self.ranges[1]), self.boards, budget)
        self.assertEqual(budget.receipt()['created_bits'], 0)

    def test_invalid_and_bounded_input(self):
        with self.assertRaises(ValueError): self.model.terminal(0,(1,1),(),1,None)
        with self.assertRaises(ValueError): self.model.terminal(0,(1,1,math.inf),(),1,None)
        with self.assertRaises(ValueError): self.model.terminal(0,(1,1,1),('Ah',),1,None)
        class Liar:
            def __len__(self): return 3
            def __iter__(self):
                yield from (1,1,1,1)
        with self.assertRaises(ValueError): self.model.terminal(0,Liar(),(),1,None)

class BudgetControls(unittest.TestCase):
    def test_preflight_rejects_before_fraction_operation(self):
        b=Budget({'integer_bits': 20})
        a=b.input(F(1, 2**10),'a')
        before=b.receipt()
        with self.assertRaises(ValueError): b.mul(a,a,'product')
        self.assertEqual(b.receipt(),before)

    def test_compare_signed_and_before_crossproducts(self):
        b = Budget({'integer_bits': 20})
        self.assertEqual(b.compare(F(-1,3),F(1,4),'cmp'),-1)
        self.assertEqual(b.compare(F(1,2),F(2,4),'cmp'),0)
        a = b.input(F(1023, 2**10),'a')
        before = b.receipt()
        with self.assertRaises(ValueError): b.compare(a,a,'cmp')
        self.assertEqual(b.receipt(),before)

    def test_cumulative_and_reduce_only_guards(self):
        with self.assertRaises(ValueError): Budget({'work':500_000_001})
        b=Budget({'created_bits':4})
        a=b.input(1,'a')
        with self.assertRaises(ValueError): b.add(a,a,'sum')
        self.assertEqual(b.receipt()['created_bits'],2)
        with self.assertRaises(ValueError): b.input(float('nan'),'nan')
        with self.assertRaises(ZeroDivisionError): Budget().div(F(1),F(0),'division')

if __name__ == '__main__': unittest.main()
