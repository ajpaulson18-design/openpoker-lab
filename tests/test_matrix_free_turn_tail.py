"""Bounded contract and parity tests for the matrix-free TURN tail draft."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from pokerlab import matrix_free_turn as matrix_free_module
from pokerlab import turn_tail_adapter as materialized_tail
from pokerlab.cards import DECK
from pokerlab.matrix_free_turn import solve_matrix_free_turn
from pokerlab.matrix_free_turn_tail import solve_matrix_free_turn_tail
from pokerlab.river_config import RiverConfig

BOARD = "2c5d9hJc"
OOP = "AsAh:0.7,KsKh:0.3,QsQh:0.5"
IP = "AsKc:0.2,AhKd:0.6,QcQd:1,TcTh:0.4"
RUNOUTS = ("3c", "4d", "7s", "8h")
CONFIG = RiverConfig(
    pot=20,
    effective_stack=(18, 32),
    bet_sizes=(0.5,),
    raise_sizes=(0.5,),
    max_raises=1,
    include_all_in=True,
)


def _row_map(result):
    return {
        (
            row["player"],
            row["hand"],
            row["street"],
            tuple(row["board"]),
            tuple(row["history"]),
        ): row
        for row in result["strategy"]
    }


def _assert_policy_close(test, actual, expected, delta=1e-9):
    actual_rows = _row_map(actual)
    expected_rows = _row_map(expected)
    test.assertEqual(set(actual_rows), set(expected_rows))
    for key in actual_rows:
        left = actual_rows[key]["actions"]
        right = expected_rows[key]["actions"]
        test.assertEqual(len(left), len(right), key)
        for left_action, right_action in zip(left, right):
            test.assertEqual(
                tuple(left_action[name] for name in
                      ("name", "amount", "raise_to", "history_key")),
                tuple(right_action[name] for name in
                      ("name", "amount", "raise_to", "history_key")),
            )
            test.assertAlmostEqual(
                left_action["probability"], right_action["probability"],
                delta=delta, msg=key,
            )


class MatrixFreeTurnTailTests(unittest.TestCase):
    def test_invalid_schedule_and_board_reject_before_tree_or_training(self):
        with patch("pokerlab.matrix_free_turn_tail.cards") as card_parser, \
             patch("pokerlab.matrix_free_turn_tail._train_tail") as trainer:
            for iterations, discard in (
                (10, True), (10, -1), (10, 10), (9, 0), (10_001, 0),
                (True, 0), (10.0, 0),
            ):
                with self.subTest(iterations=iterations, discard=discard):
                    with self.assertRaises(ValueError):
                        solve_matrix_free_turn_tail(
                            BOARD, OOP, IP, iterations=iterations, discard=discard)
            card_parser.assert_not_called()
            trainer.assert_not_called()

        with patch("pokerlab.matrix_free_turn_tail._train_tail") as trainer:
            with self.assertRaisesRegex(ValueError, "four-card board"):
                solve_matrix_free_turn_tail(
                    "2c5d9h", OOP, IP, iterations=10, discard=0)
            trainer.assert_not_called()

    def test_discard_zero_matches_existing_matrix_free_cfrplus(self):
        expected = solve_matrix_free_turn(
            BOARD, OOP, IP, CONFIG, river_config=CONFIG,
            runouts=RUNOUTS, iterations=10, algorithm="cfrplus",
        )
        actual = solve_matrix_free_turn_tail(
            BOARD, OOP, IP, CONFIG, river_config=CONFIG,
            runouts=RUNOUTS, iterations=10, discard=0,
        )
        self.assertEqual(actual["strategy"], expected["strategy"])
        for metric in (
            "value_oop", "value_ip", "oop_best_response_value",
            "ip_best_response_value", "oop_best_response_gain",
            "ip_best_response_gain", "nash_conv", "exploitability",
        ):
            self.assertEqual(actual[metric], expected[metric], metric)
        self.assertEqual(actual["worlds_materialized"], 0)
        self.assertEqual(actual["solver_version"], "research-matrix-free-turn-tail-v1")
        self.assertEqual(actual["source_iteration_window"], [1, 10])
        self.assertEqual(actual["average_weight_sum"], 55)
        self.assertEqual(actual["requested_regret_passes"], 20)
        self.assertEqual(actual["requested_average_passes"], 10)
        self.assertEqual(actual["requested_total_traversal_passes"], 30)
        self.assertEqual(actual["admitted_training_passes_per_iteration"], 3)

    def test_positive_discard_matches_materialized_tail_control(self):
        expected = materialized_tail.solve_turn_tail(
            BOARD, OOP, IP, CONFIG, river_config=CONFIG,
            runouts=RUNOUTS, iterations=10, discard=3,
        )
        actual = solve_matrix_free_turn_tail(
            BOARD, OOP, IP, CONFIG, river_config=CONFIG,
            runouts=RUNOUTS, iterations=10, discard=3,
        )
        _assert_policy_close(self, actual, expected)
        for metric in (
            "value_oop", "value_ip", "oop_best_response_value",
            "ip_best_response_value", "oop_best_response_gain",
            "ip_best_response_gain", "nash_conv", "exploitability",
        ):
            self.assertAlmostEqual(actual[metric], expected[metric], delta=1e-9)
        self.assertEqual(actual["source_iteration_window"], [4, 10])
        self.assertEqual(actual["averaged_sweeps"], 7)
        self.assertEqual(actual["average_weight_sum"], 49)

    def test_full_deck_and_selected_runouts_keep_physical_row_schema(self):
        full = solve_matrix_free_turn_tail(
            BOARD, "AsAh", "KcKd",
            RiverConfig(pot=10, effective_stack=20, bet_sizes=(0.5,),
                        raise_sizes=(), max_raises=0, include_all_in=False),
            iterations=10, discard=9,
        )
        self.assertEqual(full["runout_mode"], "full-deck")
        self.assertEqual(len(full["runouts"]), 48)
        self.assertTrue(set(full["reachable_runouts"]).issubset(full["runouts"]))
        self.assertLess(len(full["reachable_runouts"]), len(full["runouts"]))
        self.assertEqual(full["worlds_materialized"], 0)
        self.assertTrue(full["strategy"])
        for row in full["strategy"]:
            self.assertEqual(
                set(row),
                {"player", "hand", "street", "board", "history", "actions"},
            )
            self.assertTrue(row["actions"])
            self.assertTrue(all(
                set(action) == {"name", "amount", "raise_to", "history_key", "probability"}
                for action in row["actions"]
            ))

        selected = solve_matrix_free_turn_tail(
            BOARD, OOP, IP, CONFIG,
            river_config=RiverConfig(
                pot=20, effective_stack=(18, 32), bet_sizes=(1.0,),
                raise_sizes=(0.5,), max_raises=1, include_all_in=True),
            runouts=iter(RUNOUTS), iterations=10, discard=9,
        )
        self.assertEqual(selected["runout_mode"], "conditioned-subset")
        self.assertEqual(selected["runouts"], sorted(RUNOUTS, key=DECK.index))
        self.assertEqual(selected["config"], CONFIG.to_dict())
        self.assertEqual(selected["river_config"]["bet_sizes"], [1.0])
        self.assertEqual(selected["worlds_materialized"], 0)
        self.assertEqual(selected["training_calls"], 1)

    def test_blocker_dead_hand_indices_are_not_published(self):
        oop = "AcKc:1,AsAh:0.5,KsKh:1"
        ip = "AcAd:1,KcKd:0.75"
        runouts = ("As", "Ac", "Ks", "Kc", "Ad", "3c")
        config = RiverConfig(
            pot=100, effective_stack=220, bet_sizes=(0.5,),
            raise_sizes=(0.5,), max_raises=1, include_all_in=False,
        )
        result = solve_matrix_free_turn_tail(
            "Js8d4c2h", oop, ip, config, river_config=config,
            runouts=runouts, iterations=10, discard=5,
        )
        keys = set(_row_map(result))
        self.assertNotIn(("oop", "AcKc", "turn", ("Js", "8d", "4c", "2h"), ()), keys)
        self.assertEqual(result["worlds_materialized"], 0)
        self.assertGreater(result["compatible_world_count"], 0)

    def test_allin_separate_street_configs_and_dead_indices_preserve_shape(self):
        turn = RiverConfig(
            pot=20, effective_stack=(18, 32), bet_sizes=(0.5,),
            raise_sizes=(0.5,), max_raises=1, include_all_in=True,
        )
        river = RiverConfig(
            pot=20, effective_stack=(18, 32), bet_sizes=(1.0,),
            raise_sizes=(0.5,), max_raises=1, include_all_in=True,
        )
        actual = solve_matrix_free_turn_tail(
            BOARD, OOP, IP, turn, river_config=river,
            runouts=RUNOUTS, iterations=10, discard=5,
        )
        self.assertEqual(actual["turn_config"], turn.to_dict())
        self.assertEqual(actual["river_config"], river.to_dict())
        self.assertTrue(any(
            token.startswith("river@")
            for row in actual["strategy"]
            for token in row["history"]
        ))
        self.assertEqual(actual["worlds_materialized"], 0)

    def test_exceptional_conditioning_uses_existing_stable_root_kernel(self):
        board = "2c5d9hJc"
        oop = "AhAs:1,KcKd:5e-324"
        ip = "QhQs"
        config = RiverConfig(
            pot=20, effective_stack=100, bet_sizes=(0.5,),
            raise_sizes=(), max_raises=0, include_all_in=False,
        )
        result = solve_matrix_free_turn_tail(
            board, oop, ip, config, river_config=config,
            runouts=("As",), iterations=10, discard=5,
        )
        self.assertEqual(
            result.get("conditioning_mode"),
            "scaled-branch-mass-and-conditioned-folds",
        )
        self.assertEqual(result["worlds_materialized"], 0)
        self.assertLessEqual(
            result["resource_usage"]["stable_root_fold_pair_checks"],
            result["resource_usage"]["limits"]["stable_root_fold_pair_checks"],
        )

    def test_full_request_admission_does_not_shrink_with_discard(self):
        with patch("pokerlab.matrix_free_turn_tail.MAX_HAND_STATE_PASS_WORK", 0), \
             patch("pokerlab.matrix_free_turn_tail._train_tail") as trainer:
            with self.assertRaisesRegex(ValueError, "30 million hand-state-pass"):
                solve_matrix_free_turn_tail(
                    BOARD, OOP, IP, CONFIG, runouts=RUNOUTS,
                    iterations=20, discard=19,
                )
            trainer.assert_not_called()

    def test_same_input_calls_are_isolated_and_do_not_rebind_shared_trainers(self):
        original_trainer = matrix_free_module.train_ranked_turn
        kwargs = dict(
            board=BOARD, oop_range=OOP, ip_range=IP,
            config=CONFIG, river_config=CONFIG,
            runouts=RUNOUTS, iterations=10, discard=7,
        )

        def run():
            return solve_matrix_free_turn_tail(**kwargs)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.map(lambda _index: run(), range(2))
        self.assertEqual(first, second)
        self.assertIs(matrix_free_module.train_ranked_turn, original_trainer)
        self.assertEqual(first["worlds_materialized"], 0)


if __name__ == "__main__":
    unittest.main()
