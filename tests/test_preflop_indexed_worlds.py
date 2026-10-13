from itertools import permutations
import unittest
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from scripts.preflop_validation import compare_result, physical_worlds, replay_policy


class ScalarBlockerIndex:
    """Test-only reference using disjoint sets, never production bitsets."""
    def __init__(self, selected):
        self.selected = selected

    def valid_count(self, private_cards):
        blocked = set(private_cards)
        return sum(blocked.isdisjoint(flop + (turn, river))
                   for flop, turn, river in self.selected)

    def iter_valid_indices(self, private_cards):
        blocked = set(private_cards)
        for index, (flop, turn, river) in enumerate(self.selected):
            if blocked.isdisjoint(flop + (turn, river)):
                yield index


class PreflopIndexedWorldTests(unittest.TestCase):
    def test_weighted_blocker_worlds_match_scalar_reference_exactly(self):
        sb, bb = "AsAd:1,AhAc:0.25", "KsKd:1,KcKh:0.5"
        runouts = ("2c3c4d7h8h", "Kc2d3h7s8c", "Ac2d3h7s8c", "2c3c4d8h7h")
        actual = solver._enumerate_physical_worlds(sb, bb, runouts, 10)
        with patch.object(solver, "RunoutBlockerIndex", ScalarBlockerIndex):
            expected = solver._enumerate_physical_worlds(sb, bb, runouts, 10)
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual[1]), len(physical_worlds(sb, bb, runouts)))
        self.assertAlmostEqual(sum(row[2] for row in actual[1]), 1, delta=1e-12)

    def test_complete_fixed_flop_worlds_and_pair_probabilities_are_unchanged(self):
        flop = ("2c", "3c", "4d")
        deck = [card for card in solver.DECK if card not in flop]
        runouts = tuple(flop + future for future in permutations(deck, 2))
        actual = solver._enumerate_physical_worlds("AsAd,QsQd", "KsKd,JhJc", runouts, 10)
        with patch.object(solver, "RunoutBlockerIndex", ScalarBlockerIndex):
            expected = solver._enumerate_physical_worlds("AsAd,QsQd", "KsKd,JhJc", runouts, 10)
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual[1]), 7920)
        self.assertEqual(actual[2], 4)
        self.assertEqual(actual[5], 4 * 2352)
        self.assertTrue(all(abs(row["probability"] - .25) < 1e-12 for row in actual[3]))

    def test_game_policies_and_independent_replay_are_unchanged(self):
        sb, bb = "AsAd:1,AhAc:0.25", "KsKd:1,KcKh:0.5"
        kwargs = {"config": {"starting_stack": [4, 3], "max_raises": 0},
                  "runouts": ("2c3c4d7h8h", "Kc2d3h7s8c", "Ac2d3h7s8c")}
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                options = dict(iterations=10, algorithm=algorithm, traversal="public-batched",
                               diagnostics="public-batched", resource_model="public-vector",
                               averaging_delay=5 if algorithm == "cfrplus" else 0)
                actual = solver.solve_preflop(sb, bb, **kwargs, **options)
                with patch.object(solver, "RunoutBlockerIndex", ScalarBlockerIndex):
                    expected = solver.solve_preflop(sb, bb, **kwargs, **options)
                self.assertEqual(actual, expected)
                compare_result(actual, replay_policy(actual, sb, bb, **kwargs))

    def test_preflight_and_world_rejections_keep_pair_guard_order(self):
        runouts = ("2c3c4d7h8h", "2c3c4d8h7h")
        for preflight_cap, world_cap, message in ((1, 1, "pair/runout"),
                                                  (2, 1, "world iterations"),
                                                  (3, 1000, "pair/runout")):
            for index_class in (solver.RunoutBlockerIndex, ScalarBlockerIndex):
                with self.subTest(preflight_cap=preflight_cap, index=index_class.__name__):
                    with patch.object(solver, "_MAX_PAIR_RUNOUT_PREFLIGHT_CHECKS", preflight_cap):
                        with patch.object(solver, "_MAX_WORLD_ITERATIONS", world_cap):
                            with patch.object(solver, "RunoutBlockerIndex", index_class):
                                with patch.object(solver, "rank_hand") as rank:
                                    with self.assertRaisesRegex(ValueError, message):
                                        solver._enumerate_physical_worlds(
                                            "AsAd,QsQd", "KsKd", runouts, 10)
                                    rank.assert_not_called()

    def test_wholly_blocked_request_still_rejects_before_ranking(self):
        with patch.object(solver, "rank_hand") as rank:
            with self.assertRaisesRegex(ValueError, "no compatible physical deals"):
                solver._enumerate_physical_worlds("AsAd", "KsKd", ("As2c3d4h5s",), 10)
            rank.assert_not_called()


if __name__ == "__main__":
    unittest.main()
