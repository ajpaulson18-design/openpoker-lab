"""Corrupt published evidence must fail before any numerical module imports."""
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'benchmarks/results/joint-two-epoch-v1'
CHILD = '''
import importlib.abc, runpy, sys
class NoNumerics(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'tests' or fullname.startswith('tests.') or fullname == 'pokerlab' or fullname.startswith('pokerlab.') or fullname == 'scripts.replay_joint_two_epoch':
            raise RuntimeError('UNAUTHENTICATED_NUMERIC_IMPORT:' + fullname)
sys.meta_path.insert(0, NoNumerics())
sys.argv = ['scripts.replay_joint_two_epoch_packet', sys.argv[1]]
runpy.run_module('scripts.replay_joint_two_epoch_packet', run_name='__main__')
'''


class JointPacketAdmissionTests(unittest.TestCase):
    def rejected_before_numerics(self, member):
        with TemporaryDirectory(prefix='joint-packet-negative-', dir=ROOT.parent) as temporary:
            work = Path(temporary).resolve()
            self.assertEqual(work.parent, ROOT.parent.resolve())
            packet = work / 'packet'; packet.mkdir()
            for path in PACKET.iterdir():
                self.assertTrue(path.is_file())
                # Independent files: mutating a hard link would corrupt the
                # original immutable evidence and is deliberately avoided.
                shutil.copyfile(path, packet / path.name)
            target = packet / member
            raw = bytearray(target.read_bytes()); raw[0] ^= 1; target.write_bytes(raw)
            for optimized in (False, True):
                args = [sys.executable, *(['-O'] if optimized else []), '-B', '-X',
                        'pycache_prefix=' + str(work / ('optimized-cache' if optimized else 'normal-cache')),
                        '-c', CHILD, str(packet)]
                result = subprocess.run(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        timeout=30, check=False)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b'')
                self.assertIn(('literal packet file pin: ' + member).encode(), result.stderr)
                self.assertNotIn(b'UNAUTHENTICATED_NUMERIC_IMPORT', result.stderr)
            self.assertNotEqual(target.read_bytes(), (PACKET / member).read_bytes())

    def test_changed_manifest_rejects_before_numerics(self):
        self.rejected_before_numerics('manifest.json')

    def test_changed_archive_rejects_before_numerics(self):
        self.rejected_before_numerics('normal.zip')


if __name__ == '__main__':
    unittest.main()
