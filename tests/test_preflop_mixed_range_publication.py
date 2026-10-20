"""Published mixed-range policies are replayed from independent physical rows."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts import benchmark_preflop_mixed_range as bench

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'benchmarks/results/preflop-mixed-physical-range-v1.json'

class MixedRangePublicationTests(unittest.TestCase):
    def test_actual_complete_report_replays_every_profile(self):
        raw=REPORT.read_bytes();data=json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'b9fa38e916d63fe1fadcc5fe8d466bde57ca56bde0581d867f9a75fc0e1f47a1')
        self.assertEqual(data['artifact_sha256'],'907bccab88fff5e58d41c404ecd20aa4fcd5a5e9dd70fe2cb10b571244210930')
        self.assertEqual(data['source_before']['revision'],'1af4c5610bc197f028e19e151b32f644ed95c363')
        self.assertEqual(bench.verify_saved(REPORT),data['saved_verification'])
        self.assertEqual(data['saved_verification']['replayed_physical_policies'],10)
        self.assertEqual(data['saved_verification']['paired_comparisons'],5)
        self.assertEqual(data['saved_verification']['constructive_value_interval_sb_fraction'],['1/2','1'])
        self.assertFalse(data['profiles'][0]['samples'][0]['assessment']['quality_pass'])
        self.assertTrue(all(s['assessment']['quality_pass'] for s in data['profiles'][-1]['samples']))
        self.assertTrue(all(s['assessment']['bracket_intersects_constructive_interval']
                            for row in data['profiles'] for s in row['samples']))
        self.assertEqual(len(data['trusted_physical_count_rows']),72)

    def assert_rejected(self,mutate,message):
        data=json.loads(REPORT.read_bytes());mutate(data)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'tampered.json';bench.save_report(path,data)
            with self.assertRaisesRegex(ValueError,message):bench.verify_saved(path)

    def test_resigned_algorithm_relabeling_is_rejected(self):
        def mutate(data):
            sample=data['profiles'][0]['samples'][0];sample['payload']['algorithm']='vanilla'
            encoded=bench.core.canonical(sample['payload']);sample['payload_sha256']=hashlib.sha256(encoded).hexdigest()
            sample['serialized_bytes_utf8']=len(encoded)
        self.assert_rejected(mutate,'policy/digest/replay/execution census')

    def test_resigned_physical_count_and_pair_census_tampering_is_rejected(self):
        def mutate(data):
            row=data['trusted_physical_count_rows'][0];row['wins']+=1;row['losses']-=1
        self.assert_rejected(mutate,'proof, physical provenance or preflight')
        self.assert_rejected(lambda d:d['table_budget'].__setitem__('physical_worlds_upper_bound',61642944),
                             'proof, physical provenance or preflight')
