"""Independent physical-pair and sequential-deal prefix probability controls.

The oracle enumerates only private pairs. It uses no production card-total,
normalization, blocker, or chance-divisor helper and constructs no future worlds.
"""
from fractions import Fraction
from itertools import combinations
import math
import random
import unittest

from pokerlab.full_deck_prefix_mass import FullDeckPrefixMass


SEED = 83441
MODEL_COUNT = 40
PREFIX_COUNT = 160
PAIR_CHECK_COUNT = 11_520


class IndependentFullDeckPrefixTests(unittest.TestCase):
    def test_random_models_literal_pairs_and_exact_side_rescaling(self):
        rng = random.Random(SEED)
        all_hands = list(combinations(range(20), 2))
        pair_checks = prefix_checks = 0
        for model_index in range(MODEL_COUNT):
            sb = {hand: 2.0 ** rng.randrange(-20, 4)
                  for hand in rng.sample(all_hands, 8)}
            bb = {hand: 2.0 ** rng.randrange(-20, 4)
                  for hand in rng.sample(all_hands, 9)}
            exact_sb = {hand: Fraction.from_float(weight)
                        for hand, weight in sb.items()}
            exact_bb = {hand: Fraction.from_float(weight)
                        for hand, weight in bb.items()}
            root_mass = sum(
                (sw * bw for sh, sw in exact_sb.items()
                 for bh, bw in exact_bb.items()
                 if set(sh).isdisjoint(bh)), Fraction(0))
            operator = FullDeckPrefixMass(sb, bb)
            scaled = FullDeckPrefixMass(
                {hand: weight * 8 for hand, weight in sb.items()},
                {hand: weight / 4 for hand, weight in bb.items()})
            self.assertEqual(operator.root_compatible_mass, root_mass)

            for length in (0, 3, 4, 5):
                board = tuple(rng.sample(range(52), length))
                # The flop is unordered; subsequent cards retain reveal order.
                if length == 0:
                    divisor = 1
                elif length == 3:
                    divisor = math.comb(48, 3)
                elif length == 4:
                    divisor = math.comb(48, 3) * 45
                else:
                    divisor = math.comb(48, 3) * 45 * 44
                candidate = operator.at(board)
                rescaled = scaled.at(board)
                with self.subTest(model=model_index, board=board):
                    self.assertEqual(candidate.total_mass, rescaled.total_mass)
                    self.assertEqual(candidate.hand_masses, rescaled.hand_masses)
                    literal_total = Fraction(0)
                    own_masses = ({hand: Fraction(0) for hand in sb},
                                  {hand: Fraction(0) for hand in bb})
                    for sb_hand, sb_weight in exact_sb.items():
                        for bb_hand, bb_weight in exact_bb.items():
                            legal = (set(sb_hand).isdisjoint(bb_hand)
                                     and set(sb_hand + bb_hand).isdisjoint(board))
                            expected = (sb_weight * bb_weight / (root_mass * divisor)
                                        if legal else Fraction(0))
                            self.assertEqual(candidate.pair_mass(sb_hand, bb_hand),
                                             expected)
                            literal_total += expected
                            own_masses[0][sb_hand] += expected
                            own_masses[1][bb_hand] += expected
                            pair_checks += 1
                    self.assertEqual(candidate.total_mass, literal_total)
                    self.assertEqual(tuple(dict(side) for side in candidate.hand_masses),
                                     own_masses)
                prefix_checks += 1
        self.assertEqual(prefix_checks, PREFIX_COUNT)
        self.assertEqual(pair_checks, PAIR_CHECK_COUNT)

    def test_fixed_private_pair_matches_sequential_physical_deals(self):
        operator = FullDeckPrefixMass({(0, 1): 1.0}, {(2, 3): 1.0})
        # Six ordered three-card deals reveal the same canonical flop.
        flop_probability = Fraction(6, 48 * 47 * 46)
        self.assertEqual(operator.at((4, 5, 6)).total_mass, flop_probability)
        self.assertEqual(operator.at((4, 5, 6, 7)).total_mass,
                         flop_probability * Fraction(1, 45))
        self.assertEqual(operator.at((4, 5, 6, 7, 8)).total_mass,
                         flop_probability * Fraction(1, 45) * Fraction(1, 44))

    def test_minimum_subnormal_preserves_exact_positive_pair_and_marginal(self):
        tiny = float.fromhex("0x0.0000000000001p-1022")
        operator = FullDeckPrefixMass(
            {(0, 1): tiny, (2, 3): 1.0}, {(4, 5): 1.0})
        expected = Fraction.from_float(tiny) / (1 + Fraction.from_float(tiny))
        root = operator.at(())
        self.assertGreater(expected, 0)
        self.assertEqual(root.hand_masses[0][(0, 1)], expected)
        self.assertEqual(root.pair_mass((0, 1), (4, 5)), expected)


if __name__ == "__main__":
    unittest.main()
