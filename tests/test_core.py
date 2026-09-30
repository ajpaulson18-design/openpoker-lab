import itertools
import json
import random
import tempfile
import threading
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pokerlab.cards import cards, rank_hand, expand_range, DECK
from pokerlab.equity import simulate
from pokerlab.models import Store
from pokerlab.analysis import analyze
from pokerlab.contracts import (ActionFrequency, ActionValue, BetaPrior,
                                ExplanationPayload, ExploitativeAdjustment,
                                MathematicalFact, OpponentAssumption,
                                OpponentModelProvider, OpponentTendencyEstimate,
                                StrategyAnalysisResult, TendencyContext,
                                Uncertainty, stable_analysis_id)
from pokerlab.game import Game, settle
from pokerlab.solver import solve
from pokerlab.server import make_server


class CardsTests(unittest.TestCase):
    def test_categories_and_order(self):
        hands = ['As Jd 9c 6h 3s', 'As Ad 9c 6h 3s', 'As Ad 9c 9h 3s',
                 'As Ad Ac 6h 3s', 'As 2d 3c 4h 5s', 'As Js 9s 6s 3s',
                 'As Ad Ac 6h 6s', 'As Ad Ac Ah 3s', 'As Ks Qs Js Ts']
        ranks = [rank_hand(cards(h)) for h in hands]
        self.assertEqual([r[0] for r in ranks], list(range(9)))
        self.assertEqual(sorted(ranks), ranks)
        self.assertLess(rank_hand(cards('As 2d 3c 4h 5s')), rank_hand(cards('2s 3d 4c 5h 6s')))

    def test_seven_vs_best_five(self):
        rng = random.Random(8)
        for _ in range(1200):
            hand = rng.sample(DECK, 7)
            self.assertEqual(rank_hand(hand), max(rank_hand(h) for h in itertools.combinations(hand, 5)))

    def test_two_trips_and_three_pairs(self):
        self.assertEqual(rank_hand(cards('As Ad Ac Ks Kd Kc 2h')), (6, 14, 13))
        self.assertEqual(rank_hand(cards('As Ad Ks Kd Qs Qd 2h')), (2, 14, 13, 12))

    def test_range_counts(self):
        for expression, n in [('AA',6), ('AKs',4), ('AKo',12), ('AK',16), ('TT+',30), ('AJs+',12), ('random',1326)]:
            self.assertEqual(len(expand_range(expression)),n)
        self.assertEqual(len(expand_range('AA', cards('As'))),3)
        self.assertEqual(len(expand_range('AA,AA:0.5')),6)
        self.assertEqual(set(expand_range('AA:0.5').values()),{.5})
        self.assertEqual(len(expand_range('AK,AKs:0')),12)

    def test_invalid(self):
        for value in ['AsAs','Xx','ABC']:
            with self.assertRaises(ValueError): cards(value)
        for expression in ['AK:NaN','AK:2','KA','AAs','garbage']:
            with self.assertRaises(ValueError): expand_range(expression)


class EquityTests(unittest.TestCase):
    def test_royal_board_split(self):
        q=simulate('2h3h','AsKsQsJsTs',['random'],100)
        self.assertTrue(q['exact']); self.assertEqual(q['equity'],.5); self.assertEqual(q['tie'],1)
        q=simulate('2h3h','AsKsQsJsTs',['random','random'],100)
        self.assertAlmostEqual(q['equity'],1/3)

    def test_weighted_river(self):
        q=simulate('AsAh','2c3d7h8s9c',['KsKh:0.25,9s9h:0.75'],100)
        self.assertEqual(q['equity'],.25)

    def test_seed_and_aces(self):
        a=simulate('AsAh',trials=3000)
        self.assertEqual(a,simulate('AsAh',trials=3000))
        self.assertTrue(.82<a['equity']<.89)

    def test_collisions(self):
        with self.assertRaises(ValueError): simulate('AsAh','As3h4d',trials=100)
        with self.assertRaises(ValueError): simulate('AsAh',ranges=['KsKh','KsKh'],trials=100)

    def test_call_ev(self):
        r=analyze({'hero':'AsAh','board':'2c3d7h8s9c','range':'KsKh','pot':100,'to_call':50,'trials':100})
        self.assertEqual(r['actions']['call'],100)


