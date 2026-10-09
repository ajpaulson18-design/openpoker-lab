"""Integration and resource checks for the matrix-free ranked river solver."""
from math import isfinite
from fractions import Fraction as F
from itertools import combinations
import random
from unittest.mock import patch
import unittest

import pokerlab.matrix_free_river as matrix_free
from pokerlab.matrix_free_river import solve_matrix_free_river
from pokerlab.postflop_solver import solve_postflop
from pokerlab.ranked_river import RankedRiverPayoffs
from pokerlab.river_config import RiverConfig
from pokerlab.cards import DECK
from scripts.river_analytical import metrics, serialized_profile


def _fixtures():
    ranges = ("AsAh:0.75,KcKd:1,QsQh:0.5",
              "JcJd:1,6c7d:0.5,QcQd:0.7")
    return (
        ("2c3d4h5s9c", *ranges,
         RiverConfig(pot=30, effective_stack=(55, 70),
                     bet_sizes=(0.33, 0.8), raise_sizes=(0.5,),
                     max_raises=1, include_all_in=True)),
        ("2c3d4h5s9c", *ranges,
         RiverConfig(pot=20, effective_stack=(12, 35),
                     bet_sizes=(0.5, 1.0), raise_sizes=(0.5,),
                     max_raises=1, include_all_in=True)),
    )


def _solve(case, *, algorithm="vanilla", iterations=30, **kwargs):
    board, oop, ip, config = case
    return solve_matrix_free_river(board, oop, ip, config,
                                   iterations=iterations, algorithm=algorithm,
                                   **kwargs)


def _assert_strategy_valid(test, result):
    test.assertEqual(result["strategy_schema"], "postflop-strategy-v1")
    for row in result["strategy"]:
        probabilities = [action["probability"] for action in row["actions"]]
        test.assertTrue(probabilities)
        test.assertTrue(all(isfinite(value) and value >= 0 for value in probabilities))
        test.assertAlmostEqual(sum(probabilities), 1.0, places=10)


def _assert_resource_usage_valid(test, result):
    test.assertEqual(result["resource_model"], "river-hand-vectors-v1")
    usage = result["resource_usage"]
    limits = usage["limits"]
    for field in ("hand_state_pass_work", "info_action_slots", "fallback_pair_checks"):
        test.assertGreaterEqual(usage[field], 0)
        test.assertLessEqual(usage[field], limits[field], field)
    test.assertLessEqual(result["public_states"], limits["public_states"])


def _fraction_joint_marginals(hands, weights):
    """Direct compatible-pair Fraction sum, independent of blocker algebra."""
    compatible = [(i, j) for i, hand0 in enumerate(hands[0])
                 for j, hand1 in enumerate(hands[1])
                 if set(hand0).isdisjoint(hand1)]
    total = sum((F(weights[0][i]) * F(weights[1][j]) for i, j in compatible), F(0))
    if not total:
        raise ValueError("fixture has no compatible deals")
    marginals = [[F(0) for _ in hands[0]], [F(0) for _ in hands[1]]]
    for i, j in compatible:
        mass = F(weights[0][i]) * F(weights[1][j]) / total
        marginals[0][i] += mass
        marginals[1][j] += mass
    return marginals


