"""Saved-only complete PROOF9 replay. Never invokes numerical producers.

The retained guard receipts describe past observations; this verifier cannot
re-observe historical filesystem state. Current source/build checks and exact
numeric replay are separate obligations. All outputs belong outside the study.
"""
from pathlib import Path
from itertools import combinations, permutations
import ast
import hashlib
import json
import os
import stat
from tests.virtual_frozen_probe_protocol import DECK, MAX_BYTES, request, parse
from tests.virtual_frozen_reference_artifact import read_reference, artifact_allowance, reference_study_allowance
from tests.virtual_frozen_expectation import ExactExpectation, FORECAST as AGGREGATE
from tests.virtual_frozen_update_comparison import FORECAST as COMPARE
from tests.virtual_frozen_source_guard import capture_source, _path, _raw_file
from tests.virtual_frozen_build_guard import authenticate_build, file_hash
from tests.virtual_frozen_study_admission import WORST_BOARD
from tests.virtual_frozen_whole_study import SOURCE, LIMITS, FILE_FAMILIES


def canonical_boards():
    """Independent fixed-deck enumeration; no physical/reference preparation."""
    for flop in combinations(DECK, 3):
        for turn, river in permutations(tuple(c for c in DECK if c not in flop), 2):
            yield (*flop, turn, river)


def unlinked_path(path):
    path = Path(path).absolute()
    for component in (path, *path.parents):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
            raise ValueError('linked/reparse saved path')
    return path


def regular_file(path, cap):
    path = unlinked_path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > cap:
        raise ValueError('saved file bound/link: ' + str(path))
    return path, info


def bounded_bytes(path, cap):
    path, info = regular_file(path, cap)
    with path.open('rb') as source:
        raw = source.read(cap + 1)
    if len(raw) != info.st_size or len(raw) > cap:
        raise ValueError('saved file size drift')
    return raw


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate saved metadata key')
        result[key] = value
    return result


def metadata(path, cap=65536):
    def no_constant(_):
        raise ValueError('nonfinite saved metadata')
    raw = bounded_bytes(path, cap)
    value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=no_constant)
    if type(value) is not dict:
        raise ValueError('saved metadata object required')
    return value


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require_equal(actual, expected, label):
    if actual != expected:
        raise ValueError('saved review mismatch: ' + label)


def observed_success(observation):
    if (observation.get('actual_exit_observed') is not True or
            type(observation.get('returncode')) is not int or
            observation['returncode'] != 0 or observation.get('failures') != []):
        raise ValueError('authoritative successful exit required')


def bounded_inventory(root, byte_cap):
    """No-follow whole-attempt size/path admission, without loading artifacts."""
    root = unlinked_path(root)
    pending, nodes, files, total = [root], 0, 0, 0
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                nodes += 1
                if nodes > 65536:
                    raise ValueError('saved attempt inventory path cap')
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
                    raise ValueError('linked/reparse saved inventory')
                if stat.S_ISDIR(info.st_mode):
                    pending.append(Path(entry.path))
                elif stat.S_ISREG(info.st_mode):
                    files += 1
                    total += info.st_size
                    if total > byte_cap:
                        raise ValueError('saved attempt total byte admission')
                else:
                    raise ValueError('unsupported saved inventory entry')
    return {'nodes': nodes, 'files': files, 'bytes': total}


def check_plan(plan, result):
    if (plan.get('version') != 'virtual-frozen-whole-study-admission-v1' or
            plan.get('native_eval_requests') != 5040 or plan.get('native_admit_requests') != 2 or
            set(plan.get('uses', {})) != set(LIMITS) or plan.get('limits') != LIMITS):
        raise ValueError('complete unchanged saved resource plan required')
    families = {**FILE_FAMILIES, 'reference_artifacts': reference_study_allowance()['all_reference_artifact_bytes_upper']}
    families['archive_with_headers_upper'] = sum(families.values()) + (128 << 20)
    require_equal(plan.get('file_families'), families, 'unchanged whole-study file allowances')
    require_equal(plan['uses']['artifact_bytes'], sum(families.values()), 'composed artifact allowance')
    for name, ceiling in LIMITS.items():
        value = plan['uses'][name]
        if type(value) is not int or not 0 <= value <= ceiling:
            raise ValueError('saved resource plan exceeds unchanged ceiling')
    for field, allowances in [('numeric_reserved', plan['uses']), ('files_reserved', plan['file_families'])]:
        if type(result.get(field)) is not dict or set(result[field]) != set(allowances):
            raise ValueError('saved cumulative allowance fields incomplete')
        for name, amount in result[field].items():
            if type(amount) is not int or not 0 <= amount <= allowances[name]:
                raise ValueError('saved cumulative allowance exceeded')


