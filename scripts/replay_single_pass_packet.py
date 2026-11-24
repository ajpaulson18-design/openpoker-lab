"""Authenticate saved single-pass evidence, then run current independent math.

No native executable, archived source, or packaging controller is executed.
"""
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
PACKET = ROOT / 'benchmarks/results/joint-single-pass-v1'
PIN = (2417, '24b443274da4dd7261b202186a9f4363e683eb40f0fb72be7f84fba787dac68c')
ORIGIN = '70f5209c9c596ac937cd4f892584defc9c20027b'
MAX_MEMBER = MAX_ARCHIVE = 8 << 20
MAX_EXPANDED = 80 << 20
BOOTSTRAP = ('scripts/replay_single_pass_packet.py', 'scripts/replay_joint_two_epoch_packet.py')
EXTRA = ('tests/virtual_weighted_joint_reference.py', 'tests/virtual_weighted_joint_raw_reference.py',
         'tests/virtual_weighted_joint_forecast_reference.py', 'tests/virtual_native_weighted_joint_reference.py',
         'tests/virtual_single_pass_forecast_reference.py', 'tests/virtual_native_single_pass_reference.py',
         'tests/virtual_joint_numeric_projection.py', 'tests/virtual_joint_witness_cases.py')
# Unrelated historical files in the broad before/after inventory. Their exact
# original hashes and Git blobs remain pinned; none is imported as new math.
HISTORICAL_PYTHON = {
    'scripts/benchmark_native_factored_average.py': ('51ab76a595e331cfa226ad163998aa163a85892e3d8f10fd8ac5689f6a6510f3', 'e2d10dac0dfca5553b080a7f00730591caabb024'),
    'scripts/census_virtual_dyadic_factored_average.py': ('ec4fe5d2f64a5f7bf282370dd1a0536fc862fce447484d496155cf63b7954269', '9d166965566b74218384ace9edde6e107d0de5a0'),
    'scripts/replay_native_walk_contexts.py': ('2f554702d3f8c38b7c4e7442c8651dc35b5b86f67eb3e213c3cab90e2ebc9caf', 'e6a04cf8be24b3289ae32e16db0d29a597f81642'),
    'tests/test_native_walk_contexts.py': ('265c264b1b38950e379d3d753876f96b74448ae136eea22aa1a2cd0ada6e0839', '98ad1af7232796d6db81364e92eb033491e023ef'),
    'tests/test_virtual_dyadic_factored_average_census.py': ('cd8e5b02f81b108186a9b9c506e06ed9dbcb9307d65372a4a21b4f5cd074ef16', 'a28e942cac2f5e7741e5e4c6e2f27973395784c5'),
}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return sha256(raw).hexdigest()


def read(path, cap):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= cap, 'single-pass regular bounded file')
    raw = path.read_bytes()
    require(len(raw) <= cap and len(raw) == path.stat().st_size, 'single-pass bounded read drift')
    return raw


