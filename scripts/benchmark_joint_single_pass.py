"""Frozen paired complete-call comparison after exact single-pass conformance."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BLOCKS, CALLS = 8, 8


def require(value, message):
    if not value:
        raise ValueError(message)


def dump(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


def benchmark(baseline, candidate, baseline_expected, candidate_expected, output):
    from tests.test_native_exact_reach import authenticate
    from tests.virtual_frozen_run_control import run_bounded_child
    from tests.virtual_native_weighted_joint_reference import verify as verify_baseline
    from tests.virtual_native_single_pass_reference import verify as verify_candidate
    from tests.virtual_joint_numeric_projection import project
    paths = dict(baseline=baseline.resolve(), candidate=candidate.resolve())
    output = output.resolve(); require(output.parent == ROOT.parent.resolve(), 'external sibling benchmark output')
    output.mkdir(exist_ok=False)
    require(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT), 'clean committed benchmark source')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    names = tuple(name for name in subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
                  if name.endswith(('.py', '.hpp', '.cpp')))
    sources = {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
    targets = {'baseline': 'virtual-weighted-joint-two-epoch', 'candidate': 'virtual-weighted-joint-single-pass'}
    identities = {mode: authenticate(paths[mode], ROOT, targets[mode]) for mode in paths}
    base, trial = identities['baseline'][1], identities['candidate'][1]
    require(base['compiler_sha256'] == trial['compiler_sha256'] and
            base['dependency_archive_sha256'] == trial['dependency_archive_sha256'] and
            base['source_sha256'] == trial['source_sha256'], 'same compiler/dependency/complete source closure')
    def flags(record):
        return ['<owned-boost-include>' if item.startswith(('/I', '-I')) else item for item in record['flags']]
    require(flags(trial) in ([*flags(base), '/DOPENPOKER_JOINT_SINGLE_PASS'],
                            [*flags(base), '-DOPENPOKER_JOINT_SINGLE_PASS']), 'single-pass macro only flag difference')
    from tests.virtual_joint_witness_cases import validate_sign_witnesses
    sign_witnesses = validate_sign_witnesses()
    labels = ('same-world', 'sb-loss', 'sb-win')
    tickets = (0, 4, 1966603)
    expected_dirs = {'baseline': baseline_expected.resolve(), 'candidate': candidate_expected.resolve()}
    wires = {mode: tuple((directory / ('profile-1-' + label) / 'stdout.bin').read_bytes()
                         for label in labels) for mode, directory in expected_dirs.items()}
    reference = {mode: [verifier(1, ((ticket, 0), (ticket, 0)), raw)
                        for ticket, raw in zip(tickets, wires[mode])]
                 for mode, verifier in (('baseline', verify_baseline), ('candidate', verify_candidate))}
    numeric = tuple(project(raw) for raw in wires['baseline'])
    require(tuple(project(raw) for raw in wires['candidate']) == numeric, 'exact baseline/candidate numeric projections')
    dump(output / 'independent-expected.json', reference)
    dump(output / 'protocol.json', {'head': head, 'source_raw_sha256': sources,
        'selectors': [[1, ticket, 0, ticket, 0] for ticket in tickets], 'case_labels': labels,
        'independent_sign_witnesses': sign_witnesses,
        'case_schedule': '(8*block+call)%3, identical for both modes; warmups use indices 0 and 1',
        'blocks': BLOCKS, 'calls_per_block': CALLS, 'warmups_per_target': 2, 'timed_calls_per_target': 64,
        'automatic_retries': 0, 'median_candidate_baseline_limit': 0.95, 'minimum_faster_pairs': 6,
        'full_wire_sha256': {mode: [sha256(raw).hexdigest() for raw in images] for mode, images in wires.items()},
        'exact_numeric_projection_sha256': [sha256(raw).hexdigest() for raw in numeric],
        'scope': 'Named weighted full52 fixed-tree tie/loss/win same-world T2 complete-call mix only; no universal speedup, long learning, convergence or quality.'})
    for mode, identity in identities.items():
        (output / (mode + '-build.json')).write_bytes(identity[0])
    def run(mode, label, case_index):
        child = output / label
        ticket = str(tickets[case_index])
        result = run_bounded_child([str(paths[mode]), '1', ticket, '0', ticket, '0'], b'', child,
                                   stdout_limit=len(wires[mode][case_index]), stderr_limit=4096, timeout=60)
        raw = (child / 'stdout.bin').read_bytes()
        require(result['status'] == 'exited' and result['actual_exit_observed'] and result['returncode'] == 0 and
                not result['failures'] and raw == wires[mode][case_index] and (child / 'stderr.bin').read_bytes() == b'' and
                project(raw) == numeric[case_index], 'actual exit/exact complete wire/numeric projection')
        return {'mode': mode, 'case_index': case_index, 'case_label': labels[case_index],
                'duration_seconds': result['duration_seconds'], 'stdout_sha256': result['streams'][0]['sha256'],
                'numeric_projection_sha256': sha256(numeric[case_index]).hexdigest()}
    warmups = [run(mode, f'warmup-{mode}-{i}', i) for mode in ('baseline', 'candidate') for i in range(2)]
    dump(output / 'warmups.json', warmups)
    blocks = []
    for block in range(BLOCKS):
        order = ('baseline', 'candidate') if block % 2 == 0 else ('candidate', 'baseline')
        record = {'block': block, 'order': order}
        for mode in order:
            record[mode] = [run(mode, f'block-{block}-{mode}-{i}', (CALLS * block + i) % 3) for i in range(CALLS)]
        record['elapsed_ratio'] = sum(item['duration_seconds'] for item in record['candidate']) / sum(item['duration_seconds'] for item in record['baseline'])
        blocks.append(record); dump(output / f'block-{block}.json', record)
        print(json.dumps({'block': block, 'elapsed_ratio': record['elapsed_ratio']}), flush=True)
    ratios = [block['elapsed_ratio'] for block in blocks]; median = statistics.median(ratios)
    faster = sum(ratio < 1 for ratio in ratios)
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == head and
            all(sha256((ROOT / name).read_bytes()).hexdigest() == value for name, value in sources.items()), 'benchmark source drift')
    require(all(authenticate(paths[mode], ROOT, targets[mode]) == identities[mode] for mode in paths), 'benchmark native identity drift')
    result = {'status': 'single-pass-complete-call-comparison-complete', 'actual_native_calls': 132,
        'exact_full_wires_per_mode': True, 'exact_shared_numeric_projection': True,
        'paired_elapsed_ratios': ratios, 'median_candidate_baseline_ratio': median, 'candidate_faster_pairs': faster,
        'performance_gate_pass': median <= 0.95 and faster >= 6,
        'scope': 'One host and named full52 weighted fixed-tree tie/loss/win T2 mix only. Every observation retained; no universal performance or solved-quality claim.'}
    dump(output / 'result.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'candidate', 'baseline_expected', 'candidate_expected', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.baseline, args.candidate, args.baseline_expected, args.candidate_expected, args.output), indent=2))
