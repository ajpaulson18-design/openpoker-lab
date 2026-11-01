"""Exclusive capture of one source-stable component conformance attempt."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

WORK = Path(__file__).resolve().parent
REPO = WORK / 'virtual-betting-template-repo'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def snapshot():
    names = subprocess.check_output(['git', '-C', str(REPO), 'ls-files', '--cached',
                                     '--others', '--exclude-standard', '-z']).split(b'\0')
    files = {}
    for raw_name in names:
        if raw_name:
            name = raw_name.decode('utf-8')
            path = REPO / name
            if path.is_symlink() or not path.is_file():
                raise RuntimeError('Invalid source inventory: ' + name)
            files[name] = sha(path.read_bytes())
    return {'head': subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip(),
            'status': subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain'], text=True),
            'sha256': files}


def authenticate_committed(snapshot_value, expected_head):
    if snapshot_value['head'] != expected_head or snapshot_value['status']:
        raise RuntimeError('Expected clean committed source before component mathematics')
    raw_tree = subprocess.check_output(['git', '-C', str(REPO), 'ls-tree', '-r', '-z', expected_head])
    tree = {}
    filtered = 0
    for entry in raw_tree.split(b'\0'):
        if not entry:
            continue
        metadata, raw_name = entry.split(b'\t', 1)
        mode, kind, object_id = metadata.decode().split()
        name = raw_name.decode('utf-8')
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise RuntimeError('Unsupported source tree object: ' + name)
        raw = (REPO / name).read_bytes()
        raw_oid = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if raw_oid != object_id:
            actual = subprocess.check_output(['git', '-C', str(REPO), 'hash-object', '--path', name,
                                              str(REPO / name)], text=True).strip()
            if actual != object_id:
                raise RuntimeError('Source bytes do not match committed Git filter: ' + name)
            filtered += 1
        tree[name] = object_id
    if set(tree) != set(snapshot_value['sha256']):
        raise RuntimeError('Uncommitted source files in mathematical closure')
    return {'commit': expected_head, 'files': len(tree), 'raw_or_git_filtered_verified': True,
            'filtered_paths': filtered, 'tree_blob_oid': tree}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-head')
    args = parser.parse_args()
    output = args.output.resolve()
    if output == REPO or REPO in output.parents:
        raise RuntimeError('Capture must be outside source checkout')
    output.mkdir(parents=False, exist_ok=False)
    controller_hash = sha(Path(__file__).read_bytes())
    status = {'contract': ('virtual-betting-template-committed-controls-v1' if args.expected_head
                           else 'virtual-betting-template-development-controls-v1'),
              'controller_sha256_before': controller_hash, 'commands': [],
              'failure': None, 'source_stable': False}

    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    def run(label, command, env=None):
        started = time.monotonic()
        with (output / (label + '.stdout.log')).open('xb') as out, (output / (label + '.stderr.log')).open('xb') as err:
            completed = subprocess.run(command, cwd=REPO, env=env, stdout=out, stderr=err, check=False)
        receipt = {'label': label, 'command': command, 'exit_code': completed.returncode,
                   'seconds': time.monotonic() - started}
        status['commands'].append(receipt)
        save(label + '.status.json', receipt)
        if completed.returncode:
            raise RuntimeError(label + ' failed; preserved original streams')

    before = None
    try:
        before = snapshot()
        save('source-before.json', before)
        if args.expected_head:
            save('committed-source-before.json', authenticate_committed(before, args.expected_head))
        probe_dir, control_dir = output / 'probe', output / 'compiled-controls'
        run('build-probe', [sys.executable, '-B', '-m', 'scripts.build_native_exact_four_street',
                            '--target', 'virtual-betting-template', '--output-dir', str(probe_dir)])
        run('build-controls', [sys.executable, '-B', '-m', 'scripts.build_native_exact_four_street',
                               '--target', 'virtual-betting-template-controls', '--output-dir', str(control_dir)])
        suffix = '.exe' if os.name == 'nt' else ''
        run('compiled-controls', [str(control_dir / ('native-virtual-betting-template-controls' + suffix))])
        env = os.environ.copy()
        env['OPENPOKER_NATIVE_VIRTUAL_BETTING_TEMPLATE_EXE'] = str(probe_dir / ('native-virtual-betting-template-probe' + suffix))
        for label, flags in (('normal', []), ('optimized', ['-O'])):
            run(label, [sys.executable, '-B', *flags, '-m', 'unittest',
                        'tests.test_native_virtual_betting_template', '-v'], env)
    except BaseException:
        status['failure'] = traceback.format_exc()
        (output / 'first-failure.txt').write_text(status['failure'], encoding='utf-8')
    finally:
        try:
            after = snapshot()
            save('source-after.json', after)
            if args.expected_head:
                save('committed-source-after.json', authenticate_committed(after, args.expected_head))
            status['source_stable'] = before == after
            if before != after and status['failure'] is None:
                status['failure'] = 'Source inventory changed during this attempt'
        except BaseException:
            status['source_after_error'] = traceback.format_exc()
        status['controller_sha256_after'] = sha(Path(__file__).read_bytes())
        if status['controller_sha256_after'] != controller_hash:
            status['failure'] = status['failure'] or 'Capture controller changed'
        save('completion.json', status)
    print(json.dumps({'output': str(output), 'failure': status['failure'],
                      'commands': status['commands'], 'source_stable': status['source_stable']}))
    return 1 if status['failure'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
