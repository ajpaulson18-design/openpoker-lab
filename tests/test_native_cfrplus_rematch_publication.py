"""Immutable complete-call evidence and re-signed tampering regressions."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from scripts import benchmark_native_cfrplus_rematch as bench

PATH = bench.ROOT / 'benchmarks/results/native-cfrplus-rematch-v1.json'


def resign(report):
    report.pop('artifact_sha256', None)
    report['artifact_sha256'] = bench.checksum(report)
    return report


class RematchPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = PATH.read_bytes()
        cls.report = json.loads(cls.raw)

    def test_frozen_raw_artifact_replays_all_28_policies(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(),
                         '12153fe30518badc681a5bcd7e9061a0630caec6a40f538f64ba1c3323f6dc1d')
        self.assertEqual(self.report['artifact_sha256'],
                         '653ef0b66dc58d318814a8337837823f70645f9d929599f71a53ba50ab18d241')
        self.assertEqual(self.report['source_before']['revision'],
                         'ecf0a49ac88b333a1320e5de6e498f4047f1b72a')
        self.assertEqual(len(self.report['source_before']['source_hashes']), 578)
        self.assertEqual(bench.verify_saved(self.report), {'policies_replayed': 28, 'passed': True})

    def test_resigned_baseline_count_source_and_compiler_changes_reject(self):
        for lane, field, message in (
                ('baseline', 'source_lf_sha256', 'pinned Git source'),
                ('baseline', 'compiler_version', 'compiler/protocol'),
                ('counts', 'source_sha256', 'Count source/build')):
            report = deepcopy(self.report)
            for stage in ('builds_before', 'builds_after'):
                report[stage][lane]['manifest'][field] = 'changed'
            with self.subTest(lane=lane, field=field), self.assertRaisesRegex(ValueError, message):
                bench.verify_saved(resign(report))

    def test_resigned_cold_counter_and_policy_wire_changes_reject(self):
        report = deepcopy(self.report)
        sample = report['fixtures'][0]['profiles'][0]['samples'][0]
        sample['payload']['equity_preparation']['native_preparation']['response']['rank_calls'] += 2
        sample['payload_sha256'] = hashlib.sha256(bench.canonical(sample['payload'])).hexdigest()
        with self.assertRaises(ValueError):
            bench.verify_saved(resign(report))
        report = deepcopy(self.report)
        sample = report['fixtures'][0]['profiles'][0]['samples'][0]
        sample['payload']['native_training']['output_sha256'] = 'changed'
        sample['payload_sha256'] = hashlib.sha256(bench.canonical(sample['payload'])).hexdigest()
        with self.assertRaisesRegex(ValueError, 'payloads differ|wire differs'):
            bench.verify_saved(resign(report))


if __name__ == '__main__':
    unittest.main()
