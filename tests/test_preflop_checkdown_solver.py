"""Independent regression coverage for hidden full-board preflop checkdown."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
from itertools import combinations
import unittest
from unittest.mock import patch

from pokerlab import preflop_checkdown_solver as solver
from pokerlab.cards import DECK
from pokerlab.preflop_full_board_equity import (
    BOARDS_PER_PAIR, FullBoardEquities, plan_preflop_equities,
    reweight_preflop_equities,
)
from scripts.preflop_checkdown_validation import replay


SB_RANGE = "AsAd:1,QsQd:0.5"
BB_RANGE = "AsKh:0.25,KsKd:1"
AA_RANGE = "AsAd:1"
KK_RANGE = "KsKd:1"
PHYSICAL_COUNTS = {
    ("AdAs", "KdKs"): (1_410_336, 9_308, 292_660),
    ("QdQs", "AsKh"): (968_267, 7_226, 736_811),
    ("QdQs", "KdKs"): (292_846, 9_336, 1_410_122),
}


def prepared_table(sb_range=SB_RANGE, bb_range=BB_RANGE):
    """Build a trusted structural table from pinned physical W/T/L counts.

    This test fixture does not enumerate boards or call a ranker. The count
    rows are the independently enumerated PR125 pair counts.
    """
    plan = plan_preflop_equities(sb_range, bb_range)
    plan.validate()
    counts = []
    worlds = []
    report_rows = []
    for sb_index, bb_index, prior in plan.pairs:
        sb_hand = "".join(plan.hands[0][sb_index])
        bb_hand = "".join(plan.hands[1][bb_index])
        wins, ties, losses = PHYSICAL_COUNTS[(sb_hand, bb_hand)]
        counts.append((wins, ties, losses))
        report_rows.append({
            "sb_hand": sb_hand, "bb_hand": bb_hand,
            "wins": wins, "ties": ties, "losses": losses,
            "boards": BOARDS_PER_PAIR,
            "pair_probability": float(prior),
        })
        for sign, count in ((-1, losses), (0, ties), (1, wins)):
            if count:
                mass = float(prior * Fraction(count, BOARDS_PER_PAIR))
                worlds.append((sb_index, bb_index, mass, sign))
    table = FullBoardEquities(
        plan.hands, plan.pairs, tuple(counts), tuple(worlds), plan._budget_items
    )
    table.validate()
    return table, report_rows


def set_action(row, history_key, probability):
    action = next(item for item in row["actions"]
                  if item["history_key"] == history_key)
    action["probability"] = probability


def report_rows(table):
    """Convert a prepared fixture to the independent replay's public rows."""
    rows = []
    for (sb_index, bb_index, prior), (wins, ties, losses) in zip(
            table.pairs, table.counts):
        rows.append({
            "sb_hand": "".join(table.hands[0][sb_index]),
            "bb_hand": "".join(table.hands[1][bb_index]),
            "wins": wins, "ties": ties, "losses": losses,
            "boards": BOARDS_PER_PAIR,
            "pair_probability": float(prior),
        })
    return rows


class PreflopCheckdownSolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table, cls.counts = prepared_table()
        cls.aa_kk_table, cls.aa_kk_counts = prepared_table(AA_RANGE, KK_RANGE)

    def replay(self, result, sb_range, bb_range, config, counts):
        exact = replay(result, sb_range, bb_range, config, counts)
        self.assertTrue(exact["exact_fraction_replay"])
        self.assertLessEqual(max(exact["scalar_absolute_gaps"].values()), 1e-10)
        self.assertEqual(exact["checked_information_sets"], result["info_sets"])
        self.assertEqual(exact["checked_physical_boards"], result["physical_boards"])
        return exact

    def test_aa_kk_stack_two_jam_fold_equilibrium_matches_signed_equity_anchor(self):
        config = {
            "small_blind": 0.5, "big_blind": 1.0,
            "starting_stack": [2.0, 2.0], "raise_sizes": [],
            "max_raises": 1, "include_all_in": True,
        }
        result = solver.solve_prepared_preflop_checkdown(
            self.aa_kk_table, config=config, iterations=200, algorithm="cfrplus"
        )
        exact = self.replay(result, AA_RANGE, KK_RANGE, config, self.aa_kk_counts)
        signed_equity = Fraction(
            self.aa_kk_counts[0]["wins"] - self.aa_kk_counts[0]["losses"],
            BOARDS_PER_PAIR,
        )
        self.assertLess(signed_equity, 1)
        self.assertGreater(2 * signed_equity, 1)
        self.assertAlmostEqual(result["value_sb"], 1.0, delta=1e-4)
        self.assertLess(exact["nash_conv_fraction"][0] /
                        exact["nash_conv_fraction"][1], 1e-3)
        root = next(row for row in result["strategy"]
                    if row["player"] == "sb" and row["hand"] == "AdAs"
                    and row["history"] == [])
        jam = next(action for action in root["actions"]
                   if action["name"] == "all_in")
        self.assertEqual(jam["raise_to"], 2.0)
        self.assertGreater(jam["probability"], 0.98)
        response = next(row for row in result["strategy"]
                       if row["player"] == "bb" and row["hand"] == "KdKs"
                       and row["history"] == [jam["history_key"]])
        self.assertGreater(next(action["probability"] for action in response["actions"]
                                if action["name"] == "fold"), 0.98)

    def test_independent_replay_chooses_bb_best_action_and_scores_sb_fold(self):
        jam_config = {
            "small_blind": 0.5, "big_blind": 1.0,
            "starting_stack": [2.0, 2.0], "raise_sizes": [],
            "max_raises": 1, "include_all_in": True,
        }
        jam = solver.solve_prepared_preflop_checkdown(
            self.aa_kk_table, config=jam_config, iterations=10
        )
        root = next(row for row in jam["strategy"]
                    if row["player"] == "sb" and row["history"] == [])
        set_action(root, "all_in@2", 1.0)
        for action in root["actions"]:
            if action["history_key"] != "all_in@2":
                action["probability"] = 0.0
        bb_response = next(row for row in jam["strategy"]
                           if row["player"] == "bb"
                           and row["history"] == ["all_in@2"])
        set_action(bb_response, "fold", 1.0)
        for action in bb_response["actions"]:
            if action["history_key"] != "fold":
                action["probability"] = 0.0
        for row in jam["strategy"]:
            if row["player"] == "bb" and row["history"] == ["call"]:
                set_action(row, "check", 1.0)
                for action in row["actions"]:
                    if action["history_key"] != "check":
                        action["probability"] = 0.0
        jam.update(value_sb=1.0, value_bb=-1.0,
                   sb_best_response_value=1.0, bb_best_response_value=-1.0,
                   sb_best_response_gain=0.0, bb_best_response_gain=0.0,
                   nash_conv=0.0, exploitability=0.0)
        jam_exact = self.replay(jam, AA_RANGE, KK_RANGE, jam_config,
                                self.aa_kk_counts)
        self.assertEqual(jam_exact["value_sb_fraction"], [1, 1])
        self.assertEqual(jam_exact["bb_best_response_fraction"], [-1, 1])
        self.assertEqual(jam_exact["bb_best_response_gain"], 0.0)

        check_config = {
            "small_blind": 0.5, "big_blind": 1.0,
            "starting_stack": [2.0, 2.0], "raise_sizes": [],
            "max_raises": 0, "include_all_in": False,
        }
        folded = solver.solve_prepared_preflop_checkdown(
            self.aa_kk_table, config=check_config, iterations=10
        )
        root = next(row for row in folded["strategy"]
                    if row["player"] == "sb" and row["history"] == [])
        set_action(root, "fold", 1.0)
        for action in root["actions"]:
            if action["history_key"] != "fold":
                action["probability"] = 0.0
        signed_equity = Fraction(
            self.aa_kk_counts[0]["wins"] - self.aa_kk_counts[0]["losses"],
            BOARDS_PER_PAIR,
        )
        folded.update(
            value_sb=-0.5, value_bb=0.5,
            sb_best_response_value=float(signed_equity),
            bb_best_response_value=0.5,
            sb_best_response_gain=float(signed_equity + Fraction(1, 2)),
            bb_best_response_gain=0.0,
            nash_conv=float(signed_equity + Fraction(1, 2)),
            exploitability=float((signed_equity + Fraction(1, 2)) / 2),
        )
        folded_exact = self.replay(folded, AA_RANGE, KK_RANGE, check_config,
                                   self.aa_kk_counts)
        self.assertEqual(folded_exact["value_sb_fraction"], [-1, 2])
        self.assertEqual(folded_exact["sb_best_response_fraction"],
                         [signed_equity.numerator, signed_equity.denominator])
        self.assertEqual(folded_exact["bb_best_response_fraction"], [1, 2])
        self.assertGreater(folded_exact["nash_conv_fraction"][0], 0)

    def test_broad_raise_tree_replays_and_keeps_cards_hidden_without_reranking(self):
        config = {
            "small_blind": 0.5, "big_blind": 1.0,
            "starting_stack": [4.0, 2.75], "raise_sizes": [0.5, 1.0],
            "max_raises": 2, "include_all_in": True,
        }
        with patch("pokerlab.preflop_full_board_equity.rank_hand",
                   side_effect=AssertionError("prepared solve must not rank")):
            with patch("pokerlab.preflop_full_board_equity._board_combinations",
                       side_effect=AssertionError("prepared solve must not enumerate boards")):
                result = solver.solve_prepared_preflop_checkdown(
                    self.table, config=config, iterations=200,
                    algorithm="cfrplus",
                )
        exact = self.replay(result, SB_RANGE, BB_RANGE, config, self.counts)
        self.assertTrue(result["work_budget"]["source_enumeration_charged"])
        self.assertEqual(result["work_budget"]["current_rank_calls"], 0)
        self.assertEqual(result["work_budget"]["current_board_combinations"], 0)
        self.assertLessEqual(result["work_budget"]["total_loop_entries_upper_bound"],
                             result["work_budget"]["total_loop_entry_limit"])
        self.assertGreater(exact["checked_information_sets"], 0)
        self.assertTrue(all(row["revealed_board"] == [] for row in result["strategy"]))

        root = next(row for row in result["strategy"]
                    if row["player"] == "sb" and row["hand"] == "AdAs"
                    and row["history"] == [])
        self.assertIn("call", {action["name"] for action in root["actions"]})
        self.assertTrue(any(action["name"] == "raise"
                            and action["raise_to"] < config["starting_stack"][0]
                            for action in root["actions"]))
        bb_option = next(row for row in result["strategy"]
                         if row["player"] == "bb" and row["history"] == ["call"])
        self.assertIn("check", {action["name"] for action in bb_option["actions"]})
        self.assertTrue(any(action["name"] in {"raise", "all_in"}
                            for action in bb_option["actions"]))
        bb_reraise = next(row for row in result["strategy"]
                          if row["player"] == "bb" and row["history"] == ["raise@2"])
        short_all_in = next(action for action in bb_reraise["actions"]
                            if action["name"] == "all_in")
        self.assertEqual(short_all_in["raise_to"], 2.75)
        self.assertLess(short_all_in["raise_to"], 3.0)
        self.assertAlmostEqual(short_all_in["amount"], 1.75)
        sb_after_short_raise = next(
            row for row in result["strategy"]
            if row["player"] == "sb"
            and row["history"] == ["raise@2", "all_in@2.75"]
            and row["hand"] == "AdAs"
        )
        self.assertEqual(
            {action["name"] for action in sb_after_short_raise["actions"]},
            {"fold", "call"},
        )


    def test_vanilla_and_dcfr_profiles_replay_independently(self):
        config = {
            "small_blind": 0.5, "big_blind": 1.0,
            "starting_stack": [3.0, 2.5], "raise_sizes": [0.5],
            "max_raises": 1, "include_all_in": True,
        }
        for algorithm in ("vanilla", "dcfr"):
            with self.subTest(algorithm=algorithm):
                result = solver.solve_prepared_preflop_checkdown(
                    self.table, config=config, iterations=50,
                    algorithm=algorithm,
                )
                exact = self.replay(result, SB_RANGE, BB_RANGE, config,
                                    self.counts)
                self.assertGreater(exact["checked_information_sets"], 0)
                self.assertTrue(exact["exact_fraction_replay"])

    def test_reordered_and_reweighted_ranges_reuse_counts_and_replay_priors(self):
        reordered_sb = "QsQd:0.5,AsAd:1"
        reordered_bb = "KsKd:1,AsKh:0.25"
        reordered = reweight_preflop_equities(
            self.table, reordered_sb, reordered_bb
        )

        def pair_map(table):
            return {
                ("".join(table.hands[0][i]), "".join(table.hands[1][j])):
                (count, prior)
                for (i, j, prior), count in zip(table.pairs, table.counts)
            }

        original_pairs = pair_map(self.table)
        reordered_pairs = pair_map(reordered)
        self.assertEqual(set(reordered_pairs), set(original_pairs))
        for pair, (counts, prior) in original_pairs.items():
            self.assertEqual(reordered_pairs[pair][0], counts)
            self.assertEqual(reordered_pairs[pair][1], prior)

        changed_sb = "AsAd:0.5,QsQd:1"
        changed_bb = "AsKh:1,KsKd:0.5"
        changed = reweight_preflop_equities(
            reordered, changed_sb, changed_bb
        )
        changed_pairs = pair_map(changed)
        self.assertEqual(set(changed_pairs), set(original_pairs))
        expected_priors = {
            ("AdAs", "KdKs"): Fraction(1, 7),
            ("QdQs", "AsKh"): Fraction(4, 7),
            ("QdQs", "KdKs"): Fraction(2, 7),
        }
        for pair, (counts, prior) in changed_pairs.items():
            self.assertEqual(counts, original_pairs[pair][0])
            self.assertEqual(prior, expected_priors[pair])

        config = {
            "small_blind": 0.5, "big_blind": 1.0,
            "starting_stack": [2.5, 2.25], "raise_sizes": [],
            "max_raises": 0, "include_all_in": False,
        }
        result = solver.solve_prepared_preflop_checkdown(
            changed, config=config, iterations=20, algorithm="vanilla"
        )
        exact = self.replay(result, changed_sb, changed_bb, config,
                            report_rows(changed))
        self.assertTrue(exact["exact_fraction_replay"])

    def test_forced_blind_all_in_and_short_big_blind_boundaries(self):
        forced_config = {
            "small_blind": 0.5, "big_blind": 1.0,
            "starting_stack": [0.25, 2.0], "raise_sizes": [],
            "max_raises": 0, "include_all_in": True,
        }
        forced = solver.solve_prepared_preflop_checkdown(
            self.aa_kk_table, config=forced_config, iterations=10
        )
        exact = self.replay(forced, AA_RANGE, KK_RANGE, forced_config,
                            self.aa_kk_counts)
        signed_equity = Fraction(
            self.aa_kk_counts[0]["wins"] - self.aa_kk_counts[0]["losses"],
            BOARDS_PER_PAIR,
        )
        self.assertEqual(forced["tree"]["decision_nodes"], 0)
        self.assertEqual(forced["info_sets"], 0)
        self.assertEqual(forced["training_iterations_completed"], 0)
        self.assertEqual(forced["strategy"], [])
        self.assertAlmostEqual(forced["value_sb"], float(Fraction(1, 4) * signed_equity),
                               delta=1e-12)
        self.assertTrue(exact["exact_fraction_replay"])

        short_config = {
            "small_blind": 0.5, "big_blind": 1.0,
            "starting_stack": [3.0, 0.75], "raise_sizes": [],
            "max_raises": 2, "include_all_in": True,
        }
        short = solver.solve_prepared_preflop_checkdown(
            self.aa_kk_table, config=short_config, iterations=10
        )
        self.replay(short, AA_RANGE, KK_RANGE, short_config, self.aa_kk_counts)
        self.assertEqual(short["info_sets"], 1)
        root = next(row for row in short["strategy"] if row["player"] == "sb")
        self.assertEqual({action["name"] for action in root["actions"]},
                         {"fold", "call"})
        self.assertEqual(next(action["amount"] for action in root["actions"]
                              if action["name"] == "call"), 0.25)

    def test_oracle_rejects_leaks_illegal_history_amounts_and_incomplete_policy(self):
        config = {
            "small_blind": 0.5, "big_blind": 1.0,
            "starting_stack": [2.0, 2.0], "raise_sizes": [],
            "max_raises": 0, "include_all_in": False,
        }
        result = solver.solve_prepared_preflop_checkdown(
            self.aa_kk_table, config=config, iterations=10
        )
        self.replay(result, AA_RANGE, KK_RANGE, config, self.aa_kk_counts)
        cases = []

        bad = deepcopy(result)
        bad["opponent_hand"] = "KdKs"
        cases.append(("opponent top-level field", bad))

        bad = deepcopy(result)
        bad["strategy"][0]["opponent_hand"] = "KdKs"
        cases.append(("opponent hand row", bad))

        bad = deepcopy(result)
        bad["strategy"][0]["revealed_board"] = ["2c"]
        cases.append(("revealed future card", bad))

        bad = deepcopy(result)
        bad["strategy"][0]["history"].append("river@2c")
        cases.append(("unreachable future history", bad))

        bad = deepcopy(result)
        bad["strategy"][0]["actions"][0]["amount"] += 0.01
        cases.append(("illegal action amount", bad))

        bad = deepcopy(result)
        bad["strategy"][0]["actions"][0]["probability"] = 2.0
        cases.append(("invalid probability", bad))

        bad = deepcopy(result)
        bad["strategy"].pop()
        cases.append(("missing information set", bad))

        bad = deepcopy(result)
        bad["pair_equities"][0]["wins"] += 1
        cases.append(("changed physical count", bad))

        for label, candidate in cases:
            with self.subTest(tampering=label), self.assertRaises(ValueError):
                replay(candidate, AA_RANGE, KK_RANGE, config, self.aa_kk_counts)

    def test_invalid_tables_and_resource_forecasts_reject_before_tree_build(self):
        damaged_worlds = replace(self.table, worlds=self.table.worlds[:-1])
        first = list(self.table.counts[0])
        first[0] += 1
        first[2] -= 1
        damaged_counts = replace(self.table,
                                 counts=(tuple(first),) + self.table.counts[1:])
        corrupt_budget = replace(self.table, _budget_items=())
        many_hands = tuple(combinations(DECK, 2))[:65]
        too_many_candidates = replace(self.table,
                                      hands=(many_hands, many_hands))
        child_type = type("DerivedFullBoardEquities", (FullBoardEquities,), {})
        subclass_table = child_type(
            self.table.hands, self.table.pairs, self.table.counts,
            self.table.worlds, self.table._budget_items,
        )
        invalid_calls = [
            (object(), {}),
            (subclass_table, {}),
            (damaged_worlds, {}),
            (damaged_counts, {}),
            (corrupt_budget, {}),
            (too_many_candidates, {}),
            (self.table, {"iterations": True}),
            (self.table, {"iterations": 9}),
            (self.table, {"algorithm": "unknown"}),
            (self.table, {"resource_model": "unbounded"}),
            (self.table, {"config": object()}),
        ]
        with patch.object(solver, "build_preflop_tree",
                          side_effect=AssertionError("builder must not run")) as build:
            with patch.object(solver, "train_cfrplus",
                              side_effect=AssertionError("trainer must not run")) as trainer:
                for table, options in invalid_calls:
                    with self.subTest(options=options, table_type=type(table).__name__):
                        with self.assertRaises((TypeError, ValueError)):
                            solver.solve_prepared_preflop_checkdown(table, **options)
                build.assert_not_called()
                trainer.assert_not_called()

        oversized_tree = {
            "small_blind": 0.5, "big_blind": 1.0, "starting_stack": 3.0,
            "raise_sizes": list(range(1, 9)), "max_raises": 8,
            "include_all_in": True,
        }
        oversized_work = {}
        with patch.object(solver, "build_preflop_tree",
                          side_effect=AssertionError("builder must not run")) as build:
            with self.assertRaisesRegex(ValueError, "tree forecast"):
                solver.solve_prepared_preflop_checkdown(
                    self.aa_kk_table, config=oversized_tree, iterations=10,
                    resource_model="prepared-counts",
                )
            with self.assertRaisesRegex(ValueError, "500,000,000"):
                solver.solve_prepared_preflop_checkdown(
                    self.table, config=oversized_work, iterations=10_000,
                    resource_model="source-inclusive",
                )
            build.assert_not_called()


if __name__ == "__main__":
    unittest.main()