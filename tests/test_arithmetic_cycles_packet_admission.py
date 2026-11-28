"""The failed-observer evidence must authenticate before numerical imports."""
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from tests.test_joint_cycles_packet_admission import CHILD

ROOT=Path(__file__).resolve().parents[1]
PACKET=ROOT/'benchmarks/results/joint-arithmetic-cycles-v1'


class ArithmeticPacketAdmissionTests(unittest.TestCase):
    def refuses(self,member,light=False):
        with TemporaryDirectory(prefix='arithmetic-cycle-negative-',dir=ROOT.parent) as directory:
            root=Path(directory);packet=root/'packet';packet.mkdir()
            source=ROOT/'benchmarks/results/joint-arithmetic-light-v1' if light else PACKET
            for original in source.iterdir():shutil.copyfile(original,packet/original.name)
            path=packet/member;raw=bytearray(path.read_bytes());raw[0]^=1;path.write_bytes(raw)
            child=CHILD.replace('scripts.replay_joint_cycles_packet','scripts.replay_joint_arithmetic_cycles_packet')
            child=child.replace("sys.argv=['scripts.replay_joint_arithmetic_cycles_packet',sys.argv[1]]",
                                "sys.argv=['scripts.replay_joint_arithmetic_cycles_packet',sys.argv[1],*sys.argv[2:]]")
            for optimized in (False,True):
                result=subprocess.run([sys.executable,*(['-O'] if optimized else []),'-B','-X',
                    'pycache_prefix='+str(root/('optimized-cache' if optimized else 'normal-cache')),
                    '-c',child,str(packet),*(['--light'] if light else [])],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=False)
                self.assertEqual(result.returncode,1);self.assertEqual(result.stdout,b'')
                self.assertIn(('joint CPU literal packet pin: '+member).encode(),result.stderr)
                self.assertNotIn(b'UNAUTHENTICATED_CPU_NUMERICS',result.stderr)
    def test_changed_manifest(self):self.refuses('manifest.json')
    def test_changed_objects(self):self.refuses('objects.zip')
    def test_changed_light_manifest(self):self.refuses('manifest.json',light=True)
    def test_changed_light_objects(self):self.refuses('objects.zip',light=True)


if __name__=='__main__':unittest.main()
