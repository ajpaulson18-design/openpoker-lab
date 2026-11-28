"""Independent one-global-walk census; no candidate or source execution."""
from tests.virtual_weighted_joint_forecast_reference import forecast as baseline
from tests.virtual_joint_two_epoch_forecast_reference import add, copy, multiply


def forecast():
    old = baseline(); f = dict(old['components']); raw = dict(old['raw_families'])
    raw['reach'] = 1039 * (24 + multiply(365, 53) + copy(365))
    raw['scale'] = 606 * (32 + copy(629))
    raw['mix'] = (1039 * (8 + multiply(629, 53) + add(683) + copy(683)) +
                  434 * (32 + copy(683) + copy(629)) +
                  1039 * (64 + add(630) + copy(630) + multiply(630, 365) + copy(630)))
    raw['walk'] = 512 + 1105 * (128 + 128)
    # One frozen read per row instead of two:1736-868 reads removed. Each
    # removed read owns1184 Store units and two Catalog accesses of6120.
    f['catalog_work'] -= 868 * 2 * 6120
    f['history_work'] -= 2 * (48 * 1039 + 80 * 65 + 8) + 868 * 288
    f['store_component_work'] -= 868 * 1184
    f['parent_numeric_work'] = 1040000 + 4096 + 512 * 868 + 2 * sum(raw.values())
    f['total_work'] = sum(f[name] for name in ('template_work', 'catalog_work', 'history_work', 'chance_work',
        'store_component_work', 'parent_numeric_work', 'output_serialization_work'))
    return {**old, 'components': f, 'raw_families': raw, 'reads_per_observation': 434,
            'catalog_lookups': 4774, 'walk_visits_per_observation': 1105,
            'forecast_passes_caps': all(f[key] <= value for key, value in old['caps'].items()),
            'scope': 'Named full52 T2 single global-value walk scalar candidate; no timing/admission/quality claim.'}
