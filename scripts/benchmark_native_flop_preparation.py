"""Frozen native cold fixed-flop preparation and complete-call comparison."""
from contextlib import ExitStack
from datetime import datetime,timezone
from fractions import Fraction
import argparse
import gc
import hashlib
import json
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch
from pokerlab import flop_checkdown_worlds as worlds
from pokerlab.flop_checkdown_equity import FlopCheckdownEquities,prepare_flop_checkdown_equities
from pokerlab.native_flop_equity import prepare_native_flop_checkdown_equities
from pokerlab.flop_checkdown_solver import solve_prepared_flop_checkdown
from pokerlab import native_preflop_equity as count_native
from scripts import benchmark_native_fixed_street as training
from scripts import benchmark_fixed_street_profile as phases
from scripts import benchmark_flop_equity_reuse as reuse
from scripts import certify_preflop_mixed_sequence as identity
from scripts.flop_checkdown_validation import prepare_oracle,prepare_oracle_from_counts,replay
from scripts.benchmark_preflop_covered_counts import canonical,checksum

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/'benchmarks/native-flop-preparation-v1.json'
SPEC_SHA='7dee0d6e7b77686224741fcd9face6f1b508fd8ac4519464e40ffd1ff9230ed9'


def normalized(value):return json.loads(canonical(value))


def snapshot():
    state=identity.snapshot()
    paths=[SPEC,ROOT/'benchmarks/results/flop-weighted-eight-hand-v1.json',
           ROOT/'.github/workflows/native-preflop.yml',*sorted((ROOT/'native').glob('*.c'))]
    for path in paths:
        raw=path.read_bytes();state['source_hashes'][path.relative_to(ROOT).as_posix()]={
            'raw_sha256':hashlib.sha256(raw).hexdigest(),
            'lf_sha256':hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()}
    return state


def historical_counts(spec):
    path=ROOT/spec['source_count_report_path'];data=json.loads(path.read_bytes())
    if checksum(data)!=spec['source_count_report_canonical_sha256'] or not data['acceptance_gate_met'] or data['failures']:
        raise ValueError('Pinned independent physical count report changed or did not pass')
    rows=next(x['oracle_pair_counts'] for x in data['results'] if x['fixture_id']=='weighted-8x8-stack12-raises1')
    if len(rows)!=58:raise ValueError('Pinned physical count report must cover 58 compatible pairs')
    return rows


def table_for(case,spec,counts):
    plan=worlds.prepare_flop_worlds(spec['board'],case['oop_range'],case['ip_range'])
    mapping={(r['oop_hand'],r['ip_hand']):(r['wins'],r['ties'],r['losses']) for r in counts}
    values=tuple(mapping[(''.join(plan.hands[0][i]),''.join(plan.hands[1][j]))] for i,j,_ in plan.pairs)
    table=FlopCheckdownEquities(tuple(plan.board),tuple(tuple(tuple(h) for h in seat) for seat in plan.hands),
                              tuple(plan.pairs),values,tuple(plan.budget.items()))
    table.validate();reuse._verify_table_against_rows(table,counts)
    reuse._verify_exact_priors(table,spec['board'],case['oop_range'],case['ip_range'],case['expected_normalizer'])
    if len(table.pairs)!=case['expected_compatible_pairs']:raise ValueError('Frozen compatible-pair census changed')
    return table


def projection(table):
    table.validate()
    return normalized({'board':table.board,'hands':table.hands,'pairs':[(i,j,str(p)) for i,j,p in table.pairs],
                       'counts':table.counts,'budget':table.budget})


def preflights(spec):
    result=[]
    for case in spec['fixtures']:
        plan=worlds.prepare_flop_worlds(spec['board'],case['oop_range'],case['ip_range'])
        row=training._preflight_flop({'case':{'config':spec['config']},'table':plan},spec['algorithm'],spec['iterations'])
        result.append({'fixture_id':case['id'],'status':'admitted',**row})
    fresh=[worlds.prepare_flop_worlds(c['board'],c['oop_range'],c['ip_range']).budget
           for c in spec['fresh_independent_count_checks']]
    return normalized({'complete_calls':result,'fresh_count_preparation_admissions':fresh})


