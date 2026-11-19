"""Authenticate saved provisional native envelopes, then use current math.

The current entrypoint and metadata bootstrap are trusted active code. Archived
code is evidence only; no native candidate or archived Python is executed.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from scripts.replay_native_frozen_policy_state import (
    HISTORICAL_MIXED,ORACLE_SOURCES,bounded,read_json,relative_name,require,source_checkout_hashes,
)

ROOT=Path(__file__).resolve().parents[1]
MATH=(*ORACLE_SOURCES,'tests/virtual_frozen_grid_preflight_reference.py','tests/virtual_frozen_grid_envelope_reference.py')
CONTROLLER=('scripts/replay_native_frozen_policy_state.py','tests/test_native_frozen_grid_preflight.py')


def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def source_identity(directory,native):
    saved=read_json(directory/'source-identity.json')
    require(type(saved['head']) is str and len(saved['head'])==40 and all(c in '0123456789abcdef' for c in saved['head']),
            'captured envelope source commit grammar')
    require(saved['version']=='frozen-grid-envelope-source-v1','envelope source identity version')
    names=set(native['source_sha256'])|set(MATH)|set(CONTROLLER)
    require(len(names)<=128 and set(saved['raw_sha256'])==set(saved['committed_blobs'])==names,'envelope complete source closure')
    tree={}
    for line in git('ls-tree','-r',saved['head']).splitlines():
        metadata,name=line.split('\t',1);tree[name]=metadata.split()[2]
    total=0
    for name,digest in saved['raw_sha256'].items():
        relative_name(name);raw=bounded(directory/'source'/name,32<<20);total+=len(raw)
        require(total<=64<<20 and sha256(raw).hexdigest()==digest,'archived envelope source drift')
        require(name in tree and saved['committed_blobs'][name]==tree[name],'envelope captured Git blob drift')
        canonical=subprocess.check_output(['git','show',saved['head']+':'+name],cwd=ROOT)
        require(digest in source_checkout_hashes(sha256(canonical).hexdigest(),canonical) or
                HISTORICAL_MIXED.get(name)==(digest,tree[name]),'envelope archived raw/blob mismatch')
    require(all(saved['raw_sha256'][name]==digest for name,digest in native['source_sha256'].items()),'envelope build/source link')
    current={}
    for name in MATH:
        digest=sha256(bounded(ROOT/name,2<<20)).hexdigest()
        canonical=subprocess.check_output(['git','show',saved['head']+':'+name],cwd=ROOT)
        require(digest in source_checkout_hashes(saved['raw_sha256'][name],canonical),'current envelope oracle drift')
        current[name]=digest
    # Current metadata entrypoints may evolve independently of frozen math.
    for name in ('scripts/replay_frozen_grid_envelope.py','scripts/replay_native_frozen_policy_state.py'):
        require(not git('status','--porcelain','--',name),'uncommitted active envelope bootstrap')
        canonical=subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT)
        digest=sha256(bounded(ROOT/name,2<<20)).hexdigest()
        require(digest in source_checkout_hashes(sha256(canonical).hexdigest(),canonical),'active envelope bootstrap drift')
        current[name]=digest
    return saved,current


def replay(directory):
    directory=Path(directory);native=read_json(directory/'native-build-manifest.json')
    identity=read_json(directory/'native-identity.json')
    require(identity=={'manifest_sha256':sha256(bounded(directory/'native-build-manifest.json',1<<20)).hexdigest(),
                      'executable_sha256':native['executable_sha256']},'envelope native build identity')
    require(native['target']=='virtual-frozen-grid-update-preflight' and native['scope']==
        'Provisional frozen Q52 raw-update architecture envelope only; no policy import, ranking, contraction, update, training or capacity admission.',
        'envelope native target/scope')
    saved,before=source_identity(directory,native)
    command=read_json(directory/'command.json')
    require(command==[native['executable']],'envelope invocation identity')
    process=read_json(directory/'process.json')
    require(process['status']=='exited' and type(process['returncode']) is int and process['returncode']==0 and
            process['actual_exit_observed'] is True and process['automatic_retries']==0 and not process['failures'],'envelope actual exit')
    require(not bounded(directory/'request.bin',0) and process['request_sha256']==sha256(b'').hexdigest(),'envelope empty stdin')
    raw=bounded(directory/'stdout.bin',2_100_000);stderr=bounded(directory/'stderr.bin',65536)
    require(not stderr and len(process['streams'])==2,'envelope streams')
    for report,body in zip(process['streams'],(raw,stderr)):
        require(report['observed_bytes']==report['saved_bytes']==len(body) and report['sha256']==sha256(body).hexdigest(),'envelope stream identity')
    from tests.virtual_frozen_grid_envelope_reference import verify_wire
    result=verify_wire(raw)
    require(source_identity(directory,native)==(saved,before),'envelope replay source changed')
    return {**result,'candidate_calls':0,'archived_source_executed':False,'observed_source_head':saved['head'],
            'active_replay_head':git('rev-parse','HEAD'),'active_source_sha256':before,
            'native_executable_sha256':native['executable_sha256'],
            'invocation_receipt':'captured controller command/exit; not an independent execution attestation'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    print(json.dumps(replay(parser.parse_args().directory),indent=2))
