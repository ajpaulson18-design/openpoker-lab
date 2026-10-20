"""Frozen benchmark rejection, source binding and wire/complete parity gates."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from scripts import benchmark_native_cfrplus_rematch as bench


class RematchBenchmarkBoundaryTests(unittest.TestCase):
    def test_dirty_source_refuses_before_admission_or_any_build_lookup(self):
        state = {'revision': 'dirty', 'status': [' M source'], 'source_hashes': {}}
        with patch.object(bench, 'snapshot', return_value=state), \
             patch.object(bench.cold, 'preflights') as preflight, \
             patch.object(bench, 'builds') as builds:
            report = bench.run('missing', 'missing', 'missing')
        self.assertEqual(report['status'], 'error')
        preflight.assert_not_called()
        builds.assert_not_called()
        self.assertEqual(report['fixtures'], [])

    def test_alternating_pairs_require_exact_wire_and_complete_payload(self):
        spec, _ = bench.load_spec()
        order = ['baseline', 'optimized', 'optimized', 'baseline', 'baseline', 'optimized']
        rows = [{'backend': lane, 'elapsed_seconds': 1.0 if lane == 'baseline' else .9,
                 'payload': {'strategy': [0.5, 0.5],
                             'native_training': {'build': {'lane': lane}, 'output_sha256': 'same'}}}
                for lane in order]
        result = bench.summarize(rows, spec, True)
        self.assertGreater(result['observed_ratio'], 1.02)
        tampered = deepcopy(rows); tampered[-1]['payload']['strategy'] = [.6, .4]
        with self.assertRaisesRegex(ValueError, 'payloads differ'):
            bench.summarize(tampered, spec, True)
        with self.assertRaisesRegex(ValueError, 'Missing paired'):
            bench.summarize(rows[:-1], spec, True)
        reversed_rows = list(reversed(rows))
        with self.assertRaisesRegex(ValueError, 'pair order'):
            bench.summarize(reversed_rows, spec, True)
        slow = deepcopy(rows)
        for row in slow:
            row['elapsed_seconds'] = 1.0
        with self.assertRaisesRegex(ValueError, 'improvement gate missed'):
            bench.summarize(slow, spec, True)


if __name__ == '__main__':
    unittest.main()