def count_build_identity(build):
    exe,manifest=count_native._backend(build)
    return {'manifest':manifest,'manifest_sha256':hashlib.sha256((Path(build)/'native-preflop-manifest.json').read_bytes()).hexdigest(),
            'executable_sha256':hashlib.sha256(exe.read_bytes()).hexdigest()}


def legacy_identity(build,spec):
    folder=Path(build);manifest=json.loads((folder/'native-preflop-manifest.json').read_bytes())
    source=subprocess.check_output(['git','show',spec['baseline_commit']+':native/preflop_equity.c'],cwd=ROOT)
    if manifest['source_lf_sha256']!=hashlib.sha256(source.replace(b'\r\n',b'\n')).hexdigest():
        raise ValueError('Historical helper does not match the pinned pre-extension source')
    exe=folder/manifest['executable']
    digest=hashlib.sha256(exe.read_bytes()).hexdigest()
    if digest!=manifest['executable_sha256']:raise ValueError('Historical executable changed')
    return {'manifest':manifest,'manifest_sha256':hashlib.sha256((folder/'native-preflop-manifest.json').read_bytes()).hexdigest(),
            'executable_sha256':digest}


def legacy_parity(old_build,new_build,spec):
    old=legacy_identity(old_build,spec);new=count_build_identity(new_build)
    rng=random.Random(20261019)
    ranks=[(5+i%3,*rng.sample(range(52),5+i%3)) for i in range(256)]
    queries={'rank':('OPENPOKER_NATIVE_V1 RANK 256\n'+''.join(' '.join(map(str,r))+'\n' for r in ranks)).encode(),
             'count':b'OPENPOKER_NATIVE_V1 COUNT 3\n49 51 45 47\n41 43 50 47\n41 43 45 47\n'}
    rows=[]
    for mode,request in queries.items():
        outputs=[]
        for folder,meta in ((old_build,old),(new_build,new)):
            exe=Path(folder)/meta['manifest']['executable']
            done=subprocess.run([str(exe.resolve())],input=request,capture_output=True,timeout=120,check=False)
            if done.returncode or done.stderr or len(done.stdout)>262144:raise ValueError('Historical protocol compatibility query failed')
            outputs.append(done.stdout)
        if outputs[0]!=outputs[1]:raise ValueError('COUNT/RANK protocol output changed')
        rows.append({'mode':mode,'request_ascii':request.decode(),'stdout_ascii':outputs[0].decode(),
                     'request_sha256':hashlib.sha256(request).hexdigest(),
                     'stdout_sha256':hashlib.sha256(outputs[0]).hexdigest(),'byte_identical':True})
    return {'historical_build':old,'current_build':new,'queries':rows}


def assess(payload,oracle,spec):
    checked=replay(payload,oracle,tolerance=spec['acceptance']['independent_metric_absolute_tolerance'])
    return {'independent_replay':checked,'quality_pass':checked['nash_conv']<=spec['acceptance']['final_nash_conv_chip_limit']}


