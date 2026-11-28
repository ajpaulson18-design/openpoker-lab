"""Paired coarse phase diagnostic with exact independent full52 wire replay.

The standard target contains no clocks. Both targets execute the same named
weighted two-observation request. This measures wall time, not inner-walk CPU.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BLOCKS, CALLS = 8, 8
SEQUENCE = [('begin', 0), ('range_input', 0), ('template', 0), ('chance', 0), ('owners', 0), ('header', 0)]
for _epoch in (1, 2):
    SEQUENCE.extend((phase, _epoch) for phase in ('epoch_begin', 'ticket', 'walk', 'stage', 'release', 'commit', 'snapshot'))
SEQUENCE.extend((('footer', 0), ('publish', 0)))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def dump(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


def phases(raw):
    require(type(raw) is bytes and len(raw) <= 4096 and raw.startswith(b'JOINT_PHASE_PROFILE '), 'bounded diagnostic stderr')
    report = json.loads(raw.removeprefix(b'JOINT_PHASE_PROFILE '))
    require(set(report) == {'version', 'extra_work', 'metadata_entries', 'metadata_payload_bits', 'clock_reads', 'events'} and
            (report['version'], report['extra_work'], report['metadata_entries'], report['metadata_payload_bits'], report['clock_reads']) ==
            (1, 73728, 256, 16384, 23), 'diagnostic independent metadata/clock budget')
    events = report['events']
    require(type(events) is list and len(events) == len(SEQUENCE) and
            all(type(event) is list and len(event) == 3 and tuple(event[:2]) == expected and
                type(event[2]) is int and event[2] >= 0 for event, expected in zip(events, SEQUENCE)) and
            all(a[2] <= b[2] for a, b in zip(events, events[1:])), 'diagnostic exact phase structure')
    totals = {}
    for previous, event in zip(events, events[1:]):
        totals[event[0]] = totals.get(event[0], 0) + event[2] - previous[2]
    elapsed = events[-1][2] - events[0][2]
    require(elapsed > 0 and sum(totals.values()) == elapsed, 'diagnostic disjoint phase partition')
    return {'phase_nanoseconds': totals, 'interval_nanoseconds': elapsed,
            'phase_percent': {name: value * 100 / elapsed for name, value in totals.items()}}


def benchmark(standard, diagnostic, expected, output):
    from tests.test_native_exact_reach import authenticate
    from tests.virtual_frozen_run_control import run_bounded_child
    from tests.virtual_native_weighted_joint_reference import verify
    standard, diagnostic, expected, output = standard.resolve(), diagnostic.resolve(), expected.resolve(), output.resolve()
    require(output.parent == ROOT.parent.resolve(), 'external sibling output directory')
    output.mkdir(exist_ok=False)
    require(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT), 'committed clean tracked source')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    names = tuple(name for name in subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
                  if name.endswith(('.py', '.hpp', '.cpp')))
    hashes = {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
    identities = {'standard': authenticate(standard, ROOT, 'virtual-weighted-joint-two-epoch'),
                  'diagnostic': authenticate(diagnostic, ROOT, 'virtual-weighted-joint-two-epoch-profile')}
    base, candidate = (identities[name][1] for name in ('standard', 'diagnostic'))
    require(base['compiler_sha256'] == candidate['compiler_sha256'] and
            base['dependency_archive_sha256'] == candidate['dependency_archive_sha256'] and
            all(candidate['source_sha256'].get(name) == value for name, value in base['source_sha256'].items()),
            'same compiler/dependency/shared source')
    def flags(manifest):
        return ['<owned-boost-include>' if flag.startswith(('/I', '-I')) else flag for flag in manifest['flags']]
    require(flags(candidate) == [*flags(base), '/DOPENPOKER_JOINT_PHASE_PROFILE'] or
            flags(candidate) == [*flags(base), '-DOPENPOKER_JOINT_PHASE_PROFILE'], 'diagnostic macro only flag difference')
    wire = expected.read_bytes()
    # Independent saved-policy arithmetic precedes every timed native call.
    reference = verify(1, ((0, 0), (0, 0)), wire)
    dump(output / 'independent-expected.json', reference)
    dump(output / 'protocol.json', {'head': head, 'source_raw_sha256': hashes, 'blocks': BLOCKS, 'calls_per_block': CALLS,
        'warmups_per_target': 2, 'timed_calls_per_target': 64, 'automatic_retries': 0,
        'selectors': [1, 0, 0, 0, 0], 'expected_wire_sha256': sha256(wire).hexdigest(),
        'extra_diagnostic_work': 73728, 'extra_entries': 256, 'extra_payload_bits': 16384, 'stderr_limit': 4096,
        'median_paired_overhead_limit': 1.05,
        'scope': 'Named full52 weighted fixed-tree T2 phase wall time; no inner-walk CPU attribution, speedup, long learning or quality.'})
    for name, identity in identities.items():
        (output / (name + '-build.json')).write_bytes(identity[0])
    def run(mode, label):
        exe = standard if mode == 'standard' else diagnostic
        child = output / label
        result = run_bounded_child([str(exe), '1', '0', '0', '0', '0'], b'', child,
                                   stdout_limit=len(wire), stderr_limit=4096, timeout=60)
        require(result['status'] == 'exited' and result['actual_exit_observed'] and result['returncode'] == 0 and
                not result['failures'] and (child / 'stdout.bin').read_bytes() == wire, 'actual exit or complete standard wire mismatch')
        stderr = (child / 'stderr.bin').read_bytes()
        phase = phases(stderr) if mode == 'diagnostic' else None
        require(mode == 'diagnostic' or stderr == b'', 'standard target diagnostic output')
        return {'mode': mode, 'duration_seconds': result['duration_seconds'], 'phase': phase,
                'stdout_sha256': result['streams'][0]['sha256']}
    warmups = [run(mode, f'warmup-{mode}-{number}') for mode in ('standard', 'diagnostic') for number in range(2)]
    dump(output / 'warmups.json', warmups)
    blocks = []; all_phases = []
    for block in range(BLOCKS):
        order = ('standard', 'diagnostic') if block % 2 == 0 else ('diagnostic', 'standard')
        record = {'block': block, 'order': order}
        for mode in order:
            record[mode] = [run(mode, f'block-{block}-{mode}-{number}') for number in range(CALLS)]
            if mode == 'diagnostic':
                all_phases.extend(item['phase'] for item in record[mode])
        record['elapsed_ratio'] = sum(item['duration_seconds'] for item in record['diagnostic']) / sum(item['duration_seconds'] for item in record['standard'])
        blocks.append(record); dump(output / f'block-{block}.json', record)
        print(json.dumps({'block': block, 'elapsed_ratio': record['elapsed_ratio']}), flush=True)
    median = statistics.median(block['elapsed_ratio'] for block in blocks)
    result = {'status': 'joint-coarse-phase-diagnostic-complete', 'actual_native_calls': 132,
        'all_complete_wires_exact': True, 'paired_elapsed_ratios': [block['elapsed_ratio'] for block in blocks],
        'median_paired_elapsed_ratio': median, 'overhead_pass': median <= 1.05,
        'phase_wall_time_accepted': median <= 1.05, 'inner_walk_cpu_attribution_accepted': False,
        'median_phase_percent': {name: statistics.median(item['phase_percent'][name] for item in all_phases)
                                for name in all_phases[0]['phase_percent']},
        'scope': 'Named weighted full52 T2 complete-call wall time and phase partition only. Median percentages are separate statistics and need not sum100. No CPU family or speedup claim.'}
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == head and
            all(sha256((ROOT / name).read_bytes()).hexdigest() == value for name, value in hashes.items()), 'source changed during measurement')
    require(authenticate(standard, ROOT, 'virtual-weighted-joint-two-epoch') == identities['standard'] and
            authenticate(diagnostic, ROOT, 'virtual-weighted-joint-two-epoch-profile') == identities['diagnostic'], 'native identity changed during measurement')
    dump(output / 'result.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ('standard', 'diagnostic', 'expected', 'output'):
        parser.add_argument(argument, type=Path)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.standard, args.diagnostic, args.expected, args.output), indent=2))
