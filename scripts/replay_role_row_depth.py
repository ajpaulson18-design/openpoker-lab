"""Authenticate original row-carrier evidence before current independent math."""
import argparse
from hashlib import sha256
import json
from pathlib import Path, PureWindowsPath
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT/'benchmarks/results/role-row-depth-v1'
PIN = (1503, 'e4325bea438ab25b5b927338dcf155b14c843bf4fc217e90a06afa57a3705dcc')
FIRST = '6f04381c576668c1452dd4214e463ee37358615b'
PRIMARY = 'd2e003afdbe2ba2b9220f5b67a6cbe62b159229d'


def same_derived_json_bytes(actual, original):
    """Only platform LF/CRLF transport may differ in newly derived reports.

    Original packet/source bytes retain their separate exact authentication.
    No JSON parsing, reordering, whitespace or numeric normalization is used.
    """
    if type(actual) is not bytes or type(original) is not bytes:
        return False
    lf = original.replace(b'\r\n', b'\n')
    return b'\r' not in lf and actual in (lf, lf.replace(b'\n', b'\r\n'))


def replay(packet=PACKET):
    from scripts import replay_joint_cycles_packet as base, joint_evidence_archive as archive
    from scripts import replay_joint_two_epoch_packet as helper, replay_single_pass_packet as known
    need = base.need; digest = lambda b: sha256(b).hexdigest()

    def bootstrap():
        prior = base.bootstrap(); name = 'scripts/replay_role_row_depth.py'; raw = archive.read(ROOT/name)
        need(not base.git('status', '--porcelain', '--untracked-files=all', '--', name) and
             digest(raw) in base.variants(base.git('show', prior[0]+':'+name)), 'row depth committed replay bootstrap')
        return prior, digest(raw)

    before = bootstrap()
    need(not any(n == 'tests' or n.startswith(('tests.', 'pokerlab')) for n in sys.modules), 'row depth fresh mathematical process')

    def load():
        return archive.load(packet, helper, pin=PIN, version='role-row-depth', labels=('observations', 'builds', 'objects'),
                            packager='package_role_row_depth1.py.txt')

    manifest, loaded, pins = load(); files = loaded['observations']; sources = {}; authentication = {}

    class Objects(helper.GitObjects):
        def __init__(self): super().__init__(); self.by_blob = {}
        def body(self, head, name):
            blob = self.tree(head).get(name); need(blob is not None, 'row depth introduced Git source')
            if blob not in self.by_blob: self.by_blob[blob] = super().body(head, name)
            return self.by_blob[blob]

    objects = Objects()
    expected = {f'study{v}': (FIRST if v == 1 else PRIMARY, 62) for v in (1, 2)}
    expected.update({f'audit{v}/{mode}': (FIRST if v == 1 else PRIMARY, 61)
                     for v in (1, 2) for mode in ('normal', 'optimized')})
    need({n[:-len('/source-identity.json')] for n in files if n.endswith('/source-identity.json')} == set(expected),
         'row depth exact complete source closure inventory')
    for prefix, (head, count) in expected.items():
        record = helper.decode(files[prefix+'/source-identity.json']); hashes = record['raw_sha256']; source = {}
        need(record['head'] == head and len(hashes) == count and set(hashes) == set(record['committed_blobs']) and
             {n[len(prefix+'/source/'):] for n in files if n.startswith(prefix+'/source/')} == set(hashes),
             'row depth original raw source inventory')
        for name, sha in hashes.items():
            raw = files[prefix+'/source/'+helper.safe_name(name)]; blob = objects.tree(head).get(name)
            need(digest(raw) == sha and record['committed_blobs'][name] == blob and
                 (helper.source_bytes_match(raw, objects.body(head, name), name, blob) or
                  known.HISTORICAL_CHECKOUTS.get(name) == (sha, blob)), 'row depth original raw/Git source closure')
            source[name] = raw
        sources[prefix] = source; authentication[prefix] = {'head': head, 'files': count}
    processes, _sizes = helper.process_receipts(files)
    need(set(processes) == {f'study{v}/{label}-{mode}' for v in (1, 2) for label in ('controls', 'audit')
                          for mode in ('normal', 'optimized')} and all(p['exit'] == 0 for p in processes.values()),
         'row depth all eight original actual successful child exits')
    bootstrap_command = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module(sys.argv.pop(1),run_name='__main__')"
    primary_identity = helper.decode(files['study2/source-identity.json'])
    for version in (1, 2):
        report = helper.decode(files[f'study{version}/result.json'])
        need(report['status'] == 'role-row-depth-original-study-complete' and report['source_head'] == expected[f'study{version}'][0] and
             len(report['children']) == 4 and report['native_calls'] == 0, 'row depth original controller completion')
        for index, (mode, label) in enumerate((m, l) for m in ('normal', 'optimized') for l in ('controls', 'audit')):
            prefix = f'study{version}/{label}-{mode}'; child = report['children'][index]
            need((child['label'], child['mode'], child['receipt']) == (label, mode, helper.decode(files[prefix+'/process.json'])) and
                 files[prefix+'/request.bin'] == b'', 'row depth original controller/process identity')
            if label == 'controls':
                need(files[prefix+'/stdout.bin'] == b'' and b'Ran 3 tests' in files[prefix+'/stderr.bin'] and
                     files[prefix+'/stderr.bin'].rstrip().endswith(b'OK'), 'row depth original independent controls')
            else:
                summary = helper.decode(files[prefix+'/stdout.bin']); result = helper.decode(files[f'audit{version}/{mode}/result.json'])
                need(files[prefix+'/stderr.bin'] == b'' and all(result[k] == v for k, v in summary.items()),
                     'row depth original audit complete result')
            if version == 2:
                invocation = helper.decode(files[prefix+'-invocation.json']); module = 'unittest' if label == 'controls' else 'scripts.audit_role_row_depth'
                cwd = invocation['cwd']; args = ['tests.test_role_row_depth_reference', '-v'] if label == 'controls' else [
                    str(PureWindowsPath(cwd).parent/('role-row-depth-study2-audit-'+mode))]
                command = [primary_identity['python_executable'], '-I', '-S', '-B', *(['-O'] if mode == 'optimized' else []),
                           '-c', bootstrap_command, cwd, module, *args]
                need(invocation['argv'] == command and invocation['module'] == module and invocation['mode'] == mode and
                     invocation['python_executable_sha256'] == primary_identity['python_executable_sha256'] and
                     len(invocation['python_executable_sha256']) == 64, 'row depth captured primary exact original argv/executable identity')
            else:
                need(prefix+'-invocation.json' not in files, 'row depth preserve first incomplete invocation metadata')
        for name, sha in report['paired_sha256'].items():
            need(files[f'audit{version}/normal/'+name] == files[f'audit{version}/optimized/'+name] and
                 digest(files[f'audit{version}/normal/'+name]) == sha, 'row depth original paired complete bytes')
    primary = helper.decode(files['audit2/normal/result.json']); first = helper.decode(files['audit1/normal/result.json'])
    need({k: v for k, v in first.items() if k not in ('source_head', 'post_audit_budget')} ==
         {k: v for k, v in primary.items() if k not in ('source_head', 'post_audit_budget')}, 'row depth first math preserved under explicit precharge correction')
    for name in ('row-carriers.json', 'structural-powers.json', 'independent-state-replay.json'):
        need(files['audit1/normal/'+name] == files['audit2/normal/'+name], 'row depth original unchanged values and policies')
    # Current source admission is complete and precedes numerical imports.
    from scripts.run_opponent_action_study import closure
    def current_math():
        current = closure(('scripts/audit_role_row_depth.py', 'tests/role_row_depth_reference.py',
                           'tests/test_role_row_depth_reference.py', 'scripts/replay_compact_role_storage.py'))
        need(set(current) == set(sources['audit2/normal']) and
             not base.git('status', '--porcelain', '--untracked-files=all', '--', *current), 'row depth complete current mathematical closure')
        for name, raw in current.items():
            need(raw.replace(b'\r\n', b'\n') == sources['audit2/normal'][name].replace(b'\r\n', b'\n'),
                 'row depth current mathematical source pin')
        return {n: digest(b) for n, b in current.items()}
    math_before = current_math()
    from scripts.audit_role_row_depth import audit
    # The audited controller requires a fresh sibling evidence directory.
    # Temporarily release only our verified, empty owned directory; the
    # TemporaryDirectory context removes the resulting replay scratch.
    with TemporaryDirectory(prefix='role-row-depth-replay-', dir=ROOT.parent) as temporary:
        output = Path(temporary).resolve()
        need(output.parent == ROOT.parent.resolve() and output.name.startswith('role-row-depth-replay-'), 'row depth owned replay scratch')
        output.rmdir(); audit(output)
        # Compare the actual serialized report to the stored serialized
        # report: JSON arrays/object keys normalize Python tuples/int keys.
        fresh = helper.decode((output/'result.json').read_bytes())
        need({k: v for k, v in fresh.items() if k != 'source_head'} == {k: v for k, v in primary.items() if k != 'source_head'},
             'row depth complete current independent structural and numerical replay')
        for name in ('row-carriers.json', 'structural-powers.json', 'independent-state-replay.json'):
            need(same_derived_json_bytes((output/name).read_bytes(), files['audit2/normal/'+name]),
                 'row depth complete current saved value/policy equality')
    need(bootstrap() == before and current_math() == math_before and load()[2] == pins, 'row depth final raw source/packet drift')
    return {'status': 'structural-row-carrier-evidence-replayed', 'authentication': authentication,
        'original_python_children': 8, 'primary_captured_invocations': 4, 'first_incomplete_invocation_metadata_preserved': True,
        'native_calls': 0, 'archived_source_executed': False, 'native_row_carrier_implemented': False,
        'counts': fresh['counts'], 'totals_over_separate_snapshots': fresh['totals_over_separate_snapshots'],
        'root_remaining_own_decisions': fresh['root_remaining_own_decisions'], 'quality_gate': None,
        'stored_expanded_bytes': manifest['stored_expanded_bytes'],
        'scope': 'Current independent full1326 state replay, structural induction and exact prospective per-row conversion. Original primary commands and all misses retained. No native row-carrier capacity, runtime, longer lifetime or solved quality.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('packet', nargs='?', type=Path, default=PACKET)
    print(json.dumps(replay(p.parse_args().packet), indent=2))
