"""Fixed-flop suit-isomorphic equity transfer evidence; exact global suit maps only."""
from __future__ import annotations
import argparse, gc, hashlib, json, platform, statistics, subprocess, time, tracemalloc
from datetime import datetime, timezone
from fractions import Fraction
from itertools import permutations
from pathlib import Path
from unittest.mock import patch
from pokerlab.cards import expand_range
from pokerlab.flop_checkdown_equity import prepare_flop_checkdown_equities
from pokerlab.flop_checkdown_solver import solve_prepared_flop_checkdown
from pokerlab.flop_checkdown_worlds import FlopCheckdownPlan
from pokerlab import flop_checkdown_worlds as worlds
from pokerlab.flop_suit_equity import remap_flop_checkdown_equities_by_suit, flop_suit_remap_provenance
from scripts.benchmark_flop_weighted_eight_hand import preflight
from scripts.flop_checkdown_validation import prepare_oracle, replay

ROOT=Path(__file__).resolve().parents[1]
SPEC_PATH=ROOT/'benchmarks/flop-suit-equity-v1.json'
OUTPUT_PATH=ROOT/'benchmarks/results/flop-suit-equity-v1.json'
LIVE_PATH=ROOT.parent/'flop-suit-equity-live.json'
BASELINE='65fb169961c65e64828c93fbd01f7811a3719e4f'
SPEC_SHA='09c20fd26de53e602ae9edb1e0a34333e163f262cb77c9db9b0e69619c113749'
HIST_COMMIT=BASELINE
HIST_PATH='benchmarks/results/flop-equity-reuse-v1.json'
HIST_BLOB='baee3c0cb2e0d0e89fbe35411ae540d886448aa9'
HIST_REV='9af1e75ae57f5bcf0c0e7b8d30e388bc2038e5bc'
HIST_POLICY='2862026384f7fa27be751748742823e4e4eb580c24ee9fad01d8eeb20b7f5271'
SUITS='cdhs'; RANKS='23456789TJQKA'; DECK=tuple(r+s for r in RANKS for s in SUITS)
DECK_INDEX={c:i for i,c in enumerate(DECK)}

def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def serialize(value): return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def _sha(path): return hashlib.sha256((ROOT/path).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
def source_paths():
    paths={p.relative_to(ROOT).as_posix() for p in (ROOT/'pokerlab').glob('*.py')}
    paths.update({'AGENTS.md','scripts/preflop_validation.py','scripts/flop_checkdown_validation.py',
      'scripts/benchmark_flop_weighted_eight_hand.py','scripts/benchmark_flop_equity_reuse.py',
      'scripts/benchmark_flop_suit_equity.py','benchmarks/flop-equity-reuse-v1.json',
      'benchmarks/flop-suit-equity-v1.json','benchmarks/flop-weighted-eight-hand-v1.json',
      'docs/flop-suit-equity.md','docs/flop-equity-reuse.md',
      'tests/test_flop_checkdown_equity.py','tests/test_flop_checkdown_solver.py',
      'tests/test_flop_checkdown_worlds.py','tests/test_flop_equity_reuse_benchmark.py',
      'tests/test_flop_suit_equity.py','tests/test_flop_suit_equity_benchmark.py',
      'tests/test_flop_weighted_eight_hand.py'})
    return tuple(sorted(paths))
def source_hashes(): return {p:_sha(p) for p in source_paths()}
def revision(): return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
def status(): return subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()
def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True); temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n'); temp.replace(path)
def map_card(card,m):
    if len(card)!=2 or card[0] not in RANKS or card[1] not in SUITS: raise ValueError('Expected canonical card')
    return card[0]+m[card[1]]
def map_hand(hand,m):
    if len(hand)!=4: raise ValueError('Expected explicit two-card hand')
    return ''.join(map_card(hand[i:i+2],m) for i in (0,2))
def map_board(board,m):
    cs=[map_card(board[i:i+2],m) for i in range(0,len(board),2)]
    return ''.join(sorted(cs,key=DECK_INDEX.__getitem__))
def map_range(expr,m):
    return ','.join(f'{map_hand(h,m)}:{w}' for h,w in (x.rsplit(':',1) for x in expr.split(',')))
