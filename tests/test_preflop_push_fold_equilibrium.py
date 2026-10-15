import unittest
from fractions import Fraction
from itertools import product
from unittest.mock import patch

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


def split_suit_orbit_counts():
    # Swapping hearts and clubs globally maps AsKh to AsKc while fixing
    # AsAd, QsQd and KsKd. Suit-invariant board enumeration gives identical
    # physical W/T/L for the two QQ-versus-AK pairs.
    return [
        {"sb_hand": "AdAs", "bb_hand": "KdKs",
         "wins": 1_410_336, "ties": 9_308, "losses": 292_660, "boards": BOARDS},
        {"sb_hand": "QdQs", "bb_hand": "AsKh",
         "wins": 968_267, "ties": 7_226, "losses": 736_811, "boards": BOARDS},
        {"sb_hand": "QdQs", "bb_hand": "AsKc",
         "wins": 968_267, "ties": 7_226, "losses": 736_811, "boards": BOARDS},
        {"sb_hand": "QdQs", "bb_hand": "KdKs",
         "wins": 292_846, "ties": 9_336, "losses": 1_410_122, "boards": BOARDS},
    ]


def assert_exact_pure_policy_certificate(testcase, result):
    """Build an independent payoff oracle and replay every own-hand deviation."""
    sb_hands = ("AdAs", "QdQs")
    bb_hands = ("AsKc", "AsKh", "KdKs")
    priors = {
        ("AdAs", "KdKs"): Fraction(8, 13),
        ("QdQs", "AsKc"): Fraction(1, 26),
        ("QdQs", "AsKh"): Fraction(1, 26),
        ("QdQs", "KdKs"): Fraction(4, 13),
    }
    counts = {(row["sb_hand"], row["bb_hand"]): row
              for row in split_suit_orbit_counts()}
    signs = {pair: Fraction(row["wins"] - row["losses"], row["boards"])
             for pair, row in counts.items()}
    row_policies = tuple(product((0, 1), repeat=len(sb_hands)))
    column_policies = tuple(product((0, 1), repeat=len(bb_hands)))
    sb_index = {hand: index for index, hand in enumerate(sb_hands)}
    bb_index = {hand: index for index, hand in enumerate(bb_hands)}
    matrix = []
    for sb_policy in row_policies:
        row = []
        for bb_policy in column_policies:
            payoff = Fraction()
            for (sb_hand, bb_hand), prior in priors.items():
                if not sb_policy[sb_index[sb_hand]]:
                    transfer = Fraction(-1, 2)
                elif not bb_policy[bb_index[bb_hand]]:
                    transfer = Fraction(1)
                else:
                    transfer = 2 * signs[sb_hand, bb_hand]
                payoff += prior * transfer
            row.append(payoff)
        matrix.append(tuple(row))
    matrix = tuple(matrix)
    testcase.assertEqual(result["pure_policy_payoff_matrix"], matrix)
    row_count, column_count = len(matrix), len(matrix[0])
    row_mass = {policy: Fraction() for policy in row_policies}
    column_mass = {policy: Fraction() for policy in column_policies}
    for item in result["pure_policy_weights"]["sb"]:
        policy = tuple(int(action == "shove") for action in item["policy"])
        row_mass[policy] += Fraction(*item["probability"])
    for item in result["pure_policy_weights"]["bb"]:
        policy = tuple(int(action == "call") for action in item["policy"])
        column_mass[policy] += Fraction(*item["probability"])
    q = tuple(column_mass[policy] for policy in column_policies)
    p = tuple(row_mass[policy] for policy in row_policies)
    value = Fraction(*result["value_sb_fraction"])
    testcase.assertEqual(sum(p), 1)
    testcase.assertEqual(sum(q), 1)
    testcase.assertTrue(all(sum(matrix[i][j] * q[j]
                                for j in range(column_count)) <= value
                            for i in range(row_count)))
    testcase.assertTrue(all(sum(p[i] * matrix[i][j]
                                for i in range(row_count)) >= value
                            for j in range(column_count)))


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

    def test_exact_4_by_8_matrix_and_role_transposition(self):
        matrix = [
            [1, -1, 2, 2, 2, 2, 2, 2],
            [-1, 1, 2, 2, 2, 2, 2, 2],
            [-2, -2, 2, 2, 2, 2, 2, 2],
            [-2, -2, 2, 2, 2, 2, 2, 2],
        ]
        result = exact_zero_sum_witness(matrix)
        transposed = exact_zero_sum_witness(
            [[-value for value in row] for row in zip(*matrix)])
        self.assertEqual(result["value"], 0)
        self.assertEqual(transposed["value"], -result["value"])
        self.assertEqual(result["row_probabilities"],
                         (Fraction(1, 2), Fraction(1, 2), Fraction(0), Fraction(0)))
        self.assertEqual(result["column_probabilities"][:2],
                         (Fraction(1, 2), Fraction(1, 2)))
        self.assertEqual(transposed["row_probabilities"][:2],
                         result["column_probabilities"][:2])
        self.assertEqual(transposed["column_probabilities"][:4],
                         result["row_probabilities"])
        with patch("scripts.preflop_push_fold_equilibrium.Fraction",
                   side_effect=AssertionError("unsupported matrix values must not be converted")):
            with self.assertRaisesRegex(ValueError, "up to 4x8"):
                exact_zero_sum_witness([[0] * 8 for _ in range(8)])

    def test_rejects_missing_counts_unsupported_subset_and_too_many_hands(self):
        with self.assertRaisesRegex(ValueError, "Missing W/T/L"):
            equilibrium(SB, BB, CONFIG, synthetic_counts()[:2], board_count=4)
        with self.assertRaisesRegex(ValueError, "pair_subset"):
            equilibrium(SB, BB, CONFIG, synthetic_counts(),
                        pair_subset=[("AdAs", "AsKh")], board_count=4)
        with self.assertRaisesRegex(ValueError, "three active hands on one side and two"):
            equilibrium("AsAh,KsKh,QsQh", "AdAc,KdKc,QdQc", CONFIG,
                        [], board_count=4)


