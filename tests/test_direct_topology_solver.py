"""Full four-street direct-DAG integration against literal and physical replay."""
from contextlib import ExitStack
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pokerlab.selected_operator_solver import census_four_street_operator, solve_four_street_operator
from scripts.preflop_validation import replay_policy, compare_result
from scripts.four_street_certificate_v3 import evaluate_exact
from tests.test_selected_operator_solver import CASE, request


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (
    "pokerlab.preflop_solver._merge_preflop_tree",
    "pokerlab.preflop_solver._clone_template",
    "pokerlab.preflop_solver._all_nodes",
    "pokerlab.preflop_solver._positive_pot_training_view",
    "pokerlab.postflop_solver._build_public_tree",
    "pokerlab.river_tree._build_tree",
    "pokerlab.shared_public_topology.compile_shared_public_topology",
)


class DirectTopologySolverTests(unittest.TestCase):
    def check_case(self, case):
        req = request(case)
        literal = solve_four_street_operator(req, strategy_storage="packed", rank_cache_boards=64)
        with ExitStack() as stack:
            for name in FORBIDDEN:
                stack.enter_context(patch(name, side_effect=AssertionError(name)))
            direct = solve_four_street_operator(
                req, strategy_storage="packed", rank_cache_boards=64, public_topology="direct")
        for field in ("strategy", "worlds", "public_states", "decisions", "info_sets",
                      "private_pair_probabilities", "value_sb", "value_bb", "sb_best_response_value",
                      "bb_best_response_value", "nash_conv", "public_batched_training_pot_anchor"):
            self.assertEqual(direct[field], literal[field], field)
        receipt = direct["operator_census"]["direct_public_topology"]
        self.assertEqual(receipt["materialized_postflop_nodes"], 0)
        self.assertEqual(receipt["compiler_snapshots"], 0)
        self.assertEqual(receipt["expanded_logical_visits"], literal["public_states"])
        self.assertEqual(direct["public_batched_training_view_states"], 0)
        self.assertEqual(direct["operator_census"]["temporary_template_peak_states"], 0)
        numeric = replay_policy(direct, req.sb_range, req.bb_range, config=case["config"],
                                runouts=case["runouts"], flop_config=case["flop_config"],
                                turn_config=case.get("turn_config"), river_config=case.get("river_config"))
        compare_result(direct, numeric)
        return direct, literal

    def test_original_four_street_game(self):
        case = json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text())["case"]
        actual, _literal = self.check_case(case)
        self.assertEqual(actual["worlds"], 22)
        self.assertEqual(actual["operator_census"]["shared_public_topology"]["unique_vertices"], 99)

    def test_weighted_shared_futures_and_blocked_private_holes(self):
        self.check_case(dict(CASE, sb_range="AsAd:1,AhAc:0.25,2c3c:0.5"))

    def test_fractional_local_rounding_short_stack_and_tie(self):
        self.check_case(dict(CASE, config={"small_blind": .123456789, "big_blind": .345678901,
                        "starting_stack": [2.5, 2], "raise_sizes": [.5],
                        "max_raises": 1, "include_all_in": True},
                        runouts=["TcJcQcKcAc", "2c3c4d7h8h"]))

    def test_no_information_and_exact_early_all_in(self):
        actual, _ = self.check_case(dict(CASE, config={"starting_stack": [.5, 1]}))
        self.assertEqual(actual["info_sets"], 0)
        case = dict(CASE, id="direct-shared-exact-control", config={"starting_stack": [1, 2]},
                    turn_config=CASE["flop_config"], river_config=CASE["flop_config"])
        actual, literal = self.check_case(case)
        self.assertEqual(evaluate_exact(case, actual)["metrics"], evaluate_exact(case, literal)["metrics"])

    def test_later_street_raise_reopening(self):
        self.check_case(dict(CASE, sb_range="AsAd", bb_range="KsKd", runouts=["2c3c4d7h8h"],
                            config={"starting_stack": [4.5, 4], "raise_sizes": [.5],
                                    "max_raises": 1, "include_all_in": True},
                            flop_config={"bet_sizes": [.25, .5], "raise_sizes": [.5],
                                         "max_raises": 1, "include_all_in": True}))

    def test_rank_free_direct_census_and_early_selector_rejection(self):
        with patch("pokerlab.selected_runout_operator.rank_hand", side_effect=AssertionError("ranking")):
            counts = census_four_street_operator(request(CASE), strategy_storage="packed", public_topology="direct")
        self.assertEqual(counts["direct_public_topology"]["materialized_postflop_nodes"], 0)
        with patch("pokerlab.selected_operator_solver.SelectedRunoutOperator", side_effect=AssertionError("setup")):
            for kwargs in ({},):
                with self.assertRaisesRegex(ValueError, "packed CFR"):
                    solve_four_street_operator(request(CASE), public_topology="direct", **kwargs)

    def test_original_mass_and_scan_guards_remain(self):
        tiny = dict(CASE, sb_range="AsAd:1e-160", bb_range="KsKd:1e-160")
        with self.assertRaises(ValueError):
            solve_four_street_operator(request(tiny), strategy_storage="packed", public_topology="direct")
        with patch("pokerlab.selected_operator_solver.MAX_OPERATOR_SCAN_ENTRIES", 1):
            with self.assertRaisesRegex(ValueError, "scan envelope"):
                solve_four_street_operator(request(CASE), strategy_storage="packed", public_topology="direct")


if __name__ == "__main__":
    unittest.main()
