"""Freeze a mixed physical exact candidate and independently certify legal responses."""
import argparse
from contextlib import ExitStack
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch
from scripts import certify_preflop_sequence as base
from scripts.benchmark_preflop_covered_counts import canonical,checksum

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/'benchmarks/preflop-mixed-exact-witness-v1.json'
SPEC_SHA='4307f9590e2f34d568cab929c0401eab572a7c0af0725f6181299a5b6636aa19'


def snapshot():
    state=base._snapshot()
    for name in ('benchmarks/preflop-mixed-exact-witness-v1.json','benchmarks/preflop-mixed-physical-range-v1.json',
                 'benchmarks/results/preflop-five-basis-v1.json','benchmarks/results/preflop-qq-kk-basis-v1.json'):
        path=ROOT/name;raw=path.read_bytes()
        state['source_hashes'][name]={'raw_sha256':hashlib.sha256(raw).hexdigest(),
                                   'lf_sha256':hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()}
    return state


def verify_independently(candidate):
    # Resolve the oracle before disabling the producer and numeric tree. The
    # saved witness, physical source reports and literal paths are its inputs.
    from scripts import preflop_mixed_pure_response as independent
    from scripts import preflop_mixed_sequence_candidate as producer
    from scripts import preflop_checkdown_validation as rules
    from scripts import river_sequence_form as lp
    with ExitStack() as stack:
        for owner,name in ((producer,'build_candidate'),(rules,'_build'),(lp,'_solve_lp')):
            stack.enter_context(patch.object(owner,name,side_effect=AssertionError('Independent oracle invoked candidate/rules/LP')))
        checked=independent.verify_candidate(candidate)
        if checked.get('status')!='passed' or checked.get('nash_conv_fraction')!='0':
            raise ValueError('Independent physical mutual-response certificate did not pass')
        return checked


def run(spec):
    if checksum(spec)!=SPEC_SHA:raise ValueError('Requires frozen mixed exact specification')
    report={'schema_version':1,'benchmark_id':spec['benchmark_id'],'specification':spec,'spec_sha256':SPEC_SHA,
            'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'runtime':{'python':sys.version,'executable':sys.executable,'platform':platform.platform()},
            'errors':[],'source_before':None,'source_after':None,'source_unchanged':False,
            'guard_calls':{},'candidate_witness':None,'independent_verification':None,
            'serialized_witness_verification':None,'scope':spec['scope']}
    started=perf_counter()
    try:
        before=report['source_before']=snapshot()
        if before['status']:raise ValueError('Formal mixed exact certificate requires clean committed source')
        if subprocess.run(['git','merge-base','--is-ancestor',spec['baseline_commit'],before['revision']],cwd=ROOT).returncode:
            raise ValueError('Frozen physical benchmark baseline is not an ancestor of source')
        with base._guards() as calls:
            report['guard_calls']=calls
            from scripts.preflop_mixed_sequence_candidate import build_candidate
            candidate=report['candidate_witness']=build_candidate(spec)
            report['independent_verification']=verify_independently(candidate)
            report['serialized_witness_verification']=verify_independently(json.loads(canonical(candidate)))
            if report['independent_verification']!=report['serialized_witness_verification']:
                raise ValueError('Mixed serialized policy proof changed')
            if any(calls.values()):raise ValueError('Mixed witness invoked forbidden production computation')
    except Exception as exc:
        report['errors'].append({'phase':'candidate-or-verification','error':f'{type(exc).__name__}: {exc}'})
    finally:
        report['total_seconds']=perf_counter()-started
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
    if path.stat().st_size>2000000:raise ValueError('Saved mixed proof exceeds size limit')
    data=json.loads(path.read_bytes());unsigned=dict(data);digest=unsigned.pop('artifact_sha256')
    if checksum(unsigned)!=digest or data.get('status')!='passed' or data.get('errors'):
        raise ValueError('Saved mixed proof checksum or passed status failed')
    spec=data['specification']
    if checksum(spec)!=SPEC_SHA or data['spec_sha256']!=SPEC_SHA or data['benchmark_id']!=spec['benchmark_id']:
        raise ValueError('Saved mixed proof specification changed')
    if (not data['source_unchanged'] or data['source_before']!=data['source_after'] or data['source_before']['status']
            or not data['guard_calls'] or any(data['guard_calls'].values())):
        raise ValueError('Saved mixed proof source/production-guard census failed')
    with base._guards() as calls:
        if set(data['guard_calls'])!=set(calls):raise ValueError('Saved mixed proof production-guard names changed')
        checked=verify_independently(data['candidate_witness'])
        if any(calls.values()):raise ValueError('Saved mixed proof invoked forbidden production computation')
    if checked!=data['independent_verification'] or checked!=data['serialized_witness_verification']:
        raise ValueError('Saved mixed physical-response proof changed')
    return checked


def save(path,report):
    report.pop('artifact_sha256',None);report['artifact_sha256']=checksum(report)
    base._write(Path(path),report,replacing_owned=Path(path).exists())


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv);path=args.output.resolve()
    if path==ROOT or ROOT in path.parents or path.exists() or path.with_name(path.name+'.tmp').exists():
        parser.error('Preserve existing observations; use a fresh external output path')
    report=run(json.loads(SPEC.read_bytes()));save(path,report)
    try:
        report['saved_verification']=verify_saved(path)
        if snapshot()!=report['source_after']:raise ValueError('Source changed during saved proof replay')
    except Exception as exc:
        report['errors'].append({'phase':'saved-verification','error':f'{type(exc).__name__}: {exc}'});report['status']='error'
    save(path,report)
    if report['status']=='passed':verify_saved(path)
    print(json.dumps({'status':report['status'],'artifact_sha256':report['artifact_sha256'],'errors':report['errors']}),flush=True)
    return 0 if report['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
