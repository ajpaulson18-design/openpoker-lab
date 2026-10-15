"""Bounded tests for exact full-board suit-orbit count reuse."""
from dataclasses import replace
from fractions import Fraction
from itertools import permutations
import unittest
from unittest.mock import patch

from pokerlab import preflop_full_board_equity as equity
from pokerlab.cards import SUITS
from pokerlab.preflop_suit_equity import (
    preflop_suit_remap_provenance,
    remap_preflop_equities_by_suit,
)


BOARDS = (
    ("2c", "3c", "4c", "5c", "6c"),
    ("2d", "3d", "4d", "5d", "6d"),
    ("2h", "3h", "4h", "5h", "6h"),
    ("2s", "3s", "4s", "5s", "6s"),
)
RANKS = (3, 1, 2, 2, 1, 0, 3, 2)  # two wins, one tie, one loss


def build_table(sb_range, bb_range):
    with patch.object(equity, "BOARDS_PER_PAIR", len(BOARDS)):
        plan = equity.plan_preflop_equities(sb_range, bb_range)
        rank_values = RANKS * len(plan.pairs)
        with patch.object(equity, "_board_combinations",
                          side_effect=lambda _: iter(BOARDS)), \
             patch.object(equity, "rank_hand", side_effect=rank_values):
            return plan.build()


def map_hand(hand, permutation):
    suit_map = dict(zip(SUITS, permutation))
    return "".join(sorted(card[0] + suit_map[card[1]] for card in hand))


def map_range(expression, permutation):
    pieces = []
    for item in expression.split(","):
        hand, separator, weight = item.partition(":")
        mapped = map_hand((hand[:2], hand[2:]), permutation)
        pieces.append(mapped + (separator + weight if separator else ""))
    return ",".join(pieces)


def table_with_counts(table, counts):
    worlds = []
    for (sb_index, bb_index, prior), (wins, ties, losses) in zip(table.pairs, counts):
        for sign, count in zip((-1, 0, 1), (losses, ties, wins)):
            if count:
                worlds.append((sb_index, bb_index,
                               float(prior * Fraction(count, equity.BOARDS_PER_PAIR)), sign))
    return replace(table, counts=tuple(counts), worlds=tuple(worlds))


