"""Focused research tests for direct original-weight turn-tail averaging."""
from pathlib import Path
from fractions import Fraction
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]

from pokerlab import postflop_solver
from pokerlab import public_cfr
from pokerlab.postflop_solver import solve_postflop
from pokerlab.postflop_solver import _Chance
from pokerlab.river_config import RiverConfig
from pokerlab.river_tree import _Terminal
from scripts.cfr_quality import (
    build_kuhn_adapter, check_metrics, _rationalize_profile, _ordered_worlds,
    _direct_profile_value, _independent_best_response, KNOWN_P1_VALUE,
)
from scripts.river_tail_realization import reconstruct_tail
from scripts import turn_river_validation as numeric_rules


from pokerlab import turn_tail_adapter as adapter
BOARD = "Js8d4c2h"
OOP = "AsAh:0.5,KsKh:1"
IP = "AcAd:1,KcKd:0.75"
RUNOUTS = ["3c", "3d", "5h", "6s"]
CONFIG = RiverConfig(pot=100, effective_stack=220, bet_sizes=(0.5,),
                     raise_sizes=(0.5,), max_raises=1, include_all_in=False)
METRICS = (
    "value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value",
    "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability",
)


def _solve_reference(iterations, board=BOARD, oop=OOP, ip=IP, config=CONFIG,
                     runouts=RUNOUTS):
    return solve_postflop(
        board, oop, ip, config, river_config=config, runouts=runouts,
        iterations=iterations, algorithm="cfrplus", traversal="public-batched",
        diagnostics="public-batched")


def _row_map(policy):
    return {(row["player"], row["hand"], tuple(row["history"])): row
            for row in policy["strategy"]}


def _own_action_flows(policy):
    rows = _row_map(policy)
    flows = {}
    for key in sorted(rows, key=lambda value: (len(value[2]), value)):
        player, hand, history = key
        reach = 1.0
        for index, token in enumerate(history):
            ancestor = (player, hand, history[:index])
            if ancestor not in rows:
                continue
            matching = [action for action in rows[ancestor]["actions"]
                        if action["history_key"] == token]
            if len(matching) != 1:
                raise AssertionError("Own ancestor action identity is ambiguous")
            reach *= matching[0]["probability"]
        flows[key] = tuple(reach * action["probability"]
                           for action in rows[key]["actions"])
    return flows


