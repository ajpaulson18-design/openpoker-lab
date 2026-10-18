"""Literal turn/future-information anchors and adversarial saved-proof checks."""
import copy
import hashlib
import json
import unittest
import uuid
from fractions import Fraction as F
from pathlib import Path
from unittest.mock import patch
from scripts import turn_river_validation as rules
from scripts import verify_turn_sequence as verify
from scripts.turn_sequence_fixture import FIXTURE
ROOT = Path(__file__).resolve().parents[1]

class TurnLawTests(unittest.TestCase):
    def setUp(self):
        self.board=rules.cards(FIXTURE['board'])
        self.config=rules._config(FIXTURE['config'],'config')
        self.worlds,self.selected=rules._worlds(self.board,tuple(rules.expand_range(FIXTURE[p],self.board) for p in ('oop','ip')),FIXTURE['runouts'])
        self.root=rules._public_tree(self.board,self.config,self.config,self.selected,self.worlds)

    def test_frozen_pre_candidate_model_and_literal_uniform_responses(self):
        model=verify.model(FIXTURE)
        raw=json.dumps([model],sort_keys=True,indent=2,allow_nan=False).encode()+b'\n'
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'bf645923e5cbdd4bbffd4492f2ffe730c6780bb0c8ee1a430a7b2725c93c7d69')
        self.assertEqual(model['uniform_metrics'],dict(value='2175/64',lower='25/16',upper='75',nash_conv='1175/16'))
        self.assertEqual(model['check_call_ip_reference'],dict(legal_oop_br='175/2',illegal_future_peek='100',illicit_gain='25/2'))

    def test_joint_world_law_and_independent_best_five(self):
        self.assertEqual(self.selected,('8d','Kd'))
        law={(''.join(w['hands'][0]),w['river']):(w['weight'],w['sign']) for w in self.worlds}
        self.assertEqual(law,{('AhAs','8d'):(F(1,4),1),('AhAs','Kd'):(F(1,4),1),('6hTh','8d'):(F(1,4),1),('6hTh','Kd'):(F(1,4),-1)})
        draw=next(w for w in self.worlds if ''.join(w['hands'][0])=='6hTh' and w['river']=='8d')
        self.assertEqual(verify.rank(draw['board']+draw['hands'][0]),(4,11))
        for river,mean in (('8d',F(1)),('Kd',F(0))):
            group=[w for w in self.worlds if w['river']==river]
            self.assertEqual(sum(w['weight']*w['sign'] for w in group)/sum(w['weight'] for w in group),mean)

    def test_future_peeking_changes_response_and_is_illegal(self):
        policies={}
        rows=[]
        for node in rules._collect_nodes(self.root):
            for world in self.worlds:
                if world['board'][:len(node.board)]!=node.board: continue
                key=(node.player,''.join(world['hands'][node.player]),node.history)
                if key in policies: continue
                probabilities=tuple(F(a.name in ('check','call')) if node.player==1 else F(1,2) for a in node.actions)
                policies[key]=probabilities
                rows.append(dict(player='oop' if node.player==0 else 'ip',hand=key[1],history=list(node.history),street='turn' if len(node.board)==4 else 'river',board=list(node.board),actions=[a|dict(probability=float(p)) for a,p in zip(rules._row_actions(node),probabilities)]))
        self.assertEqual(verify.response(self.root,self.worlds,policies,100,0),F(175,2))
        self.assertEqual(verify.response(self.root,self.worlds,policies,100,0,peek=True),100)
        result=dict(board=list(self.board),runouts=list(self.selected),runout_mode='conditioned-subset',reachable_runouts=list(self.selected),strategy=rows,info_sets=42,worlds=4,deals=2)
        oracle=rules.replay_policy(result,FIXTURE['oop'],FIXTURE['ip'],board=FIXTURE['board'],config=FIXTURE['config'],runouts=FIXTURE['runouts'])
        self.assertEqual(oracle['oop_best_response_value'],87.5)
        self.assertEqual(len([r for r in rows if r['street']=='turn']),6)
        self.assertEqual(len([r for r in rows if r['street']=='river']),36)
        leaked=copy.deepcopy(result)
        leaked['strategy'].append(copy.deepcopy(next(r for r in rows if r['street']=='turn' and r['hand']=='6hTh')))
        with self.assertRaisesRegex(ValueError,'Duplicate strategy row'):
            rules.replay_policy(leaked,FIXTURE['oop'],FIXTURE['ip'],board=FIXTURE['board'],config=FIXTURE['config'],runouts=FIXTURE['runouts'])

    def child(self,node,name):
        return node.children[next(i for i,a in enumerate(node.actions) if a.name==name)]

    def test_turn_wagers_carry_into_river_and_unmatched_bets_refund(self):
        raised=self.child(self.root,'bet')
        turnfold=self.child(raised,'fold')
        self.assertEqual(min(turnfold.contributions),0)
        chance=self.child(raised,'call')
        river=chance.branches['Kd']
        self.assertEqual([(a.name,a.amount,a.raise_to) for a in river.actions],[('check',0.0,0.0),('all_in',50.0,100.0)])
        bet=self.child(river,'all_in')
        terminal=self.child(bet,'call')
        fold=self.child(bet,'fold')
        self.assertEqual(terminal.contributions,(100.0,100.0))
        self.assertEqual(min(fold.contributions),50)
        for world in self.worlds:
            if world['river']=='Kd':
                self.assertEqual(verify.terminal(terminal,world,100),150*world['sign'])
                self.assertEqual(verify.terminal(fold,world,100),100)
                self.assertEqual(verify.terminal(turnfold,world,100),50)
        checkchance=self.child(self.child(self.root,'check'),'check')
        river=checkchance.branches['8d']
        settled=self.child(self.child(river,'bet'),'call')
        self.assertEqual(settled.contributions,(50.0,50.0))

class WitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Establish a valid complete proof before every negative mutation family.
        cls.report=verify.verify_saved_artifact()

    def reject(self,edit):
        report=copy.deepcopy(self.report)
        edit(report)
        target=ROOT/('turn-sequence-test-'+uuid.uuid4().hex+'.json')
        try:
            target.write_text(json.dumps(report),encoding='utf-8')
            with self.assertRaises((ValueError,KeyError,TypeError,IndexError)):
                verify.verify_saved_artifact(target)
        finally: target.unlink(missing_ok=True)

    def test_untouched_shared_turn_rows(self):
        row=self.report['results'][0]
        self.assertEqual(row['exact']['metrics']['nash_conv'],'0')
        self.assertEqual(len(row['rational_strategy']),42)
        turns=[r for r in row['rational_strategy'] if r['street']=='turn']
        self.assertEqual(len(turns),6)
        self.assertTrue(all(len(r['board'])==4 and not any(t.startswith('river@') for t in r['history']) for r in turns))

    def test_each_payoff_and_both_flow_matrices(self):
        for name,offset in [('payoff_matrix',0),('flow_matrix',0),('flow_matrix',29)]:
            with self.subTest(name=name,offset=offset):
                self.reject(lambda r:r['results'][0][name][offset].__setitem__(0,'999'))

    def test_both_realizations_duals_and_slacks(self):
        for side in ('lower_lp','upper_lp'):
            for field in ('own_realization','dual_flow_values','inequality_slacks'):
                with self.subTest(side=side,field=field):
                    self.reject(lambda r:r['results'][0][side][field]['fractions'].__setitem__(0,'-999'))

    def test_chance_rescaling_is_rejected_even_with_scaled_objectives(self):
        def edit(r):
            row=r['results'][0]
            row['payoff_matrix']=[[str(F(v)/2) for v in line] for line in row['payoff_matrix']]
            for side in ('lower_lp','upper_lp'):
                lp=row[side]
                for name in ('objective','objective_bound_fraction'): lp[name]=str(F(lp[name])/2)
                for name in ('dual_flow_values','inequality_slacks'): lp[name]['fractions']=[str(F(v)/2) for v in lp[name]['fractions']]
            row['exact']['metrics']={k:str(F(v)/2) for k,v in row['exact']['metrics'].items()}
            for name in ('lower_value_bound','upper_value_bound'): row['exact'][name]=str(F(row['exact'][name])/2)
        self.reject(edit)

    def test_future_split_and_wrong_public_metadata(self):
        def duplicate(r):
            rows=r['results'][0]['rational_strategy']
            leaked=copy.deepcopy(next(x for x in rows if x['street']=='turn'))
            for i,a in enumerate(leaked['actions']): a.update(probability_fraction=str(F(i==0)),probability=float(i==0))
            rows.append(leaked)
        self.reject(duplicate)
        self.reject(lambda r:r['results'][0]['rational_strategy'][0].update(board=['2c','7d','9h','Js','Kd']))
        self.reject(lambda r:r['results'][0]['fixture'].update(runouts=['8d']))

    def test_parent_and_uniform_reference_tampering(self):
        self.reject(lambda r:r['results'][0]['sequences'][0][1].update(parent='missing'))
        self.reject(lambda r:r['results'][0]['uniform_crosscheck'].update(value_fraction='999'))

    def test_canonical_fractions_and_resource_types(self):
        self.reject(lambda r:r['results'][0]['lower_lp'].update(objective='0/2'))
        for value in (True,-1,10000001):
            self.reject(lambda r:r['results'][0]['upper_lp'].update(logical_cell_updates=value))

    def test_missing_duplicate_results_and_source_pins(self):
        self.reject(lambda r:r.update(results=[]))
        self.reject(lambda r:r['results'].append(copy.deepcopy(r['results'][0])))
        self.reject(lambda r:r['source_sha256'].pop('scripts/turn_sequence_fixture.py'))

    def test_historical_head_does_not_require_git_object(self):
        report=copy.deepcopy(self.report)
        report['baseline_git_commit']='a'*40
        target=ROOT/('turn-sequence-test-'+uuid.uuid4().hex+'.json')
        try:
            target.write_text(json.dumps(report),encoding='utf-8')
            verify.verify_saved_artifact(target)
        finally: target.unlink(missing_ok=True)

    def test_head_and_source_drift_during_verification(self):
        with patch.object(verify.subprocess,'check_output',side_effect=['a'*40+'\n','b'*40+'\n']):
            with self.assertRaisesRegex(ValueError,'HEAD changed'): verify.verify_saved_artifact()
        initial=verify._inputs()
        with patch.object(verify,'_inputs',side_effect=[initial,{}]):
            with self.assertRaisesRegex(ValueError,'Sources changed'): verify.verify_saved_artifact()

if __name__=='__main__': unittest.main()