def expand_board(board): return tuple(sorted((board[i:i+2] for i in range(0,len(board),2)),key=DECK_INDEX.__getitem__))
def pair_census(board,oop,ip):
    expanded=[expand_range(x,board) for x in (oop,ip)]; products=[]
    for h,w in expanded[0].items():
        for k,v in expanded[1].items():
            if set(h).isdisjoint(k): products.append((h,k,Fraction.from_float(w)*Fraction.from_float(v)))
    total=sum((x[2] for x in products),Fraction())
    if total<=0: raise ValueError('No compatible pair mass')
    return expanded,{(h,k):w/total for h,k,w in products},total

def cases_from_spec(spec):
    cases=[]; board=spec['source_board']; template=spec['config_template']; single=spec['single_pair']
    for i,m0 in enumerate(single['suit_maps']):
        m={s:m0[s] for s in SUITS}; b=map_board(board,m)
        cases.append({'id':f'single-pair-image-{i:02d}','group':'single-pair-image','source_map':m,'board':b,
          'oop_range':map_hand(single['source_oop_hand'],m)+':1','ip_range':map_hand(single['source_ip_hand'],m)+':1',
          'config':{**template,**single['config']},'expected_compatible_pairs':1,'expected_normalizer':'1/1'})
    for image in spec['whole_range_images']:
        m={s:image['suit_map'][s] for s in SUITS}; cases.append({'id':image['id'],'group':'whole-range-image',
          'source_map':m,'board':map_board(board,m),'oop_range':map_range(spec['source_oop_range'],m),
          'ip_range':map_range(spec['source_ip_range'],m),
          'config':{**template,'effective_stack':image['effective_stack'],'max_raises':image['max_raises']},
          'expected_compatible_pairs':58,'expected_normalizer':'1185/64'})
    mixed=spec['mixed_same_board']; cases.append({'id':mixed['id'],'group':'mixed-two-pair',
      'source_map':{s:s for s in SUITS},'board':board,'oop_range':mixed['oop_range'],'ip_range':mixed['ip_range'],
      'config':{**template,'effective_stack':mixed['effective_stack'],'max_raises':mixed['max_raises']},
      'expected_compatible_pairs':2,'expected_normalizer':'3/4'})
    return cases

