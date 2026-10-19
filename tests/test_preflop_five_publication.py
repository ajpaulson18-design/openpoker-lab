"""Fresh raw count comparison of the actual published exhaustive reference."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts.validate_preflop_five_reference import verify_saved,checksum
ROOT=Path(__file__).resolve().parents[1]

class FivePublicationTests(unittest.TestCase):
    def test_actual_saved_raw_censuses_reconstruct_agreement_and_tampering_rejects(self):
        path=ROOT/'benchmarks/results/preflop-five-basis-v1.json';raw=path.read_bytes();data=json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'bb906c0dac2deca79753e48548b5c3c1b7b9cedd92ba3574da934154713b5419')
        self.assertEqual(data['artifact_sha256'],'2ae377e0af6d55491c667d574f41482f2ea6911ba8565ade3b9c8406b54010f7')
        self.assertEqual(data['source_before']['revision'],'293e61357497f39ae02a8e0c3f75207f8e455eb7')
        self.assertEqual(verify_saved(path),data['saved_verification'])
        self.assertEqual(data['five_card_exhaustive']['mismatches_first_ten'],[])
        self.assertEqual(sum(data['five_card_exhaustive']['category_counts'].values()),2598960)
        with tempfile.TemporaryDirectory() as folder:
            changed=deepcopy(data);changed['candidate_equity_table']['counts'][0]['wins']+=1
            changed.pop('artifact_sha256');changed['artifact_sha256']=checksum(changed)
            forged=Path(folder)/'forged.json';forged.write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'counts disagree'):verify_saved(forged)
