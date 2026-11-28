"""Create a source-frozen exact target-board expectation artifact.

This is a pure-Python reference artifact, not a sampler or native training run.
The destination must be a fresh directory outside this checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from fractions import Fraction
from pathlib import Path
import platform
import struct
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MAX_ARTIFACT_BYTES = 32 << 20
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


def require(value, message):
    if not value:
        raise ValueError(message)


def git(*args, input_bytes=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, input=input_bytes)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode('ascii')


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


def source_snapshot():
    require(len(SOURCES) == 20 and len(SOURCES) <= 128, 'source closure count')
    head = git('rev-parse', 'HEAD').decode('ascii').strip()
    require(len(head) == 40 and all(c in '0123456789abcdef' for c in head), 'full committed HEAD')
    require(not git('status', '--porcelain', '--untracked-files=all', '--', *SOURCES).strip(),
            'captured source closure must be clean and committed')
    tree = {}
    for line in git('ls-tree', '-r', head).decode('utf-8').splitlines():
        meta, name = line.split('\t', 1)
        tree[name] = meta.split()[2]
    files = {}
    total = 0
    for name in SOURCES:
        require(name in tree, 'source is absent from committed HEAD: ' + name)
        path = ROOT / name
        size = path.stat().st_size
        require(size <= 2 << 20 and total + size <= 64 << 20,
                'bounded source file/closure size')
        require(int(git('cat-file', '-s', tree[name]).decode('ascii')) <= 2 << 20,
                'bounded committed source blob size')
        with path.open('rb') as source:
            raw = source.read((2 << 20) + 1)
        require(len(raw) == size and len(raw) <= 2 << 20, 'source changed during bounded read')
        total += size
        canonical = git('show', head + ':' + name)
        require(len(canonical) <= 2 << 20 and
                (raw == canonical or (b'\r' not in canonical and raw == canonical.replace(b'\n', b'\r\n'))),
                'source bytes differ beyond exact LF/CRLF forms: ' + name)
        blob = git('hash-object', '--stdin', input_bytes=canonical).decode('ascii').strip()
        require(blob == tree[name], 'canonical source differs from committed Git blob: ' + name)
        files[name] = {'raw_sha256': sha(raw), 'git_blob': blob, 'bytes': len(raw), '_raw': raw}
    return head, files


def runtime_identity():
    executable = Path(sys.executable).resolve()
    digest = hashlib.sha256()
    with executable.open('rb') as stream:
        while True:
            chunk = stream.read(1 << 20)
            if not chunk:
                break
            digest.update(chunk)
    return {
        'executable': str(executable), 'executable_sha256': digest.hexdigest(),
        'python_version': sys.version, 'implementation': platform.python_implementation(),
        'cache_tag': sys.implementation.cache_tag, 'pycache_prefix': sys.pycache_prefix,
        'dont_write_bytecode': sys.dont_write_bytecode,
        'PYTHONDONTWRITEBYTECODE': os.environ.get('PYTHONDONTWRITEBYTECODE'),
        'optimization': sys.flags.optimize,
    }


def write_new(path, raw, ledger, limit):
    require(not path.exists(), 'artifact member already exists')
    require(len(raw) <= limit - ledger[0], 'cumulative artifact byte reservation exceeded')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
    require(path.stat().st_size == len(raw), 'artifact member write length mismatch')
    ledger[0] += len(raw)
    return {'bytes': len(raw), 'sha256': sha(raw)}


def table_bytes(fixture, result):
    from tests.virtual_target_board_reference import (
        LITERAL_AVERAGE_DENOMINATOR, LITERAL_RAW_DENOMINATOR,
    )
    rows = tuple(fixture.ordered_rows())
    fixture_slots = sum(len(fixture.menus[key]) for key in rows)
    require(len(rows) == 24_420 and result['rows'] == 24_420 and result['slots'] == 58_164,
            'complete literal row/slot census')
    require(fixture_slots == result['slots'], 'fixture row/menu slot census')
    expected = 384 + 5 * len(rows) + 136 * fixture_slots
    require(expected == 8_032_788 and expected <= MAX_TABLE_BYTES,
            'fixed expectation table reservation')
    root = result['root'] * LITERAL_RAW_DENOMINATOR
    require(root.denominator == 1 and abs(root.numerator).bit_length() <= 703,
            'literal root integer representation')
    out = bytearray(b'OPLTGE01')
    out.extend(struct.pack('<8Q', 1, 24_420, 58_164, 1 << 52, 88, 48, 4, 1))
    out.extend(LITERAL_RAW_DENOMINATOR.to_bytes(88, 'little', signed=False))
    out.extend(LITERAL_AVERAGE_DENOMINATOR.to_bytes(48, 'little', signed=False))
    out.extend(root.numerator.to_bytes(88, 'little', signed=True))
    out.extend((-root.numerator).to_bytes(88, 'little', signed=True))
    require(len(out) <= MAX_TABLE_BYTES, 'expectation table header exceeds member bound')
    max_r = max_a = 0
    from fractions import Fraction
    for ordinal, key in enumerate(rows):
        regrets = result['regrets'][key]
        averages = result['averages'][key]
        require(len(regrets) == len(averages) == len(fixture.menus[key]) <= 4,
                'ordered row/action width')
        out.extend(struct.pack('<IB', ordinal, len(regrets)))
        for r, a in zip(regrets, averages):
            ri = r * LITERAL_RAW_DENOMINATOR
            ai = a * LITERAL_AVERAGE_DENOMINATOR
            require(isinstance(ri, Fraction) and isinstance(ai, Fraction) and
                    ri.denominator == ai.denominator == 1, 'literal table integer divisibility')
            rv, av = ri.numerator, ai.numerator
            max_r = max(max_r, abs(rv).bit_length())
            max_a = max(max_a, av.bit_length())
            require(max_r <= 703 and max_a <= 384 and av >= 0,
                    'literal table integer magnitude bound')
            out.extend(rv.to_bytes(88, 'little', signed=True))
            out.extend(av.to_bytes(48, 'little', signed=False))
        require(len(out) <= MAX_TABLE_BYTES, 'expectation table append exceeds member bound')
    require(len(out) == expected,
            'fixed expectation table length')
    return bytes(out), max_r, max_a


def freeze(destination):
    destination = destination.resolve()
    require(not destination.exists(), 'destination must be a fresh directory')
    require(not destination.is_relative_to(ROOT), 'destination must be outside the source checkout')
    head, source_files = source_snapshot()
    runtime = runtime_identity()
    source_total = sum(entry['bytes'] for entry in source_files.values())
    planned = 2 * (3_545_022 + 8_032_788) + source_total + (2 << 20)
    require(planned <= MAX_ARTIFACT_BYTES, 'preflight artifact member reservation exceeds 32 MiB')
    destination.mkdir(parents=True)
    source_index = {}
    ledger = [0]
    for name, entry in source_files.items():
        raw = entry.pop('_raw')
        saved = write_new(destination / 'source' / name, raw, ledger, MAX_ARTIFACT_BYTES - (1 << 20))
        require(saved['sha256'] == entry['raw_sha256'] and saved['bytes'] == entry['bytes'],
                'saved source copy identity')
        source_index[name] = dict(entry, saved_copy=saved)

    proof = json_bytes({
        'format': 'target-board-reference-input-v1', 'source_head': head,
        'source_files': source_index, 'python_runtime': runtime,
        'profiles': ['uniform', 'zero-skew'], 'boards_per_profile': 60,
        'requested_board_calls': 120, 'native_calls': 0, 'rng_calls': 0,
        'oracle_limits_per_profile': {'work': 500_000_000, 'entries': 8_000_000,
                                      'integer_bits': 4096, 'created_bits': 16_000_000_000},
        'output_forecast_bytes': planned, 'output_cap_bytes': MAX_ARTIFACT_BYTES,
        'scope': 'independent finite-game expectation reference; no producer or quality admission',
    })
    require(len(proof) <= 1 << 20, 'input proof byte ceiling')
    write_new(destination / 'input-proof.json', proof, ledger, MAX_ARTIFACT_BYTES - (1 << 20))

    # Project imports and all fixture/math generation occur only after the
    # committed bytes and runtime have been captured above.
    from tests.virtual_dyadic_training_reference import Fixture
    from tests.virtual_frozen_sample_reference import build_sampled_reference_context
    from tests.virtual_frozen_policy_input_reference import encode_snapshot
    from tests.virtual_target_board_reference import (
        build_target_board_law, fixed_profile, new_target_budget, target_board_expectation,
    )

    fixture = Fixture()
    context = build_sampled_reference_context()
    profile_reports = []
    for name in ('uniform', 'zero-skew'):
        policy = fixed_profile(fixture, name)
        encoded, ordered, _layout = encode_snapshot(fixture, policy)
        require(len(encoded) == 3_545_022 and len(encoded) <= MAX_INPUT_BYTES and
                len(ordered) == 24_420, 'full raw snapshot bounds')
        input_receipt = write_new(destination / ('input-' + name + '.bin'), encoded, ledger,
                                  MAX_ARTIFACT_BYTES - (1 << 20))
        grid = None
        try:
            from tests.virtual_grid_update_reference import freeze_grid
            grid = freeze_grid(fixture, policy)
            budget = new_target_budget(context)
            law = build_target_board_law(context, budget)
            law_receipt = json_value(law.receipt())
            law_receipt['board_probability_by_mass'] = {
                str(mass): {'probability': json_value(Fraction(mass, 580)),
                            'board_count': count}
                for mass, count in sorted(law.mass_counts.items())
            }
            prefix_denominators = {0: 29, 3: 290, 4: 580, 5: 580}
            law_receipt['prefix_probability_by_mass'] = {
                str(length): {
                    str(mass): {'probability': json_value(Fraction(mass, prefix_denominators[length])),
                                'prefix_count': count}
                    for mass, count in sorted(counts.items())
                }
                for length, counts in law.prefix_mass_counts.items()
            }
            result = target_board_expectation(fixture, context, law, grid, budget)
            table, max_r, max_a = table_bytes(fixture, result)
            table_receipt = write_new(destination / ('expected-' + name + '.bin'), table, ledger,
                                      MAX_ARTIFACT_BYTES - (1 << 20))
            profile_reports.append({
                'profile': name, 'input_policy': input_receipt,
                'expected_table': table_receipt,
                'target_law': law_receipt,
                'rows': result['rows'], 'slots': result['slots'],
                'positive_board_calls': result['board_calls'],
                'root': json_value(result['root']),
                'maximum_sample_regret_integer_bits': result['maximum_sample_regret_integer_bits'],
                'maximum_sample_average_integer_bits': result['maximum_sample_average_integer_bits'],
                'maximum_expected_regret_integer_bits': max_r,
                'maximum_expected_average_integer_bits': max_a,
                'literal_expectation_match': result['literal_expectation_match'],
                'maximum_q_uniform_over_q_target': json_value(result['maximum_q_uniform_over_q_target']),
                'coordinate_second_moment_bound_proved': result['coordinate_second_moment_bound_proved'],
                'resource_accounting': json_value(result['resource_accounting']),
            })
            del result, table, encoded, policy
        finally:
            del grid

    require(runtime_identity() == runtime, 'runtime changed during artifact construction')
    head_after, final_sources = source_snapshot()
    require(head_after == head and all(final_sources[n]['raw_sha256'] == source_index[n]['raw_sha256'] and
            final_sources[n]['git_blob'] == source_index[n]['git_blob'] for n in SOURCES),
            'source bytes or Git blobs changed during artifact construction')
    require(profile_reports[0]['rows'] == profile_reports[1]['rows'] == 24_420 and
            profile_reports[0]['slots'] == profile_reports[1]['slots'] == 58_164 and
            profile_reports[0]['positive_board_calls'] == profile_reports[1]['positive_board_calls'] == 60,
            'two-profile full output and board-call census')

    report = {
        'format': 'frozen-target-board-expectation-v1',
        'source_head': head,
        'source_files': source_index,
        'source_total_bytes': source_total,
        'python_runtime': runtime,
        'profiles': profile_reports,
        'calls': {'target_board_operator_calls': 120, 'native_calls': 0,
                  'rng_calls': 0, 'training_iterations': 0},
        'members': {},
        'scope': 'Exact expectation for two frozen Q52 PROOF9 policies under the target-board law; no stochastic training, CFR+ clipping, convergence, N11 or full-range claim.',
    }
    for path in sorted(p for p in destination.rglob('*') if p.is_file()):
        relative = path.relative_to(destination).as_posix()
        raw = path.read_bytes()
        report['members'][relative] = {'bytes': len(raw), 'sha256': sha(raw)}
    report_path = destination / 'result.json'
    encoded_report = json_bytes(report)
    require(len(encoded_report) <= 1 << 20, 'result JSON exceeds 1 MiB')
    write_new(report_path, encoded_report, ledger, MAX_ARTIFACT_BYTES)
    total = ledger[0]
    return {'status': 'frozen-target-board-expectation-created', 'directory': str(destination),
            'total_bytes': total, 'profiles': profile_reports,
            'source_head': head, 'source_files': len(SOURCES), 'native_calls': 0, 'rng_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(json.dumps(freeze(args.destination), sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
