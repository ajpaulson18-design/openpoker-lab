"""Bounded physical count reference for explicit independently checked private pairs.

Only range/card grammar and production admission are shared; compatible pairs
are separately reconstructed, and all W/T/L counts come from the best-five C
reference after current-build exhaustive conformance is verified.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from time import perf_counter

from pokerlab.cards import expand_range
from pokerlab.preflop_full_board_equity import plan_preflop_equities
from scripts.validate_preflop_five_reference import backend,verify_saved,checksum,DECK

MAX_PAIRS=4
MAX_BOARDS=6849216
MAX_SEVEN_CALLS=13698432
MAX_FIVE_CALLS=287667072
MAX_OUTPUT_BYTES=16384
ROOT=Path(__file__).resolve().parents[1]


def pair_admission(sb_range,bb_range):
    # The ordinary planner still enforces all original bounds before a
    # reference build or conformance report is even resolved.
    if any(type(value) is not str or len(value)>32768 for value in (sb_range,bb_range)):
        raise ValueError('Reference ranges must be bounded grammar expressions')
    plan=plan_preflop_equities(sb_range,bb_range);plan.validate()
    ranges=(expand_range(sb_range),expand_range(bb_range))
    pairs=[(a,b) for a in sorted(ranges[0]) for b in sorted(ranges[1]) if set(a).isdisjoint(b)]
    if not 1<=len(pairs)<=MAX_PAIRS:raise ValueError('Reference requires one to four compatible pairs')
    planned={(plan.hands[0][i],plan.hands[1][j]) for i,j,_ in plan.pairs}
    if set(pairs)!=planned:raise ValueError('Independent private pair reconstruction disagrees with admission')
    p=len(pairs)
    return pairs,{'compatible_pairs':p,'boards':1712304*p,'seven_card_rank_calls':3424608*p,
                  'five_card_rank_calls':71916768*p,'ordinary_preparation':plan.budget,
                  'limits':{'pairs':MAX_PAIRS,'boards':MAX_BOARDS,'seven_card_rank_calls':MAX_SEVEN_CALLS,
                            'five_card_rank_calls':MAX_FIVE_CALLS}}


def verify_rows(data,pairs):
    p=len(pairs)
    if not 1<=p<=MAX_PAIRS:raise ValueError('Reference pair count outside 1..4')
    if (type(data) is not dict or set(data)!={'schema_version','reference','pairs','boards_total',
            'seven_card_rank_calls','five_card_rank_calls'} or type(data['schema_version']) is not int
            or data['schema_version']!=1 or data['reference']!='preflop-five-card-pairs-v2'
            or type(data['pairs']) is not list or len(data['pairs'])!=p):
        raise ValueError('Generic reference result shape/version changed')
    for field,n in (('boards_total',1712304*p),('seven_card_rank_calls',3424608*p),('five_card_rank_calls',71916768*p)):
        if type(data[field]) is not int or data[field]!=n:raise ValueError('Generic reference actual work census changed')
    rows=[]
    for row,(a,b) in zip(data['pairs'],pairs):
        if type(row) is not dict or set(row)!={'sb_ids','bb_ids','wins','ties','losses','boards'}:
            raise ValueError('Generic reference row shape changed')
        for field,hand in (('sb_ids',a),('bb_ids',b)):
            ids=row[field]
            if (type(ids) is not list or len(ids)!=2 or any(type(n) is not int or not 0<=n<52 for n in ids)
                    or tuple(DECK[n] for n in ids)!=hand):
                raise ValueError('Generic reference ordered private hand changed')
        if (any(type(row[k]) is not int or row[k]<0 for k in ('wins','ties','losses','boards'))
                or row['boards']!=1712304 or sum(row[k] for k in ('wins','ties','losses'))!=1712304):
            raise ValueError('Generic reference physical W/T/L census failed')
        rows.append((''.join(a),''.join(b),row['wins'],row['ties'],row['losses'],row['boards']))
    return tuple(rows)


@dataclass(frozen=True)
class ReferencePreflopCounts:
    counts:tuple
    _metadata_json:str
    @property
    def rows(self):
        return [{'sb_hand':a,'bb_hand':b,'wins':w,'ties':t,'losses':l,'boards':n}
                for a,b,w,t,l,n in self.counts]
    @property
    def metadata(self):return json.loads(self._metadata_json)


class ReferenceCountFailure(ValueError):
    def __init__(self,message,observation):
        super().__init__(message)
        self.observation=observation


def reference_preflop_counts(sb_range,bb_range,*,build_directory,conformance_report,observation_directory):
    pairs,admission=pair_admission(sb_range,bb_range)
    path=Path(conformance_report)
    if path.stat().st_size>1000000:raise ValueError('Conformance report exceeds its input bound')
    with path.open('rb') as stream:raw=stream.read(1000001)
    if len(raw)>1000000:raise ValueError('Conformance report exceeds its input bound')
    conformance=json.loads(raw)
    checked=verify_saved(path)
    if checked.get('status')!='passed':raise ValueError('Reference build requires passing exhaustive conformance')
    exe,before=backend(build_directory)
    if (conformance['reference_build_before']!=before or conformance['reference_build_after']!=before
            or conformance['reference_build_unchanged'] is not True):
        raise ValueError('Conformance belongs to another reference source/executable build')
    ids={card:n for n,card in enumerate(DECK)}
    args=[str(exe),'--count-pairs',*[str(ids[card]) for a,b in pairs for card in a+b]]
    directory=Path(observation_directory).resolve()
    if directory==ROOT or ROOT in directory.parents or directory.exists():
        raise ValueError('Use a new external count-observation directory')
    directory.mkdir(parents=True)
    output_path=directory/'stdout.json';error_path=directory/'stderr.txt'
    observed={'admission':admission,'build':before,'argv':args,'stdout_path':str(output_path),
              'stderr_path':str(error_path)}
    started=perf_counter()
    try:
        with output_path.open('xb') as output,error_path.open('xb') as error:
            process=subprocess.run(args,stdout=output,stderr=error,timeout=600,check=False)
        observed['returncode']=process.returncode
        observed['stdout_bytes']=output_path.stat().st_size
        if process.returncode:raise ValueError('Best-five pair reference process failed')
        if output_path.stat().st_size>MAX_OUTPUT_BYTES:raise ValueError('Best-five reference exceeded output bound')
        payload=output_path.read_bytes()
        try:data=json.loads(payload)
        except (UnicodeError,json.JSONDecodeError) as exc:raise ValueError('Best-five reference emitted invalid JSON') from exc
        counts=verify_rows(data,pairs)
        _,after=backend(build_directory)
        if before!=after:raise ValueError('Reference source/executable changed during physical enumeration')
        if path.read_bytes()!=raw:raise ValueError('Conformance report changed during physical enumeration')
    except Exception as exc:
        observed['seconds']=perf_counter()-started
        raise ReferenceCountFailure(f'{type(exc).__name__}: {exc}',observed) from exc
    seconds=perf_counter()-started
    metadata={'reference':'preflop-five-card-pairs-v2','admission':admission,'build':before,
              'conformance_report_sha256':conformance['artifact_sha256'],
              'raw_reference_result':data,'raw_output_paths':{'stdout':str(output_path),'stderr':str(error_path)},
              'reference_complete_seconds':seconds,
              'scope':'Exact integer physical counts after current-build exhaustive five-card conformance; '
                      'no solver/default/cap change, timing comparison or cryptographic authentication claim.'}
    return ReferencePreflopCounts(counts,json.dumps(metadata,sort_keys=True,separators=(',',':'),allow_nan=False))
