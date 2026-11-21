"""Reject forged raw source/exit evidence before entering numeric replay."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from scripts import replay_native_grid_raw as reader
from scripts.replay_native_grid_raw_packet import PINS
from scripts import replay_native_grid_raw_packet as packet_reader

ROOT=Path(__file__).resolve().parents[1]


class SavedRawControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        packet=ROOT/'benchmarks/results/native-frozen-grid-raw-v1/normal.zip'
        raw=packet.read_bytes();digest,size=PINS['normal']
        if len(raw)!=size or sha256(raw).hexdigest()!=digest:
            raise ValueError('control fixture archive drift')
        with zipfile.ZipFile(packet) as archive:
            cls.source={n[7:]:archive.read(n) for n in archive.namelist()
                if n.startswith('matrix/source/') or n in {
                    'matrix/source-identity.json','matrix/native-build-manifest.json','matrix/native-identity.json'}}
            label='matrix/uniform-uniform-positive-0/'
            cls.process_files={n[len(label):]:archive.read(n) for n in archive.namelist() if n.startswith(label)}

    def setUp(self):
        self.temporary=TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(self.temporary.cleanup)
        self.directory=Path(self.temporary.name)

    def write_files(self,files):
        for name,body in files.items():
            path=self.directory/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)

    def test_source_forgeries_reject_before_numeric_import(self):
        self.write_files(self.source)
        original=json.loads(self.source['source-identity.json'])
        first=next(iter(original['raw_sha256']))
        original_body=self.source['source/'+first]
        for variant in ('head-grammar','missing-source','blob','raw-byte','self-consistent-byte-forgery'):
            with self.subTest(variant=variant):
                identity=deepcopy(original);body=original_body
                if variant=='head-grammar':identity['head']='HEAD'
                elif variant=='missing-source':del identity['raw_sha256'][first]
                elif variant=='blob':identity['committed_blobs'][first]='0'*40
                else:
                    body+=b'\n// forged evidence\n'
                    if variant=='self-consistent-byte-forgery':identity['raw_sha256'][first]=sha256(body).hexdigest()
                (self.directory/'source'/first).write_bytes(body)
                (self.directory/'source-identity.json').write_text(json.dumps(identity),encoding='utf-8')
                # Numeric modules load only after full source admission.
                # A forged closure must fail before this point, regardless of -O.
                with patch.dict('sys.modules',{'tests.virtual_dyadic_training_reference':None}):
                    with self.assertRaises(ValueError):reader.replay(self.directory)

    def test_unobserved_retried_or_corrupted_process_rejects(self):
        self.write_files(self.process_files)
        original=json.loads(self.process_files['process.json'])
        for field,value in (('actual_exit_observed',False),('automatic_retries',1),('returncode',2),('status','running')):
            with self.subTest(field=field):
                receipt=deepcopy(original);receipt[field]=value
                (self.directory/'process.json').write_text(json.dumps(receipt),encoding='utf-8')
                with self.assertRaises(ValueError):reader.process(self.directory,0)
        (self.directory/'process.json').write_bytes(self.process_files['process.json'])
        body=bytearray(self.process_files['stdout.bin']);body[-1]^=1
        (self.directory/'stdout.bin').write_bytes(body)
        with self.assertRaises(ValueError):reader.process(self.directory,0)

    def test_outer_bootstrap_checks_helpers_before_project_import(self):
        real_command=packet_reader.subprocess.check_output
        def dirty_status(command,**kwargs):
            if command[:3]==['git','status','--porcelain']:return b' M scripts/replay_native_policy_packet.py\n'
            return real_command(command,**kwargs)
        with patch.object(packet_reader.subprocess,'check_output',side_effect=dirty_status):
            with self.assertRaisesRegex(ValueError,'uncommitted raw packet bootstrap'):
                packet_reader.authenticate_bootstrap()
        real_open=Path.open
        helper=ROOT/'scripts/replay_native_policy_packet.py'
        def forged_helper(path,*args,**kwargs):
            if path==helper:return BytesIO(b'raise RuntimeError("forged helper must never execute")\n')
            return real_open(path,*args,**kwargs)
        with patch.object(Path,'open',forged_helper):
            with self.assertRaisesRegex(ValueError,'bootstrap byte drift'):
                packet_reader.authenticate_bootstrap()


if __name__=='__main__':unittest.main()
