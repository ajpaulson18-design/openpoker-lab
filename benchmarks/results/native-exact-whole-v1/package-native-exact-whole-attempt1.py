"""Archive frozen studies, independent proofs and retained development failures."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

WORK = Path(__file__).resolve().parent
AUTH_SHA = '8171ead3ba108f8200f15e85696f40d109ed894209fa7d77598780b83c1401c5'

def need(value, message):
    if not value:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=('v1', 'v2'), required=True)
    args = parser.parse_args()
    original = args.version == 'v1'
    commit = '52aa21f343aa769c4aeabf6fb7eb7c6be6816f96' if original else 'c6508947ad12a51db87bf2b41616c966ee5d339a'
    repo = WORK / ('native-exact-engine-repo' if original else 'native-exact-engine-ci-repo')
    study = WORK / ('native-exact-whole-study-' + args.version)
    target = WORK / ('native-exact-whole-evidence-' + args.version + '.zip')
    need(not target.exists(), 'Evidence archive already exists; retain it')
    source_raw = (study / 'source-before.json').read_bytes()
    source = json.loads(source_raw)
    need(source['commit'] == commit and not source['status'] and (study / 'source-after.json').read_bytes() == source_raw,
         'Frozen study source drift')
    auth_path = WORK / 'exact-selected-independent-review.py'
    need(sha(auth_path.read_bytes()) == AUTH_SHA, 'Source authentication helper drift')
    spec = importlib.util.spec_from_file_location('whole_packaging_source_auth', auth_path)
    auth = importlib.util.module_from_spec(spec); spec.loader.exec_module(auth); auth.FROZEN = commit
    authenticated = auth.source_identity(repo, source)
    manifest_raw = (study / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_raw)
    need(set(path.name for path in study.iterdir() if path.is_file()) == set(manifest['sha256']) | {'manifest.json'}, 'Study inventory drift')
    for name, expected in manifest['sha256'].items():
        need(sha((study / name).read_bytes()) == expected, 'Study bytes changed: ' + name)
    report = json.loads((study / 'report.json').read_bytes())
    need(report['failure'] is None and report['calls_completed'] == report['calls_planned'] == 18 and
         len(report['paired_identities']) == 8, 'Study incomplete')
    directories = [('study', study)]
    if original:
        directories += [('quality-review-v' + str(i), WORK / ('native-exact-whole-review-v' + str(i))) for i in (1, 2, 3)]
        directories += [('wire-strict-first-failure', WORK / 'native-exact-wire-proof-v1'),
                        ('wire-exact-tail-proof', WORK / 'native-exact-wire-proof-v2')]
        quality_dir, wire_dir = WORK / 'native-exact-whole-review-v3', WORK / 'native-exact-wire-proof-v2'
    else:
        quality_dir, wire_dir = WORK / 'native-exact-whole-review-c650-v1', WORK / 'native-exact-wire-proof-c650-v1'
        directories += [('quality-review-corrected', quality_dir), ('wire-exact-tail-proof', wire_dir)]
    need(quality_dir.is_dir() and wire_dir.is_dir(), 'Independent proofs missing')
    quality = json.loads((quality_dir / 'receipt.json').read_bytes())
    need(quality.get('status') == 'passed', 'Independent quality proof incomplete')
    wire_receipt = json.loads((wire_dir / 'receipt.json').read_bytes())
    need(wire_receipt.get('outcome') == 'passed', 'Independent wire proof incomplete')
    entries = {}
    def add(name, path):
        need(name not in entries and path.is_file() and path.stat().st_size <= 64 * 1024 * 1024,
             'Duplicate/missing/oversized evidence: ' + name)
        entries[name] = path
    for prefix, directory in directories:
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                add(prefix + '/' + path.relative_to(directory).as_posix(), path)
    for name in source['sha256']:
        path = repo / name
        if not name.startswith('benchmarks/results/') and (
                path.suffix in ('.py', '.c', '.cpp', '.h', '.hpp', '.yml', '.toml') or
                name.startswith('third_party/boost-multiprecision-1.92.0/') or
                name in subprocess.check_output(['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', commit], cwd=repo).decode().splitlines()):
            need(sha(path.read_bytes()) == source['sha256'][name], 'Source bytes differ from frozen capture')
            add('source/' + name, path)
    add('source-authentication-helper.py', auth_path)
    add('packaging-helper.py', Path(__file__))
    for path in sorted(WORK.iterdir()):
        if path.is_file() and path.suffix in ('.py', '.hpp', '.cpp', '.log', '.json', '.cmd', '.txt') and any(
            path.name.startswith(prefix) for prefix in ('native-exact-engine-', 'native-exact-graph-',
                'native-exact-cfr-', 'native-exact-wire-', 'build-native-exact-engine', 'run-native-exact-engine')):
            # Candidate executables/object files are not distributed here.
            add('development/' + path.name, path)
    for name in ('native-exact-engine-ci-ubuntu-pr-first-artifact', 'native-exact-engine-ci-ubuntu-push-first-artifact',
                 'native-exact-cfr-review-build-attempt1', 'native-exact-cfr-review-build-attempt3',
                 'native-exact-cfr-review-build-attempt4', 'native-exact-cfr-review-build-attempt5'):
        directory = WORK / name
        if directory.is_dir():
            for path in sorted(directory.rglob('*')):
                if path.is_file() and 'boost-include' not in path.parts and path.suffix in ('.json', '.log', '.cpp', '.hpp', '.cmd', '.txt'):
                    add('development/' + name + '/' + path.relative_to(directory).as_posix(), path)
    alternate = Path(r'C:\Users\pauls\Documents\Codex\work')
    if alternate.is_dir():
        for path in sorted(alternate.iterdir()):
            if path.is_file() and path.name.startswith(('native-exact-engine-', 'native-exact-graph-before')) and path.suffix in ('.cpp', '.hpp', '.log', '.json'):
                add('development/alternate-work/' + path.name, path)
    payload = {'contract': 'native-exact-whole-evidence-manifest-v1', 'version': args.version,
        'source_commit': commit, 'source_authentication': authenticated,
        'study_manifest_sha256': sha(manifest_raw), 'quality_receipt_sha256': sha((quality_dir / 'receipt.json').read_bytes()),
        'wire_receipt_sha256': sha((wire_dir / 'receipt.json').read_bytes()),
        'sha256': {name: sha(path.read_bytes()) for name, path in sorted(entries.items())},
        'scope': 'Complete frozen study plus independent saved policies/physical input-tail proof and retained errors. Raw source archive is evidence only, never executed by the reviewers. Strict graph isomorphism is false; only explicitly checked chance-only terminal tails are exact physical-game equivalent. No cross-graph floating callback/trajectory equivalence or native-heap measurement.'}
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + '\n').encode('utf-8')
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, path in sorted(entries.items()):
            raw = path.read_bytes(); need(sha(raw) == payload['sha256'][name], 'Evidence changed while packaging')
            archive.writestr(name, raw)
        archive.writestr('evidence-manifest.json', encoded)
    need(auth.source_identity(repo, source) == authenticated, 'Source drift after packaging')
    with zipfile.ZipFile(target) as archive:
        need(len(archive.namelist()) == len(entries) + 1 and archive.read('evidence-manifest.json') == encoded, 'Archive inventory mismatch')
        for name, expected in payload['sha256'].items():
            need(sha(archive.read(name)) == expected, 'Archive raw byte mismatch')
    receipt = {'version': args.version, 'source_commit': commit, 'archive': target.name,
        'archive_bytes': target.stat().st_size, 'archive_entries': len(entries) + 1,
        'archive_sha256': sha(target.read_bytes()), 'evidence_manifest_sha256': sha(encoded),
        'study_manifest_sha256': sha(manifest_raw), 'quality_receipt_sha256': payload['quality_receipt_sha256'],
        'wire_receipt_sha256': payload['wire_receipt_sha256'], 'medians_seconds': report['medians_seconds'],
        'scope': payload['scope']}
    (WORK / ('native-exact-whole-evidence-' + args.version + '-receipt.json')).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(receipt, sort_keys=True))

if __name__ == '__main__':
    main()
