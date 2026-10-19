"""Meaningful boundary checks for the separate covered-count experiment."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import benchmark_preflop_covered_counts as bench
from pokerlab.preflop_checkdown_solver import solve_prepared_preflop_checkdown

class CoveredBenchmarkTests(unittest.TestCase):
    def setUp(self):self.spec=json.loads(bench.SPEC_PATH.read_bytes())

    def test_all_frozen_requests_admit_without_build_or_training(self):
        from pokerlab import native_fixed_street as native
        with patch.object(native,'_backend',side_effect=AssertionError('looked up native early')):
            table,counts,ref=bench.inputs(self.spec)
            rows=[bench.preflight(table,self.spec,n) for n in self.spec['checkpoints']]
        self.assertEqual(len(table.pairs),6)
        self.assertEqual(len(counts),6)
        self.assertEqual(len(table.hands[1]),5)
        self.assertEqual(len(rows),4)
        self.assertTrue(all(x['python']['total_loop_entries_upper_bound']<=500000000 for x in rows))
        self.assertTrue(all(x['native']['total_loop_entries_upper_bound']<=500000000 for x in rows))
        changed=dict(self.spec,compatible_pairs=5)
        with self.assertRaises(ValueError):bench.validate_spec(changed)

    def test_dirty_source_rejects_before_counts_build_or_training(self):
        with (patch.object(bench,'identity',return_value={'status':['dirty']}),
              patch.object(bench,'inputs') as loaded,
              patch.object(bench.native,'_build_identity') as build,
              patch.object(bench,'measure') as trained):
            report=bench.run(self.spec,'unused')
        loaded.assert_not_called();build.assert_not_called();trained.assert_not_called()
        self.assertEqual(report['status'],'error')
        self.assertEqual(report['profiles'],[])

    def test_legacy_solver_payload_matches_published_frozen_reference(self):
        from scripts import benchmark_preflop_exact_anchor as old
        spec=json.loads(old.SPEC_PATH.read_bytes());item=old._load_inputs(spec)
        got=solve_prepared_preflop_checkdown(item['table'],config=item['case']['config'],
                   iterations=10,algorithm='cfrplus',resource_model='prepared-counts',world_indexing='pair-mean')
        report=json.loads((bench.ROOT/'benchmarks/results/preflop-exact-anchor-v1.json').read_bytes())
        row=next(x for x in report['profiles'] if x['algorithm']=='cfrplus' and x['iterations']==10)
        pinned=next(x for x in row['samples'] if x['backend']=='python')
        import hashlib, sys
        frozen=(bench.ROOT/'tests/fixtures/preflop_checkdown_solver_before_covered.py.txt').read_bytes()
        self.assertEqual(hashlib.sha256(frozen).hexdigest(), '377433bb3fd0a276be24f54d3249c6e573cb2930df63a27cfaba0c098063659d')
        reference={'__name__':'pokerlab._legacy_checkdown_reference','__package__':'pokerlab'}
        exec(compile(frozen,'frozen_pre_covered_checkdown','exec'),reference)
        same_interpreter=reference['solve_prepared_preflop_checkdown'](
            item['table'],config=item['case']['config'],iterations=10,algorithm='cfrplus',
            resource_model='prepared-counts',world_indexing='pair-mean')
        self.assertEqual(got,same_interpreter)
        self.assertEqual(bench.checksum(got),bench.checksum(same_interpreter))
        # The recorded raw hash is specifically a Python 3.12 observation.
        # 3.11 uses the earlier summation behavior; production code is compared
        # exactly to the untouched old body above on every interpreter.
        if sys.version_info[:2]==(3,12):
            self.assertEqual(bench.checksum(got),pinned['payload_sha256'])
            self.assertEqual(got,pinned['payload'])

    def test_failed_assessment_keeps_raw_candidate_payload(self):
        payload={'raw':'retained'}
        with (patch.object(bench,'solve_covered_preflop_checkdown',return_value=payload),
              patch.object(bench,'assess',side_effect=ValueError('independent rejection'))):
            row=bench.measure(None,None,self.spec,10,'python','unused')
        self.assertEqual(row['payload'],payload)
        self.assertEqual(row['payload_sha256'],bench.checksum(payload))
        self.assertIn('independent rejection',row['error'])
