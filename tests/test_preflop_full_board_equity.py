"""Bounded tests for exact full-board preflop equity preparation."""
import math
import unittest
from fractions import Fraction
from unittest.mock import patch

from pokerlab import preflop_full_board_equity as equity


class FullBoardEquityPlanTests(unittest.TestCase):
    def test_exact_weighted_pair_priors_and_single_private_collision(self):
        plan = equity.plan_preflop_equities(
            "AsAd:0.5,QsQd:0.25",
            "AsKh:0.75,KsKd:0.5",
        )
        self.assertEqual(plan.budget["candidate_pairs"], 4)
        self.assertEqual(plan.budget["compatible_pairs"], 3)
        self.assertEqual(
            [(i, j, p) for i, j, p in plan.pairs],
            [(0, 1, Fraction(4, 9)),
             (1, 0, Fraction(1, 3)),
             (1, 1, Fraction(2, 9))],
        )
        self.assertEqual(plan.hands[0][0], ("Ad", "As"))
        self.assertEqual(plan.hands[1][0], ("As", "Kh"))
        self.assertEqual(plan.budget["boards_per_pair"], math.comb(48, 5))
        self.assertEqual(plan.budget["physical_worlds_upper_bound"],
                         3 * math.comb(48, 5))
        self.assertEqual(plan.budget["rank_calls_upper_bound"],
                         6 * math.comb(48, 5))

    def test_subnormal_weight_products_normalize_without_raw_underflow(self):
        plan = equity.plan_preflop_equities("AsAd:5e-324", "KsKd:5e-324")
        self.assertEqual(plan.pairs, ((0, 0, Fraction(1, 1)),))

    def test_pair_probability_underflow_rejected_before_rank_work(self):
        with patch.object(equity, "rank_hand") as rank:
            with self.assertRaisesRegex(ValueError, "pair probability underflows"):
                equity.plan_preflop_equities(
                    "AsAd:5e-324,QcQd:1", "KsKd:5e-324,AhKh:1"
                )
        rank.assert_not_called()

    def test_candidate_and_compatible_pair_caps_precede_any_rank_work(self):
        with patch.object(equity, "rank_hand") as rank:
            with patch.object(equity, "MAX_CANDIDATE_PAIRS", 3):
                with self.assertRaisesRegex(ValueError, "candidate pair limit"):
                    equity.plan_preflop_equities("AsAd,QsQd", "KsKd,JhJc")
            with patch.object(equity, "MAX_COMPATIBLE_PAIRS", 2):
                with self.assertRaisesRegex(ValueError, "compatible pair limit"):
                    equity.plan_preflop_equities("AsAd,QsQd", "KsKd,JhJc")
        rank.assert_not_called()

    def test_toy_board_count_produces_ordered_categorical_rows_and_progress(self):
        toy_boards = (("2c", "3c", "4c", "5c", "6c"),
                      ("2d", "3d", "4d", "5d", "6d"),
                      ("2h", "3h", "4h", "5h", "6h"))
        progress = []
        with patch.object(equity, "BOARDS_PER_PAIR", 3), \
             patch.object(equity, "_PROGRESS_EVERY", 1), \
             patch.object(equity, "_board_combinations", return_value=iter(toy_boards)), \
             patch.object(equity, "rank_hand", side_effect=(2, 1, 1, 1, 0, 1)) as rank:
            plan = equity.plan_preflop_equities("AsAd", "KsKd")
            result = plan.build(progress=lambda *args: progress.append(args))
        self.assertEqual(rank.call_count, 6)
        self.assertEqual(result.counts, ((1, 1, 1),))
        self.assertEqual(result.worlds, ((0, 0, 1 / 3, -1),
                                         (0, 0, 1 / 3, 0),
                                         (0, 0, 1 / 3, 1)))
        self.assertEqual(progress, [(1, 0, 3), (1, 1, 3), (1, 2, 3), (1, 3, 3)])

    def test_short_and_long_toy_enumerations_fail_closed(self):
        with patch.object(equity, "BOARDS_PER_PAIR", 3), \
             patch.object(equity, "_board_combinations", return_value=iter((("2c", "3c", "4c", "5c", "6c"),))):
            with self.assertRaisesRegex(ValueError, "produced 1; expected 3"):
                equity.plan_preflop_equities("AsAd", "KsKd").build()

        too_many = iter((("2c", "3c", "4c", "5c", "6c"), ("2d", "3d", "4d", "5d", "6d"), ("2h", "3h", "4h", "5h", "6h"), ("2s", "3s", "4s", "5s", "6s")))
        with patch.object(equity, "BOARDS_PER_PAIR", 3), \
             patch.object(equity, "_board_combinations", return_value=too_many), \
             patch.object(equity, "rank_hand", return_value=1):
            with self.assertRaisesRegex(ValueError, "exceeded its admitted count"):
                equity.plan_preflop_equities("AsAd", "KsKd").build()

    def test_positive_categorical_mass_underflow_is_rejected(self):
        boards = (("2c", "3c", "4c", "5c", "6c"), ("2d", "3d", "4d", "5d", "6d"))
        ranks = iter((2, 1, 1, 2))
        with patch.object(equity, "BOARDS_PER_PAIR", 2), \
             patch.object(equity, "_board_combinations", side_effect=lambda _: iter(boards)), \
             patch.object(equity, "rank_hand", side_effect=lambda _: next(ranks)):
            plan = equity.plan_preflop_equities("AsAd:5e-324,QcQd:1", "KsKd:1")
            with self.assertRaisesRegex(ValueError, "categorical mass underflows"):
                plan.build()

    def test_progress_callback_is_validated_before_board_iteration(self):
        plan = equity.plan_preflop_equities("AsAd", "KsKd")
        with patch.object(equity, "_board_combinations") as boards:
            with self.assertRaisesRegex(TypeError, "progress must be callable"):
                plan.build(progress=True)
        boards.assert_not_called()


    def test_budget_is_copied_and_public_table_rejects_extra_rows(self):
        plan = equity.plan_preflop_equities("AsAd", "KsKd")
        budget = plan.budget
        budget["limits"]["candidate_pairs"] = 0
        self.assertEqual(plan.budget["limits"]["candidate_pairs"],
                         equity.MAX_CANDIDATE_PAIRS)

        toy_boards = (("2c", "3c", "4c", "5c", "6c"),)
        with patch.object(equity, "BOARDS_PER_PAIR", 1), \
             patch.object(equity, "_board_combinations", return_value=iter(toy_boards)), \
             patch.object(equity, "rank_hand", side_effect=(2, 1)):
            plan = equity.plan_preflop_equities("AsAd", "KsKd")
            result = plan.build()
            forged = type(result)(
                hands=result.hands,
                pairs=result.pairs,
                counts=result.counts,
                worlds=result.worlds + (result.worlds[0],),
                _budget_items=result._budget_items,
            )
            with self.assertRaisesRegex(ValueError, "Categorical rows differ"):
                forged.validate()

    def test_forged_plan_is_rejected_before_board_iterator(self):
        plan = equity.plan_preflop_equities("AsAd", "KsKd")
        forged = type(plan)(
            hands=plan.hands,
            pairs=plan.pairs + plan.pairs,
            _budget_items=plan._budget_items,
        )
        with patch.object(equity, "_board_combinations") as boards:
            with self.assertRaisesRegex(ValueError, "duplicate private pairs"):
                forged.build()
        boards.assert_not_called()

    def test_hand_count_and_candidate_product_caps_precede_hand_scans(self):
        from dataclasses import replace

        plan = equity.plan_preflop_equities("AsAd", "KsKd")
        too_many_hands = replace(
            plan, hands=(tuple([None] * (equity.MAX_HANDS_PER_PLAYER + 1)), plan.hands[1])
        )
        with self.assertRaisesRegex(ValueError, "1,326-hand cap"):
            too_many_hands.validate()

        too_many_candidates = replace(
            plan, hands=(tuple([None] * 1_326), tuple([None] * 4))
        )
        with self.assertRaisesRegex(ValueError, "candidate pair limit"):
            too_many_candidates.validate()

    def test_reversed_hand_and_boolean_world_aliases_are_rejected(self):
        from dataclasses import replace

        plan = equity.plan_preflop_equities("AsAd", "KsKd")
        reversed_hand = replace(plan, hands=((("As", "Ad"),), plan.hands[1]))
        with self.assertRaisesRegex(ValueError, "invalid private-hand"):
            reversed_hand.validate()

        toy_board = ("2c", "3c", "4c", "5c", "6c")
        with patch.object(equity, "BOARDS_PER_PAIR", 1), \
             patch.object(equity, "_board_combinations", return_value=iter((toy_board,))), \
             patch.object(equity, "rank_hand", side_effect=(2, 1)):
            plan = equity.plan_preflop_equities("AsAd", "KsKd")
            result = plan.build()
            for forged_row in ((True, 0, 1.0, 1), (0, 0, True, 1), (0, 0, 1.0, True)):
                forged = replace(result, worlds=(forged_row,))
                with self.assertRaisesRegex(ValueError, "bounded integer indices/signs"):
                    forged.validate()

    def test_result_candidate_cap_precedes_hand_scans(self):
        from dataclasses import replace

        toy_board = ("2c", "3c", "4c", "5c", "6c")
        with patch.object(equity, "BOARDS_PER_PAIR", 1), \
             patch.object(equity, "_board_combinations", return_value=iter((toy_board,))), \
             patch.object(equity, "rank_hand", side_effect=(2, 1)):
            result = equity.plan_preflop_equities("AsAd", "KsKd").build()
            forged = replace(
                result, hands=(tuple([None] * 1_326), tuple([None] * 4))
            )
            with self.assertRaisesRegex(ValueError, "candidate pair limit"):
                forged.validate()

if __name__ == "__main__":
    unittest.main()
