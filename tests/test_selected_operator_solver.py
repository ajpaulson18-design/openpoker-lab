import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pokerlab.four_street_solver import solve_four_street
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.selected_operator_solver import census_four_street_operator, solve_four_street_operator
from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions
from scripts.preflop_validation import replay_policy, compare_result


def request(case, algorithm="cfrplus", iterations=10):
    return FourStreetSolveRequest(
        case["sb_range"], case["bb_range"], tuple(case["runouts"]),
        preflop_config=PreflopConfig.from_dict(case["config"]),
        flop_actions=PostflopActions(**case["flop_config"]),
        turn_actions=None if case.get("turn_config") is None else PostflopActions(**case["turn_config"]),
        river_actions=None if case.get("river_config") is None else PostflopActions(**case["river_config"]),
        iterations=iterations, algorithm=algorithm, traversal="public-batched",
        diagnostics="public-batched", resource_model="public-vector")


CASE = {
    "sb_range": "AsAd:1,AhAc:0.25", "bb_range": "KsKd:1,KcKh:0.5",
    "config": {"starting_stack": [4, 3], "raise_sizes": [0.5], "max_raises": 1,
               "include_all_in": False},
    "runouts": ["2c3c4d7h8h", "2c3c4d7hKc", "Ac2d3h7s8c"],
    "flop_config": {"bet_sizes": [0.5], "raise_sizes": [], "max_raises": 0,
                    "include_all_in": False},
}


class OperatorSolverTests(unittest.TestCase):
    def check_game(self, case, algorithm="cfrplus"):
        req = request(case, algorithm)
        expected = solve_four_street(req).to_dict()["payload"]
        with patch("pokerlab.preflop_solver._enumerate_physical_worlds", side_effect=AssertionError("materialized worlds")), \
             patch("pokerlab.public_cfr._aggregate_prefixes", side_effect=AssertionError("stored prefix edges")):
            actual = solve_four_street_operator(req)
        for field in ("worlds", "public_states", "decisions", "info_sets"):
            self.assertEqual(expected[field], actual[field], field)
        self.assertEqual(len(expected["strategy"]), len(actual["strategy"]))
        for left, right in zip(expected["strategy"], actual["strategy"]):
            self.assertEqual({k: v for k, v in left.items() if k != "actions"},
                             {k: v for k, v in right.items() if k != "actions"})
            for a, b in zip(left["actions"], right["actions"]):
                self.assertEqual({k: v for k, v in a.items() if k != "probability"},
                                 {k: v for k, v in b.items() if k != "probability"})
                self.assertAlmostEqual(a["probability"], b["probability"], delta=1e-10)
        oracle = replay_policy(actual, req.sb_range, req.bb_range,
                               config=case["config"], runouts=case["runouts"],
                               flop_config=case["flop_config"],
                               turn_config=case.get("turn_config"), river_config=case.get("river_config"))
        compare_result(actual, oracle)
        compare_result(actual, expected)
        self.assertEqual(actual["operator_census"]["stored_complete_worlds"], 0)
        self.assertEqual(actual["operator_census"]["stored_prefix_pair_edges"], 0)
        return actual

    def test_weighted_shared_prefix_all_algorithms(self):
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                self.check_game(CASE, algorithm)

    def test_existing_twenty_two_world_fixture(self):
        case = json.loads((Path(__file__).resolve().parents[1] / "benchmarks/four-street-integration-v1.json").read_text())["case"]
        result = self.check_game(case)
        self.assertEqual(result["worlds"], 22)
        self.assertEqual({row["street"] for row in result["strategy"]}, {"preflop", "flop", "turn", "river"})

    def test_blind_all_in_integrates_hidden_boards_without_information_sets(self):
        case = dict(CASE, config={"starting_stack": [0.5, 1]})
        result = self.check_game(case)
        self.assertEqual(result["info_sets"], 0)

    def test_tie_and_short_stack_raised_game(self):
        case = dict(CASE, runouts=["TcJcQcKcAc", "2c3c4d7h8h"],
                    config={"starting_stack": [2.5, 2], "raise_sizes": [0.5],
                            "max_raises": 1, "include_all_in": True})
        self.check_game(case)

    def test_rank_free_census_and_pretraining_scan_rejection(self):
        with patch("pokerlab.selected_runout_operator.rank_hand", side_effect=AssertionError("ranking")):
            counts = census_four_street_operator(request(CASE))
        self.assertGreater(counts["action_slots"], 0)
        with patch("pokerlab.selected_operator_solver.MAX_OPERATOR_SCAN_ENTRIES", 1), \
             patch("pokerlab.selected_operator_solver._train_prepared", side_effect=AssertionError("training")):
            with self.assertRaisesRegex(ValueError, "scan envelope"):
                solve_four_street_operator(request(CASE))

    def test_incompatible_selectors_reject(self):
        bad = FourStreetSolveRequest("AsAd", "KsKd", ("2c3c4d7h8h",), iterations=10)
        with self.assertRaisesRegex(ValueError, "requires"):
            solve_four_street_operator(bad)


if __name__ == "__main__":
    unittest.main()
