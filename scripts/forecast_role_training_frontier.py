"""Rank-free lifetime/transport projections; no extension of the native T2 contract."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

POINTS = (1, 2, 3, 4, 5, 6, 8, 9, 16, 32, 1000, 1000000)
NATIVE_SOURCES = ('native/virtual_opponent_role_walk_forecast.hpp',
                  'native/virtual_opponent_role_epoch.hpp', 'native/virtual_sparse_strategy_epoch.hpp')


def need(condition, message):
    if not condition: raise ValueError(message)


def forecast(epochs=POINTS):
    # No tree, law, policy, rank or producer preparation may precede admission.
    need(type(epochs) is tuple and 0 < len(epochs) <= 16 and
         all(type(n) is int and 1 <= n <= 1000000 for n in epochs) and
         tuple(sorted(set(epochs))) == epochs, 'role frontier bounded increasing epoch domain')
    from tests.virtual_role_walk_reference import resources, plan, SUMMARY, SAMPLE
    from tests.virtual_weighted_joint_reference import forecast as law_forecast
    native = resources(); reference = plan(0, ((0, 0), (0, 0)), 'first')
    source_work = law_forecast(52, (1326, 1326))['work'] + 43000000
    need((native['input'], native['output'], native['catalog_work'], reference['complete']['work'], source_work) ==
         (4096, 549280, 11185120, 499975808, 489859648), 'role frontier unchanged T2 source/accounting bridge')
    rows = []
    for n in epochs:
        triangular = n*(n+1)//2
        # Generalized *bounds* from the current framing, not executed requests.
        ticket_input = 32 + 1664*n
        # Hypothesis: u8 counts and 204 densely packed Q52 tickets per world.
        packed_ticket_input = 32 + 1344*n
        all_snapshots = 368 + 82456*n + 125664*triangular
        regret_bits = 365 + (16*n).bit_length()
        average_bits = 52 + n.bit_length()
        compact_slot_bytes = 8*((regret_bits+1+63)//64 + (average_bits+63)//64 + 1)
        # Hypothesis: retain raw worlds/receipts/observations, one final compact
        # snapshot. Delete repeated snapshot headers; retain one final header.
        final_compact_snapshot = 400 + (90584+816*compact_slot_bytes)*n
        blocks = 204*n; menus = blocks
        lookup_cost = 512 + 256*20 + 32*(blocks+1).bit_length() + 8*21
        catalog_setup = 1024 + 8*blocks + 8*menus
        all_catalog_lookups = 612*n + 204*triangular
        final_catalog_lookups = 816*n
        all_catalog_work = catalog_setup + all_catalog_lookups*lookup_cost
        final_catalog_work = catalog_setup + final_catalog_lookups*lookup_cost
        # Deliberately excludes sample/update work: even this partial accounting
        # can exceed the existing envelope when full snapshots are repeated.
        reference_source_io = source_work + 16*(all_snapshots+ticket_input+SUMMARY)
        flags = {'current_u64_ticket_input': ticket_input <= native['input'],
            'hypothetical_packed_ticket_input': packed_ticket_input <= native['input'],
            'canonical_all_snapshots_current_output': all_snapshots <= native['output'],
            'canonical_all_snapshots_shared_output_ceiling': all_snapshots <= 2100000,
            'hypothetical_final_compact_current_output': final_compact_snapshot <= native['output'],
            'hypothetical_final_compact_shared_output_ceiling': final_compact_snapshot <= 2100000,
            'canonical_all_snapshot_catalog': all_catalog_work <= 42000000,
            'hypothetical_final_snapshot_catalog': final_catalog_work <= 42000000,
            'current_compact_numeric_widths': regret_bits <= 371 and average_bits <= 54,
            'generic_store_geometry': 204*n <= 1060 and 816*n <= 2564,
            'reference_source_plus_io_accounting': reference_source_io <= 500000000}
        rows.append({'epochs': n, 'worst_cumulative_rows': 204*n, 'worst_cumulative_slots': 816*n,
            'u64_ticket_input_bytes': ticket_input, 'hypothetical_packed_ticket_input_bytes': packed_ticket_input,
            'canonical_all_snapshot_bytes': all_snapshots, 'compact_regret_magnitude_bits': regret_bits,
            'compact_average_bits': average_bits, 'hypothetical_final_compact_slot_bytes': compact_slot_bytes,
            'hypothetical_final_compact_output_bytes': final_compact_snapshot,
            'canonical_all_snapshot_catalog_lookups': all_catalog_lookups,
            'canonical_all_snapshot_catalog_work': all_catalog_work,
            'hypothetical_final_snapshot_catalog_work': final_catalog_work,
            'reference_fixed_source_plus_all_snapshot_io_work': reference_source_io,
            'partial_budget_flags': flags, 'existing_exact_T2_lifetime': n == 2,
            'complete_future_native_admission': False})
    two = next((r for r in rows if r['epochs'] == 2), None)
    if two:
        need((two['u64_ticket_input_bytes'], two['canonical_all_snapshot_bytes'],
              two['canonical_all_snapshot_catalog_work'], two['compact_regret_magnitude_bits'], two['compact_average_bits']) ==
             (3360, 542272, 11185120, 371, 54), 'role frontier T2 byte/catalog/width identities')
    need(all(abs(v).bit_length() <= 128 for r in rows for v in r.values() if type(v) is int), 'role frontier bounded scalar widths')
    return {'status': 'role-training-frontier-projected', 'rows': rows,
        'unchanged_current_request': {'native': native, 'reference': reference['complete'], 'reference_sample_allowance': SAMPLE},
        'native_calls': 0, 'preparation_calls': 0, 'rng_calls': 0, 'attempted_training': False,
        'hypothetical_wire_implemented': False, 'native_epochs_supported': 2, 'quality_gate': None,
        'scope': 'Conservative rank-free transport, width and Catalog projections under unchanged accounting. Partial flags are not full admission. Hypothetical bit packing/final-only snapshots are unimplemented. Native lifetime, read/stage/commit/History/chance/quantizer budgets and random-stream ownership still need a new complete proof. No CPU/RSS, learning, eleven-card exhaustive or realistic NLHE admission.'}


def study(output):
    from scripts.run_opponent_action_study import ROOT, closure, git
    output = Path(output).resolve()
    need(Path.cwd().resolve() == ROOT and output.parent == ROOT.parent.resolve() and not output.exists(), 'role frontier fresh owned external study')
    names = closure(('scripts/forecast_role_training_frontier.py', 'tests/test_role_training_frontier.py', 'tests/virtual_frozen_run_control.py'))
    for name in NATIVE_SOURCES: names[name] = (ROOT/name).read_bytes()
    need(not git('status', '--porcelain', '--untracked-files=all', '--', *names), 'role frontier complete committed source')
    head = git('rev-parse', 'HEAD').decode().strip()
    tree = {s.split('\t', 1)[1]: s.split('\t', 1)[0].split()[2] for s in git('ls-tree', '-r', head).decode().splitlines()}
    executable = Path(sys.executable).resolve(); executable_hash = sha256(executable.read_bytes()).hexdigest(); output.mkdir()
    for name, raw in names.items():
        path = output/'source'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    (output/'source-identity.json').write_text(json.dumps({'head': head, 'python_version': sys.version, 'cwd': str(Path.cwd().resolve()),
        'python_executable': str(executable), 'python_executable_sha256': executable_hash,
        'raw_sha256': {n: sha256(b).hexdigest() for n, b in names.items()}, 'committed_blobs': {n: tree[n] for n in names}}, indent=2)+'\n')
    from tests.virtual_frozen_run_control import run_bounded_child
    bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module(sys.argv.pop(1),run_name='__main__')"
    records = []
    for mode, flags in (('normal', []), ('optimized', ['-O'])):
        for label, module, args in (('controls', 'unittest', ['tests.test_role_training_frontier', '-v']),
                                   ('worksheet', 'scripts.forecast_role_training_frontier', [])):
            command = [sys.executable, '-I', '-S', '-B', *flags, '-c', bootstrap, str(ROOT), module, *args]
            (output/(label+'-'+mode+'-invocation.json')).write_text(json.dumps({'argv': command, 'cwd': str(Path.cwd().resolve()),
                'source_head': head, 'python_executable_sha256': executable_hash, 'inherited_environment_captured': False}, indent=2)+'\n')
            receipt = run_bounded_child(command, b'', output/(label+'-'+mode), stdout_limit=131072, timeout=90)
            records.append({'label': label, 'mode': mode, 'receipt': receipt})
            need((receipt['status'], receipt['actual_exit_observed'], receipt['returncode'], receipt['failures']) ==
                 ('exited', True, 0, []), 'role frontier first child failed; no retry')
    normal = (output/'worksheet-normal/stdout.bin').read_bytes()
    need(normal == (output/'worksheet-optimized/stdout.bin').read_bytes(), 'role frontier paired complete worksheet bytes')
    need(sha256(executable.read_bytes()).hexdigest() == executable_hash and git('rev-parse', 'HEAD').decode().strip() == head and
         all((ROOT/n).read_bytes() == b for n, b in names.items()), 'role frontier final executable/raw-source drift')
    result = {'status': 'role-training-frontier-study-complete', 'source_head': head, 'source_files': len(names),
        'children': records, 'worksheet_sha256': sha256(normal).hexdigest(), 'worksheet': json.loads(normal),
        'native_calls': 0, 'archived_source_executed': False, 'scope': 'Four original source-frozen bounded Python children; forecast only.'}
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    return {k: result[k] for k in ('status', 'source_head', 'source_files', 'worksheet_sha256')}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--study', type=Path)
    a = p.parse_args(); print(json.dumps(study(a.study) if a.study else forecast(), indent=2))
