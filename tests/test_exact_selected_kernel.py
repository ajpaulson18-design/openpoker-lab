"""Small literal physical-deal controls for the exact selected kernel."""
from fractions import Fraction
from itertools import count
import unittest

from pokerlab.cards import rank_hand
from pokerlab.exact_selected_kernel import (
    ExactSelectedKernelLimits,
    ExactSelectedRunoutKernel,
)


RUNOUTS = ("2c3d4h5s6c", "2c3d4h7s8c")
SB = {("As", "Ah"): 0.7, ("Ks", "Kh"): 0.3, ("9s", "9h"): 0.2}
BB = {("Ad", "Ac"): 0.4, ("Kd", "Kc"): 0.6, ("8s", "8h"): 0.5}


def _source(source):
    return [(tuple(sorted(hand)), Fraction.from_float(weight))
            for hand, weight in source.items()]


def _literal(sb, bb, runouts, prefix=()):
    """Independent pair/board oracle; deliberately quadratic and test-only."""
    worlds = []
    prefix = tuple(prefix)

    def parts(outcome):
        cards = tuple(outcome[i:i + 2] for i in range(0, 10, 2))
        return tuple(sorted(cards[:3], key=lambda card: "23456789TJQKA".index(card[0]) * 4 + "cdhs".index(card[1]))), cards[3], cards[4]

    for sh, sw in _source(sb):
        for bh, bw in _source(bb):
            if set(sh) & set(bh):
                continue
            for outcome in runouts:
                flop, turn, river = parts(outcome)
                if prefix and ("".join(flop) != prefix[0] or (len(prefix) > 1 and turn != prefix[1]) or
                               (len(prefix) > 2 and river != prefix[2])):
                    continue
                board = set((*flop, turn, river))
                if (set(sh) | set(bh)) & board:
                    continue
                worlds.append((sh, bh, sw * bw, tuple(board)))
    all_worlds = []
    for sh, sw in _source(sb):
        for bh, bw in _source(bb):
            if set(sh) & set(bh):
                continue
            for outcome in runouts:
                flop, turn, river = parts(outcome)
                board = set((*flop, turn, river))
                if not ((set(sh) | set(bh)) & board):
                    all_worlds.append((sh, bh, sw * bw, tuple(board)))
    z = sum((mass for _sh, _bh, mass, _board in all_worlds), Fraction(0))
    marginals = [{h: Fraction(0) for h, _w in _source(sb)},
                 {h: Fraction(0) for h, _w in _source(bb)}]
    mass = Fraction(0)
    for sh, bh, pair_mass, board in worlds:
        marginals[0][sh] += pair_mass / z
        marginals[1][bh] += pair_mass / z
        mass += pair_mass / z
    return z, mass, marginals


