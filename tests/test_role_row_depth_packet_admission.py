"""Corrupted structural-carrier packets refuse before numerical imports."""
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from tests.test_joint_cycles_packet_admission import CHILD
from scripts.replay_role_row_depth import PACKET, same_derived_json_bytes

ROOT = Path(__file__).resolve().parents[1]


class RowDepthPacketAdmission(unittest.TestCase):
    def refuses(self, member):
        with TemporaryDirectory(prefix='row-depth-negative-', dir=ROOT.parent) as directory:
            root = Path(directory); packet = root/'packet'; packet.mkdir()
            for original in PACKET.iterdir(): shutil.copyfile(original, packet/original.name)
            path = packet/member; raw = bytearray(path.read_bytes()); raw[0] ^= 1; path.write_bytes(raw)
            child = CHILD.replace('scripts.replay_joint_cycles_packet', 'scripts.replay_role_row_depth')
            for optimized in (False, True):
                result = subprocess.run([sys.executable, *(['-O'] if optimized else []), '-B', '-X',
                    'pycache_prefix='+str(root/('optimized-cache' if optimized else 'normal-cache')),
                    '-c', child, str(packet)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
                self.assertEqual(result.returncode, 1); self.assertEqual(result.stdout, b'')
                self.assertIn(('joint CPU literal packet pin: '+member).encode(), result.stderr)
                self.assertNotIn(b'UNAUTHENTICATED_CPU_NUMERICS', result.stderr)
    def test_changed_manifest(self): self.refuses('manifest.json')
    def test_changed_objects(self): self.refuses('objects.zip')
    def test_platform_transport_preserves_exact_policy_bytes(self):
        lf = b'{\n  "regrets": [-17, 3],\n  "units": [0, 4503599627370496]\n}\n'
        windows = lf.replace(b'\n', b'\r\n')
        self.assertTrue(same_derived_json_bytes(lf, windows))
        self.assertTrue(same_derived_json_bytes(windows, lf))
        self.assertTrue(same_derived_json_bytes(windows, windows))
        for changed in (lf.replace(b'-17', b'-16'), lf.replace(b'4503599627370496', b'4503599627370495'),
                        lf.replace(b'  "regrets"', b' "regrets"'), windows.replace(b'\r\n', b'\n', 1)):
            self.assertFalse(same_derived_json_bytes(changed, windows))


if __name__ == '__main__': unittest.main()
