"""Measure the frozen six-pair covered-count preflop expansion without ranking."""
from __future__ import annotations
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
from fractions import Fraction
import gc
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
from time import perf_counter
import sys
from scripts import benchmark_preflop_exact_anchor as anchor
from scripts import benchmark_native_fixed_street as native
from scripts import benchmark_fixed_street_profile as profile
from scripts.preflop_exact_anchor_validation import load_reference
from scripts.preflop_checkdown_validation import replay
from pokerlab.preflop_covered_equity import pool_preflop_equities_by_suit
from pokerlab.preflop_checkdown_solver import solve_covered_preflop_checkdown
from pokerlab.preflop_checkdown_budget import admit_covered_prepared

ROOT=Path(__file__).resolve().parents[1]
SPEC_PATH=ROOT/'benchmarks/preflop-covered-counts-v1.json'
SPEC_SHA256='0504427311b30dd7809ada5851988697e4ee324dee85691d6d7d90d81c26391e'
BASELINE='49816ef524703a9c3909a06943cdd114395d3939'

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def checksum(value):return hashlib.sha256(canonical(value)).hexdigest()

def validate_spec(spec):
    if type(spec) is not dict or checksum(spec)!=SPEC_SHA256:
        raise ValueError('Requires the frozen covered-counts specification')
    return spec

def identity():
    state=anchor._identity()
    raw=SPEC_PATH.read_bytes()
    state['source_hashes'][SPEC_PATH.relative_to(ROOT).as_posix()]={
        'raw_sha256':hashlib.sha256(raw).hexdigest(),
        'lf_sha256':hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()}
    return state

def inputs(spec):
    ref=load_reference()
    if ref['identity']['report_sha256']!=spec['source_report_sha256']:
        raise ValueError('Pinned physical source report changed')
    oldspec=json.loads(anchor.SPEC_PATH.read_text(encoding='utf-8'))
    source=anchor._load_inputs(oldspec,ref)['table']
    table=pool_preflop_equities_by_suit([source],spec['sb_range'],spec['bb_range'])
    if (len(source.pairs)!=spec['source_pairs'] or len(table.pairs)!=spec['compatible_pairs']
            or table.budget['physical_worlds_upper_bound']!=spec['physical_boards']):
        raise ValueError('Covered physical census changed')
    # The independent replay receives pinned source W/T/L under a separately
    # reconstructed endpoint map, never the candidate result's equity rows.
    counts=[]
    source_counts={(r['sb_hand'],r['bb_hand']):(r['wins'],r['ties'],r['losses']) for r in ref['counts']}
    for proof in table.provenance():
        a,b=proof['source_sb_hand'],proof['source_bb_hand']
        mapping=proof['suit_permutation']
        if set(mapping)!=set('cdhs') or set(mapping.values())!=set('cdhs'):
            raise ValueError('Invalid full joint suit map')
        def map_hand(text):return ''.join(sorted(text[i]+mapping[text[i+1]] for i in (0,2)))
        if (map_hand(a),map_hand(b))!=(proof['target_sb_hand'],proof['target_bb_hand']):
            raise ValueError('Coverage map does not match source/target endpoints')
        w,t,l=source_counts[(a,b)]
        counts.append({'sb_hand':proof['target_sb_hand'],'bb_hand':proof['target_bb_hand'],
                       'wins':w,'ties':t,'losses':l,'boards':1712304})
    return table,counts,ref['identity']

def preflight(table,spec,n):
    py=admit_covered_prepared(table,spec['config'],n,spec['algorithm'],world_indexing='pair-mean')
    upper=py['tree_upper_bound']
    from pokerlab.native_fixed_street import admit_native_shape,complete_solve_admission
    shape=admit_native_shape(upper['public_states'],len(table.pairs),upper['information_action_slots'],n,spec['algorithm'])
    complete=complete_solve_admission(shape,py['total_loop_entries_upper_bound'],py['training_loop_entries_upper_bound'])
    return {'iterations':n,'python':py,'native':complete,'status':'admitted'}

def assess(payload,counts,spec):
    metrics=replay(payload,spec['sb_range'],spec['bb_range'],spec['config'],counts,
                   tolerance=spec['acceptance']['independent_metric_absolute_tolerance'],covered_counts=True)
    gap=Fraction(*metrics['nash_conv_fraction'])
    lower=-Fraction(*metrics['bb_best_response_fraction']);upper=Fraction(*metrics['sb_best_response_fraction'])
    if upper-lower!=gap or gap<0:raise ValueError('Independent BR bracket disagrees with NashConv')
    return {'independent_replay':metrics,'equilibrium_bracket_sb_fraction':
            [[lower.numerator,lower.denominator],[upper.numerator,upper.denominator]],
            'quality_pass':gap<=Fraction(str(spec['acceptance']['final_nash_conv_chip_limit']))}

