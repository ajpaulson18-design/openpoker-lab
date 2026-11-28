"""Authenticate original frontier sources/processes before rank-free replay."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT/'benchmarks/results/role-training-frontier-v1'
PIN = (1485, '70914a08a2b67ad02b3aba9a4a8975c5f96251df9a6fa2cc6c69541cab316314')
ORIGIN = '2a49afeffa5174ab8239a026c02be51761a88a74'


def replay(packet=PACKET):
    from scripts import replay_joint_cycles_packet as base, joint_evidence_archive as archive
    from scripts import replay_joint_two_epoch_packet as helper, replay_single_pass_packet as known
    need = base.need; digest = lambda b: sha256(b).hexdigest()
    def bootstrap():
        prior = base.bootstrap(); name = 'scripts/replay_role_training_frontier.py'; raw = archive.read(ROOT/name)
        need(not base.git('status', '--porcelain', '--untracked-files=all', '--', name) and
             digest(raw) in base.variants(base.git('show', prior[0]+':'+name)), 'role frontier committed reader bootstrap')
        return prior, digest(raw)
    before = bootstrap()
    need(not any(n == 'tests' or n.startswith(('tests.', 'pokerlab')) for n in sys.modules), 'role frontier fresh numerical process')
    def load(): return archive.load(packet, helper, pin=PIN, version='role-training-frontier', labels=('observations', 'builds', 'objects'),
                                    packager='package_role_training_frontier1.py.txt')
    manifest, loaded, pins = load(); files = loaded['observations']; identity = helper.decode(files['study/source-identity.json'])
    hashes = identity['raw_sha256']; objects = helper.GitObjects(); captured = {}
    need(identity['head'] == ORIGIN and len(hashes) == 20 and set(hashes) == set(identity['committed_blobs']) and
         {n[len('study/source/'):] for n in files if n.startswith('study/source/')} == set(hashes), 'role frontier complete original source closure')
    for name, sha in hashes.items():
        raw = files['study/source/'+helper.safe_name(name)]; blob = objects.tree(ORIGIN).get(name)
        need(digest(raw) == sha and identity['committed_blobs'][name] == blob and
             (helper.source_bytes_match(raw, objects.body(ORIGIN, name), name, blob) or
              known.HISTORICAL_CHECKOUTS.get(name) == (sha, blob)), 'role frontier raw/Git Python/native source identity')
        captured[name] = raw
    processes, _sizes = helper.process_receipts(files)
    need(set(processes) == {'study/'+label+'-'+mode for label in ('controls', 'worksheet') for mode in ('normal', 'optimized')} and
         all(v['exit'] == 0 for v in processes.values()), 'role frontier all four original actual exits')
    report = helper.decode(files['study/result.json'])
    need(report['source_head'] == ORIGIN and report['source_files'] == 20 and len(report['children']) == 4, 'role frontier original controller completion')
    boot = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module(sys.argv.pop(1),run_name='__main__')"
    for index, (mode, label) in enumerate((m, l) for m in ('normal', 'optimized') for l in ('controls', 'worksheet')):
        prefix = 'study/'+label+'-'+mode; child = report['children'][index]; invocation = helper.decode(files[prefix+'-invocation.json'])
        module = 'unittest' if label == 'controls' else 'scripts.forecast_role_training_frontier'
        args = ['tests.test_role_training_frontier', '-v'] if label == 'controls' else []
        command = [identity['python_executable'], '-I', '-S', '-B', *(['-O'] if mode == 'optimized' else []), '-c',
                   boot, identity['cwd'], module, *args]
        need(child == {'label': label, 'mode': mode, 'receipt': helper.decode(files[prefix+'/process.json'])} and
             invocation['argv'] == command and invocation['cwd'] == identity['cwd'] and invocation['source_head'] == ORIGIN and
             invocation['python_executable_sha256'] == identity['python_executable_sha256'] and files[prefix+'/request.bin'] == b'',
             'role frontier exact original command/executable/observed process link')
        if label == 'controls':
            need(files[prefix+'/stdout.bin'] == b'' and b'Ran 3 tests' in files[prefix+'/stderr.bin'] and
                 files[prefix+'/stderr.bin'].rstrip().endswith(b'OK'), 'role frontier original arithmetic/domain controls')
        else:
            need(files[prefix+'/stderr.bin'] == b'' and helper.decode(files[prefix+'/stdout.bin']) == report['worksheet'],
                 'role frontier original full worksheet equality')
    raw = files['study/worksheet-normal/stdout.bin']
    need(raw == files['study/worksheet-optimized/stdout.bin'] and digest(raw) == report['worksheet_sha256'], 'role frontier original paired worksheet bytes')
    from scripts.run_opponent_action_study import closure
    def current_math():
        current = closure(('scripts/forecast_role_training_frontier.py', 'tests/test_role_training_frontier.py', 'tests/virtual_frozen_run_control.py'))
        need(set(current) == {n for n in captured if n.endswith('.py')} and
             not base.git('status', '--porcelain', '--untracked-files=all', '--', *current), 'role frontier complete committed current math')
        for name, body in current.items():
            need(body.replace(b'\r\n', b'\n') == captured[name].replace(b'\r\n', b'\n'), 'role frontier current mathematical pin')
        return {n: digest(b) for n, b in current.items()}
    math_before = current_math()
    from scripts.forecast_role_training_frontier import forecast
    fresh = helper.decode(json.dumps(forecast()).encode())
    need(fresh == report['worksheet'] and not fresh['attempted_training'] and
         all(not r['complete_future_native_admission'] for r in fresh['rows']), 'role frontier complete current independent projection')
    need(current_math() == math_before and bootstrap() == before and load()[2] == pins, 'role frontier final source/packet drift')
    return {'status': 'role-training-frontier-evidence-replayed', 'original_source_head': ORIGIN, 'original_source_files': 20,
        'current_math_files': len(math_before), 'original_python_children': 4, 'native_calls': 0, 'preparation_calls': 0,
        'archived_source_executed': False, 'worksheet_sha256': report['worksheet_sha256'], 'quality_gate': None,
        'rows': fresh['rows'], 'stored_expanded_bytes': manifest['stored_expanded_bytes'],
        'scope': 'Exact rank-free partial projections from captured T2 contracts; not admission for a longer native run.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('packet', nargs='?', type=Path, default=PACKET)
    print(json.dumps(replay(p.parse_args().packet), indent=2))
