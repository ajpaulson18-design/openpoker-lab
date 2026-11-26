"""Independent literal pure-proposal enumeration and full four-street means."""
from fractions import Fraction
from itertools import product
import struct
import unittest
from unittest.mock import patch

from scripts.matrix_free_certificate_budget import Budget
from tests.virtual_opponent_action_moments import Node,Q,SCHEMES,integrate,deterministic_transcript
from tests.virtual_opponent_action_worlds import MOMENT_LIMITS,plan,run_case


class TinyPublicGame:
    root='root'
    def __init__(self,alias=False):
        self.nodes={
            'root':Node('decision',('left','right'),0,('root',),(Q,0)),
            'left':Node('decision',('ll','lr'),1,('left',),(3*Q//4,Q//4)),
            'right':Node('decision',('rl','rr'),1,('left' if alias else 'right',),(Q//2,Q//2)),
            'll':Node('terminal',utility=Fraction(-2)), 'lr':Node('terminal',utility=Fraction(1)),
            'rl':Node('terminal',utility=Fraction(3)), 'rr':Node('terminal',utility=Fraction(-1))}
    def node(self,handle):return self.nodes[handle]


def enumerate_proposals(game,scheme,wrong_target_average=False,with_examples=False):
    """Enumerate pure opponent maps; evaluate actual partial transcripts.

    No analytic variance recurrence from the implementation is used here.
    Unvisited map choices still enter the pure-map probability and sum out.
    """
    decisions=[n for n in game.nodes.values() if n.kind=='decision']
    aggregates={n.key:{name:[Fraction(0)]*len(n.units) for name in ('r','r2','a','a2')} for n in decisions}
    roots=[];root_values=[];examples=[]
    for target in (0,1):
        opponent=[n for n in decisions if n.actor!=target];mean=second=Fraction(0);values=[];mass=Fraction(0)
        target_examples=[]
        for choices in product(*(range(len(n.children)) for n in opponent)):
            selected=dict(zip((n.key for n in opponent),choices));probability=Fraction(1)
            for n,choice in zip(opponent,choices):
                probability*=Fraction(1,len(n.children)) if scheme==SCHEMES[0] else Fraction(n.units[choice],Q)
            if not probability:continue
            mass+=probability;raw_r={};raw_a={}
            def visit(handle,reaches,prefix_q):
                n=game.nodes[handle]
                if n.kind=='terminal':return n.utility if target==0 else -n.utility
                p=tuple(Fraction(u,Q) for u in n.units)
                if n.actor==target:
                    child_values=[]
                    for action,child in enumerate(n.children):
                        next_reach=list(reaches);next_reach[n.actor]*=p[action]
                        child_values.append(visit(child,tuple(next_reach),prefix_q))
                    mixed=sum((p[a]*v for a,v in enumerate(child_values)),Fraction(0))
                    raw_r[n.key]=tuple(reaches[1-n.actor]*(v-mixed)/prefix_q for v in child_values)
                    if scheme==SCHEMES[0] or wrong_target_average:
                        raw_a[n.key]=tuple(reaches[n.actor]*v/prefix_q for v in p)
                    return mixed
                if scheme==SCHEMES[1] and not wrong_target_average:raw_a[n.key]=p
                action=selected[n.key];q=Fraction(1,len(n.children)) if scheme==SCHEMES[0] else p[action]
                next_reach=list(reaches);next_reach[n.actor]*=p[action]
                return p[action]/q*visit(n.children[action],tuple(next_reach),prefix_q*q)
            value=visit(game.root,(Fraction(1),Fraction(1)),Fraction(1));values.append(value)
            target_examples.append((value,raw_r,raw_a))
            mean+=probability*value;second+=probability*value*value
            for field,rows in (('r',raw_r),('a',raw_a)):
                for key,increments in rows.items():
                    for a,increment in enumerate(increments):
                        aggregates[key][field][a]+=probability*increment
                        aggregates[key][field+'2'][a]+=probability*increment*increment
        if mass!=1:raise ArithmeticError('literal proposal probability did not sum to one')
        roots.append((mean,second));root_values.append(tuple(values));examples.append(target_examples)
    result=(aggregates,tuple(roots),tuple(root_values))
    return (*result,examples) if with_examples else result


class OpponentActionMomentTests(unittest.TestCase):
    def meter(self):return Budget({'work':5_000_000,'entries':500000,'created_bits':100_000_000,'integer_bits':4096})

    def test_every_tiny_first_second_coordinate_matches_literal_pure_maps(self):
        game=TinyPublicGame()
        for scheme in SCHEMES:
            literal,roots,_=enumerate_proposals(game,scheme);actual=integrate(game,scheme,self.meter())
            self.assertEqual(actual['roots'],roots)
            for key,row in actual['rows'].items():
                self.assertEqual((row.regret_mean,row.regret_second,row.average_mean,row.average_second),
                                 tuple(tuple(literal[key][name]) for name in ('r','r2','a','a2')))

    def test_policy_target_average_misses_zero_opponent_prefix_and_roles_repair_it(self):
        game=TinyPublicGame();wrong,_,_=enumerate_proposals(game,SCHEMES[1],wrong_target_average=True)
        correct=integrate(game,SCHEMES[1],self.meter())
        key=('right',)
        self.assertEqual(wrong[key]['a'],[0,0])
        self.assertEqual(correct['rows'][key].average_mean,(Fraction(1,2),Fraction(1,2)))
        self.assertEqual(correct['rows'][key].regret_mean,(0,0))

    def test_expected_zero_sum_roots_do_not_imply_opposite_sampled_roots(self):
        game=TinyPublicGame();_rows,roots,values=enumerate_proposals(game,SCHEMES[1])
        self.assertEqual(roots[0][0],-roots[1][0]);self.assertNotEqual(roots[0][1],roots[1][1])
        self.assertTrue(any(a+b!=0 for a in values[0] for b in values[1]))

    def test_rejects_aliases_and_unsupported_schemes(self):
        with self.assertRaises(ValueError):integrate(TinyPublicGame(alias=True),SCHEMES[0],self.meter())
        with patch.object(TinyPublicGame,'node',side_effect=AssertionError('source entered')):
            with self.assertRaises(ValueError):integrate(TinyPublicGame(),'wrong',self.meter())

    def test_transcript_operator_matches_independent_first_and_last_pure_maps(self):
        game=TinyPublicGame()
        for scheme in SCHEMES:
            _rows,_roots,_values,examples=enumerate_proposals(game,scheme,with_examples=True)
            for target in (0,1):
                for choice,index in (('first',0),('last',-1)):
                    result=deterministic_transcript(game,target,scheme,choice,self.meter())
                    root,r,a=examples[target][index]
                    self.assertEqual((result['root'],dict(result['regrets']),dict(result['averages'])),(root,r,a))

    def test_compact_role_carrier_and_nonmaterialized_branched_probability(self):
        class WideProposalGame:
            root=('own',())
            def node(self,handle):
                kind,path=handle[:2]
                if kind=='terminal':return Node('terminal',utility=Fraction(1,2) if not any(path) and handle[2]==0 else Fraction(0))
                if kind=='opponent':
                    return Node('decision',(('terminal',path,0),('terminal',path,1)),1,('opponent',path),(1,Q-1))
                children=tuple(('opponent' if len(path)==6 else 'own',(*path,a)) for a in (0,1))
                return Node('decision',children,0,('own',path),(1,Q-1))
        result=deterministic_transcript(WideProposalGame(),0,SCHEMES[1],'first',self.meter())
        self.assertEqual(result['root'],Fraction(1,1<<365))
        self.assertEqual(len(result['choices']),128)
        self.assertEqual(sum(q.denominator.bit_length()-1 for _key,_a,q in result['choices']),6656)
        self.assertFalse(result['probability_materialized'])
        self.assertTrue(all((1<<365)%r.denominator==0 for row in result['regrets'].values() for r in row))
        self.assertTrue(all(Q%a.denominator==0 for row in result['averages'].values() for a in row))


class FourStreetMomentTests(unittest.TestCase):
    def test_three_physical_signs_all_means_second_moments_and_visible_inputs(self):
        self.assertLessEqual(plan(3)['complete']['work'],500_000_000)
        results=[]
        for index in range(3):
            wire,report,visibility,side=run_case(index);results.append((report,visibility))
            self.assertEqual(wire[:8],b'OPLOAM01');self.assertEqual(len(wire),1_767_712)
            self.assertEqual(wire[-48:-40],b'OPLOMF01')
            self.assertEqual((report['native_calls'],report['rng_calls'],report['attempted_training'],report['quality_gate']),
                             (0,0,False,None))
            self.assertEqual(len(report['tables']),4)
            self.assertEqual(side[:8],b'OPLOAW01');self.assertLessEqual(len(side),1_048_576)
            self.assertEqual(len(report['witnesses']),4)
            for witness in report['witnesses']:
                self.assertFalse(witness['probability_materialized'])
                if witness['scheme']==SCHEMES[1]:
                    self.assertTrue(witness['role_compact_denominators_verified'])
                    self.assertLessEqual(witness['role_observed_regret_bits'],370)
                    self.assertLessEqual(witness['role_observed_average_bits'],53)
            for table in report['tables']:
                if table['scheme']=='uniform-target-average':
                    self.assertEqual(table['expected_traversal_counts']['visits'],{'numerator':1636555,'denominator':31104})
                    self.assertEqual(table['expected_unique_read_rows'],{'numerator':21883070621,'denominator':859963392})
            for key in MOMENT_LIMITS:self.assertLessEqual(report['moment_resource_accounting'][key],MOMENT_LIMITS[key])
            self.assertGreater(report['zero_own_nonzero_regret_rows'],0)
            self.assertGreater(report['zero_opponent_nonzero_average_rows'],0)
            self.assertEqual(struct.unpack_from('<Q',wire,8)[0],1)
        self.assertEqual(sorted(r['showdown_sign'] for r,_v in results),[-1,0,1])
        # Same actor's physical hand and flop; the hidden opponent/tail change.
        for first,other,actor in ((0,1,0),(0,2,1)):
            a=results[first][1];b=results[other][1]
            common={key for key in a.keys()&b.keys() if key[1]==actor}
            self.assertGreater(len(common),6)
            for key in common:self.assertEqual(a[key],b[key])

    def test_reduced_limits_reject_before_reference_preparation(self):
        source='tests.virtual_opponent_action_worlds.Request'
        with patch(source,side_effect=AssertionError('source entered')):
            for key in ('work','entries','created_bits','integer_bits'):
                with self.assertRaises(ValueError):run_case(0,limits={key:plan(1)['complete'][key]-1})
            with self.assertRaises(ValueError):run_case(True)


if __name__=='__main__':unittest.main()
