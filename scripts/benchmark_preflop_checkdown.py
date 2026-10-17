"""Opt-in frozen prepared-table full-board preflop betting benchmark.

This measures no physical enumeration. Pinned independent PR125 counts and
their recorded joint-suit derivation are reused through the previously audited
native benchmark's artifact-loading helpers, without invoking native code.
"""
import argparse
from datetime import datetime, timezone
import gc
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from time import perf_counter
import tracemalloc

from pokerlab.preflop_full_board_equity import plan_preflop_equities
from pokerlab.preflop_checkdown_budget import admit_prepared, options
from pokerlab.preflop_checkdown_solver import solve_prepared_preflop_checkdown
from scripts.preflop_checkdown_validation import replay
from scripts.benchmark_native_preflop import (
    _load_pinned_oracles, reference_table, checksum,
)

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'preflop-full-checkdown-v1'
SPEC = ROOT / 'benchmarks' / (PREFIX + '.json')
SPEC_SHA256 = '561a4da35fac7b288b38638c96461dbbb41281c646853cdddea9fd9e990c9a3b'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def snapshot():
    return {'revision': git('rev-parse', 'HEAD'),
            'status': git('status', '--porcelain', '--untracked-files=all').splitlines()}


def source_hashes():
    paths = set()
    for directory in ('pokerlab', 'scripts', 'tests'):
        paths.update((ROOT / directory).glob('*.py'))
    paths.update((ROOT / 'native').glob('*.c'))
    paths.update((ROOT / 'AGENTS.md', SPEC))
    return {p.relative_to(ROOT).as_posix(): {
        'raw_sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
        'lf_sha256': hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
    } for p in sorted(paths)}


def validate_spec(spec):
    if checksum(spec) != SPEC_SHA256:
        raise ValueError('Requires the exact frozen full-checkdown fixture')
    return spec


def prepare_cases(spec):
    # Range/candidate admission before reading historical physical evidence.
    planned = [(case, plan_preflop_equities(case['sb_range'], case['bb_range']))
               for case in spec['case_definitions']]
    for _, plan in planned:
        plan.validate()
    counts, provenance = _load_pinned_oracles(spec)
    prepared = []
    for case, plan in planned:
        table, rows, derivations = reference_table({'plan': plan}, counts)
        if len(table.pairs) != case['compatible_pairs']:
            raise AssertionError('Fixture pair census changed')
        admissions = []
        for iterations in spec['checkpoints']:
            cfg = options(case['config'], iterations, spec['algorithm'], 'prepared-counts')
            budget = admit_prepared(table, cfg, iterations, spec['algorithm'], 'prepared-counts')
            try:
                historical = {'admitted': True, 'budget': admit_prepared(
                    table, cfg, iterations, spec['algorithm'], 'source-inclusive')}
            except ValueError as exc:
                historical = {'admitted': False, 'reason': str(exc)}
            admissions.append({'iterations': iterations, 'prepared_counts': budget,
                               'source_inclusive_reference': historical})
        prepared.append({'case': case, 'table': table, 'counts': rows,
                         'derivations': derivations, 'admissions': admissions})
    # Every complete requested solve admitted before any public tree/training.
    return prepared, provenance


def measure(prepared, iterations, algorithm, *, trace=False):
    gc.collect()
    if trace:
        tracemalloc.start()
    started = perf_counter()
    try:
        result = solve_prepared_preflop_checkdown(
            prepared['table'], config=prepared['case']['config'], iterations=iterations,
            algorithm=algorithm, resource_model='prepared-counts')
        encoded = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False)
        seconds = perf_counter() - started
        peak = tracemalloc.get_traced_memory()[1] if trace else None
    finally:
        if trace:
            tracemalloc.stop()
    return result, {'seconds': seconds, 'python_peak_bytes': peak,
                    'serialized_bytes_utf8': len(encoded.encode('utf-8')),
                    'payload_sha256': hashlib.sha256(encoded.encode('utf-8')).hexdigest()}


def assess(result, prepared, spec):
    case = prepared['case']
    independent = replay(result, case['sb_range'], case['bb_range'], case['config'],
                         prepared['counts'], tolerance=spec['acceptance']['metric_absolute_tolerance'])
    # Opponent best responses give a valid finite-game equilibrium bracket.
    bracket = [-independent['bb_best_response_value'], independent['sb_best_response_value']]
    padding = spec['acceptance']['gate_padding']
    quality_pass = independent['nash_conv'] + padding <= spec['acceptance']['final_nash_conv_chip_limit']
    known = case.get('known_value_sb')
    error = None if known is None else abs(independent['value_sb'] - known)
    if error is not None:
        quality_pass = quality_pass and error + padding <= spec['acceptance']['final_known_value_error_chip_limit']
    return {'independent_replay': independent, 'equilibrium_value_bracket_sb': bracket,
            'known_value_error': error, 'meets_final_quality_gate': quality_pass}


