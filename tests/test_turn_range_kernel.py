"""Independent Fraction checks for turn-to-river range payoff kernels."""

from fractions import Fraction as F
from math import isfinite
import unittest
import math
from unittest.mock import patch

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
        payoff = F(pot) / 2 + F(min(node.contributions))
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
    def test_tiny_positive_selected_branch_preserves_conditioned_root_fold(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((_hand("As", "Ah"), _hand("Kc", "Kd")),
                 (_hand("Qh", "Qs"),))
        weights = ((F(1), F(1, 10**310)), (F(1),))
        selected = ("As",)
        kernel = TurnRangePayoffs(board, hands, weights, pot=20, runouts=selected)
        expected_marginals, _ = _oracle_marginals(board, hands, weights, selected)
        root = kernel.joint_marginals()
        prefix = kernel.joint_marginals(("As",))
        for side in (0, 1):
            for actual, expected in zip(root[side], expected_marginals[side]):
                self.assertAlmostEqual(actual, float(expected), places=12)
            self.assertEqual(root[side], prefix[side])
        self.assertEqual(root[0], (0.0, 1.0))
        fold = _Terminal("fold", (0.0, 0.0), 0)
        for branch in ((), ("As",)):
            actual = kernel.values(fold, (1.0,), 0, prefix=branch)
            expected = _oracle(board, hands, weights, 20, selected, fold,
                               (1,), 0, prefix=branch)
            self.assertEqual(actual, [0.0, 10.0])
            for got, want in zip(actual, expected):
                self.assertTrue(isfinite(got))
                self.assertAlmostEqual(got, float(want), places=12)

    def test_unrepresentable_joint_mass_is_rejected(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((_hand("Ah", "As"), _hand("Kc", "Kd")),
                 (_hand("As", "Kc"), _hand("Ah", "Qh")))
        weights = ((F(1), F(1, 10**200)), (F(1), F(1, 10**200)))
        # Three high-mass pairings are blocked. The remaining compatible
        # pair reaches RankedRiverPayoffs' reciprocal/compatible-mass limit
        # before turn-level conditional branch normalization is constructed.
        with self.assertRaisesRegex(ValueError, "unrepresentable"):
            TurnRangePayoffs(board, hands, weights, pot=20)

    def test_subnormal_conditioned_root_fold_matches_exact_world_sum_both_players(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((_hand("Ah", "As"), _hand("Kc", "Kd")),
                 (_hand("Qh", "Qs"),))
        tiny = math.nextafter(0.0, 1.0)
        weights = ((1.0, tiny), (1.0,))
        kernel = TurnRangePayoffs(board, hands, weights, pot=20, runouts=("As",))
        self.assertTrue(kernel.exceptional_conditioning)
        self.assertEqual(kernel.branch_probabilities["As"], 1.0)

        for contributions, factor in (((0.0, 0.0), 10.0), ((4.0, 4.0), 14.0)):
            for reach in (0.25, 0.75):
                for player, winner in ((0, 0), (0, 1), (1, 1), (1, 0)):
                    fold = _Terminal("fold", contributions, winner)
                    opponent_reach = (reach,) if player == 0 else (reach, reach)
                    actual_root = kernel.values(fold, opponent_reach, player)
                    actual_prefix = kernel.values(
                        fold, opponent_reach, player, prefix=("As",),
                    )
                    expected = _oracle(
                        board, hands, weights, 20, ("As",), fold,
                        opponent_reach, player,
                    )
                    signed_expected = factor * reach * (1 if winner == player else -1)
                    self.assertEqual(actual_root, actual_prefix)
                    if player == 0:
                        self.assertEqual(actual_root[1], signed_expected)
                        self.assertEqual(actual_root[0], 0.0)
                    else:
                        self.assertEqual(actual_root[0], signed_expected)
                    for got, want in zip(actual_root, expected):
                        self.assertEqual(got, float(want))

    def test_scaled_branch_mass_admits_selected_one_world_at_1e400_scale(self):
        board = ("2c", "7d", "9h", "Js")
        hands = ((_hand("As", "Ah"), _hand("3c", "4c")),
                 (_hand("As", "Kh"), _hand("5c", "6c")))
        tiny = float("1e-200")
        weights = ((1.0, tiny), (1.0, tiny))
        selected = ("As",)
        kernel = TurnRangePayoffs(board, hands, weights, pot=100,
                                  runouts=selected)
        self.assertTrue(kernel.exceptional_conditioning)
        self.assertEqual(kernel.branch_probabilities, {"As": 1.0})
        expected_marginals, exact_branch_mass = _oracle_marginals(
            board, hands, weights, selected,
        )
        self.assertEqual(exact_branch_mass, F(1))
        actual_marginals = kernel.joint_marginals()
        for player in (0, 1):
            self.assertEqual(actual_marginals[player], tuple(
                float(value) for value in expected_marginals[player]
            ))
        self.assertEqual(actual_marginals[0], (0.0, 1.0))
        fold = _Terminal("fold", (0.0, 0.0), 0)
        for player, reach in ((0, (1.0, 1.0)), (1, (1.0, 1.0))):
            actual = kernel.values(fold, reach, player)
            expected = _oracle(board, hands, weights, 100, selected,
                               fold, reach, player)
            self.assertEqual(actual, [float(value) for value in expected])
            showdown = _Terminal("showdown", (0.0, 0.0))
            actual_showdown = kernel.values(showdown, reach, player,
                                            prefix=("As",))
            expected_showdown = _oracle(
                board, hands, weights, 100, selected, showdown, reach, player,
                prefix=("As",),
            )
            self.assertEqual(actual_showdown,
                             [float(value) for value in expected_showdown])

    def test_scaled_branch_probabilities_normalize_before_subnormal_rounding(self):
        board = ("2c", "7d", "9h", "Js")
        hands = ((_hand("As", "Ah"), _hand("3c", "4c")),
                 (_hand("As", "Kd"), _hand("5c", "6c")))
        tiny = math.nextafter(0.0, 1.0)
        weights = ((1.0, tiny), (1.0, tiny))
        selected = ("As", "Kd")
        kernel = TurnRangePayoffs(board, hands, weights, pot=20,
                                  runouts=selected)
        exact_marginals, _ = _oracle_marginals(board, hands, weights, selected)
        expected_branch_probabilities = {
            river: _oracle_marginals(board, hands, weights, selected, (river,))[1]
            for river in selected
        }
        for river in selected:
            self.assertEqual(kernel.branch_probabilities[river],
                             float(expected_branch_probabilities[river]))
        self.assertEqual(kernel.branch_probabilities["As"], tiny)
        self.assertEqual(kernel.branch_probabilities["Kd"], 1.0)
        actual_marginals = kernel.joint_marginals()
        for player in (0, 1):
            self.assertEqual(actual_marginals[player], tuple(
                float(value) for value in exact_marginals[player]
            ))
        self.assertEqual(actual_marginals[0][1], 2.0 * tiny)

        # Adding Ah contributes a second ordinary-mass branch, making the
        # positive As conditional probability round below min-subnormal.
        with self.assertRaisesRegex(ValueError, "conditional probability"):
            TurnRangePayoffs(board, hands, weights, pot=20,
                             runouts=("As", "Kd", "Ah"))

    def test_unequal_tiny_multiriver_mass_matches_fraction_law_and_root_folds(self):
        board = ("2c", "7d", "9h", "Js")
        hands = ((_hand("Ah", "As"), _hand("3c", "4c"),
                  _hand("3h", "As")),
                 (_hand("Ah", "As"), _hand("5c", "6c")))
        tiny = float("1e-200")
        weights = ((1.0, tiny, 2 * tiny), (1.0, tiny))
        selected = ("As", "Ah")
        kernel = TurnRangePayoffs(board, hands, weights, pot=20,
                                  runouts=selected)
        self.assertTrue(kernel.exceptional_conditioning)

        expected_root, _ = _oracle_marginals(board, hands, weights, selected)
        expected_branches = {
            river: _oracle_marginals(board, hands, weights, selected,
                                     (river,))[1]
            for river in selected
        }
        self.assertEqual(kernel.branch_probabilities["As"], 0.25)
        self.assertEqual(kernel.branch_probabilities["Ah"], 0.75)
        for river in selected:
            self.assertEqual(kernel.branch_probabilities[river],
                             float(expected_branches[river]))
        marginals = kernel.joint_marginals()
        self.assertEqual(marginals[0], (0.0, 0.5, 0.5))
        self.assertEqual(marginals[1], (0.0, 1.0))
        for player in (0, 1):
            for actual, expected in zip(marginals[player], expected_root[player]):
                self.assertEqual(actual, float(expected))

        reaches = {0: (0.17, 0.25), 1: (0.13, 0.25, 0.75)}
        for contributions, payout in (((0.0, 0.0), 10.0),
                                      ((4.0, 4.0), 14.0)):
            for player in (0, 1):
                reach = reaches[player]
                for winner in (player, 1 - player):
                    fold = _Terminal("fold", contributions, winner)
                    actual = kernel.values(fold, reach, player)
                    expected = _oracle(board, hands, weights, 20, selected,
                                       fold, reach, player)
                    prefix_sum = [0.0] * len(hands[player])
                    for river in selected:
                        branch_values = kernel.values(
                            fold, reach, player, prefix=(river,),
                        )
                        for index, value in enumerate(branch_values):
                            prefix_sum[index] += value
                    for got, want, prefix_value in zip(actual, expected, prefix_sum):
                        self.assertAlmostEqual(got, float(want), places=14)
                        self.assertAlmostEqual(got, prefix_value, places=14)

                    if winner == player and contributions == (0.0, 0.0):
                        expected_anchor = (
                            (0.0, 1.25, 1.25) if player == 0 else (0.0, 5.0)
                        )
                        self.assertEqual(actual, list(expected_anchor))
                    if winner == player and contributions == (4.0, 4.0):
                        expected_anchor = (
                            (0.0, 1.75, 1.75) if player == 0 else (0.0, 7.0)
                        )
                        for got, want in zip(actual, expected_anchor):
                            self.assertAlmostEqual(got, want, places=14)

    def test_normal_mass_tiny_reaches_use_exact_root_fold_pairs(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((_hand("Ah", "As"), _hand("Kc", "Kd")),
                 (_hand("Qh", "Qs"),))
        weights = ((F(1), F(1, 10**300)), (F(1),))
        selected = ("As",)
        kernels = []
        for pot in (20, 2 * 10**100):
            kernel = TurnRangePayoffs(board, hands, weights, pot=pot,
                                      runouts=selected)
            kernels.append(kernel)
            self.assertFalse(kernel.exceptional_conditioning)
            self.assertEqual(kernel.branch_probabilities, {"As": 1.0})
            for contributions, scale in (((0.0, 0.0), F(pot, 2)),
                                         ((4.0, 4.0), F(pot, 2) + 4)):
                for player, winner, reach in (
                    (0, 0, (1e-100,)), (0, 1, (1e-100,)),
                    (1, 1, (0.0, 1e-100)), (1, 0, (0.0, 1e-100)),
                ):
                    fold = _Terminal("fold", contributions, winner)
                    actual = kernel.values(fold, reach, player)
                    prefix = kernel.values(fold, reach, player, prefix=("As",))
                    expected = _oracle(board, hands, weights, pot, selected,
                                       fold, reach, player)
                    self.assertEqual(actual, prefix)
                    self.assertEqual(actual, [float(value) for value in expected])
                    nonzero = 1 if player == 0 else 0
                    sign = 1.0 if winner == player else -1.0
                    self.assertEqual(actual[nonzero], float(scale) * 1e-100 * sign)
            self.assertGreater(kernel.stable_root_fold_calls, 0)
            self.assertEqual(kernel.stable_root_fold_pair_checks,
                             kernel.stable_root_fold_calls * 2)
            self.assertGreaterEqual(kernel.fallback_pair_checks,
                                    kernel.stable_root_fold_pair_checks)

    def test_nonzero_subnormal_weighted_reach_uses_exact_pairs(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((_hand("Ah", "As"), _hand("Kc", "Kd")),
                 (_hand("Qh", "Qs"),))
        weights = ((F(1), F(1, 10**200)), (F(1),))
        kernel = TurnRangePayoffs(board, hands, weights, pot=20,
                                  runouts=("As",))
        self.assertFalse(kernel.exceptional_conditioning)
        reach = (0.0, 1e-120)
        product = kernel.weights[0][1] * reach[1]
        self.assertGreater(product, 0.0)
        self.assertLess(product, math.ulp(0.0) * 2**52)
        fold = _Terminal("fold", (0.0, 0.0), 0)
        actual = kernel.values(fold, reach, 1)
        expected = _oracle(board, hands, weights, 20, ("As",), fold,
                           reach, 1)
        self.assertEqual(actual, [float(value) for value in expected])
        self.assertEqual(actual[0], -float(F.from_float(1e-120) * 10))
        self.assertEqual(kernel.stable_root_fold_calls, 1)

    def test_normalized_mass_subnormal_uses_exact_pairs(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((_hand("3c", "4c"), _hand("Ah", "As")),
                 (_hand("Qh", "Qs"),))
        tiny = math.ldexp(1.0, -1022)
        weights = ((1.0, tiny), (1.0,))
        selected = ("As", "Kd")
        kernel = TurnRangePayoffs(board, hands, weights, pot=2,
                                  runouts=selected)
        self.assertFalse(kernel.exceptional_conditioning)
        fold = _Terminal("fold", (0.0, 0.0), 0)
        reach = (1.0,)
        actual = kernel.values(fold, reach, 0)
        expected = _oracle(board, hands, weights, 2, selected,
                           fold, reach, 0)
        self.assertEqual(actual, [float(value) for value in expected])
        self.assertGreater(actual[1], 0.0)
        self.assertLess(actual[1], math.ldexp(1.0, -1022))
        self.assertEqual(kernel.stable_root_fold_calls, 1)

    def test_multi_river_exact_fold_counts_each_legal_selected_card(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((_hand("Ah", "As"), _hand("3c", "4c")),
                 (_hand("Qh", "Qs"), _hand("5c", "6c")))
        weights = ((F(1), F(1, 10**200)), (F(1), F(1, 10**200)))
        selected = ("As", "Kd")
        pot = 2 * 10**300
        kernel = TurnRangePayoffs(board, hands, weights, pot=pot,
                                  runouts=selected)
        self.assertFalse(kernel.exceptional_conditioning)
        self.assertGreater(kernel.branch_probabilities["As"], 0.0)
        self.assertGreater(kernel.branch_probabilities["Kd"], 0.0)
        reaches = {0: (1e-200, 0.0), 1: (0.0, 1e-200)}
        for player in (0, 1):
            fold = _Terminal("fold", (0.0, 0.0), player)
            actual = kernel.values(fold, reaches[player], player)
            expected = _oracle(board, hands, weights, pot, selected,
                               fold, reaches[player], player)
            prefix_sum = [0.0] * len(hands[player])
            for river in selected:
                values = kernel.values(fold, reaches[player], player,
                                       prefix=(river,))
                prefix_sum = [left + right
                              for left, right in zip(prefix_sum, values)]
            self.assertEqual(actual, [float(value) for value in expected])
            for got, prefix_value in zip(actual, prefix_sum):
                self.assertAlmostEqual(got, prefix_value, delta=1e-14)
        self.assertGreater(kernel.stable_root_fold_calls, 0)

    def test_stable_pair_budgets_preflight_atomically_and_keep_failed_charges(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((_hand("Ah", "As"), _hand("Kc", "Kd")),
                 (_hand("Qh", "Qs"),))
        weights = ((F(1), F(1, 10**300)), (F(1),))
        fold = _Terminal("fold", (0.0, 0.0), 0)

        stable_limited = TurnRangePayoffs(
            board, hands, weights, pot=20, runouts=("As",),
            stable_root_pair_limit=1,
        )
        before_fallback = stable_limited.fallback_pair_checks
        with patch("pokerlab.turn_range_kernel._fraction_from_float",
                   side_effect=AssertionError("conversion ran before admission")):
            with self.assertRaisesRegex(ValueError, "Stable turn root-fold"):
                stable_limited.values(fold, (0.0, 1e-100), 1)
        self.assertEqual(stable_limited.fallback_pair_checks, before_fallback)
        self.assertEqual(stable_limited.stable_root_fold_calls, 0)
        self.assertEqual(stable_limited.stable_root_fold_pair_checks, 0)

        fallback_limited = TurnRangePayoffs(
            board, hands, weights, pot=20, runouts=("As",),
            fallback_pair_limit=1,
        )
        with patch("pokerlab.turn_range_kernel._fraction_from_float",
                   side_effect=AssertionError("conversion ran before admission")):
            with self.assertRaisesRegex(ValueError, "fallback pair-check budget"):
                fallback_limited.values(fold, (0.0, 1e-100), 1)
        self.assertEqual(fallback_limited.fallback_pair_checks, 0)
        self.assertEqual(fallback_limited.stable_root_fold_pair_checks, 0)

        charged = TurnRangePayoffs(
            board, hands, weights, pot=20, runouts=("As",),
            stable_root_pair_limit=2, fallback_pair_limit=2,
        )
        with patch("pokerlab.turn_range_kernel._fraction_from_float",
                   side_effect=ArithmeticError("injected conversion failure")):
            with self.assertRaisesRegex(ArithmeticError, "injected"):
                charged.values(fold, (0.0, 1e-100), 1)
        self.assertEqual(charged.stable_root_fold_calls, 1)
        self.assertEqual(charged.stable_root_fold_pair_checks, 2)
        self.assertEqual(charged.fallback_pair_checks, 2)
        with self.assertRaisesRegex(ValueError, "fallback pair-check budget"):
            charged.values(fold, (0.0, 1e-100), 1)
        self.assertEqual(charged.stable_root_fold_calls, 1)
        self.assertEqual(charged.stable_root_fold_pair_checks, 2)
        self.assertEqual(charged.fallback_pair_checks, 2)

    def test_true_zero_reach_does_not_use_or_charge_stable_path(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((_hand("Ah", "As"), _hand("Kc", "Kd")),
                 (_hand("Qh", "Qs"),))
        weights = ((F(1), F(1, 10**300)), (F(1),))
        kernel = TurnRangePayoffs(board, hands, weights, pot=20,
                                  runouts=("As",), stable_root_pair_limit=0)
        before = kernel.fallback_pair_checks
        values = kernel.values(_Terminal("fold", (0.0, 0.0), 0), (0.0,), 0)
        self.assertEqual(values, [0.0, 0.0])
        self.assertEqual(kernel.stable_root_fold_calls, 0)
        self.assertEqual(kernel.stable_root_fold_pair_checks, 0)
        self.assertEqual(kernel.fallback_pair_checks, before)

    def test_stable_root_pair_limit_rejects_bool_negative_and_noninteger(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((_hand("Ah", "As"),), (_hand("Qh", "Qs"),))
        for limit in (True, -1, 1.0, "1"):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValueError, "Stable root pair limit"):
                    TurnRangePayoffs(board, hands, ((1,), (1,)), pot=20,
                                     runouts=("3c",),
                                     stable_root_pair_limit=limit)

    def test_hand_slot_cap_precedes_rank_kernel_allocation(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((_hand("As", "Ah"),), (_hand("Kc", "Kd"),))
        with patch("pokerlab.turn_range_kernel.MAX_HAND_SLOTS", 0), \
             patch("pokerlab.turn_range_kernel.RankedRiverPayoffs") as ranked:
            with self.assertRaisesRegex(ValueError, "filtered hand slots"):
                TurnRangePayoffs(board, hands, ((1,), (1,)), pot=20,
                                 runouts=("3s",))
        ranked.assert_not_called()

    def test_failed_partial_fallback_scan_is_charged_before_retry(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((_hand("Ah", "As"),),
                 (_hand("As", "Kc"), _hand("Ah", "Kd"), _hand("Kc", "Kd")))
        weights = ((F(1),), (F(1), F(1), F(1, 10**9)))
        kernel = TurnRangePayoffs(board, hands, weights, pot=20,
                                  runouts=("3c", "4d"), fallback_pair_limit=15)
        self.assertEqual(kernel.fallback_pair_checks, 12)
        with self.assertRaisesRegex(ValueError, "fallback pair-check budget"):
            kernel.joint_marginals()
        charged_after_failure = kernel.fallback_pair_checks
        self.assertEqual(charged_after_failure, 15)
        with self.assertRaisesRegex(ValueError, "fallback pair-check budget"):
            kernel.joint_marginals()
        self.assertEqual(kernel.fallback_pair_checks, charged_after_failure)

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