class PreflopSuitEquityTests(unittest.TestCase):
    def setUp(self):
        self.sb = "AsKd"
        self.bb = "QcJh"
        with patch.object(equity, "BOARDS_PER_PAIR", len(BOARDS)):
            self.source = build_table(self.sb, self.bb)

    def test_every_joint_suit_image_reuses_counts_and_provenance_is_bijective(self):
        representatives = (
            ("AsKd", "QcJh"),  # four distinct suits across four ranks
            ("AsKs", "QdJh"),  # suited hand plus an offsuit hand
            ("AsAd", "KsKd"),  # pocket pairs sharing the same suit pattern
            ("AsKh", "AhKc"),  # repeated ranks with a symmetric suit pattern
        )
        for source_sb, source_bb in representatives:
            with self.subTest(source=(source_sb, source_bb)), \
                 patch.object(equity, "BOARDS_PER_PAIR", len(BOARDS)):
                source = build_table(source_sb, source_bb)
                source_before = source
                for permutation in permutations(SUITS):
                    target_sb = map_range(source_sb, permutation)
                    target_bb = map_range(source_bb, permutation)
                    with self.subTest(permutation=permutation), \
                         patch.object(equity, "rank_hand",
                                      side_effect=AssertionError("ranked during remap")), \
                         patch.object(equity, "_board_combinations",
                                      side_effect=AssertionError("enumerated during remap")):
                        result = remap_preflop_equities_by_suit(
                            source, target_sb, target_bb)
                        mapping_rows = preflop_suit_remap_provenance(
                            source, target_sb, target_bb)
                    self.assertEqual(result.counts, source.counts)
                    self.assertEqual(len(mapping_rows), 1)
                    row = mapping_rows[0]
                    suit_map = row["suit_permutation"]
                    self.assertEqual(set(suit_map), set(SUITS))
                    self.assertEqual(set(suit_map.values()), set(SUITS))
                    permutation_tuple = tuple(suit_map[suit] for suit in SUITS)
                    self.assertEqual(map_hand(
                        (row["source_sb_hand"][:2], row["source_sb_hand"][2:]),
                        permutation_tuple), row["target_sb_hand"])
                    self.assertEqual(map_hand(
                        (row["source_bb_hand"][:2], row["source_bb_hand"][2:]),
                        permutation_tuple), row["target_bb_hand"])
                self.assertEqual(source, source_before)
    def test_changed_weights_keep_exact_global_collision_conditioned_priors(self):
        sb_range = "AsAd:1,QsQd:0.5"
        bb_range = "AsKh:0.25,KsKd:1"
        with patch.object(equity, "BOARDS_PER_PAIR", len(BOARDS)):
            source = build_table(sb_range, bb_range)
            before = source
            permutation = ("h", "s", "c", "d")
            target_sb = map_range(sb_range, permutation).replace(':0.5', ':0.0625')
            target_bb = map_range(bb_range, permutation)
            expected = equity.plan_preflop_equities(target_sb, target_bb)
            with patch.object(equity, "rank_hand",
                              side_effect=AssertionError("ranked during remap")), \
                 patch.object(equity, "_board_combinations",
                              side_effect=AssertionError("enumerated during remap")):
                result = remap_preflop_equities_by_suit(source, target_sb, target_bb)
        self.assertEqual(len(result.pairs), 3)
        self.assertEqual(result.pairs, expected.pairs)
        self.assertEqual(result.counts, source.counts)
        self.assertEqual(source, before)
        self.assertEqual(sum((prior for _, _, prior in result.pairs), Fraction()), Fraction(1))
        self.assertEqual(tuple(prior for _, _, prior in result.pairs),
                         (Fraction(64, 69), Fraction(1, 69), Fraction(4, 69)))

    def test_fully_blocked_added_hand_is_allowed(self):
        with patch.object(equity, "BOARDS_PER_PAIR", len(BOARDS)):
            source = build_table("AsAd", "KcKd")
            result = remap_preflop_equities_by_suit(source, "AsAd,KcKd", "KcKd")
        self.assertEqual(len(result.hands[0]), 2)
        self.assertEqual(len(result.pairs), 1)
        self.assertEqual(result.counts, source.counts)

    def test_different_relative_suit_pattern_and_role_reversal_are_uncovered(self):
        cases = (
            ("AsKs", "QdJh"),  # changes a four-distinct-suit pattern to a shared suit
            (self.bb, self.sb),  # canonical key preserves SB/BB roles
        )
        with patch.object(equity, "BOARDS_PER_PAIR", len(BOARDS)), \
             patch.object(equity, "rank_hand",
                          side_effect=AssertionError("ranked during remap")), \
             patch.object(equity, "_board_combinations",
                          side_effect=AssertionError("enumerated during remap")):
            for target_sb, target_bb in cases:
                with self.subTest(target=(target_sb, target_bb)), self.assertRaisesRegex(
                        ValueError, "suit orbit is not covered"):
                    remap_preflop_equities_by_suit(self.source, target_sb, target_bb)

    def test_conflicting_counts_inside_a_source_orbit_fail_closed(self):
        sb_range = "AsKd,AcKh"
        bb_range = "QcJh,QsJd"
        with patch.object(equity, "BOARDS_PER_PAIR", len(BOARDS)):
            source = build_table(sb_range, bb_range)
            source_pair = (tuple(sorted(("As", "Kd"))),
                           tuple(sorted(("Qc", "Jh"))))
            image_pair = (tuple(sorted(("Ac", "Kh"))),
                          tuple(sorted(("Qs", "Jd"))))
            orbit_indices = [
                i for i, (sb_index, bb_index, _) in enumerate(source.pairs)
                if (source.hands[0][sb_index], source.hands[1][bb_index])
                in (source_pair, image_pair)
            ]
            self.assertEqual(len(orbit_indices), 2)
            counts = list(source.counts)
            index = orbit_indices[1]
            counts[index] = (counts[index][0] + 1, counts[index][1] - 1,
                             counts[index][2])
            forged = table_with_counts(source, counts)
            forged.validate()
            with patch.object(equity, "rank_hand",
                              side_effect=AssertionError("ranked during remap")), \
                 patch.object(equity, "_board_combinations",
                              side_effect=AssertionError("enumerated during remap")), \
                 self.assertRaisesRegex(ValueError, "inconsistent.*suit orbit"):
                remap_preflop_equities_by_suit(forged, sb_range, bb_range)
    def test_uncovered_orbit_fails_before_any_output_or_board_work(self):
        with patch.object(equity, "BOARDS_PER_PAIR", len(BOARDS)), \
             patch.object(equity, "rank_hand",
                          side_effect=AssertionError("ranked during remap")), \
             patch.object(equity, "_board_combinations",
                          side_effect=AssertionError("enumerated during remap")), \
             self.assertRaisesRegex(ValueError, "suit orbit is not covered"):
            remap_preflop_equities_by_suit(self.source, "AsKs", "QdJh")

    def test_existing_plan_caps_apply_before_ranking(self):
        with patch.object(equity, "BOARDS_PER_PAIR", len(BOARDS)), \
             patch.object(equity, "rank_hand",
                          side_effect=AssertionError("ranked during remap")), \
             self.assertRaisesRegex(ValueError, "compatible pair limit"):
            remap_preflop_equities_by_suit(
                self.source, "AsAd,KsKd,QsQd", "TsTh,JsJh")

if __name__ == "__main__":
    unittest.main()
