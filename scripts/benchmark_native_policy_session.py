"""Source-frozen cold-pair versus shared-epoch complete-call comparison."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import subprocess
import sys

from scripts.replay_native_grid_raw import MATH,CONTROLLERS
from tests.test_native_exact_reach import authenticate,sha
from tests.test_native_frozen_policy_session import NEW_SOURCES,pair_selectors
from tests.virtual_dyadic_training_reference import Fixture
from tests.virtual_frozen_policy_input_reference import encode_snapshot,profile
from tests.virtual_frozen_policy_session_reference import session_forecast
from tests.virtual_frozen_grid_envelope_reference import envelope
from tests.virtual_grid_update_reference import build_sampled_reference_context
from tests.virtual_native_grid_raw_reference import verify_raw_wire
from tests.virtual_native_policy_session_reference import verify_session_wire
from tests.virtual_frozen_run_control import run_bounded_child

ROOT=Path(__file__).resolve().parents[1]


def require(value,message):
    if not value:raise ValueError(message)


def benchmark(baseline,session,directory):
    baseline=Path(baseline).resolve();session=Path(session).resolve();directory=Path(directory).resolve()
    require(directory!=ROOT and ROOT not in directory.parents,'benchmark must be outside source checkout')
    identities={'baseline':authenticate(baseline,ROOT,'virtual-frozen-grid-raw-update'),
                'session':authenticate(session,ROOT,'virtual-frozen-policy-session')}
    names=sorted(set(MATH)|set(CONTROLLERS)|set(NEW_SOURCES)|{'scripts/benchmark_native_policy_session.py'}|
        {name for _,native in identities.values() for name in native['source_sha256']})
    require(len(names)<=128 and not subprocess.check_output(['git','status','--porcelain','--untracked-files=all','--',*names],cwd=ROOT),
            'benchmark introduced source must be committed and clean')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    source={name:(ROOT/name).read_bytes() for name in names}
    require(sum(map(len,source.values()))<=64<<20,'benchmark source byte ceiling')
    tree={}
    for line in subprocess.check_output(['git','ls-tree','-r',head],cwd=ROOT,text=True).splitlines():
        metadata,name=line.split('\t',1)
        if name in names:tree[name]=metadata.split()[2]
    require(set(tree)==set(names),'benchmark complete source tree')
    directory.mkdir(parents=True,exist_ok=False)
    for name,body in source.items():
        target=directory/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
    for name,(raw,_) in identities.items():(directory/(name+'-native-build-manifest.json')).write_bytes(raw)
    (directory/'source-identity.json').write_text(json.dumps({'version':'native-policy-session-benchmark-sources-v1',
        'head':head,'raw_sha256':{n:sha256(b).hexdigest() for n,b in source.items()},'committed_blobs':tree,
        'python_version':sys.version,'python_executable_sha256':sha256(Path(sys.executable).read_bytes()).hexdigest()},indent=2)+'\n')
    fixture=Fixture();context=build_sampled_reference_context();policy=profile(fixture,'zero-skew')
    selectors=pair_selectors(fixture,context)[0][1]
    data,_,_=encode_snapshot(fixture,policy);path=directory/'input-zero-skew.bin';path.write_bytes(data)
    input_hash=sha(path)
    cold_forecast=sum(envelope(board)[12] for board,_ in selectors)
    shared_forecast=session_forecast(*selectors[0],*selectors[1])['work']
    protocol={'version':'cold-pair-shared-session-v1','source_head':head,'profile':'zero-skew','selectors':selectors,
        'warmup_groups':1,'pairs':8,'paired_order':'alternate baseline-first/session-first',
        'median_ratio_at_most':0.96,'minimum_pairs_faster':6,'automatic_retries':0,
        'baseline_scope':'two separate existing admitted requests with duplicate complete policy echoes',
        'session_scope':'one admitted request with one complete policy echo and two raw results',
        'baseline_sum_request_forecasts':cold_forecast,'session_request_forecast':shared_forecast,
        'sum_all_experiment_request_forecasts':9*(cold_forecast+shared_forecast),
        'per_child_work_ceiling':500_000_000,'per_child_stdout_ceiling':2_100_000,
        'timing':'observed child complete lifetime; two baseline durations summed; numerical replay outside timing',
        'scope':'named PROOF9 cold setup amortization only; no training-throughput, RSS or wider-capacity claim'}
    (directory/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    warm={};warm_results={}
    def observe(label,kind,index=None,initial=False):
        executable=baseline if kind=='baseline' else session
        chosen=(selectors[index],) if kind=='baseline' else selectors
        command=[str(executable),str(path),*[item for board,law in chosen for item in (law,*map(str,board))]]
        child=directory/label
        child.parent.mkdir(parents=True,exist_ok=True)
        (directory/(label.replace('/','-')+'.command.json')).write_text(json.dumps(command)+'\n')
        require(sha(path)==input_hash,'benchmark input changed before child')
        receipt=run_bounded_child(command,b'',child,stdout_limit=2_100_000,timeout=180)
        require(receipt['status']=='exited' and receipt['returncode']==0 and receipt['actual_exit_observed'] is True and
            receipt['automatic_retries']==0 and not receipt['failures'],'benchmark observed child exit')
        require(not (child/'stderr.bin').read_bytes() and sha(path)==input_hash,'benchmark stderr/input drift')
        raw=(child/'stdout.bin').read_bytes();key=(kind,index)
        if initial:
            check=(verify_raw_wire(fixture,context,policy,*chosen[0],raw) if kind=='baseline' else
                   verify_session_wire(fixture,context,policy,selectors,raw))
            warm[key]=raw;warm_results[key]=check
            (child/'independent-rows.json').write_text(json.dumps(check,indent=2)+'\n')
        else:require(raw==warm[key],'timed observation differs from independently verified full warmup wire')
        return receipt['duration_seconds']
    observe('warmup/baseline-0','baseline',0,True)
    observe('warmup/baseline-1','baseline',1,True)
    observe('warmup/session','session',initial=True)
    # Independent equality is supplemented by direct byte equality of every
    # shared policy and raw denominator/root/row payload across wire layouts.
    combined=warm['session',None];position=136+1442112
    for i,(board,_) in enumerate(selectors):
        cold=warm['baseline',i];record=envelope(board)[15]-1442112
        require(cold[256:256+1442112]==combined[136:136+1442112],'benchmark shared policy echo bytes')
        require(cold[256+1442112:-208]==combined[position+256:position+record-208],'benchmark exact raw payload bytes')
        position+=record
    pairs=[]
    for i in range(8):
        def cold_pair():return sum(observe(f'pair-{i:02}/baseline-{j}','baseline',j) for j in range(2))
        def shared():return observe(f'pair-{i:02}/session','session')
        if i%2:shared_time=shared();cold_time=cold_pair()
        else:cold_time=cold_pair();shared_time=shared()
        require(cold_time>0 and shared_time>0,'benchmark positive elapsed interval')
        pair={'pair':i,'order':'session-first' if i%2 else 'baseline-first',
            'baseline_seconds':cold_time,'session_seconds':shared_time,'ratio':shared_time/cold_time}
        pairs.append(pair);(directory/f'pair-{i:02}.json').write_text(json.dumps(pair,indent=2)+'\n')
    ratio=median(p['ratio'] for p in pairs);faster=sum(p['ratio']<1 for p in pairs)
    require(authenticate(baseline,ROOT,'virtual-frozen-grid-raw-update')==identities['baseline'] and
        authenticate(session,ROOT,'virtual-frozen-policy-session')==identities['session'],'benchmark build changed')
    require({n:(ROOT/n).read_bytes() for n in names}==source,'benchmark source changed')
    actual_cold=sum(warm_results['baseline',j]['work_actual'] for j in range(2))
    actual_shared=warm_results['session',None]['work_actual']
    result={'status':'measured','pairs':pairs,'median_ratio':ratio,'pairs_faster':faster,
        'timing_gate_passed':ratio<=0.96 and faster>=6,'observed_native_children':27,
        'all_numerical_wires_verified':True,'automatic_retries':0,'source_head':head,
        'baseline_sum_actual_work':actual_cold,'session_actual_work':actual_shared,
        'baseline_output_bytes':sum(len(warm['baseline',j]) for j in range(2)),
        'session_output_bytes':len(combined),'scope':protocol['scope']}
    (directory/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--baseline-executable',required=True,type=Path)
    parser.add_argument('--session-executable',required=True,type=Path);parser.add_argument('--output-directory',required=True,type=Path)
    args=parser.parse_args();print(json.dumps(benchmark(args.baseline_executable,args.session_executable,args.output_directory),indent=2))
