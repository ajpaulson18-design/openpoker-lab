"""Frozen paired prepared-call benchmark for opt-in preflop pair means.

No card ranking or board enumeration is performed. Physical chance counts are
pinned independent PR125 evidence, loaded through the existing audited helpers.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys

from pokerlab.preflop_checkdown_budget import admit_prepared, options
from pokerlab.preflop_full_board_equity import plan_preflop_equities
from scripts import benchmark_preflop_checkdown as baseline
from scripts.benchmark_native_preflop import _load_pinned_oracles, reference_table, checksum

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'preflop-pair-mean-v1'
SPEC = ROOT / 'benchmarks' / (PREFIX + '.json')
SPEC_SHA256 = '60f1f06de20022a7e673916b11c375d59767c7ed7d08757af6ef18ec60582ee9'
MODES = ('categorical', 'pair-mean')
METRICS = ('value_sb', 'value_bb', 'sb_best_response_value', 'bb_best_response_value',
           'sb_best_response_gain', 'bb_best_response_gain', 'nash_conv', 'exploitability')


def validate_spec(spec):
    if checksum(spec) != SPEC_SHA256:
        raise ValueError('Requires exact frozen preflop pair-mean specification')
    return spec


def source_hashes():
    hashes = baseline.source_hashes()
    raw = SPEC.read_bytes()
    hashes[SPEC.relative_to(ROOT).as_posix()] = {
        'raw_sha256': hashlib.sha256(raw).hexdigest(),
        'lf_sha256': hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()}
    return hashes


def prepare_cases(spec):
    plans = [(case, plan_preflop_equities(case['sb_range'], case['bb_range']))
             for case in spec['case_definitions']]
    for _, plan in plans:
        plan.validate()
    counts, provenance = _load_pinned_oracles(spec)
    prepared = []
    for case, plan in plans:
        table, rows, derivations = reference_table({'plan': plan}, counts)
        if len(table.pairs) != case['compatible_pairs']:
            raise AssertionError('Compatible-pair fixture changed')
        admissions = []
        for algorithm in spec['algorithms']:
            for iterations in spec['checkpoints']:
                cfg = options(case['config'], iterations, algorithm, 'prepared-counts')
                for mode in MODES:
                    budget = admit_prepared(table, cfg, iterations, algorithm,
                                            'prepared-counts', world_indexing=mode)
                    try:
                        historical = {'admitted': True, 'budget': admit_prepared(
                            table, cfg, iterations, algorithm, 'source-inclusive',
                            world_indexing=mode)}
                    except ValueError as exc:
                        historical = {'admitted': False, 'reason': str(exc)}
                    admissions.append({'algorithm': algorithm, 'iterations': iterations,
                                       'mode': mode, 'prepared_counts': budget,
                                       'source_inclusive_reference': historical})
        prepared.append({'case': case, 'table': table, 'counts': rows,
                         'derivations': derivations, 'admissions': admissions})
    return prepared, provenance


def compare_payloads(categorical, mean, spec):
    if set(mean) != set(categorical) | {'world_indexing'} or mean['world_indexing'] != 'pair-mean':
        raise ValueError('Unexpected opt-in payload shape')
    for field in ('config', 'algorithm', 'iterations', 'training_iterations_completed',
                  'tree', 'info_sets', 'compatible_pairs', 'physical_boards', 'pair_equities',
                  'solver_version', 'strategy_schema', 'runout_mode', 'scope'):
        if categorical[field] != mean[field]:
            raise ValueError('Pair-mean changed physical/game field: ' + field)
    if mean['training_world_rows'] != mean['compatible_pairs']:
        raise ValueError('Pair-mean must retain one row per private pair')
    scalar_gaps = {field: abs(categorical[field] - mean[field]) for field in METRICS}
    if len(categorical['strategy']) != len(mean['strategy']):
        raise ValueError('Strategy row count changed')
    policy_gaps = []
    for left, right in zip(categorical['strategy'], mean['strategy']):
        if {k: v for k, v in left.items() if k != 'actions'} != {k: v for k, v in right.items() if k != 'actions'}:
            raise ValueError('Private information or public history changed')
        if len(left['actions']) != len(right['actions']):
            raise ValueError('Action count changed')
        for a, b in zip(left['actions'], right['actions']):
            if {k: v for k, v in a.items() if k != 'probability'} != {k: v for k, v in b.items() if k != 'probability'}:
                raise ValueError('Legal action changed')
            policy_gaps.append(abs(a['probability'] - b['probability']))
    return {'scalar_absolute_gaps': scalar_gaps,
            'max_policy_probability_gap': max(policy_gaps, default=0.0),
            'meets_scalar_agreement_gate': max(scalar_gaps.values()) <= spec['acceptance']['cross_mode_scalar_absolute_tolerance']}


def measure(item, iterations, algorithm, mode, *, trace=False):
    # Use the existing complete-call timing boundary with an explicit local
    # mode argument; never mutate a global producer reference.
    import gc
    from time import perf_counter
    import tracemalloc
    from pokerlab.preflop_checkdown_solver import solve_prepared_preflop_checkdown
    gc.collect()
    if trace:
        tracemalloc.start()
    started = perf_counter()
    try:
        result = solve_prepared_preflop_checkdown(
            item['table'], config=item['case']['config'], iterations=iterations,
            algorithm=algorithm, resource_model='prepared-counts', world_indexing=mode)
        encoded = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
        seconds = perf_counter() - started
        peak = tracemalloc.get_traced_memory()[1] if trace else None
    finally:
        if trace:
            tracemalloc.stop()
    return result, {'seconds': seconds, 'python_peak_bytes': peak,
                    'serialized_bytes_utf8': len(encoded), 'payload_sha256': hashlib.sha256(encoded).hexdigest()}


def run(spec):
    validate_spec(spec)
    before, hashes = baseline.snapshot(), source_hashes()
    if before['status']:
        raise ValueError('Requires clean committed source before measurement')
    prepared, provenance = prepare_cases(spec)
    report = {'schema_version': 1, 'benchmark_id': PREFIX,
              'started_utc': datetime.now(timezone.utc).isoformat(),
              'specification': spec, 'spec_sha256': checksum(spec),
              'source': {'before': before, 'hashes': hashes},
              'environment': {'python': sys.version, 'executable': sys.executable,
                              'platform': platform.platform(), 'machine': platform.machine()},
              'physical_count_provenance': provenance, 'cases': [], 'errors': []}
    for item in prepared:
        case = item['case']
        output = {'id': case['id'], 'admissions': item['admissions'],
                  'count_derivations': item['derivations'], 'profiles': []}
        for algorithm in spec['algorithms']:
            for iterations in spec['checkpoints']:
                repeats = spec['final_repeats'] if iterations == spec['checkpoints'][-1] else 1
                profile = {'algorithm': algorithm, 'iterations': iterations,
                           'modes': {mode: {'samples': [], 'checks': [], 'payload': None} for mode in MODES},
                           'paired_comparisons': [], 'paired_sample_orders': []}
                for repeat in range(repeats):
                    order = MODES if repeat % 2 == 0 else tuple(reversed(MODES))
                    profile['paired_sample_orders'].append(list(order))
                    pair = {}
                    for mode in order:
                        print(f"START {case['id']} {algorithm} {iterations} repeat={repeat} mode={mode}", flush=True)
                        try:
                            result, timing = measure(item, iterations, algorithm, mode)
                            rows = profile['modes'][mode]
                            rows['samples'].append(timing)
                            if rows['payload'] is None:
                                rows['payload'] = result
                            pair[mode] = result
                            check = baseline.assess(result, item, spec)
                            rows['checks'].append(check)
                            print(f"DONE seconds={timing['seconds']:.6f} nash_conv={check['independent_replay']['nash_conv']:.10g}", flush=True)
                        except Exception as exc:
                            report['errors'].append({'case': case['id'], 'algorithm': algorithm,
                                'iterations': iterations, 'repeat': repeat, 'mode': mode,
                                'type': type(exc).__name__, 'message': str(exc)})
                    if set(pair) == set(MODES):
                        try:
                            profile['paired_comparisons'].append(compare_payloads(pair['categorical'], pair['pair-mean'], spec))
                        except Exception as exc:
                            report['errors'].append({'case': case['id'], 'algorithm': algorithm,
                                'iterations': iterations, 'repeat': repeat, 'phase': 'comparison',
                                'type': type(exc).__name__, 'message': str(exc)})
                for rows in profile['modes'].values():
                    rows['deterministic_payloads'] = len(rows['samples']) == repeats and len({x['payload_sha256'] for x in rows['samples']}) == 1
                    rows['median_seconds'] = statistics.median(x['seconds'] for x in rows['samples']) if rows['samples'] else None
                medians = [profile['modes'][mode]['median_seconds'] for mode in MODES]
                profile['observed_median_ratio_categorical_over_mean'] = medians[0] / medians[1] if all(medians) else None
                output['profiles'].append(profile)
        if case['id'] == spec['traced_case']:
            output['python_allocation_traces'] = {}
            for mode in MODES:
                print(f"START TRACE {case['id']} {mode}", flush=True)
                try:
                    result, timing = measure(item, spec['checkpoints'][-1], spec['traced_algorithm'], mode, trace=True)
                    target = next(x for x in output['profiles'] if x['iterations'] == spec['checkpoints'][-1] and x['algorithm'] == spec['traced_algorithm'])
                    output['python_allocation_traces'][mode] = {
                        **timing, 'check': baseline.assess(result, item, spec),
                        'matches_untraced_payload': timing['payload_sha256'] == target['modes'][mode]['samples'][0]['payload_sha256'],
                        'scope': spec['trace_scope']}
                    print(f"DONE TRACE seconds={timing['seconds']:.6f} bytes={timing['python_peak_bytes']}", flush=True)
                except Exception as exc:
                    report['errors'].append({'case': case['id'], 'mode': mode, 'phase': 'trace',
                                             'type': type(exc).__name__, 'message': str(exc)})
        report['cases'].append(output)
    after, after_hashes = baseline.snapshot(), source_hashes()
    report['source'].update(after=after, unchanged=before == after and hashes == after_hashes)
    final = [p for c in report['cases'] for p in c['profiles'] if p['iterations'] == spec['checkpoints'][-1]]
    report['all_final_gates_pass'] = (not report['errors'] and report['source']['unchanged']
        and len(final) == len(prepared) * len(spec['algorithms'])
        and all(all(len(rows['checks']) == spec['final_repeats'] and rows['deterministic_payloads']
                    and all(x['meets_final_quality_gate'] for x in rows['checks']) for rows in p['modes'].values())
                and len(p['paired_comparisons']) == spec['final_repeats']
                and all(x['meets_scalar_agreement_gate'] for x in p['paired_comparisons']) for p in final)
        and all(t['matches_untraced_payload'] for c in report['cases'] for t in c.get('python_allocation_traces', {}).values())
        and sum(len(c.get('python_allocation_traces', {})) for c in report['cases']) == 2
        and all(x['meets_scalar_agreement_gate'] for c in report['cases'] for p in c['profiles'] for x in p['paired_comparisons']))
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    report['artifact_sha256'] = checksum(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'benchmarks/results' / (PREFIX + '.json'))
    args = parser.parse_args()
    report = run(json.loads(SPEC.read_text(encoding='utf-8')))
    args.output.write_bytes((json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n').encode('utf-8'))
    print(json.dumps({'artifact_sha256': report['artifact_sha256'], 'all_final_gates_pass': report['all_final_gates_pass'], 'errors': report['errors']}), flush=True)
    return 0 if report['all_final_gates_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