def read_observation(directory, expected):
    """Bind exact requests and both saved streams to actual exit receipts."""
    directory = unlinked_path(directory)
    require_equal(bounded_bytes(directory / 'request.bin', 1025), expected, 'canonical request')
    receipt = metadata(directory / 'process.json')
    observed_success(receipt)
    if (receipt.get('version') != 'bounded-child-observation-v1' or
            receipt.get('status') != 'exited' or receipt.get('automatic_retries') != 0):
        raise ValueError('invalid saved native process observation')
    require_equal(receipt.get('request_sha256'), digest(expected), 'request digest')
    records = receipt.get('streams')
    if type(records) is not list or len(records) != 2:
        raise ValueError('incomplete saved streams')
    outputs = []
    for name, cap, record in zip(('stdout.bin', 'stderr.bin'), (MAX_BYTES, 65536), records):
        raw = bounded_bytes(directory / name, cap)
        require_equal(record, {'observed_bytes': len(raw), 'saved_bytes': len(raw),
                               'sha256': digest(raw)}, 'stream size/digest')
        outputs.append(raw)
    return outputs


def native_bytes(directory, mode, wire, board):
    outputs = read_observation(directory, request(mode, wire, board))
    if outputs[1]:
        raise ValueError('saved native stderr is nonempty')
    return outputs[0]


def read_call(directory, mode, wire, board):
    raw = native_bytes(directory, mode, wire, board)
    result = parse(raw, mode=mode, proposal=wire, board=board)
    if result.get('status') != ('ADMITTED' if mode == 'ADMIT' else 'COMPLETE'):
        raise ValueError('saved native request was not successful')
    return raw, result


def replay_plan():
    exports = reference_study_allowance()
    return {'native_producer_calls': 0, 'reference_producer_calls': 0,
            'calls': 5040, 'comparison_work': 5040 * COMPARE['work'],
            'comparison_created_bits': 5040 * COMPARE['created_bits'],
            'aggregation_work': 2 * AGGREGATE['work'],
            'aggregation_created_bits': 2 * AGGREGATE['created_bits'],
            'codec_work': exports['one_export_or_read_named_work_upper'],
            'reference_bytes': exports['all_reference_artifact_bytes_upper'],
            'source_snapshot_bytes': SOURCE['total_bytes'],
            'output_receipt_bytes': 1 << 20,
            'progress_bytes': 5040 * 512,
            'verifier_source_receipt_bytes': 16 << 20,
            'mutation_artifact_bytes': 128 << 20,
            'mutation_comparison_work': 6 * COMPARE['work'],
            'mutation_comparison_created_bits': 6 * COMPARE['created_bits'],
            'mutation_native_input_frames': 2,
            'mutation_scan_parse_work': 8 * 16 * MAX_BYTES,
            'mutation_expected_codec_work': 2 * artifact_allowance('expected', 24420, 58164)['work'],
            'q_free_witness_extra_work': 16,
            'q_free_witness_extra_created_bits': 131072,
            'q_free_witness_extra_entries': 32,
            'q_free_witness_peak_entries': 12361702 + artifact_allowance('expected', 24420, 58164)['entries'],
            'scope': 'one complete saved replay; existing component caps unchanged; not CPU/RSS'}


