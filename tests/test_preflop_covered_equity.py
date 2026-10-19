"""Coverage/conditioning tests use explicitly synthetic physical-sized counts."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import unittest
from unittest.mock import patch
from pokerlab import preflop_full_board_equity as ordinary
from pokerlab import preflop_covered_equity as covered
from pokerlab import preflop_checkdown_solver as solver
from pokerlab.preflop_checkdown_budget import admit_covered_prepared, options
from scripts.preflop_checkdown_validation import replay

BOARDS=1712304
# Synthetic W/T/L values model three distinct relative-suit patterns, and are
# not evidence about physical AA/KK showdown frequencies.
SYNTHETIC=((1400000,10000,302304),(1410000,11000,291304),(1420000,12000,280304))

def source_table(sb='AdAs',bb='KdKs,KcKd,KcKh',counts=SYNTHETIC):
    plan=ordinary.plan_preflop_equities(sb,bb)
    worlds=[]
    for (i,j,prior),(w,t,l) in zip(plan.pairs,counts):
        for sign,n in zip((-1,0,1),(l,t,w)):
            if n:worlds.append((i,j,float(prior*Fraction(n,BOARDS)),sign))
    table=ordinary.FullBoardEquities(plan.hands,plan.pairs,tuple(counts),tuple(worlds),plan._budget_items)
    table.validate()
    return table

def trusted_counts(table):
    return [{'sb_hand':''.join(table.hands[0][i]),'bb_hand':''.join(table.hands[1][j]),
             'wins':w,'ties':t,'losses':l,'boards':BOARDS}
            for (i,j,_),(w,t,l) in zip(table.pairs,table.counts)]

CONFIG={'small_blind':.5,'big_blind':1,'starting_stack':[3,3],
        'raise_sizes':[.5,1],'max_raises':1,'include_all_in':True}

class CoveredPreflopTests(unittest.TestCase):
    def test_thirty_six_pairs_copy_the_correct_joint_suit_orbit_without_ranking(self):
        source=source_table()
        original=deepcopy(source)
        fail=AssertionError('pooling ranked or enumerated')
        with (patch.object(ordinary,'rank_hand',side_effect=fail),
              patch.object(ordinary,'_board_combinations',side_effect=fail)):
            table=covered.pool_preflop_equities_by_suit([source],'AA','KK')
        self.assertEqual(source,original)
        self.assertEqual(len(table.pairs),36)
        # Each AA hand has exactly one KK pair with the same suits, one with
        # disjoint suits, and four with a one-suit intersection.
        by_overlap={}
        for (i,j,p),counts in zip(source.pairs,source.counts):
            overlap=len({c[1] for c in source.hands[0][i]} & {c[1] for c in source.hands[1][j]})
            by_overlap[overlap]=counts
        tally={0:0,1:0,2:0}
        for (i,j,p),counts in zip(table.pairs,table.counts):
            self.assertEqual(p,Fraction(1,36))
            overlap=len({c[1] for c in table.hands[0][i]} & {c[1] for c in table.hands[1][j]})
            self.assertEqual(counts,by_overlap[overlap]);tally[overlap]+=1
        self.assertEqual(tally,{0:6,1:24,2:6})
        self.assertEqual(table.budget['rank_calls_upper_bound'],0)
        proof=table.provenance();proof[0]['suit_permutation']['c']='s'
        table.validate()  # returned metadata is detached
        self.assertEqual(len(table.provenance()),36)

    def test_weighted_blockers_global_conditioning_and_missing_orbit_rejection(self):
        from scripts.benchmark_preflop_exact_anchor import _load_inputs,SPEC_PATH
        import json
        item=_load_inputs(json.loads(SPEC_PATH.read_text()))
        table=covered.pool_preflop_equities_by_suit([item['table']],
                    'AdAs:1,QdQs:.5','AsKh:.25,KdKs:1')
        self.assertEqual(tuple(p for _,_,p in table.pairs),(Fraction(8,13),Fraction(1,13),Fraction(4,13)))
        with self.assertRaisesRegex(ValueError,'not covered'):
            covered.pool_preflop_equities_by_suit([source_table()],'AA','QQ')

    def test_caps_precede_orbit_work_and_conflicting_sources_reject(self):
        with patch.object(covered,'_canonical_pair_key',side_effect=AssertionError('late admission')):
            with self.assertRaisesRegex(ValueError,'pair limit'):
                covered.pool_preflop_equities_by_suit([source_table()],'AA,KK,QQ','JJ,TT,99')
        one=source_table('AdAs','KdKs',(SYNTHETIC[0],))
        other=source_table('AcAh','KcKh',(SYNTHETIC[1],))
        with self.assertRaisesRegex(ValueError,'conflict'):
            covered.pool_preflop_equities_by_suit([one,other],'AdAs','KdKs')
        with self.assertRaisesRegex(ValueError,'32'):
            covered.pool_preflop_equities_by_suit([one]*33,'AdAs','KdKs')

    def test_forged_shapes_and_provenance_are_rejected(self):
        table=covered.pool_preflop_equities_by_suit([source_table()],'AA','KK')
        first=table.coverage[0]
        for altered in (replace(table,source_count=True),replace(table,pairs=table.pairs[::-1]),
                        replace(table,counts=((True,10000,BOARDS-10001),)+table.counts[1:]),
                        replace(table,coverage=((first[0],first[1],first[2],('c',)*4),)+table.coverage[1:]),
                        replace(table,worlds=((True,0,.1,1),)+table.worlds[1:])):
            with self.subTest(altered=type(altered)), self.assertRaises(ValueError):altered.validate()

    def test_shared_solver_and_independent_replay_cover_thirty_six_private_pairs(self):
        table=covered.pool_preflop_equities_by_suit([source_table()],'AA','KK')
        result=solver.solve_covered_preflop_checkdown(table,config=CONFIG,iterations=1000)
        checks=replay(result,'AA','KK',CONFIG,trusted_counts(table),covered_counts=True)
        self.assertEqual(result['compatible_pairs'],36)
        self.assertLess(checks['nash_conv'],.005)
        self.assertLess(abs(checks['value_sb']-1),.005)
        self.assertEqual(result['work_budget']['current_rank_calls'],0)
        with self.assertRaises(ValueError):replay(result,'AA','KK',CONFIG,trusted_counts(table))
        bad=deepcopy(result);bad['count_provenance'][0]['suit_permutation']={'c':'c','d':'d','h':'h','s':'h'}
        with self.assertRaisesRegex(ValueError,'suit map'):
            replay(bad,'AA','KK',CONFIG,trusted_counts(table),covered_counts=True)

    def test_legacy_admission_remains_literal_and_overbudget_never_builds_tree(self):
        source=source_table()
        with self.assertRaisesRegex(ValueError,'pair limit'):
            ordinary.plan_preflop_equities('AA','KK')
        table=covered.pool_preflop_equities_by_suit([source],'AA','KK')
        with self.assertRaises(TypeError):solver.solve_prepared_preflop_checkdown(table,resource_model='prepared-counts')
        with self.assertRaises(TypeError):solver.solve_covered_preflop_checkdown(source)
        with patch.object(solver,'build_preflop_tree',side_effect=AssertionError('built unadmitted tree')):
            with self.assertRaisesRegex(ValueError,'500,000,000'):
                solver.solve_covered_preflop_checkdown(table,config={**CONFIG,'max_raises':3},iterations=10000)

    def test_six_physical_pairs_reuse_pinned_sources_and_native_matches_python(self):
        import json, os
        from pathlib import Path
        from scripts.benchmark_preflop_exact_anchor import _load_inputs,SPEC_PATH
        item=_load_inputs(json.loads(SPEC_PATH.read_text()))
        bb='AsKh:.25,AsKc:.5,AdKh:.75,AdKc:1,KdKs:1'
        table=covered.pool_preflop_equities_by_suit([item['table']],'AdAs:1,QdQs:.5',bb)
        self.assertEqual(len(table.pairs),6)
        expected={('AdAs','KdKs'):Fraction(4,11),('QdQs','KdKs'):Fraction(2,11),
                  ('QdQs','AsKh'):Fraction(1,22),('QdQs','AsKc'):Fraction(1,11),
                  ('QdQs','AdKh'):Fraction(3,22),('QdQs','AdKc'):Fraction(2,11)}
        for i,j,p in table.pairs:
            self.assertEqual(p,expected[(''.join(table.hands[0][i]),''.join(table.hands[1][j]))])
        py=solver.solve_covered_preflop_checkdown(table,config=CONFIG,iterations=1000)
        checked=replay(py,'AdAs:1,QdQs:.5',bb,CONFIG,trusted_counts(table),covered_counts=True)
        self.assertLess(checked['nash_conv'],.005)
        build=os.environ.get('OPENPOKER_NATIVE_TRAIN_BUILD_DIR')
        if build and Path(build).is_dir():
            native=solver.solve_covered_preflop_checkdown(table,config=CONFIG,iterations=1000,
                                                        training_backend='native',build_directory=build)
            other=replay(native,'AdAs:1,QdQs:.5',bb,CONFIG,trusted_counts(table),covered_counts=True)
            self.assertLess(abs(other['nash_conv']-checked['nash_conv']),1e-10)
            for a,b in zip(py['strategy'],native['strategy']):
                for x,y in zip(a['actions'],b['actions']):
                    self.assertLess(abs(x['probability']-y['probability']),1e-6)
