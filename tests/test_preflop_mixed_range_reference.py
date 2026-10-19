"""Mixed physical range construction and independently legal value bounds."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import preflop_mixed_range_reference as ref
from scripts import benchmark_preflop_mixed_range as bench

class PhysicalRangeReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=json.loads(ref.SPEC.read_bytes());cls.table,cls.counts,cls.source=ref.load_inputs(cls.spec)

    def test_full_mixed_range_has_exact_priors_and_legal_bounds(self):
        proof=ref.constructive_bounds(self.spec,self.counts)
        self.assertEqual(len(self.table.pairs),72)
        self.assertEqual(proof['suit_overlap_class_counts'],{r:{'0':6,'1':24,'2':6} for r in ('A','Q')})
        self.assertEqual(proof['lower_bound_fraction'],'1/2')
        self.assertEqual(proof['upper_bound_fraction'],'1')
        self.assertNotIn('exact_value_sb_fraction',proof)
        self.assertEqual(self.table.budget['physical_worlds_upper_bound'],123285888)
        masses={'A':Fraction(0),'Q':Fraction(0)}
        for i,j,prior in self.table.pairs:
            rank=self.table.hands[0][i][0][0]
            self.assertEqual(prior,Fraction(1,54) if rank=='A' else Fraction(1,108))
            masses[rank]+=prior
        self.assertEqual(masses,{'A':Fraction(2,3),'Q':Fraction(1,3)})

    def test_bound_rejects_missing_pair_or_invalid_showdown_mean(self):
        with self.assertRaises(ValueError):ref.constructive_bounds(self.spec,self.counts[:-1])
        altered=deepcopy(self.counts)
        strong=next(row for row in altered if row['sb_hand'].startswith('A'))
        strong.update(wins=500000,ties=12304,losses=1200000)
        with self.assertRaisesRegex(ValueError,'payoff inequalities'):ref.constructive_bounds(self.spec,altered)
        altered=deepcopy(self.counts)
        weak=next(row for row in altered if row['sb_hand'].startswith('Q'))
        weak['wins'],weak['losses']=weak['losses'],weak['wins']
        with self.assertRaisesRegex(ValueError,'negative'):ref.constructive_bounds(self.spec,altered)
        with self.assertRaises(ValueError):ref.constructive_bounds({**self.spec,'bb_range':'QQ'},self.counts)

    def test_source_count_tampering_cannot_be_hidden_by_a_new_self_checksum(self):
        from scripts.benchmark_preflop_covered_counts import checksum
        original=json.loads(ref.REPORTS[1].read_bytes())
        original['independent_physical_count_rows'][0]['wins']+=1
        original['independent_physical_count_rows'][0]['losses']-=1
        original.pop('artifact_sha256');original['artifact_sha256']=checksum(original)
        original_read=Path.read_bytes
        def read_source(path):
            return json.dumps(original).encode() if path==ref.REPORTS[1] else original_read(path)
        with patch.object(Path,'read_bytes',read_source):
            with self.assertRaisesRegex(ValueError,'source report identity changed'):ref.load_inputs(self.spec)

    def test_constructive_consistency_uses_intersection_not_interval_containment(self):
        def assessed(lower,upper,value):
            return {'independent_replay':{'sb_best_response_fraction':[upper.numerator,upper.denominator],
                    'bb_best_response_fraction':[-lower.numerator,lower.denominator],
                    'value_sb_fraction':[value.numerator,value.denominator]}}
        for low,high,value in ((Fraction(3,4),Fraction(4,5),Fraction(2)),
                               (Fraction(0),Fraction(3,4),Fraction(-1))):
            # Profile EV may be outside the constructive equilibrium interval;
            # it is never an exact equilibrium value gate.
            with patch.object(bench.core,'assess',return_value=assessed(low,high,value)):
                checked=bench.mixed_assessment({},self.counts,self.spec)
            self.assertTrue(checked['bracket_intersects_constructive_interval'])
        with patch.object(bench.core,'assess',return_value=assessed(Fraction(2),Fraction(3),Fraction(2))):
            with self.assertRaisesRegex(ValueError,'constructive interval'):
                bench.mixed_assessment({},self.counts,self.spec)

    def test_all_requests_admit_before_lookup_and_four_pair_preparation_stays_closed(self):
        from pokerlab import native_fixed_street as native
        from pokerlab.preflop_full_board_equity import plan_preflop_equities
        with patch.object(native,'_backend',side_effect=AssertionError('native before all admissions')):
            rows=[bench.core.preflight(self.table,self.spec,n) for n in self.spec['checkpoints']]
        self.assertEqual(len(rows),3)
        self.assertLessEqual(max(x['python']['total_loop_entries_upper_bound'] for x in rows),500000000)
        self.assertLessEqual(max(x['native']['total_loop_entries_upper_bound'] for x in rows),500000000)
        with self.assertRaises(ValueError):plan_preflop_equities('AA','KK')

    def test_dirty_source_never_resolves_inputs_or_native_build(self):
        with (patch.object(bench,'snapshot',return_value={'status':['dirty']}),
              patch.object(ref,'load_inputs') as inputs,
              patch.object(bench.core.native,'_build_identity') as lookup):
            report=bench.run(self.spec,'unused')
        self.assertEqual(report['status'],'error');inputs.assert_not_called();lookup.assert_not_called()
        self.assertTrue(report['created_at_utc'])
        self.assertTrue(report['runtime']['python'])
        self.assertTrue(report['runtime']['executable'])
        self.assertTrue(report['runtime']['platform'])

    def test_saved_metadata_addition_updates_the_actual_checksum(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'report.json';report={'status':'test-only'}
            bench.save_report(path,report)
            report['saved_verification']={'status':'test-only'};bench.save_report(path,report)
            data=json.loads(path.read_bytes());digest=data.pop('artifact_sha256')
            self.assertEqual(digest,bench.core.checksum(data))

    def test_error_report_cannot_be_verified_as_a_passing_observation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'failed.json';bench.save_report(path,{'status':'error','errors':['retained failure']})
            with patch.object(ref,'load_inputs') as inputs:
                with self.assertRaisesRegex(ValueError,'did not pass'):bench.verify_saved(path)
            inputs.assert_not_called()

    def test_native_full_range_strategies_pass_independent_reference_when_built(self):
        import os
        build=os.environ.get('OPENPOKER_NATIVE_TRAIN_BUILD_DIR')
        if not build or not Path(build).is_dir():self.skipTest('Explicit native build not selected')
        from pokerlab.preflop_checkdown_solver import solve_covered_preflop_checkdown
        results={}
        for backend in ('python','native'):
            results[backend]=solve_covered_preflop_checkdown(self.table,config=self.spec['config'],
                            iterations=10,algorithm='cfrplus',training_backend=backend,
                            build_directory=build if backend=='native' else None)
            checked=bench.mixed_assessment(results[backend],self.counts,self.spec)
            self.assertTrue(checked['bracket_intersects_constructive_interval'])

        parity=bench.core.compare(results['python'],results['native'],self.spec)
        self.assertTrue(parity['meets_metric_gate']);self.assertTrue(parity['meets_policy_gate'])
