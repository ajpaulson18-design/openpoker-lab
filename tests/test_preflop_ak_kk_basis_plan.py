from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts import preflop_ak_kk_basis_plan as planner


class AKKKBasisPlanTests(unittest.TestCase):
    def test_literal_schedule_and_blocker_orbits_without_numerical_work(self):
        with patch.object(planner.reference, "backend", side_effect=AssertionError("binary lookup")), \
                patch.object(planner.ordinary, "rank_hand", side_effect=AssertionError("ranking")), \
                patch.object(planner.reference.subprocess, "run", side_effect=AssertionError("subprocess")):
            result = planner.admit_plan()
        self.assertEqual(result["status"], "admitted-plan-only")
        self.assertEqual([len(row["ordered_pairs"]) for row in result["count_requests"]], [3, 1, 2])
        self.assertEqual([row["sb_range"] for row in result["count_requests"]],
                         ["AdAs", "AcKc", "AdKc"])
        self.assertTrue(all(pair[0] == row["sb_range"]
                            for row in result["count_requests"] for pair in row["ordered_pairs"]))
        self.assertEqual(result["aggregate"]["numerical_subprocesses"], 7)
        self.assertEqual(result["aggregate"]["reference_boards"], 10_273_824)
        self.assertEqual(result["aggregate"]["reference_seven_calls"], 20_547_648)
        self.assertEqual(result["aggregate"]["reference_five_calls"], 431_500_608)
        self.assertEqual(result["future_pool_forecast"]["type_pair_counts"],
                         {"AA": 36, "AKs": 12, "AKo": 36})
        self.assertEqual(result["future_pool_forecast"]["type_prior_masses"],
                         {"AA": "3/7", "AKs": "1/7", "AKo": "3/7"})
        self.assertFalse(result["counts_generated"])

    def test_whole_request_rejects_before_caps_or_pair_planning(self):
        for mutator in (lambda value: value.__setitem__("schema_version", True),
                        lambda value: value["count_requests"].pop(),
                        lambda value: value["count_requests"].reverse(),
                        lambda value: value["count_requests"][1].__setitem__("sb_range", "AK")):
            request = planner.expected_request()
            mutator(request)
            with patch.object(planner, "_caps", side_effect=AssertionError("caps accessed")), \
                    patch.object(planner.reference, "pair_admission", side_effect=AssertionError("planning")):
                with self.assertRaisesRegex(ValueError, "entire literal"):
                    planner.admit_plan(request)

    def test_returned_request_cannot_change_later_admission(self):
        original = deepcopy(planner.expected_request())
        changed = planner.expected_request()
        changed["count_requests"][0]["compatible_pairs"] = 999
        self.assertEqual(planner.expected_request(), original)
        with self.assertRaises(ValueError):
            planner.admit_plan(changed)

    def test_live_cap_drift_rejects_before_pair_planning(self):
        with patch.object(planner.covered, "MAX_PAIRS", 129), \
                patch.object(planner.reference, "pair_admission", side_effect=AssertionError("planning")):
            with self.assertRaisesRegex(ValueError, "caps changed"):
                planner.admit_plan()

    def test_each_new_query_covers_exactly_one_distinct_global_suit_orbit(self):
        result = planner.admit_plan()
        orbits = set()
        for row in result["count_requests"][1:]:
            for sb, bb in row["ordered_pairs"]:
                self.assertTrue({sb[:2], sb[2:]}.isdisjoint((bb[:2], bb[2:])))
                orbits.add(planner._orbit((sb[:2], sb[2:]), (bb[:2], bb[2:])))
        expected = {(row["sb_hand"], row["bb_hand"])
                    for row in result["future_pool_forecast"]["source_suit_orbits"]
                    if row["type"] in ("AKs", "AKo")}
        self.assertEqual(orbits, expected)
        self.assertEqual(len(orbits), 3)


if __name__ == "__main__":
    unittest.main()
