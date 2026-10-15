"""Immutable cached fixed-flop equity preparation and reuse regressions."""
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
import math
import unittest
from unittest.mock import patch

from scripts.flop_checkdown_validation import prepare_oracle, replay
from pokerlab import flop_checkdown_equity as equity
from pokerlab import flop_checkdown_solver as solver
from pokerlab import flop_checkdown_worlds as worlds

BOARD = "2c3c4d"
OOP_RANGE = "AsAd:0.5,QsQd:0.25,2c2d:1"
IP_RANGE = "KsKd:1,AhKh:0.5,QsQd:0.75"
ANCHOR = {"pot": 2, "effective_stack": 1, "bet_sizes": [0.5],
          "raise_sizes": [], "max_raises": 0, "include_all_in": True}


def _rows_by_hands(table):
    result = {}
    for (oop_index, ip_index, prior), counts in zip(table.pairs, table.counts):
        key = ("".join(table.hands[0][oop_index]),
               "".join(table.hands[1][ip_index]))
        result[key] = (prior, counts)
    return result


class FlopCheckdownEquityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One five-pair table includes the AA-vs-KK anchor and a blocked QQ-vs-QQ pair.
        cls.table = equity.prepare_flop_checkdown_equities(BOARD, OOP_RANGE, IP_RANGE)

    def test_preparation_matches_known_anchor_and_build_covers_pair_categories(self):
        self.assertIsNone(self.table.validate())
        rows = _rows_by_hands(self.table)
        self.assertEqual(rows[("AdAs", "KdKs")], (Fraction(1, 3), (1782, 48, 150)))
        self.assertNotIn(("QdQs", "QdQs"), rows)
        self.assertEqual(len(rows), 5)

        built_worlds, count_rows = self.table.build()
        self.assertEqual(len(count_rows), len(rows))
        self.assertEqual(sum(row["wins"] + row["ties"] + row["losses"]
                             for row in count_rows), 5 * 1980)
        masses_by_pair = {}
        for oop_index, ip_index, mass, sign in built_worlds:
            self.assertIn(sign, (-1, 0, 1))
            masses_by_pair.setdefault((oop_index, ip_index), []).append(mass)
        self.assertEqual(set(masses_by_pair), {(i, j) for i, j, _ in self.table.pairs})
        self.assertTrue(math.isclose(math.fsum(mass for row in masses_by_pair.values()
                                                for mass in row), 1.0,
                                     rel_tol=0, abs_tol=1e-15))

    def test_table_is_deeply_immutable_and_budget_is_a_fresh_flat_mapping(self):
        with self.assertRaises(FrozenInstanceError):
            self.table.board = ("2c", "3c", "5d")
        self.assertIs(type(self.table.hands), tuple)
        self.assertTrue(all(type(hands) is tuple and all(type(hand) is tuple
                                                         for hand in hands)
                            for hands in self.table.hands))
        self.assertIs(type(self.table.pairs), tuple)
        self.assertIs(type(self.table.counts), tuple)
        self.assertIs(type(self.table._budget_items), tuple)
        budget = self.table.budget
        self.assertIs(type(budget), dict)
        budget["compatible_pairs"] = -1
        self.assertEqual(self.table.budget["compatible_pairs"], 5)

    def test_validate_rejects_structural_forgery_and_wrong_types(self):
        broken_counts = list(self.table.counts)
        wins, ties, losses = broken_counts[0]
        broken_counts[0] = (wins + 2, ties, losses)
        malformed = replace(self.table, counts=tuple(broken_counts))
        with self.assertRaisesRegex(ValueError, "counts totaling 1,980"):
            malformed.validate()

        with self.assertRaisesRegex(ValueError, "coverage is incomplete"):
            replace(self.table, pairs=self.table.pairs[:-1]).validate()

        bad_budget = list(self.table._budget_items)
        bad_budget[0] = ("candidate_pairs", -1)
        with self.assertRaisesRegex(ValueError, "budget metadata"):
            replace(self.table, _budget_items=tuple(bad_budget)).validate()

        with self.assertRaisesRegex(ValueError, "canonical distinct cards"):
            replace(self.table, board=("2c", "2c", "4d")).validate()
        with self.assertRaises(TypeError):
            equity.reweight_flop_checkdown_equities(object(), OOP_RANGE, IP_RANGE)
        with self.assertRaises(TypeError):
            solver.solve_prepared_flop_checkdown(object(), config=ANCHOR, iterations=10)

    def test_global_fraction_reweighting_reorders_and_subsets_by_hand_identity(self):
        # Compatible products are 1/8, 1/16, 1/4, 1/8, 1/4; QQ-vs-QQ collides.
        changed_oop = "AsAd:0.25,QsQd:0.5"
        changed_ip = "KsKd:0.5,AhKh:0.25,QsQd:1"
        changed = equity.reweight_flop_checkdown_equities(
            self.table, changed_oop, changed_ip)
        changed_rows = _rows_by_hands(changed)
        expected = {
            ("AdAs", "KdKs"): Fraction(2, 13),
            ("AdAs", "AhKh"): Fraction(1, 13),
            ("AdAs", "QdQs"): Fraction(4, 13),
            ("QdQs", "KdKs"): Fraction(4, 13),
            ("QdQs", "AhKh"): Fraction(2, 13),
        }
        self.assertEqual({key: row[0] for key, row in changed_rows.items()}, expected)
        self.assertEqual(sum((row[0] for row in changed_rows.values()), Fraction()), 1)
        oop_marginals = {hand: sum((prior for (oop, _), (prior, _) in changed_rows.items() if oop == hand), Fraction())
                          for hand in ("AdAs", "QdQs")}
        ip_marginals = {hand: sum((prior for (_, ip), (prior, _) in changed_rows.items() if ip == hand), Fraction())
                         for hand in ("KdKs", "AhKh", "QdQs")}
        self.assertEqual(oop_marginals, {"AdAs": Fraction(7, 13), "QdQs": Fraction(6, 13)})
        self.assertEqual(ip_marginals, {"KdKs": Fraction(6, 13), "AhKh": Fraction(3, 13), "QdQs": Fraction(4, 13)})
        self.assertTrue(all(changed_rows[key][1] == _rows_by_hands(self.table)[key][1]
                            for key in expected))

        reordered = equity.reweight_flop_checkdown_equities(
            self.table, "QsQd:0.5,AsAd:0.25", "QsQd:1,AhKh:0.25,KsKd:0.5")
        self.assertEqual(_rows_by_hands(reordered), changed_rows)

        subset = equity.reweight_flop_checkdown_equities(self.table, "AsAd:0.5", "KsKd:1")
        self.assertEqual(_rows_by_hands(subset), {
            ("AdAs", "KdKs"): (Fraction(1), (1782, 48, 150))})

    def test_dead_new_hand_is_ignored_but_uncovered_compatible_hand_rejects(self):
        # 2c2d is excluded by the flop before source-pair coverage is required.
        dead_added = equity.reweight_flop_checkdown_equities(
            self.table, "AsAd:0.5,2c2d:1", "KsKd:1")
        self.assertEqual(tuple(_rows_by_hands(dead_added)), (("AdAs", "KdKs"),))

        with self.assertRaisesRegex(ValueError, "not covered by the source table"): 
            equity.reweight_flop_checkdown_equities(self.table, "QhQd:1", "KsKd:1")

    def test_reweight_and_prepared_solve_do_not_rank_or_enumerate_boards(self):
        with patch.object(worlds, "rank_hand", side_effect=AssertionError("rank called")) as rank, \
             patch.object(worlds, "combinations", side_effect=AssertionError("boards enumerated")) as boards, \
             patch.object(worlds.FlopCheckdownPlan, "build", side_effect=AssertionError("source rebuilt")) as build, \
             patch.object(solver, "prepare_flop_worlds", side_effect=AssertionError("fresh plan requested")) as prepare:
            subset = equity.reweight_flop_checkdown_equities(
                self.table, "AsAd:0.5", "KsKd:1")
            prepared_result = solver.solve_prepared_flop_checkdown(
                subset, config=ANCHOR, iterations=10)
            rank.assert_not_called()
            boards.assert_not_called()
            build.assert_not_called()
            prepare.assert_not_called()

        fresh_result = solver.solve_flop_checkdown(
            BOARD, "AsAd:0.5", "KsKd:1", config=ANCHOR, iterations=10)
        self.assertEqual(prepared_result.pop("equity_preparation"), {
            "mode": "prepared-counts", "current_rank_calls": 0,
            "current_unordered_board_evaluations": 0, "source_inclusive_admission": True,
            "validation": "Structural consistency only; supplied counts require trusted provenance.",
        })
        self.assertEqual(prepared_result, fresh_result)
        oracle = prepare_oracle(BOARD, "AsAd:0.5", "KsKd:1", ANCHOR)
        replay(prepared_result, oracle)

    def test_table_caps_are_checked_before_ranking(self):
        with patch.object(worlds, "MAX_COMPATIBLE_PAIRS", 4), \
             patch.object(worlds, "rank_hand", side_effect=AssertionError("rank called")) as rank:
            with self.assertRaisesRegex(ValueError, "compatible pair limit"):
                equity.prepare_flop_checkdown_equities(BOARD, OOP_RANGE, IP_RANGE)
            rank.assert_not_called()


    def test_boolean_budget_and_underflowing_category_mass_reject_before_tree(self):
        # A one-pair structurally valid table makes bool == 1 a relevant forgery.
        one_pair_budget = self.table.budget
        one_pair_budget.update(candidate_pairs=1, compatible_pairs=1,
                               physical_worlds=1980, unordered_boards=990,
                               rank_calls_upper_bound=1980, grouped_rows_upper_bound=3)
        one_pair = replace(
            self.table,
            hands=((self.table.hands[0][0],), (self.table.hands[1][0],)),
            pairs=((0, 0, Fraction(1)),), counts=(self.table.counts[0],),
            _budget_items=tuple(one_pair_budget.items()),
        )
        self.assertIsNone(one_pair.validate())
        bool_budget = one_pair.budget
        bool_budget["candidate_pairs"] = True
        with self.assertRaises(ValueError):
            replace(one_pair, _budget_items=tuple(bool_budget.items())).validate()

        tiny = Fraction(1, 2 ** 1074)
        priors = (tiny, tiny, tiny, tiny, Fraction(1) - 4 * tiny)
        underflow = replace(
            self.table,
            pairs=tuple((i, j, prior)
                        for (i, j, _), prior in zip(self.table.pairs, priors)),
        )
        with patch.object(solver, "_build_tree",
                          side_effect=AssertionError("tree built before validation")) as tree:
            with self.assertRaises(ValueError):
                solver.solve_prepared_flop_checkdown(underflow, config=ANCHOR, iterations=10)
            tree.assert_not_called()

    def test_reweight_and_prepared_solver_require_exact_table_type(self):
        class Derived(equity.FlopCheckdownEquities):
            pass

        derived = Derived(self.table.board, self.table.hands, self.table.pairs,
                          self.table.counts, self.table._budget_items)
        with self.assertRaises(TypeError):
            equity.reweight_flop_checkdown_equities(derived, OOP_RANGE, IP_RANGE)
        with self.assertRaises(TypeError):
            solver.solve_prepared_flop_checkdown(derived, config=ANCHOR, iterations=10)
if __name__ == "__main__":
    unittest.main()
