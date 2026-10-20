"""Reconstruct every published policy and reject re-signed evidence tampering."""
from contextlib import ExitStack
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from scripts import verify_weighted_flop_publication as publication
from scripts import benchmark_weighted_full_deck_flop as experiment
from scripts.benchmark_preflop_covered_counts import canonical

TEMP_ROOT = publication.experiment.ROOT / '.test_tmp'


def local_temp():
    TEMP_ROOT.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(dir=TEMP_ROOT)


def replace_payload(directory, record, payload):
    raw = canonical(payload); compressed = gzip.compress(raw,mtime=0)
    (directory/record['file']).write_bytes(compressed)
    record.update(raw_bytes=len(raw),gzip_bytes=len(compressed),
                  payload_sha256=hashlib.sha256(raw).hexdigest(),
                  gzip_sha256=hashlib.sha256(compressed).hexdigest())


class WeightedFlopPublicationTests(unittest.TestCase):
    def test_every_saved_policy_replays_without_production_training_or_ranking(self):
        with ExitStack() as stack:
            for name in ('solve_postflop','rank_hand','_enumerate_worlds','train','train_plus',
                         'train_planned','train_public_batched','evaluate','best_response'):
                stack.enter_context(patch.object(experiment.production,name,
                                    side_effect=AssertionError('Production authority called: '+name)))
            verified=publication.verify_saved()
        self.assertEqual(verified['policies_replayed'],38)
        self.assertEqual(verified['worlds_reenumerated'],5940)
        self.assertEqual(verified['source_files'],584)
        self.assertFalse(verified['quality_gate_met'])
        self.assertTrue(verified['independent_validation_passed'])

    def test_immutable_quality_and_source_observations_cannot_be_resigned(self):
        original=json.loads((publication.PUBLICATION/'index.json').read_bytes())
        self.assertEqual(original['status'],'quality-miss')
        self.assertEqual(len(original['samples']),36)
        self.assertEqual(len(original['separate_allocation_calls']),2)
        self.assertEqual(len(original['final_quality']),4)
        self.assertTrue(all(row['target']==.005 and not row['met'] for row in original['final_quality']))
        with self.assertRaisesRegex(ValueError,'target remains unmet'):
            publication.verify_saved(require_quality=True)
        for change in ('source','gate','quality'):
            altered=deepcopy(original)
            if change=='source':
                altered['source_before']['revision']='0'*40
                altered['source_after']=deepcopy(altered['source_before'])
            elif change=='gate':
                altered['specification']['acceptance']['final_nash_conv_chip_limit']=1.0
            else:
                altered['quality_gate_met']=True;altered['status']='passed'
            with local_temp() as temp:
                directory=Path(temp)
                experiment._write_index(directory,altered)
                with self.subTest(change=change),self.assertRaisesRegex(ValueError,'Immutable published index'):
                    publication.verify_saved(directory)

    def test_resigned_physical_sign_and_action_amount_fail_independent_reconstruction(self):
        for change in ('physical-sign','action-amount'):
            with local_temp() as temp:
                directory=Path(temp)/'evidence'
                if TEMP_ROOT.resolve() not in directory.resolve().parents:
                    raise ValueError('Test evidence directory escaped workspace')
                shutil.copytree(publication.PUBLICATION,directory)
                index=json.loads((directory/'index.json').read_bytes())
                if change=='physical-sign':
                    record=index['production_physical_evidence']
                    payload=experiment.read_payload(directory,record)
                    row=payload['production_rows'][0];row[3]=1 if row[3]!=1 else -1
                    message='physical sign'
                else:
                    record=index['samples'][0]
                    payload=experiment.read_payload(directory,record)
                    payload['strategy'][0]['actions'][0]['amount']+=.125
                    message='action amount'
                replace_payload(directory,record,payload)
                experiment._write_index(directory,index)
                with self.subTest(change=change),self.assertRaisesRegex(ValueError,message):
                    experiment.verify_saved(directory)


if __name__=='__main__':
    unittest.main()