def measure(case,spec,backend,stage,count_build,train_build):
    result=None;table=None;native_metadata=None;error=None;encoded=None
    counters={'python_rank_calls':0,'python_board_combination_calls':0,'python_plan_build_calls':0}
    original_rank=worlds.rank_hand;original_combinations=worlds.combinations;original_build=worlds.FlopCheckdownPlan.build
    def ranked(*args,**kwargs):counters['python_rank_calls']+=1;return original_rank(*args,**kwargs)
    def combinations(*args,**kwargs):counters['python_board_combination_calls']+=1;return original_combinations(*args,**kwargs)
    def built(plan):counters['python_plan_build_calls']+=1;return original_build(plan)
    targets=training._phase_targets('flop','native',spec['algorithm']) if stage=='complete_call' else []
    gc.collect()
    with ExitStack() as stack:
        stack.enter_context(patch.object(worlds,'rank_hand',ranked))
        stack.enter_context(patch.object(worlds,'combinations',combinations))
        stack.enter_context(patch.object(worlds.FlopCheckdownPlan,'build',built))
        seconds,calls=stack.enter_context(phases._PhaseContext(targets))
        started=perf_counter()
        try:
            if backend=='python':table=prepare_flop_checkdown_equities(spec['board'],case['oop_range'],case['ip_range'])
            else:
                prepared=prepare_native_flop_checkdown_equities(spec['board'],case['oop_range'],case['ip_range'],build_directory=count_build)
                table=prepared.equities
            if stage=='complete_call':
                result=solve_prepared_flop_checkdown(table,config=spec['config'],iterations=spec['iterations'],
                    algorithm=spec['algorithm'],training_backend='native',build_directory=train_build)
            else:result=projection(table)
            encoded=canonical(result);digest=hashlib.sha256(encoded).hexdigest()
        except Exception as exc:error=f'{type(exc).__name__}: {exc}';digest=None
        elapsed=perf_counter()-started
    if backend=='native' and table is not None:native_metadata=prepared.metadata
    row={'preparation_backend':backend,'stage':stage,'complete_seconds':elapsed,'payload':result,
         'payload_sha256':digest,'serialized_bytes_utf8':len(encoded) if encoded is not None else None,
         'preparation_calls':counters,'phase_calls':dict(calls),'phase_seconds':dict(seconds)}
    if table is not None:row['table']=projection(table)
    if native_metadata is not None:row['native_preparation']=native_metadata
    if error:row['error']=error
    return row


def validate_sample(row,case,spec,table,oracle):
    if row.get('error') or row.get('payload') is None:raise ValueError('Measurement contains a failed raw call')
    encoded=canonical(row['payload'])
    if row['payload_sha256']!=hashlib.sha256(encoded).hexdigest() or row['serialized_bytes_utf8']!=len(encoded):
        raise ValueError('Saved payload bytes/digest changed')
    if canonical(row['table'])!=canonical(projection(table)):raise ValueError('Table counts, physical support or exact priors changed')
    py=row['preparation_backend']=='python';p=len(table.pairs)
    expected={'python_rank_calls':2*990*p if py else 0,'python_board_combination_calls':p if py else 0,
              'python_plan_build_calls':1 if py else 0}
    if row['preparation_calls']!=expected:raise ValueError('Preparation execution census changed')
    if not py:
        meta=row['native_preparation'];response=meta['response']
        ids={card:i for i,card in enumerate(worlds.DECK)}
        expected_response={'schema_version':1,'mode':'flop','board':[ids[c] for c in table.board],
            'pairs':[[ids[c] for c in table.hands[0][i]+table.hands[1][j]] for i,j,_ in table.pairs],
            'counts':[list(c) for c in table.counts],'unordered_boards_per_pair':990,
            'ordered_outcomes_per_pair':1980,'board_evaluations':990*p,'rank_calls':1980*p}
        if (canonical(response)!=canonical(expected_response) or meta['board_evaluations']!=990*p or meta['rank_calls']!=1980*p
                or meta['ordered_outcomes']!=1980*p or not meta['source_inclusive_admission']):
            raise ValueError('Raw native counts or physical counters changed')
    if row['stage']=='complete_call':
        if (row['payload']['iterations']!=spec['iterations'] or row['payload']['algorithm']!=spec['algorithm']
                or not training._phase_count_passed('flop','native',spec['algorithm'],row)):
            raise ValueError('Complete solve identity or training/diagnostic phase census failed')
        return assess(row['payload'],oracle,spec)
    if row['payload']!=projection(table) or row['phase_calls'] or row['phase_seconds']:
        raise ValueError('Cold preparation payload or phase census changed')
    return {'exact_table_verified':True}


