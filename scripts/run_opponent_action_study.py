"""Capture committed source, then retain four original bounded Python children."""
import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
ROOTS=('scripts/run_opponent_action_study.py','scripts/forecast_opponent_action_sampling.py',
       'tests/test_opponent_action_sampling_forecast.py','tests/virtual_frozen_run_control.py')


def need(value,message):
    if not value:raise ValueError(message)


def git(*args):
    result=subprocess.run(['git',*args],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    need(result.returncode==0 and len(result.stdout)<=8<<20,'study read-only Git lookup');return result.stdout


def closure():
    pending=list(ROOTS);sources={}
    def module(parts):
        if not parts or parts[0] not in ('pokerlab','scripts','tests'):return
        for depth in range(1,len(parts)+1):
            path='/'.join(parts[:depth])+'/__init__.py'
            if (ROOT/path).is_file():pending.append(path)
        path='/'.join(parts)+'.py'
        if (ROOT/path).is_file():pending.append(path)
    while pending:
        name=pending.pop()
        if name in sources:continue
        path=ROOT/name;need(path.is_file() and not path.is_symlink() and path.stat().st_size<=2<<20,'study source member boundary')
        raw=path.read_bytes();sources[name]=raw
        need(len(sources)<=256 and sum(map(len,sources.values()))<=64<<20,'study source closure boundary')
        package=name[:-3].split('/')[:-1]
        for node in ast.walk(ast.parse(raw,filename=name)):
            if isinstance(node,ast.Import):
                for alias in node.names:module(alias.name.split('.'))
            elif isinstance(node,ast.ImportFrom):
                base=(package[:len(package)-node.level+1] if node.level else [])+(node.module.split('.') if node.module else [])
                module(base)
                for alias in node.names:
                    if alias.name!='*':module([*base,alias.name])
    return sources


def run(output):
    output=Path(output).resolve();need(output.parent==ROOT.parent.resolve(),'external sibling study evidence required')
    sources=closure();need(not git('status','--porcelain','--untracked-files=all','--',*sources),'study source must be committed and clean')
    head=git('rev-parse','HEAD').decode().strip()
    tree={line.split('\t',1)[1]:line.split('\t',1)[0].split()[2] for line in git('ls-tree','-r',head).decode().splitlines()}
    need(set(sources)<=set(tree),'study source missing from captured commit')
    output.mkdir(exist_ok=False)
    for name,raw in sources.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    identity={'head':head,'python_version':sys.version,'raw_sha256':{name:sha256(raw).hexdigest() for name,raw in sources.items()},
              'committed_blobs':{name:tree[name] for name in sources},'controller':'scripts/run_opponent_action_study.py',
              'scope':'Exact current checkout source bytes and normalized Git blob identities; no archived source execution.'}
    (output/'source-identity.json').write_text(json.dumps(identity,indent=2)+'\n')
    # Source identity is durable before a numerical module is imported.
    from tests.virtual_frozen_run_control import run_bounded_child
    bootstrap="import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module(sys.argv.pop(1),run_name='__main__')"
    records=[]
    for optimized in (False,True):
        mode='optimized' if optimized else 'normal'
        for label,module,args in (('tests','unittest',['tests.test_opponent_action_sampling_forecast','-v']),
                                  ('worksheet','scripts.forecast_opponent_action_sampling',[])):
            receipt=run_bounded_child([sys.executable,'-I','-S','-B',*(['-O'] if optimized else []),'-c',bootstrap,str(ROOT),module,*args],
                b'',output/(label+'-'+mode),stdout_limit=1<<20,stderr_limit=1<<20,timeout=90)
            records.append({'label':label,'mode':mode,'receipt':receipt})
            need((receipt['status'],receipt['actual_exit_observed'],receipt['returncode'],receipt['failures'])==('exited',True,0,[]),'study original child failed; no retry')
    normal=(output/'worksheet-normal/stdout.bin').read_bytes();optimized=(output/'worksheet-optimized/stdout.bin').read_bytes()
    need(normal==optimized,'study worksheet outputs differ across Python modes')
    need(git('rev-parse','HEAD').decode().strip()==head and
         all((ROOT/name).read_bytes()==raw for name,raw in sources.items()),'study raw source drift')
    report={'status':'opponent-proposal-structural-study-complete','source_files':len(sources),'children':records,
            'worksheet_sha256':sha256(normal).hexdigest(),'worksheet':json.loads(normal),'native_calls':0,'rng_calls':0,
            'attempted_training':False,'quality_gate':None,
            'scope':'Four bounded Python children with original exits and raw streams; mathematical worksheet only, not native admission or an update/variance/quality proof.'}
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    report=run(parser.parse_args().output)
    print(json.dumps({'status':report['status'],'source_files':report['source_files'],'worksheet_sha256':report['worksheet_sha256'],
                      'native_calls':0,'attempted_training':False},indent=2))
