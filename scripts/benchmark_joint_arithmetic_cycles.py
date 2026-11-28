"""Frozen arithmetic helper attribution and independent observer-overhead gate."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import statistics
from scripts.benchmark_joint_cycles import LABELS, SELECTORS, dump, need


def benchmark(baseline, candidate, expected, output, *, parity_only=False, light=False):
    from tests.test_joint_arithmetic_cycles import capture
    from tests.test_native_lazy_joint import unchanged
    from tests.test_native_exact_reach import authenticate
    from tests.virtual_frozen_run_control import run_bounded_child
    from tests.virtual_native_single_pass_reference import verify
    from tests.virtual_joint_arithmetic_cycle_reference import decode, numeric_sequence
    if light:
        from tests.test_joint_arithmetic_light_cycles import capture
        from tests.virtual_joint_arithmetic_light_reference import decode
    root = Path(__file__).resolve().parents[1]
    paths = {'standard': baseline.resolve(), 'diagnostic': candidate.resolve()}
    targets = {'standard': 'virtual-weighted-joint-single-pass', 'diagnostic':
               'virtual-weighted-joint-single-pass-arithmetic-light-cycles' if light else 'virtual-weighted-joint-single-pass-arithmetic-cycles'}
    output = output.resolve(); expected = expected.resolve(); sequence = numeric_sequence()
    identity, head, source = capture(paths['diagnostic'], targets['diagnostic'], output)
    baseline_identity = authenticate(paths['standard'], root, targets['standard'])
    (output / 'baseline-build.json').write_bytes(baseline_identity[0])
    a, b = baseline_identity[1], identity[1]
    need(a['compiler_sha256'] == b['compiler_sha256'] and a['dependency_archive_sha256'] == b['dependency_archive_sha256'], 'matched arithmetic diagnostic compiler/dependency')
    added = {'native/joint_thread_cycle_recorder.hpp', 'native/joint_arithmetic_cycle_recorder.hpp', 'native/joint_arithmetic_light_recorder.hpp'}
    need({k: v for k, v in b['source_sha256'].items() if k not in added} == a['source_sha256'], 'matched arithmetic core source closure')
    def flags(value): return ['<include>' if flag.startswith(('/I', '-I')) else flag for flag in value['flags']]
    macro = 'OPENPOKER_JOINT_ARITHMETIC_LIGHT_CYCLES' if light else 'OPENPOKER_JOINT_ARITHMETIC_CYCLES'
    need(flags(b) in ([*flags(a), '/D' + macro], [*flags(a), '-D' + macro]), 'arithmetic diagnostic macro only flags')
    wires = [(expected / ('baseline-profile-1-' + label) / 'stdout.bin').read_bytes() for label in LABELS]
    dump(output / 'independent-expected.json', [verify(1, pair, raw) for pair, raw in zip(SELECTORS, wires)])
    dump(output / 'protocol.json', {'head': head, 'source_raw_sha256': {k: sha256(v).hexdigest() for k, v in source.items()},
        'selectors': SELECTORS, 'profile': 1, 'labels': LABELS, 'blocks': 0 if parity_only else 8,
        'observer_mode': 'typed-tls-inline-v1' if light else 'virtual-scopes-v1',
        'calls_per_block': 16, 'warmups_per_target': 2, 'automatic_retries': 0,
        'schedule': 'case=i%4; offset=(5*(4*block+i//4))%32; each case/offset once over eight blocks; alternate target order by block',
        'independent_numeric_rule_helper_sequence': sequence,
        'median_diagnostic_standard_limit': 1.05, 'maximum_pairs_above_1_10': 2,
        'full_wire_sha256': [sha256(raw).hexdigest() for raw in wires],
        'scope': 'Named weighted full52 fixed-template T2 numeric helper bodies, including guards/ledgers/local allocation. Fixed observer gate before empirical attribution. No pure op latency, cycle conversion or quality.'})
    calls = 0
    def run(mode, label, case, offset):
        nonlocal calls
        child = output / label; args = ['1', *[str(v) for item in SELECTORS[case] for v in item]]
        if mode == 'diagnostic': args.append(str(offset))
        receipt = run_bounded_child([str(paths[mode]), *args], b'', child, stdout_limit=len(wires[case]), stderr_limit=8192, timeout=60); calls += 1
        need((receipt['status'], receipt['actual_exit_observed'], receipt['returncode'], receipt['failures']) == ('exited', True, 0, []), 'arithmetic original process exit')
        need((child / 'stdout.bin').read_bytes() == wires[case], 'arithmetic complete independent exact wire')
        stderr = (child / 'stderr.bin').read_bytes(); report = decode(stderr, offset, sequence=sequence) if mode == 'diagnostic' else None
        if mode == 'standard': need(stderr == b'', 'arithmetic standard stderr')
        return {'case_index': case, 'offset': offset, 'duration_seconds': receipt['duration_seconds'], 'cpu': report}
    blocks = []
    if parity_only:
        for case in range(4):
            run('standard', f'standard-{case}', case, 0)
            for offset in range(32): dump(output / f'diagnostic-{case}-{offset}.json', run('diagnostic', f'diagnostic-{case}-{offset}', case, offset))
        for label, args in (('arity', ['1','0','0','0','0']), ('offset-boundary', ['1','0','0','0','0','32']), ('negative', ['1','0','0','0','0','-1'])):
            child = output / ('reject-' + label)
            receipt = run_bounded_child([str(paths['diagnostic']), *args], b'', child, stdout_limit=4096, stderr_limit=8192, timeout=30); calls += 1
            need((receipt['status'], receipt['actual_exit_observed'], receipt['returncode'], receipt['failures']) == ('exited', True, 2, []) and
                 (child / 'stdout.bin').read_bytes() == b'', 'arithmetic diagnostic real argument guard')
    else:
        dump(output / 'warmups.json', [run(mode, f'warmup-{mode}-{i}', i, i) for mode in paths for i in range(2)])
        for block in range(8):
            order = ('standard', 'diagnostic') if block % 2 == 0 else ('diagnostic', 'standard'); record = {'block': block, 'order': order}
            for mode in order:
                record[mode] = [run(mode, f'block-{block}-{mode}-{i}', i % 4, (5 * (4 * block + i // 4)) % 32) for i in range(16)]
            record['elapsed_ratio'] = sum(x['duration_seconds'] for x in record['diagnostic']) / sum(x['duration_seconds'] for x in record['standard'])
            blocks.append(record); dump(output / f'block-{block}.json', record)
            print(json.dumps({'block': block, 'elapsed_ratio': record['elapsed_ratio']}), flush=True)
    unchanged(paths['diagnostic'], targets['diagnostic'], identity, head, source)
    need(authenticate(paths['standard'], root, targets['standard']) == baseline_identity, 'arithmetic standard source/binary drift')
    ratios = [block['elapsed_ratio'] for block in blocks]; median = statistics.median(ratios) if ratios else None; above = sum(r > 1.10 for r in ratios)
    result = {'status': 'arithmetic-parity-complete' if parity_only else 'arithmetic-observer-overhead-comparison-complete',
        'actual_native_calls': calls, 'paired_elapsed_ratios': ratios, 'median_diagnostic_standard_ratio': median, 'pairs_above_1_10': above,
        'observer_mode': 'typed-tls-inline-v1' if light else 'virtual-scopes-v1',
        'observer_overhead_gate_pass': None if parity_only else median <= 1.05 and above <= 2, 'exact_all_row_wires': True, 'quality_gate': None,
        'scope': 'Separate eager fixed-template T2 numeric helper diagnostic. An empirical helper estimate is usable only after its own observer gate. No solver speedup, longer learning or realistic-game admission.'}
    dump(output / 'result.json', result); return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'candidate', 'expected', 'output'): parser.add_argument(name, type=Path)
    parser.add_argument('--parity-only', action='store_true'); parser.add_argument('--light', action='store_true'); args = parser.parse_args()
    print(json.dumps(benchmark(args.baseline, args.candidate, args.expected, args.output, parity_only=args.parity_only, light=args.light), indent=2))
