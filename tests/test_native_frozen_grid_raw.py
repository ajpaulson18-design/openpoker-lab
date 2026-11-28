"""Source-frozen per-board raw candidate versus the independent Q52 oracle."""
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
from tests.virtual_dyadic_training_reference import Fixture
from tests.virtual_frozen_policy_input_reference import encode_snapshot,profile
from tests.virtual_frozen_grid_envelope_reference import envelope
from tests.virtual_grid_update_reference import build_sampled_reference_context
from tests.virtual_native_grid_raw_reference import verify_raw_wire

ROOT=Path(__file__).resolve().parents[1]
ENV='OPENPOKER_NATIVE_FROZEN_GRID_RAW_EXE';OUT='OPENPOKER_NATIVE_FROZEN_GRID_RAW_DIR'
SCOPE='Fixed-policy Q52 per-board raw values/regrets/averages study only; no clipping, State update, sampled training, quality or wider capacity acceptance.'


def case_boards(fixture,context):
    positive={}
    for world in fixture.worlds:positive.setdefault(world.holdings,world.board)
    first=next(iter(positive.values()));physical=set(world.board for world in fixture.worlds)
    zero_turn=next(board for board in context.physical.proposals if board[:4]==first[:4] and board not in physical)
    zero_flop=next(board for board in context.physical.proposals if not envelope(board)[17] and envelope(board)[0]==12)
    return tuple((f'positive-{i}',board) for i,board in enumerate(positive.values()))+(('zero-shared-turn',zero_turn),('zero-at-flop',zero_flop))


