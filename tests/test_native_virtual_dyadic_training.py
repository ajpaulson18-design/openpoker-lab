"""Compiled rank-free admission and fail-closed controls; never launch TRAIN."""
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.run_virtual_dyadic_training_cohort import exact_json, validate_admission
from tests.test_native_exact_reach import authenticate, sha
from tests.virtual_frozen_run_control import run_bounded_child, run_bounded_dyadic_probe


ROOT=Path(__file__).resolve().parents[1]
ENV='OPENPOKER_NATIVE_VIRTUAL_DYADIC_TRAINING_EXE'


@unittest.skipUnless(os.environ.get(ENV),'explicit source-built PROOF9 T2 probe required')
class NativeDyadicAdmissionControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe=Path(os.environ[ENV]).resolve()
        cls.identity=authenticate(cls.exe,ROOT,'virtual-dyadic-training')
        directory=os.environ.get('OPENPOKER_NATIVE_VIRTUAL_DYADIC_TRAINING_CONTROL_DIR')
        if directory is None:
            temporary=TemporaryDirectory(dir=ROOT.parent)
            cls.addClassCleanup(temporary.cleanup)
            directory=temporary.name
        cls.output=Path(directory)

    @classmethod
    def tearDownClass(cls):
        if authenticate(cls.exe,ROOT,'virtual-dyadic-training')!=cls.identity:
            raise AssertionError('PROOF9 T2 source/build drift during controls')

    def observe(self,name,call):
        directory=self.output/name
        before=sha(self.exe)
        self.assertEqual(before,self.identity[1]['executable_sha256'])
        process=call(directory)
        after=sha(self.exe)
        (directory/'binary-identity.json').write_text(json.dumps({'before_sha256':before,'after_sha256':after,
            'manifest_sha256':hashlib.sha256(self.identity[0]).hexdigest()})+'\n')
        self.assertEqual(before,after)
        self.assertEqual((process['status'],process['actual_exit_observed'],process['automatic_retries']),('exited',True,0))
        return directory,process

    def test_admission_covers_all_in_hidden_payoffs_without_training(self):
        directory,process=self.observe('admit',lambda p:run_bounded_dyadic_probe([str(self.exe)],'ADMIT',p))
        self.assertEqual(process['returncode'],0,(directory/'stderr.bin').read_text())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        plan=validate_admission(exact_json((directory/'stdout.bin').read_bytes()))
        self.assertEqual(plan['training_invocations'],0)
        self.assertEqual(plan['rank_calls'],0)
        self.assertGreater(plan['showdown_contractions_per_pass'],plan['showdowns'])

    def test_foreign_unframed_and_multirecord_requests_fail_closed(self):
        for index,raw in enumerate((b'DYADIC_T2_V1 TRAIN 3\n',b'DYADIC_T2_V1 ADMIT\r\n',
                b'DYADIC_T2_V1 ADMIT',b'DYADIC_T2_V1 ADMIT\nDYADIC_T2_V1 TRAIN\n',b'x'*65+b'\n')):
            with self.subTest(raw=raw):
                directory,process=self.observe(f'reject-{index}',lambda p:run_bounded_child(
                    [str(self.exe)],raw,p,stdout_limit=65536))
                self.assertEqual(process['returncode'],2)
                self.assertEqual((directory/'stdout.bin').read_bytes(),b'')
                self.assertTrue((directory/'stderr.bin').read_bytes().startswith(b'DYADIC_T2_V1 ERROR '))


if __name__=='__main__':unittest.main()