class TurnTailAdapterTests(unittest.TestCase):
    def test_original_weight_tail_trainer_on_independent_kuhn_quality_game(self):
        # This tiny known game checks the local CFR+ schedule against a direct
        # terminal/payoff and exhaustive pure-response oracle, independently
        # of the Hold'em diagnostics used by solve_turn_tail.
        game = build_kuhn_adapter()
        _, hand_counts = public_cfr._validate_inputs(
            game["worlds"], game["infos"], 1000, "cfrplus", 2, _Chance)
        edges, marginals = public_cfr._aggregate_prefixes(
            game["worlds"], hand_counts)
        policy = adapter._train_original_weight_tail(
            game["root"], game["worlds"], game["infos"], 1000, 500,
            pot=2, chance_type=_Chance, edges=edges, marginals=marginals,
            hand_counts=hand_counts)
        quality = check_metrics(policy, layout=game["layout"])
        self.assertLessEqual(quality["nash_conv"], 0.01)
        self.assertLessEqual(quality["value_error"], 0.001)
        self.assertAlmostEqual(quality["known_p1_value"], -1 / 18)
        # Recompute the rationalized represented policy and all 64 pure
        # responses; the numeric quality check above is not the sole gate.
        rational_policy = _rationalize_profile(policy)
        exact_worlds = _ordered_worlds(exact=True)
        exact_value = _direct_profile_value(
            rational_policy, rational_policy, exact_worlds, game["layout"])
        exact_br0 = _independent_best_response(
            0, rational_policy, exact_worlds, game["layout"])
        exact_br1 = _independent_best_response(
            1, rational_policy, exact_worlds, game["layout"])
        exact_nash_conv = (exact_br0 - exact_value) + (exact_br1 + exact_value)
        self.assertLessEqual(-exact_br1, KNOWN_P1_VALUE)
        self.assertLessEqual(KNOWN_P1_VALUE, exact_br0)
        self.assertGreaterEqual(exact_nash_conv, 0)
        self.assertLessEqual(exact_nash_conv, Fraction(1, 100))
        self.assertLessEqual(abs(exact_value - KNOWN_P1_VALUE), Fraction(1, 1000))

    def test_finite_inputs_still_require_finite_derived_gains(self):
        with patch.object(adapter, "evaluate_profile", return_value=(-1e308, 1e308, 1e308)):
            with self.assertRaisesRegex(ValueError, "derived diagnostics must be finite"):
                adapter.solve_turn_tail(
                    BOARD, OOP, IP, CONFIG, river_config=CONFIG,
                    runouts=RUNOUTS, iterations=10, discard=0)

    def test_zero_discard_matches_existing_public_batched_cfrplus_exactly(self):
        for iterations in (10, 20):
            with self.subTest(iterations=iterations):
                expected = _solve_reference(iterations)
                original_train = adapter._train_original_weight_tail
                with patch.object(adapter, "_train_original_weight_tail",
                                  wraps=original_train) as train:
                    actual = adapter.solve_turn_tail(
                        BOARD, OOP, IP, CONFIG, river_config=CONFIG,
                        runouts=RUNOUTS, iterations=iterations, discard=0)
                train.assert_called_once()
                self.assertEqual(train.call_args.args[3:5], (iterations, 0))
                expected_rows, actual_rows = _row_map(expected), _row_map(actual)
                self.assertEqual(set(expected_rows), set(actual_rows))
                for key in expected_rows:
                    self.assertEqual(
                        [a["probability"] for a in expected_rows[key]["actions"]],
                        [a["probability"] for a in actual_rows[key]["actions"]],
                    )
                    self.assertEqual(
                        [{k: v for k, v in a.items() if k != "probability"}
                         for a in expected_rows[key]["actions"]],
                        [{k: v for k, v in a.items() if k != "probability"}
                         for a in actual_rows[key]["actions"]],
                    )
                self.assertEqual(actual["training_calls"], 1)
                self.assertEqual(actual["requested_iterations"], iterations)
                self.assertEqual(actual["discard"], 0)
                self.assertEqual(actual["average_weight_sum"], iterations * (iterations + 1) // 2)
                self.assertEqual(actual["runout_mode"], "conditioned-subset")

    def test_positive_tail_matches_independent_realization_reconstruction_and_replay(self):
        discard, total = 10, 20
        prefix = _solve_reference(discard)
        full = _solve_reference(total)
        original_train = adapter._train_original_weight_tail
        with patch.object(adapter, "_train_original_weight_tail",
                          wraps=original_train) as train:
            actual = adapter.solve_turn_tail(
                BOARD, OOP, IP, CONFIG, river_config=CONFIG, runouts=RUNOUTS,
                iterations=total, discard=discard)
        train.assert_called_once()
        self.assertEqual(train.call_args.args[3:5], (total, discard))
        reconstructed, ledger = reconstruct_tail(
            prefix["strategy"], full["strategy"], discard, total)
        actual_rows = _row_map(actual)
        reconstructed_rows = _row_map({"strategy": reconstructed})
        actual_flows = _own_action_flows(actual)
        reconstructed_flows = _own_action_flows({"strategy": reconstructed})
        self.assertEqual(set(actual_rows), set(reconstructed_rows))
        for key in actual_rows:
            self.assertEqual(
                [a["history_key"] for a in actual_rows[key]["actions"]],
                [a["history_key"] for a in reconstructed_rows[key]["actions"]],
            )
            for actual_flow, reconstructed_flow in zip(actual_flows[key],
                                                       reconstructed_flows[key]):
                self.assertAlmostEqual(actual_flow, float(reconstructed_flow), delta=1e-11)
        self.assertEqual(actual["source_iteration_window"], [discard + 1, total])
        self.assertEqual(actual["averaged_sweeps"], total - discard)
        self.assertEqual(actual["requested_regret_passes"], 2 * total)
        self.assertEqual(actual["requested_average_passes"], total - discard)
        self.assertEqual(actual["average_weight_sum"],
                         total * (total + 1) // 2 - discard * (discard + 1) // 2)
        oracle = numeric_rules.replay_policy(
            actual, OOP, IP, board=BOARD, config=CONFIG,
            river_config=CONFIG, runouts=actual["runouts"])
        for metric in METRICS:
            self.assertAlmostEqual(actual[metric], oracle[metric], delta=1e-9)

    def test_conditional_private_blockers_and_dead_hand_index(self):
        oop, ip = "AcKc:1,AsAh:0.5,KsKh:1", "AcAd:1,KcKd:0.75"
        runouts = ["As", "Ac", "Ks", "Kc", "Ad", "3c"]
        expected = _solve_reference(10, oop=oop, ip=ip, runouts=runouts)
        actual = adapter.solve_turn_tail(
            BOARD, oop, ip, CONFIG, river_config=CONFIG, runouts=runouts,
            iterations=10, discard=0)
        expected_rows, actual_rows = _row_map(expected), _row_map(actual)
        self.assertEqual(set(expected_rows), set(actual_rows))
        self.assertNotIn(("oop", "AcKc", ()), actual_rows)
        for key in expected_rows:
            self.assertEqual(
                [a["probability"] for a in expected_rows[key]["actions"]],
                [a["probability"] for a in actual_rows[key]["actions"]])
        self.assertEqual(set(actual["runouts"]), set(runouts))
        self.assertEqual(actual["compatible_pairs"], 4)
        self.assertEqual(actual["worlds"], 14)

        discard, total = 10, 20
        prefix = _solve_reference(discard, oop=oop, ip=ip, runouts=runouts)
        full = _solve_reference(total, oop=oop, ip=ip, runouts=runouts)
        tail = adapter.solve_turn_tail(
            BOARD, oop, ip, CONFIG, river_config=CONFIG, runouts=runouts,
            iterations=total, discard=discard)
        reconstructed, _ledger = reconstruct_tail(
            prefix["strategy"], full["strategy"], discard, total)
        tail_flows = _own_action_flows(tail)
        reconstructed_flows = _own_action_flows({"strategy": reconstructed})
        self.assertEqual(set(tail_flows), set(reconstructed_flows))
        for key in tail_flows:
            for left, right in zip(tail_flows[key], reconstructed_flows[key]):
                self.assertAlmostEqual(left, float(right), delta=1e-11)
        replay = numeric_rules.replay_policy(
            tail, oop, ip, board=BOARD, config=CONFIG,
            river_config=CONFIG, runouts=tail["runouts"])
        for metric in METRICS:
            self.assertAlmostEqual(tail[metric], replay[metric], delta=1e-9)

    def test_full_deck_zero_discard_and_last_sweep_tail(self):
        small = RiverConfig(pot=20, effective_stack=30, bet_sizes=(0.5,),
                            raise_sizes=(), max_raises=0, include_all_in=False)
        zero = adapter.solve_turn_tail(
            BOARD, "AsAh", "AcAd", small, river_config=small,
            iterations=10, discard=0)
        reference = solve_postflop(
            BOARD, "AsAh", "AcAd", small, river_config=small,
            iterations=10, algorithm="cfrplus", traversal="public-batched",
            diagnostics="public-batched")
        self.assertEqual(_row_map(zero), _row_map(reference))
        last = adapter.solve_turn_tail(
            BOARD, "AsAh", "AcAd", small, river_config=small,
            iterations=10, discard=9)
        self.assertEqual(last["averaged_sweeps"], 1)
        self.assertEqual(last["average_weight_sum"], 10)

    def test_local_state_isolation_for_concurrent_same_input_calls(self):
        original_binding = postflop_solver.solve_postflop
        original_trainer = postflop_solver.train_public_batched
        original_public_trainer = public_cfr.train_public_batched
        def run():
            return adapter.solve_turn_tail(
                BOARD, OOP, IP, CONFIG, river_config=CONFIG,
                runouts=RUNOUTS, iterations=10, discard=5)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.map(lambda _item: run(), range(2))
        self.assertEqual(_row_map(first), _row_map(second))
        self.assertIs(postflop_solver.solve_postflop, original_binding)
        self.assertIs(postflop_solver.train_public_batched, original_trainer)
        self.assertIs(public_cfr.train_public_batched, original_public_trainer)

    def test_last_sweep_tail_matches_independent_realization_difference(self):
        prefix = _solve_reference(19)
        full = _solve_reference(20)
        actual = adapter.solve_turn_tail(
            BOARD, OOP, IP, CONFIG, river_config=CONFIG,
            runouts=RUNOUTS, iterations=20, discard=19)
        expected_rows, _ = reconstruct_tail(prefix["strategy"], full["strategy"], 19, 20)
        expected_flows = _own_action_flows({"strategy": expected_rows})
        actual_flows = _own_action_flows(actual)
        self.assertEqual(set(actual_flows), set(expected_flows))
        for key in actual_flows:
            for observed, expected in zip(actual_flows[key], expected_flows[key]):
                self.assertAlmostEqual(observed, float(expected), delta=1e-11)

    def test_empty_information_table_remains_a_valid_trivial_profile(self):
        worlds, infos = [(0, 0, 1.0, 1)], {}
        _, counts = public_cfr._validate_inputs(worlds, infos, 10, "cfrplus", 2, _Chance)
        edges, marginals = public_cfr._aggregate_prefixes(worlds, counts)
        result = adapter._train_original_weight_tail(
            _Terminal("showdown", (0.0, 0.0)), worlds, infos, 10, 9,
            pot=2, chance_type=_Chance, edges=edges, marginals=marginals,
            hand_counts=counts)
        self.assertEqual(result, {})

    def test_full_deck_dense_boundary_keeps_full_request_charge(self):
        # This fixed game's first dense-envelope miss is T=1645, even if only
        # the last sweep contributes to the average. Its old world-node charge
        # is still admitted, so this exercises the separate new bound.
        self.assertLess(176 * 32 * 1645 * 3, 30_000_000)
        self.assertEqual(2 * 3039 * (3 * 1645 + 3), 30_013_164)
        with patch.object(adapter, "_train_original_weight_tail",
                          side_effect=AssertionError("inadmissible full request trained")) as train:
            with self.assertRaisesRegex(ValueError, "dense hand-state-pass"):
                adapter.solve_turn_tail(BOARD, OOP, IP, CONFIG,
                                        iterations=1645, discard=1644)
        train.assert_not_called()

    def test_invalid_requests_and_full_budget_admission_precede_local_trainer(self):
        cases = (
            ((BOARD, OOP, IP), {"iterations": True, "discard": 0}, "iterations"),
            ((BOARD, OOP, IP), {"iterations": -1, "discard": 0}, "iterations"),
            ((BOARD, OOP, IP), {"iterations": 10.0, "discard": 0}, "iterations"),
            ((BOARD, OOP, IP), {"iterations": 10001, "discard": 0}, "iterations"),
            ((BOARD, OOP, IP), {"iterations": 10, "discard": True}, "discard"),
            ((BOARD[:6], OOP, IP), {"iterations": 10, "discard": 0}, "four-card board"),
            ((BOARD, OOP, IP), {"iterations": 10, "discard": 10}, "discard"),
        )
        with patch.object(adapter, "_train_original_weight_tail",
                           side_effect=AssertionError("trainer reached before validation")) as train:
            for args, kwargs, message in cases:
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    adapter.solve_turn_tail(*args, **kwargs)
            mismatch = RiverConfig(pot=101, effective_stack=220, bet_sizes=(0.5,))
            with self.assertRaisesRegex(ValueError, "preserve original pot"):
                adapter.solve_turn_tail(BOARD, OOP, IP, CONFIG,
                                        river_config=mismatch, iterations=10, discard=0)
            board = postflop_solver.cards(BOARD)
            hands, worlds, _, _ = postflop_solver._enumerate_worlds(
                board, OOP, IP, runouts=RUNOUTS, iterations=20)
            counts = {}
            _root, _nodes, _chance, visited, _ops = postflop_solver._build_postflop_tree(
                board, CONFIG, river_config=CONFIG, worlds=worlds,
                allocation_counts=counts)
            tail_only_charge = len(worlds) * visited * 3
            full_request_charge = tail_only_charge * 20
            self.assertLess(tail_only_charge, full_request_charge)
            with patch.object(adapter, "_MAX_WORLD_NODE_WORK", tail_only_charge):
                with self.assertRaisesRegex(ValueError, "30 million world-node"):
                    adapter.solve_turn_tail(BOARD, OOP, IP, CONFIG,
                                            river_config=CONFIG, runouts=RUNOUTS,
                                            iterations=20, discard=19)
            with patch.object(adapter, "MAX_INFO_ACTION_SLOTS", 0):
                with self.assertRaisesRegex(ValueError, "information-set action slots"):
                    adapter.solve_turn_tail(BOARD, OOP, IP, CONFIG,
                                            river_config=CONFIG, runouts=RUNOUTS,
                                            iterations=10, discard=9)
            tail_only_dense = max(map(len, hands)) * counts["total"] * (3 + 3)
            with patch.object(adapter, "MAX_DENSE_HAND_STATE_PASS_WORK", tail_only_dense):
                with self.assertRaisesRegex(ValueError, "dense hand-state-pass"):
                    adapter.solve_turn_tail(BOARD, OOP, IP, CONFIG,
                                            river_config=CONFIG, runouts=RUNOUTS,
                                            iterations=20, discard=19)
        train.assert_not_called()


if __name__ == "__main__":
    unittest.main()
