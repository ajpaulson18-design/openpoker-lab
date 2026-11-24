"""Authenticate immutable joint-foundation packets, then replay current math.

Stdlib-only bootstrap. No native executable or archived Python is executed.
Only the two primary matrices receive fresh numerical replay; other records
receive source/build/process/parity authentication with that scope explicit.
"""
import argparse
import ast
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'benchmarks/results/joint-two-epoch-v1'
MANIFEST_PIN = ('4befe99bbcf1074be6de579c19a23fab5626e1a40151edc9859d1794d44e6435', 34151)
PACKAGING_PIN = ('5ce4010c5f41dfecc7fb54f71c51e2ca454bbf2ad8835180bf5aec09d587a2ce', 46167)
# sha256, compressed bytes, members, expanded bytes, inner manifest sha256.
PINS = {
    'normal': ('96231c832f3d5712ddb1b207656ab58775ed92ec2085e281ab49ab1ca42b220f', 1118667, 149, 5310339, '212f1743b9b484e80eb043b4a718042b0e80a8a83de386e90bc97f05175cb424'),
    'optimized': ('7a8970a3dd11eb9003de684ded2de2307bcb62cef8e4b99a6848aad680b5ef88', 1118685, 149, 5310361, 'bfdfa2e267e20cca14d01995e68a8e0269701ab9154e44d2e508a492b225dc86'),
    'components': ('a82281d7232e5d96f3ea622e1fa9c6870dc85fc88df9ca593172ef07d6b632f4', 2806242, 189, 5264534, '647b4567311cce3991220b7ca56abe30146658bbdd2e27a5c2ee3002f22c1694'),
    'legacy-prepared-normal': ('cc33cfaf26cc33914af7eeaf69d61cf7c14ca0a7826b631d321e052f0f0a158f', 3354159, 602, 15608329, '1180e1fd5d4762e22d82a58e25d09e85ec923478c89c109131e72b623c8e6eaa'),
    'legacy-prepared-optimized': ('1f5e404a9dd4e633c9a1f7fc730cca6aac621d168a89f4491a85f20fcc1eb543', 3357646, 602, 15610074, 'b569e419f9f86fa0b8b3b6da83f3839d1d3a5b0449bfa2a77af9177a291cf890'),
    'legacy-epoch': ('d63d1811d6e1afc25fb125845cdf3b534dc6e2329f08eb2517709bc6f8580f1d', 1576915, 112, 3672706, 'd3bc8a401a5e923eaab8dbae4a01e6ef3d261aba23966c888fa13c9ad799249f'),
    'legacy-public': ('495e8d9991f83a53be2d260c6862d13c671ab57e26f666d4865a430e49bfa271', 2030867, 274, 7945407, '1b882d7ffa9f0d3d22fe9d6f4ec994b36b3ae9a95f1152a4d3bdf65829c5e0d9'),
    'development': ('0fc66195da231c8ce7508409002856c8e3d73d0b4f8110cd24b4cc5ad333e362', 2164722, 150, 4251965, '1f03ff822ac6e6d81661e381d1cbfc0a88a13b7443b44740331a8e04713c3eee'),
}
MAX_MEMBER = 8 << 20
MAX_ARCHIVE = 8 << 20
MAX_EXPANDED = 80 << 20  # Also bounds the aggregate of all eight archives.
BOOTSTRAP = ('scripts/replay_joint_two_epoch_packet.py', 'scripts/replay_joint_two_epoch.py',
             'scripts/replay_native_grid_raw.py', 'scripts/replay_native_frozen_policy_state.py')
HISTORICAL_MIXED = {
    'native/training_phase_profile.hpp': ('b57fd7ed3ef7eb9bb711816b456abf53d603cb6d84ccf72594412bf279f3c022', '3000ccc8ee4d0dd89bf86153fffd876efa4f54aa'),
    'native/training_phase_trace.hpp': ('ec33454507a44d7cafd4f5da13eaffbc79da4cbd8e9f2ff190c16059031b52ee', 'e74f23f184fdee0b48d59c6cb21b4efa4258d617'),
}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(body):
    return sha256(body).hexdigest()


