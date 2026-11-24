"""Authenticate weighted foundation evidence before current saved-only math.

No archived Python, native executable or recorded packaging controller runs.
Exact source closure, process receipts, deduplicated streams and timing gates
are checked before the current independent full52 arithmetic is imported.
"""
import argparse
import ast
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import stat
import statistics
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'benchmarks/results/weighted-joint-foundation-v1'
MANIFEST_PIN = (459415, '4aa3f0406a5b8cf422f1739ea78fa59b9d50f6e32b650f02ed4a0dc684f1eb64')
OBSERVATION_PIN = (1789, '6cbbc741f4f87da133364633b7d54fa63171d981a8e75468d00d21f812b2fe28')
MAX_MEMBER = MAX_ARCHIVE = 8 << 20
MAX_EXPANDED = 80 << 20
BOOTSTRAP = ('scripts/replay_weighted_joint_packet.py', 'scripts/replay_joint_two_epoch_packet.py')
EXTRA_MATH = ('tests/virtual_weighted_joint_reference.py', 'tests/virtual_weighted_joint_raw_reference.py',
              'tests/virtual_sparse_epoch_reference.py', 'tests/virtual_weighted_joint_forecast_reference.py',
              'tests/virtual_joint_two_epoch_forecast_reference.py', 'tests/virtual_native_weighted_joint_reference.py',
              'scripts/benchmark_joint_phase_profile.py')


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return sha256(raw).hexdigest()


def bounded(path, cap):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= cap, 'weighted packet file boundary')
    raw = path.read_bytes()
    require(len(raw) <= cap and len(raw) == path.stat().st_size, 'weighted packet read drift')
    return raw


def decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate weighted JSON key'); result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(result.returncode == 0 and len(result.stdout) <= MAX_MEMBER, 'weighted read-only Git lookup')
    return result.stdout


def variants(raw):
    return {digest(raw), *( [digest(raw.replace(b'\n', b'\r\n'))] if b'\r' not in raw else [])}


def bootstrap():
    require(not git('status', '--porcelain', '--untracked-files=all', '--', *BOOTSTRAP), 'commit weighted replay bootstrap')
    head = git('rev-parse', 'HEAD').decode().strip()
    require(re.fullmatch('[0-9a-f]{40}', head), 'weighted active HEAD')
    hashes = {}
    for name in BOOTSTRAP:
        raw = bounded(ROOT / name, 2 << 20)
        require(digest(raw) in variants(git('show', head + ':' + name)), 'weighted bootstrap Git/raw drift')
        hashes[name] = digest(raw)
    return head, hashes


def files(packet):
    manifest_raw = bounded(packet / 'manifest.json', MAX_MEMBER)
    require((len(manifest_raw), digest(manifest_raw)) == MANIFEST_PIN, 'weighted literal packet pin: manifest.json')
    observation_raw = bounded(packet / 'packaging-observation.json', MAX_MEMBER)
    require((len(observation_raw), digest(observation_raw)) == OBSERVATION_PIN,
            'weighted literal packet pin: packaging-observation.json')
    manifest, observation = decode(manifest_raw), decode(observation_raw)
    require(manifest['schema'] == 'weighted-joint-foundation-evidence-v1' and
            manifest['limits'] == {'member_bytes': MAX_MEMBER, 'archive_bytes': MAX_ARCHIVE,
                                   'aggregate_expanded_bytes': MAX_EXPANDED}, 'weighted immutable scope/limits')
    records = {**manifest['archives'], **observation['outer_files']}
    require(len(manifest['archives']) == 14 and
            {path.name for path in packet.iterdir()} == {*records, 'manifest.json', 'packaging-observation.json'},
            'weighted packet extra/missing files')
    loaded, pins = {}, {'manifest.json': digest(manifest_raw), 'packaging-observation.json': digest(observation_raw)}
    for name, record in records.items():
        require(re.fullmatch('[a-z0-9.-]+', name) is not None, 'weighted flat packet name')
        raw = bounded(packet / name, MAX_ARCHIVE)
        require((len(raw), digest(raw)) == (record['bytes'], record['sha256']), 'weighted literal packet pin: ' + name)
        pins[name] = digest(raw); loaded[name] = raw
    require(observation['manifest_sha256'] == digest(manifest_raw) and
            observation['successful_packager_actual_exit'] == 0 and observation['first_packager_actual_exit'] == 1 and
            observation['first_attempt_destination_created'] is False, 'weighted retained packaging outcomes')
    return manifest, loaded, pins


