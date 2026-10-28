"""Literal pair/board Fraction oracle for the internal dyadic plan."""
from fractions import Fraction
import gc
import unittest
import weakref

from pokerlab.cards import rank_hand
from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
from pokerlab.dyadic_selected_arithmetic import DyadicSelectedArithmeticPlan


RUNOUTS = ("2c3d4h5s6c", "2c3d4h7s8c", "2c3d4h7s9c")
SB = {("As", "Ah"): 0.7, ("Ks", "Kh"): 0.3, ("9s", "9h"): 0.2}
BB = {("Ad", "Ac"): 0.4, ("Kd", "Kc"): 0.6, ("8s", "8h"): 0.5}


def _indexes(kernel, prefix):
    found = []
    for index, (flop, turn, river) in enumerate(kernel.selected):
        if (not prefix or ("".join(flop) == prefix[0] and
                (len(prefix) < 2 or turn == prefix[1]) and
                (len(prefix) < 3 or river == prefix[2]))):
            found.append(index)
    return tuple(found)


def _oracle(kernel, prefix=(), *, kind=None, payoff=None, player=None, reach=None):
    """Enumerate private pairs and boards using literal Fraction products."""
    weights, hands = kernel.weights, kernel.hands
    selected = set(_indexes(kernel, prefix))
    worlds = []
    normalizer = Fraction(0)
    for i, own0 in enumerate(hands[0]):
        for j, own1 in enumerate(hands[1]):
            if set(own0) & set(own1):
                continue
            mass = weights[0][i] * weights[1][j]
            for board_index, (flop, turn, river) in enumerate(kernel.selected):
                board = tuple(flop) + (turn, river)
                if not ((set(own0) | set(own1)) & set(board)):
                    normalizer += mass
                    if board_index in selected:
                        worlds.append((i, j, board, mass))
    if kind is None:
        result = [[Fraction(0) for _ in hands[0]],
                  [Fraction(0) for _ in hands[1]]]
        for i, j, _board, mass in worlds:
            result[0][i] += mass / normalizer
            result[1][j] += mass / normalizer
        return tuple(tuple(side) for side in result)

    opponent = 1 - player
    answer = [Fraction(0) for _ in hands[player]]
    for i, j, board, mass in worlds:
        own_index, opp_index = (i, j) if player == 0 else (j, i)
        if kind == "fold":
            value = payoff if player == 0 else -payoff
        else:
            own = hands[player][own_index]
            other = hands[opponent][opp_index]
            own_rank = rank_hand(own + board)
            other_rank = rank_hand(other + board)
            value = payoff * ((own_rank > other_rank) - (own_rank < other_rank))
        answer[own_index] += (mass / normalizer) * reach[opp_index] * value
    return tuple(answer)


class DyadicSelectedArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.kernel = ExactSelectedRunoutKernel(SB, BB, RUNOUTS, arithmetic="dyadic")
        self.plan = self.kernel._arithmetic_plan

    def test_all_prefix_marginals_match_literal_fraction_pair_oracle(self):
        prefixes = [(), ("2c3d4h",), ("2c3d4h", "7s"),
                    ("2c3d4h", "7s", "8c")]
        for prefix in prefixes:
            with self.subTest(prefix=prefix):
                self.assertEqual(self.kernel.joint_marginals_exact(prefix),
                                 _oracle(self.kernel, prefix))

    def test_fold_and_showdown_both_seats_all_prefixes_match_oracle(self):
        reach_by_player = {
            0: (Fraction(1, 2), Fraction(3, 4), Fraction(1, 8)),
            1: (Fraction(1, 4), Fraction(1, 2), Fraction(0)),
        }
        prefixes = [(), ("2c3d4h",), ("2c3d4h", "7s"),
                    ("2c3d4h", "7s", "8c")]
        for prefix in prefixes:
            indexes = _indexes(self.kernel, prefix)
            for player in (0, 1):
                reach = reach_by_player[player]
                for kind in ("fold", "showdown"):
                    payoff = Fraction(3, 2)
                    with self.subTest(prefix=prefix, player=player, kind=kind):
                        observed = self.plan.terminal(
                            indexes, kind=kind, payoff=payoff,
                            player=player, opponent_reach=reach)
                        self.assertEqual(observed, _oracle(
                            self.kernel, prefix, kind=kind, payoff=payoff,
                            player=player, reach=reach))

    def test_subnormal_dyadic_weights_and_zero_reach_are_exact(self):
        sb = {("As", "Ah"): 1e-300, ("Ks", "Kh"): 5e-324}
        bb = {("Ad", "Ac"): 5e-324, ("Kd", "Kc"): 1e-300}
        kernel = ExactSelectedRunoutKernel(sb, bb, RUNOUTS, arithmetic="dyadic")
        plan = kernel._arithmetic_plan
        self.assertEqual(plan.marginals(_indexes(kernel, ())), _oracle(kernel))
        zero = (Fraction(0), Fraction(0))
        before_ranks = kernel.statistics()["rank_calls"]
        self.assertEqual(plan.terminal(_indexes(kernel, ()), kind="showdown",
                                       payoff=Fraction(1), player=0,
                                       opponent_reach=zero), (Fraction(0), Fraction(0)))
        self.assertEqual(kernel.statistics()["rank_calls"], before_ranks)

    def test_same_holding_addback_and_board_only_rank_ties(self):
        sb = {("As", "Ah"): 1.0, ("Ks", "Kh"): 0.5}
        bb = {("As", "Ah"): 0.25, ("Kd", "Kc"): 1.0}
        kernel = ExactSelectedRunoutKernel(sb, bb, RUNOUTS, arithmetic="dyadic")
        plan = kernel._arithmetic_plan
        self.assertEqual(plan.marginals(_indexes(kernel, ())), _oracle(kernel))
        reach = (Fraction(1), Fraction(3, 4))
        for player in (0, 1):
            self.assertEqual(plan.terminal(_indexes(kernel, ()), kind="fold",
                                           payoff=Fraction(2), player=player,
                                           opponent_reach=reach),
                             _oracle(kernel, kind="fold", payoff=Fraction(2),
                                     player=player, reach=reach))
        tie_prefix = ("2c3d4h", "5s", "6c")
        ties = plan.terminal(_indexes(kernel, tie_prefix), kind="showdown",
                             payoff=Fraction(1), player=0,
                             opponent_reach=(Fraction(1), Fraction(1)))
        self.assertEqual(ties, _oracle(kernel, tie_prefix, kind="showdown",
                                       payoff=Fraction(1), player=0,
                                       reach=(Fraction(1), Fraction(1))))
        self.assertEqual(ties, (Fraction(0), Fraction(0)))

    def test_non_dyadic_reach_or_payoff_rejects_before_rank_cache(self):
        before = self.kernel.statistics()["rank_calls"]
        indexes = _indexes(self.kernel, ())
        with self.assertRaisesRegex(ValueError, "dyadic denominator"):
            self.plan.terminal(indexes, kind="showdown", payoff=Fraction(1),
                               player=0, opponent_reach=(Fraction(1, 3),) * 3)
        with self.assertRaisesRegex(ValueError, "dyadic denominator"):
            self.plan.terminal(indexes, kind="showdown", payoff=Fraction(1, 3),
                               player=0, opponent_reach=(Fraction(1),) * 3)
        self.assertEqual(self.kernel.statistics()["rank_calls"], before)
        self.assertEqual(self.kernel.statistics()["rank_cache_misses"], 0)

    def test_plan_is_immutable_receipted_and_does_not_keep_kernel_alive(self):
        receipt = self.plan.receipt()
        self.assertEqual(receipt["version"], "dyadic-selected-arithmetic-v1")
        self.assertLessEqual(receipt["retained_plan_entries"],
                             receipt["setup_reservation_entries"])
        self.assertGreater(receipt["side_weight_max_bits"][0], 0)
        with self.assertRaises(AttributeError):
            self.plan._z_integer = 1
        kernel_ref = weakref.ref(self.kernel)
        self.kernel = None
        gc.collect()
        self.assertIsNone(kernel_ref())
        with self.assertRaisesRegex(ValueError, "no longer exists"):
            self.plan.marginals(())
        self.plan = None


if __name__ == "__main__":
    unittest.main()
