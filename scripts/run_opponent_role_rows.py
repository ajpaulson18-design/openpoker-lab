"""Capture complete committed source before eight bounded native row calls."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from scripts.run_opponent_action_study import ROOT,closure,git,need
from scripts.build_opponent_role_rows import register,TARGET,SOURCES


def run(exe,output):
    exe=Path(exe).resolve();output=Path(output).resolve();register()
    need(output.parent==ROOT.parent.resolve() and not output.exists(),'role row fresh external evidence')
    names=closure(('scripts/run_opponent_role_rows.py','tests/opponent_role_row_reference.py',
                   'tests/test_native_exact_reach.py','tests/virtual_frozen_run_control.py'))
    for name in (*SOURCES,'third_party/boost-multiprecision-1.92.0/manifest.json',
                 'third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt','third_party/boost-multiprecision-1.92.0/headers.zip'):
        names[name]=(ROOT/name).read_bytes()
    need(not git('status','--porcelain','--untracked-files=all','--',*names),'role row complete source committed')
    head=git('rev-parse','HEAD').decode().strip()
    tree={line.split('\t',1)[1]:line.split('\t',1)[0].split()[2] for line in git('ls-tree','-r',head).decode().splitlines()}
    output.mkdir()
    for name,raw in names.items():
        path=output/'source'/name;path.parent.mkdir(exist_ok=True,parents=True);path.write_bytes(raw)
    (output/'source-identity.json').write_text(json.dumps({'head':head,'raw_sha256':{n:sha256(b).hexdigest() for n,b in names.items()},
        'committed_blobs':{n:tree[n] for n in names}},indent=2)+'\n')
    from tests.test_native_exact_reach import authenticate,sha
    from tests.virtual_frozen_run_control import run_bounded_child
    from tests.opponent_role_row_reference import request_rows,encode,verify
    identity=authenticate(exe,ROOT,TARGET);rows=request_rows();request=encode(rows)
    protocol={'head':head,'python_optimized':sys.flags.optimize,'native_calls':8,'automatic_retries':0,'rows':len(rows),
        'request_bytes':len(request),'request_sha256':sha256(request).hexdigest(),'request_cap':116000,'output_cap':131072,
        'transport':'Bounded regular external file; unchanged shared runner stdin cap. Full raw file bytes and command retained.',
        'scope':'Source/build-admitted compact/canonical row arithmetic. No role lease, History walk, RNG, learning, timing or quality.'}
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    (output/'row-origins.json').write_text(json.dumps([row['origin'] for row in rows],indent=2)+'\n')
    records=[]
    def call(label,payload,arguments=(),expected=0):
        need(authenticate(exe,ROOT,TARGET)==identity,'role row source/build before child')
        path=None
        if payload:
            need(len(payload)<=116000,'role row named file input cap');path=output/(label+'-payload.bin')
            with path.open('xb') as stream:stream.write(payload)
            need(not arguments,'role row explicit file transport arguments');arguments=('--request-file',str(path))
        receipt=run_bounded_child([str(exe),*arguments],b'',output/label,stdout_limit=131072,stderr_limit=65536,timeout=180)
        records.append({'label':label,'payload_sha256':sha256(payload).hexdigest(),'payload_bytes':len(payload),'receipt':receipt})
        need((receipt['status'],receipt['actual_exit_observed'],receipt['returncode'],receipt['failures'])==
             ('exited',True,expected,[]) and authenticate(exe,ROOT,TARGET)==identity and
             (path is None or path.read_bytes()==payload),'role row original child exit/source/input drift')
        raw=(output/label/'stdout.bin').read_bytes();err=(output/label/'stderr.bin').read_bytes()
        need((not err if expected==0 else bool(err) and not raw),'role row original streams')
        return raw
    guard=call('guards',b'',('--guards',))
    lines=guard.decode('ascii').splitlines()
    need(len(lines)==21 and all(x.startswith('GUARD ') and x.endswith(' PASS') for x in lines[:-1]) and
         lines[-1]=='OPPONENT_ROLE_ROW_GUARDS_V1 PASS 20','role row twenty native failure guards')
    raw=call('matrix',request);report=verify(raw,rows)
    bad=bytearray(request);bad[40:48]=(int.from_bytes(bad[40:48],'little')+1).to_bytes(8,'little')
    call('bad-grid',bytes(bad),expected=2)
    bad=bytearray(request);bad[32:40]=(3).to_bytes(8,'little');call('bad-step-count',bytes(bad),expected=2)
    k=len(rows[0]['initial']);start=40+8*k;bad=bytearray(request);bad[start:start+56]=(-(1<<447)).to_bytes(56,'little',signed=True)
    call('wide-regret',bytes(bad),expected=2)
    call('truncated',request[:-1],expected=2);call('trailing',request+b'\0',expected=2)
    call('unknown-argument',b'',('--unsupported',),expected=2)
    # Fresh Python decoder must reject a changed result coordinate too.
    changed=bytearray(raw);changed[40]^=1
    try:verify(bytes(changed),rows)
    except ValueError:pass
    else:raise ValueError('role row changed native result accepted')
    need(git('rev-parse','HEAD').decode().strip()==head and all((ROOT/n).read_bytes()==b for n,b in names.items()) and
         sha(exe)==identity[1]['executable_sha256'],'role row complete original source/executable drift')
    report={**report,'source_files':len(names),'source_head':head,'native_calls':len(records),'native_guard_refusals':20,
            'original_processes':records,'build_manifest_sha256':sha256(identity[0]).hexdigest(),
            'executable_sha256':identity[1]['executable_sha256'],'archived_source_executed':False}
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('executable',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();report=run(args.executable,args.output)
    print(json.dumps({k:v for k,v in report.items() if k!='original_processes'},indent=2))
