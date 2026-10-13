"""Frozen direct-flop full-future accuracy and complete-call measurements."""
import gc, hashlib, json, platform, statistics, subprocess, time, tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from pokerlab.flop_checkdown_solver import solve_flop_checkdown
from scripts.flop_checkdown_validation import prepare_oracle, replay
from scripts.benchmark_preflop_weighted_range_coverage import git_revision, worktree_dirty

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/'benchmarks/direct-flop-checkdown-v1.json'
OUTPUT=ROOT/'benchmarks/results/direct-flop-checkdown-v1.json'


def paths():
    return tuple(sorted(p.relative_to(ROOT).as_posix() for p in (ROOT/'pokerlab').glob('*.py'))) + (
        'AGENTS.md','scripts/preflop_validation.py','scripts/flop_checkdown_validation.py',
        'scripts/benchmark_direct_flop_checkdown.py','scripts/benchmark_preflop_weighted_range_coverage.py',
        'tests/test_flop_checkdown_worlds.py','tests/test_flop_checkdown_solver.py',
        'benchmarks/direct-flop-checkdown-v1.json')


def hashes():
    return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths()}


def measured(fixture, iterations, spec, oracle, trace=False):
    gc.collect()
    if trace: tracemalloc.start()
    started=time.perf_counter()
    try:
        result=solve_flop_checkdown(fixture['board'],fixture['oop_range'],fixture['ip_range'],
            config=fixture['config'],iterations=iterations,algorithm=spec['algorithm'])
        payload=json.dumps(result,allow_nan=False,separators=(',',':'))
    finally:
        elapsed=time.perf_counter()-started
        peak=None
        if trace:
            _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    checked=replay(result,oracle,spec['scalar_tolerance'])
    target_met=checked['nash_conv']+spec['target_padding']<=fixture['target_nash_conv']
    row={'iterations':iterations,'complete_call_plus_json_seconds':elapsed,
         'payload_sha256':hashlib.sha256(payload.encode()).hexdigest(),
         'verification':checked,'target_met':target_met,
         'work_budget':result['work_budget'],
         'game':{k:result[k] for k in ('compatible_pairs','physical_worlds','training_world_rows',
              'info_sets','public_nodes','public_states','terminal_nodes')},
         'pair_equities':result['pair_equities']}
    if 'known_oop_value' in fixture:
        row['known_value_absolute_error']=abs(checked['value_oop']-fixture['known_oop_value'])
        row['known_value_target_met']=row['known_value_absolute_error']+spec['target_padding']<=fixture['known_value_tolerance']
    if trace:row['traced_peak_bytes']=peak
    print(f"{fixture['id']} T={iterations} trace={trace} seconds={elapsed:.6f} gap={checked['nash_conv']:.12g} target={target_met}",flush=True)
    return row


def main():
    spec=json.loads(SPEC.read_text(encoding='utf-8-sig'))
    revision=git_revision(None)
    if worktree_dirty() is not False:
        raise RuntimeError('Freeze clean source/specification before measurement')
    if subprocess.run(['git','merge-base','--is-ancestor',spec['baseline_main'],revision],cwd=ROOT,check=False).returncode:
        raise ValueError('Baseline is not an ancestor')
    before=hashes();results=[];failures=[]
    progress=ROOT.parent/'direct-flop-checkdown-live.json'
    for fixture in spec['fixtures']:
        oracle=prepare_oracle(fixture['board'],fixture['oop_range'],fixture['ip_range'],fixture['config'])
        runs=[]
        for iterations in spec['checkpoints']:
            arms=[measured(fixture,iterations,spec,oracle) for _ in range(spec['timed_repeats'])]
            if len({a['payload_sha256'] for a in arms})!=1:
                failures.append(f"{fixture['id']} T={iterations} deterministic payload differs")
            runs.append({'iterations':iterations,'arms':arms,
                         'median_complete_call_plus_json_seconds':statistics.median(a['complete_call_plus_json_seconds'] for a in arms)})
            progress.write_text(json.dumps({'source_revision':revision,'fixture':fixture['id'],'completed_checkpoints':runs,'complete':False},indent=2,allow_nan=False)+'\n',encoding='utf-8')
        allocation=measured(fixture,spec['allocation_iterations'],spec,oracle,trace=True)
        if 'known_oop_value' in fixture and not all(a['known_value_target_met'] for a in runs[-1]['arms']):
            failures.append(f"{fixture['id']} final known-value target missed")
        if not all(a['target_met'] for a in runs[-1]['arms']):
            failures.append(f"{fixture['id']} final accuracy target missed")
        if runs[-1]['arms'][0]['verification']['nash_conv']>=runs[0]['arms'][0]['verification']['nash_conv']:
            failures.append(f"{fixture['id']} final gap did not improve")
        results.append({'fixture_id':fixture['id'],'checkpoints':runs,'allocation':allocation,
                        'oracle_pair_counts':oracle['counts']})
        del oracle
    if hashes()!=before or git_revision(None)!=revision or worktree_dirty() is not False:
        raise RuntimeError('Frozen source changed during measurement')
    report={'schema_version':1,'benchmark_id':spec['benchmark_id'],'source_revision':revision,
            'generated_at_utc':datetime.now(timezone.utc).isoformat(),'source_hashes':before,
            'worktree_dirty_at_start':False,'specification':spec,'python':platform.python_version(),
            'platform':platform.platform(),'results':results,'failures':failures,'acceptance_gate_met':not failures,
            'timing_scope':'Three separate complete solves plus raw JSON per checkpoint; all construction, ranking, requested training and exact diagnostics included. Inputs/GC before timing; independent oracle/replay after timing. No comparative speedup claim.',
            'allocation_scope':'Separate10-iteration complete calls plus raw JSON under tracemalloc; input preparation and GC precede tracing, independent replay follows it. Python traced allocations, not RSS or high-iteration memory.',
            'quality_scope':'Per-fixture ordered-future/best-five counts prepared independently once and reused as immutable chance evidence. Every profile is independently replayed through numeric betting rules and both legal visible-information best responses; no production policies cached between calls.'}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(f'Saved {OUTPUT}; acceptance={not failures}',flush=True)
    if failures:raise AssertionError('Report saved; '+'; '.join(failures))


if __name__=='__main__':
    main()
