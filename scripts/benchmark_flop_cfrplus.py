"""Frozen CFR+ comparison on the independently authenticated full-future flop game."""
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import traceback

from scripts import benchmark_weighted_full_deck_flop as base
from scripts.benchmark_preflop_covered_counts import checksum
from pokerlab.public_cfr import MAX_PREFIX_EDGES

ROOT = base.ROOT
SPEC = ROOT / 'benchmarks/weighted-full-deck-flop-cfrplus-v1.json'
SPEC_SHA = '035b8c8732741311a7166163516cd710c4471c1fe4776c67b0c00441db618461'
BASELINE_SOURCE_SHA = '8a482058567a779d3c781cb7a72f795c918898ecc01cdffe5fd91093582006b5'


def load_spec():
    spec = json.loads(SPEC.read_bytes())
    if checksum(spec) != SPEC_SHA:
        raise ValueError('Requires the frozen full-future flop CFR+ protocol')
    return spec


def snapshot():
    state = base.snapshot()
    raw = SPEC.read_bytes()
    state['source_hashes'][SPEC.relative_to(ROOT).as_posix()] = {
        'raw_sha256': hashlib.sha256(raw).hexdigest(),
        'lf_sha256': hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()}
    return state


def preflight(spec):
    structural = deepcopy(spec)
    structural['expected'].pop('training_passes_per_iteration')
    structural['expected'].pop('public_prefix_hand_edges')
    structural['expected']['max_world_node_iterations'] //= 3
    result = base.preflight(structural)
    result['training_passes_per_iteration'] = 3
    result['max_world_node_iterations'] *= 3
    _, _, worlds = base.geometry(spec)
    # Coordinates only: reserve public prefix/private-pair edges without ranks.
    edges = {(w[0], w[1], tuple(w[4:4+length])) for w in worlds for length in range(3)}
    result['public_prefix_hand_edges'] = len(edges)
    if (result['max_world_node_iterations'] > base.production._MAX_WORLD_NODE_WORK
            or len(edges) > MAX_PREFIX_EDGES):
        raise ValueError('Complete three-pass CFR+ request exceeds an unchanged solver cap')
    if any(result[key] != value for key, value in spec['expected'].items()
           if key not in ('pair_priors', 'raw_joint_weight_normalizer')):
        raise ValueError('Frozen CFR+ rank-free census changed')
    return result


def check_baseline_identity(report, spec):
    source = report['source_before']
    if (report['spec_sha256'] != spec['baseline_spec_sha256']
            or source['revision'] != spec['baseline_commit']
            or source != report['source_after'] or source['status']
            or checksum(source['source_hashes']) != BASELINE_SOURCE_SHA):
        raise ValueError('Requires the authenticated frozen full-deck baseline source')


def verify_baseline(directory, spec):
    directory = Path(directory)
    path = directory / 'index.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4*1024*1024:
        raise ValueError('Invalid bounded baseline index')
    raw = path.read_bytes()
    report = json.loads(raw)
    check_baseline_identity(report, spec)
    verified = base.verify_saved(directory, require_quality=False)
    if (directory / 'index.json').read_bytes() != raw:
        raise ValueError('Baseline index changed during independent reconstruction')
    return {'index_raw_sha256': hashlib.sha256(raw).hexdigest(),
            'artifact_sha256': report['artifact_sha256'], 'source_revision': spec['baseline_commit'],
            'source_hashes_sha256': BASELINE_SOURCE_SHA, 'verification': verified,
            'quality_gate_met': report['quality_gate_met'], 'final_quality': report['final_quality']}


def check_candidate(payload, row):
    public = row['traversal'] == 'public-batched'
    if (payload['algorithm'] != 'cfrplus' or payload['iterations'] != row['iterations']
            or payload['execution_backend'] != row['traversal']+'-python'
            or payload['plan_operation_limit'] is not None
            or payload['public_batch_edge_limit'] != (MAX_PREFIX_EDGES if public else None)
            or payload['training_passes_per_iteration'] != 3
            or payload['update_schedule'] != 'alternating-oop-then-ip'
            or payload['average_schedule'] != 'linear-post-sweep-own-reach'):
        raise ValueError('Saved requested CFR+ execution identity changed')


