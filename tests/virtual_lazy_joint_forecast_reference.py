"""Independent composition for unchanged arithmetic with lazy Catalog storage."""
from tests.virtual_single_pass_forecast_reference import forecast as eager_forecast
from tests.virtual_lazy_catalog_reference import forecast as catalog_forecast
from tests.virtual_weighted_joint_reference import forecast as law_forecast, LIMITS, require
from tests.virtual_weighted_joint_raw_reference import SOURCE_WORK, RAW_WORK, SOURCE_BITS, RAW_BITS


def forecast():
    old = eager_forecast(); f = dict(old['components'])
    eager = catalog_forecast(868, 868, 434, 1326, 4774, False)
    lazy = catalog_forecast(868, 868, 434, 1326, 4774)
    require((f['catalog_words'], f['catalog_work']) == (eager['metadata_words'], eager['work']),
            'independent eager Catalog source bridge')
    removed = eager['metadata_words'] - lazy['metadata_words']
    f['catalog_words'] = lazy['metadata_words']; f['catalog_work'] = lazy['work']
    f['total_entries'] += 16 - removed; f['total_payload_bits'] += 128 - 64 * removed
    f['output_bytes'] += 16; f['output_serialization_work'] = 16 * f['output_bytes']
    f['total_work'] = sum(f[name] for name in ('template_work', 'catalog_work', 'history_work', 'chance_work',
        'store_component_work', 'parent_numeric_work', 'output_serialization_work'))
    law = law_forecast(52, (1326, 1326))
    # At most two frame-buffer copies plus fixed-width metadata/434-row checks.
    # Child law/source/raw reservations are composed once, not double-billed.
    bridge = 2 * f['output_bytes'] + 65536
    reference = {'work': law['work'] + SOURCE_WORK + RAW_WORK + bridge,
        'created_bits': law['created_bits'] + SOURCE_BITS + RAW_BITS + 16 * f['output_bytes'] + 65536,
        'entries': law['entries'] + 131072 + 500000 + 2 * f['output_bytes'] + 4096, 'integer_bits': 4096}
    return {**old, 'components': f, 'forecast_passes_caps': all(f[key] <= value for key, value in old['caps'].items()),
            'reference_combined_reservation': reference, 'reference_bridge_work': bridge,
            'reference_combined_passes_caps': all(reference[key] <= LIMITS[key] for key in LIMITS),
            'scope': 'Opt-in full52 T2 lazy Catalog scalar composition only. No longer lifetime, speed, RSS or quality claim.'}
