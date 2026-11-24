import unittest

from tests.virtual_lazy_joint_forecast_reference import forecast


class LazyJointForecastTests(unittest.TestCase):
    def test_complete_unchanged_cap_composition(self):
        result = forecast(); f = result['components']
        self.assertTrue(result['forecast_passes_caps']); self.assertTrue(result['reference_combined_passes_caps'])
        self.assertEqual((f['catalog_words'], f['catalog_work']), (167680, 29381344))
        self.assertEqual((f['total_work'], f['total_entries'], f['total_payload_bits'], f['output_bytes']),
                         (150030714, 953663, 52393006, 502768))
        self.assertEqual(result['reference_bridge_work'], 1071072)
        self.assertEqual(result['reference_combined_reservation']['work'], 499930720)


if __name__ == '__main__':
    unittest.main()
