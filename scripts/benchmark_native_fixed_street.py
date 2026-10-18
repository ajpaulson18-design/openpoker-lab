"""Measure explicit native versus Python training on prepared fixed-street games.
No compilation, ranking or board enumeration is performed by this runner.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import gc
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
from time import perf_counter
import tracemalloc
from scripts import benchmark_fixed_street_profile as profile

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / 'benchmarks' / 'native-fixed-street-v1.json'
PROFILE_ARTIFACT = 'benchmarks/results/fixed-street-profile-v1.json'
EXPECTED_SPEC_SHA256 = '9eae5a9c620fa1bce94e0717c23a3ee8820b37bdfdbca815ce00c23e1f5b8a20'
EXPECTED_BASELINE = '5642c546d570100ad87c00270ddbf509eac72176'
EXPECTED_PROFILES = {'preflop': (('vanilla', 8000), ('dcfr', 8000), ('cfrplus', 3000)),
                     'flop': (('vanilla', 4000), ('dcfr', 4000), ('cfrplus', 4000))}
BACKENDS = ('python', 'native')
METRICS = {'preflop': ('value_sb', 'value_bb', 'sb_best_response_value',
                       'bb_best_response_value', 'sb_best_response_gain',
                       'bb_best_response_gain', 'nash_conv', 'exploitability'),
           'flop': ('value_oop', 'value_ip', 'oop_best_response_value',
                    'ip_best_response_value', 'oop_best_response_gain',
                    'ip_best_response_gain', 'nash_conv', 'exploitability')}


def _canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def checksum(value):
    return _sha(_canonical_bytes(value))


def _git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def _source_hashes():
    hashes = profile._source_hashes()
    paths = (*sorted((ROOT / 'native').glob('*.c')),
             ROOT / 'scripts' / 'build_native_train.py', SPEC_PATH,
             ROOT / 'benchmarks' / 'native-fixed-street-vector-v1.json',
             ROOT / PROFILE_ARTIFACT,
             ROOT / '.github' / 'workflows' / 'native-fixed-street.yml')
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        raw = path.read_bytes()
        hashes[path.relative_to(ROOT).as_posix()] = {
            'raw_sha256': _sha(raw), 'lf_sha256': _sha(raw.replace(b'\r\n', b'\n'))}
    return hashes


def _identity():
    return {'revision': _git('rev-parse', 'HEAD'),
            'status': _git('status', '--porcelain', '--untracked-files=all').splitlines(),
            'source_hashes': _source_hashes()}


def validate_spec(spec):
    if type(spec) is not dict or checksum(spec) != EXPECTED_SPEC_SHA256:
        raise ValueError('Native fixed-street benchmark requires the exact frozen specification')
    if (spec.get('benchmark_id') != 'native-fixed-street-v1'
            or spec.get('schema_version') != 1
            or spec.get('baseline_commit') != EXPECTED_BASELINE
            or spec.get('timed_repeats') != 3
            or spec.get('pair_order') != ['python', 'native', 'native', 'python', 'python', 'native']):
        raise ValueError('Frozen benchmark identity or pair order changed')
    if spec.get('preparation', {}).get('profile_spec_sha256') != profile.EXPECTED_SPEC_SHA256:
        raise ValueError('Pinned prepared profile specification changed')
    for game in ('preflop', 'flop'):
        rows = spec.get(game, {}).get('profiles')
        actual = tuple((row.get('algorithm'), row.get('iterations')) for row in rows) if type(rows) is list else ()
        if actual != EXPECTED_PROFILES[game]:
            raise ValueError('Frozen profile set changed for ' + game)
    gates = {'minimum_python_over_native_median_ratio': 1.5,
             'cross_backend_metric_absolute_tolerance': 1e-8,
             'cross_backend_policy_probability_absolute_tolerance': 1e-6,
             'independent_replay_tolerance': 1e-10, 'target_nash_conv': 0.005,
             'target_padding': 1e-10, 'mandatory_quality_algorithm': 'cfrplus'}
    if any(spec.get('acceptance', {}).get(k) != v for k, v in gates.items()):
        raise ValueError('Frozen acceptance gate changed')
    return spec


def _verify_profile_artifact(spec):
    pinned = spec['preparation']
    commit, path = pinned['profile_artifact_commit'], pinned['profile_artifact_path']
    blob = _git('rev-parse', f'{commit}:{path}')
    current_blob = _git('rev-parse', f"HEAD:{path}")
    if blob != pinned['profile_artifact_blob'] or current_blob != blob:
        raise ValueError('Pinned prepared-profile artifact differs from the current committed source')
    artifact = json.loads(subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT))
    digest = artifact.get('artifact_sha256')
    unsigned = dict(artifact); unsigned.pop('artifact_sha256', None)
    if digest != checksum(unsigned) or artifact.get('status') != 'passed':
        raise ValueError('Pinned prepared-profile report is corrupt or unsuccessful')
    for game, key in (('preflop', 'preflop_profile_payload_sha256'),
                      ('flop', 'flop_profile_payload_sha256')):
        case = artifact.get('cases', {}).get(game, {})
        if case.get('status') != 'passed' or case.get('unwrapped_reference', {}).get('payload_sha256') != pinned[key]:
            raise ValueError('Pinned PR141 payload hash changed for ' + game)
    return {'commit': commit, 'path': path, 'git_blob': blob,
            'current_git_blob': current_blob, 'artifact_sha256': digest,
            'preflop_payload_sha256': pinned['preflop_profile_payload_sha256'],
            'flop_payload_sha256': pinned['flop_profile_payload_sha256']}


def _require_baseline_ancestor(commit):
    result = subprocess.run(['git', 'merge-base', '--is-ancestor', EXPECTED_BASELINE, commit],
                            cwd=ROOT, capture_output=True, check=False)
    if result.returncode:
        raise ValueError('Frozen benchmark baseline is not an ancestor of HEAD')


def _load_inputs(spec):
    return {'preflop': profile._load_preflop_table(spec),
            'flop': profile._load_flop_table(spec)}


def _preflight_preflop(item, algorithm, iterations):
    from pokerlab import native_fixed_street as native
    from pokerlab.preflop_checkdown_budget import admit_prepared, options
    case, table = item['case'], item['table']
    cfg = options(case['config'], iterations, algorithm, 'prepared-counts')
    reference = admit_prepared(table, cfg, iterations, algorithm,
                               'prepared-counts', world_indexing='pair-mean')
    upper = reference['tree_upper_bound']
    shape = native.admit_native_shape(upper['public_states'], len(table.pairs),
                                      upper['information_action_slots'], iterations, algorithm)
    complete = native.complete_solve_admission(
        shape, reference['total_loop_entries_upper_bound'],
        reference['training_loop_entries_upper_bound'])
    return {'python_complete_admission': reference,
            'native_complete_admission': complete, 'native_shape': shape}


def _preflight_flop(item, algorithm, iterations):
    from pokerlab.flop_checkdown_solver import (
        MAX_PUBLIC_STATES, _NoPublicChance, _validate_options)
    from pokerlab.preflop_vector_budget import (
        MAX_INFO_ACTION_SLOTS, MAX_TOTAL_LOOP_ENTRIES, estimate_vector_budget)
    from pokerlab.river_tree import _Node, _build_tree
    from pokerlab import native_fixed_street as native

    case, table = item['case'], item['table']
    config = _validate_options(case['config'], iterations, algorithm)
    counts = {'decision': 0, 'terminal': 0}
    def reserve(kind):
        if sum(counts.values()) >= MAX_PUBLIC_STATES:
            raise ValueError('Flop preflight tree exceeds production state cap')
        counts[kind] += 1
    root, decisions = _build_tree(config, allocation_hook=reserve)
    active = ({i for i, _, _ in table.pairs}, {j for _, j, _ in table.pairs})
    infos, slots, pending = {}, 0, [root]
    while pending:
        node = pending.pop()
        if not isinstance(node, _Node):
            continue
        for hand in active[node.player]:
            slots += len(node.actions)
            if slots > MAX_INFO_ACTION_SLOTS:
                raise ValueError('Flop preflight information-action cap exceeded')
            infos[node.player, hand, node.history] = len(node.actions)
        pending.extend(reversed(node.children))
    if decisions > MAX_PUBLIC_STATES or sum(counts.values()) > MAX_PUBLIC_STATES:
        raise ValueError('Flop preflight tree exceeds production state cap')
    pairs = len(table.pairs)
    structural_worlds = [(i, j, 1.0 / (3 * pairs), sign)
                         for i, j, _ in table.pairs for sign in (-1, 0, 1)]
    vector = estimate_vector_budget(root, structural_worlds, infos, iterations,
                                    algorithm, chance_type=_NoPublicChance)
    source = (128 + 4 * table.budget['candidate_pairs'] + 128 * pairs
              + 64 * table.budget['unordered_boards'])
    total = vector['total_loop_entries_upper_bound'] + source
    if total > MAX_TOTAL_LOOP_ENTRIES:
        raise ValueError('Flop reference complete modeled-work cap exceeded')
    reference = {'budget_version': 'direct-flop-checkdown-budget-v1',
                 'vector_upper_bound': vector, 'source_admission': table.budget,
                 'source_bookkeeping_loop_entries_upper_bound': source,
                 'total_loop_entries_upper_bound': total,
                 'total_loop_entry_limit': MAX_TOTAL_LOOP_ENTRIES}
    shape = native.admit_native_shape(
        sum(counts.values()), pairs, slots, iterations, algorithm,
        reduction='public-batched', hand_counts=tuple(map(len, active)))
    complete = native.complete_solve_admission(shape, total,
                                                 vector['training_loop_entries_upper_bound'])
    return {'python_complete_admission': reference, 'native_complete_admission': complete,
            'native_shape': shape,
            'tree': {'decision_nodes': decisions, 'terminal_nodes': counts['terminal'],
                     'public_states': sum(counts.values()), 'information_sets': len(infos),
                     'information_action_slots': slots}}


def _preflight_all(spec, items):
    rows = []
    for game in ('preflop', 'flop'):
        for case in spec[game]['profiles']:
            identity = {'game': game, 'algorithm': case['algorithm'],
                        'iterations': case['iterations']}
            try:
                row = (_preflight_preflop(items[game], case['algorithm'], case['iterations'])
                       if game == 'preflop' else
                       _preflight_flop(items[game], case['algorithm'], case['iterations']))
                row.update(identity)
                row['status'] = 'admitted'
            except Exception as exc:
                row = {**identity, 'status': 'rejected',
                       'error': f'{type(exc).__name__}: {exc}'}
            rows.append(row)
    if len(rows) != 6:
        raise AssertionError('Exactly six backend preflights are required')
    return rows


def _phase_targets(game, backend, algorithm):
    from pokerlab import cfr, native_fixed_street as native
    if game == 'preflop':
        from pokerlab import preflop_checkdown_solver as solver
        if backend == 'native':
            trainer = ('native_train', native, 'train_native_fixed_street')
        elif algorithm == 'cfrplus':
            trainer = ('train_cfrplus', solver, 'train_cfrplus')
        else:
            trainer = ('train_cfr', cfr, 'train')
        return [trainer, ('evaluate', cfr, 'evaluate'),
                ('best_response', cfr, 'best_response')]
    from pokerlab import flop_checkdown_solver as solver
    trainer = (('native_train', native, 'train_native_fixed_street') if backend == 'native'
               else ('train_public_batched', solver, 'train_public_batched'))
    return [trainer, ('evaluate_profile', solver, 'evaluate_profile')]


def _solver_callable(item, game, algorithm, iterations, backend, build_directory):
    """Resolve imports and arguments before the complete-call timer starts."""
    if game == 'preflop':
        from pokerlab.preflop_checkdown_solver import solve_prepared_preflop_checkdown
        case = item['case']
        return lambda: solve_prepared_preflop_checkdown(
            item['table'], config=case['config'], iterations=iterations,
            algorithm=algorithm, resource_model='prepared-counts',
            world_indexing='pair-mean', training_backend=backend,
            build_directory=build_directory if backend == 'native' else None)
    from pokerlab.flop_checkdown_solver import solve_prepared_flop_checkdown
    case = item['case']
    return lambda: solve_prepared_flop_checkdown(
        item['table'], config=case['config'], iterations=iterations,
        algorithm=algorithm, training_backend=backend,
        build_directory=build_directory if backend == 'native' else None)


def _profile_call(item, game, algorithm, iterations, backend, build_directory,
                  trace_allocations=False):
    """Run a complete call; phase-wrapper setup/restore stays outside its timer."""
    gc.collect()
    targets = _phase_targets(game, backend, algorithm)
    solver_call = _solver_callable(item, game, algorithm, iterations, backend, build_directory)
    phase_seconds = {name: 0.0 for name, _, _ in targets}
    phase_calls = {name: 0 for name, _, _ in targets}
    rank_calls, result, encoded, error = {}, None, None, None
    payload_digest = None
    trace_current = trace_peak = None
    tracing_started = False
    stack = ExitStack()
    try:
        rank_calls = stack.enter_context(profile._rank_guard())
        phase_seconds, phase_calls = stack.enter_context(profile._PhaseContext(targets))
        if trace_allocations:
            tracemalloc.start()
            tracing_started = True
        started_at = datetime.now(timezone.utc).isoformat()
        started = perf_counter()
        try:
            result = solver_call()
            encoded = _canonical_bytes(result)
            payload_digest = _sha(encoded)
            if any(rank_calls.values()):
                raise AssertionError('Prepared call attempted card ranking/board enumeration')
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
        elapsed = perf_counter() - started
        ended_at = datetime.now(timezone.utc).isoformat()
        if tracing_started:
            trace_current, trace_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            tracing_started = False
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        started_at = ended_at = datetime.now(timezone.utc).isoformat()
        elapsed = 0.0
    finally:
        if tracing_started:
            trace_current, trace_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        stack.close()
    row = {'started_at_utc': started_at, 'ended_at_utc': ended_at,
           'complete_seconds': elapsed, 'phase_seconds': dict(phase_seconds),
           'phase_calls': dict(phase_calls),
           'uninstrumented_remainder_seconds': max(0.0, elapsed - sum(phase_seconds.values())),
           'rank_guard_calls': dict(rank_calls),
           'serialized_bytes_utf8': len(encoded) if encoded is not None else None,
           'payload_sha256': payload_digest}
    if trace_allocations:
        row['python_tracemalloc_current_bytes'] = trace_current
        row['python_tracemalloc_peak_bytes'] = trace_peak
    if result is not None:
        if encoded is not None:
            row['payload'] = result
        else:
            try:
                row['captured_payload_unvalidated_json'] = json.dumps(
                    result, sort_keys=True, separators=(',', ':'), allow_nan=True, default=repr)
            except Exception as exc:
                row['captured_payload_unvalidated_repr'] = repr(result)
                row['capture_error'] = f'{type(exc).__name__}: {exc}'
    if error is not None:
        row['error'] = error
    return row


def _trace_call(item, algorithm, iterations, backend, build_directory):
    row = _profile_call(item, 'preflop', algorithm, iterations, backend,
                        build_directory, trace_allocations=True)
    row['trace_scope'] = ('Python process allocations only. Native mode excludes child process, '
                          'native allocations, OS memory and RSS.')
    return row


def _phase_count_passed(game, backend, algorithm, row):
    if game == 'preflop':
        trainer = ('native_train' if backend == 'native' else
                   'train_cfrplus' if algorithm == 'cfrplus' else 'train_cfr')
        expected = {trainer: 1, 'evaluate': 1, 'best_response': 2}
    else:
        trainer = 'native_train' if backend == 'native' else 'train_public_batched'
        expected = {trainer: 1, 'evaluate_profile': 1}
    return row.get('phase_calls') == expected


def _metric_keys(game):
    return METRICS[game]


def _compare_payloads(game, python_payload, native_payload, spec):
    if type(python_payload) is not dict or type(native_payload) is not dict:
        raise ValueError('Both backend payloads are needed for comparison')
    metadata = native_payload.get('native_training')
    if type(metadata) is not dict or metadata.get('backend') != 'native-fixed-street-v1':
        raise ValueError('Native training provenance extension is missing or unsupported')
    if game == 'preflop':
        if (set(native_payload) != set(python_payload) | {'native_training', 'training_backend'}
                or 'training_backend' in python_payload or 'native_training' in python_payload
                or native_payload.get('training_backend') != 'native'):
            raise ValueError('Unexpected preflop backend payload extension')
    elif game == 'flop':
        if (set(native_payload) != set(python_payload) | {'native_training'}
                or 'native_training' in python_payload
                or python_payload.get('execution_backend') != 'public-batched-python'
                or native_payload.get('execution_backend') != 'native-fixed-street-v1'):
            raise ValueError('Unexpected flop backend payload extension')
    else:
        raise ValueError('Unsupported benchmark game')
    extensions = ({'native_training', 'training_backend'} if game == 'preflop'
                  else {'native_training', 'execution_backend'})
    left = {k: v for k, v in python_payload.items() if k not in extensions}
    right = {k: v for k, v in native_payload.items() if k not in extensions}
    for key in _metric_keys(game):
        left.pop(key, None); right.pop(key, None)
    lrows, rrows = left.pop('strategy', None), right.pop('strategy', None)
    if left != right:
        raise ValueError('Backend payloads differ outside declared scalars/policy probabilities')
    if type(lrows) is not list or type(rrows) is not list or len(lrows) != len(rrows):
        raise ValueError('Strategy row counts differ between backends')
    policy_gap = 0.0
    for lrow, rrow in zip(lrows, rrows):
        if ({k: v for k, v in lrow.items() if k != 'actions'}
                != {k: v for k, v in rrow.items() if k != 'actions'}):
            raise ValueError('Private information or public history differs between policies')
        la, ra = lrow.get('actions'), rrow.get('actions')
        if type(la) is not list or type(ra) is not list or len(la) != len(ra):
            raise ValueError('Legal action rows differ between backend policies')
        for actions in (la, ra):
            probabilities = []
            for action in actions:
                probability = action.get('probability') if type(action) is dict else None
                if (not _finite_number(probability)
                        or not 0.0 <= float(probability) <= 1.0):
                    raise ValueError('Policy probabilities must be finite numbers in [0, 1]')
                probabilities.append(float(probability))
            if not actions or abs(math.fsum(probabilities) - 1.0) > 1e-9:
                raise ValueError('Each policy action distribution must sum to one within 1e-9')
        for a, b in zip(la, ra):
            if ({k: v for k, v in a.items() if k != 'probability'}
                    != {k: v for k, v in b.items() if k != 'probability'}):
                raise ValueError('Legal action identity differs between backend policies')
            policy_gap = max(policy_gap, abs(float(a['probability']) - float(b['probability'])))
    metric_gaps = {}
    for key in _metric_keys(game):
        a, b = python_payload.get(key), native_payload.get(key)
        if (not _finite_number(a) or not _finite_number(b)):
            raise ValueError('Backend metric must be a finite number: ' + key)
        metric_gaps[key] = abs(float(a) - float(b))
    acceptance = spec['acceptance']
    return {'metric_absolute_gaps': metric_gaps,
            'maximum_metric_absolute_gap': max(metric_gaps.values(), default=0.0),
            'maximum_policy_probability_gap': policy_gap,
            'meets_metric_gate': max(metric_gaps.values(), default=0.0) <= acceptance['cross_backend_metric_absolute_tolerance'],
            'meets_policy_gate': policy_gap <= acceptance['cross_backend_policy_probability_absolute_tolerance']}


def _oracle_for(game, item):
    if game == 'preflop':
        return None
    from scripts.flop_checkdown_validation import prepare_oracle_from_counts
    case = item['case']
    return prepare_oracle_from_counts(case['board'], case['oop_range'], case['ip_range'],
                                      case['config'], item['counts'])


def _replay(game, item, payload, spec, oracle):
    tolerance = spec['acceptance']['independent_replay_tolerance']
    if game == 'preflop':
        from scripts.preflop_checkdown_validation import replay
        case = item['case']
        return replay(payload, case['sb_range'], case['bb_range'], case['config'],
                      item['counts'], tolerance=tolerance)
    from scripts.flop_checkdown_validation import replay
    return replay(payload, oracle, tolerance=tolerance)


def _replay_unique(game, item, samples, spec, errors, profile_id):
    oracle_error = None
    try:
        oracle = _oracle_for(game, item)
    except Exception as exc:
        oracle = None
        oracle_error = f'{type(exc).__name__}: {exc}'
    groups = {backend: {} for backend in BACKENDS}
    for sample in samples:
        digest = sample.get('payload_sha256')
        if digest and sample.get('payload') is not None:
            groups[sample['backend']].setdefault(digest, []).append(sample)
    output = {backend: [] for backend in BACKENDS}
    for backend, unique in groups.items():
        for digest, rows in unique.items():
            entry = {'payload_sha256': digest,
                     'applies_to_calls': [row.get('repeat', row.get('call_id', 'trace')) for row in rows]}
            try:
                if oracle_error is not None:
                    raise RuntimeError('Independent oracle construction failed: ' + oracle_error)
                entry['metrics'] = _replay(game, item, rows[0]['payload'], spec, oracle)
                gap = entry['metrics'].get('nash_conv')
                entry['target_nash_conv'] = gap
                entry['quality_passed'] = (type(gap) in (int, float)
                    and gap <= spec['acceptance']['target_nash_conv'] + spec['acceptance']['target_padding'])
                entry['status'] = 'passed'
            except Exception as exc:
                entry.update({'status': 'error', 'quality_passed': False,
                              'error': f'{type(exc).__name__}: {exc}'})
                errors.append({'profile': profile_id, 'backend': backend,
                               'payload_sha256': digest, 'phase': 'independent-replay',
                               'error': entry['error']})
            output[backend].append(entry)
    return output


def _run_profile(spec, game, item, case, build_directory, errors):
    algorithm, iterations = case['algorithm'], case['iterations']
    profile_id = f'{game}-{algorithm}-{iterations}'
    samples, paired = [], []
    for repeat in range(3):
        order = spec['pair_order'][repeat * 2:repeat * 2 + 2]
        pair = {}
        for backend in order:
            print(f'START {profile_id} repeat={repeat + 1} backend={backend}', flush=True)
            row = _profile_call(item, game, algorithm, iterations, backend, build_directory)
            row.update({'backend': backend, 'repeat': repeat + 1})
            row['phase_call_census_passed'] = _phase_count_passed(game, backend, algorithm, row)
            if row.get('error'):
                errors.append({'profile': profile_id, 'backend': backend,
                               'repeat': repeat + 1, 'error': row['error']})
            elif not row['phase_call_census_passed']:
                row['error'] = 'Unexpected top-level phase call census'
                errors.append({'profile': profile_id, 'backend': backend,
                               'repeat': repeat + 1, 'error': row['error']})
            samples.append(row)
            if row.get('payload') is not None:
                pair[backend] = row['payload']
            print(f'DONE {profile_id} repeat={repeat + 1} backend={backend} seconds={row["complete_seconds"]:.6f}', flush=True)
        if set(pair) == set(BACKENDS):
            try:
                paired.append({'repeat': repeat + 1,
                               **_compare_payloads(game, pair['python'], pair['native'], spec)})
            except Exception as exc:
                message = f'{type(exc).__name__}: {exc}'
                paired.append({'repeat': repeat + 1, 'error': message,
                               'meets_metric_gate': False, 'meets_policy_gate': False})
                errors.append({'profile': profile_id, 'repeat': repeat + 1,
                               'phase': 'backend-comparison', 'error': message})
        else:
            paired.append({'repeat': repeat + 1, 'error': 'Missing backend payload',
                           'meets_metric_gate': False, 'meets_policy_gate': False})

    replay_rows = _replay_unique(game, item, samples, spec, errors, profile_id)
    for comparison in paired:
        if not (comparison.get('meets_metric_gate') and comparison.get('meets_policy_gate')):
            errors.append({'profile': profile_id, 'repeat': comparison.get('repeat'),
                           'phase': 'backend-agreement',
                           'error': comparison.get('error', 'Cross-backend tolerance missed')})
    for row in samples:
        row['independent_replay_sha256'] = row.get('payload_sha256')
    medians = {}
    for backend in BACKENDS:
        backend_rows = [row for row in samples if row['backend'] == backend]
        medians[backend] = (statistics.median(row['complete_seconds'] for row in backend_rows)
                            if len(backend_rows) == 3 and all(not row.get('error') for row in backend_rows)
                            else None)
    ratio = (medians['python'] / medians['native']
             if medians['python'] is not None and medians['native'] else None)
    speed_pass = ratio is not None and ratio >= spec['acceptance']['minimum_python_over_native_median_ratio']
    if not speed_pass:
        errors.append({'profile': profile_id, 'phase': 'speed-gate',
                       'ratio_python_over_native': ratio,
                       'error': 'Observed complete-call speed ratio missed threshold'})
    quality = {}
    deterministic = {}
    for backend in BACKENDS:
        entries = replay_rows[backend]
        quality[backend] = bool(entries) and all(e.get('status') == 'passed' and e.get('quality_passed') for e in entries)
        backend_rows = [row for row in samples if row['backend'] == backend]
        deterministic[backend] = (len(backend_rows) == 3 and
                                  all(row.get('payload_sha256') is not None for row in backend_rows) and
                                  len({row.get('payload_sha256') for row in backend_rows}) == 1)
    for backend in BACKENDS:
        if not deterministic[backend]:
            errors.append({'profile': profile_id, 'backend': backend,
                           'phase': 'deterministic-policy',
                           'error': 'Repeated complete payloads differ within the same backend/profile'})
    is_mandatory = algorithm == spec['acceptance']['mandatory_quality_algorithm']
    if is_mandatory:
        for backend in BACKENDS:
            if not quality[backend]:
                errors.append({'profile': profile_id, 'backend': backend,
                               'phase': 'mandatory-quality', 'error': 'CFR+ independent NashConv target missed'})
    pinned_check = None
    prep = spec['preparation']
    if game == 'preflop' and algorithm == 'cfrplus' and iterations == 3000:
        expected = prep['preflop_profile_payload_sha256']
        observed = [row.get('payload_sha256') for row in samples if row['backend'] == 'python']
        pinned_check = {'expected': expected, 'observed': observed,
                        'passed': len(observed) == 3 and all(x == expected for x in observed)}
    if game == 'flop' and algorithm == 'cfrplus' and iterations == 4000:
        expected = prep['flop_profile_payload_sha256']
        observed = [row.get('payload_sha256') for row in samples if row['backend'] == 'python']
        pinned_check = {'expected': expected, 'observed': observed,
                        'passed': len(observed) == 3 and all(x == expected for x in observed)}
    if pinned_check is not None and not pinned_check['passed']:
        errors.append({'profile': profile_id, 'phase': 'pinned-profile-compatibility',
                       'error': 'Current Python payload differs from pinned PR141 output'})
    return {'profile_id': profile_id, 'game': game, 'algorithm': algorithm,
            'iterations': iterations, 'samples': samples, 'paired_comparisons': paired,
            'unique_policy_replays': replay_rows, 'deterministic_payloads': deterministic,
            'median_complete_seconds': medians,
            'observed_python_over_native_median_ratio': ratio,
            'speed_gate_passed': speed_pass,
            'independent_target_nash_conv_passed': quality,
            'mandatory_quality': is_mandatory,
            'pinned_reference_payload_check': pinned_check}


def _run_traces(spec, item, build_directory, errors):
    trace_spec = spec['traces']
    rows = {}
    for backend in trace_spec['backends']:
        print(f'START TRACE preflop-cfrplus-1000 backend={backend}', flush=True)
        row = _trace_call(item, trace_spec['algorithm'], trace_spec['iterations'],
                          backend, build_directory)
        row['backend'] = backend
        row['phase_call_census_passed'] = _phase_count_passed('preflop', backend,
                                                              trace_spec['algorithm'], row)
        if row.get('error'):
            errors.append({'phase': 'allocation-trace', 'backend': backend, 'error': row['error']})
        elif not row['phase_call_census_passed']:
            row['error'] = 'Unexpected trace phase call census'
            errors.append({'phase': 'allocation-trace', 'backend': backend, 'error': row['error']})
        rows[backend] = row
    if all(rows.get(backend, {}).get('payload') is not None for backend in BACKENDS):
        try:
            rows['cross_backend_comparison'] = _compare_payloads(
                'preflop', rows['python']['payload'], rows['native']['payload'], spec)
            if not (rows['cross_backend_comparison'].get('meets_metric_gate')
                    and rows['cross_backend_comparison'].get('meets_policy_gate')):
                raise ValueError('Trace cross-backend tolerance missed')
        except Exception as exc:
            message = f'{type(exc).__name__}: {exc}'
            rows['cross_backend_comparison'] = {'error': message}
            errors.append({'phase': 'allocation-trace-comparison', 'error': message})
    trace_samples = []
    for backend in BACKENDS:
        if backend in rows:
            rows[backend]['call_id'] = 'tracemalloc-preflop-cfrplus-1000'
            trace_samples.append(rows[backend])
    rows['independent_replays'] = _replay_unique(
        'preflop', item, trace_samples, spec, errors, 'trace-preflop-cfrplus-1000')
    return rows


def _build_identity(build_directory):
    from pokerlab import native_fixed_street as native
    directory = Path(build_directory).resolve(strict=True)
    if directory == ROOT or ROOT in directory.parents:
        raise ValueError('Native build directory must be outside the source checkout')
    executable, manifest = native._backend(directory)
    manifest_path = directory / 'native-train-manifest.json'
    return {'directory': str(directory), 'manifest': manifest,
            'manifest_sha256': _sha(manifest_path.read_bytes()),
            'executable_sha256': _sha(executable.read_bytes())}


def run(spec, build_directory):
    validate_spec(spec)
    errors, preflights, profiles, traces = [], [], [], {}
    before = after = build_before = build_after = None
    pinned_artifact = None
    items = {}
    try:
        pinned_artifact = _verify_profile_artifact(spec)
        before = _identity()
        _require_baseline_ancestor(before['revision'])
        if before['status']:
            raise ValueError('Benchmark requires clean committed source')
        items = _load_inputs(spec)
        for game, item in items.items():
            if len(item['table'].pairs) != spec[game]['compatible_pairs']:
                raise ValueError('Prepared compatible-pair count changed for ' + game)
        # Complete every profile/backend admission before checking the external
        # build manifest/executable or invoking either trainer.
        preflights = _preflight_all(spec, items)
        if any(row.get('status') != 'admitted' for row in preflights):
            raise ValueError('At least one complete Python/native profile admission was rejected; no build lookup or training was started')
        build_before = _build_identity(build_directory)
        for game in ('preflop', 'flop'):
            for case in spec[game]['profiles']:
                profiles.append(_run_profile(spec, game, items[game], case,
                                             build_directory, errors))
        traces = _run_traces(spec, items['preflop'], build_directory, errors)
        after = _identity()
        build_after = _build_identity(build_directory)
        if before != after:
            errors.append({'phase': 'source-integrity', 'error': 'Source, revision or status changed during run'})
        if build_before != build_after:
            errors.append({'phase': 'build-integrity', 'error': 'Native manifest or executable changed during run'})
    except Exception as exc:
        errors.append({'phase': 'runner', 'error': f'{type(exc).__name__}: {exc}'})
        try:
            if before is not None:
                after = _identity()
            if build_before is not None and build_directory is not None:
                build_after = _build_identity(build_directory)
        except Exception as nested:
            errors.append({'phase': 'final-identity', 'error': f'{type(nested).__name__}: {nested}'})

    all_admitted = len(preflights) == 6 and all(row.get('status') == 'admitted' for row in preflights)
    speed_pass = len(profiles) == 6 and all(row['speed_gate_passed'] for row in profiles)
    mandatory_quality = all(
        row['independent_target_nash_conv_passed'].get(backend, False)
        for row in profiles if row['mandatory_quality'] for backend in BACKENDS)
    agreement_pass = (len(profiles) == 6 and all(
        len(row['paired_comparisons']) == 3 and all(
            pair.get('meets_metric_gate') and pair.get('meets_policy_gate')
            for pair in row['paired_comparisons']) for row in profiles))
    replay_pass = len(profiles) == 6 and all(
        bool(row['unique_policy_replays'][backend]) and all(
            replay.get('status') == 'passed' for replay in row['unique_policy_replays'][backend])
        for row in profiles for backend in BACKENDS)
    source_unchanged = before is not None and before == after
    build_unchanged = build_before is not None and build_before == build_after
    mandatory_traces = (
        all(traces.get(backend, {}).get('payload') is not None for backend in BACKENDS)
        and traces.get('cross_backend_comparison', {}).get('meets_metric_gate')
        and traces.get('cross_backend_comparison', {}).get('meets_policy_gate')
        and all(traces.get('independent_replays', {}).get(backend)
                and all(x.get('status') == 'passed'
                        for x in traces['independent_replays'][backend])
                for backend in BACKENDS))
    if not mandatory_traces and profiles:
        errors.append({'phase': 'allocation-traces', 'error': 'Both separate preflop tracemalloc calls and parity check are required'})
    report = {'schema_version': 1, 'benchmark_id': spec['benchmark_id'],
              'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'specification': spec, 'spec_sha256': checksum(spec),
              'status': 'passed' if not errors else 'error', 'errors': errors,
              'source_before': before, 'source_after': after,
              'source_unchanged': source_unchanged,
              'pinned_profile_artifact': pinned_artifact,
              'physical_count_provenance': {
                  'preflop': items.get('preflop', {}).get('pinned_provenance'),
                  'flop': items.get('flop', {}).get('pinned_provenance')},
              'native_build_before': build_before, 'native_build_after': build_after,
              'native_build_unchanged': build_unchanged,
              'runtime': {'python': sys.version, 'executable': sys.executable,
                          'platform': __import__('platform').platform()},
              'preflights': preflights, 'all_six_preflights_passed': all_admitted,
              'profiles': profiles, 'separate_preflop_allocation_traces': traces,
              'gates': {'all_profiles_speed_threshold_passed': speed_pass,
                        'all_CFRplus_quality_targets_passed_both_backends': mandatory_quality,
                        'all_backend_metric_and_policy_agreement_passed': agreement_pass,
                        'all_unique_policies_replayed': replay_pass,
                        'both_traces_and_trace_parity_passed': mandatory_traces,
                        'vanilla_DCFR_quality_misses_reported_not_fatal': True},
              'method': {
                  'complete_call': 'Prepared solver invocation, canonical JSON UTF-8 serialization and payload SHA-256; loaders, replay and GC are outside timing.',
                  'pairing': 'Three complete calls per backend/profile; order alternates by repeat. All raw payloads, hashes, UTC intervals, coarse phases and failures are retained.',
                  'preflights': 'All six Python/reference and native complete-solve admission forecasts finish before native build manifest/executable lookup or any trainer call.',
                  'independent_replay': 'Pinned physical counts and independent numeric betting rules are used outside timed calls, once per distinct backend/profile payload hash.',
                  'traces': 'Separate preflop CFR+ 1,000-iteration Python/native calls. Python tracemalloc is Python-process-only; native subprocess memory and RSS are excluded.',
                  'scope': 'Two prepared finite games and the measured source-built binary/runtime only; observed speed ratios are not general speedup or convergence claims.'}}
    report['artifact_sha256'] = checksum(report)
    return report


def _atomic_json(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n',
                    encoding='utf-8', newline='\n')
    temp.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', required=True,
                        help='Explicit directory with native-train-manifest.json and executable')
    parser.add_argument('--output', type=Path,
                        default=ROOT.parent / 'native-fixed-street-v1-report.json',
                        help='Report path; default is outside the repository checkout')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error('Report output must be outside the repository checkout')
    spec = json.loads(SPEC_PATH.read_text(encoding='utf-8-sig'))
    report = run(spec, args.build_dir)
    _atomic_json(output, report)
    print(json.dumps({'status': report['status'],
                      'artifact_sha256': report['artifact_sha256'],
                      'errors': report['errors']}, sort_keys=True), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
