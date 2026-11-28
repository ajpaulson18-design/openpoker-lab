"""Freeze source, generate one independent T2 request, retain original native exits."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import struct
import sys
from scripts.run_opponent_action_study import ROOT, closure, git, need
from scripts.build_frozen_role_walk import register, TARGET, CONTROLS, SOURCES


def run(executable,controls,output,profile,selectors,rule):
    executable=Path(executable).resolve();controls=Path(controls).resolve();output=Path(output).resolve();register()
    need(output.parent==ROOT.parent.resolve() and not output.exists(),'role walk fresh external study directory')
    names=closure(('scripts/run_frozen_role_walk_study.py','scripts/run_frozen_role_walk_matrix.py','tests/virtual_role_walk_wire_reference.py',
        'tests/test_native_exact_reach.py','tests/virtual_frozen_run_control.py'))
    for name in (*SOURCES[TARGET],*SOURCES[CONTROLS],
        'third_party/boost-multiprecision-1.92.0/manifest.json',
        'third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt','third_party/boost-multiprecision-1.92.0/headers.zip'):
        names[name]=(ROOT/name).read_bytes()
    need(not git('status','--porcelain','--untracked-files=all','--',*names),'role walk study complete source committed')
    head=git('rev-parse','HEAD').decode().strip()
    tree={line.split('\t',1)[1]:line.split('\t',1)[0].split()[2] for line in git('ls-tree','-r',head).decode().splitlines()}
    output.mkdir()
    for name,body in names.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
    (output/'source-identity.json').write_text(json.dumps({'head':head,'python_version':sys.version,
        'python_optimized':sys.flags.optimize,'raw_sha256':{n:sha256(b).hexdigest() for n,b in names.items()},
        'committed_blobs':{n:tree[n] for n in names}},indent=2)+'\n')
    # Complete committed bytes are durable before numerical imports/preparation.
    from tests.test_native_exact_reach import authenticate,sha
    from tests.virtual_frozen_run_control import run_bounded_child
    from tests.virtual_role_walk_reference import Context,INPUT,OUTPUT
    from tests.virtual_role_walk_wire_reference import (verify_controls,parse,receipts,compare,request_tapes)
    identities={target:authenticate(path,ROOT,target) for target,path in ((TARGET,executable),(CONTROLS,controls))}
    for target,identity in identities.items():(output/(target+'-build.json')).write_bytes(identity[0])
    processes=[]
    def invoke(label,path,target,args=(),success=True,cap=OUTPUT):
        invocation={'command':[str(path),*map(str,args)],'executable_sha256':sha(path),'stdin_bytes':0,
            'source_head':head,'build_manifest_sha256':sha256(identities[target][0]).hexdigest(),
            'automatic_retries':0,'python_optimized':sys.flags.optimize}
        (output/(label+'-invocation.json')).write_text(json.dumps(invocation,indent=2)+'\n')
        receipt=run_bounded_child(invocation['command'],b'',output/label,stdout_limit=cap,stderr_limit=65536,timeout=180)
        processes.append({'label':label,'target':target,'receipt':receipt})
        need((receipt['status'],receipt['actual_exit_observed'],receipt['returncode'],receipt['failures'])==
            ('exited',True,0 if success else 2,[]) and authenticate(path,ROOT,target)==identities[target],
            'role walk original native exit/build identity: '+label)
        raw=(output/label/'stdout.bin').read_bytes();error=(output/label/'stderr.bin').read_bytes()
        need((not error if success else bool(error) and not raw),'role walk private success/rejection streams: '+label)
        return raw
    scalar=verify_controls(invoke('controls',controls,CONTROLS,cap=65536))
    ctx=Context(profile,selectors,rule);ctx.run();request=ctx.request()
    need(len(request)<=INPUT,'role walk full request I/O');path=output/'request.bin';path.write_bytes(request)
    protocol={'profile':profile,'selectors':selectors,'rule':rule,'request_sha256':sha256(request).hexdigest()}
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    state=[]
    for record in ctx.records:
        state.append({'roots':[s['root'] for s in record['samples']],'counts':record['counts'],'raw':record['raw'],
            'snapshot':[(public,*record['numeric'][key],record['policy'].get(key))
                for public,(key,_,_) in ctx.transport.items() if key in record['numeric']]})
    (output/'independent-state.json').write_text(json.dumps(state,indent=2)+'\n')
    raw=invoke('native',executable,TARGET,(path,))
    tapes=request_tapes(request,profile,selectors);records=parse(raw,profile,selectors,tapes);receipts(records)
    report=compare(records,request,ctx,ctx.admission,len(raw))
    # Framing, forecast, root, and committed numeric corruptions are distinct.
    changed=[('truncated',raw[:-1]),('trailing',raw+b'\0')]
    for label,offset in (('forecast',8+13*8),('target-root',280+8+18*8),
                         ('committed-regret',raw.index(b'OPLRSN01')+8+24+40)):
        body=bytearray(raw);body[offset]^=1;changed.append((label,bytes(body)))
    (output/'mutations').mkdir()
    for label,body in changed:
        (output/'mutations'/(label+'.bin')).write_bytes(body)
        try:
            altered=parse(body,profile,selectors,tapes);receipts(altered);compare(altered,request,ctx,ctx.admission,len(body))
        except ValueError:pass
        else:raise ValueError('role walk altered evidence accepted: '+label)
    bad=[]
    for label,index,value in (('version',0,2),('profile',1,2),('lifetime',2,3),
        ('private-selector',3,(1624350,25908876)[profile]),('board-selector',4,34246080),
        ('ticket-extent',7,205),('ticket-Q',11,1<<52)):
        body=bytearray(request);struct.pack_into('<Q',body,8+8*index,value);bad.append((label,bytes(body)))
    bad.extend((('trailing',request+b'\0'),('oversize',b'\0'*(INPUT+1))))
    # Missing/excess tapes fail inside the walk. Neither may publish even a
    # partial first epoch; all success bytes remain private until both commit.
    body=bytearray(request);count=struct.unpack_from('<Q',body,8+7*8)[0]
    need(count>0,'role walk short-tape witness');struct.pack_into('<Q',body,8+7*8,count-1)
    del body[96+8*(count-1):96+8*count];bad.append(('short-tape',bytes(body)))
    body=bytearray(request);struct.pack_into('<Q',body,8+7*8,count+1)
    body[96+8*count:96+8*count]=b'\0'*8;bad.append(('excess-tape',bytes(body)))
    for label,body in bad:
        path=output/(label+'-request.bin');path.write_bytes(body)
        invoke('reject-'+label,executable,TARGET,(path,),success=False)
    need(git('rev-parse','HEAD').decode().strip()==head and all((ROOT/n).read_bytes()==b for n,b in names.items()),
        'role walk study raw source/head drift')
    result={**report,'source_head':head,'source_files':len(names),'scalar_controls':scalar,
        'output_sha256':sha256(raw).hexdigest(),'parser_mutations':len(changed),'native_rejections':len(bad),
        'native_calls':len(processes),'processes':processes,'archived_source_executed':False}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('executable',type=Path);p.add_argument('controls',type=Path)
    p.add_argument('output',type=Path);p.add_argument('--profile',type=int,choices=(0,1),default=0)
    p.add_argument('--selectors',type=int,nargs=4,default=(0,0,0,0));p.add_argument('--rule',choices=('first','last','middle','alternating'),default='first')
    a=p.parse_args();s=tuple(tuple(a.selectors[i:i+2]) for i in (0,2))
    result=run(a.executable,a.controls,a.output,a.profile,s,a.rule)
    print(json.dumps({k:v for k,v in result.items() if k!='processes'},indent=2))
