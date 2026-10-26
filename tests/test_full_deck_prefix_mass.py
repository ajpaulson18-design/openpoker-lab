"""Independent physical-pair controls for the full-deck prefix-mass operator."""
from __future__ import annotations

from fractions import Fraction
from itertools import combinations
import math
import unittest

from pokerlab.full_deck_prefix_mass import FullDeckPrefixMass


def _weight_map(source):
    return {hand: Fraction.from_float(float(weight))
            for hand, weight in source.items()}


def _literal_reference(sb_source, bb_source, board=()):
    """Enumerate ordered physical private pairs independently of card totals."""
    sb, bb = _weight_map(sb_source), _weight_map(bb_source)
    compatible = [(sh, bh, sw * bw)
                  for sh, sw in sb.items()
                  for bh, bw in bb.items()
                  if not (set(sh) & set(bh))]
    root = sum((mass for _, _, mass in compatible), Fraction(0))
    if len(board) == 0:
        divisor = 1
    elif len(board) == 3:
        divisor = math.comb(48, 3)
    elif len(board) == 4:
        divisor = math.comb(48, 3) * 45
    else:
        divisor = math.comb(48, 3) * 45 * 44
    pair_masses = {
        (sh, bh): (mass / (root * divisor)
                   if not (set(sh) & set(board) or set(bh) & set(board))
                   else Fraction(0))
        for sh, bh, mass in compatible
    }
    sb_hands = {hand: sum((mass for (sh, _), mass in pair_masses.items()
                           if sh == hand), Fraction(0)) for hand in sb}
    bb_hands = {hand: sum((mass for (_, bh), mass in pair_masses.items()
                           if bh == hand), Fraction(0)) for hand in bb}
    return root, sum(pair_masses.values(), Fraction(0)), pair_masses, (sb_hands, bb_hands)