def bounded(path, cap):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= cap, 'packet file boundary')
    with path.open('rb') as source:
        raw = source.read(cap + 1)
    require(len(raw) <= cap and len(raw) == path.stat().st_size, 'packet file changed during read')
    return raw


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate packet JSON key')
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique)


def safe_name(name):
    require(type(name) is str and name and name.isascii() and '\\' not in name and ':' not in name and '\0' not in name,
            'packet POSIX path grammar')
    path = PurePosixPath(name)
    require(str(path) == name and not path.is_absolute() and '..' not in path.parts,
            'packet path boundary')
    require(path.suffix.lower() not in {'.exe', '.obj', '.o', '.dll', '.so', '.dylib', '.pdb', '.lib', '.exp', '.pyc'},
            'packet executable/object member refused')
    return name


def git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(result.returncode == 0 and len(result.stdout) <= MAX_MEMBER, 'packet read-only Git lookup failed')
    return result.stdout


def variants(canonical):
    values = {digest(canonical)}
    if b'\r' not in canonical:
        values.add(digest(canonical.replace(b'\n', b'\r\n')))
    return values


def authenticate_bootstrap():
    require(not git('status', '--porcelain', '--untracked-files=all', '--', *BOOTSTRAP),
            'commit packet replay bootstrap before execution')
    head = git('rev-parse', 'HEAD').decode('ascii').strip()
    require(re.fullmatch('[0-9a-f]{40}', head) is not None, 'active packet source HEAD')
    hashes = {}
    for name in BOOTSTRAP:
        raw = bounded(ROOT / name, 2 << 20)
        require(digest(raw) in variants(git('show', head + ':' + name)), 'active packet bootstrap byte drift')
        hashes[name] = digest(raw)
    return {'head': head, 'raw_sha256': hashes}


def authenticate_packet_files(packet):
    expected = {'manifest.json', 'packaging-observation.log', *(name + '.zip' for name in PINS)}
    require(packet.is_dir() and not packet.is_symlink() and {p.name for p in packet.iterdir()} == expected and
            all(p.is_file() and not p.is_symlink() for p in packet.iterdir()), 'packet exact flat ten-file inventory')
    pins = {'manifest.json': MANIFEST_PIN, 'packaging-observation.log': PACKAGING_PIN,
            **{name + '.zip': value[:2] for name, value in PINS.items()}}
    result = {}
    for name, (sha, size) in pins.items():
        body = bounded(packet / name, MAX_ARCHIVE)
        require((digest(body), len(body)) == (sha, size), 'literal packet file pin: ' + name)
        result[name] = sha
    return result


