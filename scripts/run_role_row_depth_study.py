"""Preserve original structural-carrier controls and paired saved-state audits."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from scripts.run_opponent_action_study import ROOT, closure, git, need


def run(output):
    output = Path(output).resolve()
    need(output.parent == ROOT.parent.resolve() and not output.exists(), 'row depth fresh external study')
    names = closure(('scripts/run_role_row_depth_study.py', 'scripts/audit_role_row_depth.py',
                     'tests/test_role_row_depth_reference.py', 'tests/virtual_frozen_run_control.py'))
    need(not git('status', '--porcelain', '--untracked-files=all', '--', *names), 'row depth complete study source committed')
    head = git('rev-parse', 'HEAD').decode().strip()
    tree = {line.split('\t', 1)[1]: line.split('\t', 1)[0].split()[2] for line in git('ls-tree', '-r', head).decode().splitlines()}
    output.mkdir()
    for name, raw in names.items():
        path = output/'source'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    (output/'source-identity.json').write_text(json.dumps({'head': head, 'raw_sha256': {n: sha256(b).hexdigest() for n, b in names.items()},
        'committed_blobs': {n: tree[n] for n in names}}, indent=2)+'\n')
    from tests.virtual_frozen_run_control import run_bounded_child
    bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module(sys.argv.pop(1),run_name='__main__')"
    records = []
    for optimized in (False, True):
        mode = 'optimized' if optimized else 'normal'
        for label, module, args in (('controls', 'unittest', ['tests.test_role_row_depth_reference', '-v']),
                                   ('audit', 'scripts.audit_role_row_depth', [str(output.parent/(output.name+'-audit-'+mode))])):
            receipt = run_bounded_child([sys.executable, '-I', '-S', '-B', *(['-O'] if optimized else []), '-c',
                bootstrap, str(ROOT), module, *args], b'', output/(label+'-'+mode), stdout_limit=1<<20, timeout=300)
            records.append({'label': label, 'mode': mode, 'receipt': receipt})
            need((receipt['status'], receipt['actual_exit_observed'], receipt['returncode'], receipt['failures']) ==
                 ('exited', True, 0, []), 'row depth first original child failed; no retry')
    first = output.parent/(output.name+'-audit-normal'); second = output.parent/(output.name+'-audit-optimized')
    hashes = {}
    for name in ('result.json', 'row-carriers.json', 'structural-powers.json', 'independent-state-replay.json'):
        raw = (first/name).read_bytes(); need(raw == (second/name).read_bytes(), 'row depth exact paired-mode audit bytes')
        hashes[name] = sha256(raw).hexdigest()
    need(git('rev-parse', 'HEAD').decode().strip() == head and all((ROOT/n).read_bytes() == b for n, b in names.items()),
         'row depth study source drift')
    result = {'status': 'role-row-depth-original-study-complete', 'source_head': head, 'source_files': len(names),
              'children': records, 'paired_sha256': hashes, 'native_calls': 0, 'attempted_training': False,
              'quality_gate': None, 'scope': 'Four original Python children; prospective structural carrier proof/audit only.'}
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('status', 'source_head', 'source_files', 'paired_sha256')}, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('output', type=Path); run(p.parse_args().output)