def compare(py,na,spec):
    gates=spec['acceptance']
    return native._compare_payloads('preflop',py,na,{'acceptance':{
        'cross_backend_metric_absolute_tolerance':gates['backend_metric_absolute_tolerance'],
        'cross_backend_policy_probability_absolute_tolerance':gates['backend_policy_probability_absolute_tolerance']}})

def measure(table,counts,spec,n,backend,build):
    gc.collect();result=None;encoded=None;digest=None;error=None
    with ExitStack() as stack:
        guards=stack.enter_context(profile._rank_guard())
        seconds,calls=stack.enter_context(profile._PhaseContext(native._phase_targets('preflop',backend,'cfrplus')))
        started=perf_counter()
        try:
            result=solve_covered_preflop_checkdown(table,config=spec['config'],iterations=n,
                    algorithm='cfrplus',world_indexing='pair-mean',training_backend=backend,
                    build_directory=build if backend=='native' else None)
            encoded=canonical(result);digest=hashlib.sha256(encoded).hexdigest()
        except Exception as exc:
            error=f'{type(exc).__name__}: {exc}'
        elapsed=perf_counter()-started
        row={'backend':backend,'complete_seconds':elapsed,
             'payload_sha256':digest,'serialized_bytes_utf8':len(encoded) if encoded is not None else None,
             'rank_guard_calls':dict(guards),'phase_calls':dict(calls),'phase_seconds':dict(seconds)}
    if result is not None:
        row['payload']=result
        try:row['assessment']=assess(result,counts,spec)
        except Exception as exc:error=f'{type(exc).__name__}: {exc}'
    if any(guards.values()) or not native._phase_count_passed('preflop',backend,'cfrplus',row):
        error=error or 'Covered measurement invoked forbidden rank/phase census'
    if error is not None:row['error']=error
    return row

def run(spec,build):
    validate_spec(spec)
    report={'schema_version':1,'benchmark_id':spec['benchmark_id'],'specification':spec,
            'spec_sha256':checksum(spec),'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'runtime':{'python':sys.version,'platform':__import__('platform').platform()},
            'profiles':[],'preflights':[],'errors':[]}
    before=after=build_before=build_after=None
    try:
        before=identity()
        if before['status']:raise ValueError('Requires clean committed source')
        if subprocess.run(['git','merge-base','--is-ancestor',BASELINE,before['revision']],cwd=ROOT).returncode:
            raise ValueError('Baseline is not an ancestor of frozen source')
        table,counts,source=inputs(spec)
        report.update({'source_reference':source,'count_provenance':table.provenance(),
                       'trusted_physical_count_rows':counts,'table_budget':table.budget})
        for n in spec['checkpoints']:
            report['preflights'].append(preflight(table,spec,n))
        build_before=native._build_identity(build)
        for n in spec['checkpoints']:
            final=n==spec['checkpoints'][-1];repeats=3 if final else 1
            row={'iterations':n,'samples':[],'paired_comparisons':[]}
            report['profiles'].append(row)
            for repeat in range(repeats):
                pair={}
                for backend in (spec['backends'] if repeat%2==0 else list(reversed(spec['backends']))):
                    print(f'START covered-six-pairs n={n} repeat={repeat+1} backend={backend}',flush=True)
                    try:
                        sample=measure(table,counts,spec,n,backend,build)
                        sample['repeat']=repeat+1;row['samples'].append(sample)
                        if sample.get('error'):
                            report['errors'].append({'iterations':n,'backend':backend,'repeat':repeat+1,'error':sample['error']})
                        if 'payload' in sample:pair[backend]=sample['payload']
                    except Exception as exc:
                        row['samples'].append({'backend':backend,'repeat':repeat+1,'error':f'{type(exc).__name__}: {exc}'})
                        report['errors'].append({'iterations':n,'backend':backend,'repeat':repeat+1,'error':str(exc)})
                if set(pair)==set(spec['backends']):
                    comparison=compare(pair['python'],pair['native'],spec)
                    comparison['repeat']=repeat+1;row['paired_comparisons'].append(comparison)
                    if not comparison['meets_metric_gate'] or not comparison['meets_policy_gate']:
                        report['errors'].append({'iterations':n,'repeat':repeat+1,'error':'backend parity missed'})
            row['median_complete_seconds']={b:statistics.median(x['complete_seconds'] for x in row['samples'] if x['backend']==b)
                 if final and len([x for x in row['samples'] if x['backend']==b and 'payload' in x])==3 else None for b in spec['backends']}
            if final:
                for b in spec['backends']:
                    samples=[x for x in row['samples'] if x['backend']==b]
                    if (len(samples)!=3 or any(not x.get('assessment',{}).get('quality_pass') for x in samples)
                            or len({x.get('payload_sha256') for x in samples})!=1):
                        report['errors'].append({'backend':b,'error':'Final quality or deterministic repeats failed'})
        after=identity();build_after=native._build_identity(build)
        if before!=after or build_before!=build_after:raise ValueError('Source or build identity changed')
    except Exception as exc:
        report['errors'].append({'phase':'runner','error':f'{type(exc).__name__}: {exc}'})
    report.update({'source_before':before,'source_after':after,'native_build_before':build_before,
                   'native_build_after':build_after,'source_unchanged':before is not None and before==after,
                   'native_build_unchanged':build_before is not None and build_before==build_after})
    report['status']='passed' if not report['errors'] else 'error'
    report['artifact_sha256']=checksum(report)
    return report

