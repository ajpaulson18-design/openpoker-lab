"""Independent Fraction checks for turn-to-river range payoff kernels."""

from fractions import Fraction as F
import unittest

from pokerlab.cards import DECK, rank_hand
from pokerlab.river_tree import _Terminal
from pokerlab.turn_range_kernel import TurnRangePayoffs


def _hand(*cards):
    """Make the kernel's canonical holding without calling its parser."""
    return tuple(sorted(cards))


def _oracle(board, hands, weights, pot, runouts, node, opponent_reach, player,
            prefix=()):
    """Direct exact sum over compatible pair × legal river worlds."""
    candidates = DECK if runouts is None else tuple(runouts)
    worlds = []
    total = F(0)
    for river in candidates:
        if river in board:
            continue
        for i, hand0 in enumerate(hands[0]):
            for j, hand1 in enumerate(hands[1]):
                if set(hand0) & set(hand1):
                    continue
                if river in hand0 or river in hand1:
                    continue
                mass = F(weights[0][i]) * F(weights[1][j])
                worlds.append((river, i, j, mass))
                total += mass
    if total == 0:
        raise ValueError("oracle fixture has no physical pair/runout worlds")

    own_index = player
    opponent = 1 - player
    values = [F(0) for _ in hands[own_index]]
    for river, i, j, mass in worlds:
        if prefix and river != prefix[0]:
            continue
        own = i if player == 0 else j
        opp = j if player == 0 else i
        reach = F(opponent_reach[opp])
        if node.kind == "fold":
            sign = 1 if node.winner == player else -1
        else:
            rank0 = rank_hand(tuple(board) + (river,) + hands[0][i])
            rank1 = rank_hand(tuple(board) + (river,) + hands[1][j])
            sign = (rank0 > rank1) - (rank0 < rank1)
            if player == 1:
                sign = -sign
        payoff = F(pot, 2) + min(node.contributions)
        values[own] += mass / total * reach * sign * payoff
    return tuple(values)


def _oracle_marginals(board, hands, weights, runouts, prefix=()):
    candidates = DECK if runouts is None else tuple(runouts)
    worlds = []
    total = F(0)
    for river in candidates:
        if river in board:
            continue
        for i, hand0 in enumerate(hands[0]):
            for j, hand1 in enumerate(hands[1]):
                if set(hand0) & set(hand1) or river in hand0 or river in hand1:
                    continue
                mass = F(weights[0][i]) * F(weights[1][j])
                worlds.append((river, i, j, mass))
                total += mass
    result = [[F(0) for _ in side] for side in hands]
    branch_mass = F(0)
    for river, i, j, mass in worlds:
        if prefix and river != prefix[0]:
            continue
        result[0][i] += mass / total
        result[1][j] += mass / total
        branch_mass += mass / total
    return tuple(tuple(row) for row in result), branch_mass


