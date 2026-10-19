"""Independent suit-equivariance acceptance; no transport/trainer/LP/exact-helper imports."""
from pathlib import Path
from fractions import Fraction as F
from itertools import permutations
import copy,hashlib,json,math,subprocess
from scripts import turn_suit_reference as reference
from scripts import verify_turn_blocker_profiles_independent as archived_check
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'benchmarks/results/turn-suit-equivariance-v1.json'
SUITS='cdhs'
PERMUTATIONS=tuple(''.join(p) for p in permutations(SUITS))
TRAINING_TARGETS=('dcsh','hscd','shdc','cdhs')
BACKENDS=('materialized','matrix-free')
ARCHIVE_GRID=tuple((b,n) for b in BACKENDS for n in (1000,3000,10000))
TRAINING_GRID=tuple((t,b,1000) for t in TRAINING_TARGETS for b in BACKENDS)
METRICS=('value_oop','value_ip','oop_best_response_value','ip_best_response_value','oop_best_response_gain','ip_best_response_gain','nash_conv','exploitability')
PROFILE_REPORT='benchmarks/results/turn-blocker-cfrplus-profiles-v1.json'
PROFILE_DIR='benchmarks/results/turn-blocker-cfrplus-policies-v1'
POLICY_DIR='benchmarks/results/turn-suit-equivariance-policies-v1'
REFERENCE_SHA='8b70ad5460061cbbe479c135a33eec69f9a80ec66b3e9d19c24f6ee919635ced'
NEGATIVE_SHA='5781e203b988bf330b2ad9f8cc91320704fc96e0987616408a4c78ffd370f8f0'


def need(condition,message):
    if not condition:raise ValueError(message)