def git(*args):
    child = subprocess.run(['git', *args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(child.returncode == 0 and len(child.stdout) <= MAX_MEMBER, 'single-pass read-only Git lookup')
    return child.stdout


def variants(raw):
    return {digest(raw), digest(raw.replace(b'\n', b'\r\n'))} if b'\r' not in raw else {digest(raw)}


def bootstrap():
    require(not git('status', '--porcelain', '--untracked-files=all', '--', *BOOTSTRAP), 'single-pass committed bootstrap required')
    head = git('rev-parse', 'HEAD').decode().strip()
    hashes = {}
    for name in BOOTSTRAP:
        raw = read(ROOT / name, 2 << 20)
        require(digest(raw) in variants(git('show', head + ':' + name)), 'single-pass bootstrap raw/Git drift')
        hashes[name] = digest(raw)
    return head, hashes


def load(packet, helper):
    raw = read(packet / 'manifest.json', MAX_MEMBER)
    require((len(raw), digest(raw)) == PIN, 'single-pass literal packet pin: manifest.json')
    manifest = helper.decode(raw)
    require(manifest['version'] == 'joint-single-pass-package-v1' and manifest['native_calls'] == 0 and
            manifest['archived_source_executed'] is False and manifest['limits'] ==
            {'member_bytes': MAX_MEMBER, 'archive_bytes': MAX_ARCHIVE, 'expanded_bytes': MAX_EXPANDED}, 'single-pass packaging scope/caps')
    records = manifest['archives']
    require(len(records) == 6 and len({item['file'] for item in records}) == 6 and
            {p.name for p in packet.iterdir()} == {'manifest.json', *(item['file'] for item in records)}, 'single-pass exact flat inventory')
    loaded = {}; pins = {}; expanded = 0
    for record in records:
        name = helper.safe_name(record['file']); body = read(packet / name, MAX_ARCHIVE)
        require((len(body), digest(body)) == (record['bytes'], record['sha256']), 'single-pass literal packet pin: ' + name)
        pins[name] = digest(body); files = {}; folded = set()
        with zipfile.ZipFile(BytesIO(body)) as archive:
            infos = archive.infolist()
            require(not archive.comment and len(infos) == record['members'] and
                    sum(item.file_size for item in infos) == record['expanded_bytes'], 'single-pass ZIP count/expanded identity')
            expanded += record['expanded_bytes']; require(expanded <= MAX_EXPANDED, 'single-pass aggregate expanded cap')
            for info in infos:
                member = helper.safe_name(info.filename); mode = info.external_attr >> 16
                require(member not in files and member.casefold() not in folded and info.create_system == 3 and
                        stat.S_ISREG(mode) and not stat.S_ISLNK(mode) and not info.is_dir() and
                        info.compress_type == zipfile.ZIP_DEFLATED and not info.flag_bits & 1 and
                        not info.extra and not info.comment and 0 <= info.file_size <= MAX_MEMBER, 'single-pass safe ZIP member')
                folded.add(member.casefold())
                with archive.open(info) as stream:
                    content = stream.read(MAX_MEMBER + 1)
                require(len(content) == info.file_size, 'single-pass bounded inflate')
                files[member] = content
        require(digest(files['MANIFEST.json']) == record['manifest_sha256'], 'single-pass inner manifest pin')
        inner = helper.decode(files['MANIFEST.json']); entries = inner['members']; label = name[:-4]
        require(inner['version'] == 'joint-single-pass-archive-v1' and inner['archive'] == label and
                len(entries) == len(files) - 1 and len({item['path'] for item in entries}) == len(entries) and
                {item['path'] for item in entries} == set(files) - {'MANIFEST.json'}, 'single-pass complete member inventory')
        for entry in entries:
            content = files[helper.safe_name(entry['path'])]
            require((len(content), digest(content)) == (entry['bytes'], entry['sha256']), 'single-pass member byte/hash identity')
        for member in tuple(files):
            if member.endswith('/stdout.ref.json'):
                ref = helper.decode(files[member]); original = helper.safe_name(ref['original_member'])
                content = files[helper.safe_name(ref['object'])]
                require(original == member[:-len('.ref.json')] + '.bin' and original not in files and
                        (len(content), digest(content)) == (ref['bytes'], ref['sha256']), 'single-pass exact stdout object identity')
                files[original] = content
        loaded[label] = files
    require(expanded == manifest['expanded_bytes'] and set(loaded) ==
            {'candidate-normal', 'candidate-optimized', 'baseline', 'legacy', 'timing', 'builds-and-first-failure'}, 'single-pass archive scope')
    require(digest(loaded['builds-and-first-failure']['package_single_pass1.py.txt']) == manifest['packager_sha256'], 'single-pass packager preserved bytes')
    return manifest, loaded, pins


def authenticate(loaded, helper, objects, origin):
    counts = {}; native_sources = {}; captured_python = None
    for label, files in loaded.items():
        closures = 0
        for member in files:
            if not member.endswith('/source-identity.json'):
                continue
            prefix = member[:-len('source-identity.json')]; saved = helper.decode(files[member]); head = saved['head']
            hashes = saved.get('native_raw_sha256', saved.get('raw_sha256'))
            require(type(hashes) is dict and 0 < len(hashes) <= 128 and
                    {name[len(prefix + 'source/'):] for name in files if name.startswith(prefix + 'source/')} == set(hashes), 'single-pass original source closure inventory')
            source = {}
            for name, expected in hashes.items():
                raw = files[prefix + 'source/' + helper.safe_name(name)]; blob = objects.tree(head).get(name)
                require(digest(raw) == expected and helper.source_bytes_match(raw, objects.body(head, name), name, blob), 'single-pass captured raw/Git source closure')
                if 'committed_blobs' in saved:
                    require(saved['committed_blobs'][name] == blob, 'single-pass captured blob identity')
                source[name] = raw
            native = helper.decode(files[prefix + 'native-build-manifest.json']); helper.build_source_links(native, source)
            native_sources.setdefault(native['target'], []).append((native, source))
            for name, expected in saved.get('tracked_python_raw_sha256', {}).items():
                require(expected in variants(objects.body(head, name)) or
                        HISTORICAL_PYTHON.get(name) == (expected, objects.tree(head).get(name)),
                        'single-pass captured complete Python inventory: ' + name)
            if label == 'candidate-normal' and prefix == 'whole-2/':
                require(head == origin, 'single-pass primary frozen origin'); captured_python = saved['tracked_python_raw_sha256']
            closures += 1
        processes, _sizes = helper.process_receipts(files)
        counts[label] = {'source_closures': closures, 'process_receipts': len(processes)}
    require(counts['candidate-normal']['process_receipts'] == 37 and counts['candidate-optimized']['process_receipts'] == 37 and
            counts['baseline']['process_receipts'] == 32 and counts['timing']['process_receipts'] == 132, 'single-pass complete native process counts')
    builds = loaded['builds-and-first-failure']
    for member, raw in builds.items():
        if member.endswith('/native-exact-build-manifest.json'):
            native = helper.decode(raw)
            matches = [source for recorded, source in native_sources[native['target']] if recorded == native]
            require(matches, 'single-pass every successful build linked to captured run')
            helper.build_source_links(native, matches[0])
    failed = helper.decode(builds['virtual-weighted-joint-single-pass-single1-build/build-failure.json'])
    require(failed['returncode'] == 2 and b'C4127' in builds['virtual-weighted-joint-single-pass-single1-build/build.log'], 'single-pass first compiler failure retained')
    context = helper.decode(builds['failed-source/context.json'])
    require(context['original_raw_checkout_captured'] is False and context['source_context_is_execution_attestation'] is False,
            'single-pass failed-source reconstruction scope')
    for entry in context['files']:
        name = entry['path']; raw = builds['failed-source/source/' + name]
        require(raw == objects.body(context['head'], name) and (len(raw), digest(raw)) == (entry['bytes'], entry['sha256']), 'single-pass canonical failure context')
    protocol = helper.decode(loaded['timing']['protocol.json'])
    require(protocol['head'] == origin, 'single-pass timing source freeze')
    for name, expected in protocol['source_raw_sha256'].items():
        canonical = objects.body(origin, name)
        require(expected in variants(canonical) or helper.HISTORICAL_MIXED.get(name) == (expected, objects.tree(origin).get(name)) or
                HISTORICAL_PYTHON.get(name) == (expected, objects.tree(origin).get(name)), 'single-pass timing complete source inventory: ' + name)
    for mode, target in (('baseline', 'virtual-weighted-joint-two-epoch'), ('candidate', 'virtual-weighted-joint-single-pass')):
        native = helper.decode(loaded['timing'][mode + '-build.json'])
        require(any(native == record for record, _source in native_sources[target]), 'single-pass timed native/build closure')
    return counts, captured_python


def current_math(helper, objects, origin, captured):
    require(not (ROOT / 'tests/__init__.py').exists() and not (ROOT / 'scripts/__init__.py').exists(),
            'single-pass original namespace-package identity')
    oracle = helper.metadata_tuple(objects.body(origin, 'scripts/replay_native_frozen_policy_state.py'), 'ORACLE_SOURCES')
    base = helper.metadata_tuple(objects.body(origin, 'scripts/replay_native_grid_raw.py'), 'MATH', {'ORACLE_SOURCES': oracle})
    new = helper.metadata_tuple(objects.body(origin, 'scripts/replay_joint_two_epoch.py'), 'NEW_MATH')
    names = tuple(dict.fromkeys((*base, *new, *EXTRA)))
    require(not git('status', '--porcelain', '--untracked-files=all', '--', *names), 'single-pass current independent math clean/committed')
    hashes = {}
    for name in names:
        raw = read(ROOT / helper.safe_name(name), 2 << 20); canonical = objects.body(origin, name)
        require(digest(raw) in variants(canonical) and captured[name] in variants(canonical), 'single-pass current/original independent math drift: ' + name)
        hashes[name] = digest(raw)
    return hashes


def replay(packet=PACKET):
    before = bootstrap()
    require(not any(name == 'tests' or name.startswith(('tests.', 'pokerlab')) for name in sys.modules), 'single-pass fresh numerical process required')
    from scripts import replay_joint_two_epoch_packet as helper
    manifest, loaded, pins = load(Path(packet), helper)
    class SharedGitObjects(helper.GitObjects):
        def __init__(self):
            super().__init__(); self.by_blob = {}

        def body(self, head, name):
            blob = self.tree(head).get(name)
            require(blob is not None, 'single-pass missing canonical source blob')
            if blob not in self.by_blob:
                self.by_blob[blob] = super().body(head, name)
            return self.by_blob[blob]
    origin = ORIGIN; objects = SharedGitObjects()
    authentication, captured = authenticate(loaded, helper, objects, origin)
    math_before = current_math(helper, objects, origin, captured)
    previous = sys.pycache_prefix, sys.dont_write_bytecode
    with TemporaryDirectory(prefix='single-pass-empty-cache-', dir=ROOT.parent) as cache:
        sys.pycache_prefix = cache; sys.dont_write_bytecode = True
        try:
            from tests.virtual_native_single_pass_reference import verify as candidate
            from tests.virtual_native_weighted_joint_reference import verify as baseline
            from tests.virtual_joint_numeric_projection import project
            from tests.virtual_joint_witness_cases import cases, validate_sign_witnesses
            witnesses = validate_sign_witnesses(); numerical = {}
            for mode in ('normal', 'optimized'):
                files = loaded['candidate-' + mode]; reports = []
                for label, profile, pair in cases():
                    raw = files['whole-2/' + label + '/stdout.bin']; result = candidate(profile, pair, raw)
                    old = loaded['baseline']['whole-2/' + label + '/stdout.bin']; baseline(profile, pair, old)
                    require(project(raw) == project(old), 'single-pass saved baseline exact numerical projection')
                    result['baseline_numeric_projection_sha256'] = digest(project(old))
                    require(result == helper.decode(files['whole-2/' + label + '/independent-rows.json']), 'single-pass fresh saved report agreement')
                    reports.append(result)
                    if 'whole-1/' + label + '/stdout.bin' in files:
                        require(files['whole-1/' + label + '/stdout.bin'] == raw, 'single-pass original six-case wire preservation')
                numerical[mode] = reports
            require(numerical['normal'] == numerical['optimized'], 'single-pass fresh cross-mode exact agreement')
            files = loaded['timing']; protocol = helper.decode(files['protocol.json'])
            require(protocol['blocks'] == protocol['calls_per_block'] == 8 and protocol['warmups_per_target'] == 2 and
                    protocol['timed_calls_per_target'] == 64 and protocol['automatic_retries'] == 0 and
                    protocol['median_candidate_baseline_limit'] == 0.95 and protocol['minimum_faster_pairs'] == 6 and
                    protocol['selectors'] == [[1, ticket, 0, ticket, 0] for ticket in (0, 4, 1966603)] and
                    protocol['independent_sign_witnesses'] == json.loads(json.dumps(witnesses)), 'single-pass frozen timing/sign protocol')
            labels = ('same-world', 'sb-loss', 'sb-win')
            def measured(mode, path, index):
                expected = loaded['baseline' if mode == 'baseline' else 'candidate-normal']
                root = 'whole-2/profile-1-' + labels[index] + '/stdout.bin'; raw = files[path + '/stdout.bin']
                process = helper.decode(files[path + '/process.json']); duration = process['duration_seconds']
                require(raw == expected[root] and files[path + '/stderr.bin'] == b'' and process['returncode'] == 0 and
                        type(duration) in (int, float) and math.isfinite(duration) and duration > 0 and
                        protocol['full_wire_sha256'][mode][index] == digest(raw) and
                        protocol['exact_numeric_projection_sha256'][index] == digest(project(raw)), 'single-pass every timed wire/projection/exit/duration')
                return {'mode': mode, 'case_index': index, 'case_label': labels[index], 'duration_seconds': duration,
                        'stdout_sha256': digest(raw), 'numeric_projection_sha256': digest(project(raw))}
            warmups = [measured(mode, f'warmup-{mode}-{i}', i) for mode in ('baseline', 'candidate') for i in range(2)]
            require(warmups == helper.decode(files['warmups.json']), 'single-pass all four warmups')
            ratios = []
            for block in range(8):
                saved = helper.decode(files[f'block-{block}.json'])
                require(saved['block'] == block and saved['order'] ==
                        (['baseline', 'candidate'] if block % 2 == 0 else ['candidate', 'baseline']), 'single-pass alternating pair order')
                for mode in ('baseline', 'candidate'):
                    rows = [measured(mode, f'block-{block}-{mode}-{i}', (8 * block + i) % 3) for i in range(8)]
                    require(rows == saved[mode], 'single-pass complete per-block observations')
                ratio = sum(item['duration_seconds'] for item in saved['candidate']) / sum(item['duration_seconds'] for item in saved['baseline'])
                require(ratio == saved['elapsed_ratio'], 'single-pass paired elapsed arithmetic'); ratios.append(ratio)
            result = helper.decode(files['result.json']); median = statistics.median(ratios); faster = sum(r < 1 for r in ratios)
            require(result['actual_native_calls'] == 132 and result['paired_elapsed_ratios'] == ratios and
                    result['median_candidate_baseline_ratio'] == median and result['candidate_faster_pairs'] == faster and
                    result['performance_gate_pass'] == (median <= 0.95 and faster >= 6), 'single-pass saved performance gate arithmetic')
            require(bootstrap() == before and current_math(helper, objects, origin, captured) == math_before and
                    load(Path(packet), helper)[2] == pins, 'single-pass source/evidence drift during replay')
            return {'status': 'single-pass-primary-saved-numerics-and-timing-exact', 'authentication': authentication,
                    'independent_cases_per_python_mode': 10, 'retained_report_sha256': digest(json.dumps(numerical['normal'], sort_keys=True).encode()),
                    'median_candidate_baseline_ratio': median, 'faster_pairs': faster, 'performance_gate_pass': result['performance_gate_pass'],
                    'expanded_bytes': manifest['expanded_bytes'], 'candidate_calls': 0, 'archived_source_executed': False,
                    'scope': 'Fresh current all-row replay of both expanded primary matrices and all132 timing observations. Legacy/guards/build logs authenticate only; no long learning, universal speedup or quality claim.'}
        finally:
            sys.pycache_prefix, sys.dont_write_bytecode = previous


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path, nargs='?', default=PACKET)
    print(json.dumps(replay(parser.parse_args().packet), indent=2))
