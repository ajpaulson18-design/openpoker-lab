"""Independent scalar composition for named full52 T2 native requests."""
from tests.virtual_joint_two_epoch_forecast_reference import forecast as n9_forecast


def forecast():
    prior = n9_forecast()
    # Same fixed route/action template; original holding identities now have a
    # 21-word seen bitmap per public block, rather than the N9 one-word bitmap.
    f = dict(prior['components'])
    extra_catalog_words = 868 * (21 - 1)
    f['catalog_words'] += extra_catalog_words
    f['catalog_work'] += 6510 * 8 * (21 - 1)
    f['chance_work'] = 65536 + 16384 * 2652 + 2 * (12288 + 64 * 1326 + 256 * (1326).bit_length())
    raw = dict(prior['raw_families']); raw['walk'] += 128 * 2 * 1105
    f['parent_numeric_work'] += 2 * 128 * 2 * 1105
    f['output_bytes'] += 32
    f['output_serialization_work'] = 16 * f['output_bytes']
    f['total_entries'] += extra_catalog_words + (256 - 128) + 32
    f['total_payload_bits'] += 64 * extra_catalog_words + (8192 - 1024) + 8 * 32
    f['total_work'] = sum(f[name] for name in ('template_work', 'catalog_work', 'history_work', 'chance_work',
        'store_component_work', 'parent_numeric_work', 'output_serialization_work'))
    return {'components': f, 'caps': prior['caps'], 'raw_families': raw,
            'forecast_passes_caps': all(f[key] <= value for key, value in prior['caps'].items()),
            'original_holding_counts': (1326, 1326), 'deck_size': 52,
            'raw_rows': 434, 'raw_slots': 1039, 'reads_per_observation': 868,
            'chance_owner_entries': 11076, 'chance_peak_entries': 11332,
            'chance_owner_payload_bits': 330407, 'chance_peak_payload_bits': 338599,
            'profile_normalizers': (1624350, 25908876), 'board_count': 34246080,
            'scope': 'Named full52 uniform/1..7 two-observation scalar admission only; no long learning or quality.'}
