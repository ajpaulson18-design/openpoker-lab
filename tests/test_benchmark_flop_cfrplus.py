"""CFR+ experiment admission, source identity and failure retention boundaries."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from scripts import benchmark_flop_cfrplus as bench


class FlopCFRPlusBenchmarkTests(unittest.TestCase):
    def test_full_three_pass_request_admitted_before_any_ranking(self):
        with patch.object(bench.base.production,'rank_hand',side_effect=AssertionError('rank')), \
             patch.object(bench.base.production,'_enumerate_worlds',side_effect=AssertionError('worlds')), \
             patch.object(bench.base.production,'solve_postflop',side_effect=AssertionError('solve')):
            forecast=bench.preflight(bench.load_spec())
        self.assertEqual(forecast['worlds'],5940)
        self.assertEqual(forecast['max_world_node_iterations'],29937600)
        self.assertEqual(forecast['training_passes_per_iteration'],3)
        self.assertEqual(forecast['public_prefix_hand_edges'],6078)
        spec=deepcopy(bench.load_spec());spec['iterations'][-1]=141
        spec['expected']['max_world_iterations']=837540
        spec['expected']['max_world_node_iterations']=30151440
        with self.assertRaisesRegex(ValueError,'three-pass'):
            bench.preflight(spec)

    def test_dirty_candidate_retains_error_before_baseline_or_ranking(self):
        state={'revision':'dirty','status':[' M source'],'source_hashes':{}}
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(bench,'snapshot',return_value=state), \
             patch.object(bench,'preflight') as forecast, \
             patch.object(bench,'verify_baseline') as baseline:
            report=bench.run(Path(temp)/'candidate',Path(temp)/'baseline')
        self.assertEqual(report['status'],'error')
        self.assertEqual(report['samples'],[])
        self.assertIn('clean frozen',report['validation_errors'][0])
        forecast.assert_not_called();baseline.assert_not_called()

    def test_unknown_resigned_baseline_source_refuses(self):
        spec=bench.load_spec()
        source={'revision':spec['baseline_commit'],'status':[], 'source_hashes':{}}
        report={'spec_sha256':spec['baseline_spec_sha256'],'source_before':source,'source_after':source}
        with self.assertRaisesRegex(ValueError,'authenticated frozen'):
            bench.check_baseline_identity(report,spec)

    def test_resigned_baseline_observation_refuses_before_candidate_ranking(self):
        original=json.loads((bench.baseline_publication.PUBLICATION/'index.json').read_bytes())
        original['runtime']['platform']='forged-platform'
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            bench.base._write_index(directory,original)
            with patch.object(bench.base,'prepare_reference',side_effect=AssertionError('ranking')), \
                 self.assertRaisesRegex(ValueError,'Immutable published index'):
                bench.verify_baseline(directory,bench.load_spec())

    def test_backend_and_three_pass_identity_cannot_be_resigned(self):
        row={'traversal':'public-batched','iterations':140}
        payload={'algorithm':'cfrplus','iterations':140,'execution_backend':'public-batched-python',
                 'plan_operation_limit':None,'public_batch_edge_limit':250000,
                 'training_passes_per_iteration':3,'update_schedule':'alternating-oop-then-ip',
                 'average_schedule':'linear-post-sweep-own-reach'}
        bench.check_candidate(payload,row)
        for key,value in (('training_passes_per_iteration',1),('public_batch_edge_limit',None),
                          ('execution_backend','recursive-python'),('iterations',141),
                          ('update_schedule','simultaneous'),('average_schedule','uniform')):
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'identity'):
                bench.check_candidate(dict(payload,**{key:value}),row)


if __name__=='__main__':
    unittest.main()