def run(spec,count_build,train_build,old_build):
    if checksum(spec)!=SPEC_SHA:raise ValueError('Requires the frozen native flop-preparation specification')
    report={'schema_version':1,'benchmark_id':spec['benchmark_id'],'specification':spec,'spec_sha256':SPEC_SHA,
            'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'runtime':{'python':sys.version,'executable':sys.executable,'platform':platform.platform()},
            'source_before':None,'source_after':None,'source_unchanged':False,'builds_before':None,'builds_after':None,
            'errors':[],'fixtures':[],'fresh_independent_count_checks':[],'legacy_protocol_parity':None}
    try:
        before=report['source_before']=snapshot()
        if before['status']:raise ValueError('Native flop benchmark requires clean committed source')
        if subprocess.run(['git','merge-base','--is-ancestor',spec['baseline_commit'],before['revision']],cwd=ROOT).returncode:
            raise ValueError('Merged solver baseline is not an ancestor of source')
        # Finish all complete and preparation admissions before either build
        # lookup or independent physical ranking. Inputs below use pinned rows.
        report['preflights']=preflights(spec)
        counts=historical_counts(spec);report['trusted_count_rows']=counts
        tables=[table_for(case,spec,counts) for case in spec['fixtures']]
        oracles=[prepare_oracle_from_counts(spec['board'],c['oop_range'],c['ip_range'],spec['config'],counts)
                 for c in spec['fixtures']]
        builds={'counts':count_build_identity(count_build),'training':training._build_identity(train_build),
                'historical':legacy_identity(old_build,spec)}
        report['builds_before']=builds
        report['legacy_protocol_parity']=legacy_parity(old_build,count_build,spec)
        for fresh in spec['fresh_independent_count_checks']:
            print('FRESH independent physical counts '+fresh['board'],flush=True)
            oracle=prepare_oracle(fresh['board'],fresh['oop_range'],fresh['ip_range'],spec['config'])
            prepared=prepare_native_flop_checkdown_equities(fresh['board'],fresh['oop_range'],fresh['ip_range'],build_directory=count_build)
            reuse._verify_table_against_rows(prepared.equities,oracle['counts'])
            report['fresh_independent_count_checks'].append({'case':fresh,'independent_rows':oracle['counts'],
                'native_table':projection(prepared.equities),'native_metadata':prepared.metadata,'all_counts_agree':True})
        for case,table,oracle in zip(spec['fixtures'],tables,oracles):
            observed={'fixture_id':case['id'],'stages':[]};report['fixtures'].append(observed)
            for stage in ('preparation','complete_call'):
                row={'stage':stage,'samples':[]};observed['stages'].append(row)
                for repeat in range(spec['paired_repeats']):
                    for backend in (spec['preparation_backends'] if repeat%2==0 else list(reversed(spec['preparation_backends']))):
                        print(f'START {case["id"]} {stage} repeat={repeat+1} preparation={backend}',flush=True)
                        sample=measure(case,spec,backend,stage,count_build,train_build);sample['repeat']=repeat+1
                        row['samples'].append(sample)
                        try:
                            sample['assessment']=validate_sample(sample,case,spec,table,oracle)
                            if stage=='complete_call' and not sample['assessment']['quality_pass']:
                                raise ValueError('Frozen complete-call quality target missed')
                        except Exception as exc:
                            sample['error']=sample.get('error') or f'{type(exc).__name__}: {exc}'
                            report['errors'].append({'fixture_id':case['id'],'stage':stage,'repeat':repeat+1,
                                                     'backend':backend,'error':sample['error']})
                row['median_complete_seconds']={b:statistics.median(x['complete_seconds'] for x in row['samples'] if x['preparation_backend']==b)
                                                 for b in spec['preparation_backends']}
                hashes={x.get('payload_sha256') for x in row['samples']}
                row['all_payloads_exactly_identical']=len(hashes)==1 and None not in hashes
                if not row['all_payloads_exactly_identical']:
                    report['errors'].append({'fixture_id':case['id'],'stage':stage,'error':'Exact payload parity/determinism failed'})
                row['observed_median_python_over_native_ratio']=row['median_complete_seconds']['python']/row['median_complete_seconds']['native']
        report['builds_after']={'counts':count_build_identity(count_build),'training':training._build_identity(train_build),
                                'historical':legacy_identity(old_build,spec)}
        if report['builds_before']!=report['builds_after']:raise ValueError('Count/training/historical build changed')
    except Exception as exc:
        report['errors'].append({'phase':'runner','error':f'{type(exc).__name__}: {exc}'})
    finally:
        try:
            report['source_after']=snapshot()
            report['source_unchanged']=report['source_before'] is not None and report['source_before']==report['source_after']
            if not report['source_unchanged']:report['errors'].append({'phase':'source-integrity','error':'Source/revision/status changed'})
        except Exception as exc:report['errors'].append({'phase':'final-source-identity','error':f'{type(exc).__name__}: {exc}'})
    report['status']='error' if report['errors'] else 'passed'
    report['artifact_sha256']=checksum(report)
    return report