def _bootstrap(boot, source, root, stage, identity, entry, interpreter=None):
    if (boot.get('version') != 'project-source-only-bootstrap-v1' or
            boot.get('entry_module') != entry or boot.get('root') != str(root)):
        raise ValueError('saved bootstrap entry/root differs')
    expected_first = {'bootstrap_path': str(root / 'scripts/run_virtual_frozen_source_only.py'),
                      'bootstrap_sha256': identity, 'command_sha256': digest(stage.encode())}
    require_equal(boot.get('trusted_first_stage'), expected_first, 'trusted first stage')
    runtime = boot.get('interpreter', {})
    if (runtime.get('isolated') != 1 or runtime.get('no_site') != 1 or
            runtime.get('dont_write_bytecode') is not True or runtime.get('optimize') != 0):
        raise ValueError('saved isolated interpreter flags differ')
    if interpreter is not None:
        require_equal(runtime, interpreter, 'build/parent interpreter')
    for scan in ('initial_cache_scan', 'final_cache_scan'):
        if boot.get(scan, {}).get('project_bytecode_files') != 0:
            raise ValueError('saved bytecode cache scan absent/nonzero')
    compiled = boot.get('compiled')
    if type(compiled) is not dict or not 1 <= len(compiled) <= SOURCE['paths']:
        raise ValueError('saved compiled source map bound')
    for name, value in compiled.items():
        if name not in source['files'] or value != source['files'][name]['raw_sha256']:
            raise ValueError('compiled Python differs from captured source')
    return runtime