def canonical(value):
    return (json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode()


def sha(raw):return hashlib.sha256(raw).hexdigest()


def read(path,cap=2000000):
    path=Path(path);need(path.stat().st_size<=cap,'File admission exceeded')
    raw=path.read_bytes();need(len(raw)<=cap,'Input drift exceeded file admission');return raw


def normalized_rows(rows):
    result=[]
    for row in rows:
        raw=tuple(F.from_float(a['probability']) for a in row['actions'])
        total=sum(raw,F(0));need(total>0,'Empty probability row')
        result.append({k:copy.deepcopy(row[k]) for k in ('player','hand','street','board','history')}|{'actions':[{k:a[k] for k in ('name','amount','raise_to','history_key')}|{'probability_fraction':str(v/total)} for a,v in zip(row['actions'],raw)]})
    return sorted(result,key=lambda r:(0 if r['player']=='oop' else 1,r['hand'],tuple(r['history'])))


def mapped_result(result,target):
    # Independent direct character bijection; no candidate transport calls.
    table=str.maketrans(SUITS,target);out=copy.deepcopy(result)
    for key in ('board','runouts','reachable_runouts','selected_runouts'):
        if key in out:
            value=out[key]
            out[key]=value.translate(table) if type(value) is str else [c.translate(table) for c in value]
    out['strategy']=reference.policy_rows(result['strategy'],target)
    return out


def load_archives(observed):
    archived_check.reconstruct()
    raw=read(ROOT/PROFILE_REPORT)
    need(sha(raw)=='5c5d4b60108af53256e9f58f21494967887fd91c8ac2871150c48f454f733e76','Pinned archive report changed')
    observed.append((ROOT/PROFILE_REPORT,sha(raw),2000000));report=json.loads(raw)
    result={}
    for item in report['results']:
        key=item['backend'],item['iterations_requested']
        need(key in ARCHIVE_GRID and key not in result,'Archived grid identity')
        expected=PROFILE_DIR+'/turn-blocker-%s-%d.json'%key
        need(item['policy_file']==expected,'Archived policy path')
        payload=read(ROOT/expected,1000000)
        need(sha(payload)==item['policy_sha256'],'Archived policy digest')
        observed.append((ROOT/expected,sha(payload),1000000))
        result[key]=(item,json.loads(payload))
    need(len(result)==6,'All six source policies required')
    return result


def reconstruct_archives(archives,verify_math=True):
    records=[]
    prepared={t:reference.game(reference.fixture(t)) for t in PERMUTATIONS}
    for target in PERMUTATIONS:
        f=reference.fixture(target)
        for backend,count in ARCHIVE_GRID:
            item,source=archives[backend,count]
            transported=mapped_result(source,target)
            metrics=reference.replay(transported['strategy'],f,prepared[target]) if verify_math else item['exact']['metrics']
            need(metrics==item['exact']['metrics'],'Exact transported archive metrics changed')
            records.append(dict(target=target,backend=backend,iterations_requested=count,source_policy_file=item['policy_file'],source_policy_sha256=item['policy_sha256'],transported_policy_sha256=sha(canonical(transported)),exact_metrics_sha256=sha(canonical(metrics)),normalized_policy_rows_sha256=sha(canonical(normalized_rows(transported['strategy']))),exact_metrics_equal_source=True,worlds=6,information_sets=56))
    return records


def saved_form(value):
    if isinstance(value,F):return str(value)
    if type(value) is dict:
        if all(type(k) is str for k in value):return {k:saved_form(v) for k,v in value.items()}
        return {'key_value_entries':[dict(key=saved_form(k),value=saved_form(v)) for k,v in sorted(value.items(),key=lambda item:canonical(item[0]))]}
    if type(value) in (tuple,list):return [saved_form(v) for v in value]
    return value


def same_numeric(saved,fresh):
    if type(fresh) is float:return type(saved) is float and math.isfinite(saved) and math.isfinite(fresh) and abs(saved-fresh)<=1e-12
    if type(fresh) is dict:return type(saved) is dict and set(saved)==set(fresh) and all(same_numeric(saved[k],v) for k,v in fresh.items())
    if type(fresh) is list:return type(saved) is list and len(saved)==len(fresh) and all(same_numeric(a,b) for a,b in zip(saved,fresh))
    return type(saved) is type(fresh) and saved==fresh


def canonical_fraction(value):
    need(type(value) is str and len(value)<=8192,'Bounded canonical fraction required')
    result=F(value);need(str(result)==value,'Noncanonical fraction');return result


def check_certificate(result,cert,metrics):
    need(cert['metrics']==metrics,'Independent exact metrics differ')
    lower=-F(metrics['ip_best_response_value']);upper=F(metrics['oop_best_response_value'])
    need(canonical_fraction(cert['lower_value_bound'])==lower<=F(115,7)<=upper==canonical_fraction(cert['upper_value_bound']),'Known exact value excluded')
    need(cert['worlds']==6 and cert['tree_nodes']==63 and cert['tree_depth']==8,'Exact physical census')
    need(cert['work_limit']==100000 and cert['depth_limit']==64 and cert['fraction_bit_limit']==65536,'Exact caps changed')
    need(type(cert['work']) is int and 0<cert['work']<=100000 and all(type(v) is int and v>=0 for v in cert['work_by_kind'].values()) and sum(cert['work_by_kind'].values())==cert['work'],'Exact work accounting')
    need(type(cert['maximum_fraction_bits']) is int and 0<cert['maximum_fraction_bits']<=65536,'Exact fraction counter')
    normalized=normalized_rows(result['strategy'])
    need(cert['normalized_policy_rows']==normalized,'Normalized complete policy rows differ')
    originals={(0 if r['player']=='oop' else 1,r['hand'],tuple(r['history'])):r for r in result['strategy']}
    need(len(originals)==len(cert['normalization_ledger'])==56,'Complete normalization census')
    seen=set();max_adjustment=F(0)
    for item in cert['normalization_ledger']:
        need(item['player'] in ('oop','ip'),'Normalization player identity')
        key=(0 if item['player']=='oop' else 1,item['hand'],tuple(item['history']))
        need(key in originals and key not in seen,'Normalization duplicate/unknown row');seen.add(key)
        row=originals[key];raw=tuple(F.from_float(a['probability']) for a in row['actions']);total=sum(raw,F(0))
        need(canonical_fraction(item['input_row_sum_fraction'])==total,'Normalization row sum differs')
        need(len(item['actions'])==len(raw),'Normalization actions differ')
        for i,(saved,action,value) in enumerate(zip(item['actions'],row['actions'],raw)):
            after=value/total;delta=after-value;max_adjustment=max(max_adjustment,abs(delta))
            need((saved['index'],saved['name'],saved['history_key'])==(i,action['name'],action['history_key']),'Normalization action identity')
            need(canonical_fraction(saved['input_fraction'])==value and canonical_fraction(saved['normalized_fraction'])==after and canonical_fraction(saved['adjustment_fraction'])==delta,'Normalization arithmetic differs')
            need(type(saved['adjustment_float']) is float and saved['adjustment_float']==float(delta),'Normalization float adjustment')
    need(canonical_fraction(cert['max_row_adjustment'])==max_adjustment,'Maximum normalization adjustment')
    need(type(cert['threshold_met']) is bool and cert['threshold_met']==(F(metrics['nash_conv'])<=F(1,1000)),'Exact threshold label differs')
    return normalized


def fresh_expected(row,archives,observed):
    key=row['target'],row['backend'],row['iterations_requested']
    need(key in TRAINING_GRID and type(key[2]) is int,'Unexpected fresh grid case')
    target,backend,count=key
    f=reference.fixture(target)
    need(row['fixture']==f,'Transformed fixture differs')
    expected_path=POLICY_DIR+'/turn-suit-%s-%s-1000.json'%(target,backend)
    need(row['policy_file']==expected_path,'Fresh policy path differs')
    raw=read(ROOT/expected_path,1000000);need(sha(raw)==row['policy_sha256'],'Fresh complete policy hash')
    observed.append((ROOT/expected_path,sha(raw),1000000));result=json.loads(raw)
    need(canonical(result)==raw,'Fresh policy must be canonical LF JSON')
    execution='public-batched-python' if backend=='materialized' else 'matrix-free-ranked-python'
    need(result.get('execution_backend')==execution and result.get('diagnostics_backend')=='public-batched-python','Fresh backend provenance differs')
    need(type(result.get('iterations')) is int and result['iterations']==count and result.get('algorithm')=='cfrplus','Fresh training metadata differs')
    need(row['iterations_completed']==count and row['policy_bytes']==len(raw),'Fresh complete count/size metadata')
    for name,value in dict(worlds=6,information_sets=56,compatible_pairs=3,policy_rows=56,total_public_nodes=63,public_decision_nodes=28).items():need(row[name]==value,'Fresh physical census differs: '+name)
    metrics=reference.replay(result['strategy'],f)
    normalized=check_certificate(result,row['exact'],metrics)
    board=reference.base.rules.cards(f['board'])
    oracle=reference.base.rules.replay_policy(result,f['oop'],f['ip'],board=f['board'],config=f['config'],river_config=f['config'],runouts=f['runouts'])
    numeric_diff=reference.base.rules.compare_result(result,oracle,tolerance=1e-9)
    need(same_numeric(row['float_projection_oracle'],saved_form(oracle)),'Saved float oracle differs')
    need(same_numeric(row['serialized_vs_float_replay_differences'],numeric_diff),'Saved serialized replay differences')
    floats={k:float(F(v)) for k,v in metrics.items()}
    deltas={k:floats[k]-oracle[k] for k in METRICS}
    need(all(math.isfinite(v) and abs(v)<=1e-9 for v in deltas.values()),'Independent exact versus float gate')
    need(same_numeric(row['exact_normalized_float_projection'],floats) and same_numeric(row['exact_vs_float_replay_differences'],deltas),'Saved exact float projection differs')
    source,base_policy=archives[backend,1000]
    need(row['source_policy_file']==source['policy_file'] and row['source_policy_sha256']==source['policy_sha256'],'Fresh baseline policy identity differs')
    exact_differences={k:str(F(metrics[k])-F(source['exact']['metrics'][k])) for k in METRICS}
    need(row['exact_metric_differences_vs_source']==exact_differences,'Symmetry exact metric differences')
    symmetric=all(abs(F(v))<=F(1,1000000000) for v in exact_differences.values())
    need(row['symmetry_target_fraction']=='1/1000000000' and row['symmetry_met'] is symmetric and symmetric,'Fresh suit symmetry tolerance failed')
    target_met=F(metrics['nash_conv'])<=F(1,1000)
    need(row['target_met'] is target_met and row['threshold_miss'] is (not target_met),'Quality target/miss differs')
    need(row.get('known_game_value_fraction')=='115/7','Fresh exact anchor label')
    baseline=mapped_result(base_policy,target)
    lookup={(r['player'],r['hand'],tuple(r['history'])):r for r in normalized_rows(baseline['strategy'])}
    maximum_exact=F(0)
    for r in normalized:
        other=lookup[r['player'],r['hand'],tuple(r['history'])]
        need([a['history_key'] for a in r['actions']]==[a['history_key'] for a in other['actions']],'Fresh/source legal actions differ')
        maximum_exact=max(maximum_exact,*(abs(F(a['probability_fraction'])-F(b['probability_fraction'])) for a,b in zip(r['actions'],other['actions'])))
    maximum=float(maximum_exact)
    need(type(row['maximum_policy_probability_difference']) is float and math.isfinite(row['maximum_policy_probability_difference']) and abs(row['maximum_policy_probability_difference']-maximum)<=1e-12,'Per-action normalized policy difference metadata')
    need(row['policy_identity_sha256']==sha(canonical(result['strategy'])) and row['normalized_policy_rows_sha256']==sha(canonical(normalized)),'Complete/normalized strategy hashes differ')
    need(row['known_value_interval']==dict(lower=row['exact']['lower_value_bound'],upper=row['exact']['upper_value_bound'],known_value='115/7',contains_known_value=True),'Known-value interval metadata differs')
    for name in ('timing_solve_plus_json_seconds','timing_replay_seconds'):need(type(row[name]) in (int,float) and math.isfinite(row[name]) and row[name]>=0,'Single-call timing observation')
    return dict(target=target,backend=backend,nash_conv=float(F(metrics['nash_conv'])),symmetry_met=symmetric,target_met=target_met,maximum_policy_probability_difference=maximum)


REQUIRED_SOURCE_PATHS=tuple(sorted(set((
    *reference.base.REQUIRED_SOURCES,
    'scripts/turn_blocker_profiles.py','scripts/verify_turn_blocker_profiles_independent.py',
    'tests/test_turn_blocker_profiles.py','tests/test_turn_blocker_profiles_independent.py',
    'scripts/turn_suit_transport.py','scripts/turn_suit_reference.py','scripts/turn_suit_validation.py','scripts/verify_turn_suit_equivariance.py',
    'tests/test_turn_suit_transport.py','tests/test_turn_suit_reference.py','tests/test_turn_suit_validation.py','tests/test_verify_turn_suit_equivariance.py',
    'scripts/benchmark_turn_river_independent.py',
    'benchmarks/results/turn-blocker-sequence-equilibrium-v1.json',PROFILE_REPORT,
    'benchmarks/results/turn-suit-exact-reference-v1.json','benchmarks/results/turn-suit-negative-reference-v1.json',
    *(PROFILE_DIR+'/turn-blocker-%s-%d.json'%key for key in ARCHIVE_GRID),
))))
SCOPE="Global suit-isomorphism validation for one blocker-conditioned selected-river configured binary64-terminal turn game, including eight fixed CFR+ calls."
LIMITATIONS=[
    'Exact response bounds apply to row-normalized saved binary64 policies and configured binary64 terminal constants.',
    'The 24 archived transport checks reuse complete immutable source policies; they are not new training calls.',
    'Eight complete-call and replay observations make no general runtime, memory, RSS, or performance claim.',
    "Results apply only to this fixed selected-river turn fixture and do not establish unrestricted Hold'em equilibrium.",
]


def source_inputs():
    names=set(REQUIRED_SOURCE_PATHS)
    names.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'pokerlab').glob('*.py'))
    values={}
    for name in sorted(names):
        path=ROOT/name;raw=read(path,1000000 if '-policies-v1/' in name else 2000000)
        if path.suffix=='.py':raw=raw.replace(b'\r\n',b'\n')
        values[name]=sha(raw)
    return values


