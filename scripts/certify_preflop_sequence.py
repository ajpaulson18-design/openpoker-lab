"""Freeze and independently verify a finite physical-count preflop witness.

Default runs require clean committed source. Feasibility runs retain dirty-source
identity explicitly and never qualify as a published formal witness.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / 'benchmarks' / 'preflop-weighted-sequence-v1.json'
EXPECTED_SPEC_SHA256 = '5b4a79d0239a42c3911928b0ca5d0f53a54be228e68c62ad9a5f8a2925719fb3'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def checksum(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_spec(spec):
    if type(spec) is not dict or checksum(spec) != EXPECTED_SPEC_SHA256:
        raise ValueError('Exact preflop witness requires the frozen specification')
    return spec


def _git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def _snapshot():
    paths = {ROOT / 'AGENTS.md', SPEC_PATH,
             ROOT / 'tests' / 'fixtures' / 'preflop-weighted-sequence-candidate-v1.json'}
    for folder in ('pokerlab', 'scripts', 'tests'):
        paths.update((ROOT / folder).rglob('*.py'))
    paths.update((ROOT / 'docs').rglob('*.md'))
    paths.update(ROOT / 'benchmarks' / 'results' /
                 f'preflop-push-fold-v1-oracle-pair-{index}.json' for index in range(3))
    hashes = {}
    for path in sorted(paths):
        raw = path.read_bytes()
        hashes[path.relative_to(ROOT).as_posix()] = {
            'raw_sha256': hashlib.sha256(raw).hexdigest(),
            'lf_sha256': hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()}
    return {'revision': _git('rev-parse', 'HEAD'),
            'status': _git('status', '--porcelain', '--untracked-files=all').splitlines(),
            'source_hashes': hashes}


@contextmanager
def _guards():
    from pokerlab import cards, preflop_full_board_equity as equity
    from pokerlab import preflop_tree, cfr, cfr_plus, public_cfr, native_fixed_street
    targets = (
        ('cards_rank_hand', cards, 'rank_hand'),
        ('preflop_rank_hand', equity, 'rank_hand'),
        ('board_enumeration', equity, '_board_combinations'),
        ('production_tree', preflop_tree, 'build_preflop_tree'),
        ('production_train', cfr, 'train'),
        ('production_cfrplus', cfr_plus, 'train'),
        ('production_evaluate', cfr, 'evaluate'),
        ('production_best_response', cfr, 'best_response'),
        ('production_vector_train', public_cfr, 'train_public_batched'),
        ('production_native_train', native_fixed_street, 'train_native_fixed_street'))
    calls = {name: 0 for name, _, _ in targets}
    def forbidden(name):
        def fail(*args, **kwargs):
            calls[name] += 1
            raise AssertionError('Exact witness called forbidden entry point: ' + name)
        return fail
    with ExitStack() as stack:
        for name, owner, attribute in targets:
            stack.enter_context(patch.object(owner, attribute, forbidden(name)))
        yield calls


def _components():
    # Resolve candidate imports inside the guards, including copied aliases.
    from scripts import preflop_sequence_equilibrium as candidate
    from scripts import verify_preflop_sequence as independent
    return candidate, independent


def _pure_check(witness):
    from scripts.preflop_sequence_pure_response import public_pure_response
    return public_pure_response(witness)


def _finish(report):
    report.pop('artifact_sha256', None)
    report['status'] = 'error' if report['errors'] else 'passed'
    report['artifact_sha256'] = checksum(report)
    return report


def run(spec, *, feasibility=False):
    validate_spec(spec)
    report = {'schema_version': 1, 'benchmark_id': spec['benchmark_id'],
              'phase': 'feasibility-only' if feasibility else 'formal-exact-equilibrium-witness',
              'formal_source_required': not feasibility,
              'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'specification': spec, 'spec_sha256': checksum(spec),
              'source_before': None, 'source_after': None, 'source_unchanged': False,
              'candidate_witness': None, 'independent_verification': None,
              'serialized_witness_verification': None,
              'exhaustive_pure_response_verification': None, 'guard_calls': {}, 'errors': [],
              'runtime': {'python': sys.version, 'executable': sys.executable,
                          'platform': platform.platform()},
              'scope': spec['scope']}
    started = perf_counter()
    try:
        before = report['source_before'] = _snapshot()
        if not feasibility and before['status']:
            raise ValueError('Formal witness requires clean committed source')
        result = subprocess.run(['git', 'merge-base', '--is-ancestor',
                                 spec['baseline_commit'], before['revision']],
                                cwd=ROOT, capture_output=True, check=False)
        if result.returncode:
            raise ValueError('Witness baseline is not an ancestor of the recorded source')
        with _guards() as calls:
            report['guard_calls'] = calls
            candidate, independent = _components()
            model = candidate.build_model(spec)
            witness = candidate.solve_model(model)
            report['candidate_witness'] = witness
            if type(witness) is not dict or witness.get('status') != 'exact-candidate-feasibility':
                raise ValueError('Candidate did not return a successful rational witness')
            report['independent_verification'] = independent.verify_certificate(witness)
            summary = report['independent_verification']
            if type(summary) is not dict or summary.get('status') != 'passed':
                raise ValueError('Independent verifier did not return a successful check')
            restored = json.loads(canonical(witness))
            report['serialized_witness_verification'] = independent.verify_certificate(restored)
            if report['independent_verification'] != report['serialized_witness_verification']:
                raise ValueError('Fresh serialized witness verification changed')
            report['exhaustive_pure_response_verification'] = _pure_check(restored)
            pure = report['exhaustive_pure_response_verification']
            if type(pure) is not dict or pure.get('status') != 'passed':
                raise ValueError('Exhaustive pure-response verification did not pass')
            if any(calls.values()):
                raise ValueError('Witness used a forbidden production/ranking entry point')
    except Exception as exc:
        report['errors'].append({'phase': 'candidate-or-independent-verification',
                                 'error': f'{type(exc).__name__}: {exc}'})
    finally:
        report['total_seconds'] = perf_counter() - started
        try:
            report['source_after'] = _snapshot()
            report['source_unchanged'] = (report['source_before'] is not None and
                                         report['source_before'] == report['source_after'])
            if not report['source_unchanged']:
                report['errors'].append({'phase': 'source-integrity',
                                         'error': 'Source/revision/status changed during witness run'})
        except Exception as exc:
            report['errors'].append({'phase': 'final-source-identity',
                                     'error': f'{type(exc).__name__}: {exc}'})
    return _finish(report)


def _write(path, report, *, replacing_owned=False):
    if path.exists() and not replacing_owned:
        raise FileExistsError('Preserve the existing observation; choose a new output path')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    if temporary.exists():
        raise FileExistsError('Preserve the existing temporary observation')
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n',
                         encoding='utf-8', newline='\n')
    temporary.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feasibility', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    path = args.output.resolve()
    if path == ROOT or ROOT in path.parents:
        parser.error('Write the raw observation outside the repository checkout')
    if path.exists() or path.with_name(path.name + '.tmp').exists():
        parser.error('Preserve the existing observation and choose a new output path')
    spec = json.loads(SPEC_PATH.read_text(encoding='utf-8'))
    report = run(spec, feasibility=args.feasibility)
    _write(path, report)
    if report['status'] == 'passed':
        try:
            # Reopen the actual saved artifact and rebuild exact verification;
            # never treat a saved summary flag as the certificate.
            saved = json.loads(path.read_text(encoding='utf-8'))
            unsigned = dict(saved); unsigned.pop('artifact_sha256', None)
            if saved.get('artifact_sha256') != checksum(unsigned):
                raise ValueError('Saved artifact checksum changed')
            with _guards():
                _, independent = _components()
                fresh = independent.verify_certificate(saved['candidate_witness'])
                fresh_pure = _pure_check(saved['candidate_witness'])
            if fresh != saved['independent_verification']:
                raise ValueError('Saved-file exact verification differs')
            if fresh_pure != saved['exhaustive_pure_response_verification']:
                raise ValueError('Saved-file exhaustive pure-response check differs')
            if _snapshot() != saved['source_after']:
                raise ValueError('Source changed during saved-file exact verification')
        except Exception as exc:
            report['errors'].append({'phase': 'saved-file-verification',
                                     'error': f'{type(exc).__name__}: {exc}'})
            _finish(report); _write(path, report, replacing_owned=True)
    print(json.dumps({'status': report['status'], 'phase': report['phase'],
                      'artifact_sha256': report['artifact_sha256'],
                      'errors': report['errors']}, sort_keys=True), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