def verify_saved(path):
    path=Path(path)
    if path.stat().st_size>16777216:raise ValueError('Native flop report exceeds bounded saved input size')
    data=json.loads(path.read_bytes());unsigned=dict(data);digest=unsigned.pop('artifact_sha256')
    if checksum(unsigned)!=digest or data['status']!='passed' or data['errors']:
        raise ValueError('Native flop report checksum or passed status failed')
    spec=data['specification']
    if checksum(spec)!=SPEC_SHA or data['spec_sha256']!=SPEC_SHA or data['benchmark_id']!=spec['benchmark_id']:
        raise ValueError('Native flop saved specification identity changed')
    if (not data['source_unchanged'] or data['source_before']!=data['source_after'] or data['source_before']['status']
            or not data['builds_before'] or data['builds_before']!=data['builds_after']):
        raise ValueError('Native flop source/build integrity census failed')
    if data['preflights']!=preflights(spec):raise ValueError('Native flop complete admission records changed')
    counts=historical_counts(spec)
    if data['trusted_count_rows']!=counts:raise ValueError('Native flop trusted physical rows changed')
    if len(data['fresh_independent_count_checks'])!=len(spec['fresh_independent_count_checks']):
        raise ValueError('Fresh independent count check census changed')
    for saved,fresh in zip(data['fresh_independent_count_checks'],spec['fresh_independent_count_checks']):
        if saved['case']!=fresh or not saved['all_counts_agree']:raise ValueError('Fresh physical check identity changed')
        # These two small fresh enumerations are independent physical oracles,
        # outside every timed preparation/solver call.
        fresh_oracle=prepare_oracle(fresh['board'],fresh['oop_range'],fresh['ip_range'],spec['config'])
        if saved['independent_rows']!=fresh_oracle['counts']:
            raise ValueError('Fresh independently enumerated physical counts changed')
        plan=worlds.prepare_flop_worlds(fresh['board'],fresh['oop_range'],fresh['ip_range'])
        if len(saved['independent_rows'])!=len(plan.pairs):raise ValueError('Fresh physical row census failed')
        mapping={(r['oop_hand'],r['ip_hand']):(r['wins'],r['ties'],r['losses']) for r in saved['independent_rows']}
        table=FlopCheckdownEquities(tuple(plan.board),tuple(tuple(tuple(h) for h in seat) for seat in plan.hands),tuple(plan.pairs),
            tuple(mapping[(''.join(plan.hands[0][i]),''.join(plan.hands[1][j]))] for i,j,_ in plan.pairs),tuple(plan.budget.items()))
        table.validate()
        if saved['native_table']!=projection(table) or saved['native_metadata']['response']['counts']!=[list(c) for c in table.counts]:
            raise ValueError('Fresh raw independent/native count agreement changed')
        if saved['native_metadata']['build']!=data['builds_before']['counts']['manifest']:
            raise ValueError('Fresh physical check build identity changed')
    parity=data['legacy_protocol_parity']
    if (parity['historical_build']!=data['builds_before']['historical'] or parity['current_build']!=data['builds_before']['counts']
            or [q['mode'] for q in parity['queries']]!=['rank','count']):
        raise ValueError('Legacy protocol/build census changed')
    for query in parity['queries']:
        if (not query['byte_identical'] or hashlib.sha256(query['request_ascii'].encode()).hexdigest()!=query['request_sha256']
                or hashlib.sha256(query['stdout_ascii'].encode()).hexdigest()!=query['stdout_sha256']
                or json.loads(query['stdout_ascii'])['mode']!=query['mode']):
            raise ValueError('Legacy protocol raw bytes changed')
    if [c['fixture_id'] for c in data['fixtures']]!=[c['id'] for c in spec['fixtures']]:
        raise ValueError('Saved fixture census changed')
    total=full=0
    for observed,case in zip(data['fixtures'],spec['fixtures']):
        table=table_for(case,spec,counts)
        oracle=prepare_oracle_from_counts(spec['board'],case['oop_range'],case['ip_range'],spec['config'],counts)
        if [r['stage'] for r in observed['stages']]!=['preparation','complete_call']:raise ValueError('Saved phase census changed')
        for row in observed['stages']:
            expected=[(r+1,b) for r in range(3) for b in (spec['preparation_backends'] if r%2==0 else list(reversed(spec['preparation_backends'])))]
            if [(x['repeat'],x['preparation_backend']) for x in row['samples']]!=expected:
                raise ValueError('Saved paired sample order/census changed')
            for sample in row['samples']:
                if sample['stage']!=row['stage'] or validate_sample(sample,case,spec,table,oracle)!=sample['assessment']:
                    raise ValueError('Saved table/policy assessment changed')
                if sample['stage']=='complete_call':
                    full+=1
                    if not sample['assessment']['quality_pass']:raise ValueError('Saved final independent quality failed')
                    if sample['payload']['native_training']['build']!=data['builds_before']['training']['manifest']:
                        raise ValueError('Saved trainer build identity changed')
                if sample['preparation_backend']=='native' and sample['native_preparation']['build']!=data['builds_before']['counts']['manifest']:
                    raise ValueError('Saved count helper build identity changed')
                total+=1
            hashes={x['payload_sha256'] for x in row['samples']}
            if not row['all_payloads_exactly_identical'] or len(hashes)!=1:raise ValueError('Saved exact parity/determinism changed')
            for b in spec['preparation_backends']:
                if row['median_complete_seconds'][b]!=statistics.median(x['complete_seconds'] for x in row['samples'] if x['preparation_backend']==b):
                    raise ValueError('Saved median summary changed')
            ratio=row['median_complete_seconds']['python']/row['median_complete_seconds']['native']
            if row['observed_median_python_over_native_ratio']!=ratio:raise ValueError('Saved ratio summary changed')
    if total!=24 or full!=12:raise ValueError('Saved complete observation census failed')
    return {'status':'passed','rechecked_raw_calls':total,'replayed_complete_policies':full,
            'compatible_pairs_per_fixture':58,'fresh_independent_count_flops':2,
            'legacy_count_rank_byte_parity_recorded':True}


def save(path,report):
    report.pop('artifact_sha256',None);report['artifact_sha256']=checksum(report)
    identity.base._write(Path(path),report,replacing_owned=Path(path).exists())


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('count-build-dir','train-build-dir','legacy-build-dir'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args(argv);path=args.output.resolve()
    if path==ROOT or ROOT in path.parents or path.exists() or path.with_name(path.name+'.tmp').exists():
        parser.error('Use a new external observation path; preserve prior reports')
    report=run(json.loads(SPEC.read_bytes()),args.count_build_dir,args.train_build_dir,args.legacy_build_dir);save(path,report)
    try:
        report['saved_verification']=verify_saved(path)
        if snapshot()!=report['source_after']:raise ValueError('Source changed during saved-file replay')
    except Exception as exc:
        report['errors'].append({'phase':'saved-verification','error':f'{type(exc).__name__}: {exc}'});report['status']='error'
    save(path,report)
    if report['status']=='passed':verify_saved(path)
    print(json.dumps({'status':report['status'],'artifact_sha256':report['artifact_sha256'],'errors':report['errors']}),flush=True)
    return 0 if report['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
