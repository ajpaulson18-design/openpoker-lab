import unittest
from fractions import Fraction

from scripts.preflop_push_fold_equilibrium import (
    NoEquilibriumWitness,
    equilibrium,
    exact_zero_sum_witness,
)

BOARDS = 1_712_304
CONFIG = {"small_blind": 0.5, "big_blind": 1, "starting_stack": 2}
SB = "AsAd:1,QsQd:0.5"
BB = "AsKh:0.25,KsKd:1"


def synthetic_counts():
    return [
        {"sb_hand": "AdAs", "bb_hand": "KdKs",
         "wins": 3, "ties": 1, "losses": 0, "boards": 4},
        {"sb_hand": "QdQs", "bb_hand": "AsKh",
         "wins": 2, "ties": 1, "losses": 1, "boards": 4},
        {"sb_hand": "QdQs", "bb_hand": "KdKs",
         "wins": 0, "ties": 1, "losses": 3, "boards": 4},
    ]


def physical_anchor_counts():
    return [
        {"sb_hand": "AdAs", "bb_hand": "KdKs",
         "wins": 1_410_336, "ties": 9_308, "losses": 292_660, "boards": BOARDS},
        {"sb_hand": "QdQs", "bb_hand": "AsKh",
         "wins": 968_267, "ties": 7_226, "losses": 736_811, "boards": BOARDS},
        {"sb_hand": "QdQs", "bb_hand": "KdKs",
         "wins": 292_846, "ties": 9_336, "losses": 1_410_122, "boards": BOARDS},
    ]


class ExactMatrixWitnessTests(unittest.TestCase):
    def test_matching_pennies_has_exact_mixed_witness(self):
        result = exact_zero_sum_witness([[1, -1], [-1, 1]])
        self.assertEqual(result["row_probabilities"], (Fraction(1, 2), Fraction(1, 2)))
        self.assertEqual(result["column_probabilities"], (Fraction(1, 2), Fraction(1, 2)))
        self.assertEqual(result["value"], 0)

    def test_pure_saddle_and_tie_matrix_are_certified(self):
        pure = exact_zero_sum_witness([[1, 1], [0, 0]])
        self.assertEqual(pure["value"], 1)
        self.assertEqual(pure["row_probabilities"], (Fraction(1), Fraction(0)))
        tied = exact_zero_sum_witness([[0, 0], [0, 0]])
        self.assertEqual(tied["value"], 0)

    def test_invalid_matrix_dimensions_and_nonrectangular_input_reject(self):
        for matrix in ([], [[]], [[1, 2], [3]], [[0] * 5 for _ in range(5)]):
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                exact_zero_sum_witness(matrix)