class TurnRangeKernelTests(unittest.TestCase):
    def test_full_turn_branches_match_fraction_global_pair_runout_oracle(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = (
            (_hand("As", "Ah"), _hand("Ks", "Kh"),
             _hand("Qs", "Qh"), _hand("3c", "4c")),
            (_hand("As", "Kc"), _hand("Ah", "Kd"),
             _hand("Qc", "Qd"), _hand("Tc", "Th")),
        )
        weights = ((F(3), F(1, 2), F(2), F(7)),
                   (F(5), F(2), F(3, 2), F(11)))
        selected = None  # all 48 cards; each physical private pair has 44 rivers
        kernel = TurnRangePayoffs(board, hands, weights, pot=80, runouts=selected)

        expected_root, _ = _oracle_marginals(board, hands, weights, selected)
        actual_root = kernel.joint_marginals()
        self.assertEqual(len(kernel.branch_probabilities), 48)
        self.assertAlmostEqual(sum(kernel.branch_probabilities.values()), 1.0, places=12)
        self.assertEqual(kernel.compatible_world_count,
                         sum(44 for i, hand0 in enumerate(hands[0])
                             for j, hand1 in enumerate(hands[1])
                             if set(hand0).isdisjoint(hand1)))
        for side in (0, 1):
            self.assertEqual(len(actual_root[side]), len(hands[side]))
            for got, expected in zip(actual_root[side], expected_root[side]):
                self.assertAlmostEqual(got, float(expected), places=11)

        for river, probability in kernel.branch_probabilities.items():
            branch_marginals, branch_mass = _oracle_marginals(
                board, hands, weights, selected, (river,),
            )
            self.assertAlmostEqual(probability, float(branch_mass), places=12)
            actual = kernel.joint_marginals((river,))
            for side in (0, 1):
                for got, expected in zip(actual[side], branch_marginals[side]):
                    self.assertAlmostEqual(got, float(expected), places=11)

    def test_root_fold_and_river_showdown_vectors_match_fraction_oracle(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((_hand("As", "Ah"), _hand("Ks", "Kh"), _hand("Qs", "Qh")),
                 (_hand("As", "Kc"), _hand("Ah", "Kd"), _hand("Qc", "Qd")))
        weights = ((F(3), F(1, 2), F(2)), (F(5), F(2), F(3, 2)))
        selected = ("3c", "4d", "7s", "8h", "Tc")
        kernel = TurnRangePayoffs(board, hands, weights, pot=70, runouts=selected)
        reach0, reach1 = (F(1, 2), F(2), F(3, 4)), (F(2), F(1, 3), F(5, 2))
        fold = _Terminal("fold", (7.0, 2.0), 0)
        for player, reach in ((0, reach1), (1, reach0)):
            actual = kernel.values(fold, reach, player)
            expected = _oracle(board, hands, weights, 70, selected, fold, reach, player)
            for got, want in zip(actual, expected):
                self.assertAlmostEqual(got, float(want), places=10)

        for river in selected:
            showdown = _Terminal("showdown", (7.0, 2.0))
            for player, reach in ((0, reach1), (1, reach0)):
                for node in (fold, showdown):
                    actual = kernel.values(node, reach, player, prefix=(river,))
                    expected = _oracle(board, hands, weights, 70, selected, node,
                                       reach, player, prefix=(river,))
                    for got, want in zip(actual, expected):
                        self.assertAlmostEqual(got, float(want), places=10)

    def test_orphan_hands_zero_mass_and_selected_branch_weights(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((_hand("As", "Ah"), _hand("Kc", "Kd"), _hand("Qs", "Qh")),
                 (_hand("As", "Kc"), _hand("Ah", "Kd")))
        weights = ((F(1), F(3), F(2)), (F(5), F(2)))
        selected = ("3c", "4d", "7s")
        kernel = TurnRangePayoffs(board, hands, weights, pot=40, runouts=selected)
        marginal = kernel.joint_marginals()
        self.assertEqual(marginal[0][0], 0.0)
        self.assertEqual(marginal[0][1], 0.0)
        fold = _Terminal("fold", (0.0, 0.0), 0)
        self.assertEqual(kernel.values(fold, (1, 1), 0)[:2], [0.0, 0.0])
        self.assertAlmostEqual(sum(kernel.branch_probabilities.values()), 1.0)

    def test_tied_board_and_asymmetric_terminal_contributions(self):
        board = ("Kc", "Qd", "Jh", "Ts")
        hands = ((_hand("2c", "3d"),), (_hand("4c", "5d"),))
        weights = ((F(7),), (F(3),))
        kernel = TurnRangePayoffs(board, hands, weights, pot=101,
                                  runouts=("9c", "8h"))
        showdown = _Terminal("showdown", (17.0, 3.0))
        # The 9c board makes the board's 9-K straight play for both hands.
        values = kernel.values(showdown, (1,), 0, prefix=("9c",))
        self.assertAlmostEqual(values[0], 0.0, places=12)
        fold = _Terminal("fold", (17.0, 3.0), 0)
        self.assertAlmostEqual(kernel.values(fold, (1,), 0, prefix=("9c",))[0],
                               0.5 * (101 / 2 + 3))
        self.assertAlmostEqual(kernel.values(fold, (1,), 1, prefix=("9c",))[0],
                               -0.5 * (101 / 2 + 3))

    def test_invalid_runouts_prefixes_and_cumulative_fallback_budget(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((_hand("As", "Ah"),),
                 (_hand("As", "Kc"), _hand("Ah", "Kd"), _hand("Kc", "Kd")))
        weights = ((F(1),), (F(1), F(1), F(1, 10**9)))
        for runouts in ((), ("2c",), ("3s", "3s"), ("ZZ",)):
            with self.subTest(runouts=runouts):
                with self.assertRaises((TypeError, ValueError)):
                    TurnRangePayoffs(board, hands, weights, pot=20, runouts=runouts)
        kernel = TurnRangePayoffs(board, hands, weights, pot=20,
                                  runouts=("3c", "4d"))
        with self.assertRaisesRegex(ValueError, "require a revealed river"):
            kernel.values(_Terminal("showdown", (0.0, 0.0)), (1, 1, 1), 0)
        for prefix in (("8s",), ("3c", "4d"), ("ZZ",)):
            with self.subTest(prefix=prefix):
                with self.assertRaises((TypeError, ValueError)):
                    kernel.joint_marginals(prefix)
                with self.assertRaises((TypeError, ValueError)):
                    kernel.values(_Terminal("fold", (0.0, 0.0), 0), (1, 1, 1),
                                  0, prefix=prefix)

        # Each selected river builds/uses its own fallback-ranked kernel, but
        # one shared cap must bound their aggregate rare direct pair scans.
        with self.assertRaisesRegex(ValueError, "fallback pair-check budget"):
            TurnRangePayoffs(board, hands, weights, pot=20,
                             runouts=("3c", "4d"), fallback_pair_limit=8)


if __name__ == "__main__":
    unittest.main()
