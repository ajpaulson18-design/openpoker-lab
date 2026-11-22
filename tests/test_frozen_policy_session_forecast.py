"""Focused controls for the independent paired-session resource equation."""
import unittest

from tests.virtual_frozen_grid_preflight_reference import boards, census, geometry
from tests.virtual_frozen_policy_session_reference import (
    CAPS, ENTRIES_CAP, HISTORY_CAP, OUTPUT_CAP, PARENT_CAP, STATE_CAP,
    WORK_CAP, fits_caps, pairwise_maxima, session_forecast,
)


class FrozenPolicySessionForecastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.boards = tuple(boards())
        cls.geometry = geometry()

    def test_order_commutes_and_duplicate_selector_is_charged_twice(self):
        board = self.boards[0]
        first = session_forecast(board, "uniform", board, "uniform")
        swapped = session_forecast(board, "uniform", board, "uniform")
        self.assertEqual(first, swapped)
        r, s = first["boards"][0]["rows"], first["boards"][0]["slots"]
        self.assertEqual(first["reads"], 24_420 + 4*r)
        self.assertEqual(first["output"], 1_443_912 + 2*136*(r+s))

    def test_selector_order_is_commutative_across_laws_and_boards(self):
        board_a, board_b = self.boards[0], self.boards[-1]
        forward = session_forecast(board_a, "uniform", board_b, "river_weighted")
        reverse = session_forecast(board_b, "river_weighted", board_a, "uniform")
        keys = ("reads", "state", "history", "chance", "parent", "work",
                "entries", "payload", "output", "feasible")
        self.assertEqual({key:forward[key] for key in keys},
                         {key:reverse[key] for key in keys})

    def test_positive_and_zero_full_target_boards_keep_prefix_rows(self):
        positive = next(board for board in self.boards if census(board)["full_target_positive"])
        zero = next(board for board in self.boards if not census(board)["full_target_positive"])
        result = session_forecast(positive, "uniform", zero, "river_weighted")
        self.assertGreater(result["boards"][0]["rows"], 0)
        self.assertGreater(result["boards"][1]["rows"], 0)
        self.assertGreater(result["boards"][1]["slots"], 0)
        self.assertEqual(result["reads"], 24_420 + 2*sum(x["rows"] for x in result["boards"]))

    def test_pairwise_axis_maxima_cover_ordered_pairs_with_replacement(self):
        proof = pairwise_maxima()
        self.assertEqual(proof["boards_examined"], 2520)
        self.assertEqual(proof["proposal_laws_per_board"], 2)
        self.assertEqual(proof["ordered_pairs_proven"], 25_401_600)
        self.assertTrue(proof["replacement_allowed"])
        maxima = proof["maximum"]
        self.assertGreater(maxima["work"], 0)
        self.assertGreater(maxima["output"], 0)
        self.assertEqual(maxima["output"], 1_443_912 + 2*136*max(
            census(board)["supported_rows"] + census(board)["supported_action_slots"]
            for board in self.boards))

    def test_all_pairwise_axis_maxima_fit_and_reduce_only_caps_reject(self):
        proof = pairwise_maxima()
        maxima = proof["maximum"]
        expected = {"work":316_294_067,"history":39_784_400,"state":55_075_516,
                    "chance":2_579_498,"parent":8_209_324,"entries":1_184_881,
                    "payload":263_169_724,"output":1_936_776,
                    "stage_payload":6_281_940}
        self.assertEqual(maxima, expected)
        for name, cap in CAPS.items():
            self.assertLessEqual(maxima[name], cap)
            self.assertFalse(fits_caps(maxima, {name:maxima[name]-1}))
        self.assertLessEqual(maxima["work"], WORK_CAP)
        self.assertLessEqual(maxima["history"], HISTORY_CAP)
        self.assertLessEqual(maxima["state"], STATE_CAP)
        self.assertLessEqual(maxima["parent"], PARENT_CAP)
        self.assertLessEqual(maxima["entries"], ENTRIES_CAP)
        self.assertLessEqual(maxima["output"], OUTPUT_CAP)
        worst = proof["maximizer_terms"]["parent"]
        board = next(board for board in self.boards
                     if census(board)["supported_rows"] == worst["rows"] and
                     census(board)["supported_action_slots"] == worst["slots"])
        rejected = session_forecast(board, "uniform", board, "uniform")
        self.assertEqual(rejected["parent"], maxima["parent"])
        self.assertTrue(rejected["feasible"])
        self.assertFalse(fits_caps(maxima, {"parent":maxima["parent"]-1}))


if __name__ == "__main__":
    unittest.main()
