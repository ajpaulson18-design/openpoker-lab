"""Recount a source-authenticated cold-pair study without invoking candidates."""
import argparse
import json
from math import isfinite
from pathlib import Path,PureWindowsPath
from statistics import median

from scripts.replay_native_frozen_policy_state import bounded,read_json,require
from scripts.replay_native_grid_raw import MATH,CONTROLLERS,process,sources

MATH_SOURCES=(*MATH,'tests/virtual_frozen_policy_session_reference.py','tests/virtual_native_policy_session_reference.py',
    'tests/test_native_frozen_policy_session.py','tests/test_native_frozen_grid_raw.py')
CONTROLLER_SOURCES=(*CONTROLLERS,'scripts/replay_native_grid_raw.py','scripts/benchmark_native_policy_session.py')
BOOTSTRAP=('scripts/replay_policy_session_benchmark.py','scripts/replay_native_grid_raw.py',
           'scripts/replay_native_frozen_policy_state.py')


def replay(directory):
    directory=Path(directory);native={name:read_json(directory/(name+'-native-build-manifest.json')) for name in ('baseline','session')}
    require(native['baseline']['target']=='virtual-frozen-grid-raw-update' and
            native['session']['target']=='virtual-frozen-policy-session','benchmark exact build targets')
    combined={}
    for manifest in native.values():
        for name,digest in manifest['source_sha256'].items():
            require(name not in combined or combined[name]==digest,'benchmark shared build-source drift')
            combined[name]=digest
    def source_identity():return sources(directory,{'source_sha256':combined},math_sources=MATH_SOURCES,
        controllers=CONTROLLER_SOURCES,version='native-policy-session-benchmark-sources-v1',bootstrap=BOOTSTRAP)
    saved,before=source_identity()
    from tests.virtual_dyadic_training_reference import Fixture
    from tests.virtual_frozen_policy_input_reference import decode_snapshot,profile
    from tests.virtual_frozen_policy_session_reference import session_forecast
    from tests.virtual_frozen_grid_envelope_reference import envelope
    from tests.virtual_grid_update_reference import build_sampled_reference_context
    from tests.virtual_native_grid_raw_reference import verify_raw_wire
    from tests.virtual_native_policy_session_reference import verify_session_wire
    from tests.test_native_frozen_policy_session import pair_selectors
    fixture=Fixture();context=build_sampled_reference_context();selectors=pair_selectors(fixture,context)[0][1]
    policy=decode_snapshot(fixture,bounded(directory/'input-zero-skew.bin',8<<20))
    require(policy==profile(fixture,'zero-skew'),'benchmark named input policy')
    protocol=read_json(directory/'protocol.json')
    cold_forecast=sum(envelope(board)[12] for board,_ in selectors)
    shared_forecast=session_forecast(*selectors[0],*selectors[1])['work']
    require(protocol['version']=='cold-pair-shared-session-v1' and protocol['source_head']==saved['head'] and
        protocol['profile']=='zero-skew' and protocol['selectors']==json.loads(json.dumps(selectors)) and
        (protocol['warmup_groups'],protocol['pairs'],protocol['minimum_pairs_faster'],protocol['automatic_retries'])==(1,8,6,0) and
        protocol['median_ratio_at_most']==0.96 and protocol['per_child_work_ceiling']==500_000_000 and
        protocol['per_child_stdout_ceiling']==2_100_000 and
        protocol['baseline_sum_request_forecasts']==cold_forecast and protocol['session_request_forecast']==shared_forecast and
        protocol['sum_all_experiment_request_forecasts']==9*(cold_forecast+shared_forecast),'benchmark frozen named protocol')
    warm={};warm_checks={};observed=set()
    def observation(label,kind,index=None,initial=False):
        observed.add(label);child=directory/label;manifest=native[kind]
        command=read_json(directory/(label.replace('/','-')+'.command.json'))
        chosen=(selectors[index],) if kind=='baseline' else selectors
        tail=[item for board,law in chosen for item in (law,*map(str,board))]
        require(type(command) is list and len(command)==2+len(tail) and command[0]==manifest['executable'] and
            PureWindowsPath(command[1]).name=='input-zero-skew.bin' and command[2:]==tail,'benchmark saved command')
        raw=process(child,0);receipt=read_json(child/'process.json');elapsed=receipt['duration_seconds']
        require(type(elapsed) in (int,float) and isfinite(elapsed) and elapsed>0,'benchmark observed positive duration')
        key=(kind,index)
        if initial:
            check=(verify_raw_wire(fixture,context,policy,*chosen[0],raw) if kind=='baseline' else
                verify_session_wire(fixture,context,policy,selectors,raw))
            warm[key]=raw;warm_checks[key]=check
        else:require(raw==warm[key],'benchmark full timed numerical wire drift')
        return elapsed
    observation('warmup/baseline-0','baseline',0,True)
    observation('warmup/baseline-1','baseline',1,True)
    observation('warmup/session','session',initial=True)
    merged=warm['session',None];position=136+1442112
    for i,(board,_) in enumerate(selectors):
        cold=warm['baseline',i];record=envelope(board)[15]-1442112
        require(cold[256:256+1442112]==merged[136:136+1442112] and
            cold[256+1442112:-208]==merged[position+256:position+record-208],'benchmark direct policy/raw byte parity')
        position+=record
    pairs=[]
    for i in range(8):
        cold_time=sum(observation(f'pair-{i:02}/baseline-{j}','baseline',j) for j in range(2))
        shared_time=observation(f'pair-{i:02}/session','session')
        pair={'pair':i,'order':'session-first' if i%2 else 'baseline-first','baseline_seconds':cold_time,
            'session_seconds':shared_time,'ratio':shared_time/cold_time}
        require(read_json(directory/f'pair-{i:02}.json')==pair,'benchmark saved pair recount')
        pairs.append(pair)
    require({p.parent.relative_to(directory).as_posix() for p in directory.rglob('process.json')}==observed and len(observed)==27,
            'benchmark full observed-child census')
    ratio=median(p['ratio'] for p in pairs);faster=sum(p['ratio']<1 for p in pairs)
    result={'status':'measured','pairs':pairs,'median_ratio':ratio,'pairs_faster':faster,
        'timing_gate_passed':ratio<=0.96 and faster>=6,'observed_native_children':27,'all_numerical_wires_verified':True,
        'automatic_retries':0,'source_head':saved['head'],
        'baseline_sum_actual_work':sum(warm_checks['baseline',j]['work_actual'] for j in range(2)),
        'session_actual_work':warm_checks['session',None]['work_actual'],
        'baseline_output_bytes':sum(len(warm['baseline',j]) for j in range(2)),
        'session_output_bytes':len(merged),'scope':protocol['scope']}
    require(read_json(directory/'result.json')==result,'benchmark full saved result recount')
    require(source_identity()==(saved,before),'benchmark replay source changed')
    return {'status':'all-timings-and-numerical-wires-recounted','result':result,'candidate_calls':0,
        'archived_source_executed':False,'active_python_sha256':before,
        'invocation_receipts':'controller commands and exit/stream observations; elapsed records are not independent clock attestations'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path)
    print(json.dumps(replay(parser.parse_args().directory),indent=2))
