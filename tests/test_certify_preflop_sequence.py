"""Publication boundaries for the exact finite preflop proof runner."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from scripts import certify_preflop_sequence as runner

SPEC = json.loads(runner.SPEC_PATH.read_text(encoding='utf-8'))


def _identity(dirty=False):
    return {'revision': 'frozen-head', 'status': [' M file'] if dirty else [],
            'source_hashes': {'source.py': {'lf_sha256': 'pinned'}}}


class PreflopCertificatePublicationTests(unittest.TestCase):
    def test_frozen_spec_and_dirty_source_reject_before_search(self):
        altered = copy.deepcopy(SPEC)
        altered['fixture']['config']['max_raises'] = 2
        with self.assertRaises(ValueError):
            runner.validate_spec(altered)
        with patch.object(runner, '_snapshot', return_value=_identity(True)), \
                patch.object(runner, '_components', side_effect=AssertionError('search started')) as components:
            report = runner.run(SPEC)
        self.assertEqual(report['status'], 'error')
        self.assertIn('clean committed source', report['errors'][0]['error'])
        components.assert_not_called()

    def test_forbidden_production_calls_are_counted_and_references_restored(self):
        from pokerlab import cfr
        original = cfr.train
        def call_production(spec):
            cfr.train(None, None, None, None)
        candidate = SimpleNamespace(build_model=call_production, solve_model=Mock())
        with patch.object(runner, '_snapshot', return_value=_identity()), \
                patch.object(runner.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                patch.object(runner, '_components', return_value=(candidate, Mock())):
            report = runner.run(SPEC)
        self.assertEqual(report['status'], 'error')
        self.assertEqual(report['guard_calls']['production_train'], 1)
        candidate.solve_model.assert_not_called()
        self.assertIs(cfr.train, original)

    def test_serialized_witness_is_checked_fresh_and_failure_keeps_candidate(self):
        witness = {'status': 'exact-candidate-feasibility', 'raw_proof_data': ['1/2']}
        candidate = SimpleNamespace(build_model=Mock(return_value='bounded-model'),
                                    solve_model=Mock(return_value=witness))
        verifier = SimpleNamespace(verify_certificate=Mock(side_effect=[
            {'status': 'passed', 'value_fraction': '1/2'},
            ValueError('serialized witness differs')]))
        with patch.object(runner, '_snapshot', return_value=_identity()), \
                patch.object(runner.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                patch.object(runner, '_components', return_value=(candidate, verifier)):
            report = runner.run(SPEC)
        self.assertEqual(report['status'], 'error')
        self.assertIs(report['candidate_witness'], witness)
        self.assertEqual(verifier.verify_certificate.call_count, 2)
        first, second = [call.args[0] for call in verifier.verify_certificate.call_args_list]
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        unsigned = dict(report); unsigned.pop('artifact_sha256')
        self.assertEqual(report['artifact_sha256'], runner.checksum(unsigned))

    def test_existing_raw_observation_is_never_overwritten(self):
        parent = runner.ROOT.parent / 'testtemp-proof-publication'
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            path = Path(directory) / 'failed-observation.json'
            original = {'status': 'error', 'errors': ['raw failure']}
            runner._write(path, original)
            with self.assertRaises(FileExistsError):
                runner._write(path, {'status': 'passed'})
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), original)


if __name__ == '__main__':
    unittest.main()
