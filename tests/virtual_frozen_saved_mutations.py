"""Corrupt real saved artifacts; never rerun a numerical producer.

These witnesses exercise detection lanes. They do not diagnose every possible
faulty algorithm or establish training/quality. Preserve every witness miss.
"""
from pathlib import Path
from copy import copy, deepcopy
import hashlib
from tests.virtual_frozen_probe_protocol import parse, MAX_BYTES, HANDS
from tests.virtual_frozen_update_comparison import compare_saved_update
from tests.virtual_frozen_reference_artifact import _loads, _dump, _integer, MAX_LINE, BITS
from tests.virtual_frozen_saved_review import (digest, canonical_boards,
    read_call, saved_reference, regular_file, require_equal)

MAX_SAVED_BYTES = 128 << 20


def doubled_hex(token, bits):
    value = int(token, 16)
    if value.bit_length() >= bits:
        raise ValueError('mutation integer width admission')
    return format(2 * value, 'x')


def mutate_native(raw, kind):
    candidate = parse(raw, mode='EVAL')
    lines = raw.decode('ascii').splitlines()
    selected = None
    if kind == 'regret_denominator':
        if not any(action[2] for row in candidate['rows'] for action in row['actions']):
            return None
        for index, line in enumerate(lines):
            if line.startswith('regret_denominator '):
                lines[index] = 'regret_denominator ' + doubled_hex(line.split()[1], 384)
                break
        selected = {'field': 'shared regret denominator'}
    elif kind in ('average_scale', 'visible_history'):
        for row in candidate['rows']:
            if kind == 'average_scale' and row['average_mass']:
                selected = row
                break
            if kind == 'visible_history' and row['key'][3]:
                selected = row
                break
        if selected is None:
            return None
        row_index = candidate['rows'].index(selected)
        start = next(i for i, line in enumerate(lines) if line.startswith('row ' + str(row_index) + ' '))
        end = lines.index('endrow', start)
        if kind == 'visible_history':
            lines[start + 1] = 'token review_corrupt_history'
        else:
            for index in range(start + 1, end):
                fields = lines[index].split()
                if fields[0] == 'average':
                    fields[2] = doubled_hex(fields[2], 384)
                    lines[index] = ' '.join(fields)
                elif fields[0] == 'action':
                    fields[5] = doubled_hex(fields[5], 384)
                    lines[index] = ' '.join(fields)
        selected = {'row_index': row_index, 'key': selected['key']}
    else:
        raise ValueError('unknown saved native mutation')
    changed = ('\n'.join(lines) + '\n').encode('ascii')
    parse(changed, mode='EVAL', proposal=candidate['proposal'], board=candidate['board'])
    if changed == raw:
        raise ValueError('saved native mutation had no effect')
    return changed, selected


def native_witnesses(study, output):
    """Three parser-valid real-frame controls, saved separately from originals."""
    study, output = Path(study), Path(output)
    output.mkdir(exist_ok=False)
    pending = {'regret_denominator', 'average_scale', 'visible_history'}
    receipts = []
    # Select at most two boards by physical support, before reading any values.
    # A missing numeric witness remains a miss; no unbounded value search.
    selections = []
    for index, board in enumerate(canonical_boards()):
        if index == 0:
            selections.append((index, board))
        if any(not (set(sb) & set(bb)) and not (set(board) & (set(sb) | set(bb)))
               for sb in HANDS[0] for bb in HANDS[1]):
            if index != 0:
                selections.append((index, board))
            break
    for index, board in selections:
        call = study / 'uniform' / f'{index:04d}'
        raw, _ = read_call(call, 'EVAL', 'UNIFORM', board)
        reference = None
        for kind in sorted(tuple(pending)):
            mutated = mutate_native(raw, kind)
            if mutated is None:
                continue
            changed, detail = mutated
            if reference is None:
                reference = saved_reference(call / 'reference.jsonl', 'sampled')
                compare_saved_update(raw, reference)
            destination = output / (kind + '.bin')
            with destination.open('xb') as saved:
                saved.write(changed)
            detected = False
            error = None
            try:
                compare_saved_update(changed, reference)
            except ValueError as failure:
                error = str(failure)
                detected = error in ('exact regret mismatch', 'exact average mass mismatch',
                                     'full physical row key mismatch')
            receipts.append({'kind': kind, 'board': list(board), 'index': index,
                             'source_sha256': digest(raw), 'mutant_sha256': digest(changed),
                             'mutant_file': destination.name, 'detail': detail,
                             'parser_valid': True, 'detected': detected, 'error': error,
                             'scope': 'real saved contribution equality detector; fault diagnosis not implied'})
            pending.remove(kind)
        if not pending:
            break
    return {'witnesses': receipts, 'unavailable': sorted(pending),
            'all_detected': not pending and all(r['detected'] for r in receipts),
            'native_producer_calls': 0, 'reference_producer_calls': 0}


