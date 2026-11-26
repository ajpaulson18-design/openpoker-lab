"""Authenticate original sources/bytes/exits before fresh conditional math."""
import argparse
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]
PACKET=ROOT/'benchmarks/results/opponent-action-moments-v1'
PIN=(1522,'d6f13fa577ea5f7c8fa0096508dcd33b4cf1f0fe72d9e90adb34a23abdb72988')
ORIGIN='a8df89a33eda4399aa420d60f9fde3b10947b746'
BOOTSTRAP=('scripts/replay_opponent_action_moments.py','scripts/opponent_action_moment_frame.py',
           'scripts/run_opponent_action_study.py')


def replay(packet=PACKET):
    from scripts import replay_joint_cycles_packet as base,joint_evidence_archive as archive
    from scripts import replay_joint_two_epoch_packet as helper,replay_single_pass_packet as known
    from scripts.opponent_action_moment_frame import parse
    from scripts.run_opponent_action_study import closure
    need=base.need;digest=lambda raw:sha256(raw).hexdigest()
    def bootstrap():
        prior=base.bootstrap();hashes={}
        need(not base.git('status','--porcelain','--untracked-files=all','--',*BOOTSTRAP),'moment committed reader closure')
        for name in BOOTSTRAP:
            raw=archive.read(ROOT/name)
            need(digest(raw) in base.variants(base.git('show',prior[0]+':'+name)),'moment reader source drift')
            hashes[name]=digest(raw)
        return prior,hashes
    before=bootstrap()
    need(not any(n=='tests' or n.startswith(('tests.','pokerlab')) for n in sys.modules),'moment fresh numerical process')
    def load():return archive.load(packet,helper,pin=PIN,version='opponent-moments',
        labels=('observations','builds','objects'),packager='package_opponent_moments1.py.txt')
    manifest,loaded,pins=load();files=loaded['observations'];objects=helper.GitObjects()
    identity=helper.decode(files['study/source-identity.json']);hashes=identity['raw_sha256']
    need(identity['head']==ORIGIN and len(hashes)==28 and set(hashes)==set(identity['committed_blobs']) and
         {n[len('study/source/'):] for n in files if n.startswith('study/source/')}==set(hashes),
         'moment complete original 28-file source closure')
    for name,expected in hashes.items():
        raw=files['study/source/'+helper.safe_name(name)];blob=objects.tree(ORIGIN).get(name)
        need(digest(raw)==expected and identity['committed_blobs'][name]==blob and
             (helper.source_bytes_match(raw,objects.body(ORIGIN,name),name,blob) or
              known.HISTORICAL_CHECKOUTS.get(name)==(expected,blob)),'moment original raw/Git source identity')
    processes,_=helper.process_receipts(files)
    expected_prefixes={f'study/{label}-{mode}' for mode in ('normal','optimized') for label in ('tests','case-0','case-1','case-2')}
    need(set(processes)==expected_prefixes and all(p['exit']==0 for p in processes.values()),'moment original eight Python exits')
    saved=helper.decode(files['study/result.json']);protocol=helper.decode(files['study/protocol.json'])
    need((saved['status'],saved['source_files'],saved['native_calls'],saved['rng_calls'],saved['attempted_training'],saved['quality_gate'])==
         ('conditional-opponent-action-moments-study-complete',28,0,0,False,None) and
         protocol['source_head']==ORIGIN and protocol['automatic_retries']==0 and
         protocol['case_indices']==[0,1,2] and protocol['modes']==['normal','optimized'] and
         protocol['complete_three_case_plan']==saved['complete_three_case_plan'],'moment complete original controller protocol')
    children=[];reports=[];layouts=[]
    for mode in ('normal','optimized'):
        for label in ('tests','case-0','case-1','case-2'):
            prefix=f'study/{label}-{mode}';receipt=helper.decode(files[prefix+'/process.json'])
            children.append({'label':'tests','mode':mode,'receipt':receipt} if label=='tests' else
                            {'label':'case','case':int(label[-1]),'mode':mode,'receipt':receipt})
            if label=='tests':
                need(files[prefix+'/stdout.bin']==b'' and b'Ran 8 tests' in files[prefix+'/stderr.bin'] and
                     b'\nOK' in files[prefix+'/stderr.bin'],'moment original independent controls');continue
            report=helper.decode(files[prefix+'/summary.json']);index=int(label[-1])
            wire=files[prefix+'/stdout.bin'];side=files[prefix+'/witness.bin']
            need(report['case']==index and report==saved['cases'][index] and files[prefix+'/stderr.bin']==b'' and
                 (report['wire_bytes'],report['wire_sha256'],report['witness_bytes'],report['witness_sha256'])==
                 (len(wire),digest(wire),len(side),digest(side)),'moment all original case bytes')
            layout=parse(wire,side,report)
            if mode=='normal':reports.append(report);layouts.append(layout)
            else:
                for name in ('stdout.bin','witness.bin','summary.json'):
                    need(files[prefix+'/'+name]==files[f'study/{label}-normal/'+name],'moment original paired-mode byte identity')
    need(saved['children']==children,'moment exact original child inventory')
    def current_math():
        need(not (ROOT/'tests/__init__.py').exists() and not (ROOT/'scripts/__init__.py').exists(),'moment namespace identity')
        sources=closure(('tests/test_opponent_action_moments.py',))
        need(len(sources)==25 and set(sources)==set(hashes)-{'scripts/run_opponent_action_moment_study.py',
             'scripts/emit_opponent_action_moment_case.py','scripts/run_opponent_action_study.py'} and
             not base.git('status','--porcelain','--untracked-files=all','--',*sources),'moment current complete mathematical closure')
        for name,raw in sources.items():
            blob=objects.tree(ORIGIN)[name]
            need(helper.source_bytes_match(raw,objects.body(ORIGIN,name),name,blob) or
                 known.HISTORICAL_CHECKOUTS.get(name)==(digest(raw),blob),'moment current mathematical source drift: '+name)
        return {name:digest(raw) for name,raw in sources.items()}
    math_before=current_math();previous=sys.pycache_prefix,sys.dont_write_bytecode
    with TemporaryDirectory(prefix='opponent-moments-empty-cache-',dir=ROOT.parent) as cache:
        sys.pycache_prefix=cache;sys.dont_write_bytecode=True
        try:
            from tests.virtual_opponent_action_worlds import run_case,plan
            from tests import test_opponent_action_moments as controls
            need(plan(3)==saved['complete_three_case_plan'],'moment unchanged complete study admission')
            for index in range(3):
                wire,report,_visibility,side=run_case(index)
                report={**report,'wire_bytes':len(wire),'wire_sha256':digest(wire),
                        'witness_bytes':len(side),'witness_sha256':digest(side)}
                need(helper.decode(json.dumps(report).encode())==reports[index] and
                     wire==files[f'study/case-{index}-normal/stdout.bin'] and
                     side==files[f'study/case-{index}-normal/witness.bin'],'moment fresh complete raw/second/witness replay')
            result=unittest.TextTestRunner(stream=StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(controls))
            need(result.testsRun==8 and result.wasSuccessful() and not result.skipped,'moment fresh eight independent controls')
            executed=[]
            for name in math_before:
                module=name[:-3].replace('/','.');module=module[:-9] if module.endswith('.__init__') else module
                imported=sys.modules.get(module)
                if imported is not None:
                    need(Path(imported.__file__).resolve()==(ROOT/name).resolve(),'moment current import identity: '+name)
                    executed.append(name)
            need({'tests/test_opponent_action_moments.py','tests/virtual_opponent_action_moments.py',
                  'tests/virtual_opponent_action_worlds.py'}<=set(executed),'moment required current references executed')
            need(bootstrap()==before and current_math()==math_before and load()[2]==pins,'moment final evidence/source drift')
            return {'status':'conditional-opponent-action-moments-replayed','original_source_head':ORIGIN,
                'original_source_files':28,'current_mathematical_files':25,'executed_current_files':sorted(executed),
                'original_python_children':8,'fresh_tests':8,
                'layouts':layouts,'cases':reports,'native_calls':0,'rng_calls':0,'archived_source_executed':False,
                'attempted_training':False,'quality_gate':None,'stored_expanded_bytes':manifest['stored_expanded_bytes'],
                'scope':'Exact conditional first/second R/A moments and deterministic transcript factors for three named full52 worlds. No full1326 moment-law admission, native sampler, timing, convergence or quality.'}
        finally:sys.pycache_prefix,sys.dont_write_bytecode=previous


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('packet',nargs='?',type=Path,default=PACKET)
    print(json.dumps(replay(parser.parse_args().packet),indent=2))
