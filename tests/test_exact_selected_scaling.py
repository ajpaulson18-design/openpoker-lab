"""Combinatorial full-range anchor for the exact selected-board mass kernel."""
from fractions import Fraction
from math import comb
import unittest
from unittest.mock import patch
from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel

class ExactSelectedScalingTests(unittest.TestCase):
    def test_all_hands_one_selected_board_without_rank_or_world_producer(self):
        with patch("pokerlab.exact_selected_kernel.rank_hand", side_effect=AssertionError("rank")), \
             patch("pokerlab.preflop_solver._enumerate_physical_worlds", side_effect=AssertionError("worlds")):
            kernel = ExactSelectedRunoutKernel("random", "random", ["2c3d4h5s6c"])
            marginals = kernel.joint_marginals_exact()
            self.assertEqual(kernel.prefix_mass_exact(), 1)
        self.assertEqual(kernel.hand_counts, (comb(52, 2), comb(52, 2)))
        self.assertEqual(kernel.statistics()["support_pair_board_occurrences"], comb(47, 2)*comb(45, 2))
        for side in marginals:
            self.assertEqual(sum(side, Fraction()), 1)
            self.assertEqual(sum(value > 0 for value in side), comb(47, 2))
            self.assertTrue(all(value in (Fraction(), Fraction(1, comb(47, 2))) for value in side))
        self.assertEqual(kernel.statistics()["rank_calls"], 0)