class ExactSelectedKernelTests(unittest.TestCase):
    def setUp(self):
        self.kernel = ExactSelectedRunoutKernel(SB, BB, RUNOUTS)

    def test_global_product_normalizer_prefix_and_marginals_match_literal_oracle(self):
        z, all_mass, marginals = _literal(SB, BB, RUNOUTS)
        actual = self.kernel.joint_marginals_exact()
        self.assertEqual(self.kernel.normalizer, z)
        self.assertEqual(self.kernel.prefix_mass_exact(), all_mass)
        for p, source in enumerate((SB, BB)):
            self.assertEqual(actual[p], tuple(marginals[p][hand] for hand, _ in _source(source)))
        flop = ("2c3d4h",)
        _z, flop_mass, flop_marginals = _literal(SB, BB, RUNOUTS, flop)
        self.assertEqual(self.kernel.prefix_mass_exact(flop), flop_mass)
        observed = self.kernel.joint_marginals_exact(flop)
        for p, source in enumerate((SB, BB)):
            self.assertEqual(observed[p], tuple(flop_marginals[p][hand] for hand, _ in _source(source)))

    def test_pair_query_counts_selected_board_occurrences_without_pair_table(self):
        for i, sh in enumerate(self.kernel.hands[0]):
            for j, bh in enumerate(self.kernel.hands[1]):
                matches = 0
                if not (set(sh) & set(bh)):
                    for outcome in RUNOUTS:
                        cards = tuple(outcome[k:k + 2] for k in range(0, 10, 2))
                        board = set(cards)
                        matches += not ((set(sh) | set(bh)) & board)
                expected = (self.kernel.weights[0][i] * self.kernel.weights[1][j] * matches /
                            self.kernel.normalizer)
                self.assertEqual(self.kernel.pair_probability_exact(i, j), expected)

    def test_fold_and_showdown_vectors_are_exact_and_player_oriented(self):
        reach = (Fraction(1, 3), Fraction(2, 5), Fraction(1, 7))
        fold0 = self.kernel.terminal_values_exact((), kind="fold", payoff=Fraction(3, 2),
                                                  player=0, opponent_reach=reach)
        fold1 = self.kernel.terminal_values_exact((), kind="fold", payoff=Fraction(3, 2),
                                                  player=1, opponent_reach=reach)
        self.assertEqual(len(fold0), len(SB))
        self.assertEqual(len(fold1), len(BB))
        self.assertTrue(all(value >= 0 for value in fold0))
        self.assertTrue(all(value <= 0 for value in fold1))
        show0 = self.kernel.terminal_values_exact((), kind="showdown", payoff=2,
                                                  player=0, opponent_reach=reach)
        show1 = self.kernel.terminal_values_exact((), kind="showdown", payoff=2,
                                                  player=1, opponent_reach=reach)
        z, _mass, _marginals = _literal(SB, BB, RUNOUTS)
        expected = [[Fraction(0) for _ in SB], [Fraction(0) for _ in BB]]
        sb_rows, bb_rows = _source(SB), _source(BB)
        for i, (sh, sw) in enumerate(sb_rows):
            for j, (bh, bw) in enumerate(bb_rows):
                if set(sh) & set(bh):
                    continue
                for outcome in RUNOUTS:
                    cards = tuple(outcome[k:k + 2] for k in range(0, 10, 2))
                    board = set(cards)
                    if (set(sh) | set(bh)) & board:
                        continue
                    mass = sw * bw / z
                    r0, r1 = rank_hand(sh + cards), rank_hand(bh + cards)
                    result = (r0 > r1) - (r0 < r1)
                    expected[0][i] += mass * reach[j] * 2 * result
                    expected[1][j] -= mass * reach[i] * 2 * result
        self.assertEqual(show0, tuple(expected[0]))
        self.assertEqual(show1, tuple(expected[1]))

    def test_full_board_blocking_applies_at_root_and_canonical_flop_prefix(self):
        with self.assertRaises(ValueError):
            ExactSelectedRunoutKernel({("2c", "As"): 1.0}, {("Kd", "Kh"): 1.0},
                                      ("2c3d4h5s6c",))

    def test_cache_and_limits_are_bounded_and_immutable(self):
        cached = ExactSelectedRunoutKernel(SB, BB, RUNOUTS, rank_cache_boards=2)
        cached.terminal_values_exact((), kind="showdown", payoff=1, player=0,
                                     opponent_reach=(1, 1, 1))
        cached.terminal_values_exact((), kind="showdown", payoff=1, player=0,
                                     opponent_reach=(1, 1, 1))
        self.assertGreater(cached.statistics()["rank_cache_hits"], 0)
        self.assertEqual(cached.statistics()["rank_calls"], 2 * sum(cached.hand_counts))
        with self.assertRaises((AttributeError, TypeError)):
            ExactSelectedKernelLimits().max_boards = 65
        with self.assertRaises(ValueError):
            ExactSelectedRunoutKernel(SB, BB, RUNOUTS,
                                      limits=ExactSelectedKernelLimits(max_storage_entries=10))
        with self.assertRaises(AttributeError):
            cached.normalizer = Fraction(1)
        with self.assertRaises(AttributeError):
            cached.hands = ((), ())

    def test_prefix_validation_is_bounded_canonical_and_charged(self):
        before = self.kernel.statistics()["work_units_cumulative"]
        with self.assertRaises(ValueError):
            self.kernel.prefix_mass_exact(count())
        after = self.kernel.statistics()["work_units_cumulative"]
        self.assertGreater(after, before)
        with self.assertRaises(ValueError):
            self.kernel.prefix_mass_exact(("4h3d2c",))

    def test_duplicate_canonical_hands_reject_and_zero_reach_keeps_physical_support(self):
        with self.assertRaises(ValueError):
            ExactSelectedRunoutKernel({("As", "Kd"): 1, ("Kd", "As"): 2}, BB, RUNOUTS)
        kernel = ExactSelectedRunoutKernel(SB, BB, RUNOUTS)
        z = kernel.normalizer
        values = kernel.terminal_values_exact((), kind="showdown", payoff=1, player=0,
                                              opponent_reach=(0, 0, 0))
        self.assertEqual(values, (Fraction(0),) * len(SB))
        self.assertEqual(kernel.normalizer, z)
        self.assertGreater(kernel.statistics()["support_pair_board_occurrences"], 0)


if __name__ == "__main__":
    unittest.main()
