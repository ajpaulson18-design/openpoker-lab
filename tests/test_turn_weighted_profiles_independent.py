"""Independent production-policy arithmetic and source/head boundaries."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import verify_turn_weighted_profiles_independent as check
ROOT=Path(__file__).resolve().parents[1]
class IndependentProfilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.valid=check.reconstruct()
    def test_six_exact_profiles_and_original_threshold_decisions(self):
        self.assertEqual(len(self.valid['results']),6)
        self.assertEqual(sum(row['target_met'] for row in self.valid['results']),2)
        self.assertTrue(all(row['known_value']=='30' and row['max_exact_vs_float_delta']<=1e-9 for row in self.valid['results']))
    def test_reconstruction_does_not_use_exact_policy_evaluator(self):
        with patch('scripts.turn_rational_certificate.evaluate_exact',side_effect=AssertionError('Exact evaluator must not run')):
            self.assertEqual(check.reconstruct(),self.valid)
    def test_forged_metric_rejected_after_valid_positive_proof(self):
        report=json.loads((ROOT/'benchmarks/results/turn-weighted-cfrplus-profiles-v1.json').read_bytes())
        report['results'][0]['exact']['metrics']['value_oop']='0'
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            target=Path(folder)/'forged.json'
            target.write_text(json.dumps(report),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Independent exact metric differs'):check.reconstruct(target)
    def test_current_head_drift_rejects(self):
        with patch.object(check.subprocess,'check_output',side_effect=['a'*40+'\n','b'*40+'\n']):
            with self.assertRaisesRegex(ValueError,'HEAD changed'):check.reconstruct()
if __name__=='__main__':unittest.main()