def validate_spec(spec):
    if not isinstance(spec,dict) or spec.get('schema_version')!=1: raise ValueError('Unsupported spec')
    if canonical_hash(spec)!=SPEC_SHA: raise ValueError('Frozen specification hash changed')
    if (spec.get('benchmark_id')!='flop-suit-equity-v1' or spec.get('baseline_main')!=BASELINE
        or spec.get('algorithm')!='cfrplus' or spec.get('iterations')!=4000 or spec.get('timed_repeats')!=3
        or spec.get('allocation_iterations')!=4000 or spec.get('target_nash_conv')!=.005
        or spec.get('target_padding')!=1e-9 or spec.get('scalar_tolerance')!=1e-10
        or spec.get('source_board')!='2c3c4d'): raise ValueError('Frozen solver settings changed')
    if spec.get('historical_source')!={'commit':HIST_COMMIT,'path':HIST_PATH,'blob':HIST_BLOB,
        'source_revision':HIST_REV,'whole_stack24_payload_sha256':HIST_POLICY}: raise ValueError('Pinned PR131 identity changed')
    single=spec.get('single_pair',{})
    if (single.get('source_oop_hand')!='QhJh' or single.get('source_ip_hand')!='QcQd'
        or single.get('source_pair_count')!=1 or single.get('config')!={'pot':6,'effective_stack':12,
        'bet_sizes':[.5,1],'raise_sizes':[.5],'max_raises':1,'include_all_in':True}): raise ValueError('Single-pair fixture changed')
    if single.get('suit_maps')!=[dict(zip(SUITS,p)) for p in permutations(SUITS)]: raise ValueError('24 suit maps changed')
    wanted=[{'id':'whole8-map-a','suit_map':{'c':'d','d':'c','h':'s','s':'h'},'effective_stack':24,'max_raises':2},
            {'id':'whole8-map-b','suit_map':{'c':'h','d':'s','h':'d','s':'c'},'effective_stack':24,'max_raises':2}]
    if spec.get('whole_range_images')!=wanted: raise ValueError('Whole-range maps changed')
    if spec.get('mixed_same_board')!={'id':'mixed-two-pair-same-board','oop_range':'QhJh:.5,QsJs:.25',
        'ip_range':'QcQd:1','expected_pair_priors':['2/3','1/3'],'effective_stack':12,'max_raises':1}: raise ValueError('Mixed fixture changed')
    if spec.get('config_template')!={'pot':6,'bet_sizes':[.5,1],'raise_sizes':[.5],'include_all_in':True}: raise ValueError('Action sizes changed')
    cases=cases_from_spec(spec)
    if len(cases)!=27 or len({x['id'] for x in cases})!=27: raise ValueError('Expected 27 fixed cases')
    if len({(x['board'],x['oop_range'],x['ip_range']) for x in cases[:24]})!=24 or len({x['board'] for x in cases[:24]})!=12:
        raise ValueError('Expected 24 pair images on 12 boards')
    for c in cases:
        _,priors,total=pair_census(c['board'],c['oop_range'],c['ip_range'])
        if len(priors)!=c['expected_compatible_pairs'] or total!=Fraction(c['expected_normalizer']):
            raise ValueError('Independent exact pair census mismatch: '+c['id'])
    if spec.get('expected_single_pair_counts')!={'source_oop_hand':'QhJh','source_ip_hand':'QcQd','ordered_outcomes':1980,'wins':6,'ties':60,'losses':1914}: raise ValueError('Single-pair count anchor changed')
    if spec.get('expected_full_range_counts')!={'candidate_pairs':64,'compatible_pairs':58,'ordered_worlds':114840,'unordered_boards':57420,'compatible_prior_normalizer':'1185/64'}: raise ValueError('Full-range count anchor changed')
    if spec.get('expected_mixed_counts')!={'candidate_pairs':2,'compatible_pairs':2,'ordered_worlds':3960,'unordered_boards':1980,'compatible_prior_normalizer':'3/4','pair_priors':['2/3','1/3']}: raise ValueError('Mixed-count anchor changed')
    if spec.get('expected_case_count')!=27 or spec.get('expected_single_pair_cases')!=24: raise ValueError('Case counts changed')
    if spec.get('expected_distinct_single_pair_joint_images')!=24 or spec.get('expected_distinct_single_pair_boards')!=12: raise ValueError('Distinct image census changed')
    _,priors,total=pair_census(spec['source_board'],spec['mixed_same_board']['oop_range'],spec['mixed_same_board']['ip_range'])
    if total!=Fraction(3,4) or sorted(map(str,priors.values()))!=['1/3','2/3']: raise ValueError('Mixed priors changed')
    return cases


def historical_report():
    blob=subprocess.check_output(['git','rev-parse',f'{HIST_COMMIT}:{HIST_PATH}'],cwd=ROOT,text=True).strip()
    if blob!=HIST_BLOB: raise ValueError('Pinned PR131 report blob mismatch')
    report=json.loads(subprocess.check_output(['git','show',f'{HIST_COMMIT}:{HIST_PATH}'],cwd=ROOT))
    checksum=report.get('artifact_sha256'); body=dict(report); body.pop('artifact_sha256',None)
    if checksum!=canonical_hash(body) or report.get('source_revision')!=HIST_REV: raise ValueError('Historical report checksum/revision failed')
    base=next((x for x in report.get('results',[]) if x.get('fixture_id')=='base-8x8-stack24-raises2'),None)
    if not base or base['fresh_calls'][0].get('payload_sha256')!=HIST_POLICY: raise ValueError('Pinned whole-range source policy missing')
    return report,base

def source_rows(table):
    out={}
    for (i,j,p),counts in zip(table.pairs,table.counts):
        out[(tuple(table.hands[0][i]),tuple(table.hands[1][j]))]=(p,counts)
    return out