def open_archives(packet):
    summary = decode(bounded(packet / 'manifest.json', 1 << 20))
    require(summary['version'] == 'joint-two-epoch-package-v1' and summary['native_calls'] == 0 and
            summary['archived_source_executed'] is False and summary['publication_performed'] is False,
            'packet packaging scope')
    expected_records = [{'file': name + '.zip', 'sha256': pin[0], 'bytes': pin[1], 'members': pin[2],
                         'expanded_bytes': pin[3], 'manifest_sha256': pin[4]} for name, pin in PINS.items()]
    require(summary['archives'] == expected_records, 'literal outer/inner archive pin agreement')
    expanded_all = 0; loaded = {}; manifests = {}
    for label, pin in PINS.items():
        files = {}
        with zipfile.ZipFile(BytesIO(bounded(packet / (label + '.zip'), MAX_ARCHIVE))) as archive:
            infos = archive.infolist()
            require(len(infos) == pin[2] and not archive.comment, 'packet ZIP count/comment')
            require(sum(info.file_size for info in infos) == pin[3], 'packet ZIP expanded pin')
            expanded_all += pin[3]; require(expanded_all <= MAX_EXPANDED, 'aggregate eight-archive expanded boundary')
            folded = set()
            for info in infos:
                name = safe_name(info.filename); mode = info.external_attr >> 16
                require(name not in files and name.casefold() not in folded and info.create_system == 3 and
                        stat.S_ISREG(mode) and not stat.S_ISLNK(mode) and not info.is_dir() and
                        info.compress_type == zipfile.ZIP_DEFLATED and not info.flag_bits & 1 and
                        not info.extra and not info.comment and 0 <= info.file_size <= MAX_MEMBER,
                        'packet ZIP regular/deflate/member boundary')
                folded.add(name.casefold())
                with archive.open(info) as stream:
                    body = stream.read(MAX_MEMBER + 1)
                require(len(body) == info.file_size, 'packet bounded inflate mismatch')
                files[name] = body
        require(digest(files['MANIFEST.json']) == pin[4], 'literal inner manifest pin')
        manifest = decode(files['MANIFEST.json'])
        require(manifest['version'] == 'joint-two-epoch-archive-v1' and manifest['archive'] == label and
                manifest['limits'] == {'member_bytes': MAX_MEMBER, 'expanded_bytes': MAX_EXPANDED, 'archive_bytes': MAX_ARCHIVE},
                'inner manifest scope/caps')
        inventory = manifest['members']
        require(len(inventory) == len(files) - 1 and len({entry['path'] for entry in inventory}) == len(inventory) and
                {entry['path'] for entry in inventory} == set(files) - {'MANIFEST.json'}, 'inner complete member inventory')
        for entry in inventory:
            body = files[safe_name(entry['path'])]
            require((len(body), digest(body)) == (entry['bytes'], entry['sha256']), 'inner member byte/hash identity')
        require(digest(files['package/package_joint_two_epoch1.py']) == summary['packager_sha256'],
                'external packager captured-byte identity')
        loaded[label] = files; manifests[label] = manifest
    return summary, loaded, manifests, expanded_all


class GitObjects:
    def __init__(self):
        self.trees = {}; self.bodies = {}; self.bytes = 0

    def tree(self, head):
        require(type(head) is str and re.fullmatch('[0-9a-f]{40}', head) is not None, 'captured source HEAD grammar')
        if head not in self.trees:
            self.trees[head] = {line.split('\t', 1)[1]: line.split('\t', 1)[0].split()[2]
                                for line in git('ls-tree', '-r', head).decode('utf-8').splitlines()}
        return self.trees[head]

    def body(self, head, name):
        safe_name(name); self.tree(head)
        key = head, name
        if key not in self.bodies:
            raw = git('show', head + ':' + name)
            self.bytes += len(raw)
            require(len(self.bodies) < 4096 and self.bytes <= MAX_EXPANDED, 'canonical Git source cache boundary')
            self.bodies[key] = raw
        return self.bodies[key]


def source_bytes_match(raw, canonical, name, blob):
    return digest(raw) in variants(canonical) or HISTORICAL_MIXED.get(name) == (digest(raw), blob)


def build_source_links(native, source_map):
    require(type(native['source_sha256']) is dict and 0 < len(native['source_sha256']) <= 128 and
            set(native.get('source_lf_sha256', {})) <= set(native['source_sha256']), 'complete native build source inventory')
    for name, expected in native['source_sha256'].items():
        safe_name(name); require(name in source_map, 'native source omitted from authenticated closure')
        raw = source_map[name]
        lf = raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        require(digest(raw) == expected or native.get('source_lf_sha256', {}).get(name) == digest(lf),
                'native build/captured raw-source link')


