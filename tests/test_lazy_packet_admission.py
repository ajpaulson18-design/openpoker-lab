"""Changed pooled evidence must refuse before any mathematical imports."""
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'benchmarks/results/lazy-joint-foundation-v1'
CHILD = '''
import importlib.abc, runpy, sys
class NoNumerics(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'tests' or fullname.startswith('tests.') or fullname.startswith('pokerlab'):
            raise RuntimeError('UNAUTHENTICATED_LAZY_NUMERICS:' + fullname)
sys.meta_path.insert(0, NoNumerics())
sys.argv = ['scripts.replay_lazy_joint_packet', sys.argv[1]]
runpy.run_module('scripts.replay_lazy_joint_packet', run_name='__main__')
'''


class LazyPacketAdmissionTests(unittest.TestCase):
    def refuses(self, member):
        with TemporaryDirectory(prefix='lazy-packet-negative-', dir=ROOT.parent) as directory:
            root = Path(directory); packet = root / 'packet'; packet.mkdir()
            for original in PACKET.iterdir():
                self.assertTrue(original.is_file()); shutil.copyfile(original, packet / original.name)
            changed = packet / member; raw = bytearray(changed.read_bytes()); raw[0] ^= 1; changed.write_bytes(raw)
            for optimized in (False, True):
                result = subprocess.run([sys.executable, *(['-O'] if optimized else []), '-B', '-X',
                    'pycache_prefix=' + str(root / ('optimized-cache' if optimized else 'normal-cache')),
                    '-c', CHILD, str(packet)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
                self.assertEqual(result.returncode, 1); self.assertEqual(result.stdout, b'')
                self.assertIn(('lazy literal packet pin: ' + member).encode(), result.stderr)
                self.assertNotIn(b'UNAUTHENTICATED_LAZY_NUMERICS', result.stderr)

    def test_changed_manifest_refuses_before_numerics(self):
        self.refuses('manifest.json')

    def test_changed_pooled_objects_refuse_before_numerics(self):
        self.refuses('objects.zip')


if __name__ == '__main__':
    unittest.main()