def verify_source_counts(table,rows):
    actual=source_rows(table); expected={(tuple(r['oop_hand'][i:i+2] for i in (0,2)),tuple(r['ip_hand'][i:i+2] for i in (0,2))):r for r in rows}
    if len(rows)!=58 or len(expected)!=len(rows) or len(actual)!=58 or set(actual)!=set(expected): raise AssertionError('Prepared source support differs from pinned PR131 rows')
    for pair,(prior,c) in actual.items():
        row=expected[pair]
        if tuple(c)!=(row['wins'],row['ties'],row['losses']) or row['ordered_outcomes']!=1980:
            raise AssertionError(f'Prepared source W/T/L differs from pinned row {pair}')
    return actual

def target_rows(table):
    return {(tuple(table.hands[0][i]),tuple(table.hands[1][j])):(p,c)
            for (i,j,p),c in zip(table.pairs,table.counts)}

def verify_target(table,oracle_rows,expected_priors):
    actual=target_rows(table); expected={(tuple(r['oop_hand'][i:i+2] for i in (0,2)),tuple(r['ip_hand'][i:i+2] for i in (0,2))):r for r in oracle_rows}
    if (len(oracle_rows)!=len(expected) or len(actual)!=len(oracle_rows)
        or set(actual)!=set(expected) or set(actual)!=set(expected_priors)): raise AssertionError('Target pair support differs from independent oracle/prior census')
    for pair,(prior,c) in actual.items():
        row=expected[pair]
        if prior!=expected_priors[pair] or float(prior)!=row['pair_probability']: raise AssertionError(f'Exact target pair prior mismatch: {pair}')
        if tuple(c)!=(row['wins'],row['ties'],row['losses']) or row['ordered_outcomes']!=1980: raise AssertionError(f'Independent target W/T/L mismatch: {pair}')
    return actual

def verify_provenance(rows,source_table,target_table):
    src=source_rows(source_table); dst=target_rows(target_table); seen=set(); verified=[]
    source_pairs=set(src)
    for row in rows:
        m=row.get('suit_permutation')
        if not isinstance(m,dict) or set(m)!=set(SUITS) or set(m.values())!=set(SUITS): raise AssertionError('Provenance must contain a full four-suit bijection')
        sb=tuple(row.get('source_board',())); tb=tuple(row.get('target_board',()))
        so=tuple(row.get('source_oop_hand','')[i:i+2] for i in (0,2)); si=tuple(row.get('source_ip_hand','')[i:i+2] for i in (0,2))
        to=tuple(row.get('target_oop_hand','')[i:i+2] for i in (0,2)); ti=tuple(row.get('target_ip_hand','')[i:i+2] for i in (0,2))
        sp=(tuple(sorted(so)),tuple(sorted(si))); tp=(tuple(sorted(to)),tuple(sorted(ti)))
        if sp not in source_pairs or tp not in dst or tp in seen: raise AssertionError('Provenance endpoint not in ordered source/target support')
        seen.add(tp)
        if row.get('source_board')!=list(source_table.board): raise AssertionError('Provenance source board mismatch')
        if row.get('target_board')!=list(target_table.board): raise AssertionError('Provenance target board differs from the remapped equity table')
        if (tuple(sorted((map_card(c,m) for c in sb),key=DECK_INDEX.__getitem__))!=tb
            or tuple(sorted(map_card(c,m) for c in so))!=tp[0]
            or tuple(sorted(map_card(c,m) for c in si))!=tp[1]
            or row.get('target_oop_hand')!=''.join(tp[0]) or row.get('target_ip_hand')!=''.join(tp[1])):
            raise AssertionError('One global suit bijection fails ordered board/OOP/IP endpoints')
        if src[sp][1]!=dst[tp][1]: raise AssertionError('Transferred W/T/L row differs from selected source row')
        image={map_card(c,m) for c in DECK}
        if len(DECK)!=52 or len(image)!=52 or image!=set(DECK): raise AssertionError('Mapping is not a full 52-card bijection')
        sd=set(sb+so+si); td=set(tb+tp[0]+tp[1])
        if len(sd)!=7 or len(td)!=7: raise AssertionError('Seven board/private cards must be distinct')
        rem={map_card(c,m) for c in set(DECK)-sd}
        if len(rem)!=45 or rem!=set(DECK)-td: raise AssertionError('Remaining 45-card deck is not bijected')
        verified.append({**row,'full_deck_bijective':True,'remaining_cards_bijective':45,'ordered_roles_preserved':True})
    if seen!=set(dst) or len(rows)!=len(dst): raise AssertionError('Provenance does not cover every target pair exactly once')
    return verified