def archives(manifest, bodies, helper):
    result = {}; expanded = 0
    for name, record in manifest['archives'].items():
        members = {}
        with zipfile.ZipFile(BytesIO(bodies[name])) as archive:
            infos = archive.infolist()
            require(len(infos) == record['members'] <= 1024 and not archive.comment, 'weighted archive member count')
            seen = set()
            for info in infos:
                safe = helper.safe_name(info.filename)
                require(safe.casefold() not in seen and not info.is_dir() and
                        stat.S_ISREG(info.external_attr >> 16) and info.compress_type == zipfile.ZIP_DEFLATED and
                        not info.flag_bits & 1 and 0 <= info.file_size <= MAX_MEMBER, 'weighted archive member grammar')
                seen.add(safe.casefold()); expanded += info.file_size
                require(expanded <= MAX_EXPANDED, 'weighted aggregate expanded-byte ceiling')
                raw = archive.read(info); require(len(raw) == info.file_size, 'weighted ZIP member size')
                members[safe] = raw
        inner = decode(members.pop('inner-manifest.json'))
        require(inner['schema'] == 'weighted-joint-evidence-inner-v1' and inner['files'] == record['inventory'] and
                set(members) == set(inner['files']), 'weighted complete inner manifest')
        for member, raw in members.items():
            require({'bytes': len(raw), 'sha256': digest(raw)} == inner['files'][member], 'weighted inner member hash')
        require(sum(len(raw) for raw in members.values()) + len(json.dumps(inner, indent=2).encode()) + 1 == record['expanded_bytes'],
                'weighted expanded-byte ledger')
        result[name.removesuffix('.zip')] = members
    return result, expanded


def source_identity(members, objects, helper, prefix=''):
    identity = decode(members[prefix + 'source-identity.json'])
    head = identity['head']; legacy = 'raw_sha256' in identity
    expected = identity['raw_sha256'] if legacy else identity['native_raw_sha256']
    require(0 < len(expected) <= 128 and {name[len(prefix + 'source/'):] for name in members
            if name.startswith(prefix + 'source/')} == set(expected), 'weighted complete captured native closure')
    body_map = {}
    for name, expected_hash in expected.items():
        raw = members[prefix + 'source/' + helper.safe_name(name)]
        require((not legacy or identity['committed_blobs'].get(name) == objects.tree(head).get(name)) and
                digest(raw) == expected_hash and helper.source_bytes_match(raw, objects.body(head, name), name,
                objects.tree(head).get(name)), 'weighted captured native raw/Git mismatch')
        body_map[name] = raw
    native = decode(members[prefix + 'native-build-manifest.json'])
    require(set(native['source_sha256']) <= set(expected) and
            (legacy or set(native['source_sha256']) == set(expected)), 'weighted full native build/capture inventory')
    helper.build_source_links(native, body_map)
    hashes = {name: value for name, value in expected.items() if name.endswith('.py')} if legacy else identity['tracked_python_raw_sha256']
    require(0 < len(hashes) <= 4096 and all(name.endswith('.py') and name in objects.tree(head) for name in hashes),
            'weighted captured Python/Git inventory')
    return head, hashes, native


def reconstruct_stdout(members):
    restored = dict(members)
    refs = [name for name in members if name.endswith('/stdout.ref.json')]
    require(len(refs) == 132, 'weighted every phase stdout requires an object reference')
    objects = set()
    for name in refs:
        record = decode(members[name]); original = record['original_member']; obj = record['object']
        require(original == name.removesuffix('.ref.json') + '.bin' and obj.startswith('stdout-objects/') and obj in members and
                original not in restored, 'weighted stdout reference path')
        raw = members[obj]
        require((len(raw), digest(raw)) == (record['bytes'], record['sha256']) and obj == 'stdout-objects/' + digest(raw) + '.bin',
                'weighted exact stdout object identity')
        restored[original] = raw; objects.add(obj)
    require(objects == {name for name in members if name.startswith('stdout-objects/')}, 'weighted no orphan stdout objects')
    return restored


