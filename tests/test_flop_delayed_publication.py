"""Immutable delayed-study authentication and independent corruption controls."""
from contextlib import ExitStack
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from scripts import verify_flop_delayed_publication as publication
from scripts import benchmark_flop_delayed_cfrplus as study
from tests.test_weighted_flop_publication import local_temp,replace_payload,TEMP_ROOT


class FlopDelayedPublicationTests(unittest.TestCase):
    def test_git_lf_attestation_matches_every_pinned_source_hash(self):
        # Authenticate the separately published receipt without requiring a
        # non-shallow Git history on CI. The actual Git comparison was executed
        # before publication; this checks its immutable bytes and complete map.
        path = publication.PUBLICATION.parent / (
            'weighted-full-deck-flop-delayed-cfrplus-v1-git-source.json')
        self.assertLessEqual(path.stat().st_size, 1024 * 1024)
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '837fd6d5326f670185d6de8609fc0d829260434592548391b47159975592b40d')
        receipt = json.loads(raw)
        report = json.loads((publication.PUBLICATION / 'index.json').read_bytes())
        expected = {name: row['lf_sha256'] for name, row in
                    report['source_before']['source_hashes'].items()}
        self.assertEqual(receipt['source_revision'], publication.SOURCE_REVISION)
        self.assertEqual(receipt['captured_files'], 602)
        self.assertEqual(receipt['matched_git_lf_files'], 602)
        self.assertEqual(receipt['mismatches'], [])
        self.assertEqual(receipt['git_lf_source_hashes'], expected)
        self.assertEqual(receipt['captured_source_hashes_sha256'],
                         publication.SOURCE_MANIFEST_SHA256)
        self.assertEqual(study.checksum(expected), receipt['git_lf_manifest_sha256'])

    def test_full_candidate_and_both_baselines_reconstruct_without_production_authority(self):
        with ExitStack() as stack:
            for name in ('solve_postflop','rank_hand','_enumerate_worlds','train','train_plus',
                         'train_planned','train_public_batched','evaluate','best_response'):
                stack.enter_context(patch.object(study.production,name,
                                    side_effect=AssertionError('Production authority called: '+name)))
            stack.enter_context(patch.object(study.delayed_kernel,'train_delayed_public_cfrplus',
                                side_effect=AssertionError('Production delayed trainer called')))
            checked=publication.verify_saved()
        self.assertEqual(checked['policies_replayed'],20)
        self.assertEqual(checked['worlds_reenumerated'],5940)
        self.assertEqual(checked['file_count'],23)
        self.assertEqual(checked['source_files'],602)
        self.assertTrue(checked['independent_validation_passed'])
        self.assertEqual(checked['quality_gate_met'],False)
        report=json.loads((publication.PUBLICATION/'index.json').read_bytes())
        self.assertEqual(report['baseline']['strict_verification']['policies_replayed'],20)
        self.assertFalse(report['baseline']['quality_gate_met'])
        self.assertEqual(len(report['final_quality']),6)
        self.assertTrue(all(row['target']==.005 and row['met']==(row['nash_conv']<=.005)
                            for row in report['final_quality']))

    def test_resigned_source_gate_status_and_control_receipt_reject(self):
        original=json.loads((publication.PUBLICATION/'index.json').read_bytes())
        self.assertEqual(len(original['samples']),18)
        self.assertEqual(len(original['separate_allocation_calls']),2)
        if not original['quality_gate_met']:
            with self.assertRaisesRegex(ValueError,'final quality target remains unmet'):
                publication.verify_saved(require_quality=True)
        for change in ('source','gate','quality','baseline'):
            altered=deepcopy(original)
            if change=='source':
                altered['source_before']['revision']='0'*40
                altered['source_after']=deepcopy(altered['source_before'])
            elif change=='gate':
                altered['specification']['acceptance']['final_nash_conv_chip_limit']=1.
            elif change=='quality':
                altered['quality_gate_met']=not original['quality_gate_met']
            else:
                altered['baseline']['publication_index_sha256']='0'*64
            with local_temp() as temp:
                directory=Path(temp);study._write_index(directory,altered)
                with self.subTest(change=change),self.assertRaisesRegex(ValueError,'Immutable published'):
                    publication.verify_saved(directory)

    def test_resigned_physical_sign_and_positive_delay_numeric_action_reject(self):
        for change in ('physical-sign','action-amount'):
            with local_temp() as temp:
                directory=Path(temp)/'evidence'
                if TEMP_ROOT.resolve() not in directory.resolve().parents:
                    raise ValueError('Publication test evidence escaped workspace')
                shutil.copytree(publication.PUBLICATION,directory)
                report=json.loads((directory/'index.json').read_bytes())
                baseline=deepcopy(report['baseline'])
                record=(report['production_physical_evidence'] if change=='physical-sign'
                        else next(row for row in report['samples'] if row['averaging_delay']>0))
                payload=study.base.read_payload(directory,record)
                if change=='physical-sign':
                    row=payload['production_rows'][0];row[3]=1 if row[3]!=1 else -1
                    message='physical sign'
                else:
                    payload['strategy'][0]['actions'][0]['amount']+=.125
                    message='action amount'
                replace_payload(directory,record,payload)
                study._write_index(directory,report)
                # Isolate candidate corruption; the positive test fully reconstructs
                # the real twenty-policy and original thirty-eight-policy baselines.
                with patch.object(study,'verify_baseline',return_value=baseline), \
                     self.subTest(change=change),self.assertRaisesRegex(ValueError,message):
                    study.verify_saved(directory,publication.study.baseline_publication.PUBLICATION)


if __name__=='__main__':
    unittest.main()