def verify_saved(path):
    report=json.loads(Path(path).read_bytes());unsigned=dict(report);digest=unsigned.pop('artifact_sha256')
    if checksum(unsigned)!=digest:raise ValueError('Saved covered report checksum failed')
    spec=validate_spec(report['specification']);table,counts,source=inputs(spec)
    if report['status']=='passed' and (report.get('preflights')!=[preflight(table,spec,n) for n in spec['checkpoints']]
            or report.get('count_provenance')!=table.provenance()
            or report.get('trusted_physical_count_rows')!=counts or report.get('source_reference')!=source):
        raise ValueError('Saved covered count provenance or preflight census differs')
    checked=0;comparisons=0
    if report['status']=='passed' and [x['iterations'] for x in report['profiles']]!=spec['checkpoints']:
        raise ValueError('Saved report checkpoint census failed')
    for row in report['profiles']:
        pairs={}
        for sample in row['samples']:
            if 'payload' not in sample:continue
            payload=sample['payload'];encoded=canonical(payload)
            if (hashlib.sha256(encoded).hexdigest()!=sample['payload_sha256']
                    or len(encoded)!=sample['serialized_bytes_utf8']
                    or assess(payload,counts,spec)!=sample['assessment']
                    or payload['iterations']!=row['iterations']
                    or any(sample['rank_guard_calls'].values())
                    or not native._phase_count_passed('preflop',sample['backend'],'cfrplus',sample)):
                raise ValueError('Saved payload/replay/census failed')
            pairs.setdefault(sample['repeat'],{})[sample['backend']]=payload;checked+=1
        for repeat,pair in pairs.items():
            if set(pair)==set(spec['backends']):
                fresh=compare(pair['python'],pair['native'],spec);fresh['repeat']=repeat
                if (fresh not in row['paired_comparisons'] or (report['status']=='passed'
                        and not (fresh['meets_metric_gate'] and fresh['meets_policy_gate']))):
                    raise ValueError('Saved backend comparison failed')
                comparisons+=1
        final=row['iterations']==spec['checkpoints'][-1]
        if report['status']=='passed':
            expected=[(r+1,b) for r in range(3 if final else 1)
                      for b in (spec['backends'] if r%2==0 else list(reversed(spec['backends'])))]
            if [(x['repeat'],x['backend']) for x in row['samples']]!=expected:
                raise ValueError('Saved paired sample order failed')
            for b in spec['backends']:
                samples=[x for x in row['samples'] if x['backend']==b]
                median=statistics.median(x['complete_seconds'] for x in samples) if final else None
                if row['median_complete_seconds'][b]!=median:raise ValueError('Saved timing summary failed')
                if final and (any(not x['assessment']['quality_pass'] for x in samples)
                              or len({x['payload_sha256'] for x in samples})!=1):
                    raise ValueError('Saved final quality/determinism failed')
    if report['status']=='passed' and (checked!=12 or comparisons!=6 or report['errors']
            or not report['source_unchanged'] or not report['native_build_unchanged']
            or report['source_before']!=report['source_after'] or report['source_before']['status']
            or report['native_build_before']!=report['native_build_after']):
        raise ValueError('Saved report completion/integrity census failed')
    return {'status':'passed','replayed_payloads':checked,'paired_comparisons':comparisons}

def save(path,report):
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(report,stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')
    tmp.replace(path)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--build-dir',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args(argv)
    path=args.output.resolve()
    if path==ROOT or ROOT in path.parents or path.exists() or path.with_name(path.name+'.tmp').exists():
        parser.error('Use a new observation path outside the checkout')
    spec=validate_spec(json.loads(SPEC_PATH.read_bytes()));report=run(spec,args.build_dir);save(path,report)
    try:
        report['saved_verification']=verify_saved(path)
        if report['source_after'] is not None and identity()!=report['source_after']:
            raise ValueError('Source changed during saved-file verification')
        if report['native_build_after'] is not None and native._build_identity(args.build_dir)!=report['native_build_after']:
            raise ValueError('Native build changed during saved-file verification')
    except Exception as exc:
        report['errors'].append({'phase':'saved-verification','error':f'{type(exc).__name__}: {exc}'})
        report['status']='error'
    report.pop('artifact_sha256');report['artifact_sha256']=checksum(report);save(path,report)
    verify_saved(path)
    print(json.dumps({'status':report['status'],'artifact_sha256':report['artifact_sha256'],'errors':report['errors']}),flush=True)
    return 0 if report['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
