"""Authenticate and independently replay a frozen target-board expectation artifact.

The archived generator/source copies are evidence only: this reader authenticates
them but never imports or executes them. Current independent math runs only after
the complete source closure and artifact inventory have been verified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import struct
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MAX_ARTIFACT_BYTES = 32 << 20
MAX_SOURCE_FILE = 2 << 20
MAX_SOURCE_TOTAL = 64 << 20
MAX_SMALL_JSON = 1 << 20
MAX_INPUT_BYTES = 8 << 20
MAX_TABLE_BYTES = 8 << 20
ORACLE_SOURCES = (
    'pokerlab/__init__.py', 'pokerlab/cards.py',
    'scripts/matrix_free_certificate_budget.py', 'scripts/matrix_free_four_street_rules.py',
    'scripts/preflop_validation.py', 'tests/full_deck_public_chance_reference.py',
    'tests/test_native_dyadic_policy.py', 'tests/test_native_exact_reach.py',
    'tests/virtual_betting_template_reference.py', 'tests/virtual_dyadic_training_reference.py',
    'tests/virtual_frozen_run_control.py', 'tests/virtual_frozen_update_reference.py',
    'tests/virtual_frozen_value_reference.py',
)
SOURCES = tuple(dict.fromkeys((*ORACLE_SOURCES,
    'scripts/replay_native_frozen_policy_state.py',
    'tests/virtual_frozen_sample_reference.py', 'tests/virtual_grid_update_reference.py',
    'tests/virtual_target_board_reference.py', 'tests/test_target_board_reference.py',
    'tests/virtual_frozen_policy_input_reference.py',
    'scripts/freeze_target_board_reference.py')))
PROFILE_NAMES = ('uniform', 'zero-skew')
INPUT_NAMES = tuple('input-' + name + '.bin' for name in PROFILE_NAMES)
TABLE_NAMES = tuple('expected-' + name + '.bin' for name in PROFILE_NAMES)
ROOT_RAW = 580 << 625
ROOT_AVERAGE = 580 << 364
HEADER = (1, 24_420, 58_164, 1 << 52, 88, 48, 4, 1)


def require(value, message):
    if not value:
        raise ValueError(message)


def git(*args, input_bytes=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, input=input_bytes)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_bounded(path, limit):
    size = path.stat().st_size
    require(size <= limit, 'bounded file size: ' + str(path.name))
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) == size and len(raw) <= limit, 'bounded stable file read: ' + str(path.name))
    return raw


def read_json(path, limit=MAX_SMALL_JSON):
    try:
        return json.loads(read_bounded(path, limit).decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('invalid bounded JSON: ' + path.name) from error


def json_value(value):
    from fractions import Fraction
    if isinstance(value, Fraction):
        return {'numerator': value.numerator, 'denominator': value.denominator}
    if isinstance(value, dict) or hasattr(value, 'items'):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def _tree(head):
    require(len(head) == 40 and all(c in '0123456789abcdef' for c in head),
            'captured full Git commit grammar')
    git('cat-file', '-e', head + '^{commit}')
    result = {}
    for line in git('ls-tree', '-r', head).decode('utf-8').splitlines():
        metadata, name = line.split('\t', 1)
        result[name] = metadata.split()[2]
    return result


def _canonical_source(tree, head, name):
    require(name in tree, 'captured source missing from recorded HEAD: ' + name)
    oid = tree[name]
    require(int(git('cat-file', '-s', oid).decode('ascii')) <= MAX_SOURCE_FILE,
            'captured Git source blob exceeds per-file cap')
    canonical = git('show', head + ':' + name)
    require(len(canonical) <= MAX_SOURCE_FILE and
            git('hash-object', '--stdin', input_bytes=canonical).decode('ascii').strip() == oid,
            'captured canonical Git source/blob mismatch')
    return canonical, oid


def _exact_paths(directory):
    require(not directory.is_symlink() and directory.is_dir(), 'artifact root must be a real directory')
    found = set()
    expected_dirs = {'source'}
    for name in SOURCES:
        parts = PurePosixPath('source/' + name).parts[:-1]
        for i in range(1, len(parts) + 1):
            expected_dirs.add('/'.join(parts[:i]))
    for current, dirs, files in os.walk(directory, followlinks=False):
        base = Path(current)
        for child in (*dirs, *files):
            path = base / child
            require(not path.is_symlink(), 'artifact contains a symbolic link')
        rel_dir = base.relative_to(directory).as_posix()
        if rel_dir != '.':
            require(rel_dir in expected_dirs, 'artifact contains an unlisted directory')
        for name in files:
            relative = (base / name).relative_to(directory).as_posix()
            require('\\' not in relative and '..' not in PurePosixPath(relative).parts,
                    'artifact member path grammar')
            found.add(relative)
    expected = ({'result.json', 'input-proof.json'} |
                set(INPUT_NAMES) | set(TABLE_NAMES) |
                {'source/' + name for name in SOURCES})
    require(found == expected, 'artifact file inventory is incomplete or contains extras')
    return found - {'result.json'}


def authenticate_sources(directory, result, proof):
    head = result.get('source_head')
    require(head == proof.get('source_head'), 'input proof/result source HEAD mismatch')
    source_map = result.get('source_files')
    require(type(source_map) is dict and set(source_map) == set(SOURCES) and
            proof.get('source_files') == source_map, 'complete 20-file source inventory mismatch')
    require(len(SOURCES) == 20, 'source closure count changed')
    captured_tree = _tree(head)
    active_head = git('rev-parse', 'HEAD').decode('ascii').strip()
    active_tree = _tree(active_head)
    status_paths = (*SOURCES, 'scripts/replay_target_board_reference.py')
    require(not git('status', '--porcelain', '--untracked-files=all', '--', *status_paths).strip(),
            'current math closure and replay bootstrap must be committed and clean')
    total = 0
    source_receipt = {}
    for name in SOURCES:
        entry = source_map[name]
        require(type(entry) is dict and type(entry.get('bytes')) is int and
                0 <= entry['bytes'] <= MAX_SOURCE_FILE, 'source receipt shape/size')
        total += entry['bytes']
        require(total <= MAX_SOURCE_TOTAL, 'source total cap')
        saved_meta = entry.get('saved_copy')
        require(type(saved_meta) is dict and saved_meta.get('bytes') == entry['bytes'] and
                saved_meta.get('sha256') == entry.get('raw_sha256'), 'saved source receipt identity')
        saved = read_bounded(directory / 'source' / name, MAX_SOURCE_FILE)
        require(len(saved) == entry['bytes'] and sha(saved) == entry['raw_sha256'],
                'saved raw source copy mismatch: ' + name)
        canonical, captured_oid = _canonical_source(captured_tree, head, name)
        require(captured_oid == entry.get('git_blob') and
                (saved == canonical or (b'\r' not in canonical and saved == canonical.replace(b'\n', b'\r\n'))),
                'saved source bytes do not correspond to captured Git blob: ' + name)

        require(name in active_tree and active_tree[name] == captured_oid,
                'active math source Git blob differs from artifact source: ' + name)
        active = read_bounded(ROOT / name, MAX_SOURCE_FILE)
        require(sha(active) == entry['raw_sha256'] and active == saved,
                'active math source bytes differ from authenticated artifact copy: ' + name)
        source_receipt[name] = {'bytes': len(saved), 'raw_sha256': sha(saved), 'git_blob': captured_oid}

    # The active replay entrypoint is itself a clean, committed stdlib bootstrap.
    reader = 'scripts/replay_target_board_reference.py'
    require(reader in active_tree, 'active replay entrypoint is not committed')
    reader_canonical, reader_blob = _canonical_source(active_tree, active_head, reader)
    reader_raw = read_bounded(ROOT / reader, MAX_SOURCE_FILE)
    require(reader_raw == reader_canonical or
            (b'\r' not in reader_canonical and reader_raw == reader_canonical.replace(b'\n', b'\r\n')),
            'active replay bootstrap differs from committed bytes')
    require(result.get('source_total_bytes') == total, 'complete source total receipt mismatch')
    return active_head, source_receipt, {'path': reader, 'git_blob': reader_blob, 'sha256': sha(reader_raw)}


def _artifact_manifest(directory, result, proof):
    paths = _exact_paths(directory)
    require(len(paths) == 25, 'artifact must contain exactly 25 authenticated data members')
    total = 0
    source_total = 0
    for relative in sorted(paths):
        path = directory / PurePosixPath(relative)
        if relative.startswith('source/'):
            cap = MAX_SOURCE_FILE
        elif relative in ('result.json', 'input-proof.json'):
            cap = MAX_SMALL_JSON
        elif relative.startswith('input-'):
            cap = MAX_INPUT_BYTES
        else:
            cap = MAX_TABLE_BYTES
        raw = read_bounded(path, cap)
        total += len(raw)
        require(total <= MAX_ARTIFACT_BYTES, 'artifact aggregate exceeds 32 MiB')
        if relative.startswith('source/'):
            source_total += len(raw)
        entry = result['members'].get(relative)
        require(type(entry) is dict and entry.get('bytes') == len(raw) and
                entry.get('sha256') == sha(raw), 'artifact member receipt mismatch: ' + relative)
    proof_raw = read_bounded(directory / 'input-proof.json', MAX_SMALL_JSON)
    result['members']  # exact member set checked below; result.json is intentionally self-excluded
    require(set(result.get('members', {})) == paths, 'result member inventory differs from artifact')
    require(proof.get('output_cap_bytes') == MAX_ARTIFACT_BYTES and
            type(proof.get('output_forecast_bytes')) is int and
            proof['output_forecast_bytes'] <= MAX_ARTIFACT_BYTES and
            proof['output_forecast_bytes'] >= total, 'input proof artifact reservation')
    return total + (directory / 'result.json').stat().st_size, source_total, len(proof_raw), paths


def _expected_law_receipt(law):
    from fractions import Fraction
    receipt = json_value(law.receipt())
    receipt['board_probability_by_mass'] = {
        str(mass): {'probability': json_value(Fraction(mass, 580)), 'board_count': count}
        for mass, count in sorted(law.mass_counts.items())
    }
    denominators = {0: 29, 3: 290, 4: 580, 5: 580}
    receipt['prefix_probability_by_mass'] = {
        str(length): {
            str(mass): {'probability': json_value(Fraction(mass, denominators[length])),
                        'prefix_count': count}
            for mass, count in sorted(counts.items())
        }
        for length, counts in law.prefix_mass_counts.items()
    }
    return receipt


def _scaled_integer(value, denominator, max_bits, label):
    from fractions import Fraction
    require(isinstance(value, Fraction), label + ' must be exact Fraction')
    require(value.numerator.bit_length() <= 704 and value.denominator.bit_length() <= 704,
            label + ' Fraction operand bit bound')
    require(value.numerator.bit_length() + denominator.bit_length() <= 1339,
            label + ' pre-multiply bit reservation')
    product = value.numerator * denominator
    require(abs(product).bit_length() <= 1339, label + ' product bit reservation')
    scaled = value * denominator
    require(scaled.denominator == 1, label + ' exact denominator divisibility')
    result = scaled.numerator
    require(abs(result).bit_length() <= max_bits, label + ' fixed-width integer bound')
    return result


def _compare_table(path, expected, fixture, table_receipt):
    require(type(table_receipt) is dict and
            table_receipt == {'bytes': 8_032_788, 'sha256': table_receipt.get('sha256')} and
            type(table_receipt.get('sha256')) is str and len(table_receipt['sha256']) == 64,
            'table receipt shape')
    require(path.stat().st_size == 8_032_788 and path.stat().st_size <= MAX_TABLE_BYTES,
            'fixed expectation table file bound')
    digest = hashlib.sha256()
    position = 0
    def take(stream, amount):
        nonlocal position
        require(0 <= amount <= 8_032_788 - position, 'expectation table read exceeds fixed layout')
        data = stream.read(amount)
        require(len(data) == amount, 'expectation table truncation')
        position += amount
        digest.update(data)
        return data

    rows = tuple(fixture.ordered_rows())
    slots = sum(len(fixture.menus[key]) for key in rows)
    require(len(rows) == 24_420 and slots == 58_164 and expected['rows'] == 24_420 and
            expected['slots'] == 58_164, 'independent output geometry')
    root_integer = _scaled_integer(expected['root'], ROOT_RAW, 703, 'root')
    max_r = max_a = 0
    with path.open('rb') as stream:
        require(take(stream, 8) == b'OPLTGE01', 'expectation table magic')
        require(struct.unpack('<8Q', take(stream, 64)) == HEADER, 'expectation table header values')
        require(int.from_bytes(take(stream, 88), 'little', signed=False) == ROOT_RAW,
                'expectation table raw denominator')
        require(int.from_bytes(take(stream, 48), 'little', signed=False) == ROOT_AVERAGE,
                'expectation table average denominator')
        require(int.from_bytes(take(stream, 88), 'little', signed=True) == root_integer and
                int.from_bytes(take(stream, 88), 'little', signed=True) == -root_integer,
                'expectation table zero-sum roots')
        for ordinal, key in enumerate(rows):
            index, count = struct.unpack('<IB', take(stream, 5))
            regrets = expected['regrets'][key]
            averages = expected['averages'][key]
            require(index == ordinal and count == len(fixture.menus[key]) == len(regrets) == len(averages),
                    'expectation row ordinal/action count')
            for regret, average in zip(regrets, averages):
                wire_r = int.from_bytes(take(stream, 88), 'little', signed=True)
                wire_a = int.from_bytes(take(stream, 48), 'little', signed=False)
                exact_r = _scaled_integer(regret, ROOT_RAW, 703, 'raw regret')
                exact_a = _scaled_integer(average, ROOT_AVERAGE, 384, 'average')
                require(wire_r == exact_r and wire_a == exact_a and exact_a >= 0,
                        'expectation table numeric mismatch')
                max_r = max(max_r, abs(wire_r).bit_length())
                max_a = max(max_a, wire_a.bit_length())
        require(position == 8_032_788 and stream.read(1) == b'', 'expectation table trailing bytes')
    require(digest.hexdigest() == table_receipt['sha256'], 'expectation table saved hash mismatch')
    return max_r, max_a


def replay(directory):
    directory = Path(directory).resolve()
    require(sys.dont_write_bytecode and sys.pycache_prefix is not None,
            'replay must use bytecode-disabled Python with an explicit fresh cache prefix')
    cache_prefix = Path(sys.pycache_prefix)
    if cache_prefix.exists():
        require(cache_prefix.is_dir() and not any(cache_prefix.iterdir()),
                'replay cache prefix must be empty')
    result = read_json(directory / 'result.json')
    proof = read_json(directory / 'input-proof.json')
    require(result.get('format') == 'frozen-target-board-expectation-v1' and
            proof.get('format') == 'target-board-reference-input-v1', 'artifact version')
    require(proof.get('profiles') == list(PROFILE_NAMES) and
            proof.get('requested_board_calls') == 120 and proof.get('native_calls') == 0 and
            proof.get('rng_calls') == 0, 'bounded reference request declaration')
    require(result.get('calls') == {'target_board_operator_calls': 120, 'native_calls': 0,
                                    'rng_calls': 0, 'training_iterations': 0},
            'result call boundary')
    total_bytes, source_bytes, proof_bytes, _members = _artifact_manifest(directory, result, proof)
    require(total_bytes <= MAX_ARTIFACT_BYTES and source_bytes <= MAX_SOURCE_TOTAL and
            proof_bytes <= MAX_SMALL_JSON, 'complete artifact bound')
    active_head, source_receipt, reader_receipt = authenticate_sources(directory, result, proof)
    runtime = result.get('python_runtime')
    require(type(runtime) is dict and proof.get('python_runtime') == runtime,
            'captured Python runtime identity')
    require(proof.get('oracle_limits_per_profile') == {'work': 500_000_000, 'entries': 8_000_000,
            'integer_bits': 4096, 'created_bits': 16_000_000_000}, 'reference budget declaration')

    # All source and packet checks are complete. Only active independent math
    # modules are imported below; archived source copies are never executed.
    from tests.virtual_dyadic_training_reference import Fixture
    from tests.virtual_frozen_sample_reference import build_sampled_reference_context
    from tests.virtual_frozen_policy_input_reference import decode_snapshot
    from tests.virtual_target_board_reference import (
        build_target_board_law, fixed_profile, new_target_budget, target_board_expectation,
    )
    from tests.virtual_grid_update_reference import freeze_grid

    fixture = Fixture()
    context = build_sampled_reference_context()
    profiles = result.get('profiles')
    require(type(profiles) is list and len(profiles) == 2 and
            all(type(row) is dict for row in profiles) and
            tuple(row.get('profile') for row in profiles) == PROFILE_NAMES,
            'two complete profile receipts')
    reports = []
    for name, saved_profile in zip(PROFILE_NAMES, profiles):
        input_path = directory / ('input-' + name + '.bin')
        input_raw = read_bounded(input_path, MAX_INPUT_BYTES)
        input_receipt = {'bytes': len(input_raw), 'sha256': sha(input_raw)}
        require(input_receipt == saved_profile.get('input_policy'), 'input policy member receipt')
        policy = decode_snapshot(fixture, input_raw)
        require(policy == fixed_profile(fixture, name), 'named input policy differs from fixed profile')
        del input_raw
        grid = freeze_grid(fixture, policy)
        del policy
        budget = new_target_budget(context)
        law = build_target_board_law(context, budget)
        expectation = target_board_expectation(fixture, context, law, grid, budget)
        max_r, max_a = _compare_table(directory / ('expected-' + name + '.bin'),
                                      expectation, fixture, saved_profile.get('expected_table'))
        table_receipt = saved_profile['expected_table']
        law_receipt = _expected_law_receipt(law)
        actual = {
            'profile': name, 'input_policy': input_receipt,
            'expected_table': table_receipt, 'target_law': law_receipt,
            'rows': expectation['rows'], 'slots': expectation['slots'],
            'positive_board_calls': expectation['board_calls'],
            'root': json_value(expectation['root']),
            'maximum_sample_regret_integer_bits': expectation['maximum_sample_regret_integer_bits'],
            'maximum_sample_average_integer_bits': expectation['maximum_sample_average_integer_bits'],
            'maximum_expected_regret_integer_bits': max_r,
            'maximum_expected_average_integer_bits': max_a,
            'literal_expectation_match': expectation['literal_expectation_match'],
            'maximum_q_uniform_over_q_target': json_value(expectation['maximum_q_uniform_over_q_target']),
            'coordinate_second_moment_bound_proved': expectation['coordinate_second_moment_bound_proved'],
            'resource_accounting': json_value(expectation['resource_accounting']),
        }
        require(actual == saved_profile, 'independent complete profile replay mismatch: ' + name)
        reports.append({'profile': name, 'rows': expectation['rows'], 'slots': expectation['slots'],
                        'board_calls': expectation['board_calls'], 'root': actual['root'],
                        'input_sha256': input_receipt['sha256'],
                        'table_sha256': table_receipt['sha256'],
                        'maximum_expected_regret_integer_bits': max_r,
                        'maximum_expected_average_integer_bits': max_a,
                        'resource_accounting': actual['resource_accounting']})
        del expectation, grid, law

    require(tuple(report['board_calls'] for report in reports) == (60, 60) and
            tuple(report['rows'] for report in reports) == (24_420, 24_420) and
            tuple(report['slots'] for report in reports) == (58_164, 58_164),
            'complete exact replay census')
    return {
        'status': 'all-target-board-expectations-exact',
        'artifact_source_head': result['source_head'], 'active_replay_head': active_head,
        'authenticated_sources': len(source_receipt), 'artifact_members': 25,
        'artifact_total_bytes': total_bytes, 'profiles': reports,
        'archived_source_executed': False, 'native_calls': 0, 'rng_calls': 0,
        'training_iterations': 0, 'quality_gate': None,
        'scope': 'Exact two-profile fixed-policy PROOF9 expectation replay; no stochastic training, CFR+ clipping, convergence, N11 or full-range claim.',
        'reader_bootstrap': reader_receipt,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print(json.dumps(replay(args.directory), sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
