"""Frozen full-deck fixed-flop CFR+ averaging-delay study."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import hashlib
import json
from math import isfinite
from pathlib import Path
import platform
import statistics
import subprocess
import traceback

from pokerlab import postflop_solver as production
from pokerlab import preflop_delayed_cfrplus as delayed_kernel
from pokerlab.public_cfr import MAX_PREFIX_EDGES
from scripts import benchmark_flop_cfrplus as previous
from scripts import benchmark_weighted_full_deck_flop as base
from scripts import verify_flop_cfrplus_publication as baseline_publication
from scripts import verify_weighted_flop_publication as original_baseline_publication
from scripts.benchmark_preflop_covered_counts import canonical, checksum


ROOT = base.ROOT
SPEC_PATH = ROOT / 'benchmarks/weighted-full-deck-flop-delayed-cfrplus-v1.json'
SPEC_SHA256 = '2b1c01a7c9a403cacae691c35347cbfc56726be5aaab8b0b0ea98f952b7bc902'
MAX_INDEX_BYTES = 4 * 1024 * 1024
MAX_RAW_GAP_EXAMPLES = 10
METRICS = ('value_oop', 'value_ip', 'oop_best_response_value',
           'ip_best_response_value', 'oop_best_response_gain',
           'ip_best_response_gain', 'nash_conv', 'exploitability')


def load_spec():
    raw = SPEC_PATH.read_bytes()
    if len(raw) > 64 * 1024:
        raise ValueError('Delayed CFR+ specification exceeds its bound')
    spec = json.loads(raw)
    validate_spec(spec)
    return spec


def validate_spec(spec):
    if type(spec) is not dict or checksum(spec) != SPEC_SHA256:
        raise ValueError('Requires the frozen weighted full-deck delayed-CFR+ specification')
    if (spec.get('iterations') != 140 or spec.get('delays') != [0, 70, 100]
            or spec.get('traversals') != ['recursive', 'public-batched']
            or spec.get('timed_repeats') != 3):
        raise ValueError('Delayed CFR+ protocol dimensions changed')
    if spec['expected']['training_passes_per_iteration'] != 3:
        raise ValueError('The frozen request must retain three CFR+ passes')
    return spec


def snapshot():
    state = previous.snapshot()
    raw = SPEC_PATH.read_bytes()
    state['source_hashes'][SPEC_PATH.relative_to(ROOT).as_posix()] = {
        'raw_sha256': hashlib.sha256(raw).hexdigest(),
        'lf_sha256': hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest(),
    }
    return state


def _rank_free_preflight(iterations):
    if type(iterations) is not int or iterations < 1:
        raise ValueError('Preflight iterations must be a positive exact integer')
    old_spec = previous.load_spec()
    old_spec['iterations'] = [iterations]
    old_spec['expected']['max_world_iterations'] = old_spec['expected']['worlds'] * iterations
    old_spec['expected']['max_world_node_iterations'] = (
        old_spec['expected']['worlds'] * old_spec['expected']['world_traversal_nodes'] * iterations * 3
    )
    return previous.preflight(old_spec)


def preflight(spec):
    validate_spec(spec)
    census = _rank_free_preflight(spec['iterations'])
    for key, expected in spec['expected'].items():
        if key not in ('pair_priors', 'raw_joint_weight_normalizer') and census[key] != expected:
            raise ValueError('Delayed protocol rank-free census changed: '+key)
    # The identical fixture/sweep count shares one structural reservation.
    # Validate and record every delay/backend request before any ranking.
    requests = []
    for delay in spec['delays']:
        if type(delay) is not int or not 0 <= delay < spec['iterations']:
            raise ValueError('Every frozen delay must be an exact integer below iterations')
        for traversal in spec['traversals']:
            requests.append({
                'algorithm': 'cfrplus', 'iterations': spec['iterations'],
                'averaging_delay': delay, 'traversal': traversal,
                'training_passes_per_iteration': 3,
                'world_node_iterations': census['max_world_node_iterations'],
                'public_prefix_hand_edges': census['public_prefix_hand_edges'],
            })
    allocation = spec['separate_allocation_calls']
    for traversal in allocation['traversals']:
        if type(allocation['averaging_delay']) is not int or not 0 <= allocation['averaging_delay'] < allocation['iterations']:
            raise ValueError('Allocation delay must be an exact integer below iterations')
        requests.append({
            'algorithm': allocation['algorithm'], 'iterations': allocation['iterations'],
            'averaging_delay': allocation['averaging_delay'], 'traversal': traversal,
            'training_passes_per_iteration': 3,
            'world_node_iterations': census['worlds'] * census['world_traversal_nodes'] * allocation['iterations'] * 3,
            'public_prefix_hand_edges': census['public_prefix_hand_edges'],
        })
    return {'rank_free': True, 'census': census, 'requests': requests}


def _check_baseline_identity(report, spec, index_bytes):
    old = spec['baseline']
    source = report['source_before']
    if (hashlib.sha256(index_bytes).hexdigest() != old['publication_index_sha256']
            or report['spec_sha256'] != old['publication_spec_sha256']
            or source['revision'] != old['measured_source_revision']
            or source != report['source_after'] or source['status']
            or len(source['source_hashes']) != old['measured_source_files']
            or checksum(source['source_hashes']) != old['measured_source_manifest_sha256']
            or report['quality_gate_met'] is not False):
        raise ValueError('Requires the authenticated immutable measured full-deck CFR+ baseline')
    hashes = {traversal: None for traversal in spec['traversals']}
    for row in report['samples']:
        if row['algorithm'] == 'cfrplus' and row['iterations'] == spec['iterations']:
            if row['repeat'] == 1:
                hashes[row['traversal']] = row['payload_sha256']
    if hashes != old['zero_delay_140_payload_sha256']:
        raise ValueError('Pinned baseline 140-sweep policy hashes changed')
    if (report['baseline']['verification']['policies_replayed']
            != old['original_baseline_policies_replayed']):
        raise ValueError('The original 38-policy baseline replay receipt changed')


def verify_baseline(directory, spec):
    directory = Path(directory)
    path = directory / 'index.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INDEX_BYTES:
        raise ValueError('Invalid bounded immutable baseline index')
    raw = path.read_bytes()
    report = json.loads(raw)
    _check_baseline_identity(report, spec, raw)
    checked = baseline_publication.verify_saved(
        directory, baseline_directory=original_baseline_publication.PUBLICATION,
        require_quality=False)
    if directory.joinpath('index.json').read_bytes() != raw:
        raise ValueError('Baseline index changed during strict reconstruction')
    if (checked['policies_replayed'] != spec['baseline']['policies_replayed']
            or checked['quality_gate_met'] is not False
            or checked['raw_index_sha256'] != spec['baseline']['publication_index_sha256']):
        raise ValueError('Pinned 20-policy CFR+ baseline verification changed')
    return {
        'publication_index_sha256': spec['baseline']['publication_index_sha256'],
        'publication_spec_sha256': spec['baseline']['publication_spec_sha256'],
        'source_revision': spec['baseline']['measured_source_revision'],
        'source_manifest_sha256': spec['baseline']['measured_source_manifest_sha256'],
        'strict_verification': checked,
        'quality_gate_met': False,
        'zero_delay_140_payload_sha256': dict(spec['baseline']['zero_delay_140_payload_sha256']),
    }


def _guarded_reference(spec):
    # The baseline oracle guard predates the postflop delayed adapter. Protect
    # that new trainer explicitly as well as all older ranking/training helpers.
    from unittest.mock import patch
    called = {'preflop_delayed_cfrplus.train_delayed_public_cfrplus': 0}
    def forbidden(*args, **kwargs):
        called['preflop_delayed_cfrplus.train_delayed_public_cfrplus'] += 1
        raise AssertionError('Independent reference called the delayed production trainer')
    with patch.object(delayed_kernel, 'train_delayed_public_cfrplus', side_effect=forbidden):
        oracle, production_calls = base.prepare_reference(spec)
    if any(called.values()) or any(production_calls.values()):
        raise ValueError('Independent physical preparation invoked production code')
    return oracle, {'legacy_production_helpers': production_calls,
                    'delayed_trainer_calls': called}


def _assess(payload, oracle, spec):
    from scripts.flop_multistreet_validation import replay
    from unittest.mock import patch
    calls = {'preflop_delayed_cfrplus.train_delayed_public_cfrplus': 0}
    def forbidden(*args, **kwargs):
        calls['preflop_delayed_cfrplus.train_delayed_public_cfrplus'] += 1
        raise AssertionError('Independent replay called the delayed production trainer')
    with ExitStack() as stack:
        legacy = stack.enter_context(base.independent_guard())
        stack.enter_context(patch.object(delayed_kernel, 'train_delayed_public_cfrplus', side_effect=forbidden))
        checked = replay(payload, oracle,
                         tolerance=spec['acceptance']['independent_metric_absolute_tolerance'])
    if any(legacy.values()) or any(calls.values()):
        raise ValueError('Candidate replay invoked production computation')
    return checked, {'legacy_production_helpers': legacy,
                     'delayed_trainer_calls': calls}


def _check_candidate(payload, row, spec):
    expected = {
        'algorithm': 'cfrplus', 'iterations': row['iterations'],
        'execution_backend': row['traversal'] + '-python',
        'plan_operation_limit': None,
        'public_batch_edge_limit': MAX_PREFIX_EDGES if row['traversal'] == 'public-batched' else None,
        'training_passes_per_iteration': 3,
        'update_schedule': 'alternating-oop-then-ip',
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError('Saved requested CFR+ execution identity changed: ' + key)
    if (row.get('algorithm') != 'cfrplus'
            or row['traversal'] not in ('recursive', 'public-batched')
            or type(row['iterations']) is not int or row['iterations'] < 1):
        raise ValueError('Invalid saved requested algorithm/traversal/iterations')
    delay = row['averaging_delay']
    if type(delay) is not int or not 0 <= delay < row['iterations']:
        raise ValueError('Sample delay is not an exact integer below iterations')
    if delay == 0:
        previous.check_candidate(payload, {'algorithm': 'cfrplus',
                                           'iterations': row['iterations'],
                                           'traversal': row['traversal']})
        if any(key in payload for key in ('averaging_delay', 'averaging_positive_sweeps', 'cfrplus_kernel')):
            raise ValueError('Zero-delay payload must preserve the old output shape')
    else:
        if (payload.get('averaging_delay') != delay
                or type(payload.get('averaging_delay')) is not int
                or payload.get('averaging_positive_sweeps') != row['iterations'] - delay
                or type(payload.get('averaging_positive_sweeps')) is not int
                or payload.get('average_schedule') != 'delayed-linear-post-sweep-own-reach'):
            raise ValueError('Positive-delay average schedule metadata changed')
        if row['traversal'] == 'public-batched':
            if payload.get('cfrplus_kernel') != 'delayed-public-batched-cfrplus-python':
                raise ValueError('Positive public-batched kernel provenance changed')
        elif 'cfrplus_kernel' in payload:
            raise ValueError('Recursive delayed output has unexpected vector-kernel provenance')


def _check_zero_control_hash(payload_sha256, traversal, spec):
    expected = spec['baseline']['zero_delay_140_payload_sha256'].get(traversal)
    if expected is None or payload_sha256 != expected:
        raise ValueError('Zero-delay 140-sweep payload differs from its immutable control')


def _decision_paths(oracle):
    from scripts.flop_multistreet_validation import _Chance, _Decision, _Terminal
    paths = {}
    def visit(node, ancestors):
        if isinstance(node, _Chance):
            for card in sorted(node.branches):
                visit(node.branches[card], ancestors)
        elif isinstance(node, _Decision):
            key = (node.player, node.history)
            if key in paths and paths[key] != ancestors:
                raise ValueError('Independent public history has multiple decision paths')
            paths[key] = ancestors
            for action_index, child in enumerate(node.children):
                visit(child, ancestors + ((node.player, node.history, action_index),))
        elif not isinstance(node, _Terminal):
            raise ValueError('Independent oracle contains an unknown tree node')
    visit(oracle['root'], ())
    return paths


def _own_reach_masses(payload, oracle, paths):
    from scripts.flop_multistreet_validation import _revealed
    policy = {(0 if row['player'] == 'oop' else 1, row['hand'], tuple(row['history'])):
              row['actions'] for row in payload['strategy']}
    prefixes = {tuple(_revealed(history)) for _, history in paths}
    chance_masses = {}
    for world in oracle['worlds']:
        world_prefixes = [tuple(world[4][3:3+length]) for length in range(3)]
        for player in (0, 1):
            for prefix in world_prefixes:
                if prefix in prefixes:
                    key = (player, world[player], prefix)
                    chance_masses[key] = chance_masses.get(key, 0.0) + float(world[2])
    reaches = {}
    # Iterate exactly the actual information keys. A Cartesian product of all
    # hands/public histories includes impossible blocker combinations, whose
    # ancestor rows correctly do not exist in a physical policy.
    for player, hand, history in policy:
        prefix = tuple(_revealed(history))
        reach = chance_masses.get((player, hand, prefix), 0.0)
        for ancestor_player, ancestor_history, action_index in paths[(player, history)]:
            if ancestor_player == player:
                actions = policy[(player, hand, ancestor_history)]
                reach *= actions[action_index]['probability']
        reaches[(player, hand, history)] = reach
    return reaches


def _cross_compare(left, right, spec, oracle):
    acceptance = spec['acceptance']
    scalar_gap = max(abs(left[key] - right[key]) for key in METRICS)
    ignored = set(METRICS) | {'strategy', 'execution_backend', 'plan_operation_limit',
                              'public_batch_edge_limit', 'cfrplus_kernel'}
    if ({key: value for key, value in left.items() if key not in ignored}
            != {key: value for key, value in right.items() if key not in ignored}):
        raise ValueError('Cross-backend structural payload fields differ')
    def row_key(row):
        return (row['player'], row['hand'], row['street'], tuple(row['board']), tuple(row['history']))
    left_rows = {row_key(row): row for row in left['strategy']}
    right_rows = {row_key(row): row for row in right['strategy']}
    if (len(left_rows) != len(left['strategy']) or len(right_rows) != len(right['strategy'])
            or set(left_rows) != set(right_rows)):
        raise ValueError('Cross-backend information-set coverage differs')
    if any(type(row.get('probability')) not in (int, float) or
           not isfinite(row['probability']) for payload in (left, right)
           for row in payload['strategy'] for row in row['actions']):
        raise ValueError('Cross-backend action probability must be finite')
    if any(type(payload.get(key)) not in (int, float) or not isfinite(payload[key])
           for payload in (left, right) for key in METRICS):
        raise ValueError('Cross-backend scalar metric must be finite')
    paths = _decision_paths(oracle)
    left_reaches = _own_reach_masses(left, oracle, paths)
    right_reaches = _own_reach_masses(right, oracle, paths)
    max_raw_gap = 0.0
    nonzero_raw_gaps = 0
    max_realization_gap = 0.0
    examples = []
    for key in sorted(left_rows):
        a, b = left_rows[key], right_rows[key]
        if {field: value for field, value in a.items() if field != 'actions'} != {
                field: value for field, value in b.items() if field != 'actions'}:
            raise ValueError('Cross-backend strategy row metadata differs')
        if len(a['actions']) != len(b['actions']):
            raise ValueError('Cross-backend action counts differ')
        player = 0 if key[0] == 'oop' else 1
        reach_a = left_reaches[(player, key[1], key[4])]
        reach_b = right_reaches[(player, key[1], key[4])]
        for index, (x, y) in enumerate(zip(a['actions'], b['actions'])):
            if ({field: x[field] for field in x if field != 'probability'}
                    != {field: y[field] for field in y if field != 'probability'}):
                raise ValueError('Cross-backend numeric action menus differ')
            raw_gap = abs(x['probability'] - y['probability'])
            if raw_gap:
                nonzero_raw_gaps += 1
                max_raw_gap = max(max_raw_gap, raw_gap)
                examples.append({
                    'row': {'player': key[0], 'hand': key[1], 'street': key[2],
                            'board': list(key[3]), 'history': list(key[4])},
                    'action_index': index, 'action': x['history_key'],
                    'left_probability': x['probability'], 'right_probability': y['probability'],
                    'absolute_gap': raw_gap,
                })
            realization_gap = abs(reach_a * x['probability'] - reach_b * y['probability'])
            max_realization_gap = max(max_realization_gap, realization_gap)
    if scalar_gap > acceptance['cross_backend_scalar_absolute_tolerance']:
        raise ValueError('Cross-backend scalar metric tolerance missed')
    if max_realization_gap > acceptance['cross_backend_action_realization_absolute_tolerance']:
        raise ValueError('Cross-backend all-row action realization tolerance missed')
    examples.sort(key=lambda row: (-row['absolute_gap'], row['row']['player'],
                                   row['row']['hand'], row['row']['history'], row['action_index']))
    return {
        'maximum_scalar_absolute_gap': scalar_gap,
        'maximum_action_realization_absolute_gap': max_realization_gap,
        'maximum_raw_conditional_probability_gap': max_raw_gap,
        'nonzero_raw_conditional_probability_gap_count': nonzero_raw_gaps,
        'largest_raw_conditional_probability_gap_examples': examples[:MAX_RAW_GAP_EXAMPLES],
        'raw_conditional_probability_gap_gated': False,
    }


def _expected_sample_order(spec):
    return [(delay, spec['iterations'], traversal, repeat)
            for delay in spec['delays']
            for repeat, order in enumerate(spec['pair_orders'], 1)
            for traversal in order]


def _summarize(directory, samples, spec, oracle):
    expected = _expected_sample_order(spec)
    actual = [(row['averaging_delay'], row['iterations'], row['traversal'], row['repeat'])
              for row in samples]
    if actual != expected:
        raise ValueError('Frozen delayed-CFR+ paired order/census changed')
    if any(row['kind'] != 'timed' or row['algorithm'] != 'cfrplus' for row in samples):
        raise ValueError('Every paired sample must be an untraced timed CFR+ call')
    summary, quality = [], []
    for delay in spec['delays']:
        item = {'averaging_delay': delay, 'iterations': spec['iterations'], 'backends': {}}
        payloads = []
        for traversal in spec['traversals']:
            rows = [row for row in samples if (row['averaging_delay'], row['traversal']) == (delay, traversal)]
            if len(rows) != 3 or len({row['payload_sha256'] for row in rows}) != 1:
                raise ValueError('Per-delay/backend complete-call repeats are not exact')
            first = rows[0]
            payload = base.read_payload(directory, first)
            _check_candidate(payload, first, spec)
            if delay == 0:
                _check_zero_control_hash(first['payload_sha256'], traversal, spec)
            payloads.append(payload)
            nc = first['independent_replay']['nash_conv']
            met = nc <= spec['acceptance']['final_nash_conv_chip_limit']
            item['backends'][traversal] = {
                'median_complete_seconds': statistics.median(row['elapsed_seconds'] for row in rows),
                'nash_conv': nc, 'quality_target': spec['acceptance']['final_nash_conv_chip_limit'],
                'quality_target_met': met, 'payload_sha256': first['payload_sha256'],
            }
            quality.append({'averaging_delay': delay, 'iterations': spec['iterations'],
                            'traversal': traversal, 'nash_conv': nc,
                            'target': spec['acceptance']['final_nash_conv_chip_limit'], 'met': met})
        item['cross_backend'] = _cross_compare(payloads[0], payloads[1], spec, oracle)
        summary.append(item)
    return summary, quality


def _store_physical(directory, filename, payload):
    return base.store_payload(directory, filename, payload)


def _timed_call(spec, directory, oracle, delay, traversal, repeat):
    from time import perf_counter
    import gc
    gc.collect()
    started_at = datetime.now(timezone.utc).isoformat()
    start = perf_counter()
    row = {'kind': 'timed', 'algorithm': 'cfrplus', 'iterations': spec['iterations'],
           'averaging_delay': delay, 'traversal': traversal, 'repeat': repeat,
           'started_at_utc': started_at}
    try:
        payload = production.solve_postflop(
            spec['board'], spec['oop_range'], spec['ip_range'], config=spec['config'],
            iterations=spec['iterations'], algorithm='cfrplus', traversal=traversal,
            averaging_delay=delay)
        raw = canonical(payload)
        digest = hashlib.sha256(raw).hexdigest()
        row['elapsed_seconds'] = perf_counter() - start
        row['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        artifact = base.store_payload(
            directory, f'cfrplus-{spec["iterations"]}-delay-{delay}-{traversal}-{repeat}.json.gz',
            payload)
        row.update(artifact)
        _check_candidate(payload, row, spec)
        if delay == 0:
            _check_zero_control_hash(digest, traversal, spec)
        checked, calls = _assess(payload, oracle, spec)
        row['independent_replay'], row['forbidden_production_calls'] = checked, calls
        if digest != row['payload_sha256']:
            raise ValueError('Canonical timed serialization hash changed')
    except Exception as exc:
        row.setdefault('elapsed_seconds', perf_counter() - start)
        row['failure_validation_seconds'] = perf_counter() - start - row['elapsed_seconds']
        row['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        row['error'] = f'{type(exc).__name__}: {exc}'
    return row


def _allocation_call(spec, directory, oracle, traversal):
    import gc
    import tracemalloc
    allocation = spec['separate_allocation_calls']
    gc.collect()
    started_at = datetime.now(timezone.utc).isoformat()
    row = {'kind': 'allocation', 'algorithm': allocation['algorithm'],
           'iterations': allocation['iterations'], 'averaging_delay': allocation['averaging_delay'],
           'traversal': traversal, 'started_at_utc': started_at}
    try:
        tracemalloc.start()
        try:
            payload = production.solve_postflop(
                spec['board'], spec['oop_range'], spec['ip_range'], config=spec['config'],
                iterations=allocation['iterations'], algorithm=allocation['algorithm'],
                traversal=traversal, averaging_delay=allocation['averaging_delay'])
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        row['python_traced_peak_bytes'] = peak
        row['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        artifact = base.store_payload(
            directory, f'allocation-delay-{allocation["averaging_delay"]}-{traversal}.json.gz',
            payload)
        row.update(artifact)
        _check_candidate(payload, row, spec)
        checked, calls = _assess(payload, oracle, spec)
        row['independent_replay'], row['forbidden_production_calls'] = checked, calls
    except Exception as exc:
        row['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        row['error'] = f'{type(exc).__name__}: {exc}'
    return row


def _write_index(directory, report):
    report.pop('artifact_sha256', None)
    report['artifact_sha256'] = checksum(report)
    raw = json.dumps(report, indent=2, sort_keys=True, allow_nan=False).encode() + b'\n'
    if len(raw) > MAX_INDEX_BYTES:
        raise ValueError('Delayed CFR+ report exceeds bounded index size')
    (directory / 'index.json').write_bytes(raw)


def verify_saved(directory, baseline_directory):
    directory = Path(directory)
    index = directory / 'index.json'
    if index.is_symlink() or not index.is_file() or index.stat().st_size > MAX_INDEX_BYTES:
        raise ValueError('Invalid bounded delayed-CFR+ index')
    raw = index.read_bytes()
    report = json.loads(raw)
    unsigned = dict(report)
    digest = unsigned.pop('artifact_sha256', None)
    spec = load_spec()
    if (checksum(unsigned) != digest or report.get('specification') != spec
            or report.get('spec_sha256') != SPEC_SHA256 or report.get('validation_errors')):
        raise ValueError('Saved delayed-CFR+ checksum/specification/validation failed')
    if report.get('source_before') != report.get('source_after') or report['source_before']['status']:
        raise ValueError('Candidate source changed during the delayed-CFR+ study')
    if report['baseline'] != verify_baseline(baseline_directory, spec):
        raise ValueError('Immutable baseline verification receipt changed')
    if report['preflight'] != preflight(spec):
        raise ValueError('Saved rank-free delayed-CFR+ admission changed')
    evidence = [report['oracle_physical_evidence'], report['production_physical_evidence'],
                *report['samples'], *report['separate_allocation_calls']]
    files = [row['file'] for row in evidence]
    if len(files) != 22 or len(set(files)) != 22 or {path.name for path in directory.iterdir()} != set(files) | {'index.json'}:
        raise ValueError('Delayed-CFR+ report must inventory exactly 23 files')
    oracle, guard = _guarded_reference(spec)
    if guard != report['oracle_forbidden_production_calls']:
        raise ValueError('Saved independent-oracle guard census changed')
    expected_worlds = base._world_projection(oracle['worlds'])
    if base.read_payload(directory, report['oracle_physical_evidence']) != {'worlds': expected_worlds}:
        raise ValueError('Saved independent ordered physical worlds changed')
    base._check_physical_record(base.read_payload(directory, report['production_physical_evidence']), oracle, spec)
    for row in report['samples'] + report['separate_allocation_calls']:
        payload = base.read_payload(directory, row)
        _check_candidate(payload, row, spec)
        checked, calls = _assess(payload, oracle, spec)
        if checked != row['independent_replay'] or calls != row['forbidden_production_calls']:
            raise ValueError('Saved candidate policy independent replay changed')
        start = datetime.fromisoformat(row['started_at_utc'])
        end = datetime.fromisoformat(row['finished_at_utc'])
        if start.tzinfo is None or end.tzinfo is None or end < start:
            raise ValueError('Invalid delayed-CFR+ UTC observation boundaries')
        if row['kind'] == 'timed':
            elapsed = row.get('elapsed_seconds')
            if type(elapsed) not in (int, float) or not 0 < elapsed < 86400:
                raise ValueError('Invalid complete-call timing observation')
            if row['averaging_delay'] == 0:
                _check_zero_control_hash(row['payload_sha256'], row['traversal'], spec)
        elif row['kind'] == 'allocation':
            if type(row.get('python_traced_peak_bytes')) is not int or row['python_traced_peak_bytes'] <= 0:
                raise ValueError('Invalid separately traced allocation observation')
        else:
            raise ValueError('Unknown delayed-CFR+ evidence type')
    expected_allocation = [('allocation', 10, 1, traversal)
                           for traversal in spec['separate_allocation_calls']['traversals']]
    if [(row['kind'], row['iterations'], row['averaging_delay'], row['traversal'])
            for row in report['separate_allocation_calls']] != expected_allocation:
        raise ValueError('Missing separate delay-one allocation call')
    summary, quality = _summarize(directory, report['samples'], spec, oracle)
    quality_met = all(row['met'] for row in quality)
    expected_status = 'passed' if quality_met else 'quality-miss'
    if (summary != report['summary'] or quality != report['final_quality']
            or report['quality_gate_met'] is not quality_met or report['status'] != expected_status):
        raise ValueError('Saved delayed-CFR+ summary or original quality misses changed')
    if index.read_bytes() != raw:
        raise ValueError('Delayed-CFR+ report changed during saved verification')
    return {'policies_replayed': len(report['samples']) + len(report['separate_allocation_calls']),
            'worlds_reenumerated': len(oracle['worlds']), 'independent_validation_passed': True,
            'quality_gate_met': quality_met, 'file_count': 23}


def run(directory, baseline_directory, *, execution_state=None):
    directory = Path(directory).resolve()
    baseline_directory = Path(baseline_directory).resolve()
    if (directory == ROOT or ROOT in directory.parents or directory.exists()
            or directory in baseline_directory.parents or baseline_directory in directory.parents
            or directory == baseline_directory):
        raise ValueError('Use a new evidence directory outside source and immutable baseline folders')
    spec = load_spec()
    before = snapshot()
    report = {
        'schema_version': 1, 'benchmark_id': spec['benchmark_id'],
        'specification': spec, 'spec_sha256': SPEC_SHA256,
        'source_before': before, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'runtime': {'python': platform.python_version(), 'executable': __import__('sys').executable,
                    'platform': platform.platform()},
        'execution_state': execution_state or {'mode': 'direct-call', 'system_required': False},
        'samples': [], 'separate_allocation_calls': [], 'validation_errors': [],
    }
    directory.mkdir(parents=False, exist_ok=False)
    try:
        if before['status']:
            raise ValueError('Commit a clean frozen delayed-CFR+ candidate before measurement')
        subprocess.run(['git', 'merge-base', '--is-ancestor', spec['baseline']['commit'], 'HEAD'],
                       cwd=ROOT, check=True)
        report['active_phase'] = 'rank-free-full-request-admission'
        report['preflight'] = preflight(spec)
        report['active_phase'] = 'strict-immutable-baseline-reconstruction'
        report['baseline'] = verify_baseline(baseline_directory, spec)
        report['active_phase'] = 'independent-physical-preparation'
        oracle, calls = _guarded_reference(spec)
        report['oracle_forbidden_production_calls'] = calls
        report['oracle_physical_evidence'] = _store_physical(
            directory, 'independent-physical-worlds.json.gz',
            {'worlds': base._world_projection(oracle['worlds'])})
        report['production_physical_evidence'] = _store_physical(
            directory, 'production-physical-worlds.json.gz',
            base.compare_physical_worlds(spec, oracle))
        for delay in spec['delays']:
            for repeat, order in enumerate(spec['pair_orders'], 1):
                for traversal in order:
                    report['active_phase'] = 'complete-timed-call'
                    report['active_request'] = {'algorithm': 'cfrplus', 'iterations': spec['iterations'],
                                                'averaging_delay': delay, 'traversal': traversal,
                                                'repeat': repeat}
                    _write_index(directory, report)
                    row = _timed_call(spec, directory, oracle, delay, traversal, repeat)
                    report['samples'].append(row)
                    if 'error' in row:
                        report['validation_errors'].append(row['file'] + ': ' + row['error']
                                                           if 'file' in row else row['error'])
                    _write_index(directory, report)
                    print(json.dumps({'event': 'sample', **report['active_request'],
                                      'elapsed_seconds': row.get('elapsed_seconds'),
                                      'nash_conv': row.get('independent_replay', {}).get('nash_conv'),
                                      'error': row.get('error')}, allow_nan=False), flush=True)
        for traversal in spec['separate_allocation_calls']['traversals']:
            report['active_phase'] = 'separate-traced-allocation-call'
            report['active_request'] = {'averaging_delay': 1, 'traversal': traversal}
            _write_index(directory, report)
            row = _allocation_call(spec, directory, oracle, traversal)
            report['separate_allocation_calls'].append(row)
            if 'error' in row:
                report['validation_errors'].append(row['error'])
            _write_index(directory, report)
            print(json.dumps({'event': 'allocation', 'traversal': traversal,
                              'averaging_delay': 1,
                              'python_traced_peak_bytes': row.get('python_traced_peak_bytes'),
                              'error': row.get('error')}, allow_nan=False), flush=True)
        if not report['validation_errors']:
            report['summary'], report['final_quality'] = _summarize(
                directory, report['samples'], spec, oracle)
            report['quality_gate_met'] = all(row['met'] for row in report['final_quality'])
        report.pop('active_phase', None)
        report.pop('active_request', None)
    except Exception as exc:
        report['validation_errors'].append(f'{type(exc).__name__}: {exc}')
        report['failure_traceback'] = traceback.format_exc()
    finally:
        report['source_after'] = snapshot()
        report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        if before != report['source_after']:
            report['validation_errors'].append('Candidate source changed during delayed-CFR+ experiment')
        report['status'] = ('error' if report['validation_errors'] else
                            'passed' if report.get('quality_gate_met') else 'quality-miss')
        _write_index(directory, report)
    if report['status'] != 'error':
        try:
            report['saved_verification'] = verify_saved(directory, baseline_directory)
        except Exception as exc:
            report['validation_errors'].append(f'Saved replay: {type(exc).__name__}: {exc}')
            report['status'] = 'error'
        _write_index(directory, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--baseline-directory', type=Path,
                        default=baseline_publication.PUBLICATION)
    args = parser.parse_args()
    with base.measurement_execution_state() as execution_state:
        report = run(args.output_directory, args.baseline_directory,
                     execution_state=execution_state)
    print(json.dumps({'status': report['status'], 'artifact_sha256': report.get('artifact_sha256'),
                      'validation_errors': report['validation_errors'],
                      'final_quality': report.get('final_quality', [])}, allow_nan=False), flush=True)
    raise SystemExit(0 if report['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
