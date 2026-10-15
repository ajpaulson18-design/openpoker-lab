import unittest
from fractions import Fraction
from copy import deepcopy
from unittest.mock import patch

from pokerlab import preflop_push_fold as solver
from scripts import preflop_push_fold_validation as oracle
from scripts.preflop_push_fold_validation import replay
from tests.test_preflop_push_fold import CONFIG, SB, BB, synthetic_table


class IndependentPushFoldReplayTests(unittest.TestCase):
    def test_independent_ranker_counts_toy_full_boards_and_blocker_shifts(self):
        boards = (
            ("2c", "3c", "4c", "5c", "6c"),
            ("2d", "3d", "4d", "5d", "6d"),
            ("2h", "3h", "4h", "5h", "6h"),
        )
        with patch.object(oracle, "BOARDS", 3), patch.object(oracle, "combinations", side_effect=lambda deck, count: iter(boards)):
            counts = oracle.independent_counts(
                "AsAd:0.5,QsQd:0.25", "AsKh:0.75,KsKd:0.5")
        self.assertEqual(len(counts), 3)
        self.assertTrue(all(row["boards"] == 3 for row in counts))
        self.assertTrue(all(row["wins"] + row["ties"] + row["losses"] == 3
                            for row in counts))
        priors = {(row["sb_hand"], row["bb_hand"]): row["pair_probability"]
                  for row in counts}
        self.assertAlmostEqual(priors[("AdAs", "KdKs")], 4 / 9)
        self.assertAlmostEqual(priors[("QdQs", "AsKh")], 1 / 3)
        self.assertAlmostEqual(priors[("QdQs", "KdKs")], 2 / 9)

    def test_exact_fraction_policy_replay_reports_same_serialized_metrics(self):
        table, counts = synthetic_table()
        result = solver.solve_prepared_push_fold(
            table, config=CONFIG, iterations=100, algorithm="dcfr")
        checked = replay(result, SB, BB, CONFIG, counts)
        exact = checked["exact_fraction_replay"]
        self.assertEqual(exact["input_frequencies"], "serialized binary64 fractions")
        self.assertEqual(exact["normalization"], "each action row normalized by its exact fraction sum")
        self.assertEqual(len(exact["exact_normalized_action_frequencies"]), 4)
        self.assertEqual(float(Fraction(*exact["value_sb"])), checked["value_sb"])
        self.assertEqual(float(Fraction(*exact["sb_best_response_value"])),
                         checked["sb_best_response_value"])
        self.assertEqual(float(Fraction(*exact["bb_best_response_value"])),
                         checked["bb_best_response_value"])
        self.assertEqual(checked["checked_information_sets"], 4)

    def test_oracle_rejects_non_full_runout_scope_and_duplicate_pair_rows(self):
        table, counts = synthetic_table()
        result = solver.solve_prepared_push_fold(table, config=CONFIG, iterations=20)
        bad = deepcopy(result)
        bad["runout_mode"] = "selected-boards"
        with self.assertRaises(AssertionError):
            replay(bad, SB, BB, CONFIG, counts)


        bad = deepcopy(result)
        bad["pair_equities"].append(deepcopy(bad["pair_equities"][0]))
        with self.assertRaises(AssertionError):
            replay(bad, SB, BB, CONFIG, counts)

        bad = deepcopy(result)
        bad["strategy"][0]["actions"][0]["surprise"] = 1
        with self.assertRaises(AssertionError):
            replay(bad, SB, BB, CONFIG, counts)

        bad = deepcopy(result)
        bad["strategy"][0]["actions"][0]["probability"] = 0.5
        with self.assertRaises(AssertionError):
            replay(bad, SB, BB, CONFIG, counts)


    def test_original_tuple_and_rounded_stack_inputs_replay_canonical_output(self):
        table, counts = synthetic_table()
        for stack in ((3, 2), (3.0000000004, 2.0000000004), 2.0000000004):
            config = {**CONFIG, 'starting_stack': stack}
            result = solver.solve_prepared_push_fold(table, config=config, iterations=20)
            replay(result, SB, BB, config, counts)


if __name__ == "__main__":
    unittest.main()
