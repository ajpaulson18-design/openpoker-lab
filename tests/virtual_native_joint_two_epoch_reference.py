"""Independent full-policy replay of deterministic native joint observations."""
from fractions import Fraction
import struct


def require(value, message):
    if not value:
        raise ValueError(message)


def verify_joint_wire(selectors, raw):
    # Framing/whole-domain admission precede Fixture/ranker/private preparation.
    from tests.virtual_joint_two_epoch_forecast_reference import forecast
    resource = forecast()
    require(resource['forecast_passes_caps'], 'joint independent complete-domain admission')
    f = resource['components']
    require(type(raw) is bytes and 1792 <= len(raw) <= f['output_bytes'] and
            raw[:8] == b'OPLJEP01', 'joint wire version or byte boundary')
    require(type(selectors) is tuple and len(selectors) == 2 and
            all(type(item) is tuple and len(item) == 2 and
                all(type(value) is int for value in item) and 0 <= item[0] < 29 and 0 <= item[1] < 20
                for item in selectors), 'joint two exact selectors')
    q = 1 << 52
    header = (1, 2, 24420, 58164, q, f['total_work'], f['total_entries'], f['total_payload_bits'],
              f['output_bytes'], f['catalog_work'], f['history_work'], f['chance_work'],
              f['store_component_work'], f['parent_numeric_work'], 6510, 1105, 388, 410, 12, 11, 704, 384, 0, 1)
    require(struct.unpack_from('<24Q', raw, 8) == header, 'joint independently composed cumulative header')
    position = 200

    def take(count):
        nonlocal position
        require(type(count) is int and 0 <= count <= len(raw) - position, 'joint frame truncation')
        result = raw[position:position + count]; position += count
        return result

    def words(count):
        return struct.unpack('<' + 'Q' * count, take(8 * count))

    def integer(size, signed, bits):
        value = int.from_bytes(take(size), 'little', signed=signed)
        require(abs(value).bit_length() <= bits, 'joint wire integer magnitude')
        return value

    dr, da = 1 << 625, 1 << 364
    require(integer(88, False, 626) == dr and integer(48, False, 365) == da, 'joint pure-power denominators')
    from tests.virtual_joint_sample_reference import Request
    from tests.virtual_joint_two_epoch_reference import two_epochs, policy_digest
    request = Request()
    fixture = request.fixture
    initial, observations = two_epochs(request, selectors)
    previous_work = (0,) * 5
    exports = export_slots = 0
    epoch_results = []
    raw_total = sum(resource['raw_families'].values())
    for index, observation in enumerate(observations, 1):
        start = position
        require(take(8) == b'OPLJEB01', 'joint epoch frame version')
        numeric = observation['numeric']; policy = observation['policy']
        rows = len(numeric); slots = sum(len(fixture.menus[key]) for key in numeric)
        exports += rows; export_slots += slots
        record_bytes = 600 + 40 * rows + 144 * slots
        require(words(20) == (1, index, *selectors[index - 1], *observation['holdings'], *observation['board'],
                             rows, slots, 434, 1039, 868, observation['quantized_rows'],
                             observation['staged_rows'], 868 * index, record_bytes), 'joint epoch selector/inventory')
        root = observation['root']
        roots = tuple(Fraction(integer(88, True, 629), dr) for _ in range(2))
        require(roots == (root, -root), 'joint independent frozen-policy root values')
        seen = set(); decoded = dict(initial)
        for _ in range(rows):
            actor, holding, ordinal, source, count = words(5)
            require(actor < 2 and holding < 2 and 2 <= count <= 4, 'joint row descriptor boundary')
            key = fixture.compact_key(ordinal, actor, holding)
            require(key in numeric and key not in seen and count == len(fixture.menus[key]) and
                    fixture.paths[ordinal >> 33][0] == source, 'joint full visible history/original holding/menu')
            seen.add(key)
            regrets, averages, units = [], [], []
            for _action in range(count):
                regrets.append(integer(88, True, 631)); averages.append(integer(48, False, 366)); units.append(words(1)[0])
            require((tuple(regrets), tuple(averages)) == numeric[key], 'joint cumulative signed regret and exact average')
            require(tuple(units) == policy[key] and sum(units) == q, 'joint independently apportioned current policy')
            decoded[key] = tuple(units)
        require(seen == set(numeric) and decoded == policy and len(decoded) == 24420,
                'joint complete policy including every untouched uniform row')
        footer = words(32)
        require(footer[:2] == (1, index) and footer[8:14] ==
                (rows, slots, 434 * index, 1039 * index, 868 * index, observation['quantized_rows']),
                'joint cumulative two-read/stage/quantization counters')
        current_work = footer[2:7]
        require(all(new >= old for new, old in zip(current_work, previous_work)), 'joint monotonic shared-owner work')
        previous_work = current_work
        require(footer[7] == raw_total and footer[2] <= resource['store']['own'] and
                footer[3] <= resource['store']['quantizer'] and footer[2] + footer[3] <= f['store_component_work'] and
                footer[4] <= f['catalog_work'] and footer[5] <= f['history_work'] and footer[6] <= f['chance_work'],
                'joint exact raw ledger and component ceilings')
        require(footer[14] <= f['store_payload_bits'] and footer[15] <= 868 and
                rows <= footer[16] <= 868 and slots <= footer[17] <= 2078 and
                footer[18] <= 434 and footer[19] <= 6510, 'joint sparse storage/catalog bounds')
        require(footer[20:26] == (2 * index, 0, 2210, 2078, 130, 1212) and footer[26] <= 683 and
                footer[27:] == (index, exports, export_slots, 1, index),
                'joint genuine target passes/selected ranks/no weighted contractions')
        require(position - start == record_bytes, 'joint exact snapshot record extent')
        digest = policy_digest(fixture, decoded)
        require(digest == observation['policy_sha256'], 'joint all-row current policy digest')
        epoch_results.append({'epoch': index, 'selector': selectors[index - 1],
                              'holdings': observation['holdings'], 'board': observation['board'],
                              'numeric_rows': rows, 'numeric_slots': slots,
                              'input_policy_sha256': observation['input_policy_sha256'], 'policy_sha256': digest,
                              'root': [str(root.numerator), str(root.denominator)],
                              'raw_rows': 434, 'raw_slots': 1039,
                              'quantized_rows': observation['quantized_rows']})
    footer = words(32)
    require(position == len(raw), 'joint trailing wire bytes')
    (version, epochs, actual, source_work, parent, store_work, quant_work, cat_work, history_work,
     chance_work, wire_bytes, staged_rows, staged_slots, reads, quant_rows, current_rows,
     current_slots, export_calls, export_rows, exported_slots, blocks, cat_rows, cat_slots,
     menus, lookups, ranks, contractions, visits, actions, reveals, complete, joint_queries) = footer
    require((version, epochs, wire_bytes, staged_rows, staged_slots, reads, quant_rows,
             current_rows, current_slots, export_calls, export_rows, exported_slots) ==
            (1, 2, len(raw), 868, 2078, 1736, observations[-1]['quantized_rows'],
             epoch_results[-1]['numeric_rows'], epoch_results[-1]['numeric_slots'], 2, exports, export_slots),
            'joint global numerical lifecycle')
    require((ranks, contractions, visits, actions, reveals, complete, joint_queries) == (4, 0, 4420, 4156, 260, 1, 2) and
            blocks <= 868 and current_rows <= cat_rows <= 868 and current_slots <= cat_slots <= 2078 and
            menus <= 434 and lookups <= 6510, 'joint global scoped chance and traversal counters')
    require((store_work, quant_work, cat_work, history_work, chance_work) == previous_work and
            parent == 1040000 + 4096 + 512 * staged_rows + 2 * raw_total,
            'joint one-owner receipt links and exact parent composition')
    require(source_work <= f['template_work'] and parent <= f['parent_numeric_work'] and
            store_work <= resource['store']['own'] and quant_work <= resource['store']['quantizer'] and
            store_work + quant_work <= f['store_component_work'] and cat_work <= f['catalog_work'] and
            history_work <= f['history_work'] and chance_work <= f['chance_work'], 'joint complete component admission')
    require(actual == source_work + parent + store_work + quant_work + cat_work + history_work + chance_work + 16 * len(raw)
            and actual <= f['total_work'], 'joint single cumulative request accounting')
    return {'status': 'joint-two-epochs-all-rows-exact', 'epochs': epoch_results,
            'work_actual': actual, 'work_forecast': f['total_work'], 'output_bytes': len(raw),
            'policy_reads': reads, 'staged_rows': staged_rows, 'quantized_rows': quant_rows,
            'implicit_policy_rows': 24420, 'rank_calls': ranks, 'chance_contractions': contractions,
            'joint_ticket_queries': joint_queries, 'rng_calls': 0, 'quality_gate': None,
            'scope': 'two deterministic true-joint PROOF9 observations; no RNG, convergence, quality or full-range admission'}
