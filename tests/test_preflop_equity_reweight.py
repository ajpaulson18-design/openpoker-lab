"""Synthetic tests for reweighting covered full-board equity counts."""
from fractions import Fraction
import unittest
from unittest.mock import patch

from pokerlab import preflop_full_board_equity as equity


SB_RANGE = "AsAd:1,QsQd:0.5"
BB_RANGE = "AsKh:0.25,KsKd:1"
TOY_BOARD_COUNT = 6


def synthetic_table(counts=((3, 1, 2), (2, 1, 3), (1, 2, 3))):
    """Build structurally valid, explicitly synthetic categorical counts."""
    plan = equity.plan_preflop_equities(SB_RANGE, BB_RANGE)
    rows = []
    for (sb_index, bb_index, prior), count_row in zip(plan.pairs, counts):
        wins, ties, losses = count_row
        for sign, count in zip(equity._SIGNS, (losses, ties, wins)):
            if count:
                mass = prior * Fraction(count, equity.BOARDS_PER_PAIR)
                rows.append((sb_index, bb_index,
                             equity._as_positive_float(mass, "categorical mass"),
                             sign))
    table = equity.FullBoardEquities(
        hands=plan.hands,
        pairs=plan.pairs,
        counts=counts,
        worlds=tuple(rows),
        _budget_items=plan._budget_items,
    )
    table.validate()
    return table


def count_map(table):
    return {
        (table.hands[0][i], table.hands[1][j]): count_row
        for (i, j, _), count_row in zip(table.pairs, table.counts)
    }


def pair_prior_map(table):
    return {
        (table.hands[0][i], table.hands[1][j]): prior
        for i, j, prior in table.pairs
    }


class ReweightPreflopEquitiesTests(unittest.TestCase):
    def setUp(self):
        self.board_count_patch = patch.object(equity, "BOARDS_PER_PAIR", TOY_BOARD_COUNT)
        self.board_count_patch.start()
        self.addCleanup(self.board_count_patch.stop)
        self.table = synthetic_table()

    def _reweight_without_board_work(self, *args):
        with patch.object(equity, "rank_hand", side_effect=AssertionError("ranked boards")) as rank, \
             patch.object(equity, "_board_combinations", side_effect=AssertionError("iterated boards")) as boards:
            result = equity.reweight_preflop_equities(*args)
        rank.assert_not_called()
        boards.assert_not_called()
        return result

    def test_same_weights_and_exact_power_of_two_scaling_preserve_table(self):
        same = self._reweight_without_board_work(self.table, SB_RANGE, BB_RANGE)
        scaled = self._reweight_without_board_work(
            self.table, "AsAd:0.5,QsQd:0.25", "AsKh:0.0625,KsKd:0.25"
        )
        self.assertEqual(same, self.table)
        self.assertEqual(scaled.pairs, self.table.pairs)
        self.assertEqual(scaled.counts, self.table.counts)
        self.assertEqual(scaled.worlds, self.table.worlds)

    def test_nonuniform_reweight_and_reordered_ranges_remap_counts(self):
        result = self._reweight_without_board_work(
            self.table, "QsQd:0.75,AsAd:0.25", "KsKd:0.5,AsKh:1"
        )
        self.assertEqual(pair_prior_map(result), {
            (self.table.hands[0][0], self.table.hands[1][1]): Fraction(1, 10),
            (self.table.hands[0][1], self.table.hands[1][0]): Fraction(3, 5),
            (self.table.hands[0][1], self.table.hands[1][1]): Fraction(3, 10),
        })
        self.assertEqual(count_map(result), count_map(self.table))
        self.assertEqual(sum((prior for _, _, prior in result.pairs), Fraction()), 1)

    def test_subset_and_new_fully_blocked_hand_reuse_only_covered_pairs(self):
        result = self._reweight_without_board_work(
            self.table, "AsKs:0.9,AsAd:0.1", "KsKd:1,AsKh:0.25"
        )
        self.assertEqual(len(result.hands[0]), 2)
        self.assertIn(tuple(sorted(("As", "Ks"))), result.hands[0])
        self.assertEqual(len(result.hands[1]), 2)
        self.assertEqual(len(result.pairs), 1)
        self.assertEqual(result.pairs[0][2], Fraction(1))
        pair = (tuple(sorted(("Ad", "As"))), tuple(sorted(("Kd", "Ks"))))
        self.assertEqual(count_map(result), {pair: count_map(self.table)[pair]})
        self.assertEqual(result.budget["candidate_pairs"], 4)
        self.assertEqual(result.budget["compatible_pairs"], 1)
        result.validate()

    def test_new_compatible_pair_is_rejected_without_ranking(self):
        with patch.object(equity, "rank_hand", side_effect=AssertionError("ranked boards")) as rank, \
             patch.object(equity, "_board_combinations", side_effect=AssertionError("iterated boards")) as boards:
            with self.assertRaisesRegex(ValueError, "not covered by the source table"):
                equity.reweight_preflop_equities(
                    self.table, "JcJd:1,AsAd:1", BB_RANGE
                )
        rank.assert_not_called()
        boards.assert_not_called()

    def test_no_compatible_pair_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no compatible private-hand pair"):
            equity.reweight_preflop_equities(self.table, "AsAd", "AsKh")

    def test_subnormal_products_normalize_exactly_without_raw_float_underflow(self):
        minimum = "5e-324"
        result = self._reweight_without_board_work(
            self.table,
            f"AsAd:{minimum},QsQd:{minimum}",
            f"AsKh:{minimum},KsKd:{minimum}",
        )
        self.assertEqual(tuple(prior for _, _, prior in result.pairs),
                         (Fraction(1, 3), Fraction(1, 3), Fraction(1, 3)))
        self.assertEqual(count_map(result), count_map(self.table))

    def test_positive_category_mass_underflow_is_rejected(self):
        # AA-vs-KK has a single tie board in this synthetic six-board count.
        source = synthetic_table(counts=((2, 1, 3), (2, 2, 2), (1, 2, 3)))
        with self.assertRaisesRegex(ValueError, "categorical mass underflows"):
            self._reweight_without_board_work(
                source, "AsAd:5e-324,QsQd:1", "AsKh:0.5,KsKd:1"
            )

    def test_source_table_is_unchanged(self):
        before = self.table
        self._reweight_without_board_work(
            self.table, "QsQd:0.75,AsAd:0.25", "KsKd:0.5,AsKh:1"
        )
        self.assertEqual(self.table, before)


if __name__ == "__main__":
    unittest.main()
