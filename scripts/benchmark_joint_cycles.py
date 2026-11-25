"""Frozen eager single-pass CPU diagnostic, exact-wire and observer-overhead gate."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
LABELS = ('same-world', 'sb-loss', 'sb-win', 'shared-board-distinct-holding')
SELECTORS = (((0, 0), (0, 0)), ((4, 0), (4, 0)), ((1966603, 0), (1966603, 0)), ((0, 2140425), (4, 2140425)))


def need(value, message):
    if not value: raise ValueError(message)


def dump(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


def benchmark(baseline, candidate, expected, output, *, parity_only=False):
    from tests.test_joint_cycle_reference import capture, unchanged
    from tests.test_native_exact_reach import authenticate
    from tests.virtual_frozen_run_control import run_bounded_child
    from tests.virtual_native_single_pass_reference import verify
    from tests.virtual_joint_cycle_reference import decode
    paths = {'standard': baseline.resolve(), 'diagnostic': candidate.resolve()}
    targets = {'standard': 'virtual-weighted-joint-single-pass', 'diagnostic': 'virtual-weighted-joint-single-pass-cycles'}
    output = output.resolve(); expected = expected.resolve()
    identity, head, source = capture(paths['diagnostic'], targets['diagnostic'], output)
    baseline_identity = authenticate(paths['standard'], ROOT, targets['standard'])
    (output / 'baseline-build.json').write_bytes(baseline_identity[0])
    a, b = baseline_identity[1], identity[1]
    need(a['compiler_sha256'] == b['compiler_sha256'] and a['dependency_archive_sha256'] == b['dependency_archive_sha256'], 'matched compiler/dependency')
    need({k: v for k, v in b['source_sha256'].items() if k != 'native/joint_thread_cycle_recorder.hpp'} == a['source_sha256'], 'matched core source closure')
    def flags(value): return ['<include>' if flag.startswith(('/I', '-I')) else flag for flag in value['flags']]
    need(flags(b) in ([*flags(a), '/DOPENPOKER_JOINT_THREAD_CYCLES'], [*flags(a), '-DOPENPOKER_JOINT_THREAD_CYCLES']), 'diagnostic macro only flags')
    wires = [(expected / ('baseline-profile-1-' + label) / 'stdout.bin').read_bytes() for label in LABELS]
    reports = [verify(1, pair, raw) for pair, raw in zip(SELECTORS, wires)]
    dump(output / 'independent-expected.json', reports)
    dump(output / 'protocol.json', {'head': head, 'source_raw_sha256': {k: sha256(v).hexdigest() for k, v in source.items()},
        'selectors': SELECTORS, 'profile': 1, 'labels': LABELS, 'blocks': 0 if parity_only else 8,
        'calls_per_block': 16, 'warmups_per_target': 2, 'automatic_retries': 0,
        'schedule': 'case=i%4; offset=(i//4)%4; every case/offset once per block; alternate target order by block',
        'median_diagnostic_standard_limit': 1.05, 'maximum_pairs_above_1_10': 2,
        'full_wire_sha256': [sha256(raw).hexdigest() for raw in wires],
        'scope': 'One host, weighted fixed-template full52 T2. Overhead gate required before using sampled CPU estimates. No unobserved owner attribution, cycle conversion or quality.'})
    calls = 0
    def run(mode, label, case, offset):
        nonlocal calls
        child = output / label
        args = ['1', *[str(v) for item in SELECTORS[case] for v in item]]
        if mode == 'diagnostic': args.append(str(offset))
        receipt = run_bounded_child([str(paths[mode]), *args], b'', child, stdout_limit=len(wires[case]), stderr_limit=8192, timeout=60)
        calls += 1
        need((receipt['status'], receipt['actual_exit_observed'], receipt['returncode'], receipt['failures']) == ('exited', True, 0, []), 'original process exit')
        need((child / 'stdout.bin').read_bytes() == wires[case], 'complete independent exact wire')
        stderr = (child / 'stderr.bin').read_bytes()
        observation = decode(stderr, offset) if mode == 'diagnostic' else None
        if mode == 'standard': need(stderr == b'', 'standard stderr empty')
        return {'case_index': case, 'offset': offset, 'duration_seconds': receipt['duration_seconds'], 'cpu': observation}
    blocks = []
    if parity_only:
        for case in range(4):
            run('standard', f'standard-{case}', case, 0)
            for offset in range(4):
                dump(output / f'diagnostic-{case}-{offset}.json', run('diagnostic', f'diagnostic-{case}-{offset}', case, offset))
    else:
        dump(output / 'warmups.json', [run(mode, f'warmup-{mode}-{i}', i, i) for mode in paths for i in range(2)])
        for block in range(8):
            order = ('standard', 'diagnostic') if block % 2 == 0 else ('diagnostic', 'standard')
            record = {'block': block, 'order': order}
            for mode in order:
                record[mode] = [run(mode, f'block-{block}-{mode}-{i}', i % 4, (i // 4) % 4) for i in range(16)]
            record['elapsed_ratio'] = sum(x['duration_seconds'] for x in record['diagnostic']) / sum(x['duration_seconds'] for x in record['standard'])
            blocks.append(record); dump(output / f'block-{block}.json', record)
            print(json.dumps({'block': block, 'elapsed_ratio': record['elapsed_ratio']}), flush=True)
    unchanged(paths['diagnostic'], targets['diagnostic'], identity, head, source)
    need(authenticate(paths['standard'], ROOT, targets['standard']) == baseline_identity, 'standard binary/source drift')
    ratios = [block['elapsed_ratio'] for block in blocks]
    median = statistics.median(ratios) if ratios else None
    above = sum(ratio > 1.10 for ratio in ratios)
    result = {'status': 'parity-complete' if parity_only else 'observer-overhead-comparison-complete', 'actual_native_calls': calls,
        'paired_elapsed_ratios': ratios, 'median_diagnostic_standard_ratio': median, 'pairs_above_1_10': above,
        'observer_overhead_gate_pass': None if parity_only else median <= 1.05 and above <= 2,
        'exact_all_row_wires': True, 'quality_gate': None,
        'scope': 'Eager single-pass fixed-template T2 diagnostic only. Sampled empirical CPU shares require the overhead gate; bounded correctness is not realistic-game scalability or convergence.'}
    dump(output / 'result.json', result); return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'candidate', 'expected', 'output'): parser.add_argument(name, type=Path)
    parser.add_argument('--parity-only', action='store_true'); args = parser.parse_args()
    print(json.dumps(benchmark(args.baseline, args.candidate, args.expected, args.output, parity_only=args.parity_only), indent=2))
