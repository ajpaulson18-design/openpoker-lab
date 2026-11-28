"""Exact synthetic sparse-store transitions; whole-game training is separate."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts.replay_native_frozen_policy_state import ORACLE_SOURCES
from tests.test_native_exact_reach import authenticate,sha
from tests.virtual_frozen_run_control import run_bounded_child
from tests.test_native_dyadic_policy import allocation,Q

ROOT=Path(__file__).resolve().parents[1]
ENV='OPENPOKER_NATIVE_SPARSE_EPOCH_EXE';OUT='OPENPOKER_NATIVE_SPARSE_EPOCH_DIR'
TARGET='virtual-sparse-epoch-controls'


@unittest.skipUnless(os.environ.get(ENV),'explicit source-built sparse component required')
class NativeSparseEpochTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe=Path(os.environ[ENV]).resolve();cls.identity=authenticate(cls.exe,ROOT,TARGET)
        names=sorted(set(cls.identity[1]['source_sha256'])|set(ORACLE_SOURCES)|{'tests/test_native_sparse_epoch.py'})
        if len(names)>128 or subprocess.check_output(['git','status','--porcelain','--untracked-files=all','--',*names],cwd=ROOT):
            raise ValueError('sparse component source must be committed and clean')
        cls.head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        cls.source={n:(ROOT/n).read_bytes() for n in names}
        if sum(map(len,cls.source.values()))>64<<20:raise ValueError('sparse source ceiling')
        tree={}
        for line in subprocess.check_output(['git','ls-tree','-r',cls.head],cwd=ROOT,text=True).splitlines():
            metadata,name=line.split('\t',1)
            if name in names:tree[name]=metadata.split()[2]
        if set(tree)!=set(names):raise ValueError('sparse complete source tree')
        target=os.environ.get(OUT)
        if target is None:
            temporary=TemporaryDirectory(dir=ROOT.parent);cls.addClassCleanup(temporary.cleanup)
            target=Path(temporary.name)/'observed'
        cls.directory=Path(target);cls.directory.mkdir(parents=True,exist_ok=False)
        for name,body in cls.source.items():
            if len(body)>32<<20:raise ValueError('sparse source member ceiling')
            path=cls.directory/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
        (cls.directory/'source-identity.json').write_text(json.dumps({'version':'sparse-epoch-component-sources-v1',
            'head':cls.head,'raw_sha256':{n:sha256(v).hexdigest() for n,v in cls.source.items()},'committed_blobs':tree,
            'python_version':sys.version,'python_executable_sha256':sha(Path(sys.executable))},indent=2)+'\n')
        (cls.directory/'native-build-manifest.json').write_bytes(cls.identity[0])
        command=[str(cls.exe)];(cls.directory/'command.json').write_text(json.dumps(command)+'\n')
        cls.process=run_bounded_child(command,b'',cls.directory/'process',stdout_limit=65536,timeout=180)
        cls.stdout=(cls.directory/'process/stdout.bin').read_bytes()
        cls.stderr=(cls.directory/'process/stderr.bin').read_bytes()
        cls.lines=cls.stdout.decode('ascii').splitlines()

    @classmethod
    def tearDownClass(cls):
        if authenticate(cls.exe,ROOT,TARGET)!=cls.identity or {n:(ROOT/n).read_bytes() for n in cls.source}!=cls.source:
            raise AssertionError('sparse component source/build drift')

    def rows(self):
        result={}
        for line in self.lines:
            if not line.startswith('ROW '):continue
            _,label,ordinal,actor,holding,count,*values=line.split();count=int(count)
            self.assertNotIn(label,result)
            self.assertEqual((int(ordinal),int(actor),int(holding),count),(0,0,0,4))
            self.assertEqual(len(values),3*count)
            values=list(map(int,values))
            result[label]=(values[::3],values[1::3],values[2::3])
        self.assertEqual(set(result),{'signed-E1','signed-E2','averages-E1','averages-E2','no-intermediate-export-E2'})
        return result

    def test_observed_process_and_rejected_lifecycle(self):
        self.assertEqual((self.process['status'],self.process['returncode'],self.process['actual_exit_observed']),('exited',0,True))
        self.assertFalse(self.stderr)
        self.assertEqual((self.lines[0],self.lines[-1]),('VIRTUAL_SPARSE_EPOCH_COMPONENT_V1','END'))
        guards=[line.split()[1:] for line in self.lines if line.startswith('GUARD ')]
        self.assertEqual(guards,[[name,'PASS'] for name in ('third-epoch','commit-during-lease','weighted-law',
            'incomplete-two-seat-read','duplicate-stage','nonmember-denominator','incomplete-stage-set',
            'uncentered-regret','wrong-average-proportions')])

    def test_signed_regret_persists_and_next_policy_uses_positive_parts(self):
        rows=self.rows();first=[5,-3,0,-2];second=[a+b for a,b in zip(first,[0,4,2,-1])]
        self.assertEqual(rows['signed-E1'][0],first);self.assertEqual(rows['signed-E2'][0],second)
        self.assertEqual(rows['signed-E1'][2],allocation(first)[0])
        self.assertEqual(rows['signed-E2'][2],allocation(second)[0])
        clipped=[max(0,a)+b for a,b in zip(first,[0,4,2,-1])]
        self.assertNotEqual(rows['signed-E2'][2],allocation(clipped)[0])
        self.assertEqual(rows['no-intermediate-export-E2'],rows['signed-E2'])
        self.assertIn('CONTROL no-intermediate-export PASS',self.lines)

    def test_exact_average_scales_and_no_quantization_for_average_only_updates(self):
        rows=self.rows();factor=20<<312
        first=[(Q//4)*factor]*4
        second=[a+b for a,b in zip(first,(7*Q,0,0,0))]
        average_only=[a+7*(Q//4) for a in first]
        for label,expected in (('signed-E1',first),('signed-E2',second),('averages-E1',first),('averages-E2',average_only)):
            self.assertEqual(rows[label][1],expected,label)
        for label in ('averages-E1','averages-E2'):
            self.assertEqual(rows[label][0],[0]*4);self.assertEqual(rows[label][2],[Q//4]*4)
        self.assertIn('CONTROL average-only-no-quantization PASS',self.lines)

    def test_cumulative_component_receipts(self):
        record=next(line for line in self.lines if line.startswith('RECEIPT signed '))
        work,quant,reads,staged_rows,slots,commits,quant_rows,current_rows,current_slots,peak=map(int,record.split()[2:])
        self.assertEqual((reads,staged_rows,slots,commits,quant_rows,current_rows,current_slots),(4,2,8,2,2,1,4))
        self.assertGreater(quant,0);self.assertLessEqual(work+quant,1_000_000)
        self.assertGreater(peak,0);self.assertLessEqual(peak,1<<30)


if __name__=='__main__':unittest.main()
