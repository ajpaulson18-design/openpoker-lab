"""Independent full-history and numerical replay of sparse two-epoch output."""
from fractions import Fraction
from hashlib import sha256
import struct

from tests.virtual_dyadic_training_reference import Q
from tests.virtual_frozen_grid_envelope_reference import envelope
from tests.virtual_sparse_epoch_reference import REGRET_DENOMINATOR, AVERAGE_DENOMINATOR
from tests.virtual_sparse_two_epoch_forecast_reference import forecast


def require(value, message):
    if not value:
        raise ValueError(message)


def policy_hash(fixture, policy):
    digest = sha256()
    for key in fixture.ordered_rows():
        for value in policy[key]:
            digest.update(value.to_bytes(8, 'little'))
    return digest.hexdigest()


def verify_sparse_wire(fixture, context, selectors, raw):
    # This module imports only current independent rules/math. Native owners,
    # forecast helpers and project rankers are never numerical authorities.
    from tests.virtual_sparse_two_epoch_reference import two_epochs
    require(type(raw) is bytes and 592 <= len(raw) <= 619152, 'sparse wire byte bound')
    require(len(selectors) == 2 and raw[:8] == b'OPLSEP01', 'sparse wire version')
    f = forecast()['components']
    expected = (1, 2, 24420, 58164, Q, f['total_work'], f['total_entries'],
                f['total_payload_bits'], f['output_bytes'], f['catalog_work'],
                f['history_work'], f['chance_work'], f['store_component_work'],
                f['parent_numeric_work'], 7950, 1105, 388, 410, 12, 11, 704, 384, 0, 1)
    require(struct.unpack_from('<24Q', raw, 8) == expected, 'sparse independent cumulative header')
    position = 200

    def take(count):
        nonlocal position
        require(0 <= count <= len(raw) - position, 'sparse frame truncation')
        result = raw[position:position + count]
        position += count
        return result

    def words(count):
        return struct.unpack('<' + 'Q' * count, take(8 * count))

    def integer(size, signed, bits):
        value = int.from_bytes(take(size), 'little', signed=signed)
        require(abs(value).bit_length() <= bits, 'sparse integer magnitude')
        return value

    require(integer(88, False, 635) == REGRET_DENOMINATOR and
            integer(48, False, 374) == AVERAGE_DENOMINATOR, 'sparse fixed denominator')
    initial, observations = two_epochs(fixture, context, *selectors)
    stages = reads = quantized = exports = export_slots = 0
    previous_work = (0,) * 5
    raw_ledgers = []
    epoch_results = []
    for index, (board, observation) in enumerate(zip(selectors, observations), 1):
        start = position
        require(take(8) == b'OPLSEB01', 'sparse epoch version')
        header = words(16)
        state = observation['state']
        numeric = state.numeric_rows
        slots = sum(len(fixture.menus[key]) for key in numeric)
        e = envelope(tuple(board))
        stages += e[0]
        reads += 2 * e[0]
        quantized += observation['quantized_rows']
        exports += len(numeric)
        export_slots += slots
        record_bytes = 568 + 40 * len(numeric) + 144 * slots
        require(header == (1, index, *board, len(numeric), slots, e[0], e[1], 2 * e[0],
                           quantized, stages, reads, record_bytes), 'sparse epoch inventory')
        root = observation['root']
        roots = tuple(Fraction(integer(88, True, 648), REGRET_DENOMINATOR) for _ in range(2))
        require(roots == (root, -root), 'sparse independently recomputed frozen-policy roots')
        seen = set()
        decoded_policy = dict(initial.policy)
        for _ in range(len(numeric)):
            actor, holding, ordinal, source, count = words(5)
            key = fixture.compact_key(ordinal, actor, holding)
            require(key in numeric and key not in seen and count == len(fixture.menus[key]),
                    'sparse row full visible history/holding/menu')
            require(fixture.paths[ordinal >> 33][0] == source, 'sparse source menu identity')
            seen.add(key)
            regrets, averages, units = [], [], []
            for _ in range(count):
                regrets.append(integer(88, True, 649))
                averages.append(integer(48, False, 382))
                units.append(words(1)[0])
            require((tuple(regrets), tuple(averages)) == numeric[key], 'sparse cumulative signed R/exact A')
            require(tuple(units) == state.policy[key] and sum(units) == Q,
                    'sparse independently apportioned next policy')
            decoded_policy[key] = tuple(units)
        require(seen == set(numeric), 'sparse complete numerical snapshot')
        # Verify implicit defaults too, including every non-exported physical
        # information set. Sparse output cannot conceal a missing changed row.
        require(decoded_policy == dict(state.policy) and len(decoded_policy) == 24420,
                'sparse all-row policy including untouched defaults')
        footer = words(32)
        require(footer[:2] == (1, index) and footer[8:14] ==
                (len(numeric), slots, stages, sum(envelope(tuple(b))[1] for b in selectors[:index]), reads, quantized),
                'sparse cumulative state counters')
        current_work = footer[2:7]
        require(all(new >= old for new, old in zip(current_work, previous_work)), 'sparse monotonic owner work')
        previous_work = current_work
        expected_raw_ledger = sum(e[6:12]) - 2 * 434 * (23 + 23)
        require(footer[7] == expected_raw_ledger, 'sparse exact raw numerical operation ledger')
        raw_ledgers.append(footer[7])
        require(footer[2] + footer[3] <= f['store_component_work'] and
                footer[4] <= f['catalog_work'] and footer[5] <= f['history_work'] and
                footer[6] <= f['chance_work'], 'sparse epoch component work bounds')
        require(footer[14] <= f['store_payload_bits'] and footer[15] <= 1060 and
                footer[16] <= 1060 and footer[17] <= 2564 and footer[18] <= 434 and footer[19] <= 7950,
                'sparse bounded owner storage/access')
        require(footer[20] <= 4 * index and footer[21] == 1220 * index and
                footer[22:26] == (2210, 2078, 130, 1212) and footer[26] <= 699 and
                footer[27:] == (index, exports, export_slots, 1, 0), 'sparse traversal/complete export counters')
        require(position - start == record_bytes, 'sparse exact epoch record extent')
        epoch_results.append({'epoch': index, 'board': tuple(board), 'numeric_rows': len(numeric),
                              'numeric_slots': slots, 'policy_sha256': policy_hash(fixture, decoded_policy),
                              'root': [str(root.numerator), str(root.denominator)],
                              'raw_rows': e[0], 'raw_slots': e[1], 'quantized_rows': quantized})
    footer = words(32)
    require(position == len(raw), 'sparse trailing bytes')
    (version, epochs, actual, source_work, parent, store_work, quant_work, cat_work, history_work,
     chance_work, wire_bytes, staged_rows, staged_slots, policy_reads, quant_rows, current_rows,
     current_slots, export_calls, export_rows, export_slot_count, blocks, cat_rows, cat_slots,
     menus, lookups, ranks, contractions, visits, actions, reveals, complete, reserved) = footer
    require((version, epochs, wire_bytes, staged_rows, staged_slots, policy_reads, quant_rows,
             current_rows, current_slots, export_calls, export_rows, export_slot_count) ==
            (1, 2, len(raw), stages, sum(envelope(tuple(b))[1] for b in selectors), reads, quantized,
             epoch_results[-1]['numeric_rows'], epoch_results[-1]['numeric_slots'], 2, exports, export_slots),
            'sparse global numerical lifecycle')
    require((contractions, visits, actions, reveals, complete, reserved) == (2440, 4420, 4156, 260, 1, 0) and
            ranks <= 8 and blocks <= 1060 and cat_rows <= 1060 and cat_slots <= 2564 and menus <= 434 and lookups <= 7950,
            'sparse global traversal/catalog bounds')
    require(source_work <= 43000000 and parent <= f['parent_numeric_work'] and
            store_work + quant_work <= f['store_component_work'] and cat_work <= f['catalog_work'] and
            history_work <= f['history_work'] and chance_work <= f['chance_work'], 'sparse component work admission')
    require((store_work, quant_work, cat_work, history_work, chance_work) == previous_work and
            parent == 1040000 + 4096 + 512 * stages + sum(raw_ledgers),
            'sparse shared owner receipts and exact parent composition')
    require(actual == source_work + parent + store_work + quant_work + cat_work + history_work + chance_work + 16 * len(raw)
            and actual <= f['total_work'], 'sparse single cumulative request work')
    return {'status': 'two-epochs-all-rows-exact', 'epochs': epoch_results, 'work_actual': actual,
            'work_forecast': f['total_work'], 'output_bytes': len(raw), 'policy_reads': reads,
            'staged_rows': stages, 'quantized_rows': quantized, 'implicit_policy_rows': 24420,
            'rank_calls': ranks, 'chance_contractions': contractions,
            'scope': 'two selected uniform PROOF9 observations; no RNG, convergence, solved quality or wider admission'}
