"""Frozen whole-call nonregression check for the exact lazy Catalog candidate."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BLOCKS, CALLS = 8, 16


def require(value, message):
    if not value:
        raise ValueError(message)


def dump(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


def benchmark(baseline, candidate, expected, output):
    from tests.test_native_exact_reach import authenticate
    from tests.virtual_frozen_run_control import run_bounded_child
    from tests.virtual_native_single_pass_reference import verify as verify_eager
    from tests.virtual_native_lazy_joint_reference import verify as verify_lazy
    from tests.virtual_joint_witness_cases import validate_sign_witnesses
    from tests.virtual_lazy_joint_witnesses import validate_shared_board_witnesses
    paths = {'eager': baseline.resolve(), 'lazy': candidate.resolve()}
    expected = expected.resolve(); output = output.resolve()
    require(output.parent == ROOT.parent.resolve(), 'external sibling lazy benchmark output')
    output.mkdir(exist_ok=False)
    require(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT), 'committed clean lazy benchmark source')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    names = tuple(name for name in subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
                  if name.endswith(('.py', '.hpp', '.cpp')))
    sources = {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
    targets = {'eager': 'virtual-weighted-joint-single-pass', 'lazy': 'virtual-weighted-joint-single-pass-lazy'}
    identities = {mode: authenticate(path, ROOT, targets[mode]) for mode, path in paths.items()}
    eager, lazy = identities['eager'][1], identities['lazy'][1]
    require(eager['compiler_sha256'] == lazy['compiler_sha256'] and
            eager['dependency_archive_sha256'] == lazy['dependency_archive_sha256'] and
            eager['source_sha256'] == lazy['source_sha256'], 'matched compiler/dependency/source closure')
    def flags(record):
        return ['<owned-boost-include>' if flag.startswith(('/I', '-I')) else flag for flag in record['flags']]
    require(flags(lazy) in ([*flags(eager), '/DOPENPOKER_JOINT_LAZY_CATALOG'],
                           [*flags(eager), '-DOPENPOKER_JOINT_LAZY_CATALOG']), 'lazy macro only flag difference')
    labels = ('same-world', 'sb-loss', 'sb-win', 'shared-board-distinct-holding')
    selectors = (((0, 0), (0, 0)), ((4, 0), (4, 0)), ((1966603, 0), (1966603, 0)),
                 ((0, 2140425), (4, 2140425)))
    wires = {mode: tuple((expected / ((('baseline-' if mode == 'eager' else '') + 'profile-1-' + label)) / 'stdout.bin').read_bytes()
                         for label in labels) for mode in paths}
    references = {'eager': [], 'lazy': []}; canonical_hashes = []
    for index, pair in enumerate(selectors):
        references['eager'].append(verify_eager(1, pair, wires['eager'][index]))
        references['lazy'].append(verify_lazy(1, pair, wires['lazy'][index]))
        canonical = sha256(wires['eager'][index]).hexdigest(); canonical_hashes.append(canonical)
        require(references['lazy'][-1]['canonical_eager_stdout_sha256'] == canonical and
                references['lazy'][-1]['epochs'] == references['eager'][-1]['epochs'], 'independently exact eager/lazy numerical and normalized counter agreement')
    witnesses = validate_sign_witnesses(); shared_board = validate_shared_board_witnesses()
    dump(output / 'independent-expected.json', references)
    dump(output / 'protocol.json', {'head': head, 'source_raw_sha256': sources,
        'selectors': [[1, *[value for item in pair for value in item]] for pair in selectors], 'case_labels': labels,
        'independent_sign_witnesses': witnesses,
        'independent_shared_board_witnesses': shared_board,
        'case_schedule': '(16*block+call)%4, identical for both modes; warmups use indices 0 and 1',
        'blocks': BLOCKS, 'calls_per_block': CALLS, 'warmups_per_target': 2, 'timed_calls_per_target': 128,
        'automatic_retries': 0, 'median_lazy_eager_limit': 1.05, 'maximum_pairs_above_1_10': 2,
        'full_wire_sha256': {mode: [sha256(raw).hexdigest() for raw in images] for mode, images in wires.items()},
        'canonical_eager_sha256': canonical_hashes,
        'scope': 'Named weighted full52 tie/loss/win fixed-tree T2 complete calls only. Storage nonregression gate, no universal performance, CPU, RSS, longer learning or quality claim.'})
    for mode, identity in identities.items():
        (output / (mode + '-build.json')).write_bytes(identity[0])
    def run(mode, label, index):
        child = output / label
        arguments = ['1', *[str(value) for item in selectors[index] for value in item]]
        result = run_bounded_child([str(paths[mode]), *arguments], b'', child,
            stdout_limit=len(wires[mode][index]), stderr_limit=4096, timeout=60)
        raw = (child / 'stdout.bin').read_bytes()
        require(result['status'] == 'exited' and result['actual_exit_observed'] and result['returncode'] == 0 and
                not result['failures'] and raw == wires[mode][index] and (child / 'stderr.bin').read_bytes() == b'',
                'actual exit and exact independently verified complete wire')
        return {'mode': mode, 'case_index': index, 'case_label': labels[index], 'duration_seconds': result['duration_seconds'],
                'stdout_sha256': result['streams'][0]['sha256'], 'canonical_eager_sha256': canonical_hashes[index]}
    warmups = [run(mode, f'warmup-{mode}-{i}', i) for mode in ('eager', 'lazy') for i in range(2)]
    dump(output / 'warmups.json', warmups)
    blocks = []
    for block in range(BLOCKS):
        order = ('eager', 'lazy') if block % 2 == 0 else ('lazy', 'eager')
        record = {'block': block, 'order': order}
        for mode in order:
            record[mode] = [run(mode, f'block-{block}-{mode}-{i}', (CALLS * block + i) % 4) for i in range(CALLS)]
        record['elapsed_ratio'] = sum(item['duration_seconds'] for item in record['lazy']) / sum(item['duration_seconds'] for item in record['eager'])
        blocks.append(record); dump(output / f'block-{block}.json', record)
        print(json.dumps({'block': block, 'elapsed_ratio': record['elapsed_ratio']}), flush=True)
    ratios = [record['elapsed_ratio'] for record in blocks]; median = statistics.median(ratios)
    above = sum(ratio > 1.10 for ratio in ratios)
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == head and
            all(sha256((ROOT / name).read_bytes()).hexdigest() == value for name, value in sources.items()), 'lazy benchmark source drift')
    require(all(authenticate(path, ROOT, targets[mode]) == identities[mode] for mode, path in paths.items()), 'lazy benchmark native/build drift')
    result = {'status': 'lazy-catalog-complete-call-nonregression-comparison-complete', 'actual_native_calls': 260,
        'exact_full_wires_per_mode': True, 'independent_all_row_and_storage_goldens': True,
        'paired_elapsed_ratios': ratios, 'median_lazy_eager_ratio': median, 'pairs_above_1_10': above,
        'nonregression_gate_pass': median <= 1.05 and above <= 2,
        'scope': 'One host and named weighted full52 tie/loss/win fixed-tree T2 mix. Every observation retained. No universal performance, CPU/RSS, longer learning or quality claim.'}
    dump(output / 'result.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'candidate', 'expected', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.baseline, args.candidate, args.expected, args.output), indent=2))
