import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import benchmark_native_fixed_street_vector as bench

SPEC = json.loads(bench.SPEC_PATH.read_text(encoding='utf-8'))


def _payload(game):
    return {'native_training': {'reduction': SPEC['reductions'][game],
            'build': {'protocol': SPEC['protocol'], 'work_model': SPEC['work_model']}}}


def _report():
    return {'errors': [], 'status': 'passed', 'artifact_sha256': 'old',
            'profiles': [{'game': game, 'samples': [
                {'backend': 'native', 'payload': _payload(game)} for _ in range(3)]}
                for game in ('preflop', 'flop') for _ in range(3)],
            'separate_preflop_allocation_traces': {'native': {'payload': _payload('preflop')}}}


class NativeVectorFollowupTests(unittest.TestCase):
    def test_frozen_followup_plan_and_initial_report_are_preserved(self):
        bench.validate_spec(SPEC)
        altered = copy.deepcopy(SPEC); altered['reductions']['flop'] = 'scalar'
        with self.assertRaises(ValueError):
            bench.validate_spec(altered)
        raw = (bench.ROOT / SPEC['initial_report_path']).read_bytes()
        with patch.object(bench.base, '_git', return_value=SPEC['initial_report_blob']), \
                patch.object(bench.subprocess, 'check_output', return_value=raw):
            identity = bench._initial_identity(SPEC)
            self.assertEqual(identity['artifact_sha256'], SPEC['initial_report_artifact_sha256'])
        with patch.object(bench.base, '_git', return_value='wrong'), \
                patch.object(bench.subprocess, 'check_output', return_value=raw):
            with self.assertRaises(ValueError):
                bench._initial_identity(SPEC)

    def test_all_native_observations_must_use_declared_reduction(self):
        report = _report()
        self.assertEqual(bench._reduction_census(report, SPEC)
                         ['native_timed_and_trace_payloads_checked'], 19)
        report['profiles'][3]['samples'][0]['payload']['native_training']['reduction'] = 'scalar'
        with self.assertRaises(ValueError):
            bench._reduction_census(report, SPEC)
        report = _report(); report['profiles'][0]['samples'].pop()
        with self.assertRaises(ValueError):
            bench._reduction_census(report, SPEC)

    def test_followup_retains_raw_failure_and_checks_initial_report_after_run(self):
        report = _report()
        report['errors'].append({'phase': 'agreement', 'error': 'retained failure'})
        report['raw_witness'] = {'probability': 0.453143317204644}
        with patch.object(bench, '_initial_identity', return_value={'pin': 1}) as identity, \
                patch.object(bench.base, 'run', return_value=report) as run:
            result = bench.run(SPEC, 'explicit-build')
        self.assertEqual(identity.call_count, 2)
        self.assertEqual(run.call_args.args[0]['acceptance']
                         ['cross_backend_policy_probability_absolute_tolerance'], 1e-6)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['raw_witness'], report['raw_witness'])
        unsigned = dict(result); unsigned.pop('artifact_sha256')
        self.assertEqual(result['artifact_sha256'], bench.base.checksum(unsigned))
        with patch.object(bench, '_initial_identity', side_effect=[{'pin': 1}, {'pin': 2}]), \
                patch.object(bench.base, 'run', return_value=_report()):
            result = bench.run(SPEC, 'explicit-build')
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['errors'][-1]['phase'], 'followup-integrity')


if __name__ == '__main__':
    unittest.main()
