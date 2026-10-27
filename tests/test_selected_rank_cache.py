import unittest
from unittest.mock import patch

from pokerlab.cards import rank_hand
from pokerlab.selected_runout_operator import SelectedRunoutOperator
from pokerlab.selected_operator_solver import solve_four_street_operator, census_four_street_operator
from tests.test_selected_operator_solver import CASE, request


class BoardRankCacheTests(unittest.TestCase):
    def make(self, capacity):
        return SelectedRunoutOperator("AsAd", "KsKd", ("2c3c4d7h8h", "2c3c4d7s8h", "2c3c4d7s8c"),
                                     rank_cache_boards=capacity)

    def test_lru_eviction_and_immutable_vectors(self):
        op = self.make(2)
        for board in (0, 1, 0, 2):
            op._world_sign(0, 0, board)
        self.assertEqual(list(op._board_rank_lru), [0, 2])
        self.assertEqual((op.rank_cache_hits, op.rank_cache_misses, op.rank_cache_evictions), (1, 3, 1))
        self.assertTrue(all(isinstance(side, tuple) for vectors in op._board_rank_lru.values() for side in vectors))
        self.assertLessEqual(op.rank_scratch_peak, op.rank_cache_requested_entries)
        self.assertEqual(op.rank_cache_retained_peak_entries, 4)
        op.clear_rank_cache()
        self.assertEqual(len(op._board_rank_lru), 0)

    def test_failed_build_is_never_cached_and_fresh_solve_is_empty(self):
        op = self.make(2)
        op._world_sign(0, 0, 0)
        with patch("pokerlab.selected_runout_operator.rank_hand", side_effect=[rank_hand(op.hands[0][0] + op.selected[1][0] + op.selected[1][1:]), RuntimeError("rank failure")]):
            with self.assertRaisesRegex(RuntimeError, "rank failure"):
                op._world_sign(0, 0, 1)
        self.assertNotIn(1, op._board_rank_lru)
        self.assertEqual(list(op._board_rank_lru), [0])
        self.assertEqual(len(self.make(2)._board_rank_lru), 0)
        op._world_sign(0, 0, 1)
        self.assertIn(1, op._board_rank_lru)

    def test_rejects_before_rank_work(self):
        with patch("pokerlab.selected_runout_operator.rank_hand", side_effect=AssertionError("ranking")):
            for bad in (True, 0, -1, 65, 2.5, "2"):
                with self.assertRaises(ValueError):
                    self.make(bad)
            with patch("pokerlab.selected_runout_operator.MAX_RANK_CACHE_ENTRIES", 3):
                with self.assertRaisesRegex(ValueError, "8,192"):
                    self.make(2)

    def test_default_payload_and_rank_free_census(self):
        default = solve_four_street_operator(request(CASE))
        explicit = solve_four_street_operator(request(CASE), rank_cache_boards=1)
        self.assertEqual(default, explicit)
        self.assertNotIn("rank_cache", default)
        with patch("pokerlab.selected_runout_operator.rank_hand", side_effect=AssertionError("ranking")):
            census = census_four_street_operator(request(CASE), rank_cache_boards=64)
        self.assertLessEqual(census["rank_cache_admission"]["retained_plus_construction_reference_slots"], 8192)
        self.assertEqual(census["pair_runout_scan_upper_bound"], default["operator_census"]["pair_runout_scan_upper_bound"])

    def test_clears_after_diagnostic_failure(self):
        captured = []
        original = SelectedRunoutOperator.__init__
        def initialize(operator, *args, **kwargs):
            original(operator, *args, **kwargs)
            captured.append(operator)
        with patch.object(SelectedRunoutOperator, "__init__", initialize), \
             patch("pokerlab.selected_operator_solver._evaluate_prepared", side_effect=RuntimeError("diagnostic failure")):
            with self.assertRaisesRegex(RuntimeError, "diagnostic failure"):
                solve_four_street_operator(request(CASE), rank_cache_boards=64)
        self.assertGreater(captured[0].rank_cache_misses, 0)
        self.assertEqual(len(captured[0]._board_rank_lru), 0)

    def test_extra_work_rejection_precedes_ranking_and_training(self):
        with patch("pokerlab.selected_operator_solver.MAX_RANK_CACHE_BOOKKEEPING_ENTRIES", 1), \
             patch("pokerlab.selected_runout_operator.rank_hand", side_effect=AssertionError("ranking")):
            with self.assertRaisesRegex(ValueError, "bookkeeping"):
                solve_four_street_operator(request(CASE), rank_cache_boards=2)

    def test_cache_reduces_ranking_without_reducing_physical_scan_charge(self):
        baseline = solve_four_street_operator(request(CASE), rank_cache_boards=1)
        candidate = solve_four_street_operator(request(CASE), rank_cache_boards=64)
        self.assertEqual(baseline["strategy"], candidate["strategy"])
        self.assertLess(candidate["operator_statistics"]["rank_calls"], baseline["operator_statistics"]["rank_calls"])
        self.assertEqual(candidate["operator_statistics"]["post_constructor_pair_board_checks"],
                         baseline["operator_statistics"]["post_constructor_pair_board_checks"])
        self.assertLessEqual(candidate["rank_cache"]["retained_peak_rank_slots"],
                             candidate["operator_census"]["rank_cache_admission"]["retained_rank_slots"])
