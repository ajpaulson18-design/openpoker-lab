"""Cross-check the literal replay against the accepted frozen q-free oracle."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from tests.virtual_dyadic_training_reference import D, Q, Fixture
from tests.virtual_frozen_reference_artifact import artifact_allowance, read_reference
from tests.virtual_frozen_update_reference import scaled_proof9_ranges


ROOT = Path(__file__).resolve().parents[1]


class IndependentDyadicTrainingReferenceTests(unittest.TestCase):
    def test_exact_first_sweep_matches_accepted_frozen_profile(self):
        directory=ROOT/'benchmarks/results/virtual-frozen-complete-v1'
        manifest=json.loads((directory/'manifest.json').read_bytes())
        archive=next(x for x in manifest['archives'] if x['path']=='producer.zip')
        path=directory/archive['path']
        self.assertEqual(path.stat().st_size,archive['bytes'])
        self.assertLess(path.stat().st_size,10<<20)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),archive['sha256'])
        with ZipFile(path) as zipped, TemporaryDirectory(prefix='opl-dyadic-oracle-') as temp:
            member=zipped.getinfo('study/expected.jsonl')
            self.assertEqual(member.file_size,5_470_756)
            raw=zipped.read(member)
            file=Path(temp)/'expected.jsonl';file.write_bytes(raw)
            frozen=read_reference(file,byte_limit=artifact_allowance('expected',24420,58164)['bytes'])
        self.assertEqual(frozen.receipt['body_sha256'],'2152c9136aef5b4d84a1d1559b3168968425c95bdd5203148ddc941a66e49ebd')
        fixture=Fixture()
        self.assertEqual(fixture.terminal_completion_counts(),(18180,22168))
        ranges=scaled_proof9_ranges()
        index=[{hand:i for i,(hand,_) in enumerate(side)} for side in ranges]
        rows={(row.actor,index[row.actor][row.hand_ids],row.history):row for row in frozen.rows.values()}
        self.assertEqual(rows.keys(),fixture.menus.keys())
        policy={}
        for key,row in rows.items():
            self.assertEqual(row.actions,fixture.menus[key])
            policy[key]=tuple(0 if e==-1 else Q>>e for e in row.action_exponents)
        regrets,averages,root=fixture.sweep(policy)
        self.assertTrue(any(v for row in regrets.values() for v in row))
        for key,row in rows.items():
            r=tuple(max(0,value)*D for value in row.regret_masses)
            a=tuple(value*D for value in row.average_action_masses)
            self.assertEqual(regrets[key],r,key)
            self.assertEqual(averages[key],a,key)
        quality=fixture.quality(policy)
        self.assertEqual(quality['profile_sb'],root)
        self.assertGreater(quality['exploitability'],0)


if __name__=='__main__':
    unittest.main()
