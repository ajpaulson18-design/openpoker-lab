"""Frozen independent weighted full-deck flop-to-river validation experiment."""
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
from fractions import Fraction
import argparse
import gc
import gzip
import hashlib
from itertools import permutations
import json
import os
from math import isfinite
from pathlib import Path
import platform
import statistics
import subprocess
from time import perf_counter
import tracemalloc
import traceback
from unittest.mock import patch

from pokerlab import postflop_solver as production
from pokerlab.river_config import RiverConfig
from scripts import benchmark_native_flop_preparation as identity
from scripts.benchmark_preflop_covered_counts import canonical, checksum

ROOT = identity.ROOT
SPEC = ROOT / 'benchmarks/weighted-full-deck-flop-v1.json'
SPEC_SHA = 'b72039785e46ba7a30850831ce0e420d1775a2b34ed7dbcbeaf8080cec88ca05'
MAX_RAW_BYTES = 64 * 1024 * 1024
MAX_GZIP_BYTES = 8 * 1024 * 1024



@contextmanager
def measurement_execution_state():
    """Keep this Windows benchmark thread active, restoring its prior state."""
    if os.name != 'nt':
        yield {'mode':'ordinary-process','system_required':False}
        return
    import ctypes
    setter = ctypes.windll.kernel32.SetThreadExecutionState
    setter.argtypes = [ctypes.c_uint32]
    setter.restype = ctypes.c_uint32
    previous = setter(0x80000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    if not previous:
        raise RuntimeError('Unable to reserve active execution before the benchmark')
    try:
        yield {'mode':'windows-benchmark-thread','system_required':True,
               'previous_flags':int(previous),'requested_flags':0x80000001}
    finally:
        setter(previous)


def load_spec():
    spec = json.loads(SPEC.read_bytes())
    if checksum(spec) != SPEC_SHA:
        raise ValueError('Requires the frozen weighted full-deck flop specification')
    return spec


def snapshot():
    state = identity.snapshot()
    raw = SPEC.read_bytes()
    state['source_hashes'][SPEC.relative_to(ROOT).as_posix()] = {
        'raw_sha256': hashlib.sha256(raw).hexdigest(),
        'lf_sha256': hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()}
    return state


def geometry(spec):
    """Only structural coordinates: deliberately no ranking or producer parsing."""
    board = tuple(spec['board'][i:i+2] for i in range(0, 6, 2))
    hands = []
    for seat in ('literal_oop_hands', 'literal_ip_hands'):
        hands.append(sorted(tuple(sorted((name[:2], name[2:]))) for name, _ in spec[seat]))
    worlds = []
    for i, a in enumerate(hands[0]):
        for j, b in enumerate(hands[1]):
            if set(a).intersection(b):
                continue
            dead = set(board + a + b)
            deck = [r+s for r in '23456789TJQKA' for s in 'cdhs' if r+s not in dead]
            worlds.extend((i, j, 1.0, 0, turn, river) for turn, river in permutations(deck, 2))
    return board, hands, worlds


def preflight(spec):
    board, hands, worlds = geometry(spec)
    config = RiverConfig.from_dict(spec['config'])
    counts = {}
    root, nodes, chance, visits, operations = production._build_postflop_tree(
        board, config, worlds=worlds, allocation_counts=counts)
    forecast = {'candidate_pairs': len(hands[0])*len(hands[1]),
                'compatible_pairs': len({w[:2] for w in worlds}), 'worlds': len(worlds),
                'public_nodes': len(nodes), 'public_states': counts['total'],
                'chance_nodes': chance, 'terminal_nodes': counts['terminal'],
                'world_traversal_nodes': visits, 'plan_operations': len(worlds)*operations,
                'max_world_iterations': len(worlds)*max(spec['iterations']),
                'max_world_node_iterations': len(worlds)*visits*max(spec['iterations'])}
    for key, expected in spec['expected'].items():
        if key not in ('pair_priors', 'raw_joint_weight_normalizer') and forecast[key] != expected:
            raise ValueError('Frozen rank-free census changed: '+key)
    if (forecast['candidate_pairs']*max(spec['iterations']) > production._MAX_CANDIDATE_HAND_ITERATIONS
            or forecast['max_world_iterations'] > production._MAX_WORLD_ITERATIONS
            or forecast['max_world_node_iterations'] > production._MAX_WORLD_NODE_WORK
            or forecast['plan_operations'] > production.MAX_PLAN_OPS):
        raise ValueError('Complete requested experiment exceeds an unchanged solver cap')
    return forecast


@contextmanager
def independent_guard():
    """Disable producer grammar, worlds, rules, ranking, kernels and diagnostics."""
    from pokerlab import cards, cfr, cfr_plus, planned_cfr, public_cfr, public_diagnostics, river_tree
    from scripts import preflop_validation as best_five_reference
    targets = [(cards, n) for n in ('cards', 'expand_range', 'rank_hand')]
    targets += [(production, n) for n in ('cards', 'expand_range', 'rank_hand', '_enumerate_worlds',
                '_build_tree', '_build_postflop_tree', '_build_public_tree', '_terminal_value',
                'train', 'train_plus', 'train_planned', 'train_public_batched',
                'evaluate', 'best_response', 'evaluate_profile')]
    targets += [(cfr, n) for n in ('train', 'evaluate', 'best_response')]
    targets += [(cfr_plus, 'train'), (planned_cfr, 'train'), (public_cfr, 'train_public_batched'),
                (public_diagnostics, 'evaluate_profile'), (river_tree, '_build_tree'),
                (river_tree, '_terminal_value')]
    targets += [(best_five_reference, 'cards'), (best_five_reference, 'expand_range'),
                (RiverConfig, 'from_dict'), (RiverConfig, '__post_init__')]
    calls = {owner.__name__+'.'+name: 0 for owner, name in targets}
    def forbidden(key):
        def fail(*args, **kwargs):
            calls[key] += 1
            raise AssertionError('Independent oracle called production helper: '+key)
        return fail
    with ExitStack() as stack:
        for owner, name in targets:
            stack.enter_context(patch.object(owner, name, forbidden(owner.__name__+'.'+name)))
        yield calls


def prepare_reference(spec):
    from scripts.flop_multistreet_validation import prepare_oracle
    with independent_guard() as calls:
        oracle = prepare_oracle(spec['board'], spec['literal_oop_hands'],
                                spec['literal_ip_hands'], spec['config'])
    if any(calls.values()):
        raise ValueError('Independent preparation used production helpers')
    priors = [[row['oop_hand'], row['ip_hand'], row['pair_probability_fraction']]
              for row in oracle['counts']]
    if (priors != spec['expected']['pair_priors']
            or oracle['normalizer'] != Fraction(spec['expected']['raw_joint_weight_normalizer'])
            or any(row['ordered_outcomes'] != 1980 for row in oracle['counts'])):
        raise ValueError('Independent exact priors/normalizer/physical count census changed')
    return oracle, calls


def _world_projection(worlds):
    return [[a, b, str(mass), sign, list(board)] for a, b, mass, sign, board in worlds]


def compare_physical_worlds(spec, oracle):
    """Compare each producer sign/prior to independent ordered physical deals."""
    hands, worlds, selected, pairs = production._enumerate_worlds(
        spec['board'], spec['oop_range'], spec['ip_range'], iterations=max(spec['iterations']))
    board = tuple(spec['board'][i:i+2] for i in range(0, 6, 2))
    rows = [(''.join(hands[0][i]), ''.join(hands[1][j]), mass, sign, board+tuple(future))
            for i, j, mass, sign, *future in worlds]
    expected = {(a, b, tuple(final)): (mass, sign) for a, b, mass, sign, final in oracle['worlds']}
    if len(rows) != len(expected) or len(rows) != spec['expected']['worlds'] or pairs != spec['expected']['compatible_pairs']:
        raise ValueError('Producer physical support census changed')
    seen = set(); gap = 0.0
    for a, b, mass, sign, final in rows:
        key = a, b, final
        if key in seen or key not in expected:
            raise ValueError('Duplicate/missing physical world identity')
        seen.add(key); wanted_mass, wanted_sign = expected[key]
        gap = max(gap, abs(mass-float(wanted_mass)))
        if sign != wanted_sign or abs(mass-float(wanted_mass)) > 1e-15:
            raise ValueError('Physical showdown sign or globally normalized prior changed')
    return {'pairs': pairs, 'worlds': len(rows), 'maximum_mass_absolute_gap': gap,
            'production_rows': [[a, b, mass, sign, list(final)] for a, b, mass, sign, final in rows]}


def store_payload(directory, filename, payload):
    raw = canonical(payload)
    if len(raw) > MAX_RAW_BYTES:
        raise ValueError('Raw policy exceeds bounded artifact capacity')
    compressed = gzip.compress(raw, mtime=0)
    if len(compressed) > MAX_GZIP_BYTES:
        raise ValueError('Compressed policy exceeds bounded artifact capacity')
    with (directory / filename).open('xb') as output:
        output.write(compressed)
    return {'file': filename, 'raw_bytes': len(raw), 'gzip_bytes': len(compressed),
            'payload_sha256': hashlib.sha256(raw).hexdigest(),
            'gzip_sha256': hashlib.sha256(compressed).hexdigest()}


def read_payload(directory, row):
    name = row['file']
    if type(name) is not str or Path(name).name != name or not name.endswith('.json.gz') or '/' in name or '\\' in name:
        raise ValueError('Saved policy must use a local evidence filename')
    path = directory / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_GZIP_BYTES:
        raise ValueError('Invalid compressed evidence file')
    compressed = path.read_bytes()
    if len(compressed) != row['gzip_bytes'] or hashlib.sha256(compressed).hexdigest() != row['gzip_sha256']:
        raise ValueError('Compressed evidence checksum changed')
    with gzip.open(path, 'rb') as source:
        raw = source.read(MAX_RAW_BYTES+1)
    if len(raw) > MAX_RAW_BYTES or len(raw) != row['raw_bytes'] or hashlib.sha256(raw).hexdigest() != row['payload_sha256']:
        raise ValueError('Lossless raw policy checksum changed')
    payload = json.loads(raw)
    if canonical(payload) != raw:
        raise ValueError('Saved policy must retain canonical raw bytes')
    return payload


def assess(payload, oracle, spec):
    from scripts.flop_multistreet_validation import replay
    for key in ('compatible_pairs', 'worlds', 'public_nodes', 'public_states',
                'chance_nodes', 'terminal_nodes', 'world_traversal_nodes'):
        if payload[key] != spec['expected'][key]:
            raise ValueError('Returned full-deck census changed: '+key)
    with independent_guard() as calls:
        checked = replay(payload, oracle, tolerance=spec['acceptance']['independent_metric_absolute_tolerance'])
    if any(calls.values()):
        raise ValueError('Policy replay used production helpers')
    return checked, calls


def call(spec, algorithm, traversal, iterations):
    return production.solve_postflop(spec['board'], spec['oop_range'], spec['ip_range'],
            config=spec['config'], iterations=iterations, algorithm=algorithm, traversal=traversal)


def timed_call(spec, directory, oracle, algorithm, traversal, iterations, repeat):
    gc.collect()
    started_at = datetime.now(timezone.utc).isoformat()
    started = perf_counter()
    payload = call(spec, algorithm, traversal, iterations)
    raw = canonical(payload); digest = hashlib.sha256(raw).hexdigest()
    elapsed = perf_counter()-started
    row = {'kind': 'timed', 'algorithm': algorithm, 'traversal': traversal,
           'iterations': iterations, 'repeat': repeat, 'elapsed_seconds': elapsed,
           'started_at_utc': started_at, 'finished_at_utc': datetime.now(timezone.utc).isoformat()}
    row.update(store_payload(directory, f'{algorithm}-{iterations}-{traversal}-{repeat}.json.gz', payload))
    if row['payload_sha256'] != digest:
        raise ValueError('Timed serialization changed outside timing')
    try:
        checked, calls = assess(payload, oracle, spec)
        row['independent_replay'], row['forbidden_production_calls'] = checked, calls
    except Exception as exc:
        row['replay_error'] = f'{type(exc).__name__}: {exc}'
    return row


def allocation_call(spec, directory, oracle, traversal):
    options = spec['separate_allocation_calls']
    gc.collect()
    started_at = datetime.now(timezone.utc).isoformat()
    tracemalloc.start()
    try:
        payload = call(spec, options['algorithm'], traversal, options['iterations'])
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    row = {'kind': 'allocation', 'algorithm': options['algorithm'], 'traversal': traversal,
           'iterations': options['iterations'], 'python_traced_peak_bytes': peak,
           'started_at_utc': started_at, 'finished_at_utc': datetime.now(timezone.utc).isoformat()}
    row.update(store_payload(directory, f'allocation-{traversal}.json.gz', payload))
    try:
        checked, calls = assess(payload, oracle, spec)
        row['independent_replay'], row['forbidden_production_calls'] = checked, calls
    except Exception as exc:
        row['replay_error'] = f'{type(exc).__name__}: {exc}'
    return row


def _cross_compare(left, right, spec):
    metric_fields = ('value_oop', 'value_ip', 'oop_best_response_value', 'ip_best_response_value',
                     'oop_best_response_gain', 'ip_best_response_gain', 'nash_conv', 'exploitability')
    metric_gap = max(abs(left[k]-right[k]) for k in metric_fields)
    # Backend metadata is intentionally different. All structural policy facts
    # and every action's numeric rule fields must still match exactly.
    ignored = set(metric_fields) | {'strategy', 'execution_backend', 'plan_operation_limit'}
    if {k: v for k, v in left.items() if k not in ignored} != {k: v for k, v in right.items() if k not in ignored}:
        raise ValueError('Recursive/planned structural result fields differ')
    if len(left['strategy']) != len(right['strategy']):
        raise ValueError('Recursive/planned information-set coverage differs')
    policy_gap = 0.0
    for a, b in zip(left['strategy'], right['strategy']):
        if {k: v for k, v in a.items() if k != 'actions'} != {k: v for k, v in b.items() if k != 'actions'}:
            raise ValueError('Recursive/planned policy keys differ')
        if len(a['actions']) != len(b['actions']):
            raise ValueError('Recursive/planned action counts differ')
        for x, y in zip(a['actions'], b['actions']):
            if {k: v for k, v in x.items() if k != 'probability'} != {k: v for k, v in y.items() if k != 'probability'}:
                raise ValueError('Recursive/planned action menus differ')
            policy_gap = max(policy_gap, abs(x['probability']-y['probability']))
    if (metric_gap > spec['acceptance']['cross_backend_metric_absolute_tolerance']
            or policy_gap > spec['acceptance']['cross_backend_policy_absolute_tolerance']):
        raise ValueError('Frozen cross-backend policy/metric agreement missed')
    return {'maximum_policy_absolute_gap': policy_gap, 'maximum_metric_absolute_gap': metric_gap}


def summarize(directory, samples, spec):
    expected_order = [(algorithm, iterations, traversal, repeat)
                      for algorithm in spec['algorithms'] for iterations in spec['iterations']
                      for repeat, order in enumerate(spec['pair_orders'], 1) for traversal in order]
    actual_order = [(r['algorithm'], r['iterations'], r['traversal'], r['repeat']) for r in samples]
    if actual_order != expected_order:
        raise ValueError('Frozen full-call sample order/census changed')
    summary, quality = [], []
    for algorithm in spec['algorithms']:
        for iterations in spec['iterations']:
            row = {'algorithm': algorithm, 'iterations': iterations, 'backends': {}}
            baselines = []
            for traversal in spec['traversals']:
                group = [r for r in samples if (r['algorithm'],r['iterations'],r['traversal']) == (algorithm,iterations,traversal)]
                if len(group) != 3 or len({r['payload_sha256'] for r in group}) != 1:
                    raise ValueError('Per-profile complete payload repeats are not exact')
                baseline = read_payload(directory, group[0]); baselines.append(baseline)
                nc = group[0]['independent_replay']['nash_conv']
                row['backends'][traversal] = {'median_complete_seconds': statistics.median(r['elapsed_seconds'] for r in group),
                    'nash_conv': nc, 'quality_target_met': nc <= spec['acceptance']['final_nash_conv_chip_limit'],
                    'payload_sha256': group[0]['payload_sha256']}
                if iterations == spec['iterations'][-1]:
                    quality.append({'algorithm': algorithm, 'traversal': traversal, 'nash_conv': nc,
                                    'target': spec['acceptance']['final_nash_conv_chip_limit'],
                                    'met': nc <= spec['acceptance']['final_nash_conv_chip_limit']})
            row['cross_backend'] = _cross_compare(*baselines, spec)
            summary.append(row)
    return summary, quality


def _check_physical_record(data, oracle, spec):
    rows = data['production_rows']
    expected = {(a, b, tuple(final)): (mass, sign) for a, b, mass, sign, final in oracle['worlds']}
    if data['pairs'] != 3 or data['worlds'] != 5940 or len(rows) != len(expected):
        raise ValueError('Saved physical census changed')
    seen = set(); gap = 0.0
    for a, b, mass, sign, final in rows:
        key = a, b, tuple(final)
        if key in seen or key not in expected or type(sign) is not int:
            raise ValueError('Saved physical identity changed')
        seen.add(key); wanted_mass, wanted_sign = expected[key]
        gap = max(gap, abs(mass-float(wanted_mass)))
        if not isfinite(mass) or sign != wanted_sign or abs(mass-float(wanted_mass)) > 1e-15:
            raise ValueError('Saved physical sign or mass changed')
    if gap != data['maximum_mass_absolute_gap']:
        raise ValueError('Saved chance disagreement summary changed')


def verify_saved(directory, *, require_quality=False):
    directory = Path(directory)
    index_path = directory / 'index.json'
    if index_path.is_symlink() or not index_path.is_file() or index_path.stat().st_size > 4*1024*1024:
        raise ValueError('Saved index exceeds bounded size')
    report = json.loads(index_path.read_bytes()); unsigned = dict(report); digest = unsigned.pop('artifact_sha256')
    spec = load_spec()
    if (checksum(unsigned) != digest or report['specification'] != spec
            or report['spec_sha256'] != SPEC_SHA or report['validation_errors']):
        raise ValueError('Saved index checksum/specification/validation failed')
    if report['source_before'] != report['source_after'] or report['source_before']['status']:
        raise ValueError('Saved source changed or was not frozen clean')
    if report['preflight'] != preflight(spec):
        raise ValueError('Saved complete admission census changed')
    all_records = [report['oracle_physical_evidence'], report['production_physical_evidence'],
                   *report['samples'], *report['separate_allocation_calls']]
    names = [row['file'] for row in all_records]
    if len(names) != 40 or len(set(names)) != len(names):
        raise ValueError('Every raw observation needs its own immutable evidence file')
    if {path.name for path in directory.iterdir()} != set(names) | {'index.json'}:
        raise ValueError('Evidence directory contains missing or unindexed observations')
    oracle, calls = prepare_reference(spec)
    if calls != report['oracle_forbidden_production_calls']:
        raise ValueError('Saved oracle producer-call audit changed')
    reference = read_payload(directory, report['oracle_physical_evidence'])
    if reference['worlds'] != _world_projection(oracle['worlds']):
        raise ValueError('Saved independent ordered physical worlds changed')
    physical = read_payload(directory, report['production_physical_evidence'])
    _check_physical_record(physical, oracle, spec)
    count = 0
    for row in report['samples'] + report['separate_allocation_calls']:
        payload = read_payload(directory, row)
        if (payload['algorithm'] != row['algorithm'] or payload['iterations'] != row['iterations']
                or payload['execution_backend'] != row['traversal']+'-python'):
            raise ValueError('Saved requested execution identity changed')
        started = datetime.fromisoformat(row['started_at_utc'])
        finished = datetime.fromisoformat(row['finished_at_utc'])
        if started.tzinfo is None or finished.tzinfo is None or finished < started:
            raise ValueError('Invalid UTC observation boundaries')
        checked, guarded = assess(payload, oracle, spec)
        if checked != row['independent_replay'] or guarded != row['forbidden_production_calls']:
            raise ValueError('Saved independent replay summary changed')
        if row['kind'] == 'timed':
            if type(row['elapsed_seconds']) not in (int,float) or not 0 < row['elapsed_seconds'] < 86400:
                raise ValueError('Invalid complete-call observation')
        elif row['kind'] == 'allocation':
            if type(row['python_traced_peak_bytes']) is not int or row['python_traced_peak_bytes'] <= 0:
                raise ValueError('Invalid separate allocation observation')
        else:
            raise ValueError('Unknown observation kind')
        count += 1
    allocation = spec['separate_allocation_calls']
    if [(r['algorithm'],r['iterations'],r['traversal']) for r in report['separate_allocation_calls']] != [
            (allocation['algorithm'], allocation['iterations'], t) for t in allocation['traversals']]:
        raise ValueError('Missing separate allocation call')
    summary, quality = summarize(directory, report['samples'], spec)
    if report['summary'] != summary or report['final_quality'] != quality:
        raise ValueError('Saved runtime, parity or quality summary changed')
    met = all(q['met'] for q in quality)
    if report['quality_gate_met'] is not met or report['status'] != ('passed' if met else 'quality-miss'):
        raise ValueError('Quality status must preserve the original target and misses')
    if require_quality and not met:
        raise ValueError('Original final quality target remains unmet')
    return {'policies_replayed': count, 'worlds_reenumerated': len(oracle['worlds']),
            'independent_validation_passed': True, 'quality_gate_met': met}


def _write_index(directory, report):
    report.pop('artifact_sha256', None); report['artifact_sha256'] = checksum(report)
    raw = json.dumps(report, indent=2, sort_keys=True, allow_nan=False).encode()+b'\n'
    (directory / 'index.json').write_bytes(raw)


def run(directory, *, execution_state=None):
    directory = Path(directory).resolve()
    if directory == ROOT or ROOT in directory.parents or directory.exists():
        raise ValueError('Use a new evidence directory outside the source checkout')
    spec = load_spec()
    before = snapshot()
    report = {'schema_version':1, 'benchmark_id':spec['benchmark_id'],
        'specification':spec, 'spec_sha256':SPEC_SHA, 'source_before':before,
        'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'runtime':{'python':platform.python_version(),'platform':platform.platform()},
        'execution_state':execution_state or {'mode':'direct-call','system_required':False},
        'samples':[], 'separate_allocation_calls':[], 'validation_errors':[]}
    directory.mkdir(parents=False, exist_ok=False)
    try:
        if before['status']:
            raise ValueError('Commit a clean frozen source before measurement')
        subprocess.run(['git','merge-base','--is-ancestor',spec['baseline_commit'],'HEAD'],cwd=ROOT,check=True)
        report['active_phase'] = 'complete-rank-free-admission'
        report['preflight'] = preflight(spec)
        report['active_phase'] = 'independent-physical-preparation'
        oracle, calls = prepare_reference(spec)
        report['oracle_forbidden_production_calls'] = calls
        report['oracle_physical_evidence'] = store_payload(directory, 'independent-physical-worlds.json.gz',
                                    {'worlds':_world_projection(oracle['worlds'])})
        report['active_phase'] = 'production-physical-comparison'
        physical = compare_physical_worlds(spec, oracle)
        report['production_physical_evidence'] = store_payload(directory, 'production-physical-worlds.json.gz', physical)
        for algorithm in spec['algorithms']:
            for iterations in spec['iterations']:
                for repeat, order in enumerate(spec['pair_orders'],1):
                    for traversal in order:
                        report['active_phase'] = 'timed-call'
                        report['active_request'] = {'algorithm':algorithm,'iterations':iterations,
                            'traversal':traversal,'repeat':repeat}
                        _write_index(directory,report)
                        row = timed_call(spec, directory, oracle, algorithm, traversal, iterations, repeat)
                        report['samples'].append(row)
                        if 'replay_error' in row:
                            report['validation_errors'].append(row['file']+': '+row['replay_error'])
                        _write_index(directory,report)
                        print(json.dumps({'event':'sample','algorithm':algorithm,'iterations':iterations,
                            'traversal':traversal,'repeat':repeat,'elapsed_seconds':row['elapsed_seconds'],
                            'nash_conv':row.get('independent_replay',{}).get('nash_conv'), 'replay_error':row.get('replay_error')}),flush=True)
        for traversal in spec['separate_allocation_calls']['traversals']:
            report['active_phase'] = 'separate-allocation-call'
            report['active_request'] = {'traversal':traversal,**spec['separate_allocation_calls']}
            _write_index(directory,report)
            row = allocation_call(spec, directory, oracle, traversal)
            report['separate_allocation_calls'].append(row)
            if 'replay_error' in row:
                report['validation_errors'].append(row['file']+': '+row['replay_error'])
            _write_index(directory,report)
            print(json.dumps({'event':'allocation','traversal':traversal,
                              'python_traced_peak_bytes':row['python_traced_peak_bytes']}),flush=True)
        if not report['validation_errors']:
            report['summary'], report['final_quality'] = summarize(directory,report['samples'],spec)
            report['quality_gate_met'] = all(row['met'] for row in report['final_quality'])
        report.pop('active_phase',None); report.pop('active_request',None)
    except Exception as exc:
        report['validation_errors'].append(f'{type(exc).__name__}: {exc}')
        report['failure_traceback'] = traceback.format_exc()
    finally:
        report['source_after'] = snapshot()
        report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        if before != report['source_after']:
            report['validation_errors'].append('Source changed during experiment')
        report['status'] = ('error' if report['validation_errors'] else
                            'passed' if report['quality_gate_met'] else 'quality-miss')
        _write_index(directory,report)
    if report['status'] != 'error':
        try:
            report['saved_verification'] = verify_saved(directory)
        except Exception as exc:
            report['validation_errors'].append('Saved replay: '+f'{type(exc).__name__}: {exc}')
            report['status'] = 'error'
        _write_index(directory,report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory',type=Path,required=True)
    args = parser.parse_args(); directory = args.output_directory.resolve()
    if directory == ROOT or ROOT in directory.parents or directory.exists():
        parser.error('Choose a new evidence directory outside the checkout')
    with measurement_execution_state() as execution_state:
        report = run(directory, execution_state=execution_state)
    print(json.dumps({'status':report['status'],'artifact_sha256':report['artifact_sha256'],
                      'validation_errors':report['validation_errors'],
                      'final_quality':report.get('final_quality',[])}),flush=True)
    raise SystemExit(0 if report['status']=='passed' else 1)


if __name__ == '__main__':
    main()
