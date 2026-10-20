"""Independent full-deck and conditioned flop CFR+ capability checks."""
import hashlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from pokerlab import postflop_solver as solver
from scripts import flop_multistreet_validation as reference
from scripts.benchmark_weighted_full_deck_flop import independent_guard

ROOT = Path(__file__).resolve().parents[1]
BOARD = '2c3d4h'
OOP = 'AsAd:1,QsQd:0.5'
IP = 'AsKh:0.25,KsKd:1'
OOP_HANDS = [['AdAs','1'],['QdQs','1/2']]
IP_HANDS = [['AsKh','1/4'],['KdKs','1']]
SMALL = dict(pot=10,effective_stack=5,bet_sizes=[.5],raise_sizes=[],max_raises=0,include_all_in=False)
METRICS = ('value_oop','value_ip','oop_best_response_value','ip_best_response_value',
           'oop_best_response_gain','ip_best_response_gain','nash_conv','exploitability')


class ReachedAdmittedTrainer(Exception):
    pass


def checked_replay(payload, oracle):
    with independent_guard() as calls:
        result = reference.replay(payload,oracle,tolerance=1e-10)
    if any(calls.values()):
        raise AssertionError('Oracle used production helpers')
    return result


def compare(testcase, a, b):
    testcase.assertEqual(len(a['strategy']),len(b['strategy']))
    for x,y in zip(a['strategy'],b['strategy']):
        testcase.assertEqual({k:v for k,v in x.items() if k!='actions'},
                             {k:v for k,v in y.items() if k!='actions'})
        testcase.assertEqual(len(x['actions']),len(y['actions']))
        for u,v in zip(x['actions'],y['actions']):
            testcase.assertEqual({k:w for k,w in u.items() if k!='probability'},
                                 {k:w for k,w in v.items() if k!='probability'})
            testcase.assertAlmostEqual(u['probability'],v['probability'],delta=1e-8)
    for key in METRICS:
        testcase.assertAlmostEqual(a[key],b[key],delta=1e-8,msg=key)


class FlopCFRPlusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with independent_guard() as calls:
            cls.full_oracle = reference.prepare_oracle(BOARD,OOP_HANDS,IP_HANDS,SMALL)
        if any(calls.values()):
            raise AssertionError('Independent preparation used production helpers')

    def test_full_deck_both_trainers_replay_without_future_information(self):
        profiles=[]
        for traversal in ('recursive','public-batched'):
            with self.subTest(traversal=traversal):
                payload=solver.solve_postflop(BOARD,OOP,IP,config=SMALL,
                    iterations=10,algorithm='cfrplus',traversal=traversal)
                audited=checked_replay(payload,self.full_oracle)
                self.assertEqual(audited['checked_physical_worlds'],5940)
                self.assertEqual(payload['training_passes_per_iteration'],3)
                self.assertEqual(payload['update_schedule'],'alternating-oop-then-ip')
                self.assertEqual(payload['average_schedule'],'linear-post-sweep-own-reach')
                self.assertTrue(any(row['street']=='turn' for row in payload['strategy']))
                self.assertTrue(any(row['street']=='river' for row in payload['strategy']))
                profiles.append(payload)
        compare(self,*profiles)

    def test_weighted_conditioned_raises_refunds_and_street_sizing_replay(self):
        config=dict(pot=10,effective_stack=[12,20],bet_sizes=[.5],raise_sizes=[.5],max_raises=1,include_all_in=True)
        turn=dict(config,bet_sizes=[.75]);river=dict(config,bet_sizes=[.25])
        runouts=[('As','5c'),('5c','As'),('5c','9h')]
        with independent_guard():
            oracle=reference.prepare_oracle(BOARD,OOP_HANDS,IP_HANDS,config,
                        turn_config=turn,river_config=river,runouts=runouts)
        for iterations in (10,30,100):
            profiles=[]
            for traversal in ('recursive','public-batched'):
                with self.subTest(iterations=iterations,traversal=traversal):
                    payload=solver.solve_postflop(BOARD,OOP,IP,config=config,
                        turn_config=turn,river_config=river,runouts=runouts,
                        iterations=iterations,algorithm='cfrplus',traversal=traversal)
                    checked_replay(payload,oracle);profiles.append(payload)
            compare(self,*profiles)

    def test_full_requested_three_pass_bound_precedes_both_trainers(self):
        for traversal in ('recursive','public-batched'):
            with self.subTest(traversal=traversal):
                with patch.object(solver,'train_plus',side_effect=ReachedAdmittedTrainer) as recursive, \
                     patch.object(solver,'train_public_batched',side_effect=ReachedAdmittedTrainer) as public:
                    with self.assertRaisesRegex(ValueError,'30 million world-node'):
                        solver.solve_postflop(BOARD,OOP,IP,config=SMALL,
                            iterations=141,algorithm='cfrplus',traversal=traversal)
                    recursive.assert_not_called();public.assert_not_called()
                    with self.assertRaises(ReachedAdmittedTrainer):
                        solver.solve_postflop(BOARD,OOP,IP,config=SMALL,
                            iterations=140,algorithm='cfrplus',traversal=traversal)
                    self.assertEqual(recursive.call_count+public.call_count,1)
                    call=(recursive if traversal=='recursive' else public).call_args
                    self.assertEqual(call.args[3],140)

    def test_planned_diagnostics_and_early_stopping_scopes_remain_explicit(self):
        for options,message in (({'algorithm':'cfrplus','traversal':'planned'},'requires recursive'),
                                ({'diagnostics':'public-batched'},'only for turn and river'),
                                ({'traversal':'public-batched','target_exploitability':.01},'only for turn and river')):
            with self.subTest(options=options),patch.object(solver,'_enumerate_worlds',
                    side_effect=AssertionError('ranked before option rejection')) as worlds:
                with self.assertRaisesRegex(ValueError,message):
                    solver.solve_postflop(BOARD,OOP,IP,config=SMALL,iterations=10,**options)
                worlds.assert_not_called()

    def test_actual_legacy_source_preserves_defaults_and_turn_river_payloads(self):
        source=(ROOT/'pokerlab/postflop_solver.py').read_text(encoding='utf-8')
        current='''    if algorithm == "cfrplus":
        if traversal == "planned":'''
        prior='''    if algorithm == "cfrplus":
        if len(board) == 3:
            raise ValueError("CFR+ is currently enabled only for turn and river starts.")
        if traversal == "planned":'''
        self.assertEqual(source.count(current),1)
        frozen=source.replace(current,prior,1)
        self.assertEqual(hashlib.sha256(frozen.encode()).hexdigest(),
                         'a9d54a39a558ef1e72dea0b84f2b1df83bd4d36bf21820f2fb8f01cb1764f085')
        old=types.ModuleType('pokerlab._flop_cfrplus_actual_baseline');old.__package__='pokerlab'
        with patch.dict(sys.modules,{old.__name__:old}):
            exec(compile(frozen,'frozen-3963e3c-postflop','exec'),old.__dict__)
            cases=[(BOARD,[('5c','9h'),('9h','5c')],('vanilla','dcfr')),
                   ('2c3d4h5c',['9h','Tc'],('vanilla','dcfr','cfrplus')),
                   ('2c3d4h5c9h',None,('vanilla','dcfr','cfrplus'))]
            for board,runouts,algorithms in cases:
                for algorithm in algorithms:
                    for traversal in ('recursive','public-batched'):
                        options=dict(config=SMALL,runouts=runouts,iterations=10,
                                     algorithm=algorithm,traversal=traversal)
                        with self.subTest(board=board,algorithm=algorithm,traversal=traversal):
                            self.assertEqual(old.solve_postflop(board,OOP,IP,**options),
                                             solver.solve_postflop(board,OOP,IP,**options))
            options=dict(config=SMALL,runouts=cases[0][1],iterations=10)
            self.assertEqual(old.solve_postflop(BOARD,OOP,IP,**options),
                             solver.solve_postflop(BOARD,OOP,IP,**options))


if __name__=='__main__':
    unittest.main()
