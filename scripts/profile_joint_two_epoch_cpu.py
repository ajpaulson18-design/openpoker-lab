"""Fixed CPU-sampling protocol for the accepted native joint observation.

Raw WPR ETL and xperf CSV stay private in the external output directory.
This driver never uploads them or changes the standard executable. Exact
native bytes are compared with an independently replayed saved observation.
No archived source is executed and native output is never a math oracle.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = '8e9c31ade82ee4e047be42a99189ddb71b8038cc456f02a97a8c7cf412b2596f'
EXPECTED_BYTES = 335744
BLOCKS = 8
CALLS = 8


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


def text_section(path):
    raw = path.read_bytes(); require(len(raw) <= 16 << 20 and raw[:2] == b'MZ', 'bounded PE image')
    pe = struct.unpack_from('<I', raw, 0x3c)[0]
    require(raw[pe:pe + 4] == b'PE\0\0', 'PE signature')
    sections = struct.unpack_from('<H', raw, pe + 6)[0]
    optional = struct.unpack_from('<H', raw, pe + 20)[0]
    for index in range(sections):
        at = pe + 24 + optional + 40 * index
        if raw[at:at + 8].rstrip(b'\0') == b'.text':
            size, rva, disk_size, offset = struct.unpack_from('<4I', raw, at + 8)
            require(size <= disk_size and offset + size <= len(raw), 'PE text extent')
            return {'rva': rva, 'virtual_bytes': size, 'sha256': sha(raw[offset:offset + size])}
    raise ValueError('missing text section')


def run(executable, output, expected):
    from tests.virtual_frozen_run_control import run_bounded_child
    result = run_bounded_child([str(executable), '0', '0', '0', '0'], b'', output,
                               stdout_limit=EXPECTED_BYTES, timeout=60)
    require(result['actual_exit_observed'] and result['returncode'] == 0 and
            result['status'] == 'exited' and not result['failures'], 'native process failed')
    require((output / 'stdout.bin').read_bytes() == expected and (output / 'stderr.bin').read_bytes() == b'',
            'native complete numerical/resource wire changed')
    return result


def collect(executable, expected_path, output):
    from tests.test_native_exact_reach import authenticate
    executable, expected_path, output = executable.resolve(), expected_path.resolve(), output.resolve()
    require(output.parent == ROOT.parent.resolve(), 'external sibling output directory required')
    output.mkdir(exist_ok=False)
    bootstrap_names = ('scripts/profile_joint_two_epoch_cpu.py', 'tests/virtual_frozen_run_control.py',
                       'tests/test_native_exact_reach.py', 'scripts/build_native_exact_four_street.py')
    require(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all', '--',
                                         *bootstrap_names], cwd=ROOT), 'committed clean controller required')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    bootstrap = {name: sha((ROOT / name).read_bytes()) for name in bootstrap_names}
    identity = authenticate(executable, ROOT, 'virtual-joint-two-epoch')
    expected = expected_path.read_bytes()
    require(len(expected) == EXPECTED_BYTES and sha(expected) == EXPECTED, 'pinned saved same-world observation')
    wpr, xperf = shutil.which('wpr.exe'), shutil.which('xperf.exe')
    require(wpr and xperf, 'installed WPR and xperf required')
    write(output / 'protocol.json', {'head': head, 'bootstrap_raw_sha256': bootstrap,
        'executable_sha256': identity[1]['executable_sha256'], 'expected_stdout_sha256': EXPECTED,
        'text_section': text_section(executable), 'blocks': BLOCKS, 'calls_per_block': CALLS,
        'profiled_calls': 64, 'control_calls': 64, 'warmups': 2, 'selectors': [0, 0, 0, 0],
        'collector': 'Installed WPR CPU default verbose profile; ETL/CSV private. Actual sample counts decide sufficiency.',
        'acceptance': {'walk_samples_total_min': 10000, 'walk_samples_each_block_min': 1000,
                       'lost_events': 0, 'lost_buffers': 0, 'median_paired_elapsed_ratio_max': 1.05},
        'scope': 'Named deterministic N9 two-observation diagnostic only; no RNG, full52, speedup or quality claim.',
        'sampling_status': 'Stack attribution requires matching text/map and target-only normalization after collection.'})
    (output / 'native-build-manifest.json').write_bytes(identity[0])
    for name in bootstrap_names:
        target = output / 'source' / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())

    def command(label, args):
        started = time.perf_counter()
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False)
        require(len(result.stdout) + len(result.stderr) <= 1 << 20, 'collector command output bound')
        (output / (label + '.stdout.log')).write_bytes(result.stdout)
        (output / (label + '.stderr.log')).write_bytes(result.stderr)
        record = {'command': args, 'observed_exit_code': result.returncode, 'elapsed_seconds': time.perf_counter() - started}
        write(output / (label + '.process.json'), record)
        return result

    status = command('initial-wpr-status', [wpr, '-status'])
    require(status.returncode == 0 and b'WPR is not recording' in status.stdout, 'another WPR recording or unreadable status')
    records = []
    try:
        for index in range(2):
            run(executable, output / ('warmup-' + str(index)), expected)
        for block in range(BLOCKS):
            row = {'block': block, 'order': ['profiled', 'control'] if block % 2 == 0 else ['control', 'profiled']}
            for mode in row['order']:
                recording = False
                trace = output / ('private-block-' + str(block) + '.etl')
                if mode == 'profiled':
                    start = command('wpr-start-' + str(block), [wpr, '-start', 'CPU', '-filemode', '-recordtempto', str(output)])
                    if start.returncode != 0:
                        write(output / 'collector-refusal.json', {'block': block, 'observed_exit_code': start.returncode,
                            'recording_owned': False, 'native_calls_completed': 2 + sum(len(r.get(m, [])) for r in records for m in ('profiled', 'control')),
                            'scope': 'Collector start failed; no sampling or owner CPU attribution is established. No retry or cancellation of foreign sessions.'})
                        return {'status': 'collector-start-refused', 'block': block}
                    recording = True
                observations = []
                try:
                    for call in range(CALLS):
                        observations.append(run(executable, output / f'block-{block}-{mode}-{call}', expected))
                finally:
                    if recording:
                        stop = command('wpr-stop-' + str(block), [wpr, '-stop', str(trace), '-skipPdbGen'])
                        require(stop.returncode == 0, 'owned WPR recording did not stop normally; inspect receipt')
                row[mode] = observations
                if recording:
                    require(trace.is_file() and trace.stat().st_size <= 256 << 20, 'private ETL size limit')
            row['elapsed_ratio'] = sum(item['duration_seconds'] for item in row['profiled']) / sum(item['duration_seconds'] for item in row['control'])
            records.append(row); write(output / ('block-' + str(block) + '.json'), row)
            print(json.dumps({'block': block, 'elapsed_ratio': row['elapsed_ratio']}), flush=True)
        ratios = [record['elapsed_ratio'] for record in records]
        result = {'status': 'collected-awaiting-stack-attribution', 'blocks': BLOCKS, 'median_paired_elapsed_ratio': statistics.median(ratios),
                  'overhead_pass': statistics.median(ratios) <= 1.05, 'cpu_attribution_accepted': False,
                  'reason': 'Sample-count/loss/map gates remain unverified. Logical work is not CPU share.'}
        write(output / 'collection-summary.json', result)
        return result
    finally:
        require(authenticate(executable, ROOT, 'virtual-joint-two-epoch') == identity, 'candidate identity changed')
        require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == head and
                all(sha((ROOT / name).read_bytes()) == value for name, value in bootstrap.items()), 'controller changed during capture')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path); parser.add_argument('expected', type=Path); parser.add_argument('output', type=Path)
    arguments = parser.parse_args()
    result = collect(arguments.executable, arguments.expected, arguments.output)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['status'] == 'collected-awaiting-stack-attribution' else 1)
