"""Independent best-five reference validation and fixed AA/KK physical census.

All five-card tuples are compared to the project-owned Python five-card oracle
before full-board reference counts are compared to the production seven-card
counter. This research path never trains a solver or changes evaluator defaults.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
from pathlib import Path
import subprocess
from time import perf_counter
import sys
from scripts.build_preflop_five_reference import SOURCE,PROTOCOL,source_hashes
from scripts.preflop_validation import _five_rank
from scripts import benchmark_preflop_covered_counts as covered
from pokerlab.native_preflop_equity import prepare_native_preflop_equities
from pokerlab.preflop_full_board_equity import plan_preflop_equities

ROOT=Path(__file__).resolve().parents[1]
SPEC_PATH=ROOT/'benchmarks/preflop-five-basis-v1.json'
SPEC_SHA256='fdea260fe8de3e9bfb48be09b2faed8e74db4465041a994ff20e8d7c74935313'
DECK=tuple(r+s for r in '23456789TJQKA' for s in 'cdhs')
FIVE_TOTAL=2598960
FIVE_BYTES=6*FIVE_TOTAL
EXPECTED_CATEGORIES={0:1302540,1:1098240,2:123552,3:54912,4:10200,5:5108,6:3744,7:624,8:40}
PAIRS=(('AdAs','KdKs'),('AdAs','KcKd'),('AdAs','KcKh'))


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def checksum(value):return hashlib.sha256(canonical(value)).hexdigest()


def snapshot():
    state=covered.identity();raw=SPEC_PATH.read_bytes()
    state['source_hashes'][SPEC_PATH.relative_to(ROOT).as_posix()]={
        'raw_sha256':hashlib.sha256(raw).hexdigest(),
        'lf_sha256':hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()}
    return state


def backend(build_directory):
    directory=Path(build_directory).resolve(strict=True);path=directory/'five-reference-manifest.json'
    if path.stat().st_size>32768:raise ValueError('Reference manifest exceeds its input bound')
    manifest=json.loads(path.read_bytes())
    expected={'schema_version','protocol','source_sha256','source_lf_sha256','executable',
              'executable_sha256','compiler','compiler_version','flags','platform'}
    if type(manifest) is not dict or set(manifest)!=expected or type(manifest['schema_version']) is not int or manifest['schema_version']!=1 or manifest['protocol']!=PROTOCOL:
        raise ValueError('Unsupported reference build identity')
    names={'preflop-five-reference','preflop-five-reference.exe'}
    if type(manifest['executable']) is not str or manifest['executable'] not in names:raise ValueError('Unexpected reference executable name')
    executable=directory/manifest['executable']
    if executable.is_symlink() or not executable.is_file():raise ValueError('Reference executable must be a regular file')
    if source_hashes()!=(manifest['source_sha256'],manifest['source_lf_sha256']):
        raise ValueError('Reference source changed; build explicitly in a new directory')
    digest=hashlib.sha256(executable.read_bytes()).hexdigest()
    if digest!=manifest['executable_sha256']:raise ValueError('Reference executable identity changed')
    return executable,{'manifest':manifest,'manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                       'executable_sha256':digest}


def validate_five_dump(path,progress=None):
    path=Path(path)
    if path.stat().st_size!=FIVE_BYTES:raise ValueError('Five-card dump must contain exactly 2598960 six-byte tuples')
    categories={i:0 for i in range(9)};mismatches=[];digest=hashlib.sha256();processed=0
    with path.open('rb') as stream:
        for hand in combinations(DECK,5):
            row=stream.read(6)
            if len(row)!=6:raise ValueError('Truncated five-card reference dump')
            digest.update(row)
            expected=tuple(_five_rank(hand));expected+= (0,)*(6-len(expected))
            if row!=bytes(expected):
                if len(mismatches)<10:mismatches.append({'hand':list(hand),'expected':list(expected),'actual':list(row)})
            if row[0]>8:raise ValueError('Five-card reference category outside 0..8')
            categories[row[0]]+=1;processed+=1
            if progress and processed%100000==0:progress(processed,FIVE_TOTAL)
        if stream.read(1):raise ValueError('Five-card reference dump has trailing bytes')
    passed=(processed==FIVE_TOTAL and categories==EXPECTED_CATEGORIES and not mismatches)
    return {'status':'passed' if passed else 'error','rank_tuples_checked':processed,
            'category_counts':categories,'mismatches_first_ten':mismatches,
            'dump_bytes':FIVE_BYTES,'dump_sha256':digest.hexdigest()}


def verify_count_result(data):
    if (type(data) is not dict or set(data)!={'schema_version','reference','pairs','boards_total',
            'five_card_rank_calls','seven_card_rank_calls'} or data['schema_version']!=1
            or type(data['schema_version']) is not int
            or data['reference']!='preflop-five-card-basis-v1' or type(data['pairs']) is not list or len(data['pairs'])!=3
            or type(data['boards_total']) is not int or data['boards_total']!=5136912
            or type(data['five_card_rank_calls']) is not int or data['five_card_rank_calls']!=215750304
            or type(data['seven_card_rank_calls']) is not int or data['seven_card_rank_calls']!=10273824):
        raise ValueError('Independent reference work/shape differs from the fixed admission')
    rows=[]
    for row,(sb,bb) in zip(data['pairs'],PAIRS):
        if type(row) is not dict or set(row)!={'sb_ids','bb_ids','wins','ties','losses','boards'}:
            raise ValueError('Independent reference pair row shape changed')
        for field,hand in (('sb_ids',sb),('bb_ids',bb)):
            ids=row[field]
            if (type(ids) is not list or len(ids)!=2 or any(type(x) is not int or not 0<=x<52 for x in ids)
                    or ''.join(DECK[x] for x in ids)!=hand):
                raise ValueError('Independent reference ordered private pair changed')
        if (any(type(row[k]) is not int or row[k]<0 for k in ('wins','ties','losses','boards'))
                or row['boards']!=1712304 or sum(row[k] for k in ('wins','ties','losses'))!=1712304):
            raise ValueError('Independent physical counts fail integer board coverage')
        rows.append({'sb_hand':sb,'bb_hand':bb,**{k:row[k] for k in ('wins','ties','losses','boards')}})
    return rows


def save(path,data):
    data.pop('artifact_sha256',None);data['artifact_sha256']=checksum(data)
    temp=path.with_name(path.name+'.tmp')
    with temp.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(data,stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')
    temp.replace(path)


def run(reference_build,candidate_build,output_directory):
    directory=Path(output_directory).resolve()
    if directory==ROOT or ROOT in directory.parents or directory.exists():
        raise ValueError('Use a new output directory outside the checkout')
    directory.mkdir(parents=True)
    report={'schema_version':1,'benchmark_id':'preflop-five-basis-v1','created_at_utc':datetime.now(timezone.utc).isoformat(),
            'runtime':{'python':sys.version,'platform':__import__('platform').platform()},'errors':[]}
    path=directory/'report.json';before=after=reference_before=reference_after=None
    try:
        spec=json.loads(SPEC_PATH.read_bytes())
        if checksum(spec)!=SPEC_SHA256:raise ValueError('Requires exact frozen physical-reference specification')
        report['specification']=spec;report['spec_sha256']=SPEC_SHA256
        before=snapshot()
        if before['status']:raise ValueError('Formal reference run requires clean committed source')
        # Candidate preparation admission still precedes any executable lookup.
        plan=plan_preflop_equities('AdAs','KdKs,KcKd,KcKh');plan.validate()
        if len(plan.pairs)!=3:raise ValueError('Fixed source-basis candidate admission changed')
        report['candidate_preflight']=plan.budget
        exe,reference_before=backend(reference_build)
        dump=directory/'all-five.bin';started=perf_counter()
        with dump.open('xb') as stream:
            process=subprocess.run([str(exe),'--all-five'],stdout=stream,stderr=subprocess.PIPE,timeout=300,check=False)
        report['five_dump_generation_seconds']=perf_counter()-started
        if process.returncode:raise ValueError('Reference all-five process failed: '+process.stderr[:4096].decode(errors='replace'))
        report['five_card_exhaustive']=validate_five_dump(dump,lambda n,total:print(f'FIVE {n}/{total}',flush=True))
        if report['five_card_exhaustive']['status']!='passed':raise ValueError('Independent all-five rank conformance failed')
        _,still=backend(reference_build)
        if still!=reference_before:raise ValueError('Reference build changed after all-five verification')
        started=perf_counter();raw_counts=directory/'basis-counts.json'
        with raw_counts.open('xb') as stream:
            process=subprocess.run([str(exe),'--count-basis'],stdout=stream,stderr=subprocess.PIPE,timeout=600,check=False)
        report['reference_full_board_seconds']=perf_counter()-started
        if process.returncode:raise ValueError('Reference count process failed: '+process.stderr[:4096].decode(errors='replace'))
        if raw_counts.stat().st_size>16384:raise ValueError('Reference count JSON exceeded its output bound')
        data=json.loads(raw_counts.read_bytes());report['reference_raw_counts']=data
        rows=verify_count_result(data);report['independent_physical_count_rows']=rows
        # Check one existing independently enumerated source as an additional
        # full-seven-card combination/board-loop anchor before adding new rows.
        old=load_old_anchor()
        if rows[0]!=old:raise ValueError('Existing independent AA/KK count anchor disagrees')
        started=perf_counter();candidate=prepare_native_preflop_equities('AdAs','KdKs,KcKd,KcKh',build_directory=candidate_build)
        report['candidate_full_board_seconds']=perf_counter()-started
        report['candidate_metadata']=candidate.metadata
        actual={(''.join(candidate.equities.hands[0][i]),''.join(candidate.equities.hands[1][j])):counts
                for (i,j,_),counts in zip(candidate.equities.pairs,candidate.equities.counts)}
        for row in rows:
            if actual[(row['sb_hand'],row['bb_hand'])]!=(row['wins'],row['ties'],row['losses']):
                raise ValueError('Independent best-five and production seven-card full-board counts disagree')
        report['all_three_physical_censuses_agree']=True
        after=snapshot();_,reference_after=backend(reference_build)
        if before!=after or reference_before!=reference_after:raise ValueError('Source/reference build identity changed')
    except Exception as exc:
        report['errors'].append({'type':type(exc).__name__,'message':str(exc)})
    report.update({'source_before':before,'source_after':after,'reference_build_before':reference_before,
                   'reference_build_after':reference_after,'source_unchanged':before is not None and before==after,
                   'reference_build_unchanged':reference_before is not None and reference_before==reference_after})
    report['status']='passed' if not report['errors'] else 'error';save(path,report)
    restored=json.loads(path.read_bytes());unsigned=dict(restored);digest=unsigned.pop('artifact_sha256')
    if checksum(unsigned)!=digest:raise ValueError('Saved reference report checksum failed')
    if report['status']=='passed':
        if verify_count_result(restored['reference_raw_counts'])!=restored['independent_physical_count_rows']:
            raise ValueError('Saved physical rows changed')
        if snapshot()!=after or backend(reference_build)[1]!=reference_after:
            raise ValueError('Final source/reference identity changed')
    return path,report


def load_old_anchor():
    from scripts.preflop_exact_anchor_validation import load_reference
    rows=load_reference()['counts']
    return next(row for row in rows if (row['sb_hand'],row['bb_hand'])==PAIRS[0])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-build',required=True);parser.add_argument('--candidate-build',required=True)
    parser.add_argument('--output-dir',required=True);args=parser.parse_args()
    path,report=run(args.reference_build,args.candidate_build,args.output_dir)
    print(json.dumps({'path':str(path),'status':report['status'],'artifact_sha256':report['artifact_sha256'],'errors':report['errors']}),flush=True)
    raise SystemExit(0 if report['status']=='passed' else 1)