class FullDeckPrefixMassTests(unittest.TestCase):
    def setUp(self):
        self.sb = {(0, 1): 1.0, (2, 3): 2.0, (4, 8): 0.5, (10, 11): 3.0}
        self.bb = {(0, 2): 2.5, (1, 4): 1.25, (5, 6): 2.0, (10, 12): 0.75}
        self.operator = FullDeckPrefixMass(self.sb, self.bb)

    def assert_matches_literal(self, board):
        expected_root, total, pairs, hands = _literal_reference(self.sb, self.bb, board)
        actual = self.operator.at(board)
        self.assertEqual(self.operator.root_compatible_mass, expected_root)
        self.assertEqual(actual.total_mass, total)
        self.assertEqual(tuple(dict(items) for items in actual.hand_masses), hands)
        for sb_hand in self.sb:
            for bb_hand in self.bb:
                self.assertEqual(actual.pair_mass(sb_hand, bb_hand),
                                 pairs.get((sb_hand, bb_hand), Fraction(0)))
        self.assertEqual(sum(actual.hand_masses[0].values()), actual.total_mass)
        self.assertEqual(sum(actual.hand_masses[1].values()), actual.total_mass)
        return actual

    def test_root_and_flop_turn_river_match_literal_ordered_pair_scan(self):
        self.assert_matches_literal(())
        self.assert_matches_literal((7, 9, 13))
        self.assert_matches_literal((13, 7, 9, 14))
        self.assert_matches_literal((13, 7, 9, 14, 15))

    def test_single_pair_uses_sequential_deal_probability_anchors(self):
        operator = FullDeckPrefixMass({(0, 1): 1.0}, {(2, 3): 1.0})
        flop = operator.at((4, 5, 6))
        turn = operator.at((4, 5, 6, 7))
        river = operator.at((4, 5, 6, 7, 8))
        self.assertEqual(flop.pair_mass((0, 1), (2, 3)),
                         Fraction(6, 48 * 47 * 46))
        self.assertEqual(turn.pair_mass((0, 1), (2, 3)),
                         Fraction(6, 48 * 47 * 46) / 45)
        self.assertEqual(river.pair_mass((0, 1), (2, 3)),
                         Fraction(6, 48 * 47 * 46) / 45 / 44)

    def test_power_of_two_rescaling_each_range_preserves_prefix_masses(self):
        scaled_sb = {hand: math.ldexp(weight, 3) for hand, weight in self.sb.items()}
        scaled_bb = {hand: math.ldexp(weight, -2) for hand, weight in self.bb.items()}
        scaled = FullDeckPrefixMass(scaled_sb, scaled_bb)
        self.assertEqual(scaled.root_compatible_mass,
                         self.operator.root_compatible_mass * 2)
        for board in ((), (7, 9, 13), (7, 9, 13, 14), (7, 9, 13, 14, 15)):
            original_prefix = self.operator.at(board)
            scaled_prefix = scaled.at(board)
            self.assertEqual(scaled_prefix.total_mass, original_prefix.total_mass)
            self.assertEqual(scaled_prefix.hand_masses, original_prefix.hand_masses)
            for sb_hand in self.sb:
                for bb_hand in self.bb:
                    self.assertEqual(scaled_prefix.pair_mass(sb_hand, bb_hand),
                                     original_prefix.pair_mass(sb_hand, bb_hand))

    def test_flop_is_canonical_and_turn_river_order_is_preserved(self):
        actual = self.operator.at((13, 7, 9, 22, 30))
        self.assertEqual(actual.board, (7, 9, 13, 22, 30))
        self.assertNotEqual(self.operator.at((7, 9, 13, 22, 30)).board,
                            self.operator.at((7, 9, 13, 30, 22)).board)

    def test_reveal_mass_conserves_at_every_turn_and_river(self):
        flop = (7, 9, 13)
        flop_mass = self.operator.at(flop).total_mass
        turn_masses = {
            card: self.operator.at((*flop, card)).total_mass
            for card in range(52) if card not in flop
        }
        self.assertEqual(len(turn_masses), 49)
        self.assertEqual(sum(turn_masses.values()), flop_mass)
        turn = 14
        turn_mass = self.operator.at((*flop, turn)).total_mass
        river_masses = {
            card: self.operator.at((*flop, turn, card)).total_mass
            for card in range(52) if card not in (*flop, turn)
        }
        self.assertEqual(len(river_masses), 48)
        self.assertEqual(sum(river_masses.values()), turn_mass)

    def test_root_mass_is_conserved_across_all_unordered_flops(self):
        root = self.operator.at(()).total_mass
        all_flops = sum((self.operator.at(flop).total_mass
                         for flop in combinations(range(52), 3)), Fraction(0))
        self.assertEqual(all_flops, root)

    def test_uniform_complete_ranges_match_symmetric_chance_anchors(self):
        complete = {hand: 1.0 for hand in combinations(range(52), 2)}
        operator = FullDeckPrefixMass(complete, complete)
        self.assertEqual(operator.input_dimensions, (1326, 1326))
        self.assertEqual(operator.root_compatible_mass, Fraction(1326 * 1225))
        self.assertEqual(operator.at((0, 1, 2)).total_mass,
                         Fraction(1, math.comb(52, 3)))
        self.assertEqual(operator.at((0, 1, 2, 3)).total_mass,
                         Fraction(1, math.comb(52, 3) * 49))
        self.assertEqual(operator.at((0, 1, 2, 3, 4)).total_mass,
                         Fraction(1, math.comb(52, 3) * 49 * 48))

    def test_full_hand_marginals_include_blocked_zeros_and_are_immutable(self):
        prefix = self.operator.at((0, 7, 9))
        self.assertEqual(prefix.hand_masses[0][(0, 1)], 0)
        self.assertEqual(prefix.hand_masses[1][(0, 2)], 0)
        with self.assertRaises(TypeError):
            prefix.hand_masses[0][(2, 3)] = Fraction(1)

    def test_input_mappings_are_copied_and_tiny_binary64_weights_are_exact(self):
        sb = {(0, 1): 5e-324, (2, 3): 2.0}
        bb = {(4, 5): 1.0, (6, 7): 3.0}
        operator = FullDeckPrefixMass(sb, bb)
        before = operator.at(()).total_mass
        sb[(0, 1)] = 1000.0
        bb.clear()
        self.assertEqual(operator.at(()).total_mass, before)
        self.assertEqual(operator._sb_weights[(0, 1)], Fraction.from_float(5e-324))

    def test_tiny_weight_keeps_exact_positive_hand_and_pair_masses(self):
        tiny = 5e-324
        tiny_fraction = Fraction.from_float(tiny)
        operator = FullDeckPrefixMass(
            {(0, 1): tiny, (2, 3): 1.0},
            {(4, 5): 1.0, (6, 7): 1.0},
        )
        prefix = operator.at(())
        self.assertEqual(operator.root_compatible_mass, 2 * (1 + tiny_fraction))
        self.assertEqual(prefix.hand_masses[0][(0, 1)],
                         tiny_fraction / (1 + tiny_fraction))
        self.assertEqual(prefix.pair_mass((0, 1), (4, 5)),
                         tiny_fraction / (2 * (1 + tiny_fraction)))
        self.assertGreater(prefix.hand_masses[0][(0, 1)], 0)
        self.assertGreater(prefix.pair_mass((0, 1), (4, 5)), 0)

    def test_board_can_remove_all_support_without_local_renormalization(self):
        sb = {(0, 1): 1.0}
        bb = {(2, 3): 1.0}
        result = FullDeckPrefixMass(sb, bb).at((0, 2, 4))
        self.assertEqual(result.total_mass, 0)
        self.assertEqual(result.pair_mass((0, 1), (2, 3)), 0)

    def test_invalid_weights_hands_and_empty_compatible_roots_are_rejected(self):
        for bad in (0, -1.0, float("nan"), float("inf"), True):
            with self.subTest(weight=bad):
                with self.assertRaises((TypeError, ValueError)):
                    FullDeckPrefixMass({(0, 1): bad}, {(2, 3): 1.0})
        for hand in ((0, 0), (1, 0), (0, 52), (False, 1)):
            with self.subTest(hand=hand):
                with self.assertRaises(ValueError):
                    FullDeckPrefixMass({hand: 1.0}, {(2, 3): 1.0})
        with self.assertRaises(ValueError):
            FullDeckPrefixMass({(0, 1): 1.0}, {(0, 1): 2.0})
        with self.assertRaises(ValueError):
            FullDeckPrefixMass({}, {(0, 1): 1.0})
        with self.assertRaises(ValueError):
            self.operator.at(()).pair_mass([0, 1], (2, 3))

    def test_invalid_boards_are_rejected(self):
        for board in ((0, 1), (0, 1, 2, 3, 4, 5), (0, 1, 1),
                      (0, 1, 52), (False, 1, 2), "abc"):
            with self.subTest(board=board):
                with self.assertRaises((TypeError, ValueError)):
                    self.operator.at(board)


if __name__ == "__main__":
    unittest.main()
