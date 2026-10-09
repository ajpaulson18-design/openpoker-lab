"""Differential and no-peek checks for the matrix-free turn payoff backend."""

from math import isfinite
from unittest.mock import patch
import unittest

from pokerlab.postflop_solver import (
    _Chance as PostflopChance,
    _build_postflop_tree,
    _enumerate_worlds,
    solve_postflop,
)
from pokerlab.public_diagnostics import (
    evaluate_profile,
    evaluate_ranked_turn_profile,
)
from pokerlab.river_config import RiverConfig
from pokerlab.river_tree import _Terminal
from pokerlab.turn_range_kernel import TurnRangePayoffs
from pokerlab.matrix_free_turn import solve_matrix_free_turn


def _cases():
    board = "2c5d9hJc"
    oop = "AsAh:0.7,KsKh:0.3,QsQh:0.5"
    ip = "AsKc:0.2,AhKd:0.6,QcQd:1,TcTh:0.4"
    return (
        (board, oop, ip,
         RiverConfig(pot=20, effective_stack=(18, 32), bet_sizes=(0.5,),
                     raise_sizes=(0.5,), max_raises=1, include_all_in=True),
         None),
        (board, "AsAh:0.9,KsKh:0.2,QsQh:0.5",
         "AsKc:0.3,AhKd:0.8,QcQd:1,TcTh:0.4",
         RiverConfig(pot=30, effective_stack=(45, 22), bet_sizes=(0.5, 1.0),
                     raise_sizes=(0.5,), max_raises=1, include_all_in=True),
         ("3c", "4d", "7s", "8h", "Ts")),
    )


def _strategy_snapshot(result):
    return [
        ((row["player"], row["hand"], row["street"], tuple(row["board"]),
          tuple(row["history"])),
         tuple((action["name"], action["amount"], action["raise_to"],
                action["history_key"], action["probability"])
               for action in row["actions"]))
        for row in result["strategy"]
    ]


class _Decision:
    def __init__(self, player, history, children):
        self.player = player
        self.history = history
        self.children = children
        self.actions = tuple(range(len(children)))


class _Chance:
    def __init__(self, branches):
        self.branches = branches


