"""Actual frozen cold-preparation records and strict saved metadata boundaries."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts import benchmark_native_flop_preparation as bench

REPORT=bench.ROOT/'benchmarks/results/native-flop-preparation-v1.json'
class NativeFlopPublicationTests(unittest.TestCase):
    def test_actual_frozen_report_replays_all_complete_policies(self):
        raw=REPORT.read_bytes();data=json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'9fee8bf0162d60e16f3f53a6ec93e585ea8b55cc8f271738961a92b834385dab')
        self.assertEqual(data['artifact_sha256'],'86d0215733529b20a174506ccd7ca41c78f4734d43aa49a48d0a07c8b31691b4')
        self.assertEqual(data['source_before']['revision'],'1cee10d63dc7abc39139d38fee7a23cdd1fe56c3')
        self.assertEqual(bench.verify_saved(REPORT),data['saved_verification'])
        self.assertEqual(data['saved_verification']['rechecked_raw_calls'],24)
        self.assertEqual(data['saved_verification']['replayed_complete_policies'],12)
        self.assertEqual(len(data['source_before']['source_hashes']),571)
        self.assertTrue(all(r['all_payloads_exactly_identical'] for c in data['fixtures'] for r in c['stages']))

    def resigned_rejected(self,mutate,message):
        data=json.loads(REPORT.read_bytes());mutate(data)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'tampered.json';bench.save(path,data)
            with self.assertRaisesRegex(ValueError,message):bench.verify_saved(path)

    def test_resigned_fresh_board_echo_or_rank_counter_is_rejected(self):
        self.resigned_rejected(lambda d:d['fresh_independent_count_checks'][0]['native_metadata']['response']['board'].__setitem__(0,1),
                               'metadata, echoes or execution census')
        self.resigned_rejected(lambda d:d['fresh_independent_count_checks'][0]['native_metadata']['response'].__setitem__('rank_calls',0),
                               'metadata, echoes or execution census')

    def test_resigned_native_identity_and_physical_table_tampering_is_rejected(self):
        self.resigned_rejected(lambda d:d['builds_before']['counts']['manifest'].__setitem__('source_lf_sha256','0'*64),
                               'source/build integrity')
        def mutate(data):
            sample=data['fixtures'][0]['stages'][0]['samples'][0]
            sample['table']['counts'][0][0]+=2;sample['table']['counts'][0][2]-=2
        self.resigned_rejected(mutate,'physical support or exact priors')
