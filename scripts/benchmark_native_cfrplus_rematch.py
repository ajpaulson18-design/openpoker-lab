"""Frozen old/new native CFR+ row-rematch complete-call comparison."""
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import gc
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
from time import perf_counter
from unittest.mock import patch

from pokerlab import native_fixed_street as native
from pokerlab.flop_checkdown_solver import solve_native_flop_checkdown
from scripts import benchmark_native_flop_preparation as cold
from scripts.benchmark_preflop_covered_counts import canonical, checksum
from scripts.flop_checkdown_validation import prepare_oracle_from_counts, replay

ROOT = cold.ROOT
SPEC = ROOT / 'benchmarks/native-cfrplus-rematch-v1.json'
SPEC_SHA = '72de646e268033049fb27e09173675634ac52610cb46014787ff63d25ff60f3f'


def load_spec():
    spec = json.loads(SPEC.read_bytes())
    if checksum(spec) != SPEC_SHA:
        raise ValueError('Requires frozen rematch specification')
    paired = json.loads((ROOT / spec['paired_spec_path']).read_bytes())
    if checksum(paired) != spec['paired_spec_sha256']:
        raise ValueError('Pinned cold-call specification changed')
    return spec, paired


def snapshot():
    result = cold.snapshot()
    raw = SPEC.read_bytes()
    result['source_hashes'][SPEC.relative_to(ROOT).as_posix()] = {
        'raw_sha256': hashlib.sha256(raw).hexdigest(),
        'lf_sha256': hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()}
    return result


@contextmanager
def historical_source(directory, spec):
    """Benchmark-only source binding for the explicitly pinned old executable."""
    manifest = json.loads((Path(directory) / 'native-train-manifest.json').read_bytes())
    raw = subprocess.check_output(['git', 'show', spec['baseline_commit'] + ':native/fixed_street_train.c'], cwd=ROOT)
    lf = raw.replace(b'\r\n', b'\n')
    forms = (lf, lf.replace(b'\n', b'\r\n'))
    if (manifest['source_lf_sha256'] != hashlib.sha256(lf).hexdigest()
            or manifest['source_lf_sha256'] != spec['baseline_source_lf_sha256']
            or [hashlib.sha256(x).hexdigest() for x in forms] != spec['baseline_source_raw_sha256_allowed']):
        raise ValueError('Historical trainer differs from pinned baseline')
    matching = [x for x in forms if hashlib.sha256(x).hexdigest() == manifest['source_sha256']]
    if not matching:
        raise ValueError('Historical trainer raw source identity cannot be reproduced')
    with tempfile.TemporaryDirectory(prefix='openpoker-rematch-baseline-') as folder:
        source = Path(folder) / 'fixed_street_train.c'
        source.write_bytes(matching[0])
        with patch.object(native, 'SOURCE', source):
            yield


