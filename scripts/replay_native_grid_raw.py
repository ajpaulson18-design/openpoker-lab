"""Authenticate a complete saved raw matrix before current independent math.

Current entrypoints/metadata bootstrap are trusted code. Archived source is
authenticated evidence only and is never imported or executed.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path,PureWindowsPath
import subprocess

from scripts.replay_native_frozen_policy_state import (
    HISTORICAL_MIXED,ORACLE_SOURCES,bounded,read_json,relative_name,require,source_checkout_hashes,
)

ROOT=Path(__file__).resolve().parents[1]
MATH=(*ORACLE_SOURCES,'tests/virtual_frozen_policy_input_reference.py',
    'tests/virtual_frozen_grid_preflight_reference.py','tests/virtual_frozen_grid_envelope_reference.py',
    'tests/virtual_grid_update_reference.py','tests/virtual_frozen_sample_reference.py','tests/virtual_native_grid_raw_reference.py')
CONTROLLERS=('scripts/replay_native_frozen_policy_state.py','tests/test_native_frozen_grid_raw.py')
SCOPE='Fixed-policy Q52 per-board raw values/regrets/averages study only; no clipping, State update, sampled training, quality or wider capacity acceptance.'


def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def sources(directory,native,*,math_sources=MATH,controllers=CONTROLLERS,
            version='native-frozen-grid-raw-sources-v1',
            bootstrap=('scripts/replay_native_grid_raw.py','scripts/replay_native_frozen_policy_state.py')):
    saved=read_json(directory/'source-identity.json');head=saved['head']
    require(type(head) is str and len(head)==40 and all(c in '0123456789abcdef' for c in head),'raw captured source commit grammar')
    expected=set(native['source_sha256'])|set(math_sources)|set(controllers)
    require(saved['version']==version and len(expected)<=128 and
            set(saved['raw_sha256'])==set(saved['committed_blobs'])==expected,'raw complete introduced-source closure')
    tree={}
    for line in git('ls-tree','-r',head).splitlines():
        metadata,name=line.split('\t',1);tree[name]=metadata.split()[2]
    total=0
    for name,digest in saved['raw_sha256'].items():
        relative_name(name);raw=bounded(directory/'source'/name,32<<20);total+=len(raw)
        require(total<=64<<20 and sha256(raw).hexdigest()==digest,'raw archived source drift')
        require(name in tree and saved['committed_blobs'][name]==tree[name],'raw captured Git blob drift')
        canonical=subprocess.check_output(['git','show',head+':'+name],cwd=ROOT)
        require(digest in source_checkout_hashes(sha256(canonical).hexdigest(),canonical) or
                HISTORICAL_MIXED.get(name)==(digest,tree[name]),'raw archived committed-byte mismatch')
    require(all(saved['raw_sha256'][n]==digest for n,digest in native['source_sha256'].items()),'raw native build/source link')
    current={}
    for name in math_sources:
        canonical=subprocess.check_output(['git','show',head+':'+name],cwd=ROOT)
        digest=sha256(bounded(ROOT/name,2<<20)).hexdigest()
        require(digest in source_checkout_hashes(saved['raw_sha256'][name],canonical),'current raw oracle drift')
        current[name]=digest
    for name in bootstrap:
        require(not git('status','--porcelain','--',name),'uncommitted active raw replay bootstrap')
        canonical=subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT)
        digest=sha256(bounded(ROOT/name,2<<20)).hexdigest()
        require(digest in source_checkout_hashes(sha256(canonical).hexdigest(),canonical),'active raw bootstrap drift')
        current[name]=digest
    return saved,current


def process(directory,expected_code):
    receipt=read_json(directory/'process.json')
    require(receipt['status']=='exited' and type(receipt['returncode']) is int and receipt['returncode']==expected_code and
            receipt['actual_exit_observed'] is True and receipt['automatic_retries']==0 and not receipt['failures'],'raw observed process outcome')
    require(not bounded(directory/'request.bin',0) and receipt['request_sha256']==sha256(b'').hexdigest(),'raw empty stdin identity')
    raw=bounded(directory/'stdout.bin',2_100_000);stderr=bounded(directory/'stderr.bin',65536)
    require(len(receipt['streams'])==2,'raw process stream count')
    for entry,body in zip(receipt['streams'],(raw,stderr)):
        require(entry['observed_bytes']==entry['saved_bytes']==len(body) and entry['sha256']==sha256(body).hexdigest(),'raw saved stream identity')
    require((not stderr if expected_code==0 else not raw and bool(stderr)),'raw successful/rejected output boundary')
    return raw


def replay(directory):
    directory=Path(directory);native=read_json(directory/'native-build-manifest.json')
    require(native['target']=='virtual-frozen-grid-raw-update' and native['scope']==SCOPE,'raw native target/scope')
    require(read_json(directory/'native-identity.json')=={
        'manifest_sha256':sha256(bounded(directory/'native-build-manifest.json',1<<20)).hexdigest(),
        'executable_sha256':native['executable_sha256']},'raw native build identity')
    saved,before=sources(directory,native)
    # Only after full archived/current source authentication do numeric modules
    # execute. No archived source directory is added to the import path.
    from tests.virtual_dyadic_training_reference import Fixture
    from tests.virtual_frozen_policy_input_reference import decode_snapshot,encode_snapshot,profile
    from tests.virtual_grid_update_reference import build_sampled_reference_context,admit_sampled_board
    from tests.virtual_frozen_grid_envelope_reference import envelope
    from tests.virtual_native_grid_raw_reference import verify_raw_wire
    fixture=Fixture();context=build_sampled_reference_context()
    inputs={};policies={}
    for name in ('uniform','zero-skew'):
        body=bounded(directory/('input-'+name+'.bin'),8<<20)
        policies[name]=decode_snapshot(fixture,body)
        require(policies[name]==profile(fixture,name),'raw matrix named policy mismatch');inputs[name]=body
    plan=read_json(directory/'case-plan.json')
    require(plan['scope']=='twenty independent bounded native requests; not one training admission' and
            plan['per_request_work_ceiling']==500_000_000 and plan['automatic_retries']==0 and len(plan['cases'])==20,'raw matrix request scope')
    labels=set();coverage=Counter();pairs={};zero_types={};results=[];forecast_sum=0
    for case in plan['cases']:
        require(type(case) is list and len(case)==4,'raw case metadata shape')
        label,name,law,cards=case;relative_name(label)
        require('/' not in label and label not in labels and name in policies and law in ('uniform','river_weighted'),'raw unique case/profile/law')
        labels.add(label);board=tuple(cards);e=envelope(board);forecast_sum+=e[12]
        require(e[18]==1 and e[12]<=plan['per_request_work_ceiling'],'raw independently feasible per-request envelope')
        prefix=name+'-'+law+'-'
        require(label.startswith(prefix) and label[len(prefix):] in {'positive-0','positive-1','positive-2','zero-shared-turn','zero-at-flop'},
                'raw named matrix selector')
        coverage[name,law]+=1
        admission=admit_sampled_board(context,board,law)
        if admission.compatible_pairs:pairs.setdefault((name,law),set()).update(admission.compatible_pairs)
        else:zero_types.setdefault((name,law),set()).add('preflop-only' if e[0]==12 else 'later-prefix')
        command=read_json(directory/(label+'.command.json'))
        require(type(command) is list and len(command)==8 and command[0]==native['executable'] and
                PureWindowsPath(command[1]).name=='input-'+name+'.bin' and command[2:]==[law,*map(str,board)],'raw saved invocation identity')
        child=directory/label
        require(read_json(child/'input-identity.json')=={'file':'input-'+name+'.bin','bytes':len(inputs[name]),'sha256':sha256(inputs[name]).hexdigest()},
                'raw input byte identity')
        raw=process(child,0)
        results.append({'case':label,**verify_raw_wire(fixture,context,policies[name],board,law,raw)})
    require(forecast_sum==plan['sum_case_request_forecasts'] and
            forecast_sum<=20*plan['per_request_work_ceiling'],'raw complete study work reservation')
    for name in policies:
        for law in ('uniform','river_weighted'):
            require(coverage[name,law]==5 and len(pairs.get((name,law),()))==3 and zero_types.get((name,law))=={'preflop-only','later-prefix'},
                    'raw matrix physical-pair and zero-prefix coverage')
    first=plan['cases'][0]
    require(first[1:3]==['uniform','uniform'] and first[0]=='uniform-uniform-positive-0','raw first matrix selector')
    board=tuple(first[3]);cards=list(map(str,board))
    negative_args={
        'reject-law':['foreign',*cards],
        'reject-duplicate':['uniform',*cards[:4],cards[3]],
        'reject-foreign-card':['uniform','0',*cards[1:]],
        'reject-unsorted-flop':['uniform',cards[1],cards[0],*cards[2:]],
        'reject-arity':['uniform'],
        'reject-late-partition':['uniform',*cards],
    }
    for label,args in negative_args.items():
        command=read_json(directory/(label+'.command.json'))
        filename='input-late-zero.bin' if label=='reject-late-partition' else 'input-uniform.bin'
        require(type(command) is list and len(command)==2+len(args) and command[0]==native['executable'] and
                PureWindowsPath(command[1]).name==filename and command[2:]==args,'raw rejection invocation')
        process(directory/label,2)
    encoded,_,layout=encode_snapshot(fixture,policies['uniform']);require(encoded==inputs['uniform'],'raw canonical input roundtrip')
    bad=bytearray(encoded);bad[layout['last_units']:layout['last_units']+8*layout['last_width']]=b'\0'*(8*layout['last_width'])
    require(bounded(directory/'input-late-zero.bin',8<<20)==bytes(bad),'raw late partition control identity')
    require(sources(directory,native)==(saved,before),'raw replay source changed')
    return {'status':'all-raw-rows-exact','cases':results,'successful_observed_requests':20,'rejected_observed_requests':6,
        'candidate_calls':0,'archived_source_executed':False,'observed_source_head':saved['head'],'active_replay_head':git('rev-parse','HEAD'),
        'active_python_sha256':before,'native_executable_sha256':native['executable_sha256'],
        'scope':'fixed-policy raw replay only; no clipping, State update, sampled training, quality or wider capacity acceptance',
        'invocation_receipts':'captured controller commands/exits; not independent execution attestations'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    print(json.dumps(replay(parser.parse_args().directory),indent=2))
