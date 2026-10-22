"""Synthetic batch lifecycle checks; no physical ranking or solver training."""
from copy import deepcopy
from fractions import Fraction
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import benchmark_flop_class_reweight_cfrplus as runner
from scripts import flop_public_classes as proof


def _source():
    return {'revision': 'a'*40, 'status': '', 'source_lf_sha256': {'fixed.py': 'b'*64}}


def _result(case_id, iterations):
    admission = runner.trainer.admit_request(case_id, iterations)
    strategy = [{'row': i} for i in range(16912)]
    metrics = {key: '0' for key in proof.METRICS}
    metrics['nash_conv'] = '1/100' if case_id == 'uniform' else '0'
    census = dict(runner.trainer.reweighted.EXPECTED_CENSUS)
    result = {'case_id': case_id, 'status': 'trained-policy-physically-verified',
              'admission': admission,
              'plan': runner.evidence._plan_record(runner.trainer.case_plan(case_id)),
              'source_lf_sha256': _source()['source_lf_sha256'],
              'baseline_worlds_sha256': proof.PHYSICAL_WORLDS_SHA256,
              'physical_worlds_sha256': 'c'*64,
              'census': census, 'maximum_world_path_states': 33,
              'raw_class_policy': [[i, 0.5, 0.5] for i in range(466)],
              'normalization': {'synthetic': True},
              'physical_policy': {'iterations': iterations, 'algorithm': 'cfrplus',
                                  'averaging_delay': 0, 'strategy': strategy},
              'audit': {'exact_metric_count': 8, 'exact_metrics': metrics,
                        'class_rows': 466, 'physical_rows_lifted': 16912,
                        'maximum_numeric_gap': 0.0, 'class_policy': [[0.5, 0.5]]*466,
                        'physical_strategy_sha256': proof._digest(strategy)},
              'preparation_forbidden_calls': {str(i): 0 for i in range(41)},
              'diagnostic_forbidden_calls': {str(i): 0 for i in range(41)},
              'quality_target': 0.005, 'quality_target_met': case_id != 'uniform'}
    result['artifact_sha256'] = proof._digest(result)
    return result


