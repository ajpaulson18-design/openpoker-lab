"""Fresh independent and native physical row agreement from the published basis."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts.benchmark_preflop_qq_kk_basis import verify_saved
from scripts.validate_preflop_five_reference import checksum
ROOT=Path(__file__).resolve().parents[1]

class QqKkPublicationTests(unittest.TestCase):
    def test_saved_raw_physical_basis_rechecks_and_resigned_count_tampering_rejects(self):
        path=ROOT/'benchmarks/results/preflop-qq-kk-basis-v1.json';raw=path.read_bytes();data=json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'44e750b135a97dc98dc8246c6c0881e5c775a697fdc9f4e1d803b995b6aa5118')
        self.assertEqual(data['artifact_sha256'],'d47fcbdca9cb84275adb8902636d8331bca8b6089e1d62e83cc2160ff09503b8')
        self.assertEqual(data['source_before']['revision'],'b37939b01c3cbfe1c22f2d39cc06207078aaddfb')
        self.assertEqual(verify_saved(path),data['saved_verification'])
        self.assertEqual(len(data['independent_physical_count_rows']),3)
        self.assertEqual(data['current_build_conformance']['five_card_exhaustive']['rank_tuples_checked'],2598960)
        self.assertEqual(data['current_build_conformance']['five_card_exhaustive']['mismatches_first_ten'],[])
        altered=deepcopy(data);altered['candidate_equity_table']['counts'][0]['wins']+=1
        altered.pop('artifact_sha256');altered['artifact_sha256']=checksum(altered)
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'altered.json';target.write_text(json.dumps(altered),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'counts disagree'):verify_saved(target)
