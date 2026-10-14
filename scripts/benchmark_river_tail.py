"""Same-trajectory original-weight CFR+ river tail experiment; research only.

Fixed experiment: two frozen river fixtures, both backends, D=3000/T=10000.
No production solver, trainer, admission guard or public API is changed.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import platform
import time
from unittest.mock import patch

from pokerlab import matrix_free_river, postflop_solver
from pokerlab.cards import cards, expand_range
from scripts.benchmark_turn_river_independent import CONFIG, ROOT, solve, source_hashes
from scripts.river_tail_realization import reconstruct_tail
from scripts.turn_river_validation import compare_result, replay_policy


DISCARD, TOTAL, TARGET = 3000, 10000, 0.001
BASELINE_REPORT = ROOT / 'benchmarks/results/river-cfrplus-accuracy-extension-v1.json'
BASELINE_POLICIES = ROOT / 'benchmarks/results/river-cfrplus-accuracy-policies-v1'
CASE_IDS = ('river-polarised-bluffcatcher', 'river-weighted-raises')
METRICS = ('value_oop', 'value_ip', 'oop_best_response_value',
           'ip_best_response_value', 'oop_best_response_gain',
           'ip_best_response_gain', 'nash_conv', 'exploitability')


def _copy_snapshot(profile, keys, infos):
    if set(profile) != set(keys):
        raise ValueError('Checkpoint information-set keys changed')
    result = {}
    for key in keys:
        if len(profile[key]) != infos[key]:
            raise ValueError('Checkpoint action count changed')
        result[key] = tuple(profile[key])
    return result


def _replay(result, case):
    return replay_policy(result, case['oop'], case['ip'],
                         board=case['board'], config=case['config'])


def _derived(result, kind, source_version, discard, total):
    result['source_solver_version'] = source_version
    result['solver_version'] = 'research-river-cfrplus-' + kind + '-v1'
    result['method'] = 'Development profile from same-run CFR+ average snapshots'
    result['diagnostic_provenance'] = 'Independent numeric-rule replay and legal BR'
    result['source_requested_iterations'] = total
    result['source_iteration_window'] = [1 if kind == 'prefix' else discard + 1,
                                          discard if kind == 'prefix' else total]
    result['averaged_sweeps'] = discard if kind == 'prefix' else total - discard
    # Tail training actually completed T sweeps; do not advertise T-D as cost.
    result['iterations'] = discard if kind == 'prefix' else total
    result['average_schedule'] = ('linear-prefix-own-reach' if kind == 'prefix'
                                  else 'original-linear-weight-tail-own-reach')
    result['scope'] = 'Research profile of the same configured fixed-board river game.'
    return result


def capture(case, backend, discard, total, interval=None):
    """Return full/prefix policies and evidence from ONE observational run.

    The full result is the unchanged production payload. Prefix diagnostics
    are independently derived. Resource metadata on the research prefix is
    inherited from admission of the full requested T call, explicitly recorded.
    """
    if (type(discard) is not int or type(total) is not int or
            not 1 <= discard < total <= TOTAL or total < 10):
        raise ValueError('Require integer 1 <= discard < total <= 10000 and total >= 10')
    interval = discard if interval is None else interval
    if type(interval) is not int or interval < 1 or discard % interval:
        raise ValueError('Positive integer interval must emit the discard checkpoint')
    if backend not in ('materialized', 'matrix-free') or len(cards(case['board'])) != 5:
        raise ValueError('Capture supports only the two fixed-board river backends')
    module, name = ((postflop_solver, 'train_public_batched') if backend == 'materialized'
                    else (matrix_free_river, 'train_ranked_river'))
    original = getattr(module, name)
    info_position = 2 if backend == 'materialized' else 1
    snapshots, callbacks, keys = {}, [], None
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls, keys
        calls += 1
        if calls != 1:
            raise ValueError('Expected exactly one fixed CFR+ trainer call')
        if (kwargs.get('checkpoint_interval') is not None or
                kwargs.get('checkpoint_callback') is not None):
            raise ValueError('Existing target/checkpoint mode is not observational capture')
        if args[info_position + 1] != total or args[info_position + 2] != 'cfrplus':
            raise ValueError('Unexpected trainer iteration budget or algorithm')
        infos = args[info_position]
        keys = tuple(sorted(infos))

        def checkpoint(iteration, profile):
            callbacks.append(iteration)
            if iteration in (discard, total):
                if iteration in snapshots:
                    raise ValueError('Duplicate requested checkpoint')
                snapshots[iteration] = _copy_snapshot(profile, keys, infos)
            return False

        kwargs.update(checkpoint_interval=interval, checkpoint_callback=checkpoint)
        return original(*args, **kwargs)

    started = time.perf_counter()
    with patch.object(module, name, observe):
        full = solve(case, backend, 'cfrplus', total)
    call_seconds = time.perf_counter() - started
    if calls != 1 or set(snapshots) != {discard, total}:
        raise ValueError('The same training run did not supply both requested snapshots')
    expected_callbacks = list(range(interval, total + 1, interval))
    if not expected_callbacks or expected_callbacks[-1] != total:
        expected_callbacks.append(total)
    if callbacks != expected_callbacks:
        raise ValueError('Unexpected completed-sweep callback schedule')

    # Production hand indices follow expand_range insertion order, including
    # possible holes from unsupported hands. Never sort the holding strings.
    hands = tuple(tuple(expand_range(case[side], cards(case['board'])))
                  for side in ('oop', 'ip'))
    if len(keys) != len(full['strategy']):
        raise ValueError('Information-set and serialized row counts differ')
    prefix = deepcopy(full)
    for key, row, prefix_row in zip(keys, full['strategy'], prefix['strategy']):
        player, hand_index, history = key
        identity = ('oop' if player == 0 else 'ip', ''.join(hands[player][hand_index]),
                    tuple(history))
        if (row['player'], row['hand'], tuple(row['history'])) != identity:
            raise ValueError('Serialized private-hand/history identity differs from trainer key')
        actual = tuple(action['probability'] for action in row['actions'])
        if actual != snapshots[total][key]:
            raise ValueError('Final callback differs from unchanged returned average')
        if len(actual) != len(snapshots[discard][key]):
            raise ValueError('Prefix action count differs from final legal row')
        for action, probability in zip(prefix_row['actions'], snapshots[discard][key]):
            action['probability'] = probability

    replay_started = time.perf_counter()
    full_oracle = _replay(full, case)
    full_differences = compare_result(full, full_oracle)
    prefix = _derived(prefix, 'prefix', full['solver_version'], discard, total)
    prefix_oracle = _replay(prefix, case)
    prefix.update({field: prefix_oracle[field] for field in METRICS})
    return full, prefix, {
        'callback_iterations': callbacks, 'trainer_calls': calls,
        'final_snapshot_exactly_matches_returned_profile': True,
        'complete_call_with_observations_seconds': call_seconds,
        'prefix_full_independent_replay_seconds': time.perf_counter() - replay_started,
        'full_scalar_differences': full_differences,
    }


def _baseline(case, backend, iterations, report):
    matches = [row for row in report['results'] if row['scenario'] == case['id']
               and row['backend'] == backend and row['iterations'] == iterations]
    if len(matches) != 1:
        raise ValueError('Expected exactly one frozen historical baseline')
    row = matches[0]
    payload = (BASELINE_POLICIES / row['policy_file']).read_bytes()
    if hashlib.sha256(payload).hexdigest() != row['policy_sha256']:
        raise ValueError('Historical policy bytes failed their recorded hash')
    return json.loads(payload)


def _hashes():
    result = source_hashes()
    paths = [ROOT / 'scripts' / name for name in (
        'river_tail_realization.py', 'benchmark_river_tail.py', 'river_analytical.py',
        'replay_river_accuracy_extension.py')]
    paths += [BASELINE_REPORT, *BASELINE_POLICIES.glob('*.json')]
    for path in paths:
        result[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _exact_json(value):
    if isinstance(value, Fraction):
        return str(value)
    raise TypeError('Unsupported evidence value: ' + type(value).__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--policies-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    historical = json.loads(BASELINE_REPORT.read_text(encoding='utf-8'))
    current = json.loads(CONFIG.read_text(encoding='utf-8'))['scenarios']
    cases = [next(case for case in current if case['id'] == case_id) for case_id in CASE_IDS]
    if cases != historical['fixtures']:
        raise ValueError('Current fixtures differ from the predeclared historical two-case set')
    before = _hashes()
    rows, captures = [], []
    args.policies_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        for backend in ('materialized', 'matrix-free'):
            full, prefix, evidence = capture(case, backend, DISCARD, TOTAL)
            if full != _baseline(case, backend, TOTAL, historical):
                raise ValueError('Observational full result differs from frozen complete baseline')
            if prefix['strategy'] != _baseline(case, backend, DISCARD, historical)['strategy']:
                raise ValueError('Captured prefix differs from frozen complete prefix strategy')
            conversion_started = time.perf_counter()
            exact_rows, ledger = reconstruct_tail(prefix['strategy'], full['strategy'], DISCARD, TOTAL)
            tail = _derived(deepcopy(full), 'tail', full['solver_version'], DISCARD, TOTAL)
            tail['strategy'] = exact_rows
            for row in tail['strategy']:
                for action in row['actions']:
                    action['probability'] = float(action['probability'])
            evidence['tail_conversion_seconds'] = time.perf_counter() - conversion_started
            tail_replay_started = time.perf_counter()
            tail_oracle = _replay(tail, case)
            tail.update({field: tail_oracle[field] for field in METRICS})
            evidence['tail_independent_replay_seconds'] = time.perf_counter() - tail_replay_started
            evidence.update(scenario=case['id'], backend=backend, correction_ledger=ledger,
                            full_payload_exactly_matches_frozen_baseline=True,
                            prefix_strategy_exactly_matches_frozen_baseline=True)
            captures.append(evidence)
            for kind, result in (('prefix', prefix), ('full', full), ('tail', tail)):
                payload = (json.dumps(result, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
                filename = f"{case['id']}-{backend}-{kind}.json"
                (args.policies_dir / filename).write_bytes(payload)
                actual = json.loads(payload)
                oracle = _replay(actual, case)
                delta = compare_result(actual, oracle)
                rows.append({
                    'scenario': case['id'], 'backend': backend, 'profile_kind': kind,
                    'algorithm': 'cfrplus', 'iterations': actual['iterations'],
                    'source_requested_iterations': TOTAL,
                    'source_iteration_window': ([1, DISCARD] if kind == 'prefix' else
                                                [DISCARD + 1, TOTAL] if kind == 'tail' else [1, TOTAL]),
                    'metrics': {field: oracle[field] for field in METRICS},
                    'diagnostic_origin': ('independent-replay-of-production' if kind == 'full'
                                          else 'independent-derived'),
                    'production_diagnostics_compared': kind == 'full',
                    'scalar_differences': delta, 'nash_conv_target': TARGET,
                    'target_met': oracle['nash_conv'] <= TARGET,
                    'verified_worlds': oracle['worlds'],
                    'verified_information_sets': oracle['checked_information_sets'],
                    'policy_file': filename, 'policy_sha256': hashlib.sha256(payload).hexdigest(),
                })
                print(case['id'], backend, kind, 'gap=', oracle['nash_conv'], flush=True)
    if _hashes() != before:
        raise RuntimeError('Source or frozen baseline changed during experiment; discard run')
    report = {
        'schema_version': 1, 'benchmark_id': 'river-cfrplus-tail-realization-v1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'python': platform.python_version(), 'platform': platform.platform(),
        'source_sha256': before, 'fixtures': cases, 'results': rows, 'captures': captures,
        'methodology': {
            'selection': 'Fixed existing two river fixtures x both backends; original-weight tail D3000/T10000, no adaptive selection or omitted cases.',
            'preconditions': 'Same-run post-sweep linear CFR+ averages, independently validated complete legal perfect-recall profiles; own-sequence realization subtraction.',
            'numerics': 'Exact binary64-to-Fraction row normalization and flow arithmetic; row/negative gate1e-12, complete reconstructed flow gate1e-11. Corrections/fallbacks explicitly recorded; no formal trainer rounding bound.',
            'diagnostics': 'Full production diagnostics compared independently. Prefix/tail diagnostics derived by independent numeric-rule replay and complete legal visible-information BR search; not independently compared production values.',
            'cost': 'T=10000 trained sweeps for each case including four observational snapshots; tail uses weights t over3001..10000, not max(t-D,0). Raw single-call/capture, conversion, replay times separate. No speedup, allocation/RSS or general convergence claim.',
            'scope': 'Research-only two synthetic finite river games; production/shared/earlier-street/Coach source unchanged. All target misses retained.',
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False,
                                      default=_exact_json) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