def authenticate_saved_study(study, operator, frozen_repo, head):
    """Read-only source/build/operator admission, never executes saved source."""
    study, operator, frozen_repo = map(unlinked_path, (study, operator, frozen_repo))
    claim = metadata(study / 'claim.json')
    source = metadata(study / 'source.json', 16 << 20)
    require_equal(claim.get('head'), head, 'claim HEAD')
    require_equal(source.get('head'), head, 'captured HEAD')
    current_capture = capture_source(frozen_repo)
    require_equal(current_capture, source, 'fresh committed/raw source authentication')
    current_source = {'head': head, 'files': len(source['files']), 'bytes': source['bytes'],
                      'raw_bytes_identical': True}
    # Verify the retained raw snapshot independently of the current checkout.
    snapshot = study / 'source'
    for name, expected in source['files'].items():
        actual = _raw_file(_path(snapshot, name))
        if any(actual[k] != expected[k] for k in actual):
            raise ValueError('retained source snapshot drift: ' + name)
    hashes = {name: record['raw_sha256'] for name, record in source['files'].items()}
    require_equal(metadata(operator / 'source-before.json', 1 << 20), hashes, 'operator source before')
    require_equal(metadata(operator / 'source-after.json', 1 << 20), hashes, 'operator source after')
    terminal = metadata(study / 'terminal.json')
    result = metadata(study / 'result.json', 1 << 20)
    plan = metadata(study / 'resource-plan.json', 1 << 20)
    check_plan(plan, result)
    inventory = bounded_inventory(study, plan['uses']['artifact_bytes'])
    if (terminal.get('status') != 'complete' or result.get('status') != 'exact_update_identity_pass'
            or result.get('source_head') != head):
        raise ValueError('study not complete for saved review')
    for receipt in (terminal.get('receipt', {}), result):
        if receipt.get('native_eval_attempts') != 5040 or receipt.get('native_eval_completions') != 5040:
            raise ValueError('complete exact native attempt/exit coverage required')
    require_equal(result.get('source_final'), current_source, 'final source receipt')
    exit_receipt = metadata(operator / 'study/exit.json')
    observed_success(exit_receipt)
    completion = metadata(operator / 'completion.json')
    require_equal(completion.get('head'), head, 'operator HEAD')
    if completion.get('raw_source_stable') is not True or len(completion.get('runs', [])) != 1:
        raise ValueError('outer source-stable completion required')
    run = completion['runs'][0]
    observed_success(run)
    require_equal(run.get('mode'), 'study', 'outer study mode')
    launch = metadata(operator / 'operator-launch.json')
    require_equal(launch.get('head'), head, 'launch HEAD')
    bootstrap_raw = bounded_bytes(snapshot / 'scripts/run_virtual_frozen_source_only.py', 64 << 20)
    values = [ast.literal_eval(node.value) for node in ast.parse(bootstrap_raw).body
              if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and
                 t.id == 'FIRST_STAGE' for t in node.targets)]
    if len(values) != 1 or type(values[0]) is not str:
        raise ValueError('saved trusted first-stage literal absent')
    stage, identity = values[0], digest(bootstrap_raw)
    require_equal(launch.get('bootstrap_sha256'), identity, 'bootstrap bytes')
    require_equal(launch.get('first_stage'), stage, 'literal first stage')
    require_equal(launch.get('first_stage_sha256'), digest(stage.encode()), 'first-stage digest')
    boot = metadata(operator / 'study-bootstrap.json', 1 << 20)
    runtime = _bootstrap(boot, source, frozen_repo, stage, identity,
                         'scripts.run_virtual_frozen_update_study')
    require_equal(file_hash(runtime['path']), runtime['sha256'], 'actual interpreter bytes')
    require_equal(run.get('compiled_project_files'), len(boot['compiled']), 'final compiled count')
    command = json.loads(bounded_bytes(operator / 'study/command.json', 65536))
    require_equal(command, [runtime['path'], '-I', '-S', '-B', '-c', stage,
                           str(frozen_repo / 'scripts/run_virtual_frozen_source_only.py'), identity,
                           '--module', 'scripts.run_virtual_frozen_update_study', '--receipt',
                           str(operator / 'study-bootstrap.json'), '--', '--output', str(study),
                           '--expected-head', head], 'actual outer command')
    closure = metadata(study / 'execution-closure.json', 1 << 20)
    require_equal(closure.get('head'), head, 'execution closure HEAD')
    require_equal(closure.get('compiled_python_sha256'), boot['compiled'], 'final compiled closure')
    require_equal(closure.get('interpreter'), runtime, 'closure interpreter')
    if type(closure.get('inputs')) is not list or not set(closure['inputs']) <= set(source['files']):
        raise ValueError('execution input closure outside source')
    guard_summary = {'head': head, 'inputs': len(closure['inputs']),
                     'bytes': sum(source['files'][name]['bytes'] for name in closure['inputs']),
                     'raw_bytes_identical': True,
                     'scope': 'all loaded project Python and declared compiled inputs; full-tree guard remains required at batch boundaries'}
    child_boot = metadata(study / 'build-bootstrap.json', 1 << 20)
    read_observation(study / 'build-process', b'')
    _bootstrap(child_boot, source, frozen_repo, stage, identity,
               'scripts.build_native_exact_four_street', runtime)
    if not {'scripts/run_virtual_frozen_source_only.py', 'scripts/build_native_exact_four_street.py'} <= set(child_boot['compiled']):
        raise ValueError('build child compiled map incomplete')
    build = authenticate_build(frozen_repo, study / 'build', source)
    require_equal(metadata(study / 'build-identity.json'), build, 'saved build identity')
    admissions = metadata(study / 'native-admissions.json')
    for wire in ('UNIFORM', 'RIVER_WEIGHTED'):
        _, admitted = read_call(study / ('admit-' + wire), 'ADMIT', wire, WORST_BOARD)
        if any(admitted['calls']) or admitted['forecast'][1] + admitted['probe'][2] > 500_000_000:
            raise ValueError('native admission exceeded unchanged work cap')
        # Controller JSON transports tuple/list identically.
        require_equal(admissions.get(wire), json.loads(json.dumps(admitted)), 'native admission receipt')
    return {'source_head': head, 'source': current_source, 'guard_summary': guard_summary,
            'build': build, 'result': result, 'inventory': inventory,
            'scope': 'retained producer observations plus current source/build checks; no retrospective temporal proof'}


def check_export(saved, exported):
    slots = sum(len(row.actions) for row in saved.rows.values())
    require_equal(exported, {'bytes': saved.receipt['bytes'],
                            'body_sha256': saved.receipt['body_sha256'],
                            'rows': len(saved.rows), 'slots': slots,
                            'allowance': saved.receipt['allowance']}, 'semantic export receipt')


