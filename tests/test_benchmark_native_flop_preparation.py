"""Frozen admission, source authentication and complete-call evidence boundaries."""
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import benchmark_native_flop_preparation as bench
from scripts.flop_checkdown_validation import prepare_oracle_from_counts

class NativeFlopBenchmarkTests(unittest.TestCase):
    def setUp(self):self.spec=json.loads(bench.SPEC.read_bytes())

    def test_all_complete_and_prep_admissions_precede_binary_lookup(self):
        with patch.object(bench.count_native,'_backend',side_effect=AssertionError('early lookup')):
            pre=bench.preflights(self.spec)
        self.assertEqual(len(pre['complete_calls']),2)
        self.assertEqual(len(pre['fresh_count_preparation_admissions']),2)
        self.assertTrue(all(r['native_complete_admission']['total_loop_entries_upper_bound']<=500000000
                            for r in pre['complete_calls']))
        self.assertTrue(all(r['native_complete_admission']['total_loop_entries_upper_bound']==378109520
                            for r in pre['complete_calls']))

    def test_dirty_source_rejects_before_counts_admission_or_build(self):
        with patch.object(bench,'snapshot',return_value={'status':['dirty']}),patch.object(bench,'preflights') as admit, \
             patch.object(bench,'count_build_identity') as lookup:
            result=bench.run(self.spec,'missing','missing','missing')
        self.assertEqual(result['status'],'error');admit.assert_not_called();lookup.assert_not_called()

    def test_pinned_independent_physical_rows_cannot_be_resigned_after_tampering(self):
        source=bench.ROOT/self.spec['source_count_report_path'];data=json.loads(source.read_bytes())
        rows=next(r['oracle_pair_counts'] for r in data['results'] if r['fixture_id']=='weighted-8x8-stack12-raises1')
        rows[0]['wins']+=2;rows[0]['losses']-=2
        raw=json.dumps(data).encode();read=Path.read_bytes
        with patch.object(Path,'read_bytes',lambda p:raw if p==source else read(p)):
            with self.assertRaisesRegex(ValueError,'Pinned independent'):bench.historical_counts(self.spec)

    def test_actual_small_full_calls_preserve_exact_payloads_and_execution_census(self):
        counts_build=os.environ.get('OPENPOKER_NATIVE_EQUITY_BUILD_DIR')
        train_build=os.environ.get('OPENPOKER_NATIVE_TRAIN_BUILD_DIR')
        if not counts_build or not train_build:self.skipTest('Explicit count and trainer builds required')
        spec=deepcopy(self.spec);spec['iterations']=10
        case={'id':'small-unit-fixture','oop_range':'AsAd','ip_range':'KsKd',
              'expected_normalizer':'1','expected_compatible_pairs':1}
        counts=[{'oop_hand':'AdAs','ip_hand':'KdKs','wins':1782,'ties':48,'losses':150,'ordered_outcomes':1980}]
        table=bench.table_for(case,spec,counts)
        oracle=prepare_oracle_from_counts(spec['board'],case['oop_range'],case['ip_range'],spec['config'],counts)
        for stage in ('preparation','complete_call'):
            rows=[bench.measure(case,spec,b,stage,counts_build,train_build) for b in ('python','native')]
            for row in rows:
                assessment=bench.validate_sample(row,case,spec,table,oracle)
                self.assertEqual(json.loads(json.dumps(assessment)),assessment)
            self.assertEqual(rows[0]['payload'],rows[1]['payload'])
            self.assertEqual(rows[0]['payload_sha256'],rows[1]['payload_sha256'])
