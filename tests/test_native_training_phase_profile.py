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
            observed = run_bounded_child([str(exe)], b'', Path(directory), stdout_limit=128*1024)
            self.assertEqual(observed['status'], 'exited')
            self.assertEqual(observed['returncode'], 0)
            self.assertEqual((Path(directory)/'stderr.bin').read_bytes(), b'')
            lines = (Path(directory)/'stdout.bin').read_text(encoding='ascii').splitlines()
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

if __name__ == '__main__':
    unittest.main()
