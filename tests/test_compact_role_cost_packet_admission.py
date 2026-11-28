"""Altered same-policy timing packets refuse before any numerical imports."""
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from tests.test_joint_cycles_packet_admission import CHILD
from scripts.replay_compact_role_cost import PACKET

ROOT=Path(__file__).resolve().parents[1]


class CompactRoleCostAdmissionTests(unittest.TestCase):
    def refuses(self,member):
        with TemporaryDirectory(prefix='compact-role-cost-negative-',dir=ROOT.parent) as directory:
            root=Path(directory);packet=root/'packet';packet.mkdir()
            for original in PACKET.iterdir():shutil.copyfile(original,packet/original.name)
            path=packet/member;body=bytearray(path.read_bytes());body[0]^=1;path.write_bytes(body)
            child=CHILD.replace('scripts.replay_joint_cycles_packet','scripts.replay_compact_role_cost')
            for optimized in (False,True):
                result=subprocess.run([sys.executable,*(['-O'] if optimized else []),'-B','-X',
                    'pycache_prefix='+str(root/('optimized-cache' if optimized else 'normal-cache')),
                    '-c',child,str(packet)],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=False)
                self.assertEqual(result.returncode,1);self.assertEqual(result.stdout,b'')
                self.assertIn(('joint CPU literal packet pin: '+member).encode(),result.stderr)
                self.assertNotIn(b'UNAUTHENTICATED_CPU_NUMERICS',result.stderr)
    def test_changed_manifest(self):self.refuses('manifest.json')
    def test_changed_objects(self):self.refuses('objects.zip')


if __name__=='__main__':unittest.main()
