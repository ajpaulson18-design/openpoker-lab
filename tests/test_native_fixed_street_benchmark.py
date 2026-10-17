from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import benchmark_native_fixed_street as bench

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / 'benchmarks' / 'native-fixed-street-v1.json').read_text(encoding='utf-8'))


def _payload(*, backend=None, scalar_delta=0.0, policy=(0.4, 0.6), row_history='root'):
    result = {
        'value_sb': 0.0 + scalar_delta, 'value_bb': 0.0,
        'sb_best_response_value': 0.0, 'bb_best_response_value': 0.0,
        'sb_best_response_gain': 0.0, 'bb_best_response_gain': 0.0,
        'nash_conv': 0.0, 'exploitability': 0.0,
        'game': 'two-player-zero-sum',
        'strategy': [{
            'player': 0, 'hand': 'AsAd', 'history': row_history,
            'actions': [
                {'action': 'fold', 'amount': 0.0, 'probability': policy[0]},
                {'action': 'all-in', 'amount': 2.0, 'probability': policy[1]},
            ],
        }],
    }
    if backend == 'native':
        result['training_backend'] = 'native'
        result['native_training'] = {'backend': 'native-fixed-street-v1'}
    return result


def _sample(payload, backend, repeat, seconds):
    return {
        'payload': payload, 'payload_sha256': f'{backend}-{repeat}',
        'complete_seconds': seconds, 'backend': backend, 'repeat': repeat,
        'phase_call_census_passed': True,
    }