def build_identity(directory):
    executable, manifest = native._backend(directory)
    return {'manifest': manifest,
            'manifest_sha256': hashlib.sha256((Path(directory) / 'native-train-manifest.json').read_bytes()).hexdigest(),
            'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest()}


def builds(old, new, count, spec):
    with historical_source(old, spec):
        baseline = build_identity(old)
    optimized = build_identity(new)
    stable = lambda row: {k: v for k, v in row['manifest'].items()
                         if k not in ('source_sha256', 'source_lf_sha256', 'executable_sha256')}
    if stable(baseline) != stable(optimized):
        raise ValueError('Paired trainers must use identical compiler/flags/protocol/work model')
    return {'baseline': baseline, 'optimized': optimized, 'counts': cold.count_build_identity(count)}


def game_payload(payload):
    result = cold.normalized(payload)
    result['native_training'].pop('build')
    return result


def measure(case, paired, lane, iterations, algorithm, count, train):
    gc.collect()
    started = perf_counter()
    payload = solve_native_flop_checkdown(
        paired['board'], case['oop_range'], case['ip_range'],
        count_build_directory=count, training_build_directory=train,
        config=paired['config'], iterations=iterations, algorithm=algorithm)
    raw = canonical(payload)
    digest = hashlib.sha256(raw).hexdigest()
    elapsed = perf_counter() - started
    return {'backend': lane, 'iterations': iterations, 'algorithm': algorithm,
            'elapsed_seconds': elapsed, 'payload_sha256': digest,
            'payload': json.loads(raw)}


def assess(sample, table, oracle, identities, spec, quality):
    payload = sample['payload']
    if hashlib.sha256(canonical(payload)).hexdigest() != sample['payload_sha256']:
        raise ValueError('Raw policy checksum changed')
    if type(sample['elapsed_seconds']) not in (int, float) or not 0 < sample['elapsed_seconds'] < 3600:
        raise ValueError('Invalid complete-call duration')
    if payload['iterations'] != sample['iterations'] or payload['algorithm'] != sample['algorithm']:
        raise ValueError('Sample requested training identity changed')
    meta = payload['native_training']
    if meta['build'] != identities[sample['backend']]['manifest']:
        raise ValueError('Sample trainer build identity changed')
    prep = payload['equity_preparation']
    if (prep['mode'] != 'native-cold-counts' or prep['current_rank_calls'] != len(table.pairs) * 1980
            or prep['current_unordered_board_evaluations'] != len(table.pairs) * 990
            or prep['source_inclusive_admission'] is not True):
        raise ValueError('Sample current cold-count work changed')
    cold.validate_native_metadata(prep['native_preparation'], table, identities['counts']['manifest'])
    if payload['pair_equities'] != cold.normalized(table.build()[1]):
        raise ValueError('Sample physical counts or globally weighted priors changed')
    checked = replay(payload, oracle, tolerance=spec['acceptance']['independent_metric_tolerance'])
    if quality and checked['nash_conv'] > spec['acceptance']['cfrplus_nash_conv_limit']:
        raise ValueError('Fixed CFR+ quality gate missed')
    return checked


def summarize(rows, spec, timed):
    if len(rows) != (6 if timed else 2):
        raise ValueError('Missing paired observations')
    expected = ['baseline', 'optimized', 'optimized', 'baseline', 'baseline', 'optimized'] if timed else ['baseline', 'optimized']
    if [r['backend'] for r in rows] != expected:
        raise ValueError('Frozen alternating pair order changed')
    if len({checksum(game_payload(r['payload'])) for r in rows}) != 1:
        raise ValueError('Old/new complete payloads differ beyond trainer build identity')
    if len({r['payload']['native_training']['output_sha256'] for r in rows}) != 1:
        raise ValueError('Old/new serialized native policy wire differs')
    medians = {b: statistics.median(r['elapsed_seconds'] for r in rows if r['backend'] == b)
               for b in ('baseline', 'optimized')}
    ratio = medians['baseline'] / medians['optimized']
    if timed and ratio < spec['acceptance']['minimum_complete_call_median_ratio']:
        raise ValueError('Frozen complete-call improvement gate missed')
    return {'median_seconds': medians, 'observed_ratio': ratio,
            'exact_policy_wire': True, 'same_payload_except_build': True}


def verify_saved(report):
    unsigned = dict(report); digest = unsigned.pop('artifact_sha256')
    spec, paired = load_spec()
    if (checksum(unsigned) != digest or report['status'] != 'passed' or report['errors']
            or report['specification'] != spec or report['spec_sha256'] != SPEC_SHA):
        raise ValueError('Saved checksum, specification or passed status changed')
    if (report['source_before'] != report['source_after'] or report['source_before']['status']
            or report['builds_before'] != report['builds_after']):
        raise ValueError('Saved source/build identity changed')
    identities = report['builds_before']
    source = report['source_before']['source_hashes']['native/fixed_street_train.c']
    for key in ('raw', 'lf'):
        if identities['optimized']['manifest']['source_' + ('sha256' if key == 'raw' else 'lf_sha256')] != source[key + '_sha256']:
            raise ValueError('Optimized source/build correspondence failed')
    baseline = identities['baseline']['manifest']
    if (baseline['source_lf_sha256'] != spec['baseline_source_lf_sha256']
            or baseline['source_sha256'] not in spec['baseline_source_raw_sha256_allowed']):
        raise ValueError('Saved baseline trainer differs from pinned Git source')
    stable = lambda row: {k: v for k, v in row['manifest'].items()
                         if k not in ('source_sha256', 'source_lf_sha256', 'executable_sha256')}
    if stable(identities['baseline']) != stable(identities['optimized']):
        raise ValueError('Saved paired compiler/protocol/work model changed')
    count_source = report['source_before']['source_hashes']['native/preflop_equity.c']
    count_manifest = identities['counts']['manifest']
    if (count_manifest['source_sha256'] != count_source['raw_sha256']
            or count_manifest['source_lf_sha256'] != count_source['lf_sha256']):
        raise ValueError('Count source/build correspondence failed')
    for identity in identities.values():
        if identity['executable_sha256'] != identity['manifest']['executable_sha256']:
            raise ValueError('Executable/manifest correspondence failed')
    if report['preflights'] != cold.preflights(paired):
        raise ValueError('Complete source-inclusive admissions changed')
    counts = cold.historical_counts(paired)
    if len(report['fixtures']) != len(paired['fixtures']):
        raise ValueError('Missing fixture')
    total = 0
    for recorded, case in zip(report['fixtures'], paired['fixtures']):
        if recorded['fixture_id'] != case['id']:
            raise ValueError('Fixture order/identity changed')
        table = cold.table_for(case, paired, counts)
        oracle = prepare_oracle_from_counts(paired['board'], case['oop_range'], case['ip_range'], paired['config'], counts)
        profiles = [('cfrplus', 4000, True)] + [(a, n, False) for a in spec['control_algorithms'] for n in spec['control_iterations']]
        if len(recorded['profiles']) != len(profiles):
            raise ValueError('Missing control/profile')
        for row, (algorithm, iterations, timed) in zip(recorded['profiles'], profiles):
            if row['algorithm'] != algorithm or row['iterations'] != iterations or row['timed'] is not timed:
                raise ValueError('Profile/checkpoint identity changed')
            for sample in row['samples']:
                if sample['algorithm'] != algorithm or sample['iterations'] != iterations:
                    raise ValueError('Sample/profile mismatch')
                checked = assess(sample, table, oracle, identities, spec, timed)
                if sample['independent_replay'] != cold.normalized(checked):
                    raise ValueError('Saved independent replay summary changed')
                total += 1
            if row['summary'] != summarize(row['samples'], spec, timed):
                raise ValueError('Saved median/parity summary changed')
    return {'policies_replayed': total, 'passed': True}


def run(old, new, count):
    spec, paired = load_spec()
    report = {'schema_version': 1, 'benchmark_id': spec['benchmark_id'], 'specification': spec,
              'spec_sha256': SPEC_SHA, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'runtime': {'python': platform.python_version(), 'platform': platform.platform()},
              'source_before': snapshot(), 'fixtures': [], 'errors': []}
    try:
        if report['source_before']['status']:
            raise ValueError('Freeze committed clean source before measurement')
        subprocess.run(['git', 'merge-base', '--is-ancestor', spec['baseline_commit'], 'HEAD'], cwd=ROOT, check=True)
        report['preflights'] = cold.preflights(paired)
        counts = cold.historical_counts(paired)
        report['builds_before'] = builds(old, new, count, spec)
        for case in paired['fixtures']:
            table = cold.table_for(case, paired, counts)
            oracle = prepare_oracle_from_counts(paired['board'], case['oop_range'], case['ip_range'], paired['config'], counts)
            fixture = {'fixture_id': case['id'], 'profiles': []}; report['fixtures'].append(fixture)
            profiles = [('cfrplus', 4000, True)] + [(a, n, False) for a in spec['control_algorithms'] for n in spec['control_iterations']]
            for algorithm, iterations, timed in profiles:
                row = {'algorithm': algorithm, 'iterations': iterations, 'timed': timed, 'samples': []}
                fixture['profiles'].append(row)
                order = ['baseline', 'optimized', 'optimized', 'baseline', 'baseline', 'optimized'] if timed else ['baseline', 'optimized']
                for lane in order:
                    if lane == 'baseline':
                        with historical_source(old, spec):
                            sample = measure(case, paired, lane, iterations, algorithm, count, old)
                    else:
                        sample = measure(case, paired, lane, iterations, algorithm, count, new)
                    row['samples'].append(sample)
                    try:
                        sample['independent_replay'] = cold.normalized(assess(sample, table, oracle, report['builds_before'], spec, timed))
                    except Exception as exc:
                        sample['assessment_error'] = f'{type(exc).__name__}: {exc}'
                        report['errors'].append(case['id'] + ': ' + sample['assessment_error'])
                try:
                    row['summary'] = summarize(row['samples'], spec, timed)
                except Exception as exc:
                    row['summary_error'] = f'{type(exc).__name__}: {exc}'
                    report['errors'].append(case['id'] + ': ' + row['summary_error'])
    except Exception as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
    finally:
        report['source_after'] = snapshot()
        if 'builds_before' in report:
            try:
                report['builds_after'] = builds(old, new, count, spec)
            except Exception as exc:
                report['errors'].append(f'Final build check: {type(exc).__name__}: {exc}')
        if report['source_before'] != report['source_after'] or report.get('builds_before') != report.get('builds_after'):
            report['errors'].append('Source or build identity changed during measurement')
    report['status'] = 'error' if report['errors'] else 'passed'
    report['artifact_sha256'] = checksum(report)
    if report['status'] == 'passed':
        try:
            report['saved_verification'] = verify_saved(report)
        except Exception as exc:
            report['errors'].append(f'Saved replay: {type(exc).__name__}: {exc}')
            report['status'] = 'error'
        report.pop('artifact_sha256'); report['artifact_sha256'] = checksum(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-build-dir', required=True)
    parser.add_argument('--optimized-build-dir', required=True)
    parser.add_argument('--count-build-dir', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents or output.exists():
        parser.error('Use a new report path outside the checkout')
    report = run(args.baseline_build_dir, args.optimized_build_dir, args.count_build_dir)
    cold.identity.base._write(output, report)
    print(json.dumps({'status': report['status'], 'errors': report['errors'], 'artifact_sha256': report['artifact_sha256']}), flush=True)
    raise SystemExit(0 if report['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