def summarize(directory, samples, spec):
    expected = [('cfrplus', n, t, r) for n in spec['iterations']
                for r, order in enumerate(spec['pair_orders'], 1) for t in order]
    if [(r['algorithm'], r['iterations'], r['traversal'], r['repeat']) for r in samples] != expected:
        raise ValueError('Frozen CFR+ paired order/census changed')
    summary, quality = [], []
    for n in spec['iterations']:
        item = {'iterations': n, 'backends': {}}
        policies = []
        for t in spec['traversals']:
            rows = [r for r in samples if (r['iterations'], r['traversal']) == (n, t)]
            if len(rows) != 3 or len({r['payload_sha256'] for r in rows}) != 1:
                raise ValueError('CFR+ complete per-profile repeats are not exact')
            payload = base.read_payload(directory, rows[0]); check_candidate(payload, rows[0])
            # Authenticate this metadata above, then normalize only its expected backend difference.
            policies.append(dict(payload, public_batch_edge_limit=None))
            nc = rows[0]['independent_replay']['nash_conv']
            met = nc <= spec['acceptance']['final_nash_conv_chip_limit']
            item['backends'][t] = {'median_complete_seconds': statistics.median(r['elapsed_seconds'] for r in rows),
                                   'nash_conv': nc, 'quality_target_met': met,
                                   'payload_sha256': rows[0]['payload_sha256']}
            if n == spec['iterations'][-1]:
                quality.append({'algorithm': 'cfrplus', 'traversal': t, 'nash_conv': nc,
                                'target': spec['acceptance']['final_nash_conv_chip_limit'], 'met': met})
        item['cross_backend'] = base._cross_compare(*policies, spec)
        summary.append(item)
    return summary, quality


def verify_saved(directory, baseline_directory, *, require_quality=False):
    directory = Path(directory); path = directory / 'index.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4*1024*1024:
        raise ValueError('Invalid bounded CFR+ index')
    report = json.loads(path.read_bytes()); unsigned = dict(report); digest = unsigned.pop('artifact_sha256')
    spec = load_spec()
    if (checksum(unsigned) != digest or report['specification'] != spec
            or report['spec_sha256'] != SPEC_SHA or report['validation_errors']):
        raise ValueError('Saved CFR+ checksum/specification/validation failed')
    if report['source_before'] != report['source_after'] or report['source_before']['status']:
        raise ValueError('Candidate source was not frozen clean')
    if report['baseline'] != verify_baseline(baseline_directory, spec):
        raise ValueError('Pinned completed baseline evidence changed')
    if report['preflight'] != preflight(spec):
        raise ValueError('Saved CFR+ complete admission changed')
    records = [report['oracle_physical_evidence'], report['production_physical_evidence'],
               *report['samples'], *report['separate_allocation_calls']]
    names = [r['file'] for r in records]
    if len(names) != 22 or len(set(names)) != 22 or {p.name for p in directory.iterdir()} != set(names) | {'index.json'}:
        raise ValueError('Missing, duplicate or unindexed CFR+ evidence')
    oracle, calls = base.prepare_reference(spec)
    if calls != report['oracle_forbidden_production_calls']:
        raise ValueError('Saved oracle producer-call audit changed')
    if base.read_payload(directory, report['oracle_physical_evidence'])['worlds'] != base._world_projection(oracle['worlds']):
        raise ValueError('Saved independent ordered physical worlds changed')
    base._check_physical_record(base.read_payload(directory, report['production_physical_evidence']), oracle, spec)
    for row in report['samples'] + report['separate_allocation_calls']:
        payload = base.read_payload(directory, row); check_candidate(payload, row)
        start = datetime.fromisoformat(row['started_at_utc']); end = datetime.fromisoformat(row['finished_at_utc'])
        if start.tzinfo is None or end.tzinfo is None or end < start:
            raise ValueError('Invalid UTC observation boundaries')
        checked, guarded = base.assess(payload, oracle, spec)
        if checked != row['independent_replay'] or guarded != row['forbidden_production_calls']:
            raise ValueError('Saved independent replay summary changed')
        if row['kind'] == 'timed':
            value = row['elapsed_seconds']
            if type(value) not in (int, float) or not 0 < value < 86400:
                raise ValueError('Invalid complete-call observation')
        elif row['kind'] == 'allocation':
            value = row['python_traced_peak_bytes']
            if type(value) is not int or value <= 0:
                raise ValueError('Invalid separate allocation observation')
        else:
            raise ValueError('Unknown observation kind')
    if [(r['kind'], r['algorithm'], r['iterations'], r['traversal']) for r in report['separate_allocation_calls']] != [
            ('allocation', 'cfrplus', 10, t) for t in spec['traversals']]:
        raise ValueError('Missing separate CFR+ allocation call')
    if any(r['kind'] != 'timed' for r in report['samples']):
        raise ValueError('Timing rows must be complete untraced calls')
    summary, quality = summarize(directory, report['samples'], spec)
    met = all(q['met'] for q in quality)
    if (report['summary'] != summary or report['final_quality'] != quality
            or report['quality_gate_met'] is not met
            or report['status'] != ('passed' if met else 'quality-miss')):
        raise ValueError('Saved CFR+ timing/parity/original quality status changed')
    if require_quality and not met:
        raise ValueError('Original final quality target remains unmet')
    return {'policies_replayed': 20, 'worlds_reenumerated': len(oracle['worlds']),
            'independent_validation_passed': True, 'quality_gate_met': met}