def verify_source_pins(saved,current):
    need(type(saved) is dict and set(REQUIRED_SOURCE_PATHS)<=set(saved),'Required source/input inventory differs')
    for name,digest in saved.items():
        need(type(name) is str and name and '\\' not in name and not Path(name).is_absolute() and not Path(name).drive and all(part not in ('','.','..') for part in name.split('/')),'Unsafe source inventory path')
        need(type(digest) is str and len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'Malformed source digest')
        if name in REQUIRED_SOURCE_PATHS:
            need(name in current and digest==current[name],'Required current proof source/input changed: '+name)


def negative_expected():
    path=ROOT/'benchmarks/results/turn-suit-negative-reference-v1.json';raw=read(path)
    need(sha(raw)==NEGATIVE_SHA,'Frozen negative reference changed')
    saved=json.loads(raw);f=copy.deepcopy(reference.FIXTURE);f['oop']='AcAh:0.25,Th6h:0.75'
    rules=reference.base.rules;board=rules.cards(f['board'])
    worlds,_=rules._worlds(board,tuple(rules.expand_range(f[p],board) for p in ('oop','ip')),f['runouts'])
    new=[w for w in worlds if ''.join(w['hands'][0])=='AcAh' and ''.join(w['hands'][1])=='AdAs']
    need(len(worlds)==8 and len({w['hands'] for w in worlds})==4 and len(new)==2 and sum((w['weight'] for w in new),F(0))==F(1,8) and all(w['sign']==0 for w in new),'One-sided physical negative control differs')
    return dict(kind=saved['kind'],candidate_training_run=False,oop_only_target='sdhc',worlds=8,compatible_pairs=4,newly_compatible_aa_pair_mass='1/8',new_pair_showdown_signs=[0,0],original_isomorphism_rejected=True,reference_sha256=NEGATIVE_SHA)


