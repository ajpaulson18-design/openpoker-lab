"""Exact and bounded full-future chance groups for a direct flop start."""
import math
import unittest
from fractions import Fraction
from unittest.mock import patch

from scripts.preflop_validation import independent_rank
from pokerlab.cards import DECK
from pokerlab import flop_checkdown_worlds as chance


class FlopCheckdownWorldTests(unittest.TestCase):
    def test_aa_vs_kk_full_future_counts_match_independent_best_five_oracle(self):
        plan = chance.prepare_flop_worlds("2c3c4d", "AsAd", "KsKd")
        self.assertEqual(plan.board, ("2c", "3c", "4d"))
        self.assertEqual(plan.budget["unordered_boards"], 990)
        self.assertEqual(plan.budget["physical_worlds"], 1980)
        self.assertEqual(plan.budget["rank_calls_upper_bound"], 1980)

        worlds, counts = plan.build()
        remaining = [card for card in DECK if card not in plan.board + ("As", "Ad", "Ks", "Kd")]
        wins = ties = losses = 0
        for turn_index, turn in enumerate(remaining):
            for river in remaining[turn_index + 1:]:
                board = plan.board + (turn, river)
                first = independent_rank(("As", "Ad") + board)
                second = independent_rank(("Ks", "Kd") + board)
                if first > second:
                    wins += 2
                elif first < second:
                    losses += 2
                else:
                    ties += 2
        self.assertEqual((wins, ties, losses), (1782, 48, 150))
        self.assertEqual(counts, [{
            "oop_hand": "AdAs", "ip_hand": "KdKs", "wins": 1782,
            "ties": 48, "losses": 150, "ordered_outcomes": 1980,
            "pair_probability": 1.0,
        }])
        self.assertEqual(worlds, [(0, 0, 150 / 1980, -1),
                                  (0, 0, 48 / 1980, 0),
                                  (0, 0, 1782 / 1980, 1)])

    def test_dead_board_private_collisions_and_exact_weighted_priors(self):
        plan = chance.prepare_flop_worlds(
            "4d2c3c",
            "AsAd:0.5,QsQd:0.25,2c2d:1",
            "KsKd:1,AhKh:0.5,QsQd:0.75",
        )
        self.assertEqual(plan.board, ("2c", "3c", "4d"))
        self.assertEqual(plan.hands[0], [("Ad", "As"), ("Qd", "Qs")])
        self.assertEqual(plan.hands[1], [("Kd", "Ks"), ("Ah", "Kh"), ("Qd", "Qs")])
        self.assertEqual(plan.pairs, [
            (0, 0, Fraction(1, 3)),
            (0, 1, Fraction(1, 6)),
            (0, 2, Fraction(1, 4)),
            (1, 0, Fraction(1, 6)),
            (1, 1, Fraction(1, 12)),
        ])
        worlds, counts = plan.build()
        self.assertEqual(len(counts), 5)
        self.assertEqual({(row[0], row[1]) for row in worlds},
                         {(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)})
        self.assertTrue(math.isclose(math.fsum(row[2] for row in worlds), 1.0,
                                     rel_tol=0, abs_tol=1e-15))
        for row in counts:
            self.assertEqual(row["wins"] + row["ties"] + row["losses"], 1980)

    def test_subnormal_raw_product_is_normalized_exactly(self):
        tiny = "5e-324"
        plan = chance.prepare_flop_worlds("2c3c4d", f"AsAd:{tiny}", f"KsKd:{tiny}")
        self.assertEqual(plan.pairs, [(0, 0, Fraction(1, 1))])
        worlds, _ = plan.build()
        self.assertTrue(math.isclose(math.fsum(row[2] for row in worlds), 1.0,
                                     rel_tol=0, abs_tol=1e-15))

    def test_positive_pair_probability_underflow_rejected_before_ranking(self):
        with patch.object(chance, "rank_hand") as rank:
            with self.assertRaisesRegex(ValueError, "pair probability underflows"):
                chance.prepare_flop_worlds(
                    "2c3c4d", "AsAd:5e-324,QcQd:1", "KsKd:5e-324,AhKh:1")
            rank.assert_not_called()

    def test_candidate_and_compatible_pair_caps_reject_before_ranking(self):
        with patch.object(chance, "rank_hand") as rank:
            with self.assertRaisesRegex(ValueError, "candidate pair limit"):
                chance.prepare_flop_worlds("2c3c4d", "random", "random")
            with self.assertRaisesRegex(ValueError, "compatible pair limit"):
                chance.prepare_flop_worlds("2c3c4d", "random", "AsAd")
            rank.assert_not_called()

    def test_each_compatible_pair_is_ranked_at_most_1980_times(self):
        original = chance.rank_hand
        with patch.object(chance, "rank_hand", wraps=original) as rank:
            worlds, _ = chance.prepare_flop_worlds("2c3c4d", "AsAd", "KsKd").build()
        self.assertEqual(rank.call_count, 1980)
        self.assertEqual(len(worlds), 3)


if __name__ == "__main__":
    unittest.main()