class PushFoldReweightWitnessTests(unittest.TestCase):
    def test_synthetic_three_pair_mixed_equilibrium_anchor(self):
        result = equilibrium(SB, BB, CONFIG, synthetic_counts(), board_count=4)
        self.assertEqual(result["value_sb_fraction"], [83, 130])
        self.assertEqual(result["behavioral_probabilities"][(0, "AdAs")], Fraction(1))
        self.assertEqual(result["behavioral_probabilities"][(0, "QdQs")], Fraction(2, 5))
        self.assertEqual(result["behavioral_probabilities"][(1, "AsKh")], Fraction(1))
        self.assertEqual(result["behavioral_probabilities"][(1, "KdKs")], Fraction(7, 10))
        self.assertEqual(result["pair_priors"]["AdAs|KdKs"], [8, 13])
        self.assertEqual(result["pair_priors"]["QdQs|AsKh"], [1, 13])
        self.assertEqual(result["pair_priors"]["QdQs|KdKs"], [4, 13])

    def test_independently_counted_physical_anchor(self):
        result = equilibrium(SB, BB, CONFIG, physical_anchor_counts())
        self.assertEqual(result["pair_priors"]["AdAs|KdKs"], [8, 13])
        self.assertEqual(result["pair_priors"]["QdQs|AsKh"], [1, 13])
        self.assertEqual(result["pair_priors"]["QdQs|KdKs"], [4, 13])
        counts = {(row["sb_hand"], row["bb_hand"]): row for row in physical_anchor_counts()}
        u = Fraction(counts[("AdAs", "KdKs")]["wins"] -
                     counts[("AdAs", "KdKs")]["losses"], BOARDS)
        v = Fraction(counts[("QdQs", "AsKh")]["wins"] -
                     counts[("QdQs", "AsKh")]["losses"], BOARDS)
        z = Fraction(counts[("QdQs", "KdKs")]["wins"] -
                     counts[("QdQs", "KdKs")]["losses"], BOARDS)
        a, b, d = Fraction(8, 13), Fraction(1, 13), Fraction(4, 13)
        x = a * (2 * u - 1) / (d * (1 - 2 * z))
        y = (b * 2 * v + d + Fraction(1, 2) * (b + d)) / (d * (1 - 2 * z))
        expected_value = a * ((1 - y) + y * 2 * u) - Fraction(1, 2) * (b + d)
        self.assertEqual(result["behavioral_probabilities"][(0, "AdAs")], Fraction(1))
        self.assertEqual(result["behavioral_probabilities"][(0, "QdQs")], x)
        self.assertEqual(result["behavioral_probabilities"][(1, "AsKh")], Fraction(1))
        self.assertEqual(result["behavioral_probabilities"][(1, "KdKs")], y)
        self.assertEqual(Fraction(*result["value_sb_fraction"]), expected_value)

    def test_relative_reweights_certify_distinct_pure_equilibria(self):
        counts = physical_anchor_counts()
        aa_heavy = equilibrium(
            "AsAd:10,QsQd:0.5", "AsKh:0.25,KsKd:1",
            CONFIG, counts)
        self.assertEqual(aa_heavy["pair_priors"], {
            "AdAs|KdKs": [16, 17], "QdQs|AsKh": [1, 85], "QdQs|KdKs": [4, 85]})
        self.assertEqual(aa_heavy["behavioral_probabilities"][(0, "AdAs")], 1)
        self.assertEqual(aa_heavy["behavioral_probabilities"][(0, "QdQs")], 1)
        self.assertEqual(aa_heavy["behavioral_probabilities"][(1, "AsKh")], 1)
        self.assertEqual(aa_heavy["behavioral_probabilities"][(1, "KdKs")], 0)

        ak_heavy = equilibrium(
            "AsAd:1,QsQd:0.5", "AsKh:10,KsKd:1",
            CONFIG, counts)
        self.assertEqual(ak_heavy["pair_priors"], {
            "AdAs|KdKs": [2, 13], "QdQs|AsKh": [10, 13], "QdQs|KdKs": [1, 13]})
        self.assertEqual(ak_heavy["behavioral_probabilities"][(0, "AdAs")], 1)
        self.assertEqual(ak_heavy["behavioral_probabilities"][(0, "QdQs")], 1)
        self.assertEqual(ak_heavy["behavioral_probabilities"][(1, "AsKh")], 1)
        self.assertEqual(ak_heavy["behavioral_probabilities"][(1, "KdKs")], 1)

    def test_reweighted_single_pair_subset_conditions_and_certifies_payoff(self):
        result = equilibrium(
            "AsAd:0.8,QsQd:0.5",
            "AsKh:0.4,KsKd:0.9",
            {"small_blind": 0.5, "big_blind": 1, "starting_stack": [3, 2]},
            synthetic_counts(),
            pair_subset=[("AdAs", "KdKs")],
            board_count=4,
        )
        self.assertEqual(result["pair_priors"], {"AdAs|KdKs": [1, 1]})
        self.assertEqual(result["behavioral_probabilities"][(0, "AdAs")], 1)
        self.assertEqual(result["behavioral_probabilities"][(1, "KdKs")], 0)
        self.assertEqual(result["value_sb_fraction"], [1, 1])

    def test_zero_reweight_reuses_old_counts_but_excludes_zero_mass_hand(self):
        result = equilibrium(
            "AsAd:0,QsQd:0.5",
            "AsKh:0.25,KsKd:1",
            CONFIG,
            synthetic_counts(),
            pair_subset=[("QdQs", "KdKs")],
            board_count=4,
        )
        self.assertEqual(result["pair_priors"], {"QdQs|KdKs": [1, 1]})
        self.assertEqual(result["value_sb_fraction"], [-1, 2])
        self.assertEqual(result["behavioral_probabilities"][(0, "QdQs")], 0)
        self.assertEqual(result["behavioral_probabilities"][(1, "KdKs")], 1)

    def test_rejects_missing_counts_unsupported_subset_and_too_many_hands(self):
        with self.assertRaisesRegex(ValueError, "Missing W/T/L"):
            equilibrium(SB, BB, CONFIG, synthetic_counts()[:2], board_count=4)
        with self.assertRaisesRegex(ValueError, "pair_subset"):
            equilibrium(SB, BB, CONFIG, synthetic_counts(),
                        pair_subset=[("AdAs", "AsKh")], board_count=4)
        with self.assertRaisesRegex(ValueError, "at most two"):
            equilibrium("AsAd,QsQd,KsKd", BB, CONFIG,
                        synthetic_counts(), board_count=4)


if __name__ == "__main__":
    unittest.main()

