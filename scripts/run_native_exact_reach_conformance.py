"""One committed exact-reach component cohort, with immutable saved controls."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import time
import traceback
from scripts.build_native_exact_four_street import build, TARGETS
from scripts.run_virtual_frozen_source_only import FIRST_STAGE, source_only_command, scan_project_caches
from tests.virtual_frozen_source_guard import capture_source, verify_source, require_source_bootstrap, _git
from tests.virtual_frozen_run_control import RunClaim, run_bounded_child

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '9dbf1ef9f42c0e63be96c4391f7084b8444e009f'
ARTIFACT_BYTES = 8 << 30


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value, cap=16 << 20):
    raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    if len(raw) > cap:
        raise ValueError('component receipt byte bound')
    with path.open('xb') as output:
        output.write(raw)


def bind_build(manifest, source, target, snapshot, directory):
    required = {*TARGETS[target][1], 'scripts/build_native_exact_four_street.py',
                'third_party/boost-multiprecision-1.92.0/manifest.json',
                'third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt',
                'third_party/boost-multiprecision-1.92.0/headers.zip'}
    if (manifest.get('contract') != 'native-exact-build-v1' or manifest.get('target') != target or
            set(manifest.get('source_sha256', {})) != required):
        raise ValueError('component build declared source closure differs')
    for name, identity in manifest['source_sha256'].items():
        if name not in source['files'] or identity != source['files'][name]['raw_sha256']:
            raise ValueError('component compiled input differs from captured committed source: '+name)
    executable = Path(manifest['executable']).resolve()
    expected_name = TARGETS[target][0] + ('.exe' if os.name == 'nt' else '')
    if executable.parent != directory.resolve() or executable.name != expected_name:
        raise ValueError('component executable output path differs')
    if sha(executable) != manifest['executable_sha256'] or sha(manifest['compiler']) != manifest['compiler_sha256']:
        raise ValueError('component executable/compiler bytes differ')
    name = 'third_party/boost-multiprecision-1.92.0/manifest.json'
    if sha(snapshot/name) != source['files'][name]['raw_sha256']:
        raise ValueError('captured dependency manifest drift')
    dependency = json.loads((snapshot/name).read_bytes())
    if manifest.get('dependency_headers') != 198 or len(dependency['headers_sha256']) != 198:
        raise ValueError('component dependency inventory differs')
    include = directory/'boost-include'
    for name, identity in dependency['headers_sha256'].items():
        path = (include/name).resolve()
        if not path.is_relative_to(include.resolve()) or sha(path) != identity:
            raise ValueError('component actual extracted header differs')


def child_bootstrap(path, root, source, entry, optimized=False):
    if path.stat().st_size > 1 << 20:
        raise ValueError('component child bootstrap receipt bound')
    receipt = json.loads(path.read_bytes())
    if type(receipt.get('compiled')) is not dict or not 1 <= len(receipt['compiled']) <= 4096:
        raise ValueError('component child compiled map bound')
    if (receipt.get('root') != str(root) or receipt.get('entry_module') != entry or
            receipt.get('version') != 'project-source-only-bootstrap-v1' or
            receipt.get('initial_cache_scan', {}).get('project_bytecode_files') != 0 or
            receipt.get('final_cache_scan', {}).get('project_bytecode_files') != 0):
        raise ValueError('component child source-only entry differs')
    bootstrap_name = 'scripts/run_virtual_frozen_source_only.py'
    expected_stage = {'bootstrap_path': str(root/bootstrap_name),
                      'bootstrap_sha256': source['files'][bootstrap_name]['raw_sha256'],
                      'command_sha256': hashlib.sha256(FIRST_STAGE.encode()).hexdigest()}
    runtime = dict(require_source_bootstrap(ROOT)['interpreter'], optimize=int(optimized))
    if receipt.get('trusted_first_stage') != expected_stage or receipt.get('interpreter') != runtime:
        raise ValueError('component child trusted stage/interpreter differs')
    required = {bootstrap_name, 'scripts/build_native_exact_four_street.py'}
    if entry == 'unittest':
        required |= {'tests/test_native_exact_reach.py', 'tests/test_native_full_deck_public_chance.py',
                     'tests/test_build_native_full_deck_public_chance.py'}
    if not required <= set(receipt['compiled']):
        raise ValueError('component child compiled map incomplete')
    for name, identity in receipt['compiled'].items():
        if name not in source['files'] or identity != source['files'][name]['raw_sha256']:
            raise ValueError('component child executed source differs from committed capture')
    return receipt


def complete(output, expected_head, baseline_repo):
    if require_source_bootstrap(ROOT)['interpreter']['optimize'] != 0:
        raise ValueError('component controller requires normal parent mode')
    head = _git(ROOT, ['rev-parse', 'HEAD']).decode().strip()
    if head != expected_head:
        raise ValueError('component candidate HEAD differs')
    baseline_repo = Path(baseline_repo).resolve(strict=True)
    if _git(baseline_repo, ['rev-parse', 'HEAD']).decode().strip() != BASELINE:
        raise ValueError('component active baseline HEAD differs')
    output = Path(output).resolve()
    if output.is_relative_to(ROOT) or output.is_relative_to(baseline_repo):
        raise ValueError('component evidence must be outside source checkouts')
    if shutil.disk_usage(output.parent).free < ARTIFACT_BYTES:
        raise ValueError('component evidence free-space admission failed')
    claim = RunClaim(output, head)
    started = time.perf_counter()
    try:
        save(output/'resource-plan.json', {
            'artifact_bytes': ARTIFACT_BYTES, 'source_trees': 2,
            'source_paths_per_tree': 4096, 'source_bytes_per_tree': 1 << 30,
            'source_file_bytes': 64 << 20, 'build_output_bytes_each': 256 << 20,
            'independent_terminal_vectors_per_mode': 120960,
            'independent_component_query_work_upper_per_mode': 120960 * 500_000_000,
            'raw_legacy_requests_per_mode': 10464, 'modes': ['normal', 'optimized'],
            'scope': 'component control experiment; no cumulative training owner or game-capacity admission'})
        source = capture_source(ROOT, snapshot_directory=output/'candidate-source')
        reference = capture_source(baseline_repo, snapshot_directory=output/'baseline-source')
        if source['head'] != head or reference['head'] != BASELINE:
            raise ValueError('component source changed before capture')
        require_source_bootstrap(ROOT, source)
        save(output/'controller-bootstrap-initial.json', require_source_bootstrap(ROOT, source))
        save(output/'candidate-source.json', source)
        save(output/'baseline-source.json', reference)
        # Preserve a fresh current executable for each explicit front door.
        current = build(output/'current-legacy', target='full-deck-chance')
        bind_build(current, source, 'full-deck-chance', output/'candidate-source', output/'current-legacy')
        exact = build(output/'current-exact', target='full-deck-exact-reach-controls')
        bind_build(exact, source, 'full-deck-exact-reach-controls', output/'candidate-source', output/'current-exact')
        baseline_script = baseline_repo/'scripts/run_virtual_frozen_source_only.py'
        baseline_bytes = baseline_script.read_bytes()
        stages = [ast.literal_eval(n.value) for n in ast.parse(baseline_bytes).body
                  if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and
                     t.id == 'FIRST_STAGE' for t in n.targets)]
        if stages != [FIRST_STAGE]:
            raise ValueError('active baseline needs a different trusted first stage')
        baseline_command = source_only_command(baseline_script,
            reference['files']['scripts/run_virtual_frozen_source_only.py']['raw_sha256'],
            'scripts.build_native_exact_four_street', output/'baseline-build-bootstrap.json',
            ['--target', 'full-deck-chance', '--output-dir', str(output/'baseline-build')])
        save(output/'baseline-build-command.json', baseline_command)
        built = run_bounded_child(baseline_command,
            b'', output/'baseline-build-process', stdout_limit=2_100_000)
        if built['status'] != 'exited' or built['returncode'] != 0:
            raise ValueError('active baseline component build failed')
        child_bootstrap(output/'baseline-build-bootstrap.json', baseline_repo, reference,
                        'scripts.build_native_exact_four_street')
        baseline = json.loads((output/'baseline-build/native-exact-build-manifest.json').read_bytes())
        bind_build(baseline, reference, 'full-deck-chance', output/'baseline-source', output/'baseline-build')
        manifests = [current, exact, baseline]
        identities = [(sha(Path(m['executable']).parent/'native-exact-build-manifest.json'),
                       sha(m['executable'])) for m in manifests]
        for m in manifests:
            total = sum(p.stat().st_size for p in Path(m['executable']).parent.rglob('*') if p.is_file())
            if total > 256 << 20:
                raise ValueError('component build artifact admission exceeded')
        save(output/'build-identities.json', manifests)
        controls = []
        for label, optimized in [('normal', False), ('optimized', True)]:
            values = {
                'OPENPOKER_NATIVE_FULL_DECK_CHANCE_EXE': current['executable'],
                'OPENPOKER_NATIVE_FULL_DECK_CONTROL_DIR': str(output/(label+'-old-controls')),
                'OPENPOKER_NATIVE_EXACT_REACH_EXE': exact['executable'],
                'OPENPOKER_NATIVE_EXACT_REACH_BASELINE_EXE': baseline['executable'],
                'OPENPOKER_NATIVE_EXACT_REACH_BASELINE_REPO': str(baseline_repo),
                'OPENPOKER_NATIVE_EXACT_REACH_CONTROL_DIR': str(output/(label+'-exact-controls')),
            }
            previous = {key: os.environ.get(key) for key in values}
            os.environ.update(values)
            try:
                receipt_path = output/(label+'-bootstrap.json')
                command = source_only_command(ROOT/'scripts/run_virtual_frozen_source_only.py',
                    source['files']['scripts/run_virtual_frozen_source_only.py']['raw_sha256'],
                    'unittest', receipt_path,
                    ['tests.test_build_native_full_deck_public_chance',
                     'tests.test_native_full_deck_public_chance', 'tests.test_native_exact_reach',
                     'tests.test_native_exact_reach_conformance', 'tests.test_virtual_frozen_run_control', '-v'])
                if optimized:
                    command.insert(command.index('-c'), '-O')
                save(output/(label+'-command.json'), command)
                observed = run_bounded_child(command, b'', output/(label+'-process'),
                                             stdout_limit=2_100_000)
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            logs = (output/(label+'-process/stderr.bin')).read_bytes()
            if (observed['status'] != 'exited' or observed['returncode'] != 0 or
                    not re.search(br'^Ran 34 tests in [0-9.]+s\r?$', logs, re.MULTILINE) or
                    not re.search(br'^OK\r?$', logs, re.MULTILINE)):
                raise ValueError('component controls failed, skipped or incomplete')
            boot = child_bootstrap(receipt_path, ROOT, source, 'unittest', optimized)
            controls.append({'mode': label, 'tests': 34, 'skips': 0,
                             'actual_exit_observed': observed['actual_exit_observed'],
                             'returncode': observed['returncode'], 'compiled_sources': len(boot['compiled'])})
        for m, expected in zip(manifests, identities):
            actual = (sha(Path(m['executable']).parent/'native-exact-build-manifest.json'), sha(m['executable']))
            if actual != expected or sha(m['compiler']) != m['compiler_sha256']:
                raise ValueError('component original build/compiler changed')
        scan_project_caches(ROOT)
        scan_project_caches(baseline_repo)
        final = verify_source(ROOT, source)
        baseline_final = verify_source(baseline_repo, reference)
        require_source_bootstrap(ROOT, source)
        size = sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
        if size > ARTIFACT_BYTES - (1 << 20):
            raise ValueError('component complete evidence artifact bound')
        result = {'status': 'committed_exact_reach_component_controls_pass', 'head': head,
                  'active_baseline_head': BASELINE, 'controls': controls,
                  'candidate_source_final': final, 'baseline_source_final': baseline_final,
                  'artifact_bytes': size, 'duration_seconds': time.perf_counter()-started,
                  'scope': 'exact terminal reach and old API compatibility; training/quality gates remain open',
                  'outer_exit_and_final_bootstrap': 'required separately'}
        save(output/'result.json', result)
        claim.finish('complete', {'result': 'result.json', 'acceptance': 'outer process exit/final bootstrap required'})
        return result
    except BaseException as error:
        claim.finish('failed', {'first_error': type(error).__name__+': '+str(error)[:2048],
                               'traceback': traceback.format_exc()[-16384:]})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline-repo', type=Path, required=True)
    parser.add_argument('--expected-head', required=True)
    args = parser.parse_args()
    print(json.dumps(complete(args.output, args.expected_head, args.baseline_repo), sort_keys=True))


if __name__ == '__main__':
    main()