def authenticate(loaded, manifest, helper):
    objects = helper.GitObjects(); reports = {}; identities = {}
    for label in ('component-normal', 'component-optimized', 'whole-normal', 'whole-optimized', 'legacy-normal', 'legacy-optimized'):
        head, hashes, native = source_identity(loaded[label], objects, helper)
        records, _sizes = helper.process_receipts(loaded[label])
        expected = 26 if label.startswith('component') else 14 if label.startswith('whole') else 13
        require(len(records) == expected, 'weighted complete process matrix')
        identities[label] = head, hashes, native
        reports[label] = {'source_head': head, 'native_process_receipts': len(records)}
        if label.startswith('component'):
            result = decode(loaded[label]['result.json'])
            require({entry['case'] for entry in result['processes']} == set(records), 'weighted component case inventory')
            for entry in result['processes']:
                case = entry['case']; record = decode(loaded[label][case + '/range-input.json'])
                raw = loaded[label][case + '.input']
                require(record == {'path': case + '.input', 'bytes': len(raw), 'sha256': digest(raw), 'stdin_bytes': 0} and
                        records[case]['exit'] == entry['expected_exit'], 'weighted explicit range input/actual exit')
        if label.startswith('whole'):
            result = decode(loaded[label]['matrix-result.json'])
            require(result['successful_requests'] == 6 and result['rejected_requests'] == 8 and
                    result['observed_native_invocations'] == 14 and result['quality_gate'] is None,
                    'weighted whole matrix scope')
    for kind in ('component', 'whole', 'legacy'):
        a, _ = helper.process_receipts(loaded[kind + '-normal']); b, _ = helper.process_receipts(loaded[kind + '-optimized'])
        require(a == b, 'weighted normal/optimized exact process streams')
    law = loaded['law-reference']; before = decode(law['sources-before.json']); after = decode(law['sources-after.json'])
    require(before['head'] == after['head'] and after['all_raw_sources_unchanged'] is True and
            {name: record['sha256'] for name, record in before['sources'].items()} == after['source_sha256'],
            'weighted law before/after raw source closure')
    tree = objects.tree(before['head'])
    require(all(tree.get(name) == record['git_blob'] for name, record in before['sources'].items()), 'weighted law source Git blobs')
    for mode in ('normal', 'optimized'):
        require(decode(law[mode + '.process.json'])['observed_exit_code'] == 0 and
                b'Ran 12 tests' in law[mode + '.stderr.log'] and law[mode + '.stderr.log'].rstrip().endswith(b'OK'),
                'weighted law actual reference exits')
    dev = loaded['development']
    for prefix in ('weighted-joint1-normal/', 'weighted-joint1-optimized/'):
        source_identity(dev, objects, helper, prefix)
        require(b'bounded child request' in dev[prefix.removesuffix('/') + '.log'], 'weighted first no-native wire refusal')
    failure = decode(dev['weighted-joint2-build/build-failure.json'])
    require(failure['returncode'] == 2 and b'C2371' in dev['weighted-joint2-build/build.log'], 'weighted first file-wire compile failure')
    for name, raw in loaded['introduced-source'].items():
        prefix = 'historical/source/' if name.startswith('historical/source/') else 'source/'
        require(name.startswith(prefix) and raw == objects.body('3eb31c6', name[len(prefix):]),
                'weighted introduced canonical source evidence')
    for number in (1, 2, 3):
        label = f'phase-{number}'; members = loaded[label]; protocol = decode(members['protocol.json']); head = protocol['head']
        for mode, target in (('standard', 'virtual-weighted-joint-two-epoch'), ('diagnostic', 'virtual-weighted-joint-two-epoch-profile')):
            native = decode(members[mode + '-build.json'])
            require(members[mode + '-build.json'] == members['build/' + target + '/native-exact-build-manifest.json'],
                    'weighted diagnostic exact observed build manifest')
            for name, expected in native['source_sha256'].items():
                raw = members['source/' + name]
                require(digest(raw) == expected and helper.source_bytes_match(raw, objects.body(head, name), name,
                        objects.tree(head).get(name)), 'weighted phase full introduced native source closure')
                if name in protocol['source_raw_sha256']:
                    require(protocol['source_raw_sha256'][name] == digest(raw), 'weighted before-call diagnostic source link')
        loaded[label] = reconstruct_stdout(members)
        records, _ = helper.process_receipts(loaded[label]); require(len(records) == 132 and all(r['exit'] == 0 for r in records.values()),
            'weighted phase all132 actual processes')
        require(protocol['timed_calls_per_target'] == 64 and protocol['warmups_per_target'] == 2 and
                protocol['median_paired_overhead_limit'] == 1.05, 'weighted frozen timing protocol')
        expected = loaded['whole-normal']['profile-1-same-world/stdout.bin']
        require(all(record['stdout_sha256'] == digest(expected) for record in records.values()), 'weighted every phase wire identity')
        reports[label] = {'head': head, 'actual_processes': 132, 'stdout_objects': 1}
    refusal = loaded['cpu-collector-refusal']; record = decode(refusal['collector-refusal.json'])
    require(record['observed_exit_code'] == 0xc5585011 and record['recording_owned'] is False and
            record['native_calls_completed'] == 2 and b'Failed to enable the policy' in refusal['wpr-start-0.stdout.log'],
            'weighted preserved WPR policy refusal')
    process, _ = helper.process_receipts(refusal)
    require(len(process) == 2 and all(row['exit'] == 0 for row in process.values()), 'weighted unprofiled collector warmups')
    protocol = decode(refusal['protocol.json']); native = decode(refusal['native-build-manifest.json'])
    for name, expected in native['source_sha256'].items():
        canonical = objects.body(protocol['head'], name); blob = objects.tree(protocol['head']).get(name)
        require(expected in variants(canonical) or helper.HISTORICAL_MIXED.get(name) == (expected, blob),
                'weighted collector original native/Git build context')
    for name, expected in protocol['bootstrap_raw_sha256'].items():
        raw = refusal['source/' + name]
        require(digest(raw) == expected and digest(raw) in variants(objects.body(protocol['head'], name)),
                'weighted collector controller source context')
    return objects, identities, reports


