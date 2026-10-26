"""Synthetic complete-artifact failure tests; no new training is performed."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.historical_turn_sources import TRANSITIONS
from scripts import benchmark_turn_tail as runner


TEMP_ROOT = Path(__file__).resolve().parents[1] / '.test_tmp'


class TurnTailArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEMP_ROOT.mkdir(exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        cls.directory = Path(cls.temporary.name).resolve()
        if TEMP_ROOT.resolve() not in cls.directory.parents:
            raise ValueError('Test temporary directory escaped its workspace')
        cls.report = cls.directory / 'report.json'
        cls.policies = cls.directory / 'policies'
        cls.baseline = runner._baseline_pins()
        cls.sources = runner.fingerprints()
        with patch.object(runner, 'fingerprints', return_value=cls.sources), \
                patch.object(runner, '_head', return_value='a' * 40), \
                patch.object(runner, 'capture', side_effect=cls.snapshots), patch('builtins.print'):
            # These historical policies are ONLY zero-training unit fixtures.
            # The real experiment requires current same-run captured snapshots.
            runner.generate(cls.report, cls.policies, allow_training=True)
        cls.accepted = cls.report.read_bytes()
        cls.policy_bytes = {p.name: p.read_bytes() for p in cls.policies.glob('*.json')}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def snapshots(cls, case, backend, discard, total, interval=None):
        return (json.loads(cls.baseline['policies'][backend, total]),
                json.loads(cls.baseline['policies'][backend, discard]),
                {'callback_iterations': [discard, total], 'trainer_calls': 1,
                 'final_snapshot_exactly_matches_returned_profile': True,
                 'complete_call_with_observations_seconds': 0.0,
                 'independent_replay_seconds': 0.0})

    def restore(self):
        self.report.write_bytes(self.accepted)
        for name, raw in self.policy_bytes.items():
            (self.policies / name).write_bytes(raw)

    def tearDown(self):
        self.restore()

    def verify(self):
        with patch.object(runner, 'fingerprints', return_value=self.sources), \
                patch.object(runner, '_head', return_value='a' * 40):
            return runner._verify_saved(self.report, self.policies)

    def test_saved_callback_window_provenance_and_hash_tampering_rejects(self):
        for field in ('callback', 'window', 'provenance', 'hash'):
            with self.subTest(field=field):
                self.restore()
                report = json.loads(self.accepted)
                row = report['results'][0]
                if field == 'callback':
                    row['capture_callback_iterations'] = [1000, 1499]
                elif field == 'hash':
                    row['policy_sha256'] = '0' * 64
                else:
                    path = self.policies / row['policy_file']
                    policy = json.loads(path.read_bytes())
                    if field == 'window':
                        policy['source_iteration_window'] = [2, 1000]
                    else:
                        policy['diagnostic_provenance'] = 'Production trainer diagnostic'
                    raw = runner._canonical(policy)
                    path.write_bytes(raw)
                    row['policy_sha256'] = runner._sha(raw)
                self.report.write_bytes(runner._canonical(report))
                with self.assertRaises(ValueError):
                    self.verify()

    def test_late_owned_policy_report_and_reference_drift_rejects(self):
        for changed in ('policy', 'report', 'reference'):
            with self.subTest(changed=changed):
                self.restore()
                original_replay, original_read = runner._replay, runner._read_capped
                calls, reference_reads = [], []

                def replay(*args, **kwargs):
                    value = original_replay(*args, **kwargs)
                    calls.append(1)
                    if len(calls) == 6:
                        if changed == 'policy':
                            first = next(iter(self.policy_bytes))
                            (self.policies / first).write_bytes(b'changed after replay')
                        elif changed == 'report':
                            self.report.write_bytes(self.accepted + b' ')
                    return value

                def read(path, cap, label):
                    raw = original_read(path, cap, label)
                    if Path(path) == runner.REFERENCE_PATH:
                        reference_reads.append(1)
                        if changed == 'reference' and len(reference_reads) > 1:
                            return raw + b'simulated late drift'
                    return raw

                with patch.object(runner, '_replay', side_effect=replay), \
                        patch.object(runner, '_read_capped', side_effect=read):
                    with self.assertRaises(ValueError):
                        self.verify()
                self.assertEqual(len(calls), 6)

    def test_input_drift_after_first_capture_stops_before_second_call(self):
        original_read, calls = runner._read_capped, []
        path, policies = self.directory / 'drift-output.json', self.directory / 'drift-policies'
        policies.mkdir()
        sibling = policies / 'unrelated.txt'
        sibling.write_bytes(b'keep')

        def capture(*args, **kwargs):
            calls.append(1)
            return self.snapshots(*args, **kwargs)

        def read(path, cap, label):
            raw = original_read(path, cap, label)
            return raw + b'changed' if calls and Path(path) == runner.BASELINE_REPORT else raw

        with patch.object(runner, 'fingerprints', return_value=self.sources), \
                patch.object(runner, '_head', return_value='a' * 40), \
                patch.object(runner, 'capture', side_effect=capture), \
                patch.object(runner, '_read_capped', side_effect=read), patch('builtins.print'):
            with self.assertRaisesRegex(ValueError, 'Baseline report changed'):
                runner.generate(path, policies, allow_training=True)
        self.assertEqual(len(calls), 1)
        self.assertFalse(path.exists())
        self.assertEqual(sibling.read_bytes(), b'keep')
        self.assertEqual(list(policies.iterdir()), [sibling])

    def test_staged_and_published_rejection_removes_only_own_new_files(self):
        def oracle(policy, case):
            # Rollback-only placeholders; no mathematical/quality evidence.
            return {**{k: policy[k] for k in runner.METRICS}, 'worlds': 176,
                    'compatible_pair_count': 4, 'checked_information_sets': 2404,
                    'public_node_count': 1254}

        for phase in ('stage', 'published'):
            with self.subTest(phase=phase):
                path = self.directory / ('rollback-' + phase + '.json')
                policies = self.directory / ('rollback-' + phase)
                policies.mkdir()
                sibling = policies / 'unrelated.txt'
                sibling.write_bytes(b'keep')
                checks = [ValueError('staged rejection')] if phase == 'stage' else [
                    {'status': 'staged'}, ValueError('published rejection')]
                with patch.object(runner, 'fingerprints', return_value=self.sources), \
                        patch.object(runner, '_head', return_value='a' * 40), \
                        patch.object(runner, 'capture', side_effect=self.snapshots), \
                        patch.object(runner, '_independent_oracle', side_effect=oracle), \
                        patch.object(runner, '_verify_saved', side_effect=checks), patch('builtins.print'):
                    with self.assertRaisesRegex(ValueError, 'rejection'):
                        runner.generate(path, policies, allow_training=True)
                self.assertFalse(path.exists())
                self.assertEqual(list(policies.iterdir()), [sibling])
                self.assertEqual(sibling.read_bytes(), b'keep')
                self.assertFalse(list(self.directory.glob('.' + path.name + '*.candidate')))


if __name__ == '__main__':
    unittest.main()
