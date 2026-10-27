import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pokerlab.selected_operator_solver import solve_four_street_operator, census_four_street_operator
from pokerlab.packed_operator_cfr import layout_census
from pokerlab.river_tree import _Node, _Terminal, _Action
from scripts.preflop_validation import replay_policy, compare_result
from scripts.four_street_certificate_v3 import evaluate_exact
from tests.test_selected_operator_solver import CASE, request


class PackedOperatorTests(unittest.TestCase):
    def compare_game(self, case, cache=1):
        req = request(case)
        expected = solve_four_street_operator(req, rank_cache_boards=cache)
        with patch("pokerlab.selected_operator_solver._train_prepared", side_effect=AssertionError("row training")):
            actual = solve_four_street_operator(req, rank_cache_boards=cache, strategy_storage="packed")
        self.assertEqual(actual["strategy"], expected["strategy"])
        for field in ("value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value", "nash_conv",
                      "worlds", "decisions", "public_states", "info_sets", "private_pair_probabilities"):
            self.assertEqual(actual[field], expected[field], field)
        self.assertEqual(actual["operator_statistics"], expected["operator_statistics"])
        oracle = replay_policy(actual, req.sb_range, req.bb_range, config=case["config"], runouts=case["runouts"],
                               flop_config=case["flop_config"], turn_config=case.get("turn_config"),
                               river_config=case.get("river_config"))
        compare_result(actual, oracle)
        return actual

    def test_weighted_blocker_shared_futures_both_cache_modes(self):
        for cache in (1, 64):
            with self.subTest(cache=cache):
                self.compare_game(CASE, cache)

    def test_reference_twenty_two_world_game(self):
        case = json.loads((Path(__file__).resolve().parents[1] / "benchmarks/four-street-integration-v1.json").read_text())["case"]
        result = self.compare_game(case, 64)
        self.assertEqual(result["operator_census"]["strategy_storage"]["numeric_buffer_bytes"], 2402 * 32)
        self.assertEqual({row["street"] for row in result["strategy"]}, {"preflop", "flop", "turn", "river"})

    def test_short_all_in_ties_and_refunds(self):
        self.compare_game(dict(CASE, config={"starting_stack": [0.5, 1]}), 64)
        self.compare_game(dict(CASE, config={"starting_stack": [2.5, 2], "raise_sizes": [0.5],
                                           "max_raises": 1, "include_all_in": True},
                               runouts=["TcJcQcKcAc", "2c3c4d7h8h"]), 64)

    def test_asymmetric_ranges_and_inactive_private_index_holes(self):
        self.compare_game(dict(CASE, sb_range="AsAd:1,AhAc:0.25,2c3c:0.5"), 64)

    def test_unsupported_algorithms_reject_before_operator(self):
        with patch("pokerlab.selected_operator_solver.SelectedRunoutOperator", side_effect=AssertionError("operator")):
            for algorithm in ("vanilla", "dcfr"):
                with self.assertRaisesRegex(ValueError, "requires CFR"):
                    solve_four_street_operator(request(CASE, algorithm), strategy_storage="packed")

    def test_rank_free_admission_and_dense_slot_cap(self):
        with patch("pokerlab.selected_runout_operator.rank_hand", side_effect=AssertionError("ranking")):
            census = census_four_street_operator(request(CASE), rank_cache_boards=64, strategy_storage="packed")
            self.assertGreater(census["strategy_storage"]["dense_decision_hand_slots"], 0)
            with patch("pokerlab.packed_operator_cfr.MAX_DENSE_DECISION_HAND_SLOTS", 1):
                with self.assertRaisesRegex(ValueError, "decision/hand"):
                    solve_four_street_operator(request(CASE), strategy_storage="packed")
            with patch("pokerlab.packed_operator_cfr.MAX_LAYOUT_LOOP_ENTRIES", 1):
                with self.assertRaisesRegex(ValueError, "layout loop"):
                    solve_four_street_operator(request(CASE), strategy_storage="packed")

    def test_terminal_failure_releases_training_buffers_and_rank_cache(self):
        from pokerlab.selected_runout_operator import SelectedRunoutOperator
        captured = []
        original = SelectedRunoutOperator.__init__
        def initialize(operator, *args, **kwargs):
            original(operator, *args, **kwargs)
            captured.append(operator)
        with patch.object(SelectedRunoutOperator, "__init__", initialize), \
             patch.object(SelectedRunoutOperator, "values", side_effect=RuntimeError("terminal failure")):
            try:
                solve_four_street_operator(request(CASE), rank_cache_boards=64, strategy_storage="packed")
            except RuntimeError as error:
                self.assertEqual(str(error), "terminal failure")
                trace = error.__traceback__
                frames = []
                while trace:
                    frames.append(trace.tb_frame)
                    trace = trace.tb_next
                frame = next(f for f in frames if f.f_code.co_name == "train_packed")
                self.assertIsNone(frame.f_locals["regrets"])
                self.assertIsNone(frame.f_locals["sums"])
                self.assertEqual(frame.f_locals["rows"], {})
            else:
                self.fail("Injected terminal failure did not propagate")
        self.assertEqual(len(captured[0]._board_rank_lru), 0)

    def test_exact_rational_small_game(self):
        case = dict(CASE, id="packed-exact-control", config={"starting_stack": [1, 2]},
                    turn_config=CASE["flop_config"], river_config=CASE["flop_config"])
        baseline = solve_four_street_operator(request(case), rank_cache_boards=64)
        candidate = solve_four_street_operator(request(case), rank_cache_boards=64, strategy_storage="packed")
        self.assertEqual(evaluate_exact(case, baseline)["metrics"], evaluate_exact(case, candidate)["metrics"])

    def test_cyclic_or_uncovered_identity_rejects(self):
        root = _Node((), 0, (_Action("check"),), (_Terminal("showdown", (1, 1)),))
        with self.assertRaisesRegex(ValueError, "complete public tree"):
            layout_census(root, {(0, 0, ("unknown",)): 1}, (1, 1), 10)
        root.children = (root,)
        with self.assertRaisesRegex(ValueError, "acyclic"):
            layout_census(root, {(0, 0, ()): 1}, (1, 1), 10)


if __name__ == "__main__":
    unittest.main()
