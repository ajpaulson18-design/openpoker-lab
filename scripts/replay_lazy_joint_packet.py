"""Authenticate pooled exact evidence before current saved-only numerical replay."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import stat
import statistics
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'benchmarks/results/lazy-joint-foundation-v1'
PIN = (3052, '945aea2c01e0eee2a148716a5150b7981f562ed52bc6ba92c04ab712816e48b1')
MAX_MEMBER = MAX_ARCHIVE = 8 << 20
MAX_EXPANDED = 80 << 20
BOOTSTRAP = ('scripts/replay_lazy_joint_packet.py', 'scripts/replay_joint_two_epoch_packet.py',
             'scripts/replay_single_pass_packet.py')
LATEST = '67244f99ec5612cb18362ffb1580e510868d81f6'


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return sha256(raw).hexdigest()


def read(path, cap):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= cap, 'lazy packet bounded regular file')
    raw = path.read_bytes(); require(len(raw) <= cap and len(raw) == path.stat().st_size, 'lazy packet file drift')
    return raw


def git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(result.returncode == 0 and len(result.stdout) <= MAX_MEMBER, 'lazy packet read-only Git lookup')
    return result.stdout


def variants(raw):
    return {digest(raw), digest(raw.replace(b'\n', b'\r\n'))} if b'\r' not in raw else {digest(raw)}


def bootstrap():
    require(not git('status', '--porcelain', '--untracked-files=all', '--', *BOOTSTRAP), 'lazy packet committed bootstrap required')
    head = git('rev-parse', 'HEAD').decode().strip(); hashes = {}
    for name in BOOTSTRAP:
        raw = read(ROOT / name, 2 << 20)
        require(digest(raw) in variants(git('show', head + ':' + name)), 'lazy packet bootstrap source drift')
        hashes[name] = digest(raw)
    return head, hashes


def load(packet, helper):
    require(packet.is_dir() and not packet.is_symlink(), 'lazy regular packet directory')
    body = read(packet / 'manifest.json', MAX_MEMBER)
    require((len(body), digest(body)) == PIN, 'lazy literal packet pin: manifest.json')
    manifest = helper.decode(body); records = manifest['archives']
    require(manifest['version'] == 'lazy-joint-package-v1' and manifest['native_calls_during_packaging'] == 0 and
            manifest['archived_source_executed'] is False and manifest['limits'] ==
            {'member_bytes': MAX_MEMBER, 'archive_bytes': MAX_ARCHIVE, 'expanded_bytes': MAX_EXPANDED}, 'lazy package scope/caps')
    require(len(records) == 8 and len({item['file'] for item in records}) == 8 and
            {p.name for p in packet.iterdir()} == {'manifest.json', *(item['file'] for item in records)}, 'lazy exact flat inventory')
    loaded = {}; pins = {}; expanded = 0
    for record in records:
        name = helper.safe_name(record['file']); raw = read(packet / name, MAX_ARCHIVE)
        require((len(raw), digest(raw)) == (record['bytes'], record['sha256']), 'lazy literal packet pin: ' + name)
        pins[name] = digest(raw); files = {}; folded = set()
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            require(not archive.comment and len(infos) == record['members'] and
                    sum(info.file_size for info in infos) == record['expanded_bytes'], 'lazy ZIP count/expanded identity')
            expanded += record['expanded_bytes']; require(expanded <= MAX_EXPANDED, 'lazy aggregate stored expansion cap')
            for info in infos:
                member = helper.safe_name(info.filename); mode = info.external_attr >> 16
                require(member not in files and member.casefold() not in folded and info.create_system == 3 and
                        stat.S_ISREG(mode) and not stat.S_ISLNK(mode) and not info.is_dir() and
                        info.compress_type == zipfile.ZIP_DEFLATED and not info.flag_bits & 1 and
                        not info.extra and not info.comment and 0 <= info.file_size <= MAX_MEMBER, 'lazy safe regular ZIP member')
                folded.add(member.casefold())
                with archive.open(info) as stream:
                    data = stream.read(MAX_MEMBER + 1)
                require(len(data) == info.file_size, 'lazy bounded inflation'); files[member] = data
        require(digest(files['MANIFEST.json']) == record['manifest_sha256'], 'lazy inner manifest pin')
        inner = helper.decode(files['MANIFEST.json']); inventory = inner['members']; label = name[:-4]
        require(inner['version'] == 'lazy-joint-archive-v1' and inner['archive'] == label and
                len(inventory) == len(files) - 1 and len({item['path'] for item in inventory}) == len(inventory) and
                {item['path'] for item in inventory} == set(files) - {'MANIFEST.json'}, 'lazy complete member inventory')
        for entry in inventory:
            data = files[helper.safe_name(entry['path'])]
            require((len(data), digest(data)) == (entry['bytes'], entry['sha256']), 'lazy member byte/hash identity')
        loaded[label] = files
    require(expanded == manifest['stored_expanded_bytes'] and set(loaded) ==
            {'components', 'whole-normal', 'whole-optimized', 'timing-1', 'timing-2', 'thread-cycle-probes', 'builds-and-parity', 'objects'}, 'lazy archive scope')
    objects = loaded['objects']; used = set(); refs = 0
    for label, files in loaded.items():
        if label == 'objects':
            continue
        for member in tuple(files):
            if not member.endswith('.ref.json'):
                continue
            ref = helper.decode(files[member]); original = helper.safe_name(ref['original_member']); obj = helper.safe_name(ref['object'])
            require(original + '.ref.json' == member and original not in files and obj in objects and
                    obj == ref['sha256'] + '.bin' and ref['encoding'] == 'Exact original bytes; shared content address only.', 'lazy pooled original-path reference')
            data = objects[obj]
            require((len(data), digest(data)) == (ref['bytes'], ref['sha256']), 'lazy pooled exact original bytes')
            files[original] = data; del files[member]; used.add(obj); refs += 1
    require(used == set(objects) - {'MANIFEST.json'} and len(used) == manifest['exact_shared_objects'] and refs <= 16384,
            'lazy complete nonorphan bounded object pool')
    require(digest(loaded['builds-and-parity']['package_lazy_joint1.py.txt']) == manifest['packager_sha256'], 'lazy original packager bytes')
    return manifest, loaded, pins


def authenticate(loaded, helper, known):
    class Objects(helper.GitObjects):
        def __init__(self):
            super().__init__(); self.by_blob = {}

        def body(self, head, name):
            blob = self.tree(head).get(name); require(blob is not None, 'lazy missing source blob')
            if blob not in self.by_blob:
                self.by_blob[blob] = super().body(head, name)
            return self.by_blob[blob]
    objects = Objects(); reports = {}; native = {}; latest = None; all_processes = {}
    for label, files in loaded.items():
        closures = 0
        for member in files:
            if not member.endswith('/source-identity.json'):
                continue
            prefix = member[:-len('source-identity.json')]; saved = helper.decode(files[member]); head = saved['head']; hashes = saved['raw_sha256']
            require(0 < len(hashes) <= 128 and
                    {name[len(prefix + 'source/'):] for name in files if name.startswith(prefix + 'source/')} == set(hashes), 'lazy complete original source closure')
            source = {}
            for name, expected in hashes.items():
                raw = files[prefix + 'source/' + helper.safe_name(name)]; blob = objects.tree(head).get(name)
                require(digest(raw) == expected and helper.source_bytes_match(raw, objects.body(head, name), name, blob), 'lazy captured source raw/Git identity')
                if 'committed_blobs' in saved:
                    require(saved['committed_blobs'][name] == blob, 'lazy captured source blob identity')
                source[name] = raw
            built = helper.decode(files[prefix + 'native-build-manifest.json']); helper.build_source_links(built, source)
            native.setdefault(built['target'], []).append((built, source))
            if label == 'whole-normal' and prefix == 'whole-3/':
                require(head == LATEST, 'lazy latest numerical source origin'); latest = source
            closures += 1
        processes, _sizes = helper.process_receipts(files); all_processes[label] = processes
        reports[label] = {'source_closures': closures, 'actual_process_receipts': len(processes)}
    require(sum(len(v) for v in all_processes.values()) == 662 and
            len(all_processes['whole-normal']) == len(all_processes['whole-optimized']) == 68 and
            len(all_processes['components']) == 4 and len(all_processes['timing-1']) == len(all_processes['timing-2']) == 260 and
            len(all_processes['thread-cycle-probes']) == 2, 'lazy complete original native process inventory')
    builds = loaded['builds-and-parity']
    for member, raw in builds.items():
        if member.endswith('/native-exact-build-manifest.json'):
            built = helper.decode(raw)
            require(any(built == old for old, _source in native[built['target']]), 'lazy every successful build linked to original run')
    for number, head in ((1, '04e6c11719bec32cd60218e6605f27b7cabc7ce1'), (2, LATEST)):
        files = loaded['timing-' + str(number)]; protocol = helper.decode(files['study/protocol.json'])
        require(protocol['head'] == head, 'lazy frozen study source')
        for name, expected in protocol['source_raw_sha256'].items():
            canonical = objects.body(head, name); blob = objects.tree(head).get(name)
            require(expected in variants(canonical) or helper.HISTORICAL_MIXED.get(name) == (expected, blob) or
                    known.HISTORICAL_CHECKOUTS.get(name) == (expected, blob), 'lazy broad frozen timing source inventory: ' + name)
        for mode, target in (('eager', 'virtual-weighted-joint-single-pass'), ('lazy', 'virtual-weighted-joint-single-pass-lazy')):
            built = helper.decode(files['study/' + mode + '-build.json'])
            require(any(built == old for old, _source in native[target]), 'lazy timed executable/build/source closure')
    parity = helper.decode(builds['parity.json'])
    require(len(parity) == 4, 'lazy complete predicate parity comparison inventory')
    for record in parity:
        if record['kind'] == 'whole':
            processes = all_processes['whole-' + record['mode']]; before = 'whole-2/'; after = 'whole-3/'
        else:
            require(record['kind'] == 'component', 'lazy parity kind')
            processes = all_processes['components']; before = 'component-1/' + record['mode'] + '/'; after = 'component-2/' + record['mode'] + '/'
        def projection(prefix):
            return {name[len(prefix):]: {'exit': value['exit'], 'stdout': value['stdout_sha256'], 'stderr': value['stderr_sha256']}
                    for name, value in processes.items() if name.startswith(prefix)}
        require(projection(before) == projection(after) == record['processes'], 'lazy predicate revision exact original-stream parity')
    return objects, latest, reports


def current_math(helper, objects, captured):
    require(not (ROOT / 'tests/__init__.py').exists() and not (ROOT / 'scripts/__init__.py').exists(), 'lazy original namespace identity')
    oracle = helper.metadata_tuple(objects.body(LATEST, 'scripts/replay_native_frozen_policy_state.py'), 'ORACLE_SOURCES')
    base = helper.metadata_tuple(objects.body(LATEST, 'scripts/replay_native_grid_raw.py'), 'MATH', {'ORACLE_SOURCES': oracle})
    new = helper.metadata_tuple(objects.body(LATEST, 'scripts/replay_joint_two_epoch.py'), 'NEW_MATH')
    extra = helper.metadata_tuple(objects.body(LATEST, 'tests/test_native_lazy_joint.py'), 'EXTRA')
    names = tuple(dict.fromkeys((*base, *new, *extra)))
    require(not git('status', '--porcelain', '--untracked-files=all', '--', *names), 'lazy current mathematical closure clean/committed')
    result = {}
    for name in names:
        raw = read(ROOT / helper.safe_name(name), 2 << 20); canonical = objects.body(LATEST, name)
        require(name in captured and digest(raw) in variants(canonical) and digest(captured[name]) in variants(canonical),
                'lazy current/captured mathematical closure drift: ' + name)
        result[name] = digest(raw)
    return result


def replay(packet=PACKET):
    before = bootstrap()
    require(not any(name == 'tests' or name.startswith(('tests.', 'pokerlab')) for name in sys.modules), 'lazy fresh numerical process required')
    from scripts import replay_joint_two_epoch_packet as helper, replay_single_pass_packet as known
    manifest, loaded, pins = load(Path(packet), helper)
    objects, captured, authentication = authenticate(loaded, helper, known)
    math_before = current_math(helper, objects, captured)
    previous = sys.pycache_prefix, sys.dont_write_bytecode
    with TemporaryDirectory(prefix='lazy-packet-empty-cache-', dir=ROOT.parent) as cache:
        sys.pycache_prefix = cache; sys.dont_write_bytecode = True
        try:
            from tests.virtual_native_lazy_joint_reference import verify
            from tests.virtual_native_single_pass_reference import verify as eager_verify
            from tests.virtual_lazy_catalog_reference import parse as component
            from tests.virtual_lazy_joint_witnesses import cases
            numerical = {}
            for mode in ('normal', 'optimized'):
                files = loaded['whole-' + mode]; results = []
                for label, profile, pair in cases():
                    raw = files['whole-3/' + label + '/stdout.bin']; result = verify(profile, pair, raw)
                    eager = files['whole-3/baseline-' + label + '/stdout.bin']; eager_verify(profile, pair, eager)
                    require(result['canonical_eager_stdout_sha256'] == digest(eager) and
                            json.loads(json.dumps(result)) == helper.decode(files['whole-3/' + label + '/independent-rows-storage.json']),
                            'lazy current all-row/storage result and normalized eager wire')
                    results.append(result)
                numerical[mode] = results
            require(numerical['normal'] == numerical['optimized'], 'lazy fresh cross-mode numerical agreement')
            components = [component(loaded['components'][f'component-2/{mode}/native/stdout.bin']) for mode in ('normal', 'optimized')]
            require(components[0] == components[1], 'lazy current component cross-mode agreement')
            timing = {}
            labels = ('same-world', 'sb-loss', 'sb-win', 'shared-board-distinct-holding')
            selectors = [[1, 0, 0, 0, 0], [1, 4, 0, 4, 0], [1, 1966603, 0, 1966603, 0], [1, 0, 2140425, 4, 2140425]]
            for version in (1, 2):
                files = loaded['timing-' + str(version)]; protocol = helper.decode(files['study/protocol.json'])
                require(protocol['selectors'] == selectors and protocol['case_labels'] == list(labels) and protocol['blocks'] == 8 and
                        protocol['calls_per_block'] == 16 and protocol['warmups_per_target'] == 2 and protocol['timed_calls_per_target'] == 128 and
                        protocol['automatic_retries'] == 0 and protocol['median_lazy_eager_limit'] == 1.05 and
                        protocol['maximum_pairs_above_1_10'] == 2, 'lazy frozen four-case elapsed protocol')
                def measured(mode, path, index):
                    prefix = 'study/' + path
                    expected = loaded['whole-normal']['whole-3/' + ('baseline-' if mode == 'eager' else '') + 'profile-1-' + labels[index] + '/stdout.bin']
                    process = helper.decode(files[prefix + '/process.json']); duration = process['duration_seconds']; raw = files[prefix + '/stdout.bin']
                    require(raw == expected and files[prefix + '/stderr.bin'] == b'' and process['returncode'] == 0 and
                            type(duration) in (int, float) and math.isfinite(duration) and duration > 0 and
                            protocol['full_wire_sha256'][mode][index] == digest(raw), 'lazy every measured full wire/exit/duration')
                    canonical = loaded['whole-normal']['whole-3/baseline-profile-1-' + labels[index] + '/stdout.bin']
                    require(protocol['canonical_eager_sha256'][index] == digest(canonical), 'lazy measured canonical eager identity')
                    return {'mode': mode, 'case_index': index, 'case_label': labels[index], 'duration_seconds': duration,
                            'stdout_sha256': digest(raw), 'canonical_eager_sha256': digest(canonical)}
                require([measured(mode, f'warmup-{mode}-{i}', i) for mode in ('eager', 'lazy') for i in range(2)] ==
                        helper.decode(files['study/warmups.json']), 'lazy all original warmups')
                ratios = []
                for block in range(8):
                    saved = helper.decode(files[f'study/block-{block}.json'])
                    require(saved['block'] == block and saved['order'] == (['eager', 'lazy'] if block % 2 == 0 else ['lazy', 'eager']),
                            'lazy original alternating pair order')
                    for mode in ('eager', 'lazy'):
                        require([measured(mode, f'block-{block}-{mode}-{i}', i % 4) for i in range(16)] == saved[mode],
                                'lazy all sixteen original block calls')
                    ratio = sum(row['duration_seconds'] for row in saved['lazy']) / sum(row['duration_seconds'] for row in saved['eager'])
                    require(ratio == saved['elapsed_ratio'], 'lazy original paired ratio arithmetic'); ratios.append(ratio)
                result = helper.decode(files['study/result.json']); median = statistics.median(ratios); above = sum(r > 1.10 for r in ratios)
                require(result['actual_native_calls'] == 260 and result['paired_elapsed_ratios'] == ratios and result['median_lazy_eager_ratio'] == median and
                        result['pairs_above_1_10'] == above and result['nonregression_gate_pass'] == (median <= 1.05 and above <= 2),
                        'lazy original elapsed gate arithmetic')
                timing[str(version)] = {'median_ratio': median, 'pairs_above_1_10': above, 'accepted': result['nonregression_gate_pass']}
            require(not timing['1']['accepted'] and not timing['2']['accepted'], 'lazy preserve both elapsed misses')
            require(bootstrap() == before and current_math(helper, objects, captured) == math_before and load(Path(packet), helper)[2] == pins,
                    'lazy source/evidence drift during replay')
            return {'status': 'lazy-joint-primary-numerics-storage-and-both-misses-replayed', 'authentication': authentication,
                    'latest_independent_cases_per_mode': 12, 'fresh_component_replays': 2, 'elapsed_studies': timing,
                    'stored_expanded_bytes': manifest['stored_expanded_bytes'], 'exact_shared_objects': manifest['exact_shared_objects'],
                    'native_calls': 0, 'archived_source_executed': False,
                    'scope': 'Fresh latest whole-row/storage and component mathematics, stream parity and both elapsed gates. Older partial/epoch/probe records authenticate only; no fresh hardware query, adoption, longer learning, CPU/RSS or quality claim.'}
        finally:
            sys.pycache_prefix, sys.dont_write_bytecode = previous


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', nargs='?', type=Path, default=PACKET)
    print(json.dumps(replay(parser.parse_args().packet), indent=2))
