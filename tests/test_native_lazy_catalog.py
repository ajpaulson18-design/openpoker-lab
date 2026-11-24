"""Source-frozen opt-in Catalog controls with independent complete-frame replay."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from scripts.replay_native_frozen_policy_state import ORACLE_SOURCES
from tests.test_native_exact_reach import authenticate
from tests.virtual_frozen_run_control import run_bounded_child
from tests.virtual_lazy_catalog_reference import parse

ROOT = Path(__file__).resolve().parents[1]
ENV = 'OPENPOKER_NATIVE_LAZY_CATALOG_EXE'
OUT = 'OPENPOKER_NATIVE_LAZY_CATALOG_DIR'
TARGET = 'virtual-lazy-catalog-controls'


@unittest.skipUnless(os.environ.get(ENV), 'explicit source-built lazy Catalog candidate required')
class NativeLazyCatalogTests(unittest.TestCase):
    def test_complete_frame_source_and_real_process(self):
        executable = Path(os.environ[ENV]).resolve(); identity = authenticate(executable, ROOT, TARGET)
        names = sorted({*identity[1]['source_sha256'], *ORACLE_SOURCES,
                        'tests/virtual_strategy_catalog_reference.py', 'tests/virtual_lazy_catalog_reference.py',
                        'tests/test_native_lazy_catalog.py', 'tests/test_lazy_catalog_reference.py'})
        self.assertLessEqual(len(names), 128)
        self.assertEqual(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all', '--', *names], cwd=ROOT), b'')
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        source = {name: (ROOT / name).read_bytes() for name in names}
        tree = {line.split('\t', 1)[1]: line.split('\t', 1)[0].split()[2]
                for line in subprocess.check_output(['git', 'ls-tree', '-r', head], cwd=ROOT, text=True).splitlines()}
        output = Path(os.environ[OUT]).resolve(); self.assertEqual(output.parent, ROOT.parent.resolve()); output.mkdir(exist_ok=False)
        for name, raw in source.items():
            path = output / 'source' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        (output / 'source-identity.json').write_text(json.dumps({'head': head, 'python_version': sys.version,
            'raw_sha256': {name: sha256(raw).hexdigest() for name, raw in source.items()},
            'committed_blobs': {name: tree[name] for name in names}}, indent=2) + '\n')
        (output / 'native-build-manifest.json').write_bytes(identity[0])
        result = run_bounded_child([str(executable)], b'', output / 'native', stdout_limit=65536, timeout=180)
        self.assertEqual((result['status'], result['actual_exit_observed'], result['returncode'], result['failures']),
                         ('exited', True, 0, []))
        self.assertEqual((output / 'native/stderr.bin').read_bytes(), b'')
        raw = (output / 'native/stdout.bin').read_bytes(); report = parse(raw)
        (output / 'independent-replay.json').write_text(json.dumps(report, indent=2) + '\n')
        for corrupt in (raw[:-1], raw + b'EXTRA\n', raw.replace(b'SPARSE 32 32 0 ', b'SPARSE 32 32 1 ', 1),
                        raw.replace(b'IDS 1326 1325 ', b'IDS 1326 1324 ', 1)):
            self.assertNotEqual(corrupt, raw)
            with self.assertRaises(ValueError):
                parse(corrupt)
        self.assertEqual(authenticate(executable, ROOT, TARGET), identity)
        self.assertEqual(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), head)
        self.assertTrue(all((ROOT / name).read_bytes() == before for name, before in source.items()))
        (output / 'result.json').write_text(json.dumps({'status': 'lazy-catalog-component-exact',
            'observed_native_calls': 1, 'original_catalog_guards': 13, 'new_typed_guards': 8,
            'corruption_controls': 4, 'quality_gate': None, 'scope': report['scope']}, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
