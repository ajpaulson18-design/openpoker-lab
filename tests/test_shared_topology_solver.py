"""Same-game shared-topology training, replay, lifetime and admission controls."""
import json
from pathlib import Path
import unittest
import weakref
from unittest.mock import patch

from pokerlab import packed_operator_cfr, selected_operator_solver
from pokerlab.selected_operator_solver import census_four_street_operator, solve_four_street_operator
from scripts.preflop_validation import replay_policy, compare_result
from scripts.four_street_certificate_v3 import evaluate_exact
from tests.test_selected_operator_solver import CASE, request


ROOT = Path(__file__).resolve().parents[1]


class SharedTopologySolverTests(unittest.TestCase):
    def check_case(self, case, iterations=10):
        req = request(case, iterations=iterations)
        expected = solve_four_street_operator(req, strategy_storage="packed", rank_cache_boards=64)
        with patch("pokerlab.preflop_solver._positive_pot_training_view",
                   side_effect=AssertionError("expanded training clone")), \
             patch("pokerlab.preflop_solver._enumerate_physical_worlds",
                   side_effect=AssertionError("world table")):
            actual = solve_four_street_operator(
                req, strategy_storage="packed", rank_cache_boards=64, public_topology="shared")
        for field in ("strategy", "private_pair_probabilities", "worlds", "public_states",
                      "decisions", "info_sets", "value_sb", "value_bb", "sb_best_response_value",
                      "bb_best_response_value", "nash_conv", "public_batched_training_pot_anchor"):
            self.assertEqual(actual[field], expected[field], field)
        self.assertEqual(actual["public_batched_training_view_states"], 0)
        self.assertLessEqual(actual["operator_census"]["shared_public_topology"]["unique_vertices"],
                             actual["public_states"])
        oracle = replay_policy(actual, req.sb_range, req.bb_range, config=case["config"],
                               runouts=case["runouts"], flop_config=case["flop_config"],
                               turn_config=case.get("turn_config"), river_config=case.get("river_config"))
        compare_result(actual, oracle)
        return actual, expected

    def test_original_twenty_two_world_complete_game(self):
        case = json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text())["case"]
        actual, _expected = self.check_case(case)
        self.assertEqual(actual["operator_census"]["shared_public_topology"]["unique_vertices"], 99)

    def test_weighted_shared_futures_and_inactive_private_indices(self):
        self.check_case(dict(CASE, sb_range="AsAd:1,AhAc:0.25,2c3c:0.5"))

    def test_fractional_blinds_refunds_and_tie(self):
        self.check_case(dict(CASE, config={"small_blind": .123456789, "big_blind": .345678901,
                        "starting_stack": [2.5, 2], "raise_sizes": [.5],
                        "max_raises": 1, "include_all_in": True},
                        runouts=["TcJcQcKcAc", "2c3c4d7h8h"]))

    def test_zero_information_sets_and_exact_short_all_in(self):
        case = dict(CASE, config={"starting_stack": [.5, 1]})
        actual, expected = self.check_case(case)
        self.assertEqual(actual["info_sets"], 0)
        case = dict(CASE, id="shared-topology-exact-control", config={"starting_stack": [1, 2]},
                    turn_config=CASE["flop_config"], river_config=CASE["flop_config"])
        actual, expected = self.check_case(case)
        self.assertEqual(evaluate_exact(case, actual)["metrics"], evaluate_exact(case, expected)["metrics"])

    def test_source_tree_is_released_before_training_and_on_training_error(self):
        original_prepare = selected_operator_solver._prepare
        original_train = packed_operator_cfr.train_packed
        roots = []

        def prepare(*args, **kwargs):
            result = original_prepare(*args, **kwargs)
            roots.append(weakref.ref(result[1]))
            return result

        def train(*args, **kwargs):
            self.assertIsNone(roots[-1](), "expanded source tree survived into training")
            return original_train(*args, **kwargs)

        with patch.object(selected_operator_solver, "_prepare", side_effect=prepare), \
             patch.object(packed_operator_cfr, "train_packed", side_effect=train):
            solve_four_street_operator(request(CASE), strategy_storage="packed", public_topology="shared")
        self.assertIsNone(roots[-1]())
        with patch.object(selected_operator_solver, "_prepare", side_effect=prepare), \
             patch.object(packed_operator_cfr, "train_packed", side_effect=RuntimeError("injected training failure")):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                solve_four_street_operator(request(CASE), strategy_storage="packed", public_topology="shared")
        self.assertIsNone(roots[-1]())

    def test_rank_free_shared_admission_and_unsupported_selection(self):
        with patch("pokerlab.selected_runout_operator.rank_hand", side_effect=AssertionError("ranking")):
            counts = census_four_street_operator(request(CASE), strategy_storage="packed", public_topology="shared")
        self.assertEqual(counts["shared_strategy_storage"]["retained_dense_lookup_slots"], 0)
        self.assertEqual(counts["shared_strategy_storage"]["semantic_row_lookup_entries"], counts["information_sets"])
        with patch.object(selected_operator_solver, "SelectedRunoutOperator", side_effect=AssertionError("preparation")):
            for kwargs in ({}, {"strategy_storage": "packed", "native_executable": "never-read"}):
                with self.assertRaisesRegex(ValueError, "Python packed"):
                    solve_four_street_operator(request(CASE), public_topology="shared", **kwargs)

    def test_history_work_rejects_before_training(self):
        with patch("pokerlab.shared_topology_view.MAX_HISTORY_LOOKUP_ENTRIES", 1), \
             patch.object(packed_operator_cfr, "train_packed", side_effect=AssertionError("training")):
            with self.assertRaisesRegex(ValueError, "history"):
                solve_four_street_operator(request(CASE), strategy_storage="packed", public_topology="shared")


if __name__ == "__main__":
    unittest.main()