class ModelTests(unittest.TestCase):
    def test_update_filter_and_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(Path(d)/'db.sqlite3'); o=s.add_opponent('Test','balanced'); identity=o['id']
            old=o['metrics']['fold_to_bet']['mean']
            s.observe(identity,'fold_to_bet',True,'river',id='hand1')
            self.assertTrue(s.observe(identity,'fold_to_bet',True,'river',id='hand1')['duplicate'])
            self.assertGreater(s.get_opponent(identity,'river')['metrics']['fold_to_bet']['mean'],old)
            self.assertEqual(s.get_opponent(identity,'turn')['metrics']['fold_to_bet']['mean'],old)
            self.assertEqual(len(s.export()['observations']),1)
            with self.assertRaises(ValueError):s.observe(identity,'fold_to_bet',False,'river',id='hand1')

    def test_immutable_snapshot_matches_street_filtered_model(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'db.sqlite3'); opponent=store.add_opponent('Test','tight')
            store.observe(opponent['id'],'fold_to_bet',True,'river',id='river-1')
            store.observe(opponent['id'],'fold_to_bet',False,'turn',id='turn-1')
            snapshot=store.opponent_snapshot(opponent['id'],'river')
            estimate=snapshot.tendency('fold_to_bet')
            legacy=store.get_opponent(opponent['id'],'river')['metrics']['fold_to_bet']
            self.assertIsInstance(store,OpponentModelProvider)
            self.assertEqual(estimate.context.street,'river')
            self.assertEqual((estimate.successes,estimate.opportunities),(1,1))
            self.assertEqual(estimate.posterior_mean,legacy['mean'])
            self.assertEqual(estimate.prior.source,'profile:tight')
            self.assertNotIn('name',snapshot.to_dict())
            with self.assertRaises(FrozenInstanceError):estimate.sample_size=2


class ContractTests(unittest.TestCase):
    def fixtures(self):
        context=TendencyContext('river','button','facing_bet',(('size','half-pot'),))
        uncertainty=Uncertainty(.30,.55,.95,'beta interval','moderate')
        tendency=OpponentTendencyEstimate('fold_to_bet',context,12,30,
                                          BetaPrior(.45,10,'profile:balanced'),
                                          .4125,uncertainty,30)
        assumption=OpponentAssumption('fold_to_bet',context,.4125,30,uncertainty)
        return context,uncertainty,tendency,assumption

    def test_strategy_contract_keeps_baseline_and_exploit_separate(self):
        _,uncertainty,_,assumption=self.fixtures()
        identity=stable_analysis_id({'hand':'AsAh','board':'2c3d7h8s9c'})
        result=StrategyAnalysisResult(
            identity,('check','bet'),
            (ActionFrequency('check',.6),ActionFrequency('bet',.4)),
            (ActionFrequency('check',.3),ActionFrequency('bet',.7)),
            (ActionValue('check',48),ActionValue('bet',55)),
            (ActionValue('check',0),ActionValue('bet',7)),
            (assumption,),'moderate',uncertainty,'example-solver-v1','beta-opportunity-v1',
            ('Heads-up only.',),())
        payload=ExplanationPayload(
            identity,'bet',result.baseline_strategy,
            ExploitativeAdjustment('bet',.4,.7),
            'The modeled fold rate raises bet EV.',assumption,30,uncertainty,7,
            (MathematicalFact('Bet EV',55,'chips'),),('Range uncertainty is additional.',))
        encoded=json.dumps({'analysis':result.to_dict(),'explanation':payload.to_dict()})
        decoded=json.loads(encoded)
        self.assertNotEqual(decoded['analysis']['baseline_strategy'],
                            decoded['analysis']['exploitative_strategy'])
        self.assertEqual(decoded['analysis']['analysis_id'],decoded['explanation']['analysis_id'])
        self.assertEqual(identity,stable_analysis_id({'board':'2c3d7h8s9c','hand':'AsAh'}))

    def test_contracts_reject_ambiguous_or_invalid_data(self):
        context,uncertainty,_,_=self.fixtures()
        with self.assertRaises(ValueError):
            OpponentTendencyEstimate('fold_to_bet',context,2,1,
                                     BetaPrior(.45,10,'profile:balanced'),.5,uncertainty,1)
        with self.assertRaises(ValueError):
            StrategyAnalysisResult(
                'id',('check','bet'),
                (ActionFrequency('check',1),ActionFrequency('bet',0)),
                (ActionFrequency('check',.2),ActionFrequency('bet',.2)),
                (ActionValue('check',1),ActionValue('bet',2)),
                (ActionValue('check',0),ActionValue('bet',1)),(),
                'low',None,'solver-v1','model-v1')


