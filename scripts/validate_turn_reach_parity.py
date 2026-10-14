"""Frozen old/new ordinary turn payload comparison with independent replay.

Both historical production modules are fingerprinted; unchanged shared
dependencies are checked against the same local baseline Git commit.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
from unittest.mock import patch

from pokerlab import public_cfr, public_diagnostics
from pokerlab.matrix_free_turn import solve_matrix_free_turn
from scripts.benchmark_turn_river_independent import CONFIG, ROOT, source_hashes
from scripts.turn_river_validation import compare_result, replay_policy


BASE = 'f934f4a'
EXPECTED = {
    'turn_range_kernel.py': '46f7614ce9dd7f74eb46a06762fbbcf8de9ec0e2ed413c0f68b9b14f4276b920',
    'matrix_free_turn.py': 'f9e452c324c3df9e9c427fe241f561df070474a18714b4d5333e5c62bdf0ebad',
}


def _canonical(payload):
    return payload.removeprefix(b'\xef\xbb\xbf').replace(b'\r\n', b'\n')


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _historical(directory):
    for filename, expected in EXPECTED.items():
        actual = hashlib.sha256(_canonical((directory / filename).read_bytes())).hexdigest()
        if actual != expected:
            raise ValueError('Historical source fingerprint differs: ' + filename)
    # Inspect every shared production dependency rather than loading an old
    # adapter against silently changed trainer/ranker/rule implementations.
    for path in sorted((ROOT / 'pokerlab').glob('*.py')):
        if path.name in EXPECTED:
            continue
        old = subprocess.check_output(['git', 'show', BASE + ':' + path.relative_to(ROOT).as_posix()], cwd=ROOT)
        if _canonical(path.read_bytes()) != _canonical(old):
            raise ValueError('Shared dependency differs from frozen baseline: ' + path.name)
    old_config = subprocess.check_output(['git', 'show', BASE + ':' + CONFIG.relative_to(ROOT).as_posix()], cwd=ROOT)
    if _canonical(CONFIG.read_bytes()) != _canonical(old_config):
        raise ValueError('Fixture specification differs from frozen baseline')
    kernel = _load(directory / 'turn_range_kernel.py', 'pokerlab._conditioning_baseline_kernel')
    adapter = _load(directory / 'matrix_free_turn.py', 'pokerlab._conditioning_baseline_adapter')
    # The old adapter's relative import initially finds the current module;
    # substitute the separately fingerprinted old kernel explicitly.
    adapter.TurnRangePayoffs = kernel.TurnRangePayoffs
    def historical_solve(*args, **kwargs):
        # These two shared imports are used only for isinstance guards (and
        # annotations). Bind the archived class during the archived call so
        # a separately loaded, unchanged historical kernel is recognizable.
        # Trainer/evaluator implementations and kernel methods stay untouched;
        # context managers restore current-class guards before every new call.
        with patch.object(public_cfr, 'TurnRangePayoffs', kernel.TurnRangePayoffs), \
             patch.object(public_diagnostics, 'TurnRangePayoffs', kernel.TurnRangePayoffs):
            return adapter.solve_matrix_free_turn(*args, **kwargs)
    return historical_solve


def _hashes():
    result = source_hashes()
    result[str(Path(__file__).relative_to(ROOT))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    old_solve = _historical(args.baseline_dir)
    cases = [case for case in json.loads(CONFIG.read_text(encoding='utf-8'))['scenarios']
             if len(case['board']) == 8]
    if len(cases) != 2:
        raise ValueError('Require exactly the two frozen existing turn fixtures')
    before = _hashes()
    baseline_before = {name: hashlib.sha256((args.baseline_dir / name).read_bytes()).hexdigest()
                       for name in EXPECTED}
    rows = []
    for case in cases:
        for algorithm in ('vanilla', 'dcfr', 'cfrplus'):
            for mode in ('fixed', 'zero-target'):
                options = {key: case[key] for key in ('river_config', 'runouts') if key in case}
                options.update(iterations=20, algorithm=algorithm)
                if mode == 'zero-target':
                    options.update(target_exploitability=0.0, check_interval=10)
                started = time.perf_counter()
                old = old_solve(case['board'], case['oop'], case['ip'], case['config'], **options)
                old_seconds = time.perf_counter() - started
                started = time.perf_counter()
                current = solve_matrix_free_turn(case['board'], case['oop'], case['ip'], case['config'], **options)
                new_seconds = time.perf_counter() - started
                if current != old:
                    raise ValueError('Ordinary complete payload changed: ' + case['id'] + '/' + algorithm + '/' + mode)
                oracle = replay_policy(current, case['oop'], case['ip'], board=case['board'],
                                       config=case['config'], **{key: case[key] for key in
                                                               ('river_config', 'runouts') if key in case})
                differences = compare_result(current, oracle)
                payload = json.dumps(current, sort_keys=True, allow_nan=False).encode('utf-8')
                rows.append({
                    'scenario': case['id'], 'algorithm': algorithm, 'mode': mode,
                    'iterations_requested': 20, 'iterations_completed': current['iterations'],
                    'complete_payload_equal': True, 'payload_sha256': hashlib.sha256(payload).hexdigest(),
                    'scalar_differences': differences,
                    'metrics': {field: oracle[field] for field in differences},
                    'verified_worlds': oracle['worlds'],
                    'verified_information_sets': oracle['checked_information_sets'],
                    'configured_solver_target_exploitability': 0.0 if mode == 'zero-target' else None,
                    'benchmark_nash_conv_threshold': 0.001,
                    'benchmark_threshold_met': oracle['nash_conv'] <= 0.001,
                    'resource_usage_identical': current['resource_usage'] == old['resource_usage'],
                    'old_call_seconds': old_seconds, 'new_call_seconds': new_seconds,
                })
                print(case['id'], algorithm, mode, 'complete payload identical; replay passed', flush=True)
    if _hashes() != before or baseline_before != {
            name: hashlib.sha256((args.baseline_dir / name).read_bytes()).hexdigest() for name in EXPECTED}:
        raise RuntimeError('Source or historical files changed during comparison; discard run')
    report = {
        'schema_version': 1, 'benchmark_id': 'turn-root-reach-ordinary-parity-v1',
        'baseline_git_commit': subprocess.check_output(['git', 'rev-parse', BASE], cwd=ROOT, text=True).strip(),
        'baseline_canonical_sha256': EXPECTED, 'source_sha256': before,
        'python': platform.python_version(), 'fixtures': cases, 'results': rows,
        'methodology': {
            'comparison': 'Both old adapter and old turn kernel fingerprinted; unchanged shared source checked against baseline. Only shared trainer/evaluator isinstance-guard class references temporarily bind the separately loaded archived kernel during old calls; algorithms/methods stay unchanged and current guards restore before new calls. Full ordinary output equality includes policy/resources/convergence.',
            'validation': 'All twelve new complete policies independently replayed with numeric rules and legal information-set BRs; eight scalar differences and all 0.001-chip benchmark-threshold misses retained. Fixed runs configure no solver stop target; zero-target runs configure target_exploitability=0.0. The separate 0.001 NashConv threshold is a reporting comparison, not the configured stopping target.',
            'timing': 'Single old/new call observations on a shared host; no controlled speedup, allocation or RSS claim.',
            'scope': 'Two frozen synthetic turn fixtures, three existing algorithms, fixed and zero-target modes at20 sweeps. Root-fold reach underflow has separate regression evidence.',
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
