"""Replay actual published trained policies against the separate exact proof."""
import hashlib
import json
from pathlib import Path
import unittest
from scripts import benchmark_preflop_exact_anchor as runner

ROOT = Path(__file__).resolve().parents[1]

class ExactAnchorPublicationTests(unittest.TestCase):
    def test_actual_saved_report_reconstructs_every_policy_and_comparison(self):
        path = ROOT / 'benchmarks/results/preflop-exact-anchor-v1.json'
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '465f9cac5aeddcd911bc97f84a30d4baaa41b82ff515bc238788f56bb4e2828e')
        data = json.loads(raw)
        self.assertEqual(data['artifact_sha256'],
                         '0b6076e0f6248810c3fc2b3348d912c4fd92f14cd8b584a0805f493a7b6d6d8f')
        self.assertEqual(data['source_before']['revision'],
                         'a818a0658eca7dbee9029967b81d66eed2e7e381')
        self.assertEqual(data['status'], 'passed')
        self.assertEqual(data['errors'], [])
        fresh = runner._verify_serialized_report(path)
        fresh.pop('serialized_artifact_sha256')
        self.assertEqual(fresh, data['final_serialized_verification'])
        self.assertEqual(fresh['reopened_payloads_replayed'], 38)
        self.assertEqual(fresh['fresh_comparisons_checked'], 19)
        for profile in data['profiles']:
            if profile['iterations'] < 8000:
                self.assertTrue(all(v is None for v in profile['median_complete_seconds'].values()))
        first = data['profiles'][0]
        self.assertFalse(any(first['quality_passed_by_backend'].values()))

if __name__ == '__main__':
    unittest.main()
