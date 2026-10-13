import itertools
import unittest

from scripts.preflop_validation import compare_result, replay_policy
from pokerlab.preflop_solver import solve_preflop


_RANKS = "23456789TJQKA"
_SUITS = "cdhs"
_FLOP = ("2c", "3c", "4d")
_SB_HAND = ("As", "Ad")
_BB_HAND = ("Ks", "Kd")


def _fixed_flop_runouts():
    """Spell the physical deck independently of the production card module."""
    unavailable = set(_FLOP + _SB_HAND + _BB_HAND)
    remaining = [rank + suit for rank in _RANKS for suit in _SUITS
                 if rank + suit not in unavailable]
    assert len(remaining) == 45
    return tuple(_FLOP + (turn, river)
                 for turn, river in itertools.permutations(remaining, 2))


class FullFixedFlopTests(unittest.TestCase):
    def test_all_ordered_turn_river_worlds_for_one_fixed_flop(self):
        runouts = _fixed_flop_runouts()
        self.assertEqual(len(runouts), 45 * 44)
        self.assertEqual(len(set(runouts)), 1980)
        self.assertIn(_FLOP + ("5c", "6c"), runouts)
        self.assertIn(_FLOP + ("6c", "5c"), runouts)

        duplicate_flop_permutation = ("3c2c4d5c6c", "2c3c4d5c6c")
        with self.assertRaisesRegex(ValueError, "Duplicate canonical"):
            solve_preflop("AsAd", "KsKd", {
                "starting_stack": 2, "max_raises": 0,
                "include_all_in": False,
            }, runouts=duplicate_flop_permutation, iterations=10,
               traversal="planned")

        result = solve_preflop(
            "AsAd", "KsKd",
            {"starting_stack": 2, "max_raises": 0,
             "include_all_in": False},
            runouts=runouts, iterations=10, traversal="planned",
        )
        self.assertEqual(result["worlds"], 1980)
        self.assertEqual(len(result["reachable_runouts"]), 1980)
        self.assertEqual(len(result["private_pair_probabilities"]), 1)
        pair = result["private_pair_probabilities"][0]
        self.assertEqual((pair["sb_hand"], pair["bb_hand"]), ("AdAs", "KdKs"))
        self.assertAlmostEqual(pair["probability"], 1.0)
        self.assertLess(result["decisions"], 10_000)
        self.assertLess(result["public_states"], 250_000)
        self.assertLessEqual(result["planned_operations"], 250_000)

        flop_rows = [row for row in result["strategy"]
                     if row["street"] == "flop"
                     and row["history"][-1] == "flop@2c3c4d"]
        self.assertEqual(len(flop_rows), 1)
        self.assertEqual(flop_rows[0]["player"], "bb")
        self.assertEqual(flop_rows[0]["hand"], "KdKs")
        self.assertEqual(flop_rows[0]["revealed_board"], list(_FLOP))

        kwargs = {
            "config": {"starting_stack": 2, "max_raises": 0,
                       "include_all_in": False},
            "runouts": runouts,
        }
        oracle = replay_policy(result, "AsAd", "KsKd", **kwargs)
        compare_result(result, oracle)
        self.assertEqual(oracle["worlds"], 1980)
        self.assertEqual(oracle["checked_information_sets"],
                         len(result["strategy"]))

        from scripts.benchmark_preflop_full_flop import known_equilibrium_profile
        anchor = replay_policy(known_equilibrium_profile(result),
                               "AsAd", "KsKd", **kwargs)
        self.assertAlmostEqual(anchor["value_sb"], 1.0, delta=1e-10)
        self.assertAlmostEqual(anchor["sb_best_response_value"], 1.0, delta=1e-10)
        self.assertAlmostEqual(anchor["bb_best_response_value"], -1.0, delta=1e-10)
        self.assertLessEqual(anchor["nash_conv"], 1e-10)


if __name__ == "__main__":
    unittest.main()
