"""Independent saved full52 wire replay; native/archive execution forbidden."""
from hashlib import sha256
from itertools import combinations
import json
import struct

from tests.virtual_weighted_joint_forecast_reference import forecast
from tests.virtual_weighted_joint_reference import require


def verify(profile, selectors, raw):
    resource = forecast(); f = resource['components']
    require(resource['forecast_passes_caps'], 'weighted whole scalar admission')
    require(type(profile) is int and profile in (0, 1) and type(selectors) is tuple and len(selectors) == 2 and
            all(type(item) is tuple and len(item) == 2 and all(type(value) is int for value in item) and
                0 <= item[0] < resource['profile_normalizers'][profile] and 0 <= item[1] < resource['board_count']
                for item in selectors), 'weighted complete selector domain')
    require(type(raw) is bytes and 1824 <= len(raw) <= f['output_bytes'] and raw[:8] == b'OPLWEP01',
            'weighted wire version/byte boundary')
    header = (1, 2, 0, 0, 1 << 52, f['total_work'], f['total_entries'], f['total_payload_bits'],
              f['output_bytes'], f['catalog_work'], f['history_work'], f['chance_work'],
              f['store_component_work'], f['parent_numeric_work'], 6510, 1105, 388, 410, 12, 11, 704, 181, 0, 1,
              52, profile, 1326, 1326)
    require(struct.unpack_from('<28Q', raw, 8) == header, 'weighted independent whole header/implicit-uniform contract')
    position = 232
    def take(count):
        nonlocal position
        require(type(count) is int and 0 <= count <= len(raw) - position, 'weighted frame truncation')
        value = raw[position:position + count]; position += count; return value
    def words(count):
        return struct.unpack('<' + 'Q' * count, take(8 * count))
    def integer(size, signed, bits):
        value = int.from_bytes(take(size), 'little', signed=signed)
        require(abs(value).bit_length() <= bits, 'weighted wire integer magnitude')
        return value
    require(integer(88, False, 626) == 1 << 625 and integer(48, False, 365) == 1 << 364,
            'weighted exact pure-power denominators')
    # The entire native byte/domain boundary is checked before full ranges,
    # independent law preparation or selected-world numeric arithmetic.
    from tests.virtual_weighted_joint_raw_reference import Request, two_epochs
    from tests.virtual_sparse_epoch_reference import _uniform_row
    def binary64(value):
        return int.from_bytes(struct.pack('>d', float(value)), 'big')
    side = tuple((hand, binary64(index % 7 + 1 if profile else 1))
                 for index, hand in enumerate(combinations(range(52), 2)))
    request = Request(tuple(range(52)), (side, side))
    observations = two_epochs(request, selectors)
    transport = {}; results = []; quantized = exports = export_slots = 0
    previous = (0,) * 5
    for epoch, observation in enumerate(observations, 1):
        world = observation['world']; numeric = observation['numeric']; policy = observation['policy']
        for key, row in observation['raw'].items():
            token = key[0], key[1], row.ordinal
            require(token not in transport or transport[token][0] == key, 'weighted independent transport collision')
            transport[token] = key, row.source, len(row.menu)
        quantized += sum(any(row.regrets) for row in observation['raw'].values())
        count = len(numeric); slots = sum(len(pair[0]) for pair in numeric.values())
        exports += count; export_slots += slots
        size = 600 + 40 * count + 144 * slots
        start = position
        require(take(8) == b'OPLWEB01', 'weighted epoch version')
        require(words(20) == (1, epoch, *selectors[epoch - 1], *world.holding_indices, *world.board,
                              count, slots, 434, 1039, 868, quantized, 434 * epoch, 868 * epoch, size),
                'weighted independently predicted epoch inventory')
        roots = integer(88, True, 629), integer(88, True, 629)
        require(roots == (observation['root'], -observation['root']), 'weighted independent frozen root')
        seen = set(); overlays = {}
        for _ in range(count):
            actor, holding, ordinal, source, actions = words(5)
            require(actor < 2 and holding < 1326 and 2 <= actions <= 4, 'weighted original row descriptor boundary')
            token = actor, holding, ordinal
            require(token in transport, 'weighted unexpected decision identity')
            key, expected_source, expected_actions = transport[token]
            require(key in numeric and key not in seen and (source, actions) == (expected_source, expected_actions),
                    'weighted visible-history/source/action row identity')
            seen.add(key); regrets, averages, units = [], [], []
            for _action in range(actions):
                regrets.append(integer(88, True, 631)); averages.append(integer(48, False, 366)); units.append(words(1)[0])
            require((tuple(regrets), tuple(averages)) == numeric[key], 'weighted independent cumulative signed R/A')
            require(tuple(units) == policy.rows.get(key, _uniform_row(actions)) and sum(units) == 1 << 52,
                    'weighted independent next Q52 policy')
            # Canonical sparse digest binds explicit overlays + default contract,
            # not a fictional enumeration of the15.9T information universe.
            if key in policy.rows:
                overlays[key] = tuple(units)
        require(seen == set(numeric) and overlays == dict(policy.rows), 'weighted complete retained numeric/policy overlay image')
        footer = words(32)
        require(footer[:2] == (1, epoch) and all(a <= b for a, b in zip(previous, footer[2:7])),
                'weighted cumulative component work monotonicity')
        previous = footer[2:7]
        public_blocks = len({(actor, ordinal) for actor, _holding, ordinal in transport})
        seen_slots = sum(value[2] for value in transport.values())
        menus = len({value[1] for value in transport.values()})
        lookups = epoch * 2604 + exports
        require(footer[2] <= resource['components']['store_component_work'] and footer[3] <= 868 * 12000 and
                footer[4] <= f['catalog_work'] and footer[5] <= f['history_work'] and footer[6] <= f['chance_work'],
                'weighted actual component exceeds forecast')
        require(footer[7] == sum(resource['raw_families'].values()) and
                footer[8:14] == (count, slots, epoch * 434, epoch * 1039, epoch * 868, quantized) and
                footer[14] <= f['store_payload_bits'] and
                footer[15:20] == (public_blocks, len(transport), seen_slots, menus, lookups) and
                footer[20:22] == (epoch * 2, 0) and footer[22:26] == (2210, 2078, 130, 1212) and
                footer[26] <= 683 and footer[27:] == (epoch, exports, export_slots, 1, epoch),
                'weighted independently bounded counters/complete traversal')
        require(position - start == size, 'weighted epoch byte census')
        digest = sha256(b'weighted-sparse-policy-v1\nuniform-q52\n')
        for key in sorted(policy.rows):
            digest.update(json.dumps([key, policy.rows[key]], separators=(',', ':')).encode() + b'\n')
        results.append({'epoch': epoch, 'holding_indices': world.holding_indices, 'board': world.board,
                        'numeric_rows': count, 'numeric_slots': slots, 'policy_overlay_rows': len(overlays),
                        'sparse_policy_sha256': digest.hexdigest(), 'root_scaled_integer': str(observation['root'])})
    final = words(32)
    require(position == len(raw) and final[:2] == (1, 2) and final[10] == len(raw), 'weighted final frame boundary')
    require(final[2] == sum(final[3:10]) + 16 * final[10] and final[2] <= f['total_work'] and
            final[3] <= f['template_work'] and final[4] <= f['parent_numeric_work'] and
            final[5] + final[6] <= f['store_component_work'] and final[7] <= f['catalog_work'] and
            final[8] <= f['history_work'] and final[9] == f['chance_work'], 'weighted independently composed actual work')
    require(final[11:15] == (868, 2078, 1736, quantized) and
            final[15:20] == (results[-1]['numeric_rows'], results[-1]['numeric_slots'], 2, exports, export_slots) and
            final[20:25] == (public_blocks, len(transport), seen_slots, menus, lookups) and
            final[25:] == (4, 0, 4420, 4156, 260, 1, 2), 'weighted independently complete cumulative counters')
    return {'status': 'weighted-joint-all-retained-rows-exact', 'profile': profile, 'epochs': results,
            'bytes': len(raw), 'stdout_sha256': sha256(raw).hexdigest(), 'whole_actual_work': final[2],
            'whole_forecast': f, 'reference_request_reservation': dict(request.forecast),
            'candidate_calls': 0, 'archived_source_executed': False,
            'scope': 'Named full52 finite fixed-tree T2 sparse witness only; no RNG, longer learning, convergence or quality.'}
