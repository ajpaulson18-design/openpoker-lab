"""Independent scalar ledger for two true-joint PROOF9 observations.

No native code, range preparation, ranker, private-pair table or policy is used.
This is a logical resource model, not RSS, runtime or larger-game admission.
"""


def words(bits):
    return max(1, (bits + 63) // 64)


def copy(bits):
    return 1 + 2 * words(bits)


def add(bits):
    return 2 + 3 * words(bits)


def multiply(left, right):
    a, b = words(left), words(right)
    return 2 + 2 * (a + b) + a * b


def row_map(rows):
    return 128 + 32 * (rows + 1).bit_length()


def forecast():
    max_rows, max_slots, rows, slots, reads = 434, 1039, 868, 2078, 1736
    catalog_words = 1024 + 32 * 868 + 320 * 434 + 868
    lookup_cost = 512 + 256 * 20 + 32 * (868 + 1).bit_length() + 8
    catalog_work = 1024 + 8 * 868 + 8 * 434 + 6510 * lookup_cost
    constructor, lease = 2048, 256
    read = reads * (160 + 32 * 4 + 2 * row_map(rows)) + 2 * max_rows * 128
    stage_slot = (48 + copy(649) + add(649) + multiply(383, 317) + add(382) + 64 +
                  multiply(648, 53) + add(703) + 2 * multiply(383, 53) + add(383) +
                  2 * copy(436) + 32)
    stage = 2 * (1024 + max_rows * (512 + 2 * row_map(max_rows) + 2 * row_map(rows) + 4 * stage_slot))
    commit = 2 * (2048 + max_rows * (256 + row_map(rows) + 32 * 4 + 256))
    enumeration = 2 * max_rows * (256 + row_map(max_rows))
    export = 256 + 3 * max_rows * (256 + 4 * (copy(649) + copy(382) + 8))
    quantizer = 2 * max_rows * 12000
    own = constructor + lease + read + stage + commit + enumeration + export
    store_component = own + quantizer
    store_entries = 256 + 48 * rows + 16 * slots + 2048
    store_payload = 2 * slots * (649 + 382 + 64) + 2 * rows * 2048 + 64 * 64000
    raw = {
        'reach': 2 * 1039 * (24 + multiply(365, 53) + copy(365)),
        'scale': 2 * 606 * (32 + copy(629)),
        'mix': (2 * 1039 * (8 + multiply(629, 53) + add(683) + copy(683)) +
                2 * 434 * (32 + copy(683) + copy(629)) +
                1039 * (64 + add(630) + copy(630) + multiply(630, 365) + copy(630))),
        'average': 434 * (64 + copy(365)) + 1039 * (32 + multiply(313, 53) + copy(365) + 2 * words(365)),
        'stage': 1024 + 64 * 434 + 16 * 1039,
        'walk': 512 + 256 * 1105,
    }
    history = 4096 * 1105 + 1280 + 4 * (48 * 1039 + 80 * 65 + 8) + reads * 288 + rows * 640
    chance = 65536 + 2 * 16384
    parent = 1040000 + 4096 + 512 * rows + 2 * sum(raw.values())
    output = 336 + 2 * 600 + 40 * (3 * max_rows) + 144 * (3 * max_slots) + 256
    raw_stage_entries = 8 * max_rows + 2 * max_slots + 64 * 19 + 64
    entries = (131072 + catalog_words + store_entries + 12000 + 32 + (32 * 1105 + 1) +
               16384 + raw_stage_entries + output + 4096)
    payload = (131072 * 64 + 64 * catalog_words + store_payload + (1 << 20) + 1024 +
               (8 << 20) + (1 << 22) + 3140970 + 8 * output + 4096 * 64 + 32 * 181)
    total = 43000000 + catalog_work + history + chance + store_component + parent + 16 * output
    components = {
        'template_work': 43000000, 'catalog_work': catalog_work, 'history_work': history,
        'chance_work': chance, 'store_component_work': store_component, 'parent_numeric_work': parent,
        'output_serialization_work': 16 * output, 'total_work': total,
        'total_entries': entries, 'total_payload_bits': payload, 'output_bytes': output,
        'store_payload_bits': store_payload, 'store_entries': store_entries, 'catalog_words': catalog_words,
    }
    caps = {'template_work': 43000000, 'catalog_work': 75000000, 'history_work': 42000000,
            'chance_work': 110000000, 'store_component_work': 75000000, 'parent_numeric_work': 115000000,
            'total_work': 500000000, 'total_entries': 2000000, 'total_payload_bits': 1 << 30,
            'output_bytes': 2100000}
    return {
        'scope': 'fixed PROOF9 two deterministic true-joint observations; logical ledger only',
        'tickets': 580, 'ordered_ticket_pairs': 336400,
        'raw_rows': max_rows, 'raw_slots': max_slots, 'reads_per_observation': 868,
        'rank_calls': 4, 'weighted_contractions': 0, 'raw_families': raw,
        'store': {'constructor': constructor, 'lease': lease, 'read': read, 'stage': stage,
                  'commit': commit, 'enumeration': enumeration, 'export': export,
                  'own': own, 'quantizer': quantizer, 'component': store_component},
        'components': components, 'caps': caps,
        'forecast_passes_caps': all(components[name] <= value for name, value in caps.items()),
        'allocation_scope': 'Conservative logical cells and numeric payload; not a complete allocator census or RSS.',
    }