class MatrixFreeRiverTests(unittest.TestCase):
    def test_joint_marginals_match_independent_fraction_pair_loop(self):
        board = ("2c", "3d", "4h", "5s", "9c")
        rng = random.Random(42613)
        available = [card for card in DECK if card not in board]
        all_hands = [tuple(sorted(pair)) for pair in combinations(available, 2)]
        fixtures = []
        for sizes in ((8, 7), (24, 25)):
            hands = (rng.sample(all_hands, sizes[0]), rng.sample(all_hands, sizes[1]))
            weights = (tuple(F(rng.randint(1, 9), rng.randint(1, 7))
                             for _ in hands[0]),
                       tuple(F(rng.randint(1, 9), rng.randint(1, 7))
                             for _ in hands[1]))
            fixtures.append((hands, weights))
        # An asymmetric blocker-heavy range exercises both identical and
        # one-card-overlap inclusion/exclusion corrections.
        fixtures.append((((tuple(sorted(("As", "Ah"))), tuple(sorted(("Kc", "Kd")))),
                          (tuple(sorted(("As", "Kc"))), tuple(sorted(("Ah", "Kd"))),
                           tuple(sorted(("Qs", "Qh"))))),
                         ((F(3), F(2)), (F(9), F(7), F(1)))))
        for case_index, (hands, weights) in enumerate(fixtures):
            kernel = RankedRiverPayoffs(board, hands, weights, pot=50)
            actual = kernel.joint_marginals()
            expected = _fraction_joint_marginals(hands, weights)
            with self.subTest(case=case_index):
                for player in (0, 1):
                    self.assertEqual(len(actual[player]), len(expected[player]))
                    for got, want in zip(actual[player], expected[player]):
                        if want:
                            self.assertAlmostEqual(got / float(want), 1.0, places=10)
                        else:
                            self.assertAlmostEqual(got, 0.0, places=12)
                    self.assertAlmostEqual(sum(actual[player]), 1.0, places=12)

    def test_fallback_pair_budget_rejects_before_rare_direct_scan(self):
        board = ("2c", "3d", "4h", "5s", "9c")
        hands = ((tuple(sorted(("As", "Ah"))),),
                 (tuple(sorted(("As", "Kc"))), tuple(sorted(("Ah", "Kd"))),
                  tuple(sorted(("Kc", "Kd")))))
        weights = ((1,), (1, 1, 1e-10))
        with self.assertRaisesRegex(ValueError, "fallback pair-check budget"):
            RankedRiverPayoffs(board, hands, weights, pot=20,
                               fallback_pair_limit=0)

    def test_small_weighted_games_match_ranked_and_sparse_postflop(self):
        for case_index, case in enumerate(_fixtures()):
            for algorithm in ("vanilla", "dcfr", "cfrplus"):
                with self.subTest(case=case_index, algorithm=algorithm):
                    matrix = _solve(case, algorithm=algorithm)
                    ranked = solve_postflop(
                        case[0], case[1], case[2], case[3], iterations=30,
                        algorithm=algorithm, traversal="public-batched",
                        diagnostics="public-batched", terminal_backend="ranked",
                    )
                    sparse = solve_postflop(
                        case[0], case[1], case[2], case[3], iterations=30,
                        algorithm=algorithm, traversal="public-batched",
                        diagnostics="public-batched", terminal_backend="sparse",
                    )
                    for reference in (ranked, sparse):
                        for field in ("value_oop", "value_ip",
                                      "oop_best_response_value", "ip_best_response_value",
                                      "nash_conv", "exploitability"):
                            self.assertAlmostEqual(matrix[field], reference[field],
                                                   delta=1e-8, msg=(field, case_index, algorithm))
                    _assert_strategy_valid(self, matrix)
                    self.assertEqual(matrix["execution_backend"],
                                     "matrix-free-ranked-python")
                    _assert_resource_usage_valid(self, matrix)

    def test_polarised_holdem_policy_matches_independent_rational_oracle(self):
        board = "2c7d9hJsKd"
        result = solve_matrix_free_river(
            board, "AsAh,3c4c", "QsQh",
            RiverConfig(100, 500, (1.0,), (), 0, False),
            iterations=300, algorithm="cfrplus",
        )
        expected = metrics(serialized_profile(result))
        for field, value in zip(("value_oop", "oop_best_response_value",
                                 "ip_best_response_value"), expected):
            self.assertAlmostEqual(result[field], float(value), places=9, msg=field)
        self.assertAlmostEqual(result["nash_conv"], float(expected[1] + expected[2]),
                               places=9)
        self.assertLess(result["nash_conv"], 4)

    def test_zero_and_orphan_hands_and_tiny_surviving_compatible_weight(self):
        board = "2c3d4h5s9c"
        config = RiverConfig(40, 80, (0.5,), (), 0, False)
        for tiny in (1e-8, 1e-10, 1e-16):
            oop, ip = "AsAh", f"AsKc,AhKd,KcKd:{tiny}"
            with self.subTest(tiny=tiny):
                matrix = solve_matrix_free_river(board, oop, ip, config,
                                                 iterations=10, algorithm="vanilla")
                sparse = solve_postflop(board, oop, ip, config, iterations=10,
                                        traversal="public-batched",
                                        diagnostics="public-batched")
                self.assertEqual(matrix["compatible_pairs"], 1)
                for field in ("value_oop", "oop_best_response_value",
                              "ip_best_response_value", "nash_conv"):
                    self.assertAlmostEqual(matrix[field], sparse[field], delta=1e-8)
                self.assertTrue(all("AsKc" not in row["hand"] and "AhKd" not in row["hand"]
                                    for row in matrix["strategy"]))
                _assert_strategy_valid(self, matrix)

    def test_complete_random_ranges_solve_without_materializing_pair_worlds(self):
        board = "2c3d4h5s9c"
        result = solve_matrix_free_river(
            board, "random", "random",
            RiverConfig(10, 20, (0.5,), (), 0, False),
            iterations=10, algorithm="vanilla",
        )
        self.assertEqual(result["compatible_pairs"], 1_070_190)
        self.assertEqual(result["worlds_materialized"], 0)
        self.assertEqual(result["execution_backend"], "matrix-free-ranked-python")
        _assert_strategy_valid(self, result)
        _assert_resource_usage_valid(self, result)

    def test_training_does_not_call_world_enumeration_or_sparse_prefix_aggregation(self):
        case = _fixtures()[0]
        with patch("pokerlab.postflop_solver._enumerate_worlds",
                   side_effect=AssertionError("pair worlds must not be enumerated")), \
             patch("pokerlab.public_cfr._aggregate_prefixes",
                   side_effect=AssertionError("sparse prefix edges must not be built")):
            result = _solve(case, iterations=10, algorithm="vanilla")
        self.assertEqual(result["worlds_materialized"], 0)

    def test_target_checkpoints_and_missed_target_use_completed_iterations(self):
        case = _fixtures()[0]
        early = _solve(case, iterations=25, target_exploitability=1e9,
                       check_interval=5)
        self.assertEqual(early["iterations"], 10)
        self.assertEqual(early["convergence"]["stop_reason"], "target-reached")
        final = _solve(case, iterations=13, target_exploitability=0.0,
                       check_interval=5)
        self.assertEqual(final["iterations"], 13)
        self.assertEqual(final["convergence"]["stop_reason"], "iteration-limit")
        self.assertEqual([item["iteration"] for item in final["convergence"]["checkpoints"]],
                         [10, 13])
        self.assertTrue(all(isfinite(item["exploitability"])
                            for item in final["convergence"]["checkpoints"]))

    def test_repeated_calls_are_deterministic_and_defaults_are_matrix_free(self):
        case = _fixtures()[0]
        first = _solve(case, iterations=15)
        second = _solve(case, iterations=15)
        self.assertEqual(first, second)
        implicit = solve_matrix_free_river(case[0], case[1], case[2], case[3],
                                           iterations=10)
        self.assertEqual(implicit["algorithm"], "cfrplus")
        _assert_strategy_valid(self, implicit)
        _assert_resource_usage_valid(self, implicit)

    def test_invalid_inputs_and_resource_guards_reject_before_training(self):
        case = _fixtures()[0]
        board, oop, ip, config = case
        for invalid_board in ("2c3d4h", "2c3d4h5s"):
            with self.subTest(board=invalid_board), self.assertRaises(ValueError):
                solve_matrix_free_river(invalid_board, oop, ip, config, iterations=10)
        for iterations in (0, 9, True, -1):
            with self.subTest(iterations=iterations), self.assertRaises(ValueError):
                solve_matrix_free_river(board, oop, ip, config, iterations=iterations)
        for target in (True, -1, float("nan"), float("inf")):
            with self.subTest(target=target), self.assertRaises(ValueError):
                solve_matrix_free_river(board, oop, ip, config, iterations=10,
                                        target_exploitability=target)
        for interval in (True, 0, -1, 1.5):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                solve_matrix_free_river(board, oop, ip, config, iterations=10,
                                        target_exploitability=1,
                                        check_interval=interval)

    def test_each_resource_guard_rejects_before_training(self):
        case = _fixtures()[0]
        board, oop, ip, config = case
        guard_fields = ("MAX_HAND_STATE_PASS_WORK", "MAX_INFO_ACTION_SLOTS",
                        "MAX_PUBLIC_STATES")
        for field in guard_fields:
            with self.subTest(limit=field), \
                 patch.object(matrix_free, field, 0), \
                 patch.object(matrix_free, "train_ranked_river",
                              side_effect=AssertionError("training ran before admission")), \
                 self.assertRaises(ValueError):
                solve_matrix_free_river(board, oop, ip, config, iterations=10,
                                         algorithm="vanilla")

        # Dominant IP mass is blocked by AsAh; the sole compatible KcKd mass
        # forces exact compatible-pair fallback accounting during admission.
        tiny_ip = "AsKc,AhKd,KcKd:1e-10"
        with patch.object(matrix_free, "MAX_FALLBACK_PAIR_CHECKS", 0), \
             patch.object(matrix_free, "train_ranked_river",
                          side_effect=AssertionError("training ran before admission")), \
             self.assertRaises(ValueError):
            solve_matrix_free_river("2c3d4h5s9c", "AsAh", tiny_ip, config,
                                    iterations=10, algorithm="vanilla")


if __name__ == "__main__":
    unittest.main()
