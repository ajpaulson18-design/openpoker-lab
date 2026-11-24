"""Authenticate lazy storage/resource changes, then reuse unchanged exact math.

The eager authority sees a precisely normalized current wire. Every changed
schema/resource field is independently checked; raw mathematical bytes are
never changed. No native or archived source execution occurs.
"""
from hashlib import sha256
import struct

from tests.virtual_lazy_joint_forecast_reference import forecast
from tests.virtual_single_pass_forecast_reference import forecast as eager_forecast
from tests.virtual_weighted_joint_reference import require, LIMITS


def header(f, profile, contract):
    return (1, 2, 0, 0, 1 << 52, f['total_work'], f['total_entries'], f['total_payload_bits'],
            f['output_bytes'], f['catalog_work'], f['history_work'], f['chance_work'],
            f['store_component_work'], f['parent_numeric_work'], 4774, 1105, 388, 410, 12, 11, 704, 181, 0, contract,
            52, profile, 1326, 1326)


def verify(profile, selectors, raw):
    resource = forecast(); f = resource['components']; old = eager_forecast()['components']
    require(resource['forecast_passes_caps'] and resource['reference_combined_passes_caps'], 'lazy complete native/reference scalar admission')
    require(type(profile) is int and profile in (0, 1) and type(selectors) is tuple and len(selectors) == 2 and
            all(type(item) is tuple and len(item) == 2 and all(type(x) is int for x in item) and
                0 <= item[0] < resource['profile_normalizers'][profile] and 0 <= item[1] < resource['board_count']
                for item in selectors), 'lazy complete selected-world domain')
    require(type(raw) is bytes and 1840 <= len(raw) <= f['output_bytes'] and raw[:8] == b'OPLLGP01' and
            struct.unpack_from('<28Q', raw, 8) == header(f, profile, 3), 'lazy global schema/resource contract')
    # Pre-admit both copies and all numerical child reservations before copying
    # the frame or preparing the law/template. Metadata loops are fixed-size.
    from scripts.matrix_free_certificate_budget import Budget
    combined = resource['reference_combined_reservation']; budget = Budget(dict(LIMITS))
    budget.charge('law_source_raw_and_lazy_frame_bridge_reserved', combined['work'])
    budget.entries(combined['entries'], 'numerical child owners and two bounded frame buffers')
    budget.created_bits = combined['created_bits']; budget.max_forecast_bits = combined['integer_bits']
    canonical = bytearray(memoryview(raw)[:-16])
    canonical[:8] = b'OPLSGP01'; struct.pack_into('<28Q', canonical, 8, *header(old, profile, 2))
    position = 368; epochs = []
    for epoch in (1, 2):
        require(position <= len(raw) - 168 and raw[position:position + 8] == b'OPLLGB01', 'lazy epoch version/boundary')
        fields = struct.unpack_from('<20Q', raw, position + 8); count, slots, size = fields[11], fields[12], fields[19]
        require(fields[:2] == (1, epoch) and count <= 868 and slots <= 2078 and
                size == 600 + 40 * count + 144 * slots and size <= len(raw) - position - 272, 'lazy bounded epoch extent')
        footer_at = position + size - 256; footer = list(struct.unpack_from('<32Q', raw, footer_at))
        require(footer[19] <= 4774 and footer[4] <= f['catalog_work'], 'lazy cumulative Catalog work/lookups')
        extra = 256 + 32 * footer[19]
        require(footer[4] >= extra, 'lazy Catalog work bridge underflow')
        footer[4] -= extra
        canonical[position:position + 8] = b'OPLSGB01'; struct.pack_into('<32Q', canonical, footer_at, *footer)
        epochs.append((position, fields)); position += size
    require(position + 272 == len(raw), 'lazy exact final extent')
    final = list(struct.unpack_from('<32Q', raw, position)); bitmap_words, occupied_words = struct.unpack_from('<2Q', raw, position + 256)
    require(final[:2] == (1, 2) and final[10] == len(raw) and final[24] <= 4774 and
            final[2] == sum(final[3:10]) + 16 * final[10] and final[2] <= f['total_work'] and
            final[7] <= f['catalog_work'] and bitmap_words <= 21 * 434 and occupied_words <= f['catalog_words'],
            'lazy final actual work/storage admission')
    extra = 256 + 32 * final[24]
    require(final[7] >= extra and final[2] >= extra + 256, 'lazy final resource bridge underflow')
    final[7] -= extra; final[2] -= extra + 256; final[10] -= 16
    struct.pack_into('<32Q', canonical, position, *final)
    # This is the second and last complete frame copy. The existing authority
    # validates every root/R/A/unit and all default/identity/traversal contracts.
    current_wire = bytes(canonical)
    from tests.virtual_native_single_pass_reference import verify as eager_verify
    numerical = eager_verify(profile, selectors, current_wire)
    require(numerical['reference_request_reservation']['work'] + resource['reference_bridge_work'] == combined['work'],
            'lazy bridge and child work composition')
    # E0 has positive uniform reach at every selected-world decision. Its first
    #434 authenticated retained descriptors therefore enumerate all public paths.
    first_at, first = epochs[0]; second = epochs[1][1]
    require(first[11:13] == (434, 1039), 'lazy first uniform complete row census')
    row_at = first_at + 344; promoted = 0
    for _ in range(434):
        actor, holding, ordinal, _source, actions = struct.unpack_from('<5Q', raw, row_at)
        require(actor < 2 and 2 <= actions <= 4, 'lazy authenticated descriptor domain')
        visible = (ordinal >> 30) & 7
        require(visible in (0, 3, 4, 5), 'lazy visible prefix length')
        if first[6:6 + visible] == second[6:6 + visible] and holding != second[4 + actor]:
            promoted += 1
        row_at += 40 + 144 * actions
    require(row_at == first_at + first[19] - 256 and bitmap_words == 21 * promoted and
            occupied_words == 1024 + 32 * final[20] + 320 * final[23] + bitmap_words,
            'lazy independent exact promoted-bitmap/occupied-ledger replay')
    return {'status': 'lazy-joint-all-retained-numerics-and-storage-exact', 'profile': profile,
            'epochs': numerical['epochs'], 'bytes': len(raw), 'stdout_sha256': sha256(raw).hexdigest(),
            'canonical_eager_stdout_sha256': sha256(current_wire).hexdigest(),
            'whole_actual_work': final[2] + extra + 256, 'whole_forecast': f,
            'allocated_bitmap_words': bitmap_words, 'promoted_public_blocks': promoted,
            'peak_occupied_metadata_words': occupied_words,
            'reference_combined_reservation': combined, 'candidate_calls': 0, 'archived_source_executed': False,
            'scope': 'Opt-in full52 fixed-tree T2 exact lazy Catalog witness only. No RNG, longer learning, speed, RSS, convergence or quality admission.'}
