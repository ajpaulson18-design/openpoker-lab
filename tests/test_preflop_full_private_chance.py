import itertools
import unittest
from unittest.mock import patch

from scripts.preflop_validation import replay_policy
from pokerlab.preflop_solver import solve_preflop


_RANKS = "23456789TJQKA"
_SUITS = "cdhs"
_FLOP = ("2c", "3c", "4d")
_SB_HANDS = {"AdAs", "QdQs"}
_BB_HANDS = {"KdKs", "JcJh"}
_SB_RANGE = "AsAd,QsQd"
_BB_RANGE = "KsKd,JhJc"


def _all_public_future_runouts():
    """Spell the fixed-flop public deck independently of production cards."""
    unavailable = set(_FLOP)
    available = [rank + suit for rank in _RANKS for suit in _SUITS
                 if rank + suit not in unavailable]
    assert len(available) == 49
    return tuple(_FLOP + (turn, river)
                 for turn, river in itertools.permutations(available, 2))


class FullPrivateChanceTests(unittest.TestCase):
    def test_exhaustive_future_cards_with_weighted_private_ranges(self):
        runouts = _all_public_future_runouts()
        self.assertEqual(len(runouts), 49 * 48)
        self.assertEqual(len(set(runouts)), 2352)

        config = {"starting_stack": 2, "max_raises": 0,
                  "include_all_in": False}
        with patch("pokerlab.preflop_solver.rank_hand") as production_rank:
            with self.assertRaisesRegex(ValueError, "3 million world iterations"):
                solve_preflop(_SB_RANGE, _BB_RANGE, config,
                              runouts=runouts, iterations=1000,
                              traversal="planned")
            production_rank.assert_not_called()

        result = solve_preflop(_SB_RANGE, _BB_RANGE, config,
                               runouts=runouts, iterations=10,
                               traversal="planned")
        self.assertEqual(result["worlds"], 4 * 45 * 44)
        self.assertEqual(len(result["reachable_runouts"]), 2352 - 16)
        self.assertEqual(result["compatible_private_pairs"], 4)
        self.assertEqual(len(result["private_pair_probabilities"]), 4)
        production_pairs = {
            (row["sb_hand"], row["bb_hand"]): row["probability"]
            for row in result["private_pair_probabilities"]
        }
        self.assertEqual(set(production_pairs),
                         {(sb, bb) for sb in _SB_HANDS for bb in _BB_HANDS})
        for probability in production_pairs.values():
            self.assertAlmostEqual(probability, 0.25, delta=1e-12)

        self.assertLess(result["decisions"], 10_000)
        self.assertLess(result["public_states"], 250_000)
        self.assertLessEqual(result["planned_operations"], 250_000)

        kwargs = {"config": config, "runouts": runouts}
        oracle = replay_policy(result, _SB_RANGE, _BB_RANGE, **kwargs)
        self.assertEqual(oracle["worlds"], 4 * 45 * 44)
        self.assertEqual(oracle["checked_information_sets"],
                         len(result["strategy"]))
        oracle_pairs = {
            (row["sb"], row["bb"]): row["probability"]
            for row in oracle["private_pair_probabilities"]
        }
        self.assertEqual(set(oracle_pairs), set(production_pairs))
        for pair, probability in production_pairs.items():
            self.assertAlmostEqual(probability, oracle_pairs[pair], delta=1e-12)
        for field in ("value_sb", "value_bb", "sb_best_response_value",
                      "bb_best_response_value", "nash_conv"):
            self.assertAlmostEqual(result[field], oracle[field], delta=1e-10)

        for row in result["strategy"]:
            if row["player"] == "sb":
                self.assertIn(row["hand"], _SB_HANDS)
            else:
                self.assertIn(row["hand"], _BB_HANDS)
            self.assertEqual(len(row["revealed_board"]),
                             {"preflop": 0, "flop": 3, "turn": 4,
                              "river": 5}[row["street"]])
            self.assertTrue(set(row["revealed_board"]).isdisjoint(
                set(row["hand"][index:index + 2] for index in (0, 2))))


if __name__ == "__main__":
    unittest.main()