class AsymmetricThreeHandWitnessTests(unittest.TestCase):
    def test_suit_orbit_split_preserves_physical_equilibrium_and_priors(self):
        old = equilibrium(SB, BB, CONFIG, physical_anchor_counts())
        split = equilibrium(
            "AsAd:1,QsQd:0.5",
            "AsKh:0.125,AsKc:0.125,KsKd:1",
            CONFIG,
            split_suit_orbit_counts(),
        )
        self.assertEqual(split["search_limit"]["row_policies"], 4)
        self.assertEqual(split["search_limit"]["column_policies"], 8)
        self.assertEqual(split["search_limit"]["max_support_candidates"], 494)
        self.assertEqual(split["pair_priors"], {
            "AdAs|KdKs": [8, 13],
            "QdQs|AsKc": [1, 26],
            "QdQs|AsKh": [1, 26],
            "QdQs|KdKs": [4, 13],
        })
        self.assertEqual(old["search_limit"], {
            "row_policies": 4, "column_policies": 4,
            "max_active_hands_per_player": 2})
        self.assertEqual(split["value_sb_fraction"], old["value_sb_fraction"])
        self.assertEqual(split["behavioral_probabilities"][(0, "QdQs")],
                         old["behavioral_probabilities"][(0, "QdQs")])
        self.assertEqual(split["behavioral_probabilities"][(1, "KdKs")],
                         old["behavioral_probabilities"][(1, "KdKs")])
        self.assertEqual(split["behavioral_probabilities"][(1, "AsKh")], 1)
        self.assertEqual(split["behavioral_probabilities"][(1, "AsKc")], 1)
        assert_exact_pure_policy_certificate(self, split)

    def test_three_sb_hands_and_two_bb_hands_use_transposed_policy_shape(self):
        sb_range = "AsAh,KsKh,QsQh"
        bb_range = "AdAc,KdKc"
        counts = []
        for sb_hand in ("AsAh", "KsKh", "QsQh"):
            for bb_hand in ("AdAc", "KdKc"):
                counts.append({"sb_hand": sb_hand, "bb_hand": bb_hand,
                               "wins": 2, "ties": 0, "losses": 2, "boards": 4})
        result = equilibrium(sb_range, bb_range, CONFIG, counts, board_count=4)
        self.assertEqual(result["search_limit"]["row_policies"], 8)
        self.assertEqual(result["search_limit"]["column_policies"], 4)
        self.assertEqual(result["value_sb_fraction"], [0, 1])
        matrix = result["pure_policy_payoff_matrix"]
        row_mixture = [Fraction() for _ in range(8)]
        column_mixture = [Fraction() for _ in range(4)]
        row_policies = tuple(product((0, 1), repeat=3))
        column_policies = tuple(product((0, 1), repeat=2))
        for item in result["pure_policy_weights"]["sb"]:
            policy = tuple(int(action == "shove") for action in item["policy"])
            row_mixture[row_policies.index(policy)] += Fraction(*item["probability"])
        for item in result["pure_policy_weights"]["bb"]:
            policy = tuple(int(action == "call") for action in item["policy"])
            column_mixture[column_policies.index(policy)] += Fraction(*item["probability"])
        value = Fraction(*result["value_sb_fraction"])
        self.assertTrue(all(sum(matrix[i][j] * column_mixture[j] for j in range(4)) <= value
                            for i in range(8)))
        self.assertTrue(all(sum(row_mixture[i] * matrix[i][j] for i in range(8)) >= value
                            for j in range(4)))

    def test_three_hands_on_each_side_reject_before_policy_search(self):
        with patch("scripts.preflop_push_fold_equilibrium.product",
                   side_effect=AssertionError("policy matrix should not be built")):
            with self.assertRaisesRegex(ValueError, "three active hands on one side and two"):
                equilibrium(
                    "AsAh,KsKh,QsQh",
                    "AdAc,KdKc,QdQc",
                    CONFIG,
                    [],
                    board_count=4,
                )



if __name__ == "__main__":
    unittest.main()