def original_source(files, prefix, recorded, objects):
    base = prefix + '/'
    identity_raw = files[base + 'source-identity.json']; identity = decode(identity_raw)
    head = identity['head']; hashes = identity['raw_sha256']; blobs = identity['committed_blobs']
    require(0 < len(hashes) <= 128 and set(hashes) == set(blobs), 'captured raw/blob source inventories')
    source_prefix = base + 'source/'
    require({name[len(source_prefix):] for name in files if name.startswith(source_prefix)} == set(hashes),
            'captured source tree has missing or extra members')
    source_map = {}
    for name, sha in hashes.items():
        raw = files[source_prefix + safe_name(name)]
        require(digest(raw) == sha and objects.tree(head).get(name) == blobs[name] and
                source_bytes_match(raw, objects.body(head, name), name, blobs[name]), 'original captured raw/Git source mismatch')
        source_map[name] = raw
    native_raw = files[base + 'native-build-manifest.json']; native = decode(native_raw)
    build_source_links(native, source_map)
    require(recorded == {'kind': 'original-captured-raw-source', 'head': head, 'files': len(hashes),
                         'source_identity_sha256': digest(identity_raw), 'native_manifest_sha256': digest(native_raw),
                         'native_executable_sha256': native['executable_sha256']}, 'inner source authentication report')
    build_base = 'build/' if prefix == 'matrix' else (
        prefix.rsplit('/', 1)[0] + '/build/' if prefix.endswith(('/normal', '/optimized')) else base + 'build/')
    require(files[build_base + 'native-exact-build-manifest.json'] == native_raw, 'captured run/build manifest raw-byte agreement')
    if base + 'native-identity.json' in files:
        require(decode(files[base + 'native-identity.json']) == {
            'manifest_sha256': digest(native_raw), 'executable_sha256': native['executable_sha256']},
            'captured executable/build hash link')
    return head, source_map


def reconstructed_source(files, prefix, recorded, objects):
    record = decode(files[prefix + '/CANONICAL-GIT-RECONSTRUCTION.json'])
    require(record['version'] == 'canonical-git-reconstruction-v1' and
            record['original_raw_checkout_captured'] is False and
            record['source_context_is_execution_attestation'] is False and bool(record['explanation']),
            'canonical reconstruction must remain distinct from raw capture')
    head = record['head']; entries = record['files']
    require(0 < len(entries) <= 128 and len({entry['path'] for entry in entries}) == len(entries), 'canonical complete source inventory')
    source_prefix = prefix + '/source/'
    require({name[len(source_prefix):] for name in files if name.startswith(source_prefix)} == {entry['path'] for entry in entries},
            'canonical source missing or extra members')
    native_member = prefix.rsplit('/', 1)[0] + '/build/native-exact-build-manifest.json'
    native = decode(files[native_member]) if native_member in files else None
    native_hashes = {}
    for entry in entries:
        name = safe_name(entry['path']); raw = files[source_prefix + name]; canonical = objects.body(head, name)
        require(raw == canonical and (len(raw), digest(raw), objects.tree(head).get(name)) ==
                (entry['bytes'], entry['sha256'], entry['blob']), 'canonical reconstructed source/Git object mismatch')
        expected = entry['recorded_native_raw_sha256']
        if expected is not None:
            require(native is not None and native['source_sha256'].get(name) == expected and
                    (expected in variants(canonical) or HISTORICAL_MIXED.get(name) == (expected, entry['blob']) or
                     native.get('source_lf_sha256', {}).get(name) == digest(canonical.replace(b'\r\n', b'\n'))),
                    'canonical/captured native checkout-form link')
            native_hashes[name] = expected
    require(recorded == {'prefix': prefix, 'head': head, 'files': len(entries), 'kind': 'canonical-git-reconstruction-only'},
            'canonical reconstruction inner report')
    if native_hashes:
        require(native_hashes == native['source_sha256'], 'canonical complete native manifest linkage')
    return head


