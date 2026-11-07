from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
from types import SimpleNamespace as S
import hashlib,json,tempfile,unittest
from tests.test_virtual_frozen_update_comparison import reference
from tests.test_virtual_frozen_probe_protocol import fixture
from tests.virtual_frozen_update_comparison import compare_saved_update
from tests.virtual_frozen_reference_artifact import (
    write_reference,read_reference,artifact_allowance,MAX_LINE,SavedReferenceRow,
)

class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd().parent)
        self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def save(self):
        path=self.root/'reference.jsonl';result=write_reference(path,reference(),'sampled')
        return path,result
    def test_exact_roundtrip_can_feed_separate_comparator(self):
        path,receipt=self.save()
        loaded=read_reference(path,byte_limit=receipt['allowance']['bytes'])
        self.assertEqual(set(loaded.rows),set(reference().rows))
        restored=next(iter(loaded.rows.values()));original=next(iter(reference().rows.values()))
        for field in ('actor','hand_ids','history','actions','action_exponents','regret_masses','average_mass','average_action_masses'):
            self.assertEqual(getattr(restored,field),getattr(original,field))
        compare_saved_update(fixture(),loaded)
        self.assertLessEqual(receipt['bytes'],receipt['allowance']['bytes'])
    def test_boundary_width_and_expected_row_alias(self):
        ref=reference();old=next(iter(ref.rows.values()))
        huge=F((1<<4096)-1,(1<<4095)+1)
        row=SavedReferenceRow(old.actor,old.hand_ids,old.history,old.actions,
                              old.action_exponents,(huge,-huge),old.average_mass,old.average_action_masses)
        expected=S(rows={row.key:row})
        p=self.root/'expected.jsonl';r=write_reference(p,expected,'expected')
        loaded=read_reference(p,byte_limit=r['allowance']['bytes'])
        self.assertEqual(next(iter(loaded.rows.values())).regret_masses,(huge,-huge))
        self.assertEqual(next(iter(loaded.rows.values())).average_reach_mass,F(2,5))
        self.assertIsNone(loaded.admission)
    def test_checksum_truncation_and_trailing_bytes_reject(self):
        path,r=self.save();raw=path.read_bytes()
        lines=raw.splitlines(keepends=True)
        bad=lines[0]+lines[1].replace(b'"-1"',b'"-2"')+lines[2]
        self.assertNotEqual(raw,bad)
        for index,data in enumerate((bad,raw[:-1],raw+b'bad\n')):
            p=self.root/('bad'+str(index));p.write_bytes(data)
            with self.assertRaises(ValueError):read_reference(p,byte_limit=r['allowance']['bytes'])
    def test_numeric_width_and_nesting_fail_before_conversion(self):
        path,r=self.save();lines=path.read_bytes().splitlines(keepends=True)
        variants=[lines[0]+b'['*7+b']'*7+b'\n',
                  lines[0]+lines[1].replace(b'[0,',b'[999999999,',1),
                  lines[0]+lines[1].replace(b'"-1"',b'"'+b'f'*1025+b'"')]
        for index,data in enumerate(variants):
            p=self.root/('width'+str(index));p.write_bytes(data)
            with self.assertRaises(ValueError):read_reference(p,byte_limit=r['allowance']['bytes'])
    def test_reference_export_family_covers_all_declared_calls(self):
        from tests.virtual_frozen_reference_artifact import reference_study_allowance
        receipt=reference_study_allowance()
        self.assertEqual(receipt['all_reference_artifact_bytes_upper'],2*receipt['sampled_law_bytes_upper']+receipt['q_free_bytes_upper'])
        self.assertGreater(receipt['sampled_law_bytes_upper'],2520*8192)
        self.assertFalse(receipt['full_study_admission'])
    def test_no_overwrite_and_whole_artifact_admission(self):
        path,r=self.save();original=path.read_bytes()
        with self.assertRaises(FileExistsError):write_reference(path,reference(),'sampled')
        self.assertEqual(path.read_bytes(),original)
        p=self.root/'tiny'
        with self.assertRaisesRegex(ValueError,'admission'):write_reference(p,reference(),'sampled',byte_limit=1)
        self.assertFalse(p.exists())
        with self.assertRaisesRegex(ValueError,'admission'):read_reference(path,byte_limit=r['allowance']['bytes']-1)
    def test_resigned_wrong_value_is_not_mathematical_authority(self):
        path,r=self.save();lines=path.read_bytes().splitlines(keepends=True)
        row=json.loads(lines[1]);row[6]=['4','5']
        lines[1]=(json.dumps(row,separators=(',',':'))+'\n').encode()
        lines[2]=(json.dumps({'end':1,'body_sha256':hashlib.sha256(lines[0]+lines[1]).hexdigest()},separators=(',',':'))+'\n').encode()
        path.write_bytes(b''.join(lines))
        loaded=read_reference(path,byte_limit=r['allowance']['bytes'])
        with self.assertRaisesRegex(ValueError,'average mass'):compare_saved_update(fixture(),loaded)

if __name__ == '__main__':unittest.main()
