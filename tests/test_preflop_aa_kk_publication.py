"""Actual full physical AA/KK policy evidence is freshly replayed."""
import hashlib
import json
from pathlib import Path
import unittest
from scripts.benchmark_preflop_aa_kk_range import verify_saved
ROOT=Path(__file__).resolve().parents[1]

class PhysicalRangePublicationTests(unittest.TestCase):
    def test_actual_report_replays_all_policies_against_one_chip_bounds(self):
        path=ROOT/'benchmarks/results/preflop-aa-kk-physical-range-v1.json';raw=path.read_bytes();data=json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'4708b767516847d0e95d99fb197cd6d66531485f28fdfc130f784afb49c56979')
        self.assertEqual(data['artifact_sha256'],'324e7b011e06c56ee6b7c9caf78e59e85ffa40fb0e3d9fa2c96974a5eeeccacd')
        self.assertEqual(data['source_before']['revision'],'d7b8883b1fa1b5f94ccb32dd5160ed073e609019')
        self.assertEqual(data['status'],'passed');self.assertEqual(data['errors'],[])
        self.assertEqual(verify_saved(path),data['saved_verification'])
        self.assertEqual(data['saved_verification']['replayed_physical_policies'],10)
        self.assertEqual(data['saved_verification']['paired_comparisons'],5)
        for row in data['profiles']:
            self.assertTrue(all(x['assessment']['exact_anchor_contained'] for x in row['samples']))

    def test_resigned_algorithm_relabeling_is_rejected(self):
        from copy import deepcopy
        import tempfile
        from scripts.benchmark_preflop_aa_kk_range import core
        data=json.loads((ROOT/'benchmarks/results/preflop-aa-kk-physical-range-v1.json').read_bytes())
        sample=data['profiles'][0]['samples'][0]
        sample['payload']['algorithm']='vanilla'
        encoded=core.canonical(sample['payload'])
        sample['payload_sha256']=hashlib.sha256(encoded).hexdigest()
        sample['serialized_bytes_utf8']=len(encoded)
        data.pop('artifact_sha256');data['artifact_sha256']=core.checksum(data)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'relabeled.json';path.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'policy/digest/replay/execution census'):
                verify_saved(path)
