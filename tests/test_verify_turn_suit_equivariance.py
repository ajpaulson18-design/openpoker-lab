"""Independent saved suit-study acceptance and adversarial publication boundaries."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import verify_turn_suit_equivariance as verify

class IndependentSuitStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch('scripts.turn_suit_transport.transform_result',side_effect=AssertionError('Candidate mapping called')),patch('scripts.turn_suit_transport.transform_rows',side_effect=AssertionError('Candidate rows called')),patch('scripts.turn_suit_validation._solve',side_effect=AssertionError('Trainer called')),patch('scripts.turn_rational_certificate.evaluate_exact',side_effect=AssertionError('Exact evaluator called')),patch('scripts.turn_sequence_compact_lp.solve_lp',side_effect=AssertionError('LP called')):
            cls.report=verify.verify_saved_artifact()

    def reject(self,change,before_proofs=False):
        report=copy.deepcopy(self.report);change(report)
        with tempfile.TemporaryDirectory(dir=verify.ROOT) as folder:
            target=Path(folder)/'mutated.json';target.write_bytes(verify.canonical(report))
            if before_proofs:
                with patch.object(verify,'exact_summaries',side_effect=AssertionError('Proof math ran')):
                    with self.assertRaises((ValueError,KeyError,TypeError,IndexError)):verify.verify_saved_artifact(target)
            else:
                # Positive full144-replay baseline was established above. These
                # cases exercise changed stored data without repeating that proof.
                with patch.object(verify,'reconstruct_archives',return_value=self.report['archive_transports']):
                    with self.assertRaises((ValueError,KeyError,TypeError,IndexError)):verify.verify_saved_artifact(target)

    def test_positive_all_fixed_cases_and_retained_quality_decisions(self):
        self.assertEqual(len(self.report['exact_reference_summary']),24)
        self.assertEqual(len(self.report['archive_transports']),144)
        self.assertEqual(len(self.report['fresh_results']),8)
        self.assertTrue(all(r['symmetry_met'] for r in self.report['fresh_results']))
        self.assertTrue(all(type(r['target_met']) is bool and r['threshold_miss'] is not r['target_met'] for r in self.report['fresh_results']))

    def test_schema_source_and_threshold_reject_before_proofs(self):
        self.reject(lambda r:r.update(symmetry_target_fraction='1/1000'),True)
        self.reject(lambda r:r.update(training_targets=['cdhs']),True)
        self.reject(lambda r:r.update(baseline_git_commit='malformed'),True)
        self.reject(lambda r:r['source_sha256'].update({'scripts/turn_suit_reference.py':'0'*64}),True)

    def test_negative_and_exact_reference_metadata_tampering(self):
        self.reject(lambda r:r['negative_control'].update(newly_compatible_aa_pair_mass='0'))
        self.reject(lambda r:r['exact_reference_summary'][0].update(river_decision_reach='0'))

    def test_archived_transport_digest_tampering(self):
        self.reject(lambda r:r['archive_transports'][0].update(transported_policy_sha256='0'*64))

    def test_forged_fresh_metric_normalization_and_symmetry_metadata(self):
        self.reject(lambda r:r['fresh_results'][0]['exact']['metrics'].update(value_oop='0'))
        self.reject(lambda r:r['fresh_results'][0]['exact']['normalization_ledger'][0].update(input_row_sum_fraction='999'))
        self.reject(lambda r:r['fresh_results'][0]['exact_metric_differences_vs_source'].update(value_oop='1'))
        self.reject(lambda r:r['fresh_results'][0].update(symmetry_met=False))

    def test_unsafe_policy_path_rejected_before_access(self):
        self.reject(lambda r:r['fresh_results'][0].update(policy_file='../outside.json'))

    def test_head_drift_rejects_after_valid_cached_proofs(self):
        with patch.object(verify,'current_head',side_effect=['a'*40,'b'*40]),patch.object(verify,'reconstruct_archives',return_value=self.report['archive_transports']):
            with self.assertRaisesRegex(ValueError,'HEAD drift'):verify.verify_saved_artifact()

    def test_oversized_input_rejected_before_read(self):
        with tempfile.TemporaryDirectory(dir=verify.ROOT) as folder:
            path=Path(folder)/'oversized.json';path.write_bytes(b' ' *2000001)
            with patch.object(Path,'read_bytes',side_effect=AssertionError('Oversized bytes read')):
                with self.assertRaisesRegex(ValueError,'File admission'):verify.read(path)

if __name__=='__main__':unittest.main()
