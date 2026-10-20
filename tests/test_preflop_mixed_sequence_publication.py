"""Published exact mixed-game proof is freshly checked without candidate search."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts import certify_preflop_mixed_sequence as formal

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'benchmarks/results/preflop-mixed-exact-witness-v1.json'
INITIAL=ROOT/'benchmarks/results/preflop-mixed-exact-witness-v1-initial.json'

class MixedSequencePublicationTests(unittest.TestCase):
    def test_actual_saved_certificate_proves_full_physical_mutual_responses(self):
        raw=REPORT.read_bytes();data=json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'1c5427b4cca145b4931913599ee244f044deac9fac5d0a94521902ec3371726f')
        self.assertEqual(data['artifact_sha256'],'ed3512d35f03e2e7ed9e7440b73923670ca2412779a3e2dee97e79ad478d1ebb')
        self.assertEqual(data['source_before']['revision'],'009e4626b9a365b330b1b36ec1ea113113c7c20a')
        checked=formal.verify_saved(REPORT)
        self.assertEqual(checked,data['saved_verification'])
        self.assertEqual(checked['profile_value_sb_fraction'],'61612/75655')
        self.assertEqual(checked['nash_conv_fraction'],'0')
        self.assertEqual(checked['pure_response_policies_enumerated'],{'sb':576,'bb':216,'total':792})
        self.assertTrue(checked['exact_mutual_response_verified'])
        self.assertEqual(checked['physical_pair_count'],72)
        self.assertEqual(checked['physical_board_count'],123285888)
        self.assertEqual(checked['sb_best_response_own_utility_fraction'],'61612/75655')
        self.assertEqual(checked['bb_best_response_own_utility_fraction'],'-61612/75655')
        illegal=checked['illegal_clairvoyant_control']
        self.assertGreater(Fraction(illegal['sb_own_utility_fraction']),Fraction(61612,75655))
        self.assertGreater(Fraction(illegal['bb_own_utility_fraction']),Fraction(-61612,75655))

    def test_initial_saved_summary_failure_is_preserved_without_relabeling(self):
        initial=json.loads(INITIAL.read_bytes());current=json.loads(REPORT.read_bytes())
        unsigned=dict(initial);digest=unsigned.pop('artifact_sha256')
        self.assertEqual(formal.checksum(unsigned),digest)
        self.assertEqual(initial['status'],'error')
        self.assertEqual(initial['errors'],[{'phase':'saved-verification',
                         'error':'ValueError: Saved mixed physical-response proof changed'}])
        self.assertEqual(initial['candidate_witness'],current['candidate_witness'])
        with self.assertRaisesRegex(ValueError,'passed status'):formal.verify_saved(INITIAL)

    def assert_resigned_rejected(self,mutate,message):
        data=json.loads(REPORT.read_bytes());mutate(data)
        candidate=data['candidate_witness'];candidate.pop('artifact_sha256',None)
        candidate['artifact_sha256']=formal.checksum(candidate)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'tampered.json';formal.save(path,data)
            with self.assertRaisesRegex(ValueError,message):formal.verify_saved(path)

    def test_resigned_false_value_and_declared_game_are_rejected(self):
        self.assert_resigned_rejected(lambda d:d['candidate_witness'].__setitem__('value_candidate_fraction','0'),
                                     'mutual-response certificate did not pass')
        self.assert_resigned_rejected(lambda d:d['candidate_witness'].__setitem__('physical_game_spec_sha256','0'*64),
                                     'specification identity')

    def test_resigned_missing_production_guard_cannot_pass(self):
        self.assert_resigned_rejected(lambda d:d['guard_calls'].pop('production_best_response'),
                                     'guard names changed')
