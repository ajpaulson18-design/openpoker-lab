"""Freeze complete source before a paired-mode conditional moment study."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from scripts.run_opponent_action_study import ROOT,closure,git,need

ROOTS=('scripts/run_opponent_action_moment_study.py','scripts/emit_opponent_action_moment_case.py',
       'tests/test_opponent_action_moments.py','tests/virtual_opponent_action_moments.py',
       'tests/virtual_opponent_action_worlds.py','tests/virtual_frozen_run_control.py')


def run(output):
    output=Path(output).resolve();need(output.parent==ROOT.parent.resolve(),'external sibling moment study required')
    sources=closure(ROOTS);need(not git('status','--porcelain','--untracked-files=all','--',*sources),'moment complete source must be committed and clean')
    head=git('rev-parse','HEAD').decode().strip()
    tree={line.split('\t',1)[1]:line.split('\t',1)[0].split()[2] for line in git('ls-tree','-r',head).decode().splitlines()}
    need(set(sources)<=set(tree),'moment missing captured source blob');output.mkdir(exist_ok=False)
    for name,raw in sources.items():
        path=output/'source'/name;path.parent.mkdir(exist_ok=True,parents=True);path.write_bytes(raw)
    identity={'head':head,'python_version':sys.version,'raw_sha256':{name:sha256(raw).hexdigest() for name,raw in sources.items()},
              'committed_blobs':{name:tree[name] for name in sources},'scope':'Original current committed checkout before numerical imports. No archive execution.'}
    (output/'source-identity.json').write_text(json.dumps(identity,indent=2)+'\n')
    from tests.virtual_opponent_action_worlds import plan,WIRE_LIMIT,SIDE_LIMIT,SUMMARY_LIMIT
    from tests.virtual_frozen_run_control import run_bounded_child
    protocol={'source_head':head,'complete_three_case_plan':plan(3),'case_indices':[0,1,2],
              'profiles':['uniform','visible-hash'],'schemes':['uniform-target-average','policy-role-average'],
              'modes':['normal','optimized'],'automatic_retries':0,'rng_calls':0,'native_calls':0,
              'scope':'Conditional named full52 worlds; selected-hand range witnesses. No full1326 moment law, native training or quality.'}
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    bootstrap="import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module(sys.argv.pop(1),run_name='__main__')"
    records=[];summaries={}
    for optimized in (False,True):
        mode='optimized' if optimized else 'normal'
        command=[sys.executable,'-I','-S','-B',*(['-O'] if optimized else []),'-c',bootstrap,str(ROOT)]
        receipt=run_bounded_child([*command,'unittest','tests.test_opponent_action_moments','-v'],b'',output/('tests-'+mode),
            stdout_limit=65536,stderr_limit=65536,timeout=300)
        records.append({'label':'tests','mode':mode,'receipt':receipt})
        need((receipt['status'],receipt['actual_exit_observed'],receipt['returncode'],receipt['failures'])==('exited',True,0,[]),
             'moment original controls failed; no retry')
        for index in range(3):
            child=output/f'case-{index}-{mode}'
            receipt=run_bounded_child([*command,'scripts.emit_opponent_action_moment_case','--case',str(index),
                '--witness-output',str(child/'witness.bin'),'--summary-output',str(child/'summary.json')],b'',child,
                stdout_limit=WIRE_LIMIT,stderr_limit=65536,timeout=300)
            records.append({'label':'case','case':index,'mode':mode,'receipt':receipt})
            need((receipt['status'],receipt['actual_exit_observed'],receipt['returncode'],receipt['failures'])==('exited',True,0,[]),
                 'moment original case failed; no retry')
            need((child/'stderr.bin').read_bytes()==b'' and (child/'witness.bin').stat().st_size<=SIDE_LIMIT and
                 (child/'summary.json').stat().st_size<=SUMMARY_LIMIT,'moment side output boundary')
            saved=json.loads((child/'summary.json').read_bytes());summaries[index,mode]=saved
            need(saved['wire_sha256']==sha256((child/'stdout.bin').read_bytes()).hexdigest() and
                 saved['witness_sha256']==sha256((child/'witness.bin').read_bytes()).hexdigest(),'moment complete original streams')
    for index in range(3):
        need(summaries[index,'normal']==summaries[index,'optimized'],'moment paired-mode summary equality')
        for name in ('stdout.bin','witness.bin'):
            need((output/f'case-{index}-normal'/name).read_bytes()==(output/f'case-{index}-optimized'/name).read_bytes(),
                 'moment paired-mode complete raw equality')
    need(git('rev-parse','HEAD').decode().strip()==head and all((ROOT/name).read_bytes()==raw for name,raw in sources.items()),
         'moment raw source drift during study')
    report={'status':'conditional-opponent-action-moments-study-complete','source_files':len(sources),'children':records,
            'cases':[summaries[index,'normal'] for index in range(3)],'complete_three_case_plan':protocol['complete_three_case_plan'],
            'native_calls':0,'rng_calls':0,'attempted_training':False,'quality_gate':None,
            'scope':'Paired-mode exact conditional first/second moments, raw policies and deterministic witnesses; no native sampler, global quality or realistic-game solve.'}
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    report=run(parser.parse_args().output)
    print(json.dumps({'status':report['status'],'source_files':report['source_files'],'cases':3,'native_calls':0,'attempted_training':False},indent=2))