def mutate_expected(path, destination, key, original_body_sha256):
    """Stream one average-row scaling and recompute a valid artifact checksum."""
    # Reserve room for all three bounded native mutants and small receipts.
    cap = MAX_SAVED_BYTES - 3 * MAX_BYTES - (1 << 20)
    path, info = regular_file(path, cap)
    source_digest, body_digest, full_digest = (hashlib.sha256() for _ in range(3))
    selected = None
    total = 0
    with path.open('rb') as source, Path(destination).open('xb') as output:
        header = source.readline(MAX_LINE + 1)
        value = _loads(header)
        if value.get('kind') != 'expected':
            raise ValueError('q-free corruption requires expected artifact')
        source_digest.update(header)
        def put(raw):
            nonlocal total
            total += len(raw)
            if total > cap or len(raw) > MAX_LINE:
                raise ValueError('saved mutation byte admission')
            output.write(raw)
            full_digest.update(raw)
        put(header)
        body_digest.update(header)
        for index in range(value['rows']):
            raw = source.readline(MAX_LINE + 1)
            row = _loads(raw)
            source_digest.update(raw)
            row_key = (row[1], tuple(row[2]), tuple(row[3]))
            if row_key == key:
                if selected is not None or _integer(row[6][0]) <= 0:
                    raise ValueError('q-free mutation needs unique positive average row')
                old_mass = list(row[6])
                row[6][0] = doubled_hex(row[6][0], BITS)
                for pair in row[8]:
                    pair[0] = doubled_hex(pair[0], BITS)
                raw = _dump(row)
                selected = {'row_index': index, 'key': key, 'original_average_mass': old_mass,
                            'mutated_average_mass': row[6]}
            put(raw)
            body_digest.update(raw)
        footer = _loads(source.readline(MAX_LINE + 1))
        if (source.read(1) or selected is None or
                footer != {'end': value['rows'], 'body_sha256': source_digest.hexdigest()}):
            raise ValueError('q-free source changed or witness missing')
        require_equal(source_digest.hexdigest(), original_body_sha256, 'q-free mutation source digest')
        put(_dump({'end': value['rows'], 'body_sha256': body_digest.hexdigest()}))
    return {'detail': selected, 'source_body_sha256': source_digest.hexdigest(),
            'mutant_body_sha256': body_digest.hexdigest(), 'mutant_sha256': full_digest.hexdigest(),
            'mutant_bytes': total, 'source_bytes': info.st_size}


def expected_witness(owner, expected, source_path, output_path):
    """Check a terminal-only fork; never reopen or recover a poisoned owner.

    Accumulated rows/boards are shared read-only. Only the small Budget metadata
    is copied. `finish` never changes accumulated rows; no `add` is allowed on
    this fork. The original owner remains available for its one true finish.
    """
    if owner._closed or len(owner._boards) != 2520:
        raise ValueError('q-free witness requires complete unfinished accumulator')
    first = next(iter(owner._rows))
    key = first[0], (first[1], first[2]), first[3]
    receipt = mutate_expected(source_path, output_path, key, expected.receipt['body_sha256'])
    changed = saved_reference(output_path, 'expected')
    terminal = copy(owner)
    terminal._budget = deepcopy(owner._budget)
    original_budget = owner._budget.receipt()
    before = terminal._budget.receipt()
    error = None
    try:
        terminal.finish(changed)
    except ValueError as failure:
        error = str(failure)
    after = terminal._budget.receipt()
    if owner._closed or owner._budget.receipt() != original_budget:
        raise ValueError('terminal witness modified original accumulator')
    delta = {name: after[name] - before[name] for name in ('work', 'entries', 'created_bits')}
    # The chosen first row's average mass is the first numeric finish check.
    # Charge a conservative separate witness envelope; do not reset any owner.
    if delta['work'] > 16 or delta['entries'] > 32 or delta['created_bits'] > 131072:
        raise ValueError('q-free terminal witness exceeded first-scalar allowance')
    receipt.update({'kind': 'q_free_average_scale', 'parser_valid': True,
                    'detected': error == 'exact q-free expectation mismatch', 'error': error,
                    'additional_budget_actual': delta,
                    'scope': 'terminal-only snapshot of complete saved accumulation; no add/retry or numerical producer'})
    return receipt