class NativeFixedStreetBenchmarkHarnessTests(unittest.TestCase):
    def test_frozen_spec_rejects_mutated_gate_and_profile(self):
        bench.validate_spec(SPEC)
        for mutation in ('gate', 'profile'):
            altered = copy.deepcopy(SPEC)
            if mutation == 'gate':
                altered['acceptance']['cross_backend_metric_absolute_tolerance'] *= 2
            else:
                altered['flop']['profiles'][0]['iterations'] += 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                bench.validate_spec(altered)

    def test_payload_comparison_requires_same_game_history_actions_and_valid_numbers(self):
        left = _payload(backend='python')
        right = _payload(backend='native')
        equal = bench._compare_payloads('preflop', left, right, SPEC)
        self.assertTrue(equal['meets_metric_gate'])
        self.assertTrue(equal['meets_policy_gate'])

        mutations = []
        changed_game = copy.deepcopy(right); changed_game['game'] = 'different-game'; mutations.append(changed_game)
        missing_native = copy.deepcopy(right); missing_native.pop('native_training'); mutations.append(missing_native)
        wrong_native = copy.deepcopy(right); wrong_native['native_training']['backend'] = 'other'; mutations.append(wrong_native)
        changed_hand = copy.deepcopy(right); changed_hand['strategy'][0]['hand'] = 'KhKd'; mutations.append(changed_hand)
        changed_history = copy.deepcopy(right); changed_history['strategy'][0]['history'] = 'raise'; mutations.append(changed_history)
        changed_action = copy.deepcopy(right); changed_action['strategy'][0]['actions'][0]['action'] = 'check'; mutations.append(changed_action)
        for altered in mutations:
            with self.subTest(payload=altered), self.assertRaises(ValueError):
                bench._compare_payloads('preflop', left, altered, SPEC)

        scalar_miss = bench._compare_payloads(
            'preflop', left, _payload(backend='native', scalar_delta=1e-4), SPEC)
        self.assertFalse(scalar_miss['meets_metric_gate'])
        policy_miss = bench._compare_payloads(
            'preflop', left, _payload(backend='native', policy=(0.40001, 0.59999)), SPEC)
        self.assertFalse(policy_miss['meets_policy_gate'])
        for invalid in (float('nan'), float('inf'), -0.1, 1.1):
            bad = copy.deepcopy(right)
            bad['strategy'][0]['actions'][0]['probability'] = invalid
            with self.subTest(probability=invalid), self.assertRaises(ValueError):
                bench._compare_payloads('preflop', left, bad, SPEC)
        unnormalized = copy.deepcopy(right)
        unnormalized['strategy'][0]['actions'][1]['probability'] = 0.5
        with self.assertRaises(ValueError):
            bench._compare_payloads('preflop', left, unnormalized, SPEC)
        for invalid_metric in (float('nan'), float('inf')):
            bad = copy.deepcopy(right)
            bad['nash_conv'] = invalid_metric
            with self.subTest(metric=invalid_metric), self.assertRaises(ValueError):
                bench._compare_payloads('preflop', left, bad, SPEC)

    def test_rejected_preflight_never_looks_up_native_build(self):
        preflights = [
            {'game': 'preflop' if i < 3 else 'flop',
             'algorithm': 'vanilla', 'iterations': i + 1,
             'status': 'rejected' if i == 2 else 'admitted'}
            for i in range(6)
        ]
        identity = {'revision': 'frozen-test-rev', 'status': [], 'source_hashes': {}}
        with patch.object(bench, '_verify_profile_artifact', return_value={'ok': True}), \
             patch.object(bench, '_identity', return_value=identity), \
             patch.object(bench, '_require_baseline_ancestor'), \
             patch.object(bench, '_load_inputs', return_value={
                 'preflop': {'table': SimpleNamespace(pairs=(1, 2, 3))}, 'flop': {'table': SimpleNamespace(pairs=tuple(range(58)))}}), \
             patch.object(bench, '_preflight_all', return_value=preflights) as preflight, \
             patch.object(bench, '_build_identity', side_effect=AssertionError('native lookup occurred')) as build:
            report = bench.run(SPEC, 'nonexistent-native-build')
        preflight.assert_called_once()
        build.assert_not_called()
        self.assertFalse(report['all_six_preflights_passed'])
        self.assertEqual(report['profiles'], [])
        self.assertTrue(any('admission' in row.get('error', '').lower() for row in report['errors']))

    def test_replay_failure_keeps_timed_payload_and_duration(self):
        payloads = {
            'python': [_payload(backend='python') for _ in range(3)],
            'native': [_payload(backend='native') for _ in range(3)],
        }
        calls = []
        def fake_call(item, game, algorithm, iterations, backend, build_directory):
            repeat = 1 + sum(1 for row in calls if row['backend'] == backend)
            sample = _sample(payloads[backend][repeat - 1], backend, repeat,
                             2.0 if backend == 'python' else 1.0)
            calls.append(sample)
            return dict(sample)
        def replay_failure(game, item, samples, spec, errors, profile_id):
            errors.append({'phase': 'independent-replay', 'error': 'oracle rejected payload'})
            return {'python': [{'status': 'error'}], 'native': [{'status': 'error'}]}
        errors = []
        with patch.object(bench, '_profile_call', side_effect=fake_call), \
             patch.object(bench, '_phase_count_passed', return_value=True), \
             patch.object(bench, '_replay_unique', side_effect=replay_failure):
            result = bench._run_profile(SPEC, 'preflop', {'case': {}},
                                        {'algorithm': 'vanilla', 'iterations': 8000},
                                        'unused-build', errors)
        self.assertEqual(len(result['samples']), 6)
        for row in result['samples']:
            self.assertIsNotNone(row['payload'])
            self.assertGreater(row['complete_seconds'], 0)
        self.assertEqual(result['median_complete_seconds'], {'python': 2.0, 'native': 1.0})
        self.assertTrue(any(row.get('phase') == 'independent-replay' for row in errors))

    def test_trace_samples_are_separate_from_profile_medians(self):
        profile_result = {
            'profile_id': 'preflop-vanilla-8000', 'mandatory_quality': False,
            'speed_gate_passed': True,
            'independent_target_nash_conv_passed': {'python': False, 'native': False},
            'paired_comparisons': [{'meets_metric_gate': True, 'meets_policy_gate': True}] * 3,
            'unique_policy_replays': {'python': [{'status': 'passed'}], 'native': [{'status': 'passed'}]},
            'median_complete_seconds': {'python': 2.0, 'native': 1.0},
        }
        identity = {'revision': 'frozen-test-rev', 'status': [], 'source_hashes': {}}
        with patch.object(bench, '_verify_profile_artifact', return_value={'ok': True}), \
             patch.object(bench, '_identity', return_value=identity), \
             patch.object(bench, '_require_baseline_ancestor'), \
             patch.object(bench, '_load_inputs', return_value={
                 'preflop': {'table': SimpleNamespace(pairs=(1, 2, 3))}, 'flop': {'table': SimpleNamespace(pairs=tuple(range(58)))}}), \
             patch.object(bench, '_preflight_all', return_value=[{'status': 'admitted'}] * 6), \
             patch.object(bench, '_build_identity', return_value={'manifest_sha256': 'x'}), \
             patch.object(bench, '_run_profile', return_value=profile_result), \
             patch.object(bench, '_run_traces', return_value={
                 'python': {'complete_seconds': 1000.0, 'payload': None},
                 'native': {'complete_seconds': 2000.0, 'payload': None}}):
            report = bench.run(SPEC, 'mock-build')
        self.assertEqual(len(report['profiles']), 6)
        for profile in report['profiles']:
            self.assertEqual(profile['median_complete_seconds'], {'python': 2.0, 'native': 1.0})
            self.assertNotIn('trace', profile)
        self.assertEqual(report['separate_preflop_allocation_traces']['python']['complete_seconds'], 1000.0)
        self.assertEqual(report['separate_preflop_allocation_traces']['native']['complete_seconds'], 2000.0)


if __name__ == '__main__':
    unittest.main()