def process_receipts(files):
    result = {}; sizes = {}
    for name, body in files.items():
        if not name.endswith('/process.json'):
            continue
        prefix = name[:-len('/process.json')]; receipt = decode(body)
        require(receipt['status'] == 'exited' and receipt['actual_exit_observed'] is True and
                type(receipt['returncode']) is int and receipt['automatic_retries'] == 0 and not receipt['failures'] and
                len(receipt['streams']) == 2, 'actual process exit/cumulative stream receipt')
        request = files[prefix + '/request.bin']
        require(receipt['request_sha256'] == digest(request), 'captured request identity')
        hashes = []
        for filename, stream in zip(('stdout.bin', 'stderr.bin'), receipt['streams']):
            raw = files[prefix + '/' + filename]
            require(stream['observed_bytes'] == stream['saved_bytes'] == len(raw) and stream['sha256'] == digest(raw),
                    'captured process stream bytes/hash')
            hashes.append(digest(raw))
        result[prefix] = {'exit': receipt['returncode'], 'stdout_sha256': hashes[0], 'stderr_sha256': hashes[1]}
        sizes[prefix] = len(files[prefix + '/stdout.bin'])
    return result, sizes


def authenticate_evidence(loaded, manifests, objects):
    reports = {}; processes = {}; sizes = {}; primary = {}
    for label, files in loaded.items():
        records = manifests[label]['source_and_process_authentication']
        originals = {entry['prefix']: entry['source'] for entry in records if 'source' in entry}
        reconstructed = {entry['prefix']: entry for entry in records if entry.get('kind') == 'canonical-git-reconstruction-only'}
        require(len(originals) == sum('source' in entry for entry in records) and
                len(reconstructed) == sum(entry.get('kind') == 'canonical-git-reconstruction-only' for entry in records),
                'duplicate source authentication declaration')
        actual_original = {name[:-len('/source-identity.json')] for name in files if name.endswith('/source-identity.json')}
        actual_reconstructed = {name[:-len('/CANONICAL-GIT-RECONSTRUCTION.json')] for name in files
                                if name.endswith('/CANONICAL-GIT-RECONSTRUCTION.json')}
        require(set(originals) == actual_original and set(reconstructed) == actual_reconstructed,
                'every introduced original/canonical source closure must be authenticated')
        heads = []
        for prefix, record in originals.items():
            head, source_map = original_source(files, prefix, record, objects); heads.append(head)
            if label in ('normal', 'optimized'):
                require(prefix == 'matrix' and head == '8c42ee1410992bd5be8deb4ab65dd4ec649a1135', 'primary captured source head')
                primary[label] = source_map
        for prefix, record in reconstructed.items():
            heads.append(reconstructed_source(files, prefix, record, objects))
        for member in files:
            if '/source/' in member:
                require(any(member.startswith(prefix + '/source/') for prefix in (*originals, *reconstructed)),
                        'unattributed source subtree')
        actual, byte_counts = process_receipts(files)
        expected = {}
        for entry in records:
            for relative, record in entry.get('processes', {}).items():
                path = entry['prefix'] + '/' + relative
                require(path not in expected, 'duplicate declared process')
                expected[path] = record
        require(actual == expected, 'all process inventories must equal authenticated inner records')
        # Legacy Prepared lacked raw source capture; retain and verify its
        # per-invocation binary/build identity separately from reconstruction.
        for member in files:
            if not member.endswith('/native-identity.json') or not member.startswith('joint-legacy-prepared1/'):
                continue
            identity = decode(files[member]); native_raw = files['joint-legacy-prepared1/build/native-exact-build-manifest.json']
            native = decode(native_raw)
            require(identity['expected_sha256'] == identity['before_sha256'] == identity['after_sha256'] == native['executable_sha256'] and
                    identity['captured_manifest_sha256'] == digest(native_raw), 'legacy Prepared observed binary/build link')
        if label.startswith('legacy-prepared-'):
            require({member[:-len('/native-identity.json')] for member in files if member.endswith('/native-identity.json')} == set(actual),
                    'every legacy Prepared invocation requires its observed native identity')
        if label == 'development':
            scope = decode(files['metadata/development-scope.json'])
            refusal = decode(files['packaging-cap-refusal/classification.json'])
            require(scope['failures_preserved'] == 4 and scope['raw_or_policy_numerical_failure_claimed'] is False and
                    refusal['limits_raised'] is False and refusal['output_directory_created'] is False and refusal['native_calls'] == 0 and
                    refusal['failed_packager_sha256'] == digest(files['packaging-cap-refusal/package_joint_two_epoch1-first.py.txt']) and
                    refusal['failure_log_sha256'] == digest(files['packaging-cap-refusal/joint-two-epoch-package1.log']),
                    'development compile/fixture/packaging failures retain their original scope')
        reports[label] = {'status': 'source-build-process-authenticated', 'original_source_closures': len(originals),
                          'canonical_reconstructions': len(reconstructed), 'source_heads': sorted(set(heads)),
                          'process_receipts': len(actual), 'fresh_numerical_replay': label in ('normal', 'optimized')}
        processes[label] = actual; sizes[label] = byte_counts
    require(set(primary) == {'normal', 'optimized'} and primary['normal'] == primary['optimized'], 'primary cross-mode source agreement')
    return reports, processes, sizes, primary['normal']


