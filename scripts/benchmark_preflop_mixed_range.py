"""Frozen 72-pair mixed physical preflop strategy validation."""
import argparse
from datetime import datetime, timezone
import sys
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
from scripts import benchmark_preflop_covered_counts as core
from scripts import preflop_mixed_range_reference as reference

ROOT=Path(__file__).resolve().parents[1]
BASELINE='8578988dae3dbf78c5fa8adaf56edbd80b592fbc'


def snapshot():
    state=core.identity();raw=reference.SPEC.read_bytes()
    for path in (reference.SPEC,*reference.REPORTS):
        raw=path.read_bytes();state['source_hashes'][path.relative_to(ROOT).as_posix()]={
            'raw_sha256':hashlib.sha256(raw).hexdigest(),
            'lf_sha256':hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()}
    return state


def mixed_assessment(payload,counts,spec):
    checked=core.assess(payload,counts,spec);metrics=checked['independent_replay']
    sb=Fraction(*metrics['sb_best_response_fraction']);bb=Fraction(*metrics['bb_best_response_fraction'])
    lower,upper=map(Fraction,spec['acceptance']['constructive_value_interval_sb_fraction'])
    if sb<lower or -bb>upper:
        raise ValueError('Independent policy BR bracket cannot contain a value in the constructive interval')
    checked.update({'constructive_value_interval_sb_fraction':[str(lower),str(upper)],
                    'bracket_intersects_constructive_interval':True})
    return checked


def run(spec,build):
    if core.checksum(spec)!=reference.SPEC_SHA:raise ValueError('Requires the exact frozen physical mixed AA/QQ-KK specification')
    report={'schema_version':1,'benchmark_id':spec['benchmark_id'],'specification':spec,
            'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'runtime':{'python':sys.version,'executable':sys.executable,'platform':__import__('platform').platform()},
            'spec_sha256':core.checksum(spec),'profiles':[],'preflights':[],'errors':[]}
    before=after=build_before=build_after=None
    try:
        before=snapshot()
        if before['status']:raise ValueError('Requires clean committed source')
        if subprocess.run(['git','merge-base','--is-ancestor',BASELINE,before['revision']],cwd=ROOT).returncode:
            raise ValueError('Merged physical basis is not an ancestor of source')
        table,counts,source=reference.load_inputs(spec)
        proof=reference.constructive_bounds(spec,counts)
        report.update({'constructive_value_bounds':proof,'source_reference':source,
                       'trusted_physical_count_rows':counts,'count_provenance':table.provenance(),
                       'table_budget':table.budget})
        report['preflights']=[core.preflight(table,spec,n) for n in spec['checkpoints']]
        build_before=core.native._build_identity(build)
        for n in spec['checkpoints']:
            final=n==spec['checkpoints'][-1];row={'iterations':n,'samples':[],'paired_comparisons':[]}
            report['profiles'].append(row)
            for repeat in range(3 if final else 1):
                pair={}
                for backend in (spec['backends'] if repeat%2==0 else list(reversed(spec['backends']))):
                    print(f'START physical mixed AA/QQ-KK pairs=72 n={n} repeat={repeat+1} backend={backend}',flush=True)
                    sample=core.measure(table,counts,spec,n,backend,build)
                    sample['repeat']=repeat+1;row['samples'].append(sample)
                    if 'payload' in sample:
                        try:sample['assessment']=mixed_assessment(sample['payload'],counts,spec)
                        except Exception as exc:sample['error']=f'{type(exc).__name__}: {exc}'
                        pair[backend]=sample['payload']
                    if sample.get('error'):
                        report['errors'].append({'iterations':n,'repeat':repeat+1,'backend':backend,'error':sample['error']})
                if set(pair)==set(spec['backends']):
                    comparison=core.compare(pair['python'],pair['native'],spec)
                    comparison['repeat']=repeat+1;row['paired_comparisons'].append(comparison)
                    if not comparison['meets_metric_gate'] or not comparison['meets_policy_gate']:
                        report['errors'].append({'iterations':n,'repeat':repeat+1,'error':'Backend parity failed'})
            row['median_complete_seconds']={b:statistics.median(x['complete_seconds'] for x in row['samples'] if x['backend']==b)
                if final and len([x for x in row['samples'] if x['backend']==b and 'payload' in x])==3 else None for b in spec['backends']}
            if final:
                for b in spec['backends']:
                    samples=[x for x in row['samples'] if x['backend']==b]
                    if (len(samples)!=3 or any(not x.get('assessment',{}).get('quality_pass')
                             for x in samples)
                            or len({x.get('payload_sha256') for x in samples})!=1):
                        report['errors'].append({'backend':b,'error':'Final quality/determinism failed'})
        after=snapshot();build_after=core.native._build_identity(build)
        if before!=after or build_before!=build_after:raise ValueError('Source or native build changed')
    except Exception as exc:
        report['errors'].append({'phase':'runner','error':f'{type(exc).__name__}: {exc}'})
    report.update({'source_before':before,'source_after':after,'native_build_before':build_before,'native_build_after':build_after,
                   'source_unchanged':before is not None and before==after,
                   'native_build_unchanged':build_before is not None and build_before==build_after})
    report['status']='passed' if not report['errors'] else 'error'
    report['artifact_sha256']=core.checksum(report)
    return report