def run(spec):
    validate_spec(spec)
    before, hashes = snapshot(), source_hashes()
    if before['status']:
        raise ValueError('Benchmark requires a clean committed checkout')
    prepared, provenance = prepare_cases(spec)
    report = {'schema_version': 1, 'benchmark_id': PREFIX,
              'started_utc': datetime.now(timezone.utc).isoformat(),
              'spec_sha256': checksum(spec), 'specification': spec,
              'source': {'before': before, 'hashes': hashes},
              'environment': {'python': sys.version, 'executable': sys.executable,
                              'platform': platform.platform(), 'machine': platform.machine()},
              'physical_count_provenance': provenance, 'cases': [], 'errors': []}
    for item in prepared:
        case = item['case']
        output = {'id': case['id'], 'admissions': item['admissions'],
                  'count_derivations': item['derivations'], 'checkpoints': []}
        for iterations in spec['checkpoints']:
            samples, checks, payloads = [], [], []
            repeats = spec['final_repeats'] if iterations == spec['checkpoints'][-1] else 1
            for repeat in range(repeats):
                print(f"START {case['id']} {iterations} repeat={repeat}", flush=True)
                try:
                    result, timing = measure(item, iterations, spec['algorithm'])
                    # Keep raw timing and payload even when independent replay
                    # fails; a correctness miss must not erase its observation.
                    samples.append(timing); payloads.append(result)
                    check = assess(result, item, spec)
                    checks.append(check)
                    print(f"DONE {case['id']} {iterations} seconds={timing['seconds']:.6f} "
                          f"nash_conv={check['independent_replay']['nash_conv']:.10g}", flush=True)
                except Exception as exc:
                    report['errors'].append({'case': case['id'], 'iterations': iterations,
                                             'repeat': repeat, 'type': type(exc).__name__, 'message': str(exc)})
            checkpoint = {'iterations': iterations, 'samples': samples, 'checks': checks,
                          'median_seconds': statistics.median(s['seconds'] for s in samples) if samples else None,
                          'deterministic_payloads': len(samples) == repeats and len({s['payload_sha256'] for s in samples}) == 1,
                          'payload': payloads[0] if payloads else None}
            output['checkpoints'].append(checkpoint)
        if case['id'] == spec['traced_case']:
            print(f"START TRACE {case['id']}", flush=True)
            try:
                result, timing = measure(item, spec['checkpoints'][-1], spec['algorithm'], trace=True)
                output['python_allocation_trace'] = {
                    **timing, 'check': assess(result, item, spec),
                    'matches_untraced_payload': timing['payload_sha256'] == output['checkpoints'][-1]['samples'][0]['payload_sha256'],
                    'scope': spec['trace_scope']}
                print(f"DONE TRACE seconds={timing['seconds']:.6f} bytes={timing['python_peak_bytes']}", flush=True)
            except Exception as exc:
                report['errors'].append({'case': case['id'], 'phase': 'trace',
                                         'type': type(exc).__name__, 'message': str(exc)})
        report['cases'].append(output)
    after, after_hashes = snapshot(), source_hashes()
    report['source']['after'] = after
    report['source']['unchanged'] = before == after and hashes == after_hashes
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    report['all_final_gates_pass'] = (not report['errors'] and report['source']['unchanged']
        and all(len(case['checkpoints'][-1]['samples']) == spec['final_repeats']
                and case['checkpoints'][-1]['deterministic_payloads']
                and all(check['meets_final_quality_gate'] for check in case['checkpoints'][-1]['checks'])
                for case in report['cases'])
        and all(case.get('python_allocation_trace', {}).get('matches_untraced_payload', True)
                for case in report['cases']))
    report['artifact_sha256'] = checksum(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'benchmarks/results' / (PREFIX + '.json'))
    args = parser.parse_args()
    report = run(json.loads(SPEC.read_text(encoding='utf-8')))
    args.output.write_bytes((json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n').encode('utf-8'))
    print(json.dumps({'artifact_sha256': report['artifact_sha256'],
                      'all_final_gates_pass': report['all_final_gates_pass'],
                      'errors': report['errors']}), flush=True)
    return 0 if report['all_final_gates_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