def hand_text(hand): return ''.join(sorted(hand))
def inverse_map_result(result,mapping,source_oop,source_ip,source_board):
    inv={v:k for k,v in mapping.items()}; out=json.loads(json.dumps(result)); out.pop('equity_preparation',None)
    out['board']=list(sorted((map_card(c,inv) for c in out['board']),key=DECK_INDEX.__getitem__))
    expected_board=list(expand_board(source_board))
    if out['board']!=expected_board: raise AssertionError('Inverse map did not recover source board')
    oi={hand_text(h):i for i,h in enumerate(expand_range(source_oop,source_board))}
    ii={hand_text(h):i for i,h in enumerate(expand_range(source_ip,source_board))}
    for row in out['pair_equities']:
        row['oop_hand']=hand_text(tuple(map_card(row['oop_hand'][i:i+2],inv) for i in (0,2)))
        row['ip_hand']=hand_text(tuple(map_card(row['ip_hand'][i:i+2],inv) for i in (0,2)))
    out['pair_equities'].sort(key=lambda r:(oi[r['oop_hand']],ii[r['ip_hand']]))
    for row in out['strategy']:
        mapped_board=sorted((map_card(c,inv) for c in row['board']),key=DECK_INDEX.__getitem__)
        if mapped_board!=expected_board: raise AssertionError('Strategy-row board failed inverse suit mapping')
        row['hand']=hand_text(tuple(map_card(row['hand'][i:i+2],inv) for i in (0,2)))
        row['board']=expected_board
    order={'oop':0,'ip':1}
    out['strategy'].sort(key=lambda r:(order[r['player']],(oi if r['player']=='oop' else ii)[r['hand']],tuple(r['history'])))
    return out

def guard_warm(fn):
    calls={'rank_hand':0,'combinations':0,'plan_build':0}
    def blocked(name):
        def f(*args,**kwargs): calls[name]+=1; raise AssertionError(f'Warm path called {name}')
        return f
    with patch.object(worlds,'rank_hand',blocked('rank_hand')),patch.object(worlds,'combinations',blocked('combinations')),patch.object(FlopCheckdownPlan,'build',blocked('plan_build')):
        value=fn()
    if calls!={'rank_hand':0,'combinations':0,'plan_build':0}: raise AssertionError(f'Warm rank guard changed: {calls}')
    return value,calls

def warm_call(source_table,case):
    def call():
        target=remap_flop_checkdown_equities_by_suit(source_table,case['board'],case['oop_range'],case['ip_range'])
        provenance=flop_suit_remap_provenance(source_table,case['board'],case['oop_range'],case['ip_range'])
        result=solve_prepared_flop_checkdown(target,config=case['config'],iterations=4000,algorithm='cfrplus')
        payload=serialize({'result':result,'provenance':provenance})
        return target,provenance,result,payload
    start=time.perf_counter(); (target,provenance,result,payload),guards=guard_warm(call)
    return target,provenance,result,payload,time.perf_counter()-start,guards

def verify_result(result,oracle,spec,expected_budget):
    if result.get('work_budget')!=expected_budget: raise AssertionError('Measured solver budget differs from preflight')
    checked=replay(result,oracle,spec['scalar_tolerance'])
    met=checked['nash_conv']+spec['target_padding']<=spec['target_nash_conv']
    return {'replay':checked,'target_met':met,'target_limit_with_padding':spec['target_nash_conv'],'work_budget_matches_preflight':True}

def preflight_failure_report(spec,rev,hashes,rows):
    report={'schema_version':1,'benchmark_id':spec['benchmark_id'],'source_revision':rev,
      'generated_at_utc':datetime.now(timezone.utc).isoformat(),'specification_sha256':canonical_hash(spec),
      'source_hashes_lf_normalized':hashes,'worktree_clean_at_start_and_before_publication':True,
      'specification':spec,'preflights_complete_before_ranking':len(rows)==27,'preflights':rows,
      'ranking_started':False,'results':[],'acceptance_gate_met':False,'quality_misses':[],
      'rejection_scope':'All no-rank preflight failures are retained; no source preparation, oracle ranking or training ran.'}
    report['artifact_sha256']=canonical_hash(report); atomic_json(OUTPUT_PATH,report); return report

