"""Actual physical covered-count report is independently replayed after saving."""
import hashlib
import json
from pathlib import Path
import unittest
from scripts.benchmark_preflop_covered_counts import verify_saved
ROOT=Path(__file__).resolve().parents[1]

class CoveredPublicationTests(unittest.TestCase):
    def test_actual_physical_report_replays_all_policies_and_preserves_miss(self):
        path=ROOT/'benchmarks/results/preflop-covered-counts-v1.json';raw=path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '0f436faa5c7909617db2ead4ec39a23fafe1876ae56c6365f37283af0489eaf6')
        data=json.loads(raw)
        self.assertEqual(data['status'],'passed');self.assertEqual(data['errors'],[])
        self.assertEqual(data['artifact_sha256'],'a0a8644de32cead9f081c88ae50e980bc958bc4b611f175b887676b4463984eb')
        self.assertEqual(data['source_before']['revision'],'e5dea4ea0193b682bb856c9b3eb7df9f3a53891c')
        self.assertEqual(verify_saved(path),data['saved_verification'])
        self.assertEqual(data['saved_verification']['replayed_payloads'],12)
        self.assertEqual(data['saved_verification']['paired_comparisons'],6)
        self.assertTrue(all(not x['assessment']['quality_pass'] for x in data['profiles'][0]['samples']))
        self.assertEqual(data['table_budget']['compatible_pairs'],6)
        self.assertEqual(data['table_budget']['physical_worlds_upper_bound'],10273824)
        self.assertTrue(all(x['assessment']['quality_pass'] for x in data['profiles'][-1]['samples']))
