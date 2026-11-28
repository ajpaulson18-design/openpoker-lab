"""Focused checks for the independent complete-request forecast."""
import unittest

from tests.virtual_frozen_grid_preflight_reference import boards, census, geometry
from tests.virtual_sparse_two_epoch_forecast_reference import (
    BOARD_COUNT, PAIR_COUNT, check_caps, forecast, output_upper_bytes,
    pair_forecast,
)


class SparseTwoEpochForecastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = forecast()
        cls.board_list = tuple(boards())

    def test_fixed_geometry_and_all_selector_count(self):
        g = geometry()
        self.assertEqual(g["literal_occurrences"], 1105)
        self.assertEqual(g["max_actor_decisions"], (6, 7))
        self.assertEqual(g["max_total_decisions"], 12)
        self.assertEqual(g["max_opponent_past_plus_all_future_decisions_excluding_current"], 11)
        self.assertEqual(len(self.board_list), BOARD_COUNT)
        self.assertEqual(PAIR_COUNT, 6_350_400)
        self.assertEqual((self.result["geometry"]["max_rows_per_board"],
                          self.result["geometry"]["max_slots_per_board"]), (530, 1282))

    def test_positive_same_board_and_zero_target_pair_terms(self):
        positive = next(board for board in self.board_list if census(board)["full_target_positive"])
        zero = next(board for board in self.board_list if not census(board)["full_target_positive"])
        same = pair_forecast(positive, positive)
        mixed = pair_forecast(positive, zero)
        zeroes = pair_forecast(zero, zero)
        self.assertGreater(same["supported_rows"], 0)
        self.assertEqual(mixed["chance_work"],
                         pair_forecast(zero, positive)["chance_work"])
        self.assertGreater(mixed["supported_rows"], zeroes["supported_rows"])
        self.assertGreater(mixed["raw_family_work"], zeroes["raw_family_work"])
        self.assertGreater(self.result["maxima"]["full_target_zero"], 0)

    def test_every_axis_uses_additive_pair_maxima(self):
        maxima = self.result["maxima"]
        self.assertEqual(maxima["rows"], max(census(board)["supported_rows"] for board in self.board_list))
        self.assertEqual(maxima["slots"], max(census(board)["supported_action_slots"] for board in self.board_list))
        # For independent legal selectors with replacement, max(x(B1)+x(B2))=2*max(x(B)).
        self.assertEqual(self.result["components"]["chance_work"],
                         65_536 + 2 * maxima["chance_delta"])
        self.assertEqual(self.result["components"]["parent_numeric_work"],
                         1_040_000 + 4096 + 512 * 1060 +
                         2 * maxima["raw_family_sum_from_axis_maxima"])
        self.assertEqual(maxima["raw_family_sum_from_axis_maxima"], sum(maxima["raw_families"]))

    def test_output_and_component_ledgers_stay_within_ceilings(self):
        self.assertEqual(output_upper_bytes(), 619_152)
        self.assertTrue(check_caps(self.result))
        self.assertTrue(all(self.result["caps_pass"].values()))
        components = self.result["components"]
        self.assertEqual(components["total_work"], sum((
            components["template_work"], components["catalog_work"], components["history_work"],
            components["chance_work"], components["store_component_work"],
            components["parent_numeric_work"], components["output_serialization_work"])))
        self.assertLessEqual(components["total_entries"], 2_000_000)
        self.assertLessEqual(components["total_payload_bits"], 1 << 30)
        self.assertEqual(components["source_integer_scratch_bits"], 32 * 181)
        self.assertEqual(components["total_payload_bits"], 55_627_714)
        self.assertLessEqual(components["output_bytes"], 2_100_000)

    def test_one_less_global_work_unit_rejects(self):
        total = self.result["components"]["total_work"]
        self.assertFalse(check_caps(self.result, {"total_work": total - 1}))

    def test_scope_and_template_payload_guard_are_explicit(self):
        self.assertIn("no producer/admission/training claim", self.result["scope"])
        self.assertIn("does not prove", self.result["assumptions"]["template_entry_guard"])
        self.assertIn("not RSS", self.result["assumptions"]["payload"])
        self.assertEqual(self.result["proposal_law"], "uniform public board only")


if __name__ == "__main__":
    unittest.main()