def exact_summaries():
    rebuilt=reference.reconstruct();raw=(json.dumps(rebuilt,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    need(sha(raw)==REFERENCE_SHA and read(reference.REFERENCE)==raw,'Frozen exact24 model/policy reference differs')
    witness=json.loads(read(reference.base.OUTPUT));rows=witness['results'][0]['rational_strategy']
    result=[]
    for case in rebuilt['results']:
        target=case['target'];inverse=str.maketrans(target,SUITS)
        g=reference.game(reference.fixture(target));moved=reference.policy_rows(rows,target)
        reach=reference.base.equilibrium_reach(dict(results=[dict(fixture=reference.fixture(target),rational_strategy=moved)]))
        need(reach['river_decision_reach']=='1','Exact transported policy river reach differs')
        result.append(dict(target=target,tree_identity_sha256=sha(canonical(reference.structure(g[2],inverse))),world_law_sha256=sha(canonical(reference.world_law(g[1],inverse))),rational_strategy_sha256=sha(canonical(moved)),exact_metrics_sha256=sha(canonical(case['metrics'])),known_value_interval=dict(lower='115/7',upper='115/7',contains_115_over_7=True),river_decision_reach=reach['river_decision_reach']))
    return result


def current_head():
    value=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    need(len(value)==40 and all(c in '0123456789abcdef' for c in value),'Invalid current Git head')
    return value


def verify_saved_artifact(path=OUTPUT):
    path=Path(path);own=Path(__file__).read_bytes();before=source_inputs();head=current_head()
    raw=read(path);report=json.loads(raw);observed=[(path,sha(raw),2000000)]
    need(type(report.get('schema_version')) is int and report['schema_version']==1 and report.get('certificate_id')=='turn-suit-equivariance-v1','Unsupported suit report schema')
    need(report.get('fixture')==reference.FIXTURE and report.get('permutations')==list(PERMUTATIONS) and report.get('training_targets')==list(TRAINING_TARGETS),'Fixed permutation experiment differs')
    need(report.get('grid')==[dict(target=t,backend=b,iterations=n) for t,b,n in TRAINING_GRID],'Fixed eight-call grid differs')
    need(report.get('known_game_value_fraction')=='115/7' and report.get('target_nash_conv_fraction')=='1/1000' and report.get('symmetry_target_fraction')=='1/1000000000','Known value/thresholds differ')
    need(report.get('scope')==SCOPE and report.get('limitations')==LIMITATIONS,'Report scope differs')
    baseline=report.get('baseline_git_commit');need(type(baseline) is str and len(baseline)==40 and all(c in '0123456789abcdef' for c in baseline),'Invalid generation Git head')
    need(type(report.get('python')) is str and report['python'] and type(report.get('platform')) is str and report['platform'],'Generation interpreter/platform observations missing')
    need(report.get('exact_reference_sha256')==REFERENCE_SHA and report.get('negative_reference_sha256')==NEGATIVE_SHA,'Frozen reference identities differ')
    verify_source_pins(report.get('source_sha256'),before)
    need(report.get('negative_control')==negative_expected(),'Negative control evidence differs')
    need(report.get('exact_reference_summary')==exact_summaries(),'Exact24 transport evidence differs')
    archives=load_archives(observed)
    # Reject changed stored transports before expensive response reconstruction;
    # every accepted report still executes all144 exact replays below.
    expected_archive=reconstruct_archives(archives,verify_math=False)
    need(report.get('archive_transports')==expected_archive,'Archived transport hashes/identities differ')
    fresh=report.get('fresh_results');need(type(fresh) is list and len(fresh)==8,'Eight full fresh policies required')
    seen=set()
    for row in fresh:
        key=row.get('target'),row.get('backend'),row.get('iterations_requested')
        need(key in TRAINING_GRID and key not in seen and type(key[2]) is int,'Repeated/unexpected fresh case');seen.add(key)
        fresh_expected(row,archives,observed)
    need(seen==set(TRAINING_GRID),'Fresh grid incomplete')
    need(reconstruct_archives(archives)==expected_archive,'Exact archived transport reconstruction differs')
    need(source_inputs()==before and Path(__file__).read_bytes()==own,'Current source/input drift during acceptance')
    need(all(sha(read(p,cap))==digest for p,digest,cap in observed),'Saved report/policy drift during acceptance')
    need(current_head()==head,'Git HEAD drift during acceptance')
    return report


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',type=Path,default=OUTPUT)
    args=parser.parse_args();report=verify_saved_artifact(args.input)
    print(json.dumps(dict(status='SUIT_EQUIVARIANCE_INDEPENDENTLY_VERIFIED',exact_transports=24,archive_transports=len(report['archive_transports']),fresh_policies=len(report['fresh_results']),quality_target_met=sum(r['target_met'] for r in report['fresh_results'])),sort_keys=True))

if __name__=='__main__':main()
