"""Authenticate a saved immutable-session matrix before independent numerical replay."""
import argparse
from hashlib import sha256
import json
from pathlib import Path,PureWindowsPath

from scripts.replay_native_frozen_policy_state import bounded,read_json,require
from scripts.replay_native_grid_raw import MATH,CONTROLLERS,process,sources

MATH_SOURCES=(*MATH,'tests/virtual_frozen_policy_session_reference.py','tests/virtual_native_policy_session_reference.py',
    'tests/test_native_frozen_policy_session.py','tests/test_native_frozen_grid_raw.py')
CONTROLLER_SOURCES=(*CONTROLLERS,'tests/test_native_frozen_policy_session.py','scripts/replay_native_grid_raw.py')
BOOTSTRAP=('scripts/replay_native_policy_session.py','scripts/replay_native_grid_raw.py',
           'scripts/replay_native_frozen_policy_state.py')
SCOPE='Two-board immutable Q52 session only; no policy transition, clipping, training, quality or wider capacity acceptance.'


def replay(directory):
    directory=Path(directory);native=read_json(directory/'native-build-manifest.json')
    require(native['target']=='virtual-frozen-policy-session' and native['scope']==SCOPE,'session native target/scope')
    require(read_json(directory/'native-identity.json')=={
        'manifest_sha256':sha256(bounded(directory/'native-build-manifest.json',1<<20)).hexdigest(),
        'executable_sha256':native['executable_sha256']},'session native build identity')
    def source_identity():return sources(directory,native,math_sources=MATH_SOURCES,
        controllers=CONTROLLER_SOURCES,version='native-frozen-policy-session-sources-v1',bootstrap=BOOTSTRAP)
    saved,before=source_identity()
    from tests.virtual_dyadic_training_reference import Fixture
    from tests.virtual_frozen_policy_input_reference import decode_snapshot,encode_snapshot,profile
    from tests.virtual_frozen_policy_session_reference import session_forecast
    from tests.virtual_grid_update_reference import build_sampled_reference_context
    from tests.virtual_native_policy_session_reference import verify_session_wire
    from tests.test_native_frozen_policy_session import pair_selectors
    fixture=Fixture();context=build_sampled_reference_context();pairs=pair_selectors(fixture,context)
    expected=json.loads(json.dumps([(name+'-'+label,name,selectors)
        for name in ('uniform','zero-skew') for label,selectors in pairs]))
    plan=read_json(directory/'case-plan.json')
    require(plan['scope']=='twelve independent two-board immutable requests; not training' and
        plan['per_request_work_ceiling']==500_000_000 and plan['automatic_retries']==0 and
        plan['cases']==expected,'session complete selector/order/maximum-stage plan')
    inputs={};policies={}
    for name in ('uniform','zero-skew'):
        body=bounded(directory/('input-'+name+'.bin'),8<<20);policy=decode_snapshot(fixture,body)
        require(policy==profile(fixture,name),'session named immutable policy');inputs[name]=body;policies[name]=policy
    results=[];forecast_sum=0;stream_hashes={}
    for label,name,selectors in expected:
        f=session_forecast(*selectors[0],*selectors[1]);forecast_sum+=f['work']
        require(f['feasible'] and f['work']<=plan['per_request_work_ceiling'],'session independently admitted request')
        args=read_json(directory/(label+'.command.json'))
        tail=[item for board,law in selectors for item in (law,*map(str,board))]
        require(type(args) is list and len(args)==14 and args[0]==native['executable'] and
            PureWindowsPath(args[1]).name=='input-'+name+'.bin' and args[2:]==tail,'session saved command identity')
        child=directory/label
        require(read_json(child/'input-identity.json')=={'file':'input-'+name+'.bin','bytes':len(inputs[name]),
            'sha256':sha256(inputs[name]).hexdigest()},'session saved input identity')
        raw=process(child,0)
        results.append({'case':label,**verify_session_wire(fixture,context,policies[name],selectors,raw)})
        stream_hashes[label]=[s['sha256'] for s in read_json(child/'process.json')['streams']]
    require(forecast_sum==plan['sum_case_request_forecasts'] and forecast_sum<=12*plan['per_request_work_ceiling'],
            'session aggregate independent experiment reservation')
    first=read_json(directory/(expected[0][0]+'.command.json'))
    # Commands describe controller intent; process records independently bind
    # observed stream/exit outcomes, not the child's actual file-open syscalls.
    negative={
        'reject-second-law':first[:8]+['foreign',*first[9:]],
        'reject-second-duplicate':first[:-1]+[first[-2]],
        'reject-second-foreign':first[:9]+['0',*first[10:]],
        'reject-second-unsorted':first[:9]+[first[10],first[9],*first[11:]],
        'reject-arity':first[:-1],
        'reject-third-selector':first+first[2:8],
    }
    for label,expected_args in negative.items():
        require(read_json(directory/(label+'.command.json'))==expected_args,'session rejection command')
        process(directory/label,2)
        stream_hashes[label]=[s['sha256'] for s in read_json(directory/label/'process.json')['streams']]
    label='reject-late-partition';args=read_json(directory/(label+'.command.json'))
    require(len(args)==14 and args[0]==first[0] and PureWindowsPath(args[1]).name=='input-late-zero.bin' and
        args[2:]==first[2:],'session late input rejection command')
    encoded,_,layout=encode_snapshot(fixture,policies['uniform']);require(encoded==inputs['uniform'],'session canonical snapshot')
    bad=bytearray(encoded);bad[layout['last_units']:layout['last_units']+8*layout['last_width']]=b'\0'*(8*layout['last_width'])
    require(bounded(directory/'input-late-zero.bin',8<<20)==bytes(bad),'session late invalid partition bytes')
    process(directory/label,2)
    stream_hashes[label]=[s['sha256'] for s in read_json(directory/label/'process.json')['streams']]
    require(source_identity()==(saved,before),'session source changed during replay')
    return {'status':'all-session-rows-exact','cases':results,'observed_successes':12,'observed_rejections':7,
        'observed_source_head':saved['head'],'active_python_sha256':before,'observed_stream_sha256':stream_hashes,
        'candidate_calls':0,'archived_source_executed':False,
        'scope':'immutable two-board raw session only; no policy transition, training, quality or wider admission',
        'invocation_receipts':'controller commands and observed exits/streams; no independent syscall attestation'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path)
    print(json.dumps(replay(parser.parse_args().directory),indent=2))
