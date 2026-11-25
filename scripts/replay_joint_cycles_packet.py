"""Authenticate original evidence, then independently replay math and CPU accounting."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'benchmarks/results/joint-thread-cycles-v1'
PIN = (2147, 'b5318e223def3f5230fb6435a2bee2c5ca9ed42338397c50e14352b46ad55c74')
ORIGIN = 'ab2c4e14c8eba4b7ff7b9a68e68f182692d59c9a'
BOOTSTRAP = ('scripts/replay_joint_cycles_packet.py', 'scripts/joint_evidence_archive.py',
             'scripts/replay_lazy_joint_packet.py', 'scripts/replay_joint_two_epoch_packet.py',
             'scripts/replay_single_pass_packet.py')
LABELS = ('same-world', 'sb-loss', 'sb-win', 'shared-board-distinct-holding')
SELECTORS = (((0, 0), (0, 0)), ((4, 0), (4, 0)), ((1966603, 0), (1966603, 0)), ((0, 2140425), (4, 2140425)))


def need(value, message):
    if not value: raise ValueError(message)


def digest(raw): return sha256(raw).hexdigest()


def git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    need(result.returncode == 0 and len(result.stdout) <= 8 << 20, 'CPU replay read-only Git lookup')
    return result.stdout


def variants(raw):
    return {digest(raw), digest(raw.replace(b'\n', b'\r\n'))} if b'\r' not in raw else {digest(raw)}


def bootstrap():
    need(not git('status', '--porcelain', '--untracked-files=all', '--', *BOOTSTRAP), 'CPU committed bootstrap required')
    head = git('rev-parse', 'HEAD').decode().strip(); hashes = {}
    for name in BOOTSTRAP:
        path = ROOT / name; need(path.is_file() and not path.is_symlink() and path.stat().st_size <= 2 << 20, 'CPU bootstrap boundary')
        raw = path.read_bytes(); need(digest(raw) in variants(git('show', head + ':' + name)), 'CPU bootstrap source drift'); hashes[name] = digest(raw)
    return head, hashes


def authenticate(loaded, helper, *, origin=ORIGIN, expected_inventory=None,
                 added_headers=('native/joint_thread_cycle_recorder.hpp',), allowed_exits=(0,)):
    class Objects(helper.GitObjects):
        def __init__(self): super().__init__(); self.by_blob = {}
        def body(self, head, name):
            blob = self.tree(head).get(name); need(blob is not None, 'CPU missing source blob')
            if blob not in self.by_blob: self.by_blob[blob] = super().body(head, name)
            return self.by_blob[blob]
    objects = Objects(); reports = {}; builds = {}; latest = None
    for label, files in loaded.items():
        closures = 0
        for member in files:
            if not member.endswith('/source-identity.json'): continue
            prefix = member[:-len('source-identity.json')]; saved = helper.decode(files[member]); source = {}; head = saved['head']; hashes = saved['raw_sha256']
            need(0 < len(hashes) <= 128 and {n[len(prefix + 'source/'):] for n in files if n.startswith(prefix + 'source/')} == set(hashes), 'CPU complete source closure')
            for name, expected in hashes.items():
                raw = files[prefix + 'source/' + helper.safe_name(name)]; blob = objects.tree(head).get(name)
                need(digest(raw) == expected and helper.source_bytes_match(raw, objects.body(head, name), name, blob) and
                     saved['committed_blobs'][name] == blob, 'CPU captured raw/Git source identity'); source[name] = raw
            built = helper.decode(files[prefix + 'native-build-manifest.json']); helper.build_source_links(built, source)
            builds.setdefault(built['target'], []).append(built)
            if prefix + 'baseline-build.json' in files:
                baseline = helper.decode(files[prefix + 'baseline-build.json']); helper.build_source_links(baseline, source)
                need({k: v for k, v in built['source_sha256'].items() if k not in added_headers} == baseline['source_sha256'], 'CPU same baseline core closure')
                builds.setdefault(baseline['target'], []).append(baseline)
            if label == 'overhead':
                need(prefix == 'study/' and head == origin, 'CPU frozen timing origin'); latest = source
                protocol = helper.decode(files['study/protocol.json'])
                need(protocol['head'] == head and protocol['source_raw_sha256'] == hashes, 'CPU timing complete frozen source inventory')
            closures += 1
        processes, _ = helper.process_receipts(files)
        need(all(p['exit'] in allowed_exits for p in processes.values()), 'CPU original native exits')
        reports[label] = {'source_closures': closures, 'actual_process_receipts': len(processes)}
    inventory = {'controls': 4, 'parity': 40, 'overhead': 260, 'builds': 0, 'objects': 0} if expected_inventory is None else expected_inventory
    need({k: v['actual_process_receipts'] for k, v in reports.items()} == inventory, 'CPU exact process inventory')
    for name, raw in loaded['builds'].items():
        if name.endswith('/native-exact-build-manifest.json'):
            built = helper.decode(raw); need(built in builds[built['target']], 'CPU every successful build linked')
    need(latest is not None, 'CPU latest captured source required')
    return objects, latest, reports


def replay(packet=PACKET):
    before = bootstrap()
    need(not any(n == 'tests' or n.startswith(('tests.', 'pokerlab')) for n in sys.modules), 'CPU fresh numerical process')
    from scripts import replay_joint_two_epoch_packet as helper, replay_lazy_joint_packet as old, joint_evidence_archive as archive
    def load(): return archive.load(packet, helper, pin=PIN, version='joint-cycles',
        labels=('controls', 'parity', 'overhead', 'builds', 'objects'), packager='package_joint_cycles1.py.txt')
    manifest, loaded, pins = load(); objects, captured, authentication = authenticate(loaded, helper)
    math_before = old.current_math(helper, objects, captured)
    parser_name = 'tests/virtual_joint_cycle_reference.py'
    def parser_identity():
        raw = old.read(ROOT / parser_name, 2 << 20); canonical = objects.body(ORIGIN, parser_name)
        need(not git('status', '--porcelain', '--untracked-files=all', '--', parser_name) and
             digest(raw) in variants(canonical) and digest(captured[parser_name]) in variants(canonical), 'CPU current/captured parser source drift')
        return digest(raw)
    parser_before = parser_identity(); previous = sys.pycache_prefix, sys.dont_write_bytecode
    with TemporaryDirectory(prefix='joint-cycles-empty-cache-', dir=ROOT.parent) as cache:
        sys.pycache_prefix = cache; sys.dont_write_bytecode = True
        try:
            from tests.virtual_joint_cycle_reference import decode
            from tests.virtual_native_single_pass_reference import verify
            files = loaded['parity']; wires = [files[f'normal/standard-{case}/stdout.bin'] for case in range(4)]
            references = [verify(1, pair, raw) for pair, raw in zip(SELECTORS, wires)]
            for mode in ('normal', 'optimized'):
                need(helper.decode(files[mode + '/independent-expected.json']) == json.loads(json.dumps(references)), 'CPU fresh complete all-row arithmetic')
                for case in range(4):
                    need(files[f'{mode}/standard-{case}/stdout.bin'] == wires[case] and files[f'{mode}/standard-{case}/stderr.bin'] == b'', 'CPU standard cross-mode wire')
                    for offset in range(4):
                        prefix = f'{mode}/diagnostic-{case}-{offset}'
                        need(files[prefix + '/stdout.bin'] == wires[case], 'CPU every offset exact numeric wire')
                        report = decode(files[prefix + '/stderr.bin'], offset)
                        saved = helper.decode(files[prefix + '.json'])
                        need(saved['case_index'] == case and saved['offset'] == offset and saved['cpu'] == report, 'CPU fresh parity accounting')
            for version in (1, 2):
                for mode in ('normal', 'optimized'):
                    raw = loaded['controls'][f'controls-{version}/{mode}/native/stdout.bin']; lines = raw.splitlines(keepends=True)
                    need(len(lines) == 18, 'CPU original synthetic controls inventory')
                    for offset in range(4):
                        report = decode(lines[offset], offset, synthetic=True)
                        need(report['empirical_full_read_cycles_proxy'] == report['empirical_walk_cycles_proxy'] == 6076000 and
                             report['empirical_read_share_proxy'] == 1 and report['raw']['events'][-1][2] == 6564000,
                             'CPU independent exact synthetic body/observer accounting')
            files = loaded['overhead']; protocol = helper.decode(files['study/protocol.json'])
            need(protocol['selectors'] == [[list(x) for x in pair] for pair in SELECTORS] and protocol['profile'] == 1 and
                 protocol['labels'] == list(LABELS) and protocol['blocks'] == 8 and protocol['calls_per_block'] == 16 and
                 protocol['warmups_per_target'] == 2 and protocol['automatic_retries'] == 0 and
                 protocol['median_diagnostic_standard_limit'] == 1.05 and protocol['maximum_pairs_above_1_10'] == 2,
                 'CPU unchanged frozen observer gate')
            observations = []
            def measured(mode, path, case, offset, timed=False):
                prefix = 'study/' + path; receipt = helper.decode(files[prefix + '/process.json']); duration = receipt['duration_seconds']
                need(type(duration) in (int, float) and math.isfinite(duration) and duration > 0 and
                     files[prefix + '/stdout.bin'] == wires[case] and protocol['full_wire_sha256'][case] == digest(wires[case]),
                     'CPU every original full wire and duration')
                stderr = files[prefix + '/stderr.bin']; report = decode(stderr, offset) if mode == 'diagnostic' else None
                if mode == 'standard': need(stderr == b'', 'CPU original standard stderr')
                if timed and report is not None: observations.append((case, report))
                return {'case_index': case, 'offset': offset, 'duration_seconds': duration, 'cpu': report}
            need([measured(mode, f'warmup-{mode}-{i}', i, i) for mode in ('standard', 'diagnostic') for i in range(2)] ==
                 helper.decode(files['study/warmups.json']), 'CPU all original warmups')
            ratios = []
            for block in range(8):
                record = helper.decode(files[f'study/block-{block}.json'])
                need(record['block'] == block and record['order'] == (['standard', 'diagnostic'] if block % 2 == 0 else ['diagnostic', 'standard']), 'CPU alternating block order')
                for mode in ('standard', 'diagnostic'):
                    need([measured(mode, f'block-{block}-{mode}-{i}', i % 4, (i // 4) % 4, True) for i in range(16)] == record[mode], 'CPU every balanced case/offset call')
                ratio = sum(v['duration_seconds'] for v in record['diagnostic']) / sum(v['duration_seconds'] for v in record['standard'])
                need(ratio == record['elapsed_ratio'], 'CPU paired ratio arithmetic'); ratios.append(ratio)
            median = statistics.median(ratios); above = sum(r > 1.10 for r in ratios); accepted = median <= 1.05 and above <= 2
            result = helper.decode(files['study/result.json'])
            need(result['actual_native_calls'] == 260 and result['paired_elapsed_ratios'] == ratios and result['median_diagnostic_standard_ratio'] == median and
                 result['pairs_above_1_10'] == above and result['observer_overhead_gate_pass'] == accepted and accepted, 'CPU original overhead gate arithmetic')
            shares = [r['empirical_read_share_proxy'] for _, r in observations]
            phase_cycles = {}
            for name in dict.fromkeys(event[0] for _, r in observations for event in r['raw']['events']):
                totals = []
                for _, report in observations:
                    previous_cycle = total = 0
                    for event, _epoch, cycle in report['raw']['events']:
                        if event == name: total += cycle - previous_cycle
                        previous_cycle = cycle
                    totals.append(total)
                phase_cycles[name] = statistics.median(totals)
            need(bootstrap() == before and old.current_math(helper, objects, captured) == math_before and parser_identity() == parser_before and load()[2] == pins, 'CPU source/evidence replay drift')
            return {'status': 'joint-cycles-exact-math-accounting-and-overhead-replayed', 'authentication': authentication,
                'fresh_independent_cases': 4, 'parity_calls': 40, 'timed_diagnostic_calls': len(observations),
                'observer_gate': {'paired_ratios': ratios, 'median_ratio': median, 'pairs_above_1_10': above, 'accepted': accepted},
                'cpu_observation': {'median_read_share_proxy': statistics.median(shares), 'range_read_share_proxy': [min(shares), max(shares)],
                    'by_case_median_read_share_proxy': {label: statistics.median(r['empirical_read_share_proxy'] for case, r in observations if case == i) for i, label in enumerate(LABELS)},
                    'median_recorded_phase_cycles': phase_cycles},
                'stored_expanded_bytes': manifest['stored_expanded_bytes'], 'native_calls': 0, 'archived_source_executed': False, 'quality_gate': None,
                'scope': 'Saved sampled read-family CPU cycles and empirical correction, one host/frozen fixed-template T2. No hardware query, cycle conversion, exact unprofiled owner share, kernel speedup, longer learning or realistic-game admission.'}
        finally: sys.pycache_prefix, sys.dont_write_bytecode = previous


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('packet', nargs='?', type=Path, default=PACKET)
    print(json.dumps(replay(parser.parse_args().packet), indent=2))
