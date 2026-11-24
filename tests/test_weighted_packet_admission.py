"""Changed weighted evidence must refuse before numerical imports."""
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'benchmarks/results/weighted-joint-foundation-v1'
CHILD = '''
import importlib.abc, runpy, sys
class NoNumerics(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'tests' or fullname.startswith('tests.') or fullname.startswith('pokerlab'):
            raise RuntimeError('UNAUTHENTICATED_WEIGHTED_NUMERICS:' + fullname)
sys.meta_path.insert(0, NoNumerics())
sys.argv = ['scripts.replay_weighted_joint_packet', sys.argv[1]]
runpy.run_module('scripts.replay_weighted_joint_packet', run_name='__main__')
'''


class WeightedPacketAdmissionTests(unittest.TestCase):
    def refuses(self, member):
        with TemporaryDirectory(prefix='weighted-packet-negative-', dir=ROOT.parent) as directory:
            root = Path(directory); packet = root / 'packet'; packet.mkdir()
            for original in PACKET.iterdir():
                self.assertTrue(original.is_file())
                shutil.copyfile(original, packet / original.name)
            target = packet / member
            data = bytearray(target.read_bytes()); data[0] ^= 1; target.write_bytes(data)
            for optimized in (False, True):
                command = [sys.executable, *(['-O'] if optimized else []), '-B', '-X',
                           'pycache_prefix=' + str(root / ('optimized-cache' if optimized else 'normal-cache')),
                           '-c', CHILD, str(packet)]
                result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        timeout=30, check=False)
                self.assertEqual(result.returncode, 1); self.assertEqual(result.stdout, b'')
                self.assertIn(('weighted literal packet pin: ' + member).encode(), result.stderr)
                self.assertNotIn(b'UNAUTHENTICATED_WEIGHTED_NUMERICS', result.stderr)
            self.assertNotEqual(target.read_bytes(), (PACKET / member).read_bytes())

    def test_changed_manifest_rejects_before_numerics(self):
        self.refuses('manifest.json')

    def test_changed_primary_archive_rejects_before_numerics(self):
        self.refuses('whole-normal.zip')


if __name__ == '__main__':
    unittest.main()
