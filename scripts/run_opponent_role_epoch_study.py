"""Freeze complete source before original native role guards and independent math."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from scripts.run_opponent_action_study import ROOT,closure,git,need
from scripts.build_opponent_role_epoch import register,TARGET,SOURCES


def mutations(raw,verify):
    cases=(('root-regret','ROW both 1 0 0 0 ',7),('root-average','ROW both 1 0 0 0 ',8),
           ('root-policy','ROW both 1 0 0 0 ',9),('frozen-read-ledger','RECEIPT both ',4),
           ('resource-equation','FORECAST full ',2),('failed-commit','GUARD late-callback-error ',3))
    changed=[]
    for label,prefix,column in cases:
        lines=raw.decode('ascii').splitlines();index=next(i for i,line in enumerate(lines) if line.startswith(prefix))
        fields=lines[index].split();fields[column]=str(int(fields[column])+1);lines[index]=' '.join(fields)
        changed.append((label,('\n'.join(lines)+'\n').encode()))
    lines=raw.decode('ascii').splitlines();index=next(i for i,line in enumerate(lines) if line.startswith('ALIAS '))
    fields=lines[index].split();fields[3]=fields[2];lines[index]=' '.join(fields)
    changed.append(('collapsed-history',('\n'.join(lines)+'\n').encode()))
    for label,body in changed:
        try:verify(body)
        except ValueError:pass
        else:raise ValueError('role epoch altered frame accepted: '+label)
    return changed


def run(executable,output):
    executable=Path(executable).resolve();output=Path(output).resolve();register()
    need(output.parent==ROOT.parent.resolve() and not output.exists(),'role epoch fresh external evidence directory')
    names=closure(('scripts/run_opponent_role_epoch_study.py','tests/opponent_role_epoch_reference.py',
        'tests/test_native_exact_reach.py','tests/virtual_frozen_run_control.py'))
    for name in (*SOURCES,'third_party/boost-multiprecision-1.92.0/manifest.json',
                 'third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt','third_party/boost-multiprecision-1.92.0/headers.zip'):
        names[name]=(ROOT/name).read_bytes()
    need(not git('status','--porcelain','--untracked-files=all','--',*names),'role epoch complete study source committed')
    head=git('rev-parse','HEAD').decode().strip()
    tree={line.split('\t',1)[1]:line.split('\t',1)[0].split()[2] for line in git('ls-tree','-r',head).decode().splitlines()}
    output.mkdir()
    for name,raw in names.items():
        path=output/'source'/name;path.parent.mkdir(exist_ok=True,parents=True);path.write_bytes(raw)
    (output/'source-identity.json').write_text(json.dumps({'head':head,'raw_sha256':{n:sha256(b).hexdigest() for n,b in names.items()},
        'committed_blobs':{n:tree[n] for n in names}},indent=2)+'\n')
    from tests.test_native_exact_reach import authenticate,sha
    from tests.virtual_frozen_run_control import run_bounded_child
    from tests.opponent_role_epoch_reference import verify
    identity=authenticate(executable,ROOT,TARGET)
    invocation={'command':[str(executable)],'executable_sha256':sha(executable),
        'build_manifest_sha256':sha256(identity[0]).hexdigest(),'stdin_bytes':0,'automatic_retries':0,
        'python_optimized':sys.flags.optimize,'source_head':head}
    (output/'invocation.json').write_text(json.dumps(invocation,indent=2)+'\n')
    (output/'native-build-manifest.json').write_bytes(identity[0])
    receipt=run_bounded_child([str(executable)],b'',output/'native',stdout_limit=65536,stderr_limit=65536,timeout=180)
    need((receipt['status'],receipt['actual_exit_observed'],receipt['returncode'],receipt['failures'])==('exited',True,0,[]) and
         authenticate(executable,ROOT,TARGET)==identity,'role epoch original native exit/build identity')
    need((output/'native/stderr.bin').read_bytes()==b'','role epoch original native stderr')
    raw=(output/'native/stdout.bin').read_bytes();report=verify(raw);changed=mutations(raw,verify)
    (output/'mutations').mkdir()
    for label,body in changed:(output/'mutations'/(label+'.bin')).write_bytes(body)
    need(git('rev-parse','HEAD').decode().strip()==head and all((ROOT/n).read_bytes()==b for n,b in names.items()) and
         sha(executable)==identity[1]['executable_sha256'],'role epoch original source/executable drift')
    report={**report,'source_head':head,'source_files':len(names),'native_calls':1,'original_receipt':receipt,
        'output_sha256':sha256(raw).hexdigest(),'parser_mutations':len(changed),'mutation_labels':[label for label,_body in changed],
        'build_manifest_sha256':sha256(identity[0]).hexdigest(),'executable_sha256':identity[1]['executable_sha256'],
        'archived_source_executed':False}
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('executable',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();result=run(args.executable,args.output)
    print(json.dumps({k:v for k,v in result.items() if k!='original_receipt'},indent=2))
