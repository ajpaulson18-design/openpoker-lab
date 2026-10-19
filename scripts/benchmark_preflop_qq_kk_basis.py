"""Physically validate three QQ/KK suit classes using bounded generic best-five counts."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from time import perf_counter
from scripts import validate_preflop_five_reference as five
from scripts.preflop_five_count_reference import pair_admission,reference_preflop_counts,verify_rows
from pokerlab import native_preflop_equity as candidate
from pokerlab.preflop_full_board_equity import plan_preflop_equities

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/'benchmarks/preflop-qq-kk-basis-v1.json'
SPEC_SHA='8cbe4ec3dcae27b0dd6189a5ccf4b137b6078440afc92e28d725ab5d6724a36c'


def snapshot():
    state=five.snapshot();raw=SPEC.read_bytes()
    state['source_hashes'][SPEC.relative_to(ROOT).as_posix()]={
        'raw_sha256':hashlib.sha256(raw).hexdigest(),
        'lf_sha256':hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()}
    return state


def candidate_identity(build):
    exe,manifest=candidate._backend(build)
    return {'manifest':manifest,'executable_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
            'manifest_sha256':hashlib.sha256((Path(build)/'native-preflop-manifest.json').read_bytes()).hexdigest()}


def old_anchor(spec):
    pinned=spec['old_shared_suits_anchor'];data=json.loads((ROOT/pinned['path']).read_bytes())
    unsigned=dict(data);digest=unsigned.pop('artifact_sha256')
    if digest!=pinned['artifact_sha256'] or five.checksum(unsigned)!=digest:
        raise ValueError('Original independent QQ/KK count artifact changed')
    row={k:data['counts'][k] for k in ('sb_hand','bb_hand','wins','ties','losses','boards')}
    expected={k:pinned[k] for k in ('sb_hand','bb_hand','wins','ties','losses')};expected['boards']=1712304
    if row!=expected:raise ValueError('Original QQ/KK source row differs from the frozen anchor')
    return row


def run(reference_build,candidate_build,output_directory):
    directory=Path(output_directory).resolve()
    if directory==ROOT or ROOT in directory.parents or directory.exists():
        raise ValueError('Use a new external QQ/KK observation directory')
    directory.mkdir(parents=True)
    report={'schema_version':1,'benchmark_id':'preflop-qq-kk-basis-v1','created_at_utc':datetime.now(timezone.utc).isoformat(),
            'runtime':{'python':sys.version,'executable':sys.executable,'platform':__import__('platform').platform()},'errors':[]}
    before=after=ref_before=ref_after=cand_before=cand_after=None
    path=directory/'report.json'
    try:
        spec=json.loads(SPEC.read_bytes())
        if five.checksum(spec)!=SPEC_SHA:raise ValueError('Requires exact frozen QQ/KK source specification')
        report['specification']=spec;report['spec_sha256']=SPEC_SHA
        before=snapshot()
        if before['status']:raise ValueError('QQ/KK source validation requires clean committed source')
        pairs,admission=pair_admission(spec['sb_range'],spec['bb_range'])
        # Admit both fixed conformance and the separate QQ/KK query before
        # resolving either binary. No production request exceeds four pairs.
        conformance_plan=plan_preflop_equities('AdAs','KdKs,KcKd,KcKh');conformance_plan.validate()
        report['query_admission']=admission
        report['conformance_candidate_admission']=conformance_plan.budget
        _,ref_before=five.backend(reference_build);cand_before=candidate_identity(candidate_build)
        conformance_path,conformance=five.run(reference_build,candidate_build,directory/'conformance')
        report['current_build_conformance']=conformance
        if conformance['status']!='passed':raise ValueError('Current reference build failed exhaustive conformance')
        result=reference_preflop_counts(spec['sb_range'],spec['bb_range'],build_directory=reference_build,
                                       conformance_report=conformance_path,observation_directory=directory/'qq-reference-raw')
        report['independent_physical_count_rows']=result.rows;report['reference_metadata']=result.metadata
        anchor=old_anchor(spec)
        if next((x for x in result.rows if (x['sb_hand'],x['bb_hand'])==(anchor['sb_hand'],anchor['bb_hand'])),None)!=anchor:
            raise ValueError('Generic reference does not reproduce the original QQ/KK shared-suits anchor')
        started=perf_counter();prepared=candidate.prepare_native_preflop_equities(spec['sb_range'],spec['bb_range'],build_directory=candidate_build)
        report['candidate_complete_seconds']=perf_counter()-started
        report['candidate_metadata']=prepared.metadata;report['candidate_equity_table']=prepared.equities.metadata()
        actual={(''.join(prepared.equities.hands[0][i]),''.join(prepared.equities.hands[1][j])):counts
                for (i,j,_),counts in zip(prepared.equities.pairs,prepared.equities.counts)}
        expected={(x['sb_hand'],x['bb_hand']):(x['wins'],x['ties'],x['losses']) for x in result.rows}
        if actual!=expected:raise ValueError('Best-five reference and native seven-card QQ/KK counts disagree')
        report['all_three_qq_kk_censuses_agree']=True
        after=snapshot();_,ref_after=five.backend(reference_build);cand_after=candidate_identity(candidate_build)
        if before!=after or ref_before!=ref_after or cand_before!=cand_after:raise ValueError('QQ/KK source or counter build changed')
    except Exception as exc:
        if hasattr(exc,'observation'):report['reference_failed_observation']=exc.observation
        report['errors'].append({'type':type(exc).__name__,'message':str(exc)})
    report.update({'source_before':before,'source_after':after,'reference_build_before':ref_before,
                   'reference_build_after':ref_after,'candidate_build_before':cand_before,'candidate_build_after':cand_after,
                   'source_unchanged':before is not None and before==after,
                   'reference_build_unchanged':ref_before is not None and ref_before==ref_after,
                   'candidate_build_unchanged':cand_before is not None and cand_before==cand_after})
    report['status']='passed' if not report['errors'] else 'error';five.save(path,report)
    try:
        report['saved_verification']=verify_saved(path)
        if report['status']=='passed' and (snapshot()!=after or five.backend(reference_build)[1]!=ref_after
                                         or candidate_identity(candidate_build)!=cand_after):
            raise ValueError('Final QQ/KK source or counter identity changed')
    except Exception as exc:
        report['errors'].append({'phase':'saved-verification','type':type(exc).__name__,'message':str(exc)});report['status']='error'
    five.save(path,report)
    if report['status']=='passed':verify_saved(path)
    return path,report


def verify_saved(path):
    report=json.loads(Path(path).read_bytes());unsigned=dict(report);digest=unsigned.pop('artifact_sha256')
    if five.checksum(unsigned)!=digest:raise ValueError('Saved QQ/KK report checksum failed')
    if five.checksum(report.get('specification'))!=SPEC_SHA or report.get('spec_sha256')!=SPEC_SHA:
        raise ValueError('Saved QQ/KK specification changed')
    if report['status']!='passed':return {'status':'recorded-failed-observation'}
    spec=report['specification'];pairs,admission=pair_admission(spec['sb_range'],spec['bb_range'])
    if report['query_admission']!=admission:raise ValueError('Saved QQ/KK admission changed')
    with tempfile.TemporaryDirectory() as temp:
        conformance=Path(temp)/'conformance.json';conformance.write_text(json.dumps(report['current_build_conformance']),encoding='utf-8')
        checked=five.verify_saved(conformance)
    if checked['status']!='passed':raise ValueError('Saved current-build five-card conformance failed')
    if (report['current_build_conformance']['reference_build_before']!=report['reference_build_before']
            or report['reference_metadata']['build']!=report['reference_build_before']
            or report['reference_metadata']['conformance_report_sha256']!=report['current_build_conformance']['artifact_sha256']):
        raise ValueError('Saved conformance and generic count executable identities disagree')
    rows=verify_rows(report['reference_metadata']['raw_reference_result'],pairs)
    simple=[{'sb_hand':a,'bb_hand':b,'wins':w,'ties':t,'losses':l,'boards':n} for a,b,w,t,l,n in rows]
    if simple!=report['independent_physical_count_rows']:raise ValueError('Saved generic independent count rows differ from raw response')
    anchor=old_anchor(spec)
    if next((x for x in simple if (x['sb_hand'],x['bb_hand'])==(anchor['sb_hand'],anchor['bb_hand'])),None)!=anchor:
        raise ValueError('Saved QQ/KK source anchor changed')
    actual={}
    for row in report['candidate_equity_table']['counts']:
        key=row['sb_hand'],row['bb_hand']
        if key in actual or row['board_outcomes']!=1712304 or any(type(row[k]) is not int or row[k]<0 for k in ('wins','ties','losses')):
            raise ValueError('Saved native QQ/KK row census failed')
        actual[key]=(row['wins'],row['ties'],row['losses'])
    if actual!={(x['sb_hand'],x['bb_hand']):(x['wins'],x['ties'],x['losses']) for x in simple}:
        raise ValueError('Saved raw native/reference QQ/KK counts disagree')
    if (report['errors'] or report['source_before']!=report['source_after'] or report['source_before']['status']
            or report['reference_build_before']!=report['reference_build_after']
            or report['candidate_build_before']!=report['candidate_build_after']
            or not all(report.get(k) is True for k in ('source_unchanged','reference_build_unchanged',
                    'candidate_build_unchanged','all_three_qq_kk_censuses_agree'))):
        raise ValueError('Saved QQ/KK source/build or complete-result integrity failed')
    return {'status':'passed','physical_qq_kk_pairs_rechecked':3,'current_build_exhaustive_conformance_rechecked':True,
            'raw_best_five_and_native_counts_rechecked':True}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--reference-build',required=True)
    parser.add_argument('--candidate-build',required=True);parser.add_argument('--output-dir',required=True);args=parser.parse_args()
    path,report=run(args.reference_build,args.candidate_build,args.output_dir)
    print(json.dumps({'path':str(path),'status':report['status'],'artifact_sha256':report['artifact_sha256'],'errors':report['errors']}),flush=True)
    raise SystemExit(0 if report['status']=='passed' else 1)
