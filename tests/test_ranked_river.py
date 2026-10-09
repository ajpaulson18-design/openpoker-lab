"""Independent pair-loop checks for exact ranked river payoff vectors."""
from fractions import Fraction as F
from itertools import combinations
import math
import random
import unittest

from pokerlab.cards import DECK, rank_hand
from pokerlab.ranked_river import RankedRiverPayoffs
from pokerlab.river_tree import _Terminal


def _hand(text):
    return tuple(sorted((text[:2], text[2:])))


def _brute(board, hands, weights, terminal, opponent_reach, player, pot):
    """Rational pair-loop oracle; no production payoff or mass helpers."""
    rank_cache = {}
    total_mass = F(0)
    rank_cache = {}

    def rank_of(hand):
        if hand not in rank_cache:
            rank_cache[hand] = rank_hand(tuple(board) + tuple(hand))
        return rank_cache[hand]

    for i, h0 in enumerate(hands[0]):
        for j, h1 in enumerate(hands[1]):
            if set(h0).isdisjoint(h1):
                total_mass += F(weights[0][i]) * F(weights[1][j])
    output = [F(0) for _ in hands[player]]
    for i, h0 in enumerate(hands[0]):
        for j, h1 in enumerate(hands[1]):
            if not set(h0).isdisjoint(h1):
                continue
            mass = F(weights[0][i]) * F(weights[1][j]) / total_mass
            if terminal.kind == "fold":
                oop_utility = ((1 if terminal.winner == 0 else -1) *
                               (F(pot) / 2 + min(terminal.contributions)))
            else:
                rank0 = rank_of(h0)
                rank1 = rank_of(h1)
                sign = (rank0 > rank1) - (rank0 < rank1)
                oop_utility = sign * (F(pot) / 2 +
                                      min(terminal.contributions))
            own, opponent = (i, j) if player == 0 else (j, i)
            utility = oop_utility if player == 0 else -oop_utility
            output[own] += mass * F(opponent_reach[opponent]) * utility
    return output


def _assert_vector_matches(test, actual, expected, *, places=11):
    test.assertEqual(len(actual), len(expected))
    for index, (got, want) in enumerate(zip(actual, expected)):
        test.assertAlmostEqual(got, float(want), places=places, msg=f"hand {index}")


