"""Independent complete feasible-state reservation and architecture boundaries."""
import unittest

from tests.virtual_lazy_catalog_reference import feasible_peak, forecast


class LazyCatalogReferenceTests(unittest.TestCase):
    def test_peak_matches_every_bounded_feasible_descriptor_bitmap_state(self):
        for blocks in range(1, 17):
            for rows in range(blocks, min(40, 2 * blocks + 4) + 1):
                for words in range(1, 22):
                    plan = forecast(blocks, rows, 1, min(1326, 64 * words), 1)
                    self.assertEqual(plan['metadata_words'] - 1024 - 320, feasible_peak(blocks, rows, words))

    def test_two_observation_and_hundred_world_catalog_only_comparisons(self):
        eager = forecast(868, 868, 434, 1326, 4774, False)
        lazy = forecast(868, 868, 434, 1326, 4774)
        self.assertEqual((eager['metadata_words'], lazy['metadata_words']), (185908, 167680))
        self.assertEqual(lazy['work'] - eager['work'], 256 + 32 * 4774)
        # Deterministic upper encounter geometry:6 preflop public paths share
        # their public block; all later prefixes may be distinct each world.
        old = forecast(6 + 428 * 100, 434 * 100, 434, 1326, 1, False)
        new = forecast(6 + 428 * 100, 434 * 100, 434, 1326, 1)
        self.assertEqual((old['metadata_words'], new['metadata_words']), (2408622, 1522170))
        self.assertFalse(old['passes_component_caps']); self.assertTrue(new['passes_component_caps'])
        # One lookup is deliberate: this comparison tests metadata, not the
        # real lifetime lookup/work bill, native epochs or learning admission.

    def test_invalid_geometry_rejects_before_arithmetic(self):
        for args in ((2, 1, 1, 1326, 4), (0, 1, 1, 1, 1), (1, 1, 1, 1327, 1), (True, 2, 1, 1, 1)):
            with self.assertRaises(ValueError):
                forecast(*args)


if __name__ == '__main__':
    unittest.main()
