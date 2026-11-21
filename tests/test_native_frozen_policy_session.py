"""Two-board immutable epoch versus independent four-street raw arithmetic."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts.replay_native_grid_raw import MATH,CONTROLLERS
from tests.test_native_exact_reach import authenticate,sha
from tests.test_native_frozen_grid_raw import case_boards
from tests.virtual_dyadic_training_reference import Fixture
from tests.virtual_frozen_policy_input_reference import encode_snapshot,profile
from tests.virtual_frozen_grid_preflight_reference import boards,census
from tests.virtual_frozen_policy_session_reference import session_forecast
from tests.virtual_grid_update_reference import build_sampled_reference_context
from tests.virtual_native_policy_session_reference import verify_session_wire
from tests.virtual_frozen_run_control import run_bounded_child

ROOT=Path(__file__).resolve().parents[1]
ENV='OPENPOKER_NATIVE_POLICY_SESSION_EXE';OUT='OPENPOKER_NATIVE_POLICY_SESSION_DIR'
SCOPE='Two-board immutable Q52 session only; no policy transition, clipping, training, quality or wider capacity acceptance.'
NEW_SOURCES=('tests/virtual_frozen_policy_session_reference.py','tests/virtual_native_policy_session_reference.py',
    'tests/test_native_frozen_policy_session.py','tests/test_native_frozen_grid_raw.py')


def pair_selectors(fixture,context):
    selected=dict(case_boards(fixture,context))
    a,b,c=(selected['positive-'+str(i)] for i in range(3))
    most=max(boards(),key=lambda board:census(board)['supported_rows']+census(board)['supported_action_slots'])
    return (
        ('different-pairs',((a,'uniform'),(b,'river_weighted'))),
        ('reversed',((b,'river_weighted'),(a,'uniform'))),
        ('same-selector',((a,'uniform'),(a,'uniform'))),
        ('zero-shared-turn',((a,'river_weighted'),(selected['zero-shared-turn'],'uniform'))),
        ('zero-flop-first',((selected['zero-at-flop'],'river_weighted'),(c,'uniform'))),
        ('maximum-retained-stage',((most,'uniform'),(most,'river_weighted'))),
    )


@unittest.skipUnless(os.environ.get(ENV),'explicit source-built immutable session required')
class NativeSessionTests(unittest.TestCase):
    def test_twelve_sessions_and_complete_preparation_rejections(self):
        exe=Path(os.environ[ENV]).resolve();identity=authenticate(exe,ROOT,'virtual-frozen-policy-session')
        self.assertEqual(identity[1]['scope'],SCOPE)
        names=sorted(set(identity[1]['source_sha256'])|set(MATH)|set(CONTROLLERS)|set(NEW_SOURCES))
        self.assertLessEqual(len(names),128)
        self.assertFalse(subprocess.check_output(['git','status','--porcelain','--untracked-files=all','--',*names],cwd=ROOT))
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        source={n:(ROOT/n).read_bytes() for n in names}
        self.assertLessEqual(sum(map(len,source.values())),64<<20)
        tree={}
        for line in subprocess.check_output(['git','ls-tree','-r',head],cwd=ROOT,text=True).splitlines():
            metadata,name=line.split('\t',1)
            if name in names:tree[name]=metadata.split()[2]
        self.assertEqual(set(tree),set(names))
        fixture=Fixture();context=build_sampled_reference_context();pairs=pair_selectors(fixture,context)
        with TemporaryDirectory(dir=ROOT.parent) as temporary:
            directory=Path(os.environ.get(OUT,str(Path(temporary)/'observed')));directory.mkdir(parents=True,exist_ok=False)
            for name,body in source.items():
                target=directory/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
            (directory/'source-identity.json').write_text(json.dumps({'version':'native-frozen-policy-session-sources-v1',
                'head':head,'raw_sha256':{n:sha256(body).hexdigest() for n,body in source.items()},'committed_blobs':tree,
                'python_version':sys.version,'python_executable_sha256':sha256(Path(sys.executable).read_bytes()).hexdigest()},indent=2)+'\n')
            (directory/'native-build-manifest.json').write_bytes(identity[0])
            (directory/'native-identity.json').write_text(json.dumps({'manifest_sha256':sha256(identity[0]).hexdigest(),
                'executable_sha256':identity[1]['executable_sha256']})+'\n')
            plan=[(name+'-'+label,name,selectors) for name in ('uniform','zero-skew') for label,selectors in pairs]
            (directory/'case-plan.json').write_text(json.dumps({'scope':'twelve independent two-board immutable requests; not training',
                'per_request_work_ceiling':500_000_000,'cases':plan,'automatic_retries':0,
                'sum_case_request_forecasts':sum(session_forecast(*sel[0],*sel[1])['work'] for _,_,sel in plan)},indent=2)+'\n')
            policies={n:profile(fixture,n) for n in ('uniform','zero-skew')};inputs={};layouts={}
            for name,policy in policies.items():
                data,_,layouts[name]=encode_snapshot(fixture,policy);path=directory/('input-'+name+'.bin');path.write_bytes(data)
                inputs[name]=(path,sha(path),data)
            def command(path,selectors):
                return [str(exe),str(path),*[item for board,law in selectors for item in (law,*map(str,board))]]
            def observe(label,args):
                (directory/(label+'.command.json')).write_text(json.dumps(args)+'\n')
                child=directory/label
                result=run_bounded_child(args,b'',child,stdout_limit=2_100_000,timeout=180)
                return child,result
            results=[];first=None
            for label,name,selectors in plan:
                path,digest,data=inputs[name];child,result=observe(label,command(path,selectors))
                self.assertEqual(sha(path),digest,label)
                (child/'input-identity.json').write_text(json.dumps({'file':path.name,'bytes':len(data),'sha256':digest})+'\n')
                self.assertEqual((result['status'],result['returncode'],result['actual_exit_observed']),('exited',0,True),label)
                self.assertEqual((child/'stderr.bin').read_bytes(),b'',label)
                raw=(child/'stdout.bin').read_bytes();check=verify_session_wire(fixture,context,policies[name],selectors,raw)
                (child/'independent-rows.json').write_text(json.dumps(check,indent=2)+'\n');results.append({'case':label,**check})
                if first is None:first=(raw,policies[name],selectors)
            path,_,data=inputs['uniform'];good=command(path,pairs[0][1])
            late=bytearray(data);layout=layouts['uniform'];late[layout['last_units']:layout['last_units']+8*layout['last_width']]=b'\0'*(8*layout['last_width'])
            bad_path=directory/'input-late-zero.bin';bad_path.write_bytes(late)
            invalid={
                'reject-second-law':good[:8]+['foreign',*good[9:]],
                'reject-second-duplicate':good[:-1]+[good[-2]],
                'reject-second-foreign':good[:9]+['0',*good[10:]],
                'reject-second-unsorted':good[:9]+[good[10],good[9],*good[11:]],
                'reject-arity':good[:-1],
                'reject-third-selector':good+good[2:8],
                'reject-late-partition':[str(exe),str(bad_path),*good[2:]],
            }
            for label,args in invalid.items():
                child,result=observe(label,args)
                self.assertEqual((result['status'],result['returncode'],result['actual_exit_observed']),('exited',2,True),label)
                self.assertEqual((child/'stdout.bin').read_bytes(),b'',label)
            self.assertEqual(bad_path.read_bytes(),bytes(late),'late invalid input drift')
            for name,(path,digest,_) in inputs.items():self.assertEqual(sha(path),digest,name)
            # Corrupt the saved raw root while keeping its shape/length: the
            # independent math must reject it, not merely a file digest guard.
            raw,policy,selectors=first
            corrupt=bytearray(raw);corrupt[136+1442112+256+88]^=1
            with self.assertRaises(ValueError):verify_session_wire(fixture,context,policy,selectors,bytes(corrupt))
            with self.assertRaises(ValueError):verify_session_wire(fixture,context,policy,selectors,raw[:-1])
            (directory/'matrix-results.json').write_text(json.dumps({'status':'all-session-rows-exact','cases':results,
                'successful_observed_requests':12,'rejected_observed_requests':7,'state_updates':0,'training_iterations':0},indent=2)+'\n')
        self.assertEqual(authenticate(exe,ROOT,'virtual-frozen-policy-session'),identity)
        self.assertEqual({n:(ROOT/n).read_bytes() for n in names},source)


if __name__=='__main__':unittest.main()
