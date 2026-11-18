"""Authenticate and replay saved native read-only policy import observations.

The candidate executable and archived source are never executed. The active
independent oracle is authenticated before import; unrelated source may evolve.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path,PurePosixPath
import subprocess
import sys

from scripts.replay_frozen_grid_packet import ORACLE_SOURCES,source_checkout_hashes

ROOT=Path(__file__).resolve().parents[1]
PYTHON_SOURCES=(*ORACLE_SOURCES,'scripts/replay_frozen_grid_packet.py',
    'scripts/replay_native_frozen_policy_state.py','tests/virtual_frozen_policy_input_reference.py',
    'tests/test_native_frozen_policy_state.py')


def require(value,message):
    if not value:raise ValueError(message)


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def relative_name(name):
    require(type(name) is str,'source path type')
    path=PurePosixPath(name)
    require(bool(name) and str(path)==name and not path.is_absolute() and '..' not in path.parts and
            '\\' not in name and ':' not in name,'source path boundary')
    return name


def bounded(path,limit):
    require(path.is_file() and path.stat().st_size<=limit,'saved file byte boundary')
    with path.open('rb') as source:raw=source.read(limit+1)
    require(len(raw)<=limit,'saved file grew past bound');return raw


def unique(pairs):
    result={}
    for k,v in pairs:require(k not in result,'duplicate saved JSON key');result[k]=v
    return result


def read_json(path):return json.loads(bounded(path,1<<20),object_pairs_hook=unique)


def capture_sources(native_manifest):
    names=sorted(set(native_manifest['source_sha256'])|set(PYTHON_SOURCES)|
                 {'.github/workflows/native-frozen-policy-state.yml'})
    require(len(names)<=128,'introduced source count')
    for name in names:relative_name(name)
    require(not git('status','--porcelain','--untracked-files=all','--',*names),'commit introduced sources before observation')
    tree={}
    for line in git('ls-tree','-r','HEAD').splitlines():
        metadata,name=line.split('\t',1)
        if name in names:tree[name]=metadata.split()[2]
    require(set(tree)==set(names),'introduced source is not committed')
    hashes={name:sha256(bounded(ROOT/name,32<<20)).hexdigest() for name in names}
    require(all(hashes[name]==digest for name,digest in native_manifest['source_sha256'].items()),'build source closure differs')
    return {'version':'native-frozen-policy-sources-v1','head':git('rev-parse','HEAD'),
            'raw_sha256':hashes,'committed_blobs':tree,'python_version':sys.version,
            'python_executable_sha256':sha256(Path(sys.executable).read_bytes()).hexdigest()}


def save_sources(directory,identity):
    for name,digest in identity['raw_sha256'].items():
        raw=bounded(ROOT/name,32<<20);require(sha256(raw).hexdigest()==digest,'introduced source drift')
        target=directory/'source'/name;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as output:output.write(raw)
    with (directory/'source-identity.json').open('x',encoding='utf-8') as output:
        json.dump(identity,output,indent=2);output.write('\n')


def authenticate_sources(directory,native):
    saved=read_json(directory/'source-identity.json')
    require(saved['version']=='native-frozen-policy-sources-v1' and len(saved['raw_sha256'])<=128,'saved source identity')
    expected=set(native['source_sha256'])|set(PYTHON_SOURCES)|{'.github/workflows/native-frozen-policy-state.yml'}
    require(set(saved['raw_sha256'])==set(saved['committed_blobs'])==expected,'saved source closure membership')
    tree={}
    for line in git('ls-tree','-r',saved['head']).splitlines():
        metadata,name=line.split('\t',1);tree[name]=metadata.split()[2]
    total=0
    for name,digest in saved['raw_sha256'].items():
        relative_name(name);raw=bounded(directory/'source'/name,32<<20);total+=len(raw)
        require(total<=64<<20 and sha256(raw).hexdigest()==digest,'archived introduced source drift')
        require(name in tree and saved['committed_blobs'][name]==tree[name],'captured committed source closure drift')
        canonical=subprocess.check_output(['git','show',saved['head']+':'+name],cwd=ROOT)
        require(sha256(raw).hexdigest() in source_checkout_hashes(sha256(canonical).hexdigest(),canonical),
                'archived source differs from captured committed bytes')
    require(all(saved['raw_sha256'].get(name)==digest for name,digest in native['source_sha256'].items()),
            'native build source is not in captured closure')
    # Current candidate C++ may change. Only the actual Python oracle/codec
    # dependencies below execute during replay, so authenticate those now.
    current={}
    for name in PYTHON_SOURCES:
        require(name in saved['raw_sha256'],'missing Python replay dependency')
        raw=bounded(ROOT/name,2<<20);digest=sha256(raw).hexdigest()
        if digest!=saved['raw_sha256'][name]:
            canonical=subprocess.check_output(['git','show',saved['head']+':'+name],cwd=ROOT)
            require(digest in source_checkout_hashes(saved['raw_sha256'][name],canonical),'current oracle/codec source drift')
        current[name]=digest
    return saved,current


def replay(directory):
    directory=Path(directory).resolve()
    native=read_json(directory/'native-build-manifest.json')
    require(native['target']=='virtual-frozen-policy-state-controls' and native['scope']==
            'Frozen Q52 policy import/read conformance only; no update, training, solver or capacity acceptance.',
            'saved native build target/scope')
    identity=read_json(directory/'native-identity.json')
    require(identity['manifest_sha256']==sha256(bounded(directory/'native-build-manifest.json',1<<20)).hexdigest() and
            identity['executable_sha256']==native['executable_sha256'],'saved native executable identity')
    saved,before=authenticate_sources(directory,native)
    from tests.virtual_dyadic_training_reference import Fixture
    from tests.virtual_frozen_policy_input_reference import decode_snapshot,verify_snapshot_wire
    fixture=Fixture();results=[]
    for case in ('uniform','zero-skew'):
        input_raw=bounded(directory/(case+'.input.bin'),8<<20)
        input_identity=read_json(directory/case/'input-identity.json')
        require(input_identity=={'bytes':len(input_raw),'sha256':sha256(input_raw).hexdigest()},'saved snapshot input identity')
        process=read_json(directory/case/'process.json')
        require(process['status']=='exited' and type(process['returncode']) is int and process['returncode']==0 and
                process['actual_exit_observed'] is True and process['automatic_retries']==0 and not process['failures'],
                'saved candidate process did not complete')
        raw=bounded(directory/case/'stdout.bin',2_100_000);stderr=bounded(directory/case/'stderr.bin',65536)
        require(not stderr,'saved native stderr')
        require(len(process['streams'])==2,'saved native stream count')
        for report,body in zip(process['streams'],(raw,stderr)):
            require(report['saved_bytes']==report['observed_bytes']==len(body) and report['sha256']==sha256(body).hexdigest(),
                    'saved native stream identity')
        policy=decode_snapshot(fixture,input_raw)
        results.append({'case':case,**verify_snapshot_wire(fixture,policy,raw)})
    require(authenticate_sources(directory,native)==(saved,before),'replay source changed during verification')
    return {'status':'exact','candidate_calls':0,'archived_code_executed':False,'source_head':saved['head'],
            'introduced_sources_authenticated':len(saved['raw_sha256']),'current_python_sources_authenticated':len(before),
            'results':results,'scope':'saved read-only import conformance; no raw update, training or quality acceptance'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    print(json.dumps(replay(parser.parse_args().directory),indent=2))
