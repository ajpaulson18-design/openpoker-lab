"""Frozen ordinary river complete-payload parity after ceiling-only admission."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

from pokerlab.matrix_free_river import solve_matrix_free_river
from scripts.benchmark_turn_river_independent import CONFIG, ROOT, source_hashes
from scripts.turn_river_validation import compare_result, replay_policy


BASE = '3ea3ea3'
EXPECTED = '8172684e2f3b5d6066761a3cbd9e0cb57c8f7e244e636dc62b4c0932d2e32111'


def _canonical(payload):
    return payload.removeprefix(b'\xef\xbb\xbf').replace(b'\r\n', b'\n')


def historical(directory):
    path = directory / 'matrix_free_river.py'
    if hashlib.sha256(_canonical(path.read_bytes())).hexdigest() != EXPECTED:
        raise ValueError('Historical isolated river module fingerprint differs')
    for shared in sorted((ROOT / 'pokerlab').glob('*.py')):
        if shared.name == path.name:
            continue
        old = subprocess.check_output(['git', 'show', BASE + ':' + shared.relative_to(ROOT).as_posix()], cwd=ROOT)
        if _canonical(shared.read_bytes()) != _canonical(old):
            raise ValueError('Shared production source differs from baseline: ' + shared.name)
    old_config = subprocess.check_output(['git', 'show', BASE + ':' + CONFIG.relative_to(ROOT).as_posix()], cwd=ROOT)
    if _canonical(CONFIG.read_bytes()) != _canonical(old_config):
        raise ValueError('Fixture specification differs from baseline')
    name = 'pokerlab._river_long_baseline'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module.solve_matrix_free_river


def fingerprints(directory):
    hashes = source_hashes()
    hashes[Path(__file__).relative_to(ROOT).as_posix()] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    hashes['historical/matrix_free_river.py'] = hashlib.sha256((directory / 'matrix_free_river.py').read_bytes()).hexdigest()
    return hashes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    old_solve = historical(args.baseline_dir)
    cases = [case for case in json.loads(CONFIG.read_text(encoding='utf-8'))['scenarios']
             if len(case['board']) == 10]
    if len(cases) != 2:
        raise ValueError('Require the two frozen existing river fixtures')
    before = fingerprints(args.baseline_dir)
    rows = []
    for case in cases:
        for algorithm in ('vanilla', 'dcfr', 'cfrplus'):
            for mode in ('fixed', 'zero-target'):
                options = {'iterations': 20, 'algorithm': algorithm}
                if mode == 'zero-target':
                    options.update(target_exploitability=0.0, check_interval=10)
                start = time.perf_counter()
                old = old_solve(case['board'], case['oop'], case['ip'], case['config'], **options)
                old_seconds = time.perf_counter() - start
                start = time.perf_counter()
                result = solve_matrix_free_river(case['board'], case['oop'], case['ip'], case['config'], **options)
                new_seconds = time.perf_counter() - start
                if old != result:
                    raise ValueError('Ordinary complete river payload changed')
                oracle = replay_policy(result, case['oop'], case['ip'], board=case['board'], config=case['config'])
                differences = compare_result(result, oracle)
                payload = json.dumps(result, sort_keys=True, allow_nan=False).encode('utf-8')
                rows.append({
                    'scenario': case['id'], 'algorithm': algorithm, 'mode': mode,
                    'iterations_requested': 20, 'iterations_completed': result['iterations'],
                    'complete_payload_equal': True, 'payload_sha256': hashlib.sha256(payload).hexdigest(),
                    'metrics': {field: oracle[field] for field in differences},
                    'scalar_differences': differences,
                    'verified_worlds': oracle['worlds'],
                    'verified_information_sets': oracle['checked_information_sets'],
                    'configured_solver_target_exploitability': 0.0 if mode == 'zero-target' else None,
                    'benchmark_nash_conv_threshold': 0.001,
                    'benchmark_threshold_met': oracle['nash_conv'] <= 0.001,
                    'old_call_seconds': old_seconds, 'new_call_seconds': new_seconds,
                })
                print(case['id'], algorithm, mode, 'complete payload identical; independent replay passed', flush=True)
    if fingerprints(args.baseline_dir) != before:
        raise RuntimeError('Protected source changed during parity comparison')
    report = {
        'schema_version': 1, 'benchmark_id': 'river-long-budget-ordinary-parity-v1',
        'baseline_git_commit': subprocess.check_output(['git', 'rev-parse', BASE], cwd=ROOT, text=True).strip(),
        'baseline_canonical_sha256': EXPECTED, 'source_sha256': before,
        'python': platform.python_version(), 'fixtures': cases, 'results': rows,
        'methodology': {
            'comparison': 'Fingerprint frozen old isolated river module; all shared production source and fixture specification must match baseline. Compare complete payloads exactly across two existing fixtures, three algorithms and fixed/zero-target modes at20 sweeps.',
            'validation': 'Independently replay every new complete policy using physical-world weights, numeric rules and legal information-set best responses. The reporting-only 0.001 NashConv threshold differs from configured solver stopping settings (None or zero exploitability).',
            'timing': 'Single old/new observations on a shared host; no controlled speed, allocation or RSS claim.',
            'scope': 'Ordinary small river fixtures. Longer requested ceilings have separate admission and quality evidence.',
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
