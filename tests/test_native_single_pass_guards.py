"""Source-authenticated guards for one-read versus two-read epoch contracts."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import unittest

from tests.test_native_exact_reach import authenticate
from tests.virtual_frozen_run_control import run_bounded_child

ROOT = Path(__file__).resolve().parents[1]
ENV = 'OPENPOKER_NATIVE_SINGLE_PASS_EPOCH_EXE'
OUT = 'OPENPOKER_NATIVE_SINGLE_PASS_EPOCH_DIR'
TARGET = 'virtual-single-pass-epoch-controls'


@unittest.skipUnless(os.environ.get(ENV), 'explicit source-built single-pass epoch guard candidate required')
class NativeSinglePassGuardTests(unittest.TestCase):
    def test_read_arithmetic_owner_and_seal_contracts(self):
        executable = Path(os.environ[ENV]).resolve(); identity = authenticate(executable, ROOT, TARGET)
        names = sorted({*identity[1]['source_sha256'], 'tests/test_native_single_pass_guards.py',
                        'tests/test_native_exact_reach.py', 'tests/virtual_frozen_run_control.py'})
        self.assertEqual(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all', '--', *names], cwd=ROOT), b'')
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        source = {name: (ROOT / name).read_bytes() for name in names}
        output = Path(os.environ[OUT]).resolve(); self.assertEqual(output.parent, ROOT.parent.resolve()); output.mkdir(exist_ok=False)
        for name, raw in source.items():
            path = output / 'source' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        (output / 'source-identity.json').write_text(json.dumps({'head': head,
            'raw_sha256': {name: sha256(raw).hexdigest() for name, raw in source.items()}}, indent=2) + '\n')
        (output / 'native-build-manifest.json').write_bytes(identity[0])
        result = run_bounded_child([str(executable)], b'', output / 'native', stdout_limit=16384, timeout=180)
        self.assertEqual((result['status'], result['actual_exit_observed'], result['returncode'], result['failures']),
                         ('exited', True, 0, []))
        self.assertEqual((output / 'native/stderr.bin').read_bytes(), b'')
        lines = (output / 'native/stdout.bin').read_text().splitlines()
        expected = {'legacy-one-read', 'weighted-v1-one-read', 'single-mode-two-reads', 'zero-read-contract',
                    'duplicate-read', 'wrong-seal-read-count', 'abandoned-stage', 'old-mode-still-needs-two',
                    'unobserved-stage-row', 'public-proposal'}
        self.assertEqual(set(lines[:-1]), {'GUARD ' + label + ' PASS' for label in expected})
        self.assertEqual(len(lines), 11); self.assertEqual(lines[-1], 'SINGLE_PASS_EPOCH_GUARDS_V1 PASS 10 1')
        self.assertEqual(authenticate(executable, ROOT, TARGET), identity)
        self.assertEqual(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), head)
        self.assertTrue(all((ROOT / name).read_bytes() == raw for name, raw in source.items()))
        (output / 'result.json').write_text(json.dumps({'status': 'single-pass-read-contract-guards-exact',
            'guards': sorted(expected), 'valid_commits': 1, 'observed_native_calls': 1,
            'scope': 'Synthetic epoch ownership/read/seal guards only; no whole-game, speed or quality claim.'}, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