class WeightedPilotTests(unittest.TestCase):
    def _contexts(self, *, solve=None, snapshots=None):
        def fake_solve(case_id, iterations):
            runner.cfr_plus.train(None, (), {}, iterations)
            return _result(case_id, iterations)
        return (patch.object(runner, '_snapshot', return_value=_source())
                if snapshots is None else patch.object(runner, '_snapshot', side_effect=snapshots),
                patch.object(runner.trainer, 'source_hashes', return_value=_source()['source_lf_sha256']),
                patch.object(runner, '_proof_world_identities', return_value={x: 'c'*64 for x in runner.CASES}),
                patch.object(runner, '_baseline_reference', return_value=_result('baseline', 560)),
                patch.object(runner.cfr_plus, 'train', return_value={}),
                patch.object(runner.trainer, 'solve_reweighted', side_effect=solve or fake_solve))

    def _run(self, output, *, solve=None, snapshots=None):
        c = self._contexts(solve=solve, snapshots=snapshots)
        with c[0], c[1], c[2], c[3], c[4] as original, c[5]:
            report = runner.run(output)
            self.assertIs(runner.cfr_plus.train, original)
        return report

    def test_real_protocol_admits_all_three_requests_without_auth_or_training(self):
        with patch.object(runner.publication, '_read_index', side_effect=AssertionError('auth')), \
             patch.object(runner.trainer, 'solve_reweighted', side_effect=AssertionError('solve')):
            requests = runner._preflight(runner._protocol())
        self.assertEqual([row[:2] for row in requests], [(x, 560) for x in runner.CASES])
        self.assertEqual(sum(row[2]['total_admitted_work'] for row in requests), 225323868)

    def test_quality_miss_retained_and_later_case_runs_with_three_actual_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)/'batch'
            report = self._run(directory)
            self.assertEqual(report['status'], 'complete')
            self.assertEqual(report['training_calls'], 3)
            self.assertEqual(report['solve_calls_started'], 3)
            self.assertEqual(report['solve_calls_completed'], 3)
            self.assertEqual([r['status'] for r in report['cases']], ['complete']*3)
            self.assertFalse(report['cases'][1]['audit_summary']['quality_target_met'])
            self.assertTrue(report['cases'][0]['old_baseline_semantics_equal'])
            self.assertEqual(len(report['files']), 3)
            result = json.loads(gzip.decompress((directory/'uniform-560.json.gz').read_bytes()))
            self.assertEqual(result['audit']['exact_metrics']['nash_conv'], '1/100')
            self.assertFalse(result['quality_target_met'])

    def test_post_training_exception_keeps_original_error_and_stops_later_cases(self):
        def fail(case_id, iterations):
            runner.cfr_plus.train(None, (), {}, iterations)
            raise RuntimeError('original failure after actual invocation')
        with tempfile.TemporaryDirectory() as tmp:
            report = self._run(Path(tmp)/'batch', solve=fail)
            self.assertEqual(report['status'], 'error')
            self.assertEqual(report['training_calls'], 1)
            self.assertEqual(report['solve_calls_completed'], 0)
            self.assertEqual(report['cases'][0]['status'], 'error')
            self.assertIn('original failure after actual invocation', report['errors'][0]['error'])
            self.assertIn('RuntimeError', report['errors'][0]['traceback'])
            self.assertEqual([r['not_run_reason'] for r in report['cases'][1:]],
                             ['stopped-after-earlier-failure']*2)

    def test_invalid_return_is_saved_before_acceptance_and_never_retried(self):
        def invalid(case_id, iterations):
            runner.cfr_plus.train(None, (), {}, iterations)
            result = _result(case_id, iterations)
            result['physical_worlds_sha256'] = 'd'*64
            result['artifact_sha256'] = proof._digest({k:v for k,v in result.items()
                                                       if k != 'artifact_sha256'})
            return result
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)/'batch'
            report = self._run(directory, solve=invalid)
            self.assertEqual(report['status'], 'error')
            self.assertEqual(report['training_calls'], 1)
            self.assertEqual(len(report['files']), 1)
            self.assertIn('world identity', report['errors'][0]['error'])
            saved = json.loads(gzip.decompress((directory/'baseline-560.json.gz').read_bytes()))
            self.assertEqual(saved['physical_worlds_sha256'], 'd'*64)

    def test_source_drift_after_call_is_primary_and_retains_policy(self):
        def drift(case_id, iterations):
            runner.cfr_plus.train(None, (), {}, iterations)
            return _result(case_id, iterations)
        changed = {**_source(), 'revision': 'e'*40}
        with tempfile.TemporaryDirectory() as tmp:
            report = self._run(Path(tmp)/'batch', solve=drift,
                               snapshots=[_source(),_source(),_source(),changed,changed])
            self.assertEqual(report['status'], 'error')
            self.assertEqual(len(report['files']), 1)
            self.assertIn('Source changed during weighted call', report['errors'][0]['error'])
            self.assertEqual(report['training_calls'], 1)

    def test_baseline_raw_policy_mismatch_is_an_error_even_with_quality_pass(self):
        def bad_baseline(case_id, iterations):
            runner.cfr_plus.train(None, (), {}, iterations)
            result = _result(case_id, iterations)
            result['raw_class_policy'][0][1] = 0.25
            result['artifact_sha256'] = proof._digest({k:v for k,v in result.items()
                                                       if k != 'artifact_sha256'})
            return result
        with tempfile.TemporaryDirectory() as tmp:
            report = self._run(Path(tmp)/'batch', solve=bad_baseline)
            self.assertEqual(report['status'], 'error')
            self.assertIn('published 560-sweep pilot', report['errors'][0]['error'])
            self.assertEqual(report['training_calls'], 1)


if __name__ == '__main__':
    unittest.main()
