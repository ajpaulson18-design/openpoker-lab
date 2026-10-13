"""Frozen experiment for a preflop-owned target-delta traversal description."""
from contextlib import nullcontext
from datetime import datetime, timezone
import gc
import json
from pathlib import Path
import platform
import statistics
import time
import tracemalloc
from unittest.mock import patch

from pokerlab import public_cfr
from pokerlab.preflop_solver import solve_preflop
from scripts.benchmark_preflop_two_flops import futures, verify
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty
from scripts.preflop_target_plan_prototype import compile_target_plan

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'benchmarks/preflop-target-plan-prototype-v1.json'
OUTPUT = ROOT / 'benchmarks/results/preflop-target-plan-prototype-v1.json'
SOURCES = tuple(sorted(str(p.relative_to(ROOT)).replace('\\', '/')
                       for p in (ROOT / 'pokerlab').glob('*.py'))) + (
    'scripts/preflop_target_plan_prototype.py',
    'scripts/benchmark_preflop_target_plan_prototype.py',
    'scripts/benchmark_preflop_two_flops.py', 'scripts/benchmark_turn_solver.py',
    'scripts/preflop_validation.py', 'tests/test_preflop_target_plan_prototype.py',
    'tests/test_preflop_delayed_cfrplus.py', 'tests/test_preflop_vector_budget.py')


def solve(spec, kwargs, checkpoint, planned):
    plan = None
    identity = None
    metadata = None
    calls = 0

    def target(root, edges, infos, current, player, counts, half_pot, chance_type):
        nonlocal plan, identity, metadata, calls
        if plan is None:
            plan = compile_target_plan(root, edges, infos, counts, half_pot, chance_type)
            identity = (id(root), id(edges), id(infos), tuple(counts), half_pot, chance_type)
            metadata = dict(plan.metadata)
        assert identity == (id(root), id(edges), id(infos), tuple(counts), half_pot, chance_type)
        calls += 1
        return plan.target_deltas(current, player)

    context = patch.object(public_cfr, '_cfrplus_target_deltas', target) if planned else nullcontext()
    try:
        with context:
            result = solve_preflop(spec['sb'], spec['bb'], **kwargs,
                iterations=checkpoint['iterations'], averaging_delay=checkpoint['delay'],
                algorithm='cfrplus', traversal='public-batched', diagnostics='public-batched',
                resource_model='public-vector', tree_admission='vector')
        # Deliberately retain the prototype through exact diagnostics and JSON.
        # This conservative experiment lifetime is part of the memory scope.
        json.dumps(result)
        if planned:
            assert calls == 2 * checkpoint['iterations']
        return result, {'plan':metadata, 'target_delta_calls':calls if planned else None}
    finally:
        plan = None
        identity = None


def check(result, spec, kwargs):
    verified = verify(result, spec, kwargs)
    gap = verified['configured_replay']['nash_conv']
    return {'worlds':result['worlds'], 'information_sets':result['info_sets'],
            'target_nash_conv':spec['target_nash_conv'],
            'independent_target_met':gap + 1e-10 <= spec['target_nash_conv'],
            'existing_solver_budget_excludes_prototype_census_and_plan':result['vector_work_budget'],
            **verified}


