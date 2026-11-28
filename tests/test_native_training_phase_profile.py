"""Deterministic controls for the bounded native phase recorder."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from tests.test_native_exact_reach import authenticate, sha
from tests.virtual_frozen_run_control import run_bounded_child

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.environ.get('OPENPOKER_NATIVE_TRAINING_PHASE_PROFILE_EXE'),
                     'explicit source-built phase controls required')
class NativeTrainingPhaseProfileTests(unittest.TestCase):
    def test_deterministic_trace_and_guards(self):
        exe = Path(os.environ['OPENPOKER_NATIVE_TRAINING_PHASE_PROFILE_EXE']).resolve()
        identity = authenticate(exe, ROOT, 'training-phase-profile-controls')
        expected = identity[1]['executable_sha256']
        self.assertEqual(sha(exe), expected)
        with TemporaryDirectory() as directory:
            output=Path(directory)/'probe'
            observed = run_bounded_child([str(exe)], b'', output, stdout_limit=128*1024)
            self.assertEqual(observed['status'], 'exited')
            self.assertEqual(observed['returncode'], 0)
            self.assertEqual((output/'stderr.bin').read_bytes(), b'')
            lines = (output/'stdout.bin').read_text(encoding='ascii').splitlines()
        self.assertEqual(sha(exe), expected)
        self.assertEqual(authenticate(exe, ROOT, 'training-phase-profile-controls'), identity)
        names = ('plan_preflight', 'chance_setup', 'owners_setup', 'row_registration', 'freeze',
                 'prelude', 'policy_build', 'policy_emit', 'walk', 'commit', 'checkpoint',
                 'average_export', 'footer')
        expected_lines = [f'EVENT {2*i+j} {name} {edge} {i} {10*(2*i+j+1)}'
                          for i, name in enumerate(names) for j, edge in enumerate(('begin', 'end'))]
        self.assertEqual(lines, expected_lines + ['PROFILE_CONTROLS PASS'])
        self.assertTrue(observed['actual_exit_observed'])
        self.assertEqual(observed['automatic_retries'], 0)

@unittest.skipUnless(os.environ.get('OPENPOKER_NATIVE_VIRTUAL_DYADIC_TRAINING_PROFILE_EXE'),
                     'explicit diagnostic trainer build required')
class DiagnosticTrainingPhaseGuardTests(unittest.TestCase):
    def test_diagnostic_switch_rejects_other_requests_before_scratch(self):
        exe=Path(os.environ['OPENPOKER_NATIVE_VIRTUAL_DYADIC_TRAINING_PROFILE_EXE']).resolve()
        before=authenticate(exe,ROOT,'virtual-dyadic-training-profile')
        cases=(('ADMIT_TEN_BOUNDED_DIVISION','--profile-phases'),
               ('TRAIN_TEN_PAIR_COMPLEMENT','--profile-phases'),
               ('FORECAST_ELEVEN','--profile-phases'),
               ('TRAIN_TEN_BOUNDED_DIVISION','--profile-phases-extra'))
        with TemporaryDirectory(dir=ROOT.parent) as directory:
            folder=Path(directory)
            for index,(mode,flag) in enumerate(cases):
                with self.subTest(mode=mode,flag=flag):
                    scratch=folder/str(index)/'page-images'
                    output=folder/('probe-'+str(index))
                    observed=run_bounded_child([str(exe),str(scratch),flag],
                        ('DYADIC_T2_V1 '+mode+'\n').encode('ascii'),output,stdout_limit=4096,timeout=10)
                    self.assertEqual((observed['actual_exit_observed'],observed['returncode'],
                                      observed['automatic_retries']),(True,2,0))
                    self.assertEqual((output/'stdout.bin').read_bytes(),b'')
                    self.assertIn(b'fixed request scratch argument count',(output/'stderr.bin').read_bytes())
                    self.assertFalse(scratch.exists())
                    self.assertFalse((scratch.parent/'phase-profile.json').exists())
        self.assertEqual(authenticate(exe,ROOT,'virtual-dyadic-training-profile'),before)

if __name__ == '__main__':
    unittest.main()