def verify_saved(path):
    data=json.loads(Path(path).read_bytes());unsigned=dict(data);digest=unsigned.pop('artifact_sha256')
    if core.checksum(unsigned)!=digest:raise ValueError('mixed AA/QQ-KK saved report checksum failed')
    if data.get('status')!='passed':raise ValueError('Saved mixed observation did not pass')
    spec=data['specification']
    if data.get('spec_sha256')!=reference.SPEC_SHA or data.get('benchmark_id')!=spec['benchmark_id']:
        raise ValueError('Saved mixed observation/spec identity changed')
    if core.checksum(spec)!=reference.SPEC_SHA:raise ValueError('mixed AA/QQ-KK saved spec changed')
    table,counts,source=reference.load_inputs(spec)
    if data['status']=='passed' and (data['constructive_value_bounds']!=reference.constructive_bounds(spec,counts)
            or data['trusted_physical_count_rows']!=counts or data['count_provenance']!=table.provenance()
            or data['table_budget']!=table.budget or data['source_reference']!=source or data['preflights']!=[core.preflight(table,spec,n) for n in spec['checkpoints']]):
        raise ValueError('mixed AA/QQ-KK saved proof, physical provenance or preflight changed')
    checked=comparisons=0
    if data['status']=='passed' and [row['iterations'] for row in data['profiles']]!=spec['checkpoints']:
        raise ValueError('mixed AA/QQ-KK checkpoint census failed')
    for row in data['profiles']:
        final=row['iterations']==spec['checkpoints'][-1];pairs={}
        for sample in row['samples']:
            if sample.get('error') and data['status']=='passed':raise ValueError('Passed observation contains failed sample')
            if 'payload' not in sample:continue
            payload=sample['payload'];encoded=core.canonical(payload)
            if (hashlib.sha256(encoded).hexdigest()!=sample['payload_sha256'] or len(encoded)!=sample['serialized_bytes_utf8']
                    or mixed_assessment(payload,counts,spec)!=sample['assessment']
                    or payload['iterations']!=row['iterations'] or payload['algorithm']!=spec['algorithm']
                    or payload.get('world_indexing')!=spec['world_indexing']
                    or any(sample['rank_guard_calls'].values())
                    or not core.native._phase_count_passed('preflop',sample['backend'],'cfrplus',sample)):
                raise ValueError('mixed AA/QQ-KK saved policy/digest/replay/execution census changed')
            pairs.setdefault(sample['repeat'],{})[sample['backend']]=payload;checked+=1
        for repeat,pair in pairs.items():
            if set(pair)==set(spec['backends']):
                comparison=core.compare(pair['python'],pair['native'],spec);comparison['repeat']=repeat
                if comparison not in row['paired_comparisons'] or (data['status']=='passed' and
                       not (comparison['meets_metric_gate'] and comparison['meets_policy_gate'])):
                    raise ValueError('mixed AA/QQ-KK saved backend comparison failed')
                comparisons+=1
        if data['status']=='passed':
            if len(row['paired_comparisons'])!=(3 if final else 1):raise ValueError('Mixed comparison census failed')
            expected=[(r+1,b) for r in range(3 if final else 1)
                      for b in (spec['backends'] if r%2==0 else list(reversed(spec['backends'])))]
            if [(x['repeat'],x['backend']) for x in row['samples']]!=expected:
                raise ValueError('mixed AA/QQ-KK paired sample order failed')
            for b in spec['backends']:
                samples=[x for x in row['samples'] if x['backend']==b]
                median=statistics.median(x['complete_seconds'] for x in samples) if final else None
                if row['median_complete_seconds'][b]!=median:raise ValueError('mixed AA/QQ-KK median summary failed')
                if final and (any(not x['assessment']['quality_pass'] for x in samples)
                              or len({x['payload_sha256'] for x in samples})!=1):
                    raise ValueError('mixed AA/QQ-KK final quality/determinism failed')
    if data['status']=='passed' and (checked!=10 or comparisons!=5 or data['errors']
            or not data['source_unchanged'] or not data['native_build_unchanged']
            or data['source_before']!=data['source_after'] or data['source_before']['status']
            or data['native_build_before']!=data['native_build_after']):
        raise ValueError('mixed AA/QQ-KK complete saved observation/integrity census failed')
    return {'status':'passed','replayed_physical_policies':checked,'paired_comparisons':comparisons,
            'constructive_value_interval_sb_fraction':['1/2','1']}


def save_report(path,report):
    report.pop('artifact_sha256',None);report['artifact_sha256']=core.checksum(report)
    core.save(path,report)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--build-dir',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args(argv)
    path=args.output.resolve()
    if path==ROOT or ROOT in path.parents or path.exists() or path.with_name(path.name+'.tmp').exists():
        parser.error('Use a new report path outside checkout')
    spec=json.loads(reference.SPEC.read_bytes());report=run(spec,args.build_dir);save_report(path,report)
    try:
        report['saved_verification']=verify_saved(path)
        if report['source_after'] is not None and snapshot()!=report['source_after']:
            raise ValueError('Source changed during saved-file verification')
        if report['native_build_after'] is not None and core.native._build_identity(args.build_dir)!=report['native_build_after']:
            raise ValueError('Native build changed during saved-file verification')
    except Exception as exc:
        report['errors'].append({'phase':'saved-verification','error':f'{type(exc).__name__}: {exc}'});report['status']='error'
    save_report(path,report)
    if report['status']=='passed':verify_saved(path)
    print(json.dumps({'status':report['status'],'artifact_sha256':report['artifact_sha256'],'errors':report['errors']}),flush=True)
    return 0 if report['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