def saved_reference(path, kind):
    shape = (24420, 58164) if kind == 'expected' else (868, 2078)
    cap = artifact_allowance(kind, *shape)['bytes']
    path, info = regular_file(path, cap)
    saved = read_reference(path, byte_limit=cap)
    require_equal(saved.receipt['bytes'], info.st_size, 'reference read size')
    return saved


def replay_saved_numeric(study, provenance, *, progress=None, witness_directory=None):
    """Complete saved comparison/expectation, with one law owner at a time."""
    study = unlinked_path(study)
    expected = saved_reference(study / 'expected.jsonl', 'expected')
    if expected.admission is not None or len(expected.rows) != 24420:
        raise ValueError('complete q-free saved expectation required')
    check_export(expected, provenance['result']['expected_export'])
    laws = {}
    q_free_witness = None
    total_calls = 0
    for law, wire in (('uniform', 'UNIFORM'), ('river_weighted', 'RIVER_WEIGHTED')):
        law_dir = unlinked_path(study / law)
        names = set()
        for entry in law_dir.iterdir():
            entry = unlinked_path(entry)
            if len(names) >= 2520 or not entry.is_dir():
                raise ValueError('saved law directory shape')
            names.add(entry.name)
        require_equal(names, {f'{i:04d}' for i in range(2520)}, 'complete canonical call inventory')
        owner = ExactExpectation(law)
        for index, board in enumerate(canonical_boards()):
            call = law_dir / f'{index:04d}'
            # ExactExpectation.add performs the one admitted full parse and
            # semantic comparison; do not duplicate parsing in the I/O guard.
            raw = native_bytes(call, 'EVAL', wire, board)
            saved_comparison = metadata(call / 'comparison.json')
            sample = saved_reference(call / 'reference.jsonl', 'sampled')
            require_equal((sample.admission.board, sample.admission.proposal_law), (board, law), 'reference board/law')
            check_export(sample, saved_comparison['reference_export'])
            reference_receipt = metadata(call / 'reference-receipt.json')
            require_equal(reference_receipt.get('version'), 'n9-sampled-board-update-reference-v1', 'sampled reference version')
            require_equal(reference_receipt.get('rows'), len(sample.rows), 'reference row receipt')
            require_equal(reference_receipt.get('action_slots'), sum(len(row.actions) for row in sample.rows.values()), 'reference slot receipt')
            require_equal(reference_receipt.get('admission', {}).get('board'), list(board), 'reference admitted board')
            require_equal(reference_receipt.get('admission', {}).get('proposal_law'), law, 'reference admitted law')
            comparison = owner.add(raw, sample)
            require_equal(comparison, saved_comparison['comparison'], 'replayed exact comparison')
            for name in ('source_before', 'source_after'):
                require_equal(saved_comparison[name], provenance['guard_summary'], 'producer ' + name + ' receipt')
            total_calls += 1
            if progress is not None:
                progress({'law': law, 'index': index, 'board': list(board), 'calls': total_calls,
                          'native_sha256': digest(raw), 'reference_body_sha256': sample.receipt['body_sha256']})
            del sample, raw
        if witness_directory is not None and law == 'uniform':
            from tests.virtual_frozen_saved_mutations import expected_witness
            q_free_witness = expected_witness(owner, expected, study / 'expected.jsonl',
                                              Path(witness_directory) / 'q-free-mutant.jsonl')
        laws[law] = owner.finish(expected)
        require_equal(laws[law], metadata(study / (law + '-expectation.json')), 'whole-law expectation receipt')
        require_equal(laws[law], provenance['result']['laws'][law], 'controller law summary')
        del owner
    return {'status': 'complete_saved_numeric_replay_pass', 'source_head': provenance['source_head'],
            'native_producer_calls': 0, 'reference_producer_calls': 0, 'calls': total_calls,
            'laws': laws, 'resource_plan': replay_plan(),
            'q_free_mutation_witness': q_free_witness,
            'mutation_witnesses': 'separate required gate' if witness_directory is None else 'see witness receipts',
            'scope': 'fixed-profile exact update identity only; no training/quality/scalability acceptance'}
