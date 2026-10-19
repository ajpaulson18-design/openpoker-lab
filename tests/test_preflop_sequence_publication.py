"""Fresh reconstruction of the actual published preflop proof artifact."""
import json
from pathlib import Path
import unittest
from scripts.certify_preflop_sequence import checksum, EXPECTED_SPEC_SHA256
from scripts.preflop_sequence_pure_response import public_pure_response
from scripts.verify_preflop_sequence import verify_certificate

ROOT = Path(__file__).resolve().parents[1]


class PreflopSequencePublicationTests(unittest.TestCase):
    def test_saved_formal_report_reconstructs_every_independent_result(self):
        report = json.loads((ROOT / 'benchmarks/results/preflop-weighted-sequence-v1.json')
                            .read_text(encoding='utf-8'))
        unsigned = dict(report); unsigned.pop('artifact_sha256')
        self.assertEqual(checksum(unsigned), report['artifact_sha256'])
        self.assertEqual(report['artifact_sha256'],
                         '7bdffdf73df5950d73f9fab54e27b364babb4e00718249a44cafdf47c62415c6')
        self.assertEqual(report['phase'], 'formal-exact-equilibrium-witness')
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['errors'], [])
        self.assertTrue(report['formal_source_required'])
        self.assertEqual(report['spec_sha256'], EXPECTED_SPEC_SHA256)
        self.assertEqual(report['source_before']['revision'],
                         '3857eb7f5cd67040511715f53fb078ad629b9e20')
        self.assertEqual(report['source_before']['status'], [])
        self.assertEqual(report['source_before'], report['source_after'])
        self.assertTrue(report['source_unchanged'])
        self.assertFalse(any(report['guard_calls'].values()))
        witness = report['candidate_witness']
        fresh = verify_certificate(witness)
        self.assertEqual(fresh, report['independent_verification'])
        self.assertEqual(fresh, report['serialized_witness_verification'])
        self.assertEqual(public_pure_response(witness),
                         report['exhaustive_pure_response_verification'])
        self.assertEqual(fresh['nash_conv_fraction'], '0')
        self.assertEqual(fresh['bb_best_response_fraction'], '-' + fresh['value_sb_fraction'])


if __name__ == '__main__':
    unittest.main()