def authenticate_parity(summary, loaded, processes, sizes):
    recorded = decode(loaded['legacy-epoch']['checks/joint-two-epoch-parity1.json'])
    require(recorded == summary['parity'] and recorded['status'] == 'all-retained-native-streams-exact', 'packet parity metadata link')
    mappings = {
        'joint-two-epoch1': (('normal', 'matrix'), ('optimized', 'matrix')),
        'joint-chance1': (('components', 'joint-chance1/normal'), ('components', 'joint-chance1/optimized')),
        'joint-epoch3': (('components', 'joint-epoch3/normal'), ('components', 'joint-epoch3/optimized')),
        'joint-legacy-prepared1': (('legacy-prepared-normal', 'joint-legacy-prepared1/normal'),
                                   ('legacy-prepared-optimized', 'joint-legacy-prepared1/optimized')),
        'joint-legacy-epoch1': (('legacy-epoch', 'joint-legacy-epoch1/normal'), ('legacy-epoch', 'joint-legacy-epoch1/optimized')),
        'joint-legacy-public1': (('legacy-public', 'joint-legacy-public1/normal'), ('legacy-public', 'joint-legacy-public1/optimized')),
        'historical-public-exact': (('legacy-public', 'joint-legacy-public1/normal'),),
    }
    entries = recorded['comparisons']
    require(len(entries) == 7 and {entry['label'] for entry in entries} == set(mappings), 'complete seven-part parity inventory')
    for entry in entries:
        for archive, prefix in mappings[entry['label']]:
            actual = {key[len(prefix) + 1:]: value for key, value in processes[archive].items() if key.startswith(prefix + '/')}
            require(actual == entry['requests'] and len(actual) == entry['observed_requests'] and
                    sum(size for key, size in sizes[archive].items() if key.startswith(prefix + '/')) == entry['stdout_bytes'],
                    'parity receipt differs from archived observed streams')
    return {'comparisons': 7, 'current_normal_optimized_comparisons': 6,
            'historical_public_scope': 'Receipt linked to current archived streams; historical original packet not freshly replayed.'}


def metadata_tuple(raw, assignment, environment=None):
    """Read literal source-list metadata via AST; never execute archived code."""
    environment = environment or {}
    for statement in ast.parse(raw).body:
        if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == assignment
                                                     for target in statement.targets):
            require(isinstance(statement.value, ast.Tuple), 'literal source-list tuple required')
            result = []
            for entry in statement.value.elts:
                if isinstance(entry, ast.Starred) and isinstance(entry.value, ast.Name):
                    result.extend(environment[entry.value.id])
                else:
                    result.append(ast.literal_eval(entry))
            require(all(type(name) is str for name in result), 'source-list metadata strings')
            return tuple(result)
    raise ValueError('missing literal source inventory: ' + assignment)