class RankedRiverPayoffsTests(unittest.TestCase):
    def test_deterministic_random_sparse_ranges_match_pairwise_oracle(self):
        rng = random.Random(28401)
        board = ("2c", "3d", "4h", "5s", "9c")
        available = [card for card in DECK if card not in board]
        all_hands = [tuple(sorted(hand)) for hand in combinations(available, 2)]
        for trial in range(5):
            hands = (rng.sample(all_hands, 8), rng.sample(all_hands, 7))
            weights = (tuple(F(rng.randint(1, 9), rng.randint(1, 7)) for _ in hands[0]),
                       tuple(F(rng.randint(1, 9), rng.randint(1, 7)) for _ in hands[1]))
            # Keep only physically compatible aggregate ranges; the kernel must
            # remove pair blockers before normalizing the joint distribution.
            terminal = _Terminal("showdown", (F(25), F(25)))
            kernel = RankedRiverPayoffs(board, hands, weights, pot=100)
            for player, reach in ((0, [1, 0, 2, F(1, 3), 5, 0, F(2, 7)]),
                                  (1, [F(3, 4), 0, 1, 8, F(1, 2), 0, 2, 1])):
                with self.subTest(trial=trial, player=player):
                    expected = _brute(board, hands, weights, terminal, reach, player, 100)
                    _assert_vector_matches(self, kernel.values(terminal, reach, player), expected)

    def test_dense_random_ranges_match_fraction_oracle_for_both_players(self):
        rng = random.Random(90917)
        board = ("2c", "3d", "4h", "5s", "9c")
        available = [card for card in DECK if card not in board]
        all_hands = [tuple(sorted(hand)) for hand in combinations(available, 2)]
        hands = (rng.sample(all_hands, 32), rng.sample(all_hands, 32))
        weights = (tuple(F(rng.randint(1, 5), rng.randint(1, 5)) for _ in hands[0]),
                   tuple(F(rng.randint(1, 5), rng.randint(1, 5)) for _ in hands[1]))
        reach0 = [F(rng.randint(0, 9), 9) for _ in hands[0]]
        reach1 = [F(rng.randint(0, 9), 9) for _ in hands[1]]
        terminal = _Terminal("showdown", (F(17), F(43)))
        kernel = RankedRiverPayoffs(board, hands, weights, pot=73)
        for player, reach in ((0, reach1), (1, reach0)):
            with self.subTest(player=player):
                expected = _brute(board, hands, weights, terminal, reach, player, 73)
                _assert_vector_matches(self, kernel.values(terminal, reach, player), expected)

    def test_identical_and_one_card_overlapping_holdings_are_blocked(self):
        board = ("2c", "3d", "4h", "5s", "9c")
        shared = _hand("AsAh")
        hands = ((shared, _hand("KcKd"), _hand("QsQh")),
                 (shared, _hand("AsQd"), _hand("JcJd"), _hand("6c7d")))
        weights = ((F(2), F(3), F(5)), (F(7), F(11), F(13), F(17)))
        kernel = RankedRiverPayoffs(board, hands, weights, pot=80)
        terminal = _Terminal("showdown", (F(12), F(35)))
        for player, reach in ((0, [0, F(1, 2), 3, 1]),
                              (1, [1, 2, 0])):
            expected = _brute(board, hands, weights, terminal, reach, player, 80)
            _assert_vector_matches(self, kernel.values(terminal, reach, player), expected)

    def test_fold_winners_ties_and_all_in_excess_refunds_match_oracle(self):
        board = ("2c", "3d", "4h", "5s", "9c")
        hands = ((_hand("AsAh"), _hand("KcKd"), _hand("QsQh")),
                 (_hand("JcJd"), _hand("6c7d"), _hand("8c8d")))
        weights = ((F(1), F(3), F(2)), (F(4), F(1), F(5)))
        kernel = RankedRiverPayoffs(board, hands, weights, pot=100)
        reaches = ([F(0), F(1, 5), F(3, 2)], [F(2), F(0), F(1, 3)])
        terminals = (
            _Terminal("fold", (F(10), F(40)), winner=0),
            _Terminal("fold", (F(10), F(40)), winner=1),
            # Unequal all-in commitments refund the unmatched 30 chips.
            _Terminal("showdown", (F(10), F(40))),
            _Terminal("showdown", (F(25), F(25))),
        )
        for terminal in terminals:
            for player in (0, 1):
                with self.subTest(terminal=terminal, player=player):
                    expected = _brute(board, hands, weights, terminal,
                                      reaches[1 - player], player, 100)
                    _assert_vector_matches(
                        self, kernel.values(terminal, reaches[1 - player], player), expected)

        # On a royal-flush board every compatible pair ties; excess commitment
        # still refunds to the shorter stack and produces zero utility.
        tie_board = ("As", "Ks", "Qs", "Js", "Ts")
        tie_hands = ((_hand("2c3c"), _hand("4d5d")),
                     (_hand("6c7c"), _hand("8d9d")))
        tie_kernel = RankedRiverPayoffs(tie_board, tie_hands,
                                       ((1, 2), (3, 4)), pot=60)
        tie_terminal = _Terminal("showdown", (F(4), F(19)))
        for player in (0, 1):
            values = tie_kernel.values(tie_terminal, [F(1), F(2)], player)
            self.assertEqual(values, [0.0, 0.0])

    def test_all_legal_holdings_are_normalized_once_over_compatible_pairs(self):
        board = ("2c", "3d", "4h", "5s", "9c")
        available = [card for card in DECK if card not in board]
        hands = tuple(tuple(sorted(hand)) for hand in combinations(available, 2))
        weights = ((F(1),) * len(hands), (F(1),) * len(hands))
        kernel = RankedRiverPayoffs(board, (hands, hands), weights, pot=100)
        terminal = _Terminal("fold", (F(0), F(0)), winner=0)
        # Every physical pair of distinct holdings has equal mass. The exact
        # sum of one responder's vector at unit reach is exactly the fold EV.
        values = kernel.values(terminal, [1] * len(hands), 0)
        compatible = sum(1 for h0 in hands for h1 in hands
                         if set(h0).isdisjoint(h1))
        self.assertEqual(compatible, len(hands) * math.comb(len(available) - 2, 2))
        self.assertAlmostEqual(sum(values), 50.0, places=10)

    def test_fraction_reaches_preserve_small_residual_after_large_cancellation(self):
        board = ("2c", "3d", "4h", "5s", "9c")
        own = _hand("AsAh")
        opponents = (_hand("KcKd"), _hand("QcQd"), _hand("6c7d"))
        hands = ((own,), opponents)
        weights = ((F(1),), (F(1), F(1), F(1)))
        reaches = (F(10**16), F(1), F(10**16))
        terminal = _Terminal("showdown", (F(0), F(0)))
        kernel = RankedRiverPayoffs(board, hands, weights, pot=2)
        expected = _brute(board, hands, weights, terminal, reaches, 0, 2)
        _assert_vector_matches(self, kernel.values(terminal, reaches, 0), expected)
        self.assertNotEqual(expected[0], 0)

    def test_tiny_compatible_mass_survives_blocked_dominant_mass(self):
        board = ("2c", "3d", "4h", "5s", "9c")
        own = _hand("AsAh")
        opponents = (_hand("AsKc"), _hand("AhKd"), _hand("KcKd"))
        weights = ((F(1),), (F(10**16), F(10**16), F(1)))
        kernel = RankedRiverPayoffs(board, ( (own,), opponents), weights, pot=40)
        fold = _Terminal("fold", (F(0), F(0)), winner=0)
        reaches = [F(1), F(1), F(1)]
        expected = _brute(board, ( (own,), opponents), weights, fold, reaches, 0, 40)
        _assert_vector_matches(self, kernel.values(fold, reaches, 0), expected)
        self.assertAlmostEqual(kernel.values(fold, reaches, 0)[0], 20.0, places=10)

    def test_ranges_with_only_blocked_weighted_pairs_are_rejected(self):
        board = ("2c", "3d", "4h", "5s", "9c")
        # Every cross-player pair shares a card, despite multiple hands and
        # highly skewed positive weights. There is no physical deal to normalize.
        hands = ((_hand("AsAh"), _hand("KcKd")),
                 (_hand("AsKc"), _hand("AhKd")))
        weights = ((F(10**16), F(1)), (F(1), F(10**16)))
        with self.assertRaisesRegex(ValueError, "no compatible"):
            RankedRiverPayoffs(board, hands, weights, pot=40)

    def test_bounded_reaches_with_skewed_weights_preserve_tiny_showdown_residual(self):
        board = ("2c", "3d", "4h", "5s", "9c")
        own = _hand("AsAh")
        opponents = (_hand("KcKd"), _hand("QcQd"), _hand("6c7d"))
        hands = ((own,), opponents)
        weights = ((F(1),), (F(10**16), F(1), F(10**16)))
        reaches = (F(1), F(1), F(1))
        terminal = _Terminal("showdown", (F(0), F(0)))
        kernel = RankedRiverPayoffs(board, hands, weights, pot=2)
        expected = _brute(board, hands, weights, terminal, reaches, 0, 2)
        actual = kernel.values(terminal, reaches, 0)
        self.assertAlmostEqual(actual[0] / float(expected[0]), 1.0, places=6)
        self.assertGreater(actual[0], 0.0)

    def test_zero_reach_and_identical_tied_holdings_have_no_rank_wins(self):
        board = ("As", "Ks", "Qs", "Js", "Ts")
        shared = _hand("2c3c")
        hands = ((shared, _hand("4d5d")), (shared, _hand("6c7c")))
        kernel = RankedRiverPayoffs(board, hands, ((1, 1), (1, 1)), pot=60)
        terminal = _Terminal("showdown", (F(9), F(31)))
        for player in (0, 1):
            zeros = kernel.values(terminal, [0, 0], player)
            self.assertEqual(zeros, [0.0, 0.0])
            ties = kernel.values(terminal, [1, 1], player)
            self.assertEqual(ties, [0.0, 0.0])

    def test_invalid_dimensions_weights_reaches_and_player_are_rejected(self):
        board = ("2c", "3d", "4h", "5s", "9c")
        hands = ((_hand("AsAh"), _hand("KcKd")), (_hand("QsQh"),))
        terminal = _Terminal("fold", (0, 0), winner=0)
        with self.assertRaises(ValueError):
            RankedRiverPayoffs(board, hands, ((1,), (1,)), pot=20)
        for side in (0, 1):
            for bad_weight in (0, -1, True, float("nan"), float("inf"), -float("inf")):
                weights = [[1, 1], [1]]
                weights[side] = ([1, bad_weight] if side == 0 else [bad_weight])
                with self.subTest(side=side, weight=bad_weight), self.assertRaises(ValueError):
                    RankedRiverPayoffs(board, hands, weights, pot=20)
        kernel = RankedRiverPayoffs(board, hands, ((1, 1), (1,)), pot=20)
        for bad_reach in ([], [1, 2], [float("nan"), 0], [float("inf"), 0],
                          [-1, 0], [True, 0]):
            with self.subTest(reach=bad_reach), self.assertRaises(ValueError):
                kernel.values(terminal, bad_reach, 0)
        for player in (-1, 2, True, 0.0):
            with self.subTest(player=player), self.assertRaises(ValueError):
                kernel.values(terminal, [1], player)
        with self.assertRaises(ValueError):
            RankedRiverPayoffs(("2c", "3d", "4h", "5s"), hands,
                               ((1, 1), (1,)), pot=20)


if __name__ == "__main__":
    unittest.main()