class MatrixFreeTurnTests(unittest.TestCase):
    def test_matches_public_batched_for_algorithms_and_runout_conditioning(self):
        for case_index, (board, oop, ip, config, runouts) in enumerate(_cases()):
            for algorithm in ("vanilla", "dcfr", "cfrplus"):
                with self.subTest(case=case_index, algorithm=algorithm):
                    candidate = solve_matrix_free_turn(
                        board, oop, ip, config, runouts=runouts,
                        iterations=20, algorithm=algorithm,
                    )
                    reference = solve_postflop(
                        board, oop, ip, config, runouts=runouts,
                        iterations=20, algorithm=algorithm,
                        traversal="public-batched", diagnostics="public-batched",
                        terminal_backend="sparse",
                    )
                    for field in ("value_oop", "value_ip",
                                  "oop_best_response_value", "ip_best_response_value",
                                  "nash_conv", "exploitability"):
                        self.assertAlmostEqual(candidate[field], reference[field],
                                               delta=1e-8, msg=(field, case_index, algorithm))
                    candidate_rows = _strategy_snapshot(candidate)
                    reference_rows = _strategy_snapshot(reference)
                    self.assertEqual(len(candidate_rows), len(reference_rows))
                    for left, right in zip(candidate_rows, reference_rows):
                        self.assertEqual(left[0], right[0])
                        self.assertEqual(tuple(action[:4] for action in left[1]),
                                         tuple(action[:4] for action in right[1]))
                        for a, b in zip(left[1], right[1]):
                            self.assertAlmostEqual(a[4], b[4], delta=1e-9)
                    self.assertEqual(candidate["worlds_materialized"], 0)
                    self.assertEqual(candidate["compatible_world_count"],
                                     reference["worlds"])
                    self.assertEqual(candidate["runout_mode"],
                                     "full-deck" if runouts is None else "conditioned-subset")
                    if runouts is None:
                        self.assertEqual(len(candidate["runouts"]), 48)
                    self.assertEqual(candidate["execution_backend"],
                                     "matrix-free-ranked-python")

    def test_target_checkpoints_determinism_and_fixed_budget_admission(self):
        board, oop, ip, config, runouts = _cases()[1]
        early = solve_matrix_free_turn(
            board, oop, ip, config, runouts=runouts, iterations=25,
            algorithm="vanilla", target_exploitability=1e9, check_interval=5,
        )
        self.assertEqual(early["iterations"], 10)
        self.assertEqual(early["convergence"]["stop_reason"], "target-reached")
        final = solve_matrix_free_turn(
            board, oop, ip, config, runouts=runouts, iterations=13,
            algorithm="vanilla", target_exploitability=0.0, check_interval=5,
        )
        self.assertEqual(final["iterations"], 13)
        self.assertEqual(final["convergence"]["stop_reason"], "iteration-limit")
        self.assertEqual([entry["iteration"] for entry in final["convergence"]["checkpoints"]],
                         [10, 13])
        first = solve_matrix_free_turn(board, oop, ip, config, runouts=runouts,
                                       iterations=12, algorithm="dcfr")
        second = solve_matrix_free_turn(board, oop, ip, config, runouts=runouts,
                                        iterations=12, algorithm="dcfr")
        self.assertEqual(first, second)

    def test_never_enumerates_worlds_or_sparse_prefix_edges(self):
        board, oop, ip, config, runouts = _cases()[1]
        with patch("pokerlab.postflop_solver._enumerate_worlds",
                   side_effect=AssertionError("turn pair worlds must not be enumerated")), \
             patch("pokerlab.public_cfr._aggregate_prefixes",
                   side_effect=AssertionError("sparse prefix edges must not be built")):
            result = solve_matrix_free_turn(
                board, oop, ip, config, runouts=runouts, iterations=10,
                algorithm="vanilla",
            )
        self.assertEqual(result["worlds_materialized"], 0)
        self.assertGreater(result["compatible_world_count"], 0)

    def test_resource_guard_rejects_before_training(self):
        board, oop, ip, config, runouts = _cases()[1]
        for algorithm in ("vanilla", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                with patch("pokerlab.matrix_free_turn.MAX_HAND_STATE_PASS_WORK", 0), \
                     patch("pokerlab.matrix_free_turn.train_ranked_turn") as trainer:
                    with self.assertRaisesRegex(ValueError, "hand-state pass"):
                        solve_matrix_free_turn(board, oop, ip, config, runouts=runouts,
                                               iterations=10, algorithm=algorithm)
                trainer.assert_not_called()

    def test_public_state_node_and_info_slot_caps_precede_training(self):
        board, oop, ip = "2c5d9hJc", "AsAh", "KcKd"
        config = RiverConfig(20, 30, (0.5,), (), 0, False)
        limits = (
            ("MAX_PUBLIC_STATES", "public states"),
            ("MAX_PUBLIC_NODES", "decision nodes"),
            ("MAX_INFO_ACTION_SLOTS", "information-set action slots"),
        )
        for constant, error_text in limits:
            for algorithm in ("vanilla", "cfrplus"):
                with self.subTest(constant=constant, algorithm=algorithm):
                    with patch(f"pokerlab.matrix_free_turn.{constant}", 1), \
                         patch("pokerlab.matrix_free_turn.train_ranked_turn") as trainer:
                        with self.assertRaisesRegex(ValueError, error_text):
                            solve_matrix_free_turn(
                                board, oop, ip, config, runouts=("3s", "4s"),
                                iterations=10, algorithm=algorithm,
                            )
                    trainer.assert_not_called()

    def test_full_ranges_support_low_iteration_selected_runout_probe(self):
        result = solve_matrix_free_turn(
            "2c5d9hJc", "random", "random",
            RiverConfig(10, 20, (0.5,), (), 0, False),
            runouts=("3c", "4d"), iterations=10, algorithm="vanilla",
        )
        self.assertEqual(result["iterations"], 10)
        self.assertEqual(result["worlds_materialized"], 0)
        self.assertEqual(result["resource_model"], "turn-hand-vectors-v1")
        self.assertLessEqual(result["resource_usage"]["hand_state_pass_work"],
                             result["resource_usage"]["limits"]["hand_state_pass_work"])
        self.assertEqual(result["runout_mode"], "conditioned-subset")

    def test_runout_generators_default_config_and_distinct_river_config(self):
        board, oop, ip, config, _runouts = _cases()[1]
        generated = solve_matrix_free_turn(
            board, oop, ip, config, runouts=iter(("3c", "4d", "7s")),
            iterations=10, algorithm="vanilla",
        )
        listed = solve_matrix_free_turn(
            board, oop, ip, config, runouts=("3c", "4d", "7s"),
            iterations=10, algorithm="vanilla",
        )
        self.assertEqual(generated, listed)

        defaulted = solve_matrix_free_turn(
            board, "AsAh", "KcKd", runouts=("3c", "4d"),
            iterations=10, algorithm="vanilla",
        )
        explicit_default = solve_matrix_free_turn(
            board, "AsAh", "KcKd", RiverConfig(), runouts=("3c", "4d"),
            iterations=10, algorithm="vanilla",
        )
        self.assertEqual(defaulted, explicit_default)

        river_config = RiverConfig(
            pot=config.pot, effective_stack=config.stacks,
            bet_sizes=(0.25,), raise_sizes=(0.5,), max_raises=1,
            include_all_in=True,
        )
        candidate = solve_matrix_free_turn(
            board, oop, ip, config, river_config=river_config,
            runouts=("3c", "4d", "7s"), iterations=10, algorithm="dcfr",
        )
        reference = solve_postflop(
            board, oop, ip, config, river_config=river_config,
            runouts=("3c", "4d", "7s"), iterations=10, algorithm="dcfr",
            traversal="public-batched", diagnostics="public-batched",
            terminal_backend="sparse",
        )
        for field in ("value_oop", "oop_best_response_value",
                      "ip_best_response_value", "nash_conv"):
            self.assertAlmostEqual(candidate[field], reference[field], delta=1e-8)

    def test_river_config_must_preserve_pot_and_stack_caps_before_training(self):
        board, oop, ip, config, runouts = _cases()[1]
        mismatch = RiverConfig(
            pot=config.pot + 1, effective_stack=config.stacks,
            bet_sizes=(0.5,), include_all_in=False,
        )
        with patch("pokerlab.matrix_free_turn.train_ranked_turn") as trainer:
            with self.assertRaisesRegex(ValueError, "preserve the original pot"):
                solve_matrix_free_turn(
                    board, oop, ip, config, river_config=mismatch,
                    runouts=runouts, iterations=10,
                )
        trainer.assert_not_called()

    def test_candidate_metrics_replay_through_materialized_world_public_evaluator(self):
        # This is the benchmark's literal eight-holding weighted fixture. The
        # legacy tree/world evaluator only replays the serialized candidate
        # policy; it does not train a second policy or assert policy parity.
        board = "2c7d9hJs"
        oop = ("2hKs:1.0,2sJh:0.5,3c9s:0.75,3d8c:0.25,"
               "3h6h:0.125,3s5h:1.0,4c4s:0.5,4cAs:0.75")
        ip = ("2s6h:0.75,3c9c:0.25,3dQc:0.125,3hAs:1.0,"
              "4c7c:0.5,4dJc:0.75,4s5c:0.25,5c9s:0.125")
        config = RiverConfig(100.0, 200.0, (0.75,), (), 0, False)
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                candidate = solve_matrix_free_turn(
                    board, oop, ip, config, iterations=10, algorithm=algorithm,
                )
                hands, worlds, _selected, _pairs = _enumerate_worlds(
                    board, oop, ip, None, iterations=10,
                )
                root, _nodes, _chance, _visited, _plan = _build_postflop_tree(
                    board, config, worlds=worlds,
                )
                by_hand = tuple({"".join(hand): index for index, hand in enumerate(side)}
                                for side in hands)
                policy = {}
                for row in candidate["strategy"]:
                    player = 0 if row["player"] == "oop" else 1
                    key = (player, by_hand[player][row["hand"]], tuple(row["history"]))
                    policy[key] = tuple(action["probability"] for action in row["actions"])
                replay = evaluate_profile(
                    root, worlds, policy, pot=config.pot,
                    chance_type=PostflopChance,
                )
                replay_nash_conv = max(
                    0.0, (replay[1] - replay[0]) + (replay[2] + replay[0]),
                )
                replay_metrics = (replay[0], replay[1], replay[2],
                                  replay_nash_conv, replay_nash_conv / 2.0)
                candidate_metrics = tuple(candidate[field] for field in (
                    "value_oop", "oop_best_response_value", "ip_best_response_value",
                    "nash_conv", "exploitability",
                ))
                for actual, expected in zip(candidate_metrics, replay_metrics):
                    self.assertTrue(isfinite(actual) and isfinite(expected))
                    self.assertAlmostEqual(actual, expected, delta=1e-9)

    def test_best_response_sums_river_chance_before_maximizing(self):
        board = ("2c", "5d", "9h", "Jc")
        hands = ((("Ah", "As"),), (("Kh", "Ks"),))
        weights = ((1,), (1,))
        kernel = TurnRangePayoffs(board, hands, weights, pot=20,
                                  runouts=("3s", "4s"))
        # For either action the opponent's fold response wins 10 on one river
        # and loses 10 on the other. The legal BR is therefore 0; maximizing
        # within each river first would incorrectly report +10.
        action_a = _Chance({
            "3s": _Terminal("fold", (0.0, 0.0), 0),
            "4s": _Terminal("fold", (0.0, 0.0), 1),
        })
        action_b = _Chance({
            "3s": _Terminal("fold", (0.0, 0.0), 1),
            "4s": _Terminal("fold", (0.0, 0.0), 0),
        })
        root = _Decision(0, ("turn-root",), [action_a, action_b])
        value, br0, br1 = evaluate_ranked_turn_profile(
            root, {(0, 0, ("turn-root",)): [1.0, 0.0]},
            terminal_kernel=kernel, chance_type=_Chance,
        )
        self.assertAlmostEqual(value, 0.0, places=12)
        self.assertAlmostEqual(br0, 0.0, places=12)
        self.assertAlmostEqual(br1, 0.0, places=12)


if __name__ == "__main__":
    unittest.main()