@unittest.skipUnless(os.environ.get(ENV),'explicit source-built raw candidate required')
class NativeRawTests(unittest.TestCase):
    def test_twenty_case_matrix_and_preparation_rejections(self):
        exe=Path(os.environ[ENV]).resolve();identity=authenticate(exe,ROOT,'virtual-frozen-grid-raw-update')
        self.assertEqual(identity[1]['scope'],SCOPE)
        names=sorted(set(identity[1]['source_sha256'])|set(ORACLE_SOURCES)|{
            'scripts/replay_native_frozen_policy_state.py','tests/virtual_frozen_policy_input_reference.py',
            'tests/virtual_frozen_grid_preflight_reference.py','tests/virtual_frozen_grid_envelope_reference.py',
            'tests/virtual_grid_update_reference.py','tests/virtual_frozen_sample_reference.py',
            'tests/virtual_native_grid_raw_reference.py','tests/test_native_frozen_grid_raw.py'})
        self.assertLessEqual(len(names),128)
        self.assertFalse(subprocess.check_output(['git','status','--porcelain','--untracked-files=all','--',*names],cwd=ROOT))
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        source={n:(ROOT/n).read_bytes() for n in names}
        self.assertLessEqual(sum(map(len,source.values())),64<<20)
        tree={}
        for line in subprocess.check_output(['git','ls-tree','-r',head],cwd=ROOT,text=True).splitlines():
            meta,name=line.split('\t',1)
            if name in names:tree[name]=meta.split()[2]
        self.assertEqual(set(tree),set(names))
        fixture=Fixture();context=build_sampled_reference_context();boards=case_boards(fixture,context)
        self.assertEqual(len(boards),5)
        with TemporaryDirectory(dir=ROOT.parent) as temporary:
            directory=Path(os.environ.get(OUT,str(Path(temporary)/'observed')));directory.mkdir(parents=True,exist_ok=False)
            for name,raw in source.items():
                target=directory/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            (directory/'source-identity.json').write_text(json.dumps({'version':'native-frozen-grid-raw-sources-v1','head':head,
                'raw_sha256':{n:sha256(raw).hexdigest() for n,raw in source.items()},'committed_blobs':tree,
                'python_version':sys.version,'python_executable_sha256':sha256(Path(sys.executable).read_bytes()).hexdigest()},indent=2)+'\n')
            (directory/'native-build-manifest.json').write_bytes(identity[0])
            (directory/'native-identity.json').write_text(json.dumps({'manifest_sha256':sha256(identity[0]).hexdigest(),
                'executable_sha256':identity[1]['executable_sha256']})+'\n')
            plan=[(f'{name}-{law}-{label}',name,law,board) for name in ('uniform','zero-skew') for law in ('uniform','river_weighted') for label,board in boards]
            (directory/'case-plan.json').write_text(json.dumps({'scope':'twenty independent bounded native requests; not one training admission',
                'cases':plan,'per_request_work_ceiling':500_000_000,'sum_case_request_forecasts':sum(envelope(b)[12] for _,_,_,b in plan),
                'automatic_retries':0},indent=2)+'\n')
            policies={name:profile(fixture,name) for name in ('uniform','zero-skew')};inputs={};layouts={}
            for name,policy in policies.items():
                data,_,layouts[name]=encode_snapshot(fixture,policy);path=directory/('input-'+name+'.bin');path.write_bytes(data)
                inputs[name]=(path,sha(path),data)
            results=[];first=None
            def observe(label,command):
                (directory/(label+'.command.json')).write_text(json.dumps(command)+'\n')
                child=directory/label
                observed=run_bounded_child(command,b'',child,stdout_limit=2_100_000,timeout=180)
                return child,observed
            for label,name,law,board in plan:
                path,digest,data=inputs[name];command=[str(exe),str(path),law,*map(str,board)]
                child,observed=observe(label,command)
                self.assertEqual(sha(path),digest,label)
                (child/'input-identity.json').write_text(json.dumps({'file':path.name,'bytes':len(data),'sha256':digest})+'\n')
                self.assertEqual((observed['status'],observed['returncode'],observed['actual_exit_observed']),('exited',0,True),label)
                self.assertEqual((child/'stderr.bin').read_bytes(),b'',label)
                raw=(child/'stdout.bin').read_bytes();result=verify_raw_wire(fixture,context,policies[name],board,law,raw)
                (child/'independent-rows.json').write_text(json.dumps(result,indent=2)+'\n');results.append({'case':label,**result})
                if first is None:first=(raw,policies[name],board,law)
            path,_,data=inputs['uniform'];board=boards[0][1]
            negatives={
                'reject-law':[str(exe),str(path),'foreign',*map(str,board)],
                'reject-duplicate':[str(exe),str(path),'uniform',*map(str,(*board[:4],board[3]))],
                'reject-foreign-card':[str(exe),str(path),'uniform','0',*map(str,board[1:])],
                'reject-unsorted-flop':[str(exe),str(path),'uniform',*map(str,(board[1],board[0],*board[2:]))],
                'reject-arity':[str(exe),str(path),'uniform'],
            }
            changed=bytearray(data);layout=layouts['uniform']
            changed[layout['last_units']:layout['last_units']+8*layout['last_width']]=b'\0'*(8*layout['last_width'])
            bad=directory/'input-late-zero.bin';bad.write_bytes(changed)
            negatives['reject-late-partition']=[str(exe),str(bad),'uniform',*map(str,board)]
            for label,command in negatives.items():
                child,observed=observe(label,command)
                self.assertEqual((observed['status'],observed['returncode'],observed['actual_exit_observed']),('exited',2,True),label)
                self.assertEqual((child/'stdout.bin').read_bytes(),b'',label);self.assertTrue((child/'stderr.bin').read_bytes(),label)
            raw,policy,board,law=first
            corrupted=bytearray(raw);corrupted[1_442_768]^=1
            for changed in (raw[:-1],bytes(corrupted)):
                with self.assertRaises(ValueError):verify_raw_wire(fixture,context,policy,board,law,changed)
            self.assertEqual(authenticate(exe,ROOT,'virtual-frozen-grid-raw-update'),identity)
            for name,raw in source.items():self.assertEqual((ROOT/name).read_bytes(),raw)
            (directory/'matrix-results.json').write_text(json.dumps({'status':'all-raw-rows-exact','cases':results,'successful_calls':20,
                'rejected_calls':6,'automatic_retries':0,'scope':'fixed-policy raw conformance only; no clipping, training or quality acceptance'},indent=2)+'\n')


if __name__=='__main__':unittest.main()