def authenticate_current_math(captured):
    oracle = metadata_tuple(captured['scripts/replay_native_frozen_policy_state.py'], 'ORACLE_SOURCES')
    base = metadata_tuple(captured['scripts/replay_native_grid_raw.py'], 'MATH', {'ORACLE_SOURCES': oracle})
    new = metadata_tuple(captured['scripts/replay_joint_two_epoch.py'], 'NEW_MATH')
    names = tuple(dict.fromkeys((*base, *new)))
    require(len(names) <= 128 and set(names) <= set(captured), 'complete current numeric dependency inventory')
    require(not git('status', '--porcelain', '--untracked-files=all', '--', *names),
            'current independent numeric closure must be committed and clean')
    hashes = {}
    for name in names:
        raw = bounded(ROOT / safe_name(name), 2 << 20)
        canonical = git('show', '8c42ee1410992bd5be8deb4ab65dd4ec649a1135:' + name)
        # Admit the exact Git checkout forms while preserving each recorded
        # raw source hash. Arbitrary mixed-newline rewrites are not admitted.
        require(digest(raw) in variants(canonical), 'current independent numeric source drift')
        hashes[name] = digest(raw)
    return hashes


def materialize_primary(files, directory):
    for name, raw in files.items():
        if name.startswith(('matrix/', 'build/')):
            target = directory.joinpath(*PurePosixPath(safe_name(name)).parts)
            require(directory.resolve() in target.resolve().parents, 'private extraction path boundary')
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as output:
                output.write(raw)


def replay_packets(packet=PACKET):
    packet = Path(packet)
    bootstrap = authenticate_bootstrap()
    loaded_project = [name for name, module in tuple(sys.modules.items()) if name != '__main__' and
                      getattr(module, '__file__', None) and ROOT in Path(module.__file__).resolve().parents]
    require(not loaded_project, 'packet replay requires a fresh Python process')
    packet_before = authenticate_packet_files(packet)
    summary, loaded, manifests, expanded = open_archives(packet)
    evidence, processes, sizes, captured = authenticate_evidence(loaded, manifests, GitObjects())
    parity = authenticate_parity(summary, loaded, processes, sizes)
    math_before = authenticate_current_math(captured)
    previous = sys.pycache_prefix, sys.dont_write_bytecode
    with TemporaryDirectory(prefix='joint-packet-current-cache-', dir=ROOT.parent) as cache:
        sys.pycache_prefix = cache; sys.dont_write_bytecode = True
        try:
            # Only after every archive/source/process/current-math check above.
            from scripts.replay_joint_two_epoch import replay
            results = {}
            for mode in ('normal', 'optimized'):
                with TemporaryDirectory(prefix='joint-packet-' + mode + '-', dir=ROOT.parent) as temporary:
                    directory = Path(temporary)
                    materialize_primary(loaded[mode], directory)
                    results[mode] = replay(directory / 'matrix')
            require(results['normal']['cases'] == results['optimized']['cases'] and
                    results['normal']['stdout_sha256'] == results['optimized']['stdout_sha256'] and
                    all(result['candidate_calls'] == 0 and result['archived_source_executed'] is False
                        for result in results.values()), 'primary fresh all-row numerical replay/cross-mode agreement')
            require(authenticate_bootstrap() == bootstrap and authenticate_current_math(captured) == math_before and
                    authenticate_packet_files(packet) == packet_before, 'packet/bootstrap/math changed during replay')
            return {'status': 'joint-two-epoch-packets-exact', 'primary_numerical_replays': results,
                    'archive_authentication': evidence, 'expanded_bytes': expanded, 'parity': parity,
                    'active_bootstrap': bootstrap, 'active_math_sha256': math_before,
                    'candidate_calls': 0, 'archived_source_executed': False,
                    'other_archives_scope': 'Source/build/process/parity authentication only; no fresh component, legacy or failure numerical replay.',
                    'python_imports': 'Fresh current process and empty bytecode-cache prefix; archived paths never added to sys.path.',
                    'scope': summary['scope']}
        finally:
            sys.pycache_prefix, sys.dont_write_bytecode = previous


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', nargs='?', type=Path, default=PACKET)
    print(json.dumps(replay_packets(parser.parse_args().packet), indent=2))