def run(directory, baseline_directory, *, execution_state=None):
    directory = Path(directory).resolve(); baseline_directory = Path(baseline_directory).resolve()
    if baseline_directory in directory.parents:
        raise ValueError('Candidate output must be outside immutable baseline evidence')
    if directory == ROOT or ROOT in directory.parents or directory.exists():
        raise ValueError('Use a new evidence directory outside the source checkout')
    spec = load_spec(); before = snapshot()
    report = {'schema_version': 1, 'benchmark_id': spec['benchmark_id'],
              'specification': spec, 'spec_sha256': SPEC_SHA, 'source_before': before,
              'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'runtime': {'python': platform.python_version(), 'platform': platform.platform()},
              'execution_state': execution_state or {'mode': 'direct-call', 'system_required': False},
              'samples': [], 'separate_allocation_calls': [], 'validation_errors': []}
    directory.mkdir(parents=False, exist_ok=False)
    try:
        if before['status']:
            raise ValueError('Commit a clean frozen candidate source before measurement')
        subprocess.run(['git', 'merge-base', '--is-ancestor', spec['baseline_commit'], 'HEAD'], cwd=ROOT, check=True)
        report['active_phase'] = 'complete-rank-free-admission'; report['preflight'] = preflight(spec)
        report['active_phase'] = 'completed-baseline-reconstruction'
        report['baseline'] = verify_baseline(baseline_directory, spec)
        report['active_phase'] = 'independent-physical-preparation'
        oracle, calls = base.prepare_reference(spec); report['oracle_forbidden_production_calls'] = calls
        report['oracle_physical_evidence'] = base.store_payload(directory, 'independent-physical-worlds.json.gz',
                                                              {'worlds': base._world_projection(oracle['worlds'])})
        report['production_physical_evidence'] = base.store_payload(directory, 'production-physical-worlds.json.gz',
                                                                  base.compare_physical_worlds(spec, oracle))
        for iterations in spec['iterations']:
            for repeat, order in enumerate(spec['pair_orders'], 1):
                for traversal in order:
                    report['active_phase'] = 'timed-call'
                    report['active_request'] = {'algorithm': 'cfrplus', 'iterations': iterations,
                                                'traversal': traversal, 'repeat': repeat}
                    base._write_index(directory, report)
                    row = base.timed_call(spec, directory, oracle, 'cfrplus', traversal, iterations, repeat)
                    report['samples'].append(row)
                    if 'replay_error' in row:
                        report['validation_errors'].append(row['file']+': '+row['replay_error'])
                    base._write_index(directory, report)
                    print(json.dumps({'event': 'sample', **report['active_request'],
                                      'elapsed_seconds': row['elapsed_seconds'],
                                      'nash_conv': row.get('independent_replay', {}).get('nash_conv'),
                                      'replay_error': row.get('replay_error')}), flush=True)
        for traversal in spec['traversals']:
            report['active_phase'] = 'separate-allocation-call'; report['active_request'] = {'traversal': traversal}
            base._write_index(directory, report)
            row = base.allocation_call(spec, directory, oracle, traversal)
            report['separate_allocation_calls'].append(row)
            if 'replay_error' in row:
                report['validation_errors'].append(row['file']+': '+row['replay_error'])
            base._write_index(directory, report)
            print(json.dumps({'event': 'allocation', 'traversal': traversal,
                              'python_traced_peak_bytes': row['python_traced_peak_bytes']}), flush=True)
        if not report['validation_errors']:
            report['summary'], report['final_quality'] = summarize(directory, report['samples'], spec)
            report['quality_gate_met'] = all(r['met'] for r in report['final_quality'])
        report.pop('active_phase', None); report.pop('active_request', None)
    except Exception as exc:
        report['validation_errors'].append(f'{type(exc).__name__}: {exc}')
        report['failure_traceback'] = traceback.format_exc()
    finally:
        report['source_after'] = snapshot(); report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        if before != report['source_after']:
            report['validation_errors'].append('Candidate source changed during experiment')
        report['status'] = ('error' if report['validation_errors'] else
                            'passed' if report['quality_gate_met'] else 'quality-miss')
        base._write_index(directory, report)
    if report['status'] != 'error':
        try:
            report['saved_verification'] = verify_saved(directory, baseline_directory)
        except Exception as exc:
            report['validation_errors'].append('Saved replay: '+f'{type(exc).__name__}: {exc}')
            report['status'] = 'error'
        base._write_index(directory, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--baseline-directory', type=Path, required=True)
    args = parser.parse_args()
    with base.measurement_execution_state() as execution_state:
        report = run(args.output_directory, args.baseline_directory, execution_state=execution_state)
    print(json.dumps({'status': report['status'], 'artifact_sha256': report['artifact_sha256'],
                      'validation_errors': report['validation_errors'],
                      'final_quality': report.get('final_quality', [])}), flush=True)
    raise SystemExit(0 if report['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