def main():
    spec = json.loads(SPEC.read_text(encoding='utf-8'))
    hashes = {p:file_sha256(ROOT/p) for p in SOURCES}
    specification_hash = file_sha256(SPEC)
    revision, dirty = git_revision(None), worktree_dirty()
    if dirty:
        raise RuntimeError('Freeze source/spec in a clean commit before measuring.')
    kwargs = {'config':spec['config'], 'runouts':futures(spec['flops'])}
    pairs = []
    for index in range(spec['paired_timing']['pairs']):
        order = (False, True) if index % 2 == 0 else (True, False)
        rows, policies = {}, {}
        diagnostic_reference = None
        for planned in order:
            label = 'planned' if planned else 'reference'
            print(f'pair{index+1}: {label} start', flush=True)
            gc.collect()
            start = time.perf_counter()
            result, metadata = solve(spec, kwargs, spec['paired_timing'], planned)
            elapsed = time.perf_counter() - start
            rows[label] = {'complete_call_seconds':elapsed, **metadata, **check(result,spec,kwargs)}
            policies[label] = result['strategy']
            metrics = tuple(result[k] for k in ('value_sb','sb_best_response_value','bb_best_response_value','nash_conv'))
            if diagnostic_reference is None:
                diagnostic_reference = metrics
            else:
                assert metrics == diagnostic_reference
            print(f'  seconds={elapsed:.3f} gap={result["nash_conv"]:.12g}', flush=True)
        assert policies['planned'] == policies['reference']
        pairs.append({'pair':index+1, 'order':['planned' if p else 'reference' for p in order],
                      'policy_and_row_order_exactly_equal':True, 'diagnostics_exactly_equal':True,
                      'records':rows})
        del result, policies
    memory = {}
    memory_policy = None
    for planned in (False, True):
        label = 'planned' if planned else 'reference'
        print(f'separate complete-call allocation trace: {label} start', flush=True)
        gc.collect()
        tracemalloc.start()
        try:
            result, metadata = solve(spec, kwargs, spec['memory'], planned)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        memory[label] = {'complete_peak_traced_python_bytes':peak, **metadata, **check(result,spec,kwargs)}
        if memory_policy is None:
            memory_policy = result['strategy']
        else:
            assert memory_policy == result['strategy']
        print(f'  peak={peak}', flush=True)
        del result
    assert hashes == {p:file_sha256(ROOT/p) for p in SOURCES}
    assert specification_hash == file_sha256(SPEC)
    medians = {label:statistics.median(p['records'][label]['complete_call_seconds'] for p in pairs)
               for label in ('reference','planned')}
    reduction = 1 - medians['planned']/medians['reference']
    report = {'schema_version':1, 'benchmark_id':spec['benchmark_id'],
        'generated_at':datetime.now(timezone.utc).isoformat(), 'source_revision':revision,
        'worktree_dirty_at_start':dirty, 'source_hashes':hashes,
        'configuration_sha256':specification_hash, 'specification':spec,
        'python':platform.python_version(), 'platform':platform.platform(),
        'paired_timings':pairs, 'paired_timing_medians':medians,
        'observed_median_time_reduction':reduction, 'runtime_gate_met':reduction >= .05,
        'memory':memory, 'memory_policy_and_row_order_exactly_equal':True,
        'accuracy_scope':'Same fixed iterations/delay in both arms. Every final policy independently replayed from numeric rules and exact visible-information best responses. Exact policy, row-order and diagnostic parity required. Unchanged0.005 target misses retained; no accuracy improvement claimed.',
        'timing_scope':'Three alternating paired complete two-flop20/delay10 solves plus JSON, including prototype census/compilation and exact diagnostics. Preallocated runout arguments, pre-callGC and independent replay excluded. One shared host; no universal speed claim.',
        'memory_scope':'Separate complete two-flop10/delay5 solves plus JSON under tracemalloc. Prototype retained through final diagnostics and JSON; runout arguments preallocated. Independent replay, native allocations and RSS excluded; no high-iteration guarantee. Earlier reference policy retained during planned trace but allocated before tracing, so the trace reports new Python allocations rather than total live process memory.',
        'admission_scope':'Experimental helper has its own preallocation record/reference caps. Existing solver budget does not account for prototype census/compilation or retained plan storage. Production integration requires independent versioned workload/allocation admission; runtime gate alone is insufficient.',
        'provenance':'Independently implemented description/execution of this repository\'s own target-delta semantics. No third-party source/dependencies or shared postflop/turn/river changes. Luna implements prototype/parity tests; lead owns frozen complete-call measurement and adoption decision.',
        'model_limits':'Conditioned finite heads-up two-selected-flop game with complete ordered future deals and narrow ranges. No full-deck preflop, unrestricted NLHE, multiway, universal convergence or formal floating-point certificate.'}
    OUTPUT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(f'report saved; runtime gate={report["runtime_gate_met"]}; reduction={reduction:.3%}',flush=True)


if __name__ == '__main__':
    main()