class GameTests(unittest.TestCase):
    def test_custom_names_are_used_in_state_and_history(self):
        g=Game([100,100,100],names=['Hero','Mike','Sarah'],seed=4)
        self.assertEqual(g.state()['names'],['Hero','Mike','Sarah'])
        self.assertEqual(g.state()['actor_name'],'Hero')
        g.act('call')
        self.assertEqual(g.state()['log'][0]['name'],'Hero')
        with self.assertRaises(ValueError):Game([100,100],names=['Mike','mike'])
        with self.assertRaises(ValueError):Game([100,100],names=['Only one'])

    def test_positions_and_checkdown(self):
        for n in (2,3,6):
            g=Game([100]*n,seed=4)
            self.assertEqual(g.actor,0 if n in (2,3) else 3)
            while not g.done:
                g.act('call' if g.legal()['call'] else 'check')
            self.assertEqual(sum(g.stacks),100*n)
            self.assertEqual(len(g.board),5)

    def test_fold(self):
        g=Game(seed=4);g.act('fold')
        self.assertTrue(g.done);self.assertEqual(g.stacks,[199,201])

    def test_sidepots(self):
        hands=[cards('AsAh'),cards('KsKh'),cards('QsQh')]
        payouts,pots=settle([50,100,200],[False]*3,hands,cards('2c3d7h8sJc'))
        self.assertEqual(payouts,[150,100,100]);self.assertEqual(sum(payouts),350)

    def test_odd_chip(self):
        payouts,_=settle([5,5,5],[False,False,True],
                         [cards('2h3h'),cards('2d3d'),cards('2c3c')],cards('AsKsQsJsTs'),button=0)
        self.assertEqual(payouts,[7,8,0])

    def test_allin_runout(self):
        g=Game([50,100,200],seed=2)
        while not g.done:
            legal=g.legal();g.act('raise',legal['raise_max']) if legal['raise'] else g.act('call' if legal['call'] else 'check')
        self.assertEqual(sum(g.stacks),350);self.assertEqual(len(g.board),5)

    def test_short_raise_no_reopen(self):
        g=Game([100,25,100],seed=3)
        g.act('raise',20) # seat 0 raises by 18
        g.act('raise',25) # seat 1 short all-in
        g.act('call')
        self.assertEqual(g.actor,0);self.assertFalse(g.legal()['raise'])
        with self.assertRaises(ValueError):g.act('raise',50)

    def test_random_legal_hands_conserve_chips(self):
        rng=random.Random(10)
        for trial in range(300):
            stacks=[rng.randint(1,150) for _ in range(rng.randint(2,6))]
            g=Game(stacks,seed=trial)
            actions=0
            while not g.done:
                legal=g.legal();choices=['check'] if legal['check'] else ['call','fold']
                if legal['raise']:choices+=['raise']
                action=rng.choice(choices)
                g.act(action,rng.randint(legal['raise_min'],legal['raise_max']) if action=='raise' else None)
                self.assertTrue(all(s>=0 for s in g.stacks));actions+=1;self.assertLess(actions,200)
            self.assertEqual(sum(g.stacks),sum(stacks))


class SolverTests(unittest.TestCase):
    def test_known_winner(self):
        r=solve('2c3d7h8sJc','AsAh','KsKh',iterations=1000)
        self.assertLess(r['nash_conv'],.3)
        self.assertAlmostEqual(r['value_oop'],50,delta=.2)

    def test_tied_board(self):
        r=solve('AsKsQsJsTs','2h3h','2d3d',iterations=1000)
        self.assertAlmostEqual(r['value_oop'],0,delta=.3)
        self.assertLess(r['nash_conv'],.3)

    def test_mixed_game_convergence(self):
        r=solve('Js8d4c2h2s','AsAh,KsKh,QsQh,AsKs','AcAd,KcKd,QcQd,AcKc',iterations=3000)
        self.assertLess(r['nash_conv'],2)
        for player in ('oop','ip'):
            for row in r[player]:
                self.assertTrue(all(0<=v<=1 for k,v in row.items() if k!='hand'))

    def test_node_lock(self):
        r=solve('2c3d7h8sJc','QsQh','KsKh',iterations=1000,lock={'ip_call':0,'ip_bet':0})
        self.assertGreater(r['oop'][0]['bet'],.99)
        self.assertEqual(r['ip'][0]['call'],0)
        self.assertGreater(r['nash_conv'],1) # exploitable locked opponent, not a fake certificate


class ServerTests(unittest.TestCase):
    def test_api_validation_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            server=make_server(0,Path(d)/'db.sqlite3')
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            root=f'http://127.0.0.1:{server.server_port}'
            try:
                self.assertTrue(json.load(urlopen(root+'/api/health'))['ok'])
                request=Request(root+'/api/opponents',json.dumps({'name':'Local player'}).encode(),{'Content-Type':'application/json'})
                self.assertEqual(json.load(urlopen(request))['name'],'Local player')
                self.assertEqual(len(json.load(urlopen(root+'/api/opponents'))['opponents']),1)
                request=Request(root+'/api/equity',b'{}',{'Content-Type':'application/json','Origin':'https://example.com'})
                with self.assertRaises(HTTPError) as context:urlopen(request)
                self.assertEqual(context.exception.code,403)
                request=Request(root+'/api/equity',b'{"hero":"AsAs"}',{'Content-Type':'application/json'})
                with self.assertRaises(HTTPError) as context:urlopen(request)
                self.assertEqual(context.exception.code,400)
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
