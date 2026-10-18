"""Repeat the frozen six-profile experiment after public-batched C reduction.

Retains the original failed report and every original gate/profile/timing rule.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
from scripts import benchmark_native_fixed_street as base

ROOT = base.ROOT
SPEC_PATH = ROOT / 'benchmarks' / 'native-fixed-street-vector-v1.json'
EXPECTED_SPEC_SHA256 = '99baef6f53b5e1ed84abc69149dcae87faf00852089b9662b300bd30ac7f318c'


def validate_spec(spec):
    if type(spec) is not dict or base.checksum(spec) != EXPECTED_SPEC_SHA256:
        raise ValueError('Public-batched followup requires its exact frozen specification')
    return spec


def _initial_identity(spec):
    commit, path = spec['initial_report_commit'], spec['initial_report_path']
    blob = base._git('rev-parse', f'{commit}:{path}')
    current = base._git('rev-parse', f'HEAD:{path}')
    raw = subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT)
    local = (ROOT / path).read_bytes()
    if blob != spec['initial_report_blob'] or current != blob:
        raise ValueError('Initial failed report Git identity changed')
    # Checkout newline conversion is not a mathematical artifact change.
    if raw.replace(b'\r\n', b'\n') != local.replace(b'\r\n', b'\n'):
        raise ValueError('Initial failed report working copy changed')
    artifact = json.loads(raw)
    unsigned = dict(artifact); unsigned.pop('artifact_sha256', None)
    digest = artifact.get('artifact_sha256')
    if (digest != spec['initial_report_artifact_sha256']
            or base.checksum(unsigned) != digest or artifact.get('status') != 'error'):
        raise ValueError('Initial failed report checksum/status changed')
    return {'commit': commit, 'path': path, 'git_blob': blob,
            'artifact_sha256': digest, 'raw_sha256': base._sha(local)}


def _reduction_census(report, spec):
    checked = []
    for row in report.get('profiles', []):
        game = row['game']
        for sample in row['samples']:
            if sample['backend'] == 'native':
                checked.append((game, sample.get('payload')))
    trace = report.get('separate_preflop_allocation_traces', {}).get('native', {})
    if trace.get('payload') is not None:
        checked.append(('preflop', trace['payload']))
    if len(checked) != 19:
        raise ValueError('Followup requires all 18 native timed policies and the separate trace')
    for game, payload in checked:
        metadata = payload.get('native_training', {})
        build = metadata.get('build', {})
        if (metadata.get('reduction') != spec['reductions'][game]
                or build.get('protocol') != spec['protocol']
                or build.get('work_model') != spec['work_model']):
            raise ValueError('Followup payload reduction/build identity differs from frozen plan')
    return {'native_timed_and_trace_payloads_checked': len(checked),
            'reductions': spec['reductions'], 'passed': True}


def run(spec, build_directory):
    validate_spec(spec)
    before = _initial_identity(spec)
    paired = json.loads((ROOT / spec['paired_spec_path']).read_text(encoding='utf-8'))
    if base.checksum(paired) != spec['paired_spec_sha256']:
        raise ValueError('Original paired specification changed')
    report = base.run(paired, build_directory)
    report.pop('artifact_sha256', None)
    report['benchmark_id'] = spec['benchmark_id']
    report['followup_specification'] = spec
    report['followup_spec_sha256'] = base.checksum(spec)
    report['initial_failed_report_before'] = before
    try:
        after = _initial_identity(spec)
        report['initial_failed_report_after'] = after
        if before != after:
            raise ValueError('Initial report changed during the followup')
        report['reduction_census'] = _reduction_census(report, spec)
    except Exception as exc:
        report['errors'].append({'phase': 'followup-integrity',
                                 'error': f'{type(exc).__name__}: {exc}'})
    report['status'] = 'error' if report['errors'] else 'passed'
    report['artifact_sha256'] = base.checksum(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', required=True)
    parser.add_argument('--output', type=Path,
                        default=ROOT.parent / 'native-fixed-street-vector-v1-report.json')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error('Report output must be outside the repository checkout')
    spec = json.loads(SPEC_PATH.read_text(encoding='utf-8'))
    report = run(spec, args.build_dir)
    base._atomic_json(output, report)
    print(json.dumps({'status': report['status'], 'artifact_sha256': report['artifact_sha256'],
                      'errors': report['errors']}, sort_keys=True), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
