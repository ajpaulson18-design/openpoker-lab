"""Verify the published target-board evidence packet, then replay it once.

This stdlib-only bootstrap authenticates the packet before importing the active
independent reader. It reconstructs only the original bounded artifact files;
archived code and package scripts are never executed.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'benchmarks' / 'results' / 'target-board-reference-v1'
CAPTURE_HEAD = '3564e4cd06f45dbd8c4863fbc01fe2837bd6994b'
FIRST_READER_HEAD = '961e7d834db5a186be951adf6a166f7d69f45931'
READER_HEAD = 'efffb416349ea80ad703d7eef291457bb6b22f63'
PACKET_COMMIT = 'f127f090c9da3a06bfc9adfb503c0d06172a2495'
PACKAGING_LOG = 'benchmarks/results/target-board-reference-v1/packaging-observation.log'
PACKAGING_LOG_BLOB = '1505c538206b0086fc0c505cf27533340404c08b'
PACKAGING_LOG_BYTES = 1245
PACKAGING_LOG_SHA256 = '5ae431fbc9a247a4c1da61a6d840e6ac15fcd197868ccff6a6ef98c96eedf786'
PACKET_MANIFEST_SHA256 = '9cd993bb460224bdfca83e7d43b22bdca0a0cce9e615385fd64150e5b47addcc'
ARCHIVES = {
    'source-and-policies.zip': ('de50e8043a79003bb0e9c71910894fdffd7efd25f9ab22f357bcf3cd6b5008a3', 7_522_469),
    'expected-uniform.zip': ('3b1f1f422519f13ce3eb3a2704c52d5cd266a7a57d5b00de98e767189ad4412d', 8_037_136),
    'expected-zero-skew.zip': ('48883d691b9ec756b1209f1aeb4f3667efee98175133e9b1c39b2b1d010d4427', 8_037_119),
    'checks-and-provenance.zip': ('97b0a9a06ff985b312275aa8f76e9be4a00a7f228bd815375b6f7bcaf8be366a', 111_038),
}
MAX_MEMBER = 8 * 1024 * 1024
MAX_ARCHIVE = 8 * 1024 * 1024
MAX_EXPANDED = 80 * 1024 * 1024
MAX_ARTIFACT = 32 * 1024 * 1024
SOURCE_NAMES = (
    'pokerlab/__init__.py', 'pokerlab/cards.py',
    'scripts/matrix_free_certificate_budget.py', 'scripts/matrix_free_four_street_rules.py',
    'scripts/preflop_validation.py', 'tests/full_deck_public_chance_reference.py',
    'tests/test_native_dyadic_policy.py', 'tests/test_native_exact_reach.py',
    'tests/virtual_betting_template_reference.py', 'tests/virtual_dyadic_training_reference.py',
    'tests/virtual_frozen_run_control.py', 'tests/virtual_frozen_update_reference.py',
    'tests/virtual_frozen_value_reference.py',
    'scripts/replay_native_frozen_policy_state.py',
    'tests/virtual_frozen_sample_reference.py', 'tests/virtual_grid_update_reference.py',
    'tests/virtual_target_board_reference.py', 'tests/test_target_board_reference.py',
    'tests/virtual_frozen_policy_input_reference.py',
    'scripts/freeze_target_board_reference.py',
)
ARTIFACT_NAMES = ({'result.json', 'input-proof.json', 'input-uniform.bin', 'input-zero-skew.bin',
                   'expected-uniform.bin', 'expected-zero-skew.bin'} |
                  {'source/' + name for name in SOURCE_NAMES})
ARCHIVE_NAMES = tuple(ARCHIVES)
READER_PATH = 'scripts/replay_target_board_reference.py'
SELF_PATH = 'scripts/replay_target_board_reference_packet.py'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str, input_bytes: bytes | None = None) -> bytes:
    process = subprocess.run(['git', *args], cwd=ROOT, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, input=input_bytes, check=False)
    require(process.returncode == 0,
            'git command failed: ' + process.stderr.decode('utf-8', 'replace')[:500])
    return process.stdout


def git_text(*args: str) -> str:
    return git(*args).decode('ascii').strip()


def bounded(path: Path, maximum: int) -> bytes:
    require(path.is_file() and not path.is_symlink(), 'missing or linked packet member: ' + str(path))
    size = path.stat().st_size
    require(size <= maximum, 'packet member exceeds its byte cap: ' + path.name)
    with path.open('rb') as stream:
        data = stream.read(maximum + 1)
    require(len(data) == size and len(data) <= maximum, 'bounded read changed size: ' + path.name)
    return data


def safe_name(name: str) -> str:
    require(type(name) is str and name and '\\' not in name and ':' not in name and
            '\x00' not in name and not name.startswith('/'),
            'archive member name grammar')
    parts = PurePosixPath(name).parts
    require(all(part not in ('', '.', '..') for part in parts), 'archive traversal member refused')
    normalized = PurePosixPath(name).as_posix()
    require(normalized == name, 'archive member path is not canonical')
    return normalized


def json_load(data: bytes, label: str):
    try:
        return json.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('invalid JSON: ' + label) from error


def authenticate_bootstrap() -> dict:
    head = git_text('rev-parse', 'HEAD')
    require(git_text('merge-base', '--is-ancestor', READER_HEAD, head) == '',
            'reader source commit is not an ancestor of this checkout')
    require(not git('status', '--porcelain', '--untracked-files=all', '--',
                    SELF_PATH, READER_PATH, PACKAGING_LOG).strip(),
            'packet bootstrap and active reader must be committed and clean')
    tree = {}
    for line in git('ls-tree', '-r', head).decode('utf-8').splitlines():
        metadata, name = line.split('\t', 1)
        tree[name] = metadata.split()[2]
    require(git_text('rev-parse', f'{PACKET_COMMIT}:{PACKAGING_LOG}') == PACKAGING_LOG_BLOB and
            tree.get(PACKAGING_LOG) == PACKAGING_LOG_BLOB,
            'committed package observation log pin mismatch')
    self_raw = bounded(ROOT / SELF_PATH, MAX_MEMBER)
    self_oid = tree.get(SELF_PATH)
    require(self_oid is not None, 'packet bootstrap is not committed')
    self_canonical = git('show', f'{head}:{SELF_PATH}')
    require(self_raw == self_canonical or
            (b'\r' not in self_canonical and self_raw == self_canonical.replace(b'\n', b'\r\n')),
            'packet bootstrap differs from clean committed source')
    reader_oid = tree.get(READER_PATH)
    require(reader_oid == git_text('rev-parse', f'{READER_HEAD}:{READER_PATH}'),
            'active replay reader blob is not the frozen final source')
    reader_raw = bounded(ROOT / READER_PATH, MAX_MEMBER)
    reader_canonical = git('show', f'{head}:{READER_PATH}')
    require(reader_raw == reader_canonical or
            (b'\r' not in reader_canonical and reader_raw == reader_canonical.replace(b'\n', b'\r\n')),
            'active replay reader differs from committed bytes')
    require(not git('status', '--porcelain', '--untracked-files=all', '--', *SOURCE_NAMES).strip(),
            'active independent math closure must be clean')
    for name in SOURCE_NAMES:
        require(name in tree and git_text('rev-parse', f'{CAPTURE_HEAD}:{name}') == tree[name],
                'active math source blob differs from the captured artifact: ' + name)
    return {'active_head': head, 'self_git_blob': self_oid, 'self_sha256': sha(self_raw),
            'reader_git_blob': reader_oid, 'reader_sha256': sha(reader_raw),
            'packaging_log_blob': PACKAGING_LOG_BLOB}


def verify_packet_directory() -> tuple[dict, dict[str, dict[str, bytes]]]:
    require(not PACKET.is_symlink() and PACKET.is_dir(), 'packet directory missing or linked')
    expected_files = {'manifest.json', 'packaging-observation.log', *ARCHIVE_NAMES}
    found = set()
    for path in PACKET.rglob('*'):
        require(not path.is_symlink(), 'packet contains a symlink')
        if path.is_file():
            relative = path.relative_to(PACKET).as_posix()
            found.add(safe_name(relative))
        elif path.is_dir():
            raise ValueError('packet root must remain flat; directories are refused')
    require(found == expected_files, 'packet root contains missing or extra files')
    manifest_raw = bounded(PACKET / 'manifest.json', 1 << 20)
    require(sha(manifest_raw) == PACKET_MANIFEST_SHA256, 'packet manifest SHA-256 mismatch')
    manifest = json_load(manifest_raw, 'manifest.json')
    require(manifest.get('schema') == 'target-board-reference-evidence-package-v1' and
            manifest.get('artifact_source_head') == CAPTURE_HEAD and
            manifest.get('reader_source_commit') == READER_HEAD,
            'packet manifest schema/source pin mismatch')
    package_log = bounded(PACKET / 'packaging-observation.log', MAX_MEMBER)
    require(len(package_log) == PACKAGING_LOG_BYTES and sha(package_log) == PACKAGING_LOG_SHA256,
            'committed package observation log bytes/hash mismatch')
    log_receipt = json_load(package_log, 'packaging-observation.log')
    require(log_receipt.get('manifest_sha256') == PACKET_MANIFEST_SHA256 and
            log_receipt.get('artifact_source_head') == CAPTURE_HEAD and
            log_receipt.get('reader_source_commit') == READER_HEAD,
            'packaging observation log does not match pinned packet')
    require(manifest.get('limits') == {
        'max_member_bytes': MAX_MEMBER, 'max_archive_bytes': MAX_ARCHIVE,
        'max_expanded_archive_bytes': MAX_EXPANDED, 'max_artifact_bytes': MAX_ARTIFACT,
        'zip_compression': 'stored to guarantee bounded archive size',
    }, 'packet byte-limit policy differs from the verifier')
    archive_manifest = manifest.get('archives')
    require(type(archive_manifest) is dict and set(archive_manifest) == set(ARCHIVE_NAMES),
            'packet archive inventory mismatch')
    expanded_total = 0
    archive_members = {}
    for name, (pinned_sha, pinned_size) in ARCHIVES.items():
        entry = archive_manifest[name]
        raw = bounded(PACKET / name, MAX_ARCHIVE)
        require(len(raw) == pinned_size and sha(raw) == pinned_sha and
                entry.get('bytes') == pinned_size and entry.get('sha256') == pinned_sha,
                'archive pinned size/hash mismatch: ' + name)
        require(entry.get('member_count') == len(entry.get('inventory', {})),
                'archive member count mismatch: ' + name)
        expected_inventory = entry['inventory']
        with zipfile.ZipFile(io.BytesIO(raw), 'r') as archive:
            infos = archive.infolist()
            names = [safe_name(info.filename) for info in infos]
            require(len(names) == len(set(names)) and set(names) == set(expected_inventory),
                    'ZIP names differ from authenticated inventory: ' + name)
            members = {}
            expanded = 0
            for info in infos:
                member = safe_name(info.filename)
                require(not info.is_dir() and info.file_size <= MAX_MEMBER and
                        info.compress_size == info.file_size and info.compress_type == zipfile.ZIP_STORED and
                        not (info.flag_bits & 1), 'ZIP member metadata outside bounded stored-file policy')
                mode = info.external_attr >> 16
                require(stat.S_IFMT(mode) in (0, stat.S_IFREG), 'ZIP nonregular member refused')
                meta = expected_inventory[member]
                require(type(meta) is dict and meta.get('bytes') == info.file_size,
                        'ZIP member declared length mismatch: ' + member)
                body = archive.read(info)
                require(len(body) == info.file_size and sha(body) == meta.get('sha256'),
                        'ZIP member content hash mismatch: ' + member)
                expanded += len(body)
                require(expanded <= MAX_EXPANDED, 'ZIP expanded limit exceeded')
                members[member] = body
            inventory_bytes = members.get('members.json')
            require(inventory_bytes is not None and sha(inventory_bytes) == expected_inventory['members.json']['sha256'],
                    'inner ZIP inventory missing or changed')
            inner = json_load(inventory_bytes, name + '/members.json')
            require(inner == {member: meta for member, meta in expected_inventory.items()
                              if member != 'members.json'},
                    'inner ZIP member inventory mismatch: ' + name)
            require(expanded == entry.get('expanded_bytes') and expanded <= MAX_EXPANDED,
                    'ZIP expanded byte receipt mismatch: ' + name)
        expanded_total += expanded
        archive_members[name] = members
    require(expanded_total <= MAX_EXPANDED, 'combined expanded packet bound')
    return manifest, archive_members


def reconstruct_artifact(manifest: dict, archive_members: dict[str, dict[str, bytes]]) -> tuple[dict[str, bytes], dict]:
    original = {}
    source_members = archive_members['source-and-policies.zip']
    for name in SOURCE_NAMES:
        key = 'artifact/source/' + name
        require(key in source_members, 'missing archived source: ' + name)
        original['source/' + name] = source_members[key]
    for name in ('artifact/input-proof.json', 'artifact/input-uniform.bin', 'artifact/input-zero-skew.bin'):
        require(name in source_members, 'missing archived policy input: ' + name)
        original[name[len('artifact/'):]] = source_members[name]
    for archive_name, members in (
        ('expected-uniform.zip', archive_members['expected-uniform.zip']),
        ('expected-zero-skew.zip', archive_members['expected-zero-skew.zip']),
    ):
        artifact_name = next(name for name in members if name.startswith('artifact/expected-'))
        original[artifact_name[len('artifact/'):]] = members[artifact_name]
    checks = archive_members['checks-and-provenance.zip']
    original['result.json'] = checks['artifact/result.json']
    require(set(original) == ARTIFACT_NAMES and len(original) == 26,
            'reconstructed artifact is not the exact 26-member original')
    art_meta = manifest.get('artifact', {})
    expected_inventory = art_meta.get('inventory')
    require(type(expected_inventory) is dict and set(expected_inventory) == ARTIFACT_NAMES,
            'global original artifact inventory mismatch')
    total = 0
    for name, body in original.items():
        require(len(body) <= MAX_MEMBER, 'reconstructed artifact member cap: ' + name)
        meta = expected_inventory[name]
        require(meta.get('bytes') == len(body) and meta.get('sha256') == sha(body),
                'reconstructed original artifact hash mismatch: ' + name)
        total += len(body)
        require(total <= MAX_ARTIFACT, 'reconstructed artifact exceeds 32 MiB')
    require(total == art_meta.get('total_bytes') == 23_513_442 and
            art_meta.get('members_including_result') == 26 and
            art_meta.get('result_sha256') == sha(original['result.json']),
            'reconstructed artifact aggregate identity mismatch')
    result = json_load(original['result.json'], 'artifact/result.json')
    require(result.get('source_head') == CAPTURE_HEAD and result.get('members') == {
        name: {'bytes': len(body), 'sha256': sha(body)} for name, body in sorted(original.items())
        if name != 'result.json'}, 'original result manifest does not cover reconstructed files')
    for zip_name, expected_profile in (('expected-uniform.zip', 'uniform'),
                                       ('expected-zero-skew.zip', 'zero-skew')):
        zip_members = archive_members[zip_name]
        profile_key = 'metadata/profile-' + expected_profile + '.json'
        saved_profile = json_load(zip_members[profile_key], profile_key)
        profile = next(row for row in result['profiles'] if row['profile'] == expected_profile)
        require(saved_profile == profile, 'table archive profile metadata mismatch: ' + expected_profile)
    return original, checks


def verify_execution_history(manifest: dict, checks: dict[str, bytes]) -> dict:
    execution = json_load(checks['execution/first-and-refused-invocations.json'], 'execution receipt')
    require(execution.get('source_head') == CAPTURE_HEAD and
            execution.get('result_sha256') == manifest['artifact']['result_sha256'] and
            execution.get('result_bytes') == 26_708 and
            execution.get('total_bytes') == 23_513_442 and execution.get('members_including_result') == 26 and
            execution.get('all_members_hash_matched') is True,
            'artifact execution receipt is not bound to frozen payload')
    first = execution.get('first_invocation', {})
    second = execution.get('second_invocation', {})
    provenance = execution.get('console_provenance', {})
    require(first.get('tool_session') == 99512 and first.get('observed_python_exit') == 0 and
            second.get('observed_python_exit') == 1 and second.get('mathematical_calls_entered') == 0 and
            'fresh directory' in second.get('refusal', '') and
            provenance.get('first_console_log_overwritten_by_second_refusal') is True and
            provenance.get('original_console_log_available') is False,
            'first-success / second-refusal provenance changed')
    refusal = checks['execution/available-console-is-second-refusal.log']
    require(b'destination must be a fresh directory' in refusal,
            'available console file is not the second refused invocation')
    saved_result = json_load(checks['artifact/result.json'], 'result.json')
    receipt_profiles = execution.get('profiles', [])
    result_profiles = {row['profile']: row for row in saved_result.get('profiles', [])}
    require(tuple(row.get('profile') for row in receipt_profiles) == ('uniform', 'zero-skew'),
            'execution receipt profile order')
    for row in receipt_profiles:
        reference = result_profiles[row['profile']]
        require(row.get('rows') == reference.get('rows') == 24_420 and
                row.get('slots') == reference.get('slots') == 58_164 and
                row.get('positive_board_calls') == reference.get('positive_board_calls') == 60 and
                row.get('input_policy') == reference.get('input_policy') and
                row.get('expected_table') == reference.get('expected_table') and
                row.get('root') == reference.get('root'),
                'execution receipt profile differs from frozen result: ' + row['profile'])
    return {'first_exit': 0, 'first_session': 99512, 'second_exit': 1,
            'second_math_calls': 0, 'original_first_console_available': False}


def comparable(report: dict) -> dict:
    return {key: value for key, value in report.items()
            if key not in ('active_replay_head', 'reader_bootstrap')}


def replay_packet() -> dict:
    require(sys.dont_write_bytecode and sys.pycache_prefix is not None,
            'packet replay requires bytecode-disabled Python and a fresh cache prefix')
    cache = Path(sys.pycache_prefix)
    if cache.exists():
        require(cache.is_dir() and not any(cache.iterdir()), 'packet replay cache prefix is not empty')
    bootstrap = authenticate_bootstrap()
    manifest, archive_members = verify_packet_directory()
    original, checks = reconstruct_artifact(manifest, archive_members)
    history = verify_execution_history(manifest, checks)
    require(manifest['reader_source'].get('reader_source_commit') == READER_HEAD and
            manifest['reader_source'].get('reader_git_blob') == bootstrap['reader_git_blob'],
            'packet reader source pin mismatch')
    packed_reader = archive_members['source-and-policies.zip']['reader/scripts/replay_target_board_reference.py']
    reader_current = bounded(ROOT / READER_PATH, MAX_MEMBER)
    require(sha(packed_reader) == manifest['reader_source'].get('reader_sha256') and
            (reader_current == packed_reader or
             (b'\r' not in packed_reader and reader_current == packed_reader.replace(b'\n', b'\r\n'))),
            'current reader source differs from authenticated packet copy')
    legacy_reader = archive_members['source-and-policies.zip']['reader/development/replay_target_board_reference-961e7d8.py']
    legacy_canonical = git('show', f'{FIRST_READER_HEAD}:{READER_PATH}')
    legacy_blob = git_text('rev-parse', f'{FIRST_READER_HEAD}:{READER_PATH}')
    require(sha(legacy_reader) == manifest['reader_source'].get('first_reader_sha256') and
            legacy_reader == legacy_canonical and
            git('hash-object', '--stdin', input_bytes=legacy_canonical).decode('ascii').strip() == legacy_blob,
            'archived development reader hash mismatch')
    final_canonical = git('show', f'{READER_HEAD}:{READER_PATH}')
    final_blob = git_text('rev-parse', f'{READER_HEAD}:{READER_PATH}')
    require(packed_reader == final_canonical and
            sha(final_canonical) == manifest['reader_source'].get('reader_sha256') and
            final_blob == manifest['reader_source'].get('reader_git_blob') and
            git('hash-object', '--stdin', input_bytes=final_canonical).decode('ascii').strip() == final_blob,
            'archived final reader does not match its frozen Git source')
    require(sha(archive_members['source-and-policies.zip']['source-differences/reader-added.patch']) ==
            manifest['reader_source'].get('first_reader_patch_sha256') and
            sha(archive_members['source-and-policies.zip']['source-differences/reader-line-ending-portability-fix.patch']) ==
            manifest['reader_source'].get('portability_patch_sha256') and
            sha(archive_members['source-and-policies.zip']['source-differences/reader-captured-to-final.patch']) ==
            manifest['reader_source'].get('reader_patch_sha256'), 'source difference patch hashes mismatch')
    source_members = archive_members['source-and-policies.zip']
    require(source_members['source-differences/reader-added.patch'] ==
            git('diff', '--binary', CAPTURE_HEAD, FIRST_READER_HEAD, '--', READER_PATH) and
            source_members['source-differences/reader-line-ending-portability-fix.patch'] ==
            git('diff', '--binary', FIRST_READER_HEAD, READER_HEAD, '--', READER_PATH) and
            source_members['source-differences/reader-captured-to-final.patch'] ==
            git('diff', '--binary', CAPTURE_HEAD, READER_HEAD, '--', READER_PATH),
            'archived source patches differ from the exact pinned Git transitions')

    # All four archive hashes, all member hashes, source pins, and original
    # artifact members are authenticated before importing the current reader.
    with tempfile.TemporaryDirectory(prefix='target-board-packet-replay-') as temp:
        root = Path(temp)
        for name, body in original.items():
            path = root / PurePosixPath(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(body)
        require(len([path for path in root.rglob('*') if path.is_file()]) == 26,
                'temporary artifact reconstruction count')
        from scripts.replay_target_board_reference import replay
        current = replay(root)

    final_normal = json_load(checks['checks/independent-replay/normal.json'], 'saved final normal report')
    final_optimized = json_load(checks['checks/independent-replay/optimized.json'], 'saved final optimized report')
    dev_normal = json_load(checks['checks/development-reader-961e7d8/normal.json'], 'saved development normal report')
    dev_optimized = json_load(checks['checks/development-reader-961e7d8/optimized.json'], 'saved development optimized report')
    reports = (final_normal, final_optimized, dev_normal, dev_optimized)
    require(all(comparable(current) == comparable(report) for report in reports),
            'fresh packet replay differs from one or more retained reports')
    require(current.get('status') == 'all-target-board-expectations-exact' and
            current.get('artifact_members') == 25 and current.get('authenticated_sources') == 20 and
            current.get('native_calls') == current.get('rng_calls') == current.get('training_iterations') == 0 and
            current.get('quality_gate') is None, 'replayed scope/call boundary')
    require(authenticate_bootstrap() == bootstrap,
            'active HEAD, bootstrap, reader, or package-log provenance changed during replay')
    final_manifest, _final_archives = verify_packet_directory()
    require(final_manifest == manifest,
            'packet manifest or archive inventory changed during replay')
    return {
        'status': 'authenticated-target-board-packet-replayed-exactly',
        'packet_manifest_sha256': PACKET_MANIFEST_SHA256,
        'packaging_log_sha256': PACKAGING_LOG_SHA256,
        'archive_sha256': {name: values[0] for name, values in ARCHIVES.items()},
        'active_checkout_head': bootstrap['active_head'],
        'replay_source_head_pin': READER_HEAD,
        'captured_artifact_source_head': CAPTURE_HEAD,
        'reconstructed_original_members': len(original),
        'reconstructed_original_bytes': manifest['artifact']['total_bytes'],
        'replay_reports_compared': 4,
        'historical_execution': history,
        'profiles': current['profiles'],
        'archived_source_executed': False,
        'native_calls': 0, 'rng_calls': 0, 'training_iterations': 0,
        'quality_gate': None,
        'scope': current['scope'],
    }


def main() -> None:
    print(json.dumps(replay_packet(), sort_keys=True))


if __name__ == '__main__':
    main()
