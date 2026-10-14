"""Synthetic numerical matrix tests; physical full-board equity is benchmarked.

Hand-constructed sign counts here are controlled payoff inputs, not claimed
real Hold'em equity. The frozen full-board experiment separately verifies all
actual physical counts with the independent best-five oracle.
"""
import copy
from fractions import Fraction
import unittest
from unittest.mock import patch
from pokerlab import preflop_push_fold as solver
from pokerlab.preflop_full_board_equity import plan_preflop_equities,FullBoardEquities,BOARDS_PER_PAIR
from scripts.preflop_push_fold_validation import replay,weighted_equilibrium_certificate

SB='AsAd:1,QsQd:.5'
BB='AsKh:.25,KsKd:1'
CONFIG={'small_blind':.5,'big_blind':1,'starting_stack':2}


def synthetic_table():
    plan=plan_preflop_equities(SB,BB)
    counts=[];worlds=[]
    for (i,j,prior),signed in zip(plan.pairs,(Fraction(3,4),Fraction(1,4),Fraction(-3,4))):
        wins=int(BOARDS_PER_PAIR*(1+signed)/2);losses=BOARDS_PER_PAIR-wins
        counts.append((wins,0,losses))
        for sign,count in ((-1,losses),(1,wins)):
            worlds.append((i,j,float(prior*Fraction(count,BOARDS_PER_PAIR)),sign))
    table=FullBoardEquities(plan.hands,plan.pairs,tuple(counts),tuple(worlds),plan._budget_items)
    reported=tuple({'sb_hand':''.join(plan.hands[0][i]),'bb_hand':''.join(plan.hands[1][j]),
        'wins':w,'ties':t,'losses':l,'boards':BOARDS_PER_PAIR,'pair_probability':float(prior)}
        for (i,j,prior),(w,t,l) in zip(plan.pairs,counts))
    return table,reported


class PushFoldTests(unittest.TestCase):
    def setUp(self):
        self.table,self.counts=synthetic_table()

    def test_independent_analytical_mixed_equilibrium_certificate(self):
        result=solver.solve_prepared_push_fold(self.table,config=CONFIG,iterations=100)
        certificate,exact=weighted_equilibrium_certificate(result,self.counts)
        self.assertEqual(exact,{'sb_qq_shove_fraction':[2,5],'bb_kk_call_fraction':[7,10],
                                'value_sb_fraction':[83,130]})
        checked=replay(certificate,SB,BB,CONFIG,self.counts)
        self.assertLess(checked['nash_conv'],1e-14)
        self.assertAlmostEqual(checked['value_sb'],83/130)

    def test_all_algorithms_and_delayed_cfrplus_match_visible_information_br(self):
        for algorithm,delay in (('vanilla',0),('dcfr',0),('cfrplus',0),('cfrplus',50)):
            with self.subTest(algorithm=algorithm,delay=delay):
                result=solver.solve_prepared_push_fold(self.table,config=CONFIG,
                    iterations=100,algorithm=algorithm,averaging_delay=delay)
                replay(result,SB,BB,CONFIG,self.counts)
                self.assertEqual(result['info_sets'],4)
                self.assertTrue(all(r['revealed_board']==[] for r in result['strategy']))
                self.assertEqual(result['work_budget']['requested_iterations'],100)

    def test_prepared_table_reuse_does_not_rank_or_mutate(self):
        before=self.table
        with patch('pokerlab.preflop_full_board_equity.rank_hand',side_effect=AssertionError('Re-ranked')):
            first=solver.solve_prepared_push_fold(self.table,config=CONFIG,iterations=100)
            second=solver.solve_prepared_push_fold(self.table,config=CONFIG,iterations=100)
        self.assertEqual(first,second)
        self.assertEqual(self.table,before)

    def test_blind_transfers_and_asymmetric_call_refunds_replay(self):
        for stacks in ([3,5],[5,3],[1.5,4]):
            config={**CONFIG,'starting_stack':stacks}
            result=solver.solve_prepared_push_fold(self.table,config=config,iterations=20)
            replay(result,SB,BB,config,self.counts)
            root=next(r for r in result['strategy'] if r['player']=='sb')
            response=next(r for r in result['strategy'] if r['player']=='bb')
            self.assertEqual(root['actions'][1]['raise_to'],stacks[0])
            self.assertEqual(response['actions'][1]['raise_to'],min(stacks))
            self.assertEqual(response['actions'][1]['amount'],min(stacks)-1)

    def test_invalid_options_and_full_requested_work_reject_before_equity_build(self):
        invalid=({'iterations':True},{'iterations':9},{'algorithm':'unknown'},
                 {'algorithm':'dcfr','averaging_delay':1},{'averaging_delay':1000},
                 {'config':{'starting_stack':[1,2]}},{'config':{'raise_sizes':[1]}})
        for changes in invalid:
            with self.subTest(changes=changes),patch.object(solver,'plan_preflop_equities') as plan:
                with self.assertRaises((TypeError,ValueError)):
                    solver.solve_preflop_push_fold(SB,BB,**changes)
                plan.assert_not_called()
        with patch('pokerlab.preflop_full_board_equity.PreflopEquityPlan.build') as build:
            with self.assertRaisesRegex(ValueError,'full-requested work'):
                solver.solve_preflop_push_fold(SB,BB,iterations=10000)
            build.assert_not_called()

    def test_oracle_rejects_wrong_blind_call_amount_and_revealed_cards(self):
        result=solver.solve_prepared_push_fold(self.table,config=CONFIG,iterations=10)
        bad=copy.deepcopy(result)
        next(r for r in bad['strategy'] if r['player']=='bb')['actions'][1]['amount']+=.01
        with self.assertRaisesRegex(AssertionError,'amount mismatch'):
            replay(bad,SB,BB,CONFIG,self.counts)
        bad=copy.deepcopy(result);bad['strategy'][0]['revealed_board']=['As']
        with self.assertRaises(AssertionError):
            replay(bad,SB,BB,CONFIG,self.counts)


if __name__=='__main__':
    unittest.main()
