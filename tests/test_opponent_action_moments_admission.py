"""Altered evidence and inconsistent raw moment/proposal frames must refuse."""
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from tests.test_joint_cycles_packet_admission import CHILD
from scripts import joint_evidence_archive as archive,replay_joint_two_epoch_packet as helper
from scripts.replay_opponent_action_moments import PACKET,PIN
from scripts.opponent_action_moment_frame import parse

ROOT=Path(__file__).resolve().parents[1]


class MomentPacketAdmissionTests(unittest.TestCase):
    def refuses(self,member):
        with TemporaryDirectory(prefix='moment-negative-',dir=ROOT.parent) as directory:
            root=Path(directory);packet=root/'packet';packet.mkdir()
            for original in PACKET.iterdir():shutil.copyfile(original,packet/original.name)
            path=packet/member;raw=bytearray(path.read_bytes());raw[0]^=1;path.write_bytes(raw)
            child=CHILD.replace('scripts.replay_joint_cycles_packet','scripts.replay_opponent_action_moments')
            for optimized in (False,True):
                result=subprocess.run([sys.executable,*(['-O'] if optimized else []),'-B','-X',
                    'pycache_prefix='+str(root/('optimized-cache' if optimized else 'normal-cache')),
                    '-c',child,str(packet)],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=False)
                self.assertEqual(result.returncode,1);self.assertEqual(result.stdout,b'')
                self.assertIn(('joint CPU literal packet pin: '+member).encode(),result.stderr)
                self.assertNotIn(b'UNAUTHENTICATED_CPU_NUMERICS',result.stderr)
    def test_changed_manifest_precedes_numerical_imports(self):self.refuses('manifest.json')
    def test_changed_objects_precedes_numerical_imports(self):self.refuses('objects.zip')

    def test_raw_units_second_moments_and_proposal_factors_are_checked(self):
        _manifest,loaded,_pins=archive.load(PACKET,helper,pin=PIN,version='opponent-moments',
            labels=('observations','builds','objects'),packager='package_opponent_moments1.py.txt')
        files=loaded['observations'];wire=files['study/case-0-normal/stdout.bin'];side=files['study/case-0-normal/witness.bin']
        report=helper.decode(files['study/case-0-normal/summary.json']);self.assertEqual(parse(wire,side,report)['tables'],4)
        # First table: header, two root moment pairs, first row descriptor.
        first_slot=176+88+2*(88+168)+40
        changed=bytearray(wire);struct.pack_into('<Q',changed,first_slot,1<<52)
        with self.assertRaisesRegex(ValueError,'grid/center/average ratio'):parse(bytes(changed),side,report)
        # A positive raw expected average cannot have zero marginal second moment.
        changed=bytearray(wire);a2=first_slot+8+88+168+48;changed[a2:a2+96]=b'\0'*96
        with self.assertRaisesRegex(ValueError,'variance/bound'):parse(bytes(changed),side,report)
        # Last 8 bytes of the final witness are its final proposal denominator.
        changed=bytearray(side);changed[-8:]=b'\0'*8
        with self.assertRaisesRegex(ValueError,'proposal'):parse(wire,bytes(changed),report)
        with self.assertRaises(ValueError):parse(wire[:-1],side,report)
        with self.assertRaises(ValueError):parse(wire,side+b'\0',report)


if __name__=='__main__':unittest.main()
