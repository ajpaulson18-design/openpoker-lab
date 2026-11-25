"""Admit immutable source/process evidence before current structural math."""
import argparse
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]
PACKET=ROOT/'benchmarks/results/opponent-action-study-v1'
PIN=(1866,'ae2152a69f96873226949f695e73d45ffdbf45145cd73a9d67576f55fc381c9c')
ORIGINS={'first-refusal':'4d973b27e849592bd13875764ef22dd61747ccc1','completed':'37a8ebeaaae4b6da68f08b62a83410ffe8b3ff04'}
MATH=('scripts/forecast_opponent_action_sampling.py','tests/test_opponent_action_sampling_forecast.py',
      'tests/virtual_frozen_update_reference.py','tests/virtual_betting_template_reference.py',
      'scripts/preflop_validation.py','pokerlab/__init__.py','pokerlab/cards.py',
      'scripts/matrix_free_four_street_rules.py','scripts/matrix_free_certificate_budget.py',
      'tests/full_deck_public_chance_reference.py')


def replay(packet=PACKET):
    from scripts import replay_joint_cycles_packet as base, joint_evidence_archive as archive
    from scripts import replay_joint_two_epoch_packet as helper, replay_single_pass_packet as known
    need=base.need;digest=lambda raw:sha256(raw).hexdigest()
    def bootstrap():
        prior=base.bootstrap();name='scripts/replay_opponent_action_study.py';raw=archive.read(ROOT/name)
        need(not base.git('status','--porcelain','--untracked-files=all','--',name) and
             digest(raw) in base.variants(base.git('show',prior[0]+':'+name)),'opponent study committed reader source')
        return prior,digest(raw)
    before=bootstrap()
    need(not any(n=='tests' or n.startswith(('tests.','pokerlab')) for n in sys.modules),'opponent study fresh numerical process')
    def load():return archive.load(packet,helper,pin=PIN,version='opponent-action',
        labels=('first-refusal','completed','builds','objects'),packager='package_opponent_action1.py.txt')
    manifest,loaded,pins=load();objects=helper.GitObjects();captured={};authentication={}
    for label in ('first-refusal','completed'):
        files=loaded[label];identity=helper.decode(files['attempt/source-identity.json']);head=identity['head'];hashes=identity['raw_sha256']
        need(head==ORIGINS[label] and len(hashes)==13 and set(hashes)==set(identity['committed_blobs']) and
             {name[len('attempt/source/'):] for name in files if name.startswith('attempt/source/')}==set(hashes),'opponent complete captured source inventory')
        source={}
        for name,expected in hashes.items():
            raw=files['attempt/source/'+helper.safe_name(name)];blob=objects.tree(head).get(name);canonical=objects.body(head,name)
            need(digest(raw)==expected and identity['committed_blobs'][name]==blob and
                 (helper.source_bytes_match(raw,canonical,name,blob) or known.HISTORICAL_CHECKOUTS.get(name)==(expected,blob)),
                 'opponent captured raw/Git source identity');source[name]=raw
        processes,_=helper.process_receipts(files)
        need(len(processes)==(0 if label=='first-refusal' else 4) and all(p['exit']==0 for p in processes.values()),'opponent original four Python exits')
        authentication[label]={'source_files':len(source),'original_python_children':len(processes)};captured[label]=source
    need(b'ValueError: reduce-only child bounds' in loaded['first-refusal']['logs/opponent-action-study1.log'],
         'opponent preserve original pre-child refusal')
    def current_math():
        need(not (ROOT/'tests/__init__.py').exists() and not (ROOT/'scripts/__init__.py').exists(),'opponent namespace identity')
        need(not base.git('status','--porcelain','--untracked-files=all','--',*MATH),'opponent current mathematical closure clean')
        result={}
        for name in MATH:
            raw=archive.read(ROOT/name);canonical=objects.body(ORIGINS['completed'],name)
            need(digest(raw) in base.variants(canonical) and digest(captured['completed'][name]) in base.variants(canonical),
                 'opponent current/captured mathematical source drift: '+name);result[name]=digest(raw)
        return result
    math_before=current_math();previous=sys.pycache_prefix,sys.dont_write_bytecode
    with TemporaryDirectory(prefix='opponent-study-empty-cache-',dir=ROOT.parent) as cache:
        sys.pycache_prefix=cache;sys.dont_write_bytecode=True
        try:
            from scripts.forecast_opponent_action_sampling import forecast
            from tests import test_opponent_action_sampling_forecast as controls
            fresh=forecast();files=loaded['completed'];saved=helper.decode(files['attempt/result.json'])
            expected_children=[]
            for mode in ('normal','optimized'):
                for label in ('tests','worksheet'):
                    prefix=f'attempt/{label}-{mode}';receipt=helper.decode(files[prefix+'/process.json'])
                    expected_children.append({'label':label,'mode':mode,'receipt':receipt})
                    if label=='worksheet':
                        need(helper.decode(files[prefix+'/stdout.bin'])==fresh and files[prefix+'/stderr.bin']==b'','opponent fresh deterministic worksheet match')
                    else:need(b'Ran 4 tests' in files[prefix+'/stderr.bin'] and b'\nOK' in files[prefix+'/stderr.bin'],'opponent original four controls')
            need(saved['children']==expected_children and saved['worksheet']==fresh and saved['source_files']==13 and
                 saved['worksheet_sha256']==digest(files['attempt/worksheet-normal/stdout.bin']) and
                 files['attempt/worksheet-normal/stdout.bin']==files['attempt/worksheet-optimized/stdout.bin'] and
                 (saved['native_calls'],saved['rng_calls'],saved['attempted_training'],saved['quality_gate'])==(0,0,False,None),
                 'opponent complete original controller outcome')
            suite=unittest.defaultTestLoader.loadTestsFromModule(controls);result=unittest.TextTestRunner(stream=StringIO()).run(suite)
            need(result.testsRun==4 and result.wasSuccessful() and not result.skipped,'opponent fresh independent structural controls')
            for name in MATH:
                module=name[:-3].replace('/','.')
                if module.endswith('.__init__'):module=module[:-len('.__init__')]
                imported=sys.modules.get(module)
                need(imported is not None and Path(imported.__file__).resolve()==(ROOT/name).resolve(),'opponent imported current source identity')
            need(bootstrap()==before and current_math()==math_before and load()[2]==pins,'opponent source/evidence replay drift')
            return {'status':'opponent-proposal-structural-study-replayed','authentication':authentication,'fresh_tests':4,
                'worksheet_sha256':saved['worksheet_sha256'],'worksheet':fresh,'native_calls':0,'rng_calls':0,
                'archived_source_executed':False,'attempted_training':False,'quality_gate':None,
                'stored_expanded_bytes':manifest['stored_expanded_bytes'],
                'scope':'Current structural costs, small exact occupancy and budget-refusal checks after complete original source/process admission. No sampled R/A operator, second-moment proof, timing, native lifetime, numerical-retention or quality claim.'}
        finally:sys.pycache_prefix,sys.dont_write_bytecode=previous


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('packet',nargs='?',type=Path,default=PACKET)
    print(json.dumps(replay(parser.parse_args().packet),indent=2))