def current_math(objects, identities, helper):
    head, captured, _native = identities['whole-normal']
    oracle = helper.metadata_tuple(objects.body(head, 'scripts/replay_native_frozen_policy_state.py'), 'ORACLE_SOURCES')
    base = helper.metadata_tuple(objects.body(head, 'scripts/replay_native_grid_raw.py'), 'MATH', {'ORACLE_SOURCES': oracle})
    names = tuple(dict.fromkeys((*base, *EXTRA_MATH)))
    require(not git('status', '--porcelain', '--untracked-files=all', '--', *names), 'weighted current math must be committed/clean')
    hashes = {}
    for name in names:
        # The phase parser was introduced after the primary arithmetic capture.
        origin = '3eb31c6' if name == 'scripts/benchmark_joint_phase_profile.py' else head
        canonical = objects.body(origin, name); raw = bounded(ROOT / name, 2 << 20)
        require(digest(raw) in variants(canonical), 'weighted current independent math drift: ' + name)
        if origin == head:
            require(name in captured and captured[name] in variants(canonical), 'weighted original numeric source inventory')
        hashes[name] = digest(raw)
    return hashes


def replay(packet=PACKET):
    before = bootstrap()
    require(not any(name == 'tests' or name.startswith(('tests.', 'pokerlab')) for name in sys.modules), 'weighted replay requires fresh Python process')
    manifest, bodies, pins = files(Path(packet))
    # This authenticated helper imports only stdlib; no numerical namespace.
    from scripts import replay_joint_two_epoch_packet as helper
    loaded, expanded = archives(manifest, bodies, helper)
    objects, identities, authentication = authenticate(loaded, manifest, helper)
    math_before = current_math(objects, identities, helper)
    previous = sys.pycache_prefix, sys.dont_write_bytecode
    with TemporaryDirectory(prefix='weighted-packet-empty-cache-', dir=ROOT.parent) as cache:
        sys.pycache_prefix = cache; sys.dont_write_bytecode = True
        try:
            from tests.virtual_native_weighted_joint_reference import verify
            from scripts.benchmark_joint_phase_profile import phases
            numerical = {}
            for mode in ('normal', 'optimized'):
                members = loaded['whole-' + mode]; saved = decode(members['matrix-result.json']); results = []
                for record in saved['cases']:
                    label = record['case']; profile = record['profile']
                    # Selectors are independently parsed from the saved frame;
                    # the complete arithmetic verifier validates their domain.
                    raw = members[label + '/stdout.bin']
                    position = 368; selectors = []
                    for _ in range(2):
                        header = struct_words(raw, position + 8, 20)
                        selectors.append((header[2], header[3])); position += header[19]
                    result = verify(profile, tuple(selectors), raw)
                    require(decode(members[label + '/independent-rows.json']) == json.loads(json.dumps(result)),
                            'weighted saved full retained-row report drift')
                    results.append(result)
                numerical[mode] = results
            require(numerical['normal'] == numerical['optimized'], 'weighted fresh cross-mode numerical agreement')
            timing = {}
            for number in (1, 2, 3):
                members = loaded[f'phase-{number}']; ratios = []; parsed = []
                for block in range(8):
                    saved = decode(members[f'block-{block}.json']); durations = {}
                    for mode in ('standard', 'diagnostic'):
                        durations[mode] = []
                        for call in range(8):
                            prefix = f'block-{block}-{mode}-{call}'
                            process = decode(members[prefix + '/process.json']); durations[mode].append(process['duration_seconds'])
                            require(saved[mode][call]['duration_seconds'] == process['duration_seconds'], 'weighted measured duration identity')
                            stderr = members[prefix + '/stderr.bin']
                            if mode == 'diagnostic':
                                parsed.append(phases(stderr)); require(saved[mode][call]['phase'] == parsed[-1], 'weighted phase arithmetic identity')
                            else:
                                require(stderr == b'', 'weighted standard contains diagnostic output')
                    ratio = sum(durations['diagnostic']) / sum(durations['standard'])
                    require(ratio == saved['elapsed_ratio'], 'weighted paired ratio replay'); ratios.append(ratio)
                median = statistics.median(ratios); result = decode(members['result.json'])
                require(median == result['median_paired_elapsed_ratio'] and result['overhead_pass'] == (median <= 1.05) and
                        result['phase_wall_time_accepted'] == (median <= 1.05) and result['inner_walk_cpu_attribution_accepted'] is False and
                        result['median_phase_percent'] == {name: statistics.median(item['phase_percent'][name] for item in parsed)
                                                         for name in parsed[0]['phase_percent']}, 'weighted retained diagnostic gate replay')
                timing[str(number)] = {'median_ratio': median, 'phase_wall_time_accepted': median <= 1.05}
            require([timing[str(i)]['phase_wall_time_accepted'] for i in (1, 2, 3)] == [False, False, True], 'weighted preserve both misses')
            require(bootstrap() == before and current_math(objects, identities, helper) == math_before and
                    files(Path(packet))[2] == pins, 'weighted source/evidence drift during replay')
            return {'status': 'weighted-joint-packet-authenticated-and-primary-numerics-exact',
                    'authentication': authentication, 'primary_full52_numerical_replays': numerical,
                    'coarse_diagnostic_gates': timing, 'expanded_archive_bytes': expanded,
                    'candidate_calls': 0, 'archived_source_executed': False,
                    'scope': 'Fresh full52 primary all-retained-row replay and phase arithmetic. Components/legacy/law logs authenticate only; no fresh independent component census or historical numerical rerun. No convergence or quality claim.'}
        finally:
            sys.pycache_prefix, sys.dont_write_bytecode = previous


def struct_words(raw, offset, count):
    import struct
    require(type(offset) is int and 0 <= offset <= len(raw) - 8 * count, 'weighted saved frame header boundary')
    return struct.unpack_from('<' + 'Q' * count, raw, offset)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', nargs='?', type=Path, default=PACKET)
    print(json.dumps(replay(parser.parse_args().packet), indent=2))
