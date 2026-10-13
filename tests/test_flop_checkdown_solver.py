"""Direct flop strategy, independent legality/BR and pre-ranking admission."""
import copy
import unittest
from unittest.mock import patch
from pokerlab import flop_checkdown_solver as solver
from pokerlab import flop_checkdown_worlds as chance
from scripts.flop_checkdown_validation import prepare_oracle, replay

ANCHOR = {'pot':2,'effective_stack':1,'bet_sizes':[.5], 'raise_sizes':[],
          'max_raises':0,'include_all_in':True}
WEIGHTED = {'pot':5.5,'effective_stack':[3.25,7.75],'bet_sizes':[.25,.5,1],
            'raise_sizes':[.25,.75],'max_raises':2,'include_all_in':True}


class DirectFlopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.anchor = prepare_oracle('2c3c4d','AsAd','KsKd',ANCHOR)
        cls.weighted = prepare_oracle('4d2c3c','AsAd:.5,QsQd:.25,2c2d',
                                      'KsKd,AhKh:.5,QsQd:.75',WEIGHTED)

    def test_known_value_equilibrium_and_learned_accuracy(self):
        result = solver.solve_flop_checkdown('2c3c4d','AsAd','KsKd',config=ANCHOR,iterations=100)
        replay(result,self.anchor)
        self.assertLess(result['nash_conv'],.0001)
        self.assertLess(abs(result['value_oop']-1),.0001)
        certificate = copy.deepcopy(result)
        for row in certificate['strategy']:
            # OOP shoves; IP folds to the shove. Complete all other legal rows.
            desired = ('all_in' if not row['history'] else 'call') if row['player']=='oop' else ('check' if row['history']==['check'] else 'fold')
            for a in row['actions']:
                a['probability'] = float(a['name']==desired)
        certificate.update(value_oop=1.,value_ip=-1.,oop_best_response_value=1.,
                           ip_best_response_value=-1.,nash_conv=0.,exploitability=0.)
        self.assertEqual(replay(certificate,self.anchor)['nash_conv'],0.)

    def test_weighted_asymmetric_raises_and_hidden_checkdown(self):
        for algorithm in ('vanilla','dcfr','cfrplus'):
            with self.subTest(algorithm=algorithm):
                result=solver.solve_flop_checkdown('4d2c3c','AsAd:.5,QsQd:.25,2c2d',
                    'KsKd,AhKh:.5,QsQd:.75',config=WEIGHTED,iterations=20,algorithm=algorithm)
                replay(result,self.weighted)
                self.assertEqual(result['compatible_pairs'],5)
                self.assertEqual(result['physical_worlds'],9900)
                self.assertLessEqual(result['training_world_rows'],15)
                self.assertTrue(any(a['name']=='raise' for r in result['strategy'] for a in r['actions']))
                self.assertTrue(all(r['board']==['2c','3c','4d'] for r in result['strategy']))
                self.assertTrue(all(not any('turn' in h or 'river' in h for h in r['history']) for r in result['strategy']))
                self.assertEqual(result['work_budget']['vector_upper_bound']['iterations'],20)

    def test_positive_terminal_mass_underflow_rejects_instead_of_losing_support(self):
        with self.assertRaisesRegex(ValueError,'terminal chance mass underflows'):
            solver.solve_flop_checkdown('2c3c4d','AsAd:5e-324,QsQd','KsKd',
                                        config=ANCHOR,iterations=10)

    def test_inactive_hand_index_holes_preserve_active_identity_and_budget(self):
        oop,ip='AsAd,QsQd,KsKd','AsAh'
        result=solver.solve_flop_checkdown('2c3c4d',oop,ip,config=ANCHOR,iterations=10)
        replay(result,prepare_oracle('2c3c4d',oop,ip,ANCHOR))
        own={r['hand'] for r in result['strategy'] if r['player']=='oop'}
        self.assertEqual(own,{'QdQs','KdKs'})
        self.assertEqual(result['compatible_pairs'],2)

    def test_work_and_state_rejections_precede_ranking(self):
        for target in ('MAX_TOTAL_LOOP_ENTRIES','MAX_PUBLIC_STATES','MAX_INFO_ACTION_SLOTS'):
            with self.subTest(target=target), patch.object(solver,target,1), patch.object(chance,'rank_hand') as rank:
                with self.assertRaises(ValueError):
                    solver.solve_flop_checkdown('2c3c4d','AsAd','KsKd',config=ANCHOR)
                rank.assert_not_called()

    def test_invalid_options_reject_before_chance_preparation(self):
        for changes in ({'iterations':True},{'iterations':9},{'algorithm':'invalid'},
                        {'config':'invalid'}):
            with self.subTest(changes=changes), patch.object(solver,'prepare_flop_worlds') as prepare:
                with self.assertRaises((ValueError,TypeError)):
                    solver.solve_flop_checkdown('2c3c4d','AsAd','KsKd',**changes)
                prepare.assert_not_called()

    def test_oracle_rejects_illegal_action_and_chance_tampering(self):
        result=solver.solve_flop_checkdown('2c3c4d','AsAd','KsKd',config=ANCHOR,iterations=10)
        bad=copy.deepcopy(result);bad['strategy'][0]['actions'][0]['amount']+=.01
        with self.assertRaisesRegex(AssertionError,'Action differs'):
            replay(bad,self.anchor)
        bad=copy.deepcopy(result);bad['pair_equities'][0]['wins']-=2
        with self.assertRaisesRegex(AssertionError,'Chance count'):
            replay(bad,self.anchor)


if __name__=='__main__':
    unittest.main()
