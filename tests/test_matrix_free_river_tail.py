"""Bounded policy, independent replay and admission controls for river tails."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import math
import sys
import unittest
from unittest.mock import patch

from pokerlab import matrix_free_river as original
from pokerlab import matrix_free_river_tail as tail
from pokerlab.river_config import RiverConfig
from pokerlab.river_tail_adapter import solve_river_tail
from scripts import turn_rational_certificate as exact
from scripts import turn_river_validation as rules


METRICS = (
    "value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value",
    "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability",
)
CASES = (
    (
        "AhKdQcJs2d",
        "AsTc:1,3c4c:0.25,9c9d:0.75,5c6c:0.5",
        "AsKh:0.5,QhTh:0.75,8c8d:0.25,6c7d:1",
        RiverConfig(pot=100, effective_stack=(120, 80), bet_sizes=(0.33,),
                    raise_sizes=(0.25,), max_raises=1, include_all_in=True),
    ),
    (
        "9h8h7h2c2d",
        "6h5h:0.75,AhKh:0.25,9c9d:1,2h2s:0.5",
        "JhTh:0.5,QhKh:1,8c8d:0.75,7c7d:0.25",
        RiverConfig(pot=100, effective_stack=(70, 80), bet_sizes=(0.25,),
                    raise_sizes=(0.25,), max_raises=1, include_all_in=True),
    ),
    (
        "2c7d9hJs5s", "AcKc:1,AsAh:0.5,KsKh:1", "AcAd:1,KcKd:0.75",
        RiverConfig(pot=17.3, effective_stack=(29.1, 11.2), bet_sizes=(0.33,),
                    raise_sizes=(0.25,), max_raises=1, include_all_in=True),
    ),
)


def _solve(case=CASES[0], *, iterations=20, discard=5):
    return tail.solve_matrix_free_river_tail(*case, iterations=iterations, discard=discard)


def _canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))


@contextmanager
def _production_forbidden():
    """Disable every imported alias of production solver/model/rank helpers."""
    modules = [module for name, module in list(sys.modules.items())
               if name.startswith("pokerlab.") and module is not None]
    tokens = ("solve", "train", "evaluate", "rank", "_build_tree",
              "_build_postflop_tree", "_enumerate_worlds", "_prefix_hand_index",
              "_cfrplus_target_deltas")
    identities = {
        id(value)
        for module in modules for name, value in vars(module).items()
        if callable(value) and (any(token in name.lower() for token in tokens)
                                or name == "strategy")
    }
    changes, calls = [], []

    def blocked(name):
        def fail(*args, **kwargs):
            calls.append(name)
            raise AssertionError("Independent replay reached production helper: " + name)
        return fail

    for module in modules:
        for name, value in list(vars(module).items()):
            if id(value) in identities:
                changes.append((module, name, value))
                setattr(module, name, blocked(module.__name__ + "." + name))
    try:
        yield calls
    finally:
        for module, name, value in reversed(changes):
            setattr(module, name, value)


def _independent_audit(result, case):
    board_text, oop, ip, config = case
    with _production_forbidden() as blocked_calls:
        replay = rules.replay_policy(result, oop, ip, board=board_text, config=config)
        differences = rules.compare_result(result, replay, tolerance=1e-9)
        board = rules.cards(board_text, 5)
        ranges = (rules.expand_range(oop, board), rules.expand_range(ip, board))
        worlds, selected = rules._worlds(board, ranges, None)
        config_rules = rules._config(config, "config")
        root = rules._public_tree(board, config_rules, config_rules, selected, worlds)
        nodes = rules._collect_nodes(root)
        policies = rules._validate_policy(
            result, root, nodes, worlds, board, selected, runouts_were_omitted=True)
        outputs = [exact.evaluate_exact(
            root, worlds, policies, config.pot, result=result,
            max_work=100_000, max_depth=64, max_bits=65_536, chance_grouping=mode,
        ) for mode in ("scan", "partition")]
        if blocked_calls:
            raise AssertionError(blocked_calls)
    return replay, differences, outputs, worlds


class MatrixFreeRiverTailTests(unittest.TestCase):
    def assert_metadata(self, result, total, discard):
        self.assertEqual(result["solver_version"], "research-matrix-free-river-tail-v1")
        self.assertEqual(result["iterations"], total)
        self.assertEqual(result["requested_iterations"], total)
        self.assertEqual(result["discard"], discard)
        self.assertEqual(result["source_iteration_window"], [discard + 1, total])
        self.assertEqual(result["averaged_sweeps"], total - discard)
        self.assertEqual(result["average_weight_sum"],
                         (total * (total + 1) - discard * (discard + 1)) // 2)
        self.assertEqual(result["requested_regret_passes"], 2 * total)
        self.assertEqual(result["requested_average_passes"], total - discard)
        self.assertEqual(result["requested_total_traversal_passes"], 3 * total - discard)
        self.assertEqual(result["admitted_training_passes_per_iteration"], 3)
        self.assertEqual(result["worlds_materialized"], 0)
        self.assertEqual(result["strategy_schema"], "postflop-strategy-v1")
        self.assertEqual(result["average_schedule"],
                         "direct-original-linear-sweep-weight-own-reach-tail")
        self.assertEqual(result["update_schedule"], "alternating-oop-then-ip")
        usage = result["resource_usage"]
        self.assertEqual(usage["admitted_traversal_passes"], 3 * total + 3)
        self.assertEqual(usage["hand_state_pass_work"],
                         max(usage["hand_counts"]) * result["public_states"] * (3 * total + 3))
        self.assertEqual(usage["limits"], {
            "hand_state_pass_work": 30_000_000, "info_action_slots": 1_000_000,
            "fallback_pair_checks": 30_000_000, "public_states": 250_000,
        })
        self.assertNotIn("convergence", result)

    def assert_policy_close(self, actual, expected):
        self.assertEqual(len(actual["strategy"]), len(expected["strategy"]))
        for row, reference in zip(actual["strategy"], expected["strategy"]):
            self.assertEqual({key: value for key, value in row.items() if key != "actions"},
                             {key: value for key, value in reference.items() if key != "actions"})
            self.assertEqual(len(row["actions"]), len(reference["actions"]))
            for action, other in zip(row["actions"], reference["actions"]):
                self.assertEqual({key: value for key, value in action.items() if key != "probability"},
                                 {key: value for key, value in other.items() if key != "probability"})
                self.assertAlmostEqual(action["probability"], other["probability"], delta=1e-9)

    def test_zero_discard_is_literal_serialized_policy_and_metric_parity(self):
        for case, total in ((CASES[0], 10), (CASES[1], 20), (CASES[2], 40)):
            with self.subTest(board=case[0], total=total):
                expected = original.solve_matrix_free_river(
                    *case, iterations=total, algorithm="cfrplus")
                actual = _solve(case, iterations=total, discard=0)
                self.assertEqual(_canonical(actual["strategy"]), _canonical(expected["strategy"]))
                for name in METRICS:
                    self.assertEqual(actual[name], expected[name], name)
                self.assert_metadata(actual, total, 0)
                self.assertEqual(expected, original.solve_matrix_free_river(
                    *case, iterations=total, algorithm="cfrplus"))

    def test_positive_tail_matches_materialized_and_independent_exact_replay(self):
        saw_tie = False
        for case, total, discard in ((CASES[0], 20, 5), (CASES[1], 40, 20),
                                      (CASES[2], 10, 9)):
            with self.subTest(board=case[0], total=total, discard=discard):
                actual = _solve(case, iterations=total, discard=discard)
                expected = solve_river_tail(*case, iterations=total, discard=discard)
                self.assert_policy_close(actual, expected)
                for name in METRICS:
                    self.assertAlmostEqual(actual[name], expected[name], delta=1e-9)
                self.assert_metadata(actual, total, discard)
                replay, differences, outputs, worlds = _independent_audit(actual, case)
                self.assertEqual(set(differences), set(METRICS))
                self.assertEqual(outputs[0]["metrics"], outputs[1]["metrics"])
                for output in outputs:
                    for name in METRICS:
                        self.assertAlmostEqual(actual[name], float(output["metrics"][name]),
                                               delta=1e-9, msg=name)
                    self.assertLessEqual(output["lower_value_bound"], output["metrics"]["value_oop"])
                    self.assertLessEqual(output["metrics"]["value_oop"], output["upper_value_bound"])
                    self.assertEqual(output["metrics"]["nash_conv"],
                                     output["upper_value_bound"] - output["lower_value_bound"])
                self.assertEqual(replay["checked_information_sets"], actual["info_sets"])
                saw_tie |= any(world["sign"] == 0 for world in worlds)
        self.assertTrue(saw_tie)

    def test_dead_blocked_hands_and_identical_holdings_keep_only_legal_rows(self):
        # OOP AcKc is blocked by every opponent hand, including identical AcKc.
        case = ("2c7d9hJs5s", "AcKc:1,AsAh:0.5,KsKh:1", "AcAd:1,KcKd:0.75,AcKc:0.25",
                CASES[2][3])
        result = _solve(case, iterations=20, discard=19)
        self.assertTrue(result["strategy"])
        self.assertTrue(all(row["player"] != "oop" or row["hand"] != "AcKc"
                            for row in result["strategy"]))
        self.assertTrue(any(row["player"] == "oop" and row["hand"] == "AhAs"
                            for row in result["strategy"]))
        replay, _, _, _ = _independent_audit(result, case)
        self.assertEqual(replay["compatible_pair_count"], result["compatible_pairs"])

    def test_no_pair_worlds_or_shared_trainer_are_used(self):
        with patch("pokerlab.postflop_solver._enumerate_worlds",
                   side_effect=AssertionError("joint worlds")), \
             patch("pokerlab.public_cfr._aggregate_prefixes",
                   side_effect=AssertionError("sparse joint pairs")), \
             patch("pokerlab.public_cfr.train_ranked_river",
                   side_effect=AssertionError("old all-sweeps trainer")), \
             patch("pokerlab.matrix_free_turn_tail._train_tail",
                   side_effect=AssertionError("turn-local trainer")):
            result = _solve(("2c7d9hJsKd", "AsAh", "QsQh",
                             RiverConfig(100, 100, (1.0,), (), 0, False)),
                            iterations=10, discard=5)
        self.assertEqual(result["worlds_materialized"], 0)
        self.assertEqual(result["resource_usage"]["fallback_pair_checks"], 0)

    def test_invalid_schedules_reject_before_parsing_kernel_tree_or_training(self):
        with patch.object(tail, "cards") as parser, \
             patch.object(tail, "RankedRiverPayoffs") as kernel, \
             patch.object(tail, "_build_tree") as builder, \
             patch.object(tail, "_train_tail") as trainer:
            for iterations, discard in ((9, 0), (100_001, 0), (True, 0), (10.0, 0),
                                         (10, True), (10, -1), (10, 10), (10, 1.0)):
                with self.subTest(iterations=iterations, discard=discard), self.assertRaises(ValueError):
                    _solve(iterations=iterations, discard=discard)
            parser.assert_not_called()
            kernel.assert_not_called()
            builder.assert_not_called()
            trainer.assert_not_called()
        with patch.object(tail, "_train_tail") as trainer:
            with self.assertRaisesRegex(ValueError, "five-card board"):
                tail.solve_matrix_free_river_tail("2c3d4h5s", "AsAh", "KcKd", iterations=10)
            trainer.assert_not_called()

    def test_full_requested_admission_is_independent_of_discard(self):
        admitted = _solve(iterations=20, discard=0)
        work = admitted["resource_usage"]["hand_state_pass_work"]
        for discard in (0, 19):
            with self.subTest(discard=discard), \
                 patch.object(tail, "MAX_HAND_STATE_PASS_WORK", work - 1), \
                 patch.object(tail, "_train_tail") as trainer, \
                 patch.object(tail, "evaluate_ranked_profile") as diagnose:
                with self.assertRaisesRegex(ValueError, "30 million hand-state pass"):
                    _solve(iterations=20, discard=discard)
                trainer.assert_not_called()
                diagnose.assert_not_called()
        last = _solve(iterations=20, discard=19)
        self.assertEqual(last["resource_usage"]["hand_state_pass_work"], work)
        self.assert_metadata(last, 20, 19)

    def test_each_tree_and_action_guard_precedes_training(self):
        for constant in ("MAX_INFO_ACTION_SLOTS", "MAX_PUBLIC_STATES"):
            with self.subTest(limit=constant), patch.object(tail, constant, 0), \
                 patch.object(tail, "_train_tail") as trainer:
                with self.assertRaises(ValueError):
                    _solve(iterations=10, discard=9)
                trainer.assert_not_called()

    def test_100000_input_ceiling_is_distinct_from_full_work_admission(self):
        # A valid input T can still fail the complete requested vector budget.
        with patch.object(tail, "_train_tail") as trainer, \
             self.assertRaisesRegex(ValueError, "30 million hand-state pass"):
            _solve(iterations=100_000, discard=99_999)
        trainer.assert_not_called()

    def test_cancellation_fallback_is_counted_and_dynamic_limit_is_retained(self):
        case = ("2c3d4h5s9c", "AsAh", "AsKc,AhKd,KcKd:1e-10",
                RiverConfig(20, 40, (0.5,), (), 0, False))
        result = _solve(case, iterations=10, discard=9)
        checks = result["resource_usage"]["fallback_pair_checks"]
        self.assertGreater(checks, 3)  # Constructor and later terminal traversals.
        self.assertLessEqual(checks, 30_000_000)
        _independent_audit(result, case)
        with patch.object(tail, "MAX_FALLBACK_PAIR_CHECKS", 0), \
             patch.object(tail, "_train_tail") as trainer, \
             self.assertRaisesRegex(ValueError, "fallback pair-check budget"):
            _solve(case, iterations=10, discard=9)
        trainer.assert_not_called()
        # Construction reserves six checks (three for the compatible hand mass,
        # three for the global mass). Marginals reserve another five: three for
        # OOP and one for each blocked IP hand. Only the next terminal traversal
        # can exceed this eleven-check limit.
        with patch.object(tail, "MAX_FALLBACK_PAIR_CHECKS", 11), \
             patch.object(tail, "_train_tail", wraps=tail._train_tail) as trainer, \
             self.assertRaisesRegex(ValueError, "fallback pair-check budget"):
            _solve(case, iterations=10, discard=9)
        trainer.assert_called_once()

    def test_finite_diagnostics_and_legal_response_bounds_are_required(self):
        for diagnostics, exception, message in (
                ((math.nan, 0.0, 0.0), ValueError, "finite"),
                ((0.0, math.inf, 0.0), ValueError, "finite"),
                ((0.0, -1.0, 0.0), RuntimeError, "legal response bounds"),
                ((0.0, 0.0, -1.0), RuntimeError, "legal response bounds")):
            with self.subTest(diagnostics=diagnostics), \
                 patch.object(tail, "evaluate_ranked_profile", return_value=diagnostics), \
                 self.assertRaisesRegex(exception, message):
                _solve(iterations=10, discard=9)

    def test_same_input_calls_are_isolated_and_restore_shared_references(self):
        old_trainer = original.train_ranked_river
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.map(lambda _: _solve(iterations=10, discard=5), range(2))
        self.assertEqual(first, second)
        self.assertIs(original.train_ranked_river, old_trainer)


if __name__ == "__main__":
    unittest.main()
