"""Replay the immutable CFR+ corpus and reject re-signed candidate observations."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from scripts import verify_flop_cfrplus_publication as publication
from scripts import benchmark_flop_cfrplus as experiment
from tests.test_weighted_flop_publication import local_temp,replace_payload,TEMP_ROOT


class FlopCFRPlusPublicationTests(unittest.TestCase):
    def test_all_twenty_policies_and_pinned_baseline_reconstruct_without_production_authority(self):
        with ExitStack() as stack:
            for name in ('solve_postflop','rank_hand','_enumerate_worlds','train','train_plus',
                         'train_planned','train_public_batched','evaluate','best_response'):
                stack.enter_context(patch.object(experiment.base.production,name,
                                    side_effect=AssertionError('Production authority called: '+name)))
            checked=publication.verify_saved()
        report=json.loads((publication.PUBLICATION/'index.json').read_bytes())
        self.assertEqual(report['baseline']['verification']['policies_replayed'],38)
        self.assertFalse(report['baseline']['quality_gate_met'])
        self.assertEqual(checked['policies_replayed'],20)
        self.assertEqual(checked['worlds_reenumerated'],5940)
        self.assertEqual(checked['source_files'],593)
        self.assertTrue(checked['independent_validation_passed'])
        self.assertEqual(checked['quality_gate_met'],False)

    def test_final_quality_and_source_record_cannot_be_resigned(self):
        original=json.loads((publication.PUBLICATION/'index.json').read_bytes())
        self.assertEqual(len(original['samples']),18)
        self.assertEqual(len(original['separate_allocation_calls']),2)
        self.assertEqual(len(original['final_quality']),2)
        self.assertTrue(all(row['target']==.005 and row['met']==(row['nash_conv']<=.005)
                            for row in original['final_quality']))
        self.assertEqual(original['quality_gate_met'],all(row['met'] for row in original['final_quality']))
        if not original['quality_gate_met']:
            with self.assertRaisesRegex(ValueError,'target remains unmet'):
                publication.verify_saved(require_quality=True)
        for change in ('source','gate','quality','baseline'):
            altered=deepcopy(original)
            if change=='source':
                altered['source_before']['revision']='0'*40
                altered['source_after']=deepcopy(altered['source_before'])
            elif change=='gate':
                altered['specification']['acceptance']['final_nash_conv_chip_limit']=1.0
            elif change=='baseline':
                altered['baseline']['index_raw_sha256']='0'*64
            else:
                altered['quality_gate_met']=not original['quality_gate_met']
            with local_temp() as temp:
                directory=Path(temp);experiment.base._write_index(directory,altered)
                with self.subTest(change=change),self.assertRaisesRegex(ValueError,r'Immutable published CFR\+ index'):
                    publication.verify_saved(directory)

    def test_resigned_candidate_signs_and_numeric_actions_reject(self):
        for change in ('physical-sign','action-amount','baseline-receipt'):
            with local_temp() as temp:
                directory=Path(temp)/'evidence'
                if TEMP_ROOT.resolve() not in directory.resolve().parents:
                    raise ValueError('Candidate test evidence escaped workspace')
                shutil.copytree(publication.PUBLICATION,directory)
                report=json.loads((directory/'index.json').read_bytes())
                accepted_baseline=deepcopy(report['baseline'])
                if change=='baseline-receipt':
                    report['baseline']['index_raw_sha256']='0'*64
                    message='completed baseline evidence changed'
                else:
                    record=report['production_physical_evidence'] if change=='physical-sign' else report['samples'][0]
                    payload=experiment.base.read_payload(directory,record)
                    if change=='physical-sign':
                        row=payload['production_rows'][0];row[3]=1 if row[3]!=1 else -1
                        message='physical sign'
                    else:
                        payload['strategy'][0]['actions'][0]['amount']+=.125
                        message='action amount'
                    replace_payload(directory,record,payload)
                experiment.base._write_index(directory,report)
                # Isolate candidate tamper paths; the positive integration above fully
                # reconstructs the real baseline and checks its immutable identity.
                with patch.object(experiment,'verify_baseline',return_value=accepted_baseline), \
                     self.subTest(change=change),self.assertRaisesRegex(ValueError,message):
                    experiment.verify_saved(directory,publication.baseline.PUBLICATION)


if __name__=='__main__':
    unittest.main()