def _run_frozen(spec=None):
    if spec is None: spec=json.loads(SPEC_PATH.read_text(encoding='utf-8-sig'))
    cases=validate_spec(spec)
    if status(): raise RuntimeError('Freeze and commit benchmark source/config before formal run')
    rev=revision()
    if subprocess.run(['git','merge-base','--is-ancestor',spec['baseline_main'],rev],cwd=ROOT,check=False).returncode:
        raise ValueError('PR131 baseline is not an ancestor')
    before=source_hashes(); clean_before=status()
    live={'benchmark_id':spec['benchmark_id'],'source_revision':rev,'phase':'starting','complete':False,'preflights':[],'results':[]}
    atomic_json(LIVE_PATH,live)
    # All 27 no-ranking admissions must finish before physical source prep or oracle work.
    preflights=[]
    for i,case in enumerate(cases):
        row=preflight(case,4000,'cfrplus'); row['fixture_id']=case['id']; preflights.append(row)
        live.update({'phase':'preflight','completed':i+1,'total':27,'active_fixture':case['id'],'preflights':preflights[:]})
        atomic_json(LIVE_PATH,live)
    if len(preflights)!=27 or any(x.get('status')!='admitted' for x in preflights):
        if source_hashes()!=before or revision()!=rev or status()!=clean_before: raise RuntimeError('Source changed during preflight')
        preflight_failure_report(spec,rev,before,preflights)
        live.update({'phase':'preflight-rejected','complete':True,'ranking_started':False,'report':OUTPUT_PATH.as_posix()})
        atomic_json(LIVE_PATH,live); raise AssertionError('Required admission rejected; no ranking started')

    live.update({'phase':'cold-source-preparation','completed':27,'total':27}); atomic_json(LIVE_PATH,live)
    gc.collect(); start=time.perf_counter()
    source=prepare_flop_checkdown_equities(spec['source_board'],spec['source_oop_range'],spec['source_ip_range'])
    cold_seconds=time.perf_counter()-start; source.validate()
    historical,baseline=historical_report(); src_counts=verify_source_counts(source,baseline['oracle_pair_counts'])
    if len(source.pairs)!=58 or source.budget['physical_worlds']!=114840 or source.budget['unordered_boards']!=57420:
        raise AssertionError('Cold 8x8 table does not match frozen support')
    failures=[]; results=[]
    for index,(case,pf) in enumerate(zip(cases,preflights)):
        live.update({'phase':'independent-oracle','active_fixture':case['id'],'completed':index,'total':27}); atomic_json(LIVE_PATH,live)
        oracle=prepare_oracle(case['board'],case['oop_range'],case['ip_range'],case['config'])
        oracle_rows=oracle.get('counts',[]); expected_n=case['expected_compatible_pairs']
        if len(oracle_rows)!=expected_n or sum(r['ordered_outcomes'] for r in oracle_rows)!=expected_n*1980:
            raise AssertionError(f'Independent physical count census mismatch: {case["id"]}')
        if case['group']=='single-pair-image' and case['id']=='single-pair-image-00':
            anchor=spec['expected_single_pair_counts']; row=oracle_rows[0]
            if tuple(row[k] for k in ('wins','ties','losses','ordered_outcomes')) != tuple(anchor[k] for k in ('wins','ties','losses','ordered_outcomes')):
                raise AssertionError('Independent identity-image oracle disagrees with the fixed 6/60/1,914 count anchor')
        _,expected_priors,normalizer=pair_census(case['board'],case['oop_range'],case['ip_range'])
        if normalizer!=Fraction(case['expected_normalizer']): raise AssertionError('Frozen target prior normalizer mismatch')
        target=remap_flop_checkdown_equities_by_suit(source,case['board'],case['oop_range'],case['ip_range'])
        prov=flop_suit_remap_provenance(source,case['board'],case['oop_range'],case['ip_range'])
        target_count_rows=verify_target(target,oracle_rows,expected_priors)
        checked_prov=verify_provenance(prov,source,target)
        if pf.get('status')!='admitted' or pf.get('ranking_started') is not False: raise AssertionError('Missing admitted preflight')
        if case['group']=='mixed-two-pair':
            maps={tuple((s,row['suit_permutation'][s]) for s in SUITS) for row in checked_prov}
            identity=tuple((s,s) for s in SUITS); alternate=(('c','c'),('d','d'),('h','s'),('s','h'))
            if len(target.pairs)!=2 or identity not in maps or alternate not in maps:
                raise AssertionError('Mixed fixture did not exercise the identity and nonidentity suit transfers')
        expected_budget=pf['solver_budget']; repeats=[]
        for repeat in range(3):
            live.update({'phase':'timed-remap-provenance-solve-json','active_fixture':case['id'],'repeat':repeat+1,'repeat_total':3})
            atomic_json(LIVE_PATH,live)
            target,prov,result,payload,elapsed,guards=warm_call(source,case)
            if result.get('work_budget')!=expected_budget: raise AssertionError('Measured work budget differs from preflight')
            checked_prov=verify_provenance(prov,source,target)
            target_count_rows=verify_target(target,oracle_rows,expected_priors)
            quality=verify_result(result,oracle,spec,expected_budget)
            if not quality['target_met']:
                failures.append({'fixture_id':case['id'],'repeat':repeat+1,'nash_conv':quality['replay']['nash_conv'],'target_met':False})
            solver_payload=serialize(result)
            row={'repeat':repeat+1,'remap_provenance_solve_json_seconds':elapsed,
                 'complete_payload_sha256':hashlib.sha256(payload.encode()).hexdigest(),
                 'solver_payload_sha256':hashlib.sha256(solver_payload.encode()).hexdigest(),
                 'verification':quality,'ranking_guards':guards,'compatible_pairs':len(target.pairs),
                 'physical_ordered_worlds':target.budget['physical_worlds'],
                 'count_rows_match_independent_oracle':True,'exact_priors_match_independent_census':True,
                 'provenance_rows_full_deck_valid':len(checked_prov)==len(target.pairs),
                 'work_budget_matches_preflight':True}
            if case['group']=='whole-range-image':
                back=inverse_map_result(result,case['source_map'],spec['source_oop_range'],spec['source_ip_range'],spec['source_board'])
                backhash=hashlib.sha256(serialize(back).encode()).hexdigest()
                row['inverse_mapped_source_payload_sha256']=backhash
                row['matches_pinned_pr131_whole_stack24_payload']=backhash==HIST_POLICY
                if backhash!=HIST_POLICY: failures.append({'fixture_id':case['id'],'repeat':repeat+1,'whole_range_payload_match':False})
            repeats.append(row)
            print(f'{case["id"]} repeat={repeat+1}/3 sec={elapsed:.6f} gap={quality["replay"]["nash_conv"]:.12g}',flush=True)
        if len({r['complete_payload_sha256'] for r in repeats})!=1: raise AssertionError('Repeated remap payloads are nondeterministic')
        results.append({'fixture_id':case['id'],'fixture_group':case['group'],'board':case['board'],'config':case['config'],
          'compatible_pairs':len(target.pairs),'physical_ordered_worlds':target.budget['physical_worlds'],
          'preflight':pf,'repeats':repeats,'median_seconds':statistics.median(r['remap_provenance_solve_json_seconds'] for r in repeats),
          'target_pair_counts':[{'oop_hand':''.join(target.hands[0][i]),'ip_hand':''.join(target.hands[1][j]),'prior':str(prior),
              'wins':counts[0],'ties':counts[1],'losses':counts[2],'ordered_outcomes':1980}
              for (i,j,prior),counts in zip(target.pairs,target.counts)],
          'verified_provenance':checked_prov,
          'independent_oracle_pair_counts':[{k:r[k] for k in ('oop_hand','ip_hand','wins','ties','losses','ordered_outcomes')} for r in oracle_rows]})
        live['results']=results[:]; atomic_json(LIVE_PATH,live); del oracle,target,prov

    # Separate 4,000-iteration trace for the first whole 8x8 image; oracle was completed outside trace.
    alloc_case=cases[24]; live.update({'phase':'allocation-trace','active_fixture':alloc_case['id']}); atomic_json(LIVE_PATH,live)
    print(f'starting allocation trace {alloc_case["id"]}',flush=True); gc.collect(); tracemalloc.start()
    try:
        at,ap,ar,aj,asec,aguards=warm_call(source,alloc_case); _,peak=tracemalloc.get_traced_memory()
    finally: tracemalloc.stop()
    matching=results[24]['repeats'][0]
    if hashlib.sha256(aj.encode()).hexdigest()!=matching['complete_payload_sha256']:
        raise AssertionError('Allocation call does not match verified timed whole-range profile')
    allocation={'fixture_id':alloc_case['id'],'iterations':4000,'traced_peak_bytes':peak,
      'remap_provenance_solve_json_seconds_under_tracemalloc':asec,
      'complete_payload_sha256':hashlib.sha256(aj.encode()).hexdigest(),'matches_timed_verified_call':True,
      'ranking_guards':aguards,'includes':'Suit remap, provenance, prepared solve and wrapper JSON serialization.',
      'excludes':'Cached source table, cold preparation, independent oracle, process RSS.'}
    if source_hashes()!=before or revision()!=rev or status()!=clean_before: raise RuntimeError('Frozen sources/worktree changed during measurement')
    report={'schema_version':1,'benchmark_id':spec['benchmark_id'],'source_revision':rev,
      'generated_at_utc':datetime.now(timezone.utc).isoformat(),'specification_sha256':canonical_hash(spec),
      'source_hashes_lf_normalized':before,'worktree_clean_at_start_and_before_publication':True,
      'python':platform.python_version(),'platform':platform.platform(),'specification':spec,
      'cold_source_preparation_seconds':cold_seconds,
      'pinned_source_table':{'compatible_pairs':len(source.pairs),'ordered_worlds':source.budget['physical_worlds'],
        'unordered_boards':source.budget['unordered_boards'],'historical_commit':HIST_COMMIT,'historical_path':HIST_PATH,
        'historical_blob':HIST_BLOB,'historical_source_revision':HIST_REV,'all_58_counts_match_pinned_report':True},
      'preflights_complete_before_cold_preparation_or_ranking':True,'preflights':preflights,
      'results':results,'allocation':allocation,'quality_misses':failures,'acceptance_gate_met':not failures,
      'timing_scope':'Three complete 4,000-iteration calls per case; each timed call includes suit remap, provenance generation, prepared solve and JSON serialization of result plus provenance. Independent numeric-rule oracle and replay are outside timing.',
      'allocation_scope':'Separate Python tracemalloc call for first 8x8 image includes suit remap, provenance, solve and JSON; excludes source table/cold preparation, oracle and process RSS.',
      'accuracy_scope':'Independent ordered future board and best-five numeric-rule replay with own-hand information-set best responses. Whole eight-hand source-game images must inverse-map to the pinned PR131 result payload hash. Preserve misses; no fallback.'}
    report['artifact_sha256']=canonical_hash(report); atomic_json(OUTPUT_PATH,report)
    live.update({'phase':'complete','complete':True,'acceptance_gate_met':not failures,'report':OUTPUT_PATH.as_posix()}); atomic_json(LIVE_PATH,live)
    print(f'Saved {OUTPUT_PATH}; acceptance={not failures}',flush=True)
    if failures: raise AssertionError('Report saved with quality or full-range parity misses')
    return report

def run(spec=None):
    try: return _run_frozen(spec)
    except Exception as exc:
        try:
            state=json.loads(LIVE_PATH.read_text(encoding='utf-8-sig')) if LIVE_PATH.exists() else {}
            state.update({'phase':'failed','complete':True,'error_type':type(exc).__name__,'error':str(exc)})
            atomic_json(LIVE_PATH,state)
        except Exception: pass
        raise

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--preflight-only',action='store_true'); args=parser.parse_args()
    spec=json.loads(SPEC_PATH.read_text(encoding='utf-8-sig')); cases=validate_spec(spec)
    if args.preflight_only:
        print(json.dumps([preflight(c,4000,'cfrplus') for c in cases],indent=2,allow_nan=False)); return
    run(spec)
if __name__=='__main__': main()
