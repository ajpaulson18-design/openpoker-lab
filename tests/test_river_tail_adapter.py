"""Independent flow, metric and admission tests for the river tail adapter."""
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
import hashlib
import json
import math
import unittest
from unittest.mock import patch

from pokerlab import postflop_solver, public_cfr
from pokerlab import turn_tail_adapter
from pokerlab.postflop_solver import _Chance, solve_postflop
from pokerlab.river_config import RiverConfig
from pokerlab.turn_tail_adapter import _train_original_weight_tail
from scripts import river_analytical, river_tail_realization
from scripts import turn_river_validation as numeric_rules
from pokerlab import river_tail_adapter as adapter


BOARD = "2c7d9hJsKd"
OOP = "AsAh:1,3c4c:1"
IP = "QsQh:1"
ONE_BET = RiverConfig(pot=100, effective_stack=300, bet_sizes=(1,),
                      raise_sizes=(), max_raises=0, include_all_in=False)
POLARIZED_FROZEN = RiverConfig(pot=100, effective_stack=100, bet_sizes=(1,),
                               raise_sizes=(), max_raises=0, include_all_in=False)
RAISED_WEIGHTED = RiverConfig(pot=100, effective_stack=(240, 300),
                              bet_sizes=(0.5,), raise_sizes=(0.5,),
                              max_raises=1, include_all_in=False)
BLOCKER_BOARD = "2c7d9hJs5s"
BLOCKER_OOP = "AcKc:1,AsAh:0.5,KsKh:1"
BLOCKER_IP = "AcAd:1,KcKd:0.75"
LONG_WEIGHTED_BOARD = "Js8d4c2h2s"
LONG_WEIGHTED_OOP = "AsAh:0.5,KsKh:1"
LONG_WEIGHTED_IP = "AcAd:1,KcKd:0.75"
LONG_WEIGHTED = RiverConfig(pot=100, effective_stack=(220, 120),
                             bet_sizes=(0.33, 0.75), raise_sizes=(0.5, 1),
                             max_raises=2, include_all_in=True)
METRICS = (
    "value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value",
    "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability",
)


def _row_map(rows):
    return {(row["player"], row["hand"], tuple(row["history"])): row for row in rows}


def _prepare(board_text, oop, ip, config, iterations):
    board = postflop_solver.cards(board_text)
    hands, worlds, selected, pairs = postflop_solver._enumerate_worlds(
        board, oop, ip, iterations=iterations)
    root, nodes, chance_nodes, visited, _ = postflop_solver._build_postflop_tree(
        board, config, worlds=worlds, allocation_counts={})
    legal = postflop_solver._prefix_hand_index(worlds)
    infos, metadata = {}, {}
    for (player, history), node in nodes.items():
        for hand_index in sorted(legal.get((player, ()), ())):
            key = (player, hand_index, history)
            infos[key] = len(node.actions)
            metadata[key] = node
    _, hand_counts = public_cfr._validate_inputs(
        worlds, infos, iterations, "cfrplus", config.pot, _Chance)
    edges, marginals = public_cfr._aggregate_prefixes(worlds, hand_counts)
    return dict(board=board, hands=hands, worlds=worlds, selected=selected,
                pairs=pairs, root=root, nodes=nodes, chance_nodes=chance_nodes,
                visited=visited, infos=infos, metadata=metadata,
                hand_counts=hand_counts, edges=edges, marginals=marginals)


def _rows(average_policy, context):
    result = []
    for player, hand_index, history in sorted(context["infos"]):
        node = context["metadata"][(player, hand_index, history)]
        result.append({
            "player": "oop" if player == 0 else "ip",
            "hand": "".join(context["hands"][player][hand_index]),
            "street": "river", "board": list(context["board"]),
            "history": list(history),
            "actions": [{
                "name": action.name, "amount": action.amount,
                "raise_to": action.raise_to, "history_key": action.token,
                "probability": probability,
            } for action, probability in zip(
                node.actions, average_policy[(player, hand_index, history)])],
        })
    return result


def _same_run_prefix_full(board, oop, ip, config, total, discard):
    context = _prepare(board, oop, ip, config, total)
    snapshots = {}

    def capture(iteration, average_policy):
        if iteration in (discard, total):
            snapshots[iteration] = _rows(average_policy, context)
        return False

    public_cfr.train_public_batched(
        context["root"], context["worlds"], context["infos"], total, "cfrplus",
        pot=config.pot, chance_type=_Chance, checkpoint_interval=discard,
        checkpoint_callback=capture)
    if set(snapshots) != {discard, total}:
        raise AssertionError("Ordinary public trainer did not produce D and T snapshots")
    return snapshots


def _own_action_flows(rows):
    keyed, order, probabilities, _ = river_tail_realization._snapshot(rows, "test")
    reaches = river_tail_realization._own_reaches(keyed, order, probabilities)
    return {
        (key, index): reaches[key] * probability
        for key in order for index, probability in enumerate(probabilities[key])
    }


def _fraction_one_bet_profile(rows):
    labels = {
        frozenset(("As", "Ah")): "nuts",
        frozenset(("3c", "4c")): "air",
        frozenset(("Qs", "Qh")): "catcher",
    }
    profile = {}
    for row in rows:
        player = 0 if row["player"] == "oop" else 1
        hand = labels[frozenset((row["hand"][:2], row["hand"][2:]))]
        history = tuple("bet" if token.split("@")[0] == "all_in"
                         else token.split("@")[0] for token in row["history"])
        by_name = {action["name"]: Fraction.from_float(float(action["probability"]))
                   for action in row["actions"]}
        if "all_in" in by_name:
            by_name["bet"] = by_name["all_in"]
        ordered = ("check", "bet") if "check" in by_name else ("fold", "call")
        raw = tuple(by_name[name] for name in ordered)
        total = sum(raw, Fraction(0))
        if total <= 0:
            raise AssertionError("Invalid binary64 row probability mass")
        key = (player, hand, history)
        if key in profile:
            raise AssertionError("Duplicate visible information set")
        profile[key] = tuple(value / total for value in raw)
    if set(profile) != set(river_analytical.OOP_KEYS + river_analytical.IP_KEYS):
        raise AssertionError("One-bet profile does not span the independent tree")
    return profile


def _one_bet_metrics(rows):
    value, br_oop, br_ip = river_analytical.metrics(
        _fraction_one_bet_profile(rows), nut_mass=Fraction(1, 2), pot=100, bet=100)
    gain_oop = max(Fraction(0), br_oop - value)
    gain_ip = max(Fraction(0), br_ip + value)
    gap = gain_oop + gain_ip
    return {
        "value_oop": value, "value_ip": -value,
        "oop_best_response_value": br_oop,
        "ip_best_response_value": br_ip,
        "oop_best_response_gain": gain_oop,
        "ip_best_response_gain": gain_ip,
        "nash_conv": gap, "exploitability": gap / 2,
    }


def _canonical_sha256(payload):
    raw = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False,
                      allow_nan=False) + "\n").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class RiverTailAdapterTests(unittest.TestCase):
    def _assert_metadata(self, result, total, discard):
        self.assertEqual(result["iterations"], total)
        self.assertEqual(result["requested_iterations"], total)
        self.assertEqual(result["discard"], discard)
        self.assertEqual(result["source_iteration_window"], [discard + 1, total])
        self.assertEqual(result["averaged_sweeps"], total - discard)
        self.assertEqual(result["average_weight_sum"],
                         total * (total + 1) // 2 - discard * (discard + 1) // 2)
        self.assertEqual(result["runout_mode"], "none")
        self.assertEqual(result["runouts"], [])
        self.assertEqual(result["reachable_runouts"], [])
        self.assertEqual(result["turn_config"], None)
        self.assertEqual(result["street_configs"], {"river": result["config"]})
        self.assertEqual(result["training_calls"], 1)
        self.assertEqual(result["requested_regret_passes"], 2 * total)
        self.assertEqual(result["requested_average_passes"], total - discard)
        self.assertEqual(result["requested_total_traversal_passes"], 3 * total - discard)

    def _assert_matches_numeric_replay(self, result, oop, ip, board, config):
        replay = numeric_rules.replay_policy(result, oop, ip, board=board, config=config)
        for name in METRICS:
            self.assertAlmostEqual(result[name], replay[name], delta=1e-9)

    def test_zero_discard_exact_row_parity_one_bet_and_weighted_raises(self):
        cases = (
            (BOARD, OOP, IP, ONE_BET),
            (BLOCKER_BOARD, BLOCKER_OOP, BLOCKER_IP, RAISED_WEIGHTED),
        )
        for board, oop, ip, config in cases:
            with self.subTest(board=board, config=config):
                expected = solve_postflop(
                    board, oop, ip, config, iterations=10, algorithm="cfrplus",
                    traversal="public-batched", diagnostics="public-batched")
                actual = adapter.solve_river_tail(
                    board, oop, ip, config, iterations=10, discard=0)
                expected_rows = _row_map(expected["strategy"])
                actual_rows = _row_map(actual["strategy"])
                self.assertEqual(set(expected_rows), set(actual_rows))
                self.assertEqual(expected["strategy"], actual["strategy"])
                self._assert_metadata(actual, 10, 0)
                self._assert_matches_numeric_replay(actual, oop, ip, board, config)

    def test_all_existing_small_v1_payloads_remain_byte_identical(self):
        fixtures = (
            (BOARD, OOP, IP, ONE_BET, 20, 0,
             "b364156aba22b62ef5f0a549f4489fe1d84cf028d215af70e18ac266ae140aec"),
            (BOARD, OOP, IP, RAISED_WEIGHTED, 20, 10,
             "957dd2898cbd1dab3776eef8f1def63d06f58de5e2996dd8a7d373c2e4eef939"),
            (BLOCKER_BOARD, BLOCKER_OOP, BLOCKER_IP, RAISED_WEIGHTED, 20, 19,
             "09aa4f3393f5db0d3a2c3a8f2d8d41ea3224aa6ce22d7bb169aba8cea5ffdac0"),
        )
        self.assertEqual(adapter.SOLVER_VERSION, "research-river-tail-adapter-v1")
        for board, oop, ip, config, total, discard, expected_hash in fixtures:
            with self.subTest(board=board, config=config, discard=discard):
                result = adapter.solve_river_tail(
                    board, oop, ip, config, iterations=total, discard=discard)
                self.assertEqual(result["solver_version"], adapter.SOLVER_VERSION)
                self.assertEqual(_canonical_sha256(result), expected_hash)

    def _assert_positive_tail_reconstruction(self, board, oop, ip, config,
                                             total=20, discard=10):
        snapshots = _same_run_prefix_full(board, oop, ip, config, total, discard)
        actual = adapter.solve_river_tail(
            board, oop, ip, config, iterations=total, discard=discard)
        reconstructed, ledger = river_tail_realization.reconstruct_tail(
            snapshots[discard], snapshots[total], discard, total)
        direct_flow = _own_action_flows(actual["strategy"])
        reconstructed_flow = _own_action_flows(reconstructed)
        self.assertEqual(set(direct_flow), set(reconstructed_flow))
        for key in direct_flow:
            self.assertLessEqual(abs(direct_flow[key] - reconstructed_flow[key]),
                                 Fraction(1, 10**11))
        self.assertLessEqual(ledger["maximum_reconstruction_discrepancy"],
                             Fraction(1, 10**11))
        self._assert_metadata(actual, total, discard)
        self._assert_matches_numeric_replay(actual, oop, ip, board, config)
        return actual

    def test_positive_tail_and_last_sweep_flows_and_all_eight_metrics(self):
        result = self._assert_positive_tail_reconstruction(
            BLOCKER_BOARD, BLOCKER_OOP, BLOCKER_IP, RAISED_WEIGHTED, total=20, discard=10)
        self.assertEqual(result["compatible_pairs"], 4)
        self.assertEqual(result["worlds"], 4)
        self.assertNotIn(("oop", "AcKc", ()), _row_map(result["strategy"]))
        last = self._assert_positive_tail_reconstruction(
            BOARD, OOP, IP, ONE_BET, total=10, discard=9)
        self.assertEqual(last["average_weight_sum"], 10)

    def test_independent_exact_binary64_one_bet_16_by_4_responses_and_known_value(self):
        result = adapter.solve_river_tail(
            BOARD, OOP, IP, ONE_BET, iterations=1000, discard=500)
        exact = _one_bet_metrics(result["strategy"])
        for name in METRICS:
            self.assertAlmostEqual(result[name], float(exact[name]), delta=1e-9)
        self.assertLessEqual(-exact["ip_best_response_value"], Fraction(25))
        self.assertLessEqual(Fraction(25), exact["oop_best_response_value"])
        self.assertGreater(exact["nash_conv"], Fraction(1, 1000),
                           "Retain this observed target miss; it is not an acceptance gate.")
        self.assertGreater(exact["nash_conv"], 0)
        self._assert_metadata(result, 1000, 500)

    def test_10001_sweep_long_version_has_independent_numeric_and_exact_replay(self):
        total, discard = 10_001, 3_000
        result = adapter.solve_river_tail(
            BOARD, OOP, IP, POLARIZED_FROZEN, iterations=total, discard=discard)
        self.assertEqual(result["solver_version"], adapter.LONG_SOLVER_VERSION)
        self.assertEqual(adapter.LONG_SOLVER_VERSION,
                         "research-river-long-tail-adapter-v1")
        self._assert_metadata(result, total, discard)
        self._assert_matches_numeric_replay(
            result, OOP, IP, BOARD, POLARIZED_FROZEN)
        exact = _one_bet_metrics(result["strategy"])
        for name in METRICS:
            self.assertAlmostEqual(result[name], float(exact[name]), delta=1e-9)
        self.assertLessEqual(-exact["ip_best_response_value"], Fraction(25))
        self.assertLessEqual(Fraction(25), exact["oop_best_response_value"])
        self.assertEqual(result["resource_usage"]["full_requested_world_node_work"],
                         2 * result["world_traversal_nodes"] * total * 3)
        self.assertEqual(
            result["resource_usage"]["full_requested_dense_hand_state_pass_work"],
            2 * result["public_states"] * (3 * total + 3))

    def test_zero_own_tail_reach_fallback_preserves_flow_not_conditional_row(self):
        total, discard = 1000, 500
        snapshots = _same_run_prefix_full(BOARD, OOP, IP, ONE_BET, total, discard)
        actual = adapter.solve_river_tail(
            BOARD, OOP, IP, ONE_BET, iterations=total, discard=discard)
        reconstructed, ledger = river_tail_realization.reconstruct_tail(
            snapshots[discard], snapshots[total], discard, total)
        direct_flow = _own_action_flows(actual["strategy"])
        reconstructed_flow = _own_action_flows(reconstructed)
        self.assertEqual(set(direct_flow), set(reconstructed_flow))
        for key in direct_flow:
            self.assertLessEqual(abs(direct_flow[key] - reconstructed_flow[key]),
                                 Fraction(1, 10**11))
        self.assertLessEqual(ledger["maximum_reconstruction_discrepancy"],
                             Fraction(1, 10**11))

        direct_rows = _row_map(actual["strategy"])
        reconstructed_rows = _row_map(reconstructed)
        zero_reach_changed = []
        for key in direct_rows:
            direct_probs = tuple(a["probability"] for a in direct_rows[key]["actions"])
            reconstructed_probs = tuple(
                a["probability"] for a in reconstructed_rows[key]["actions"])
            indexes = [i for (flow_key, i), amount in direct_flow.items()
                       if flow_key == key]
            if (all(direct_flow[(key, i)] == 0 for i in indexes)
                    and all(reconstructed_flow[(key, i)] == 0 for i in indexes)
                    and direct_probs != reconstructed_probs):
                zero_reach_changed.append(key)
        self.assertTrue(zero_reach_changed,
                        "fixture should exercise a zero-own-reach conditional fallback row")

    def test_invalid_requests_and_resource_admission_reject_before_trainer(self):
        cases = (
            ((BOARD, OOP, IP), {"iterations": True, "discard": 0}, "iterations"),
            ((BOARD, OOP, IP), {"iterations": 9, "discard": 0}, "iterations"),
            ((BOARD, OOP, IP), {"iterations": 10.0, "discard": 0}, "iterations"),
            ((BOARD, OOP, IP), {"iterations": 100001, "discard": 0}, "iterations"),
            ((BOARD, OOP, IP), {"iterations": 10, "discard": True}, "discard"),
            ((BOARD, OOP, IP), {"iterations": 10, "discard": 10}, "discard"),
            ((BOARD[:-2], OOP, IP), {"iterations": 10, "discard": 0}, "five board cards"),
            (("2c7d9hJsKdKd", OOP, IP), {"iterations": 10, "discard": 0}, "same card"),
        )
        with patch.object(adapter, "_train_original_weight_tail",
                          side_effect=AssertionError("inadmissible request trained")) as trainer:
            for args, kwargs, message in cases:
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    adapter.solve_river_tail(*args, **kwargs)
            with self.assertRaises((TypeError, ValueError)):
                adapter.solve_river_tail(BOARD, OOP, IP, {"unknown": True}, iterations=10)
            with patch.object(adapter, "MAX_INFO_ACTION_SLOTS", 0):
                with self.assertRaisesRegex(ValueError, "information-set action slots"):
                    adapter.solve_river_tail(BOARD, OOP, IP, ONE_BET, iterations=10)
            context = _prepare(BOARD, OOP, IP, ONE_BET, 20)
            actual_dense = max(map(len, context["hands"])) * 9 * (3 * 20 + 3)
            tail_only_dense = max(map(len, context["hands"])) * 9 * (3 * 1 + 3)
            self.assertGreater(actual_dense, tail_only_dense)
            with patch.object(adapter, "MAX_DENSE_HAND_STATE_PASS_WORK", tail_only_dense):
                with self.assertRaisesRegex(ValueError, "dense hand-state-pass"):
                    adapter.solve_river_tail(BOARD, OOP, IP, ONE_BET,
                                             iterations=20, discard=19)
            world_charge = len(context["worlds"]) * context["visited"] * 20 * 3
            with patch.object(adapter, "MAX_WORLD_NODE_WORK", world_charge - 1):
                with self.assertRaisesRegex(ValueError, "world-node"):
                    adapter.solve_river_tail(BOARD, OOP, IP, ONE_BET,
                                             iterations=20, discard=19)
            dense_fixture = RiverConfig(
                pot=100, effective_stack=10000, bet_sizes=(0.25, 0.5, 1),
                raise_sizes=(0.25, 0.5, 1), max_raises=3, include_all_in=False)
            with self.assertRaisesRegex(ValueError, "dense hand-state-pass"):
                adapter.solve_river_tail(
                    BOARD, OOP, IP, dense_fixture, iterations=6915, discard=6914)
            with self.assertRaisesRegex(ValueError, "iterations"):
                adapter.solve_river_tail(BOARD, OOP, IP, ONE_BET,
                                         iterations=100001, discard=100000)
        trainer.assert_not_called()

    def test_100k_weighted_fixture_fails_dense_guard_before_trainer(self):
        context = _prepare(LONG_WEIGHTED_BOARD, LONG_WEIGHTED_OOP,
                           LONG_WEIGHTED_IP, LONG_WEIGHTED, 100_000)
        world_charge = (len(context["worlds"]) * context["visited"] * 100_000 * 3)
        dense_charge = (max(map(len, context["hands"])) * 51 * (3 * 100_000 + 3))
        self.assertEqual(world_charge, 21_600_000)
        self.assertLess(world_charge, 30_000_000)
        self.assertEqual(dense_charge, 30_600_306)
        with patch.object(adapter, "_train_original_weight_tail",
                          side_effect=AssertionError("over-cap request trained")) as trainer:
            with self.assertRaisesRegex(ValueError, "dense hand-state-pass"):
                adapter.solve_river_tail(
                    LONG_WEIGHTED_BOARD, LONG_WEIGHTED_OOP, LONG_WEIGHTED_IP,
                    LONG_WEIGHTED, iterations=100_000, discard=99_999)
        trainer.assert_not_called()

    def test_turn_api_keeps_its_10000_iteration_ceiling(self):
        with patch.object(turn_tail_adapter, "_train_original_weight_tail",
                          side_effect=AssertionError("turn request trained")) as trainer:
            with self.assertRaisesRegex(ValueError, "iterations"):
                turn_tail_adapter.solve_turn_tail(
                    "2c7d9hJs", OOP, IP, ONE_BET,
                    iterations=10_001, discard=10_000)
        trainer.assert_not_called()

    def test_100k_one_bet_admission_passes_full_request_without_running_trainer(self):
        captured = {}

        def no_training(root, worlds, infos, iterations, discard, **kwargs):
            captured["iterations"] = iterations
            captured["discard"] = discard
            captured["worlds"] = len(worlds)
            captured["infos"] = len(infos)
            return {key: [1.0 / count] * count for key, count in infos.items()}

        with patch.object(adapter, "_train_original_weight_tail",
                          side_effect=no_training) as trainer:
            result = adapter.solve_river_tail(
                BOARD, OOP, IP, ONE_BET, iterations=100_000, discard=99_999)

        trainer.assert_called_once()
        self.assertEqual(captured, {"iterations": 100_000, "discard": 99_999,
                                    "worlds": 2, "infos": 6})
        self.assertEqual(result["solver_version"], adapter.LONG_SOLVER_VERSION)
        self.assertEqual(result["average_weight_sum"], 100_000)
        self.assertEqual(result["requested_average_passes"], 1)
        self.assertEqual(result["requested_total_traversal_passes"], 200_001)
        self.assertEqual(result["resource_usage"]["full_requested_world_node_work"],
                         2_400_000)
        self.assertEqual(
            result["resource_usage"]["full_requested_dense_hand_state_pass_work"],
            5_400_054)

    def test_finite_inputs_must_not_overflow_derived_diagnostics(self):
        with patch.object(adapter, "evaluate_profile",
                          return_value=(-1e308, 1e308, 1e308)):
            with self.assertRaisesRegex(ValueError, "derived diagnostics must be finite"):
                adapter.solve_river_tail(
                    BOARD, OOP, IP, ONE_BET, iterations=10, discard=0)

    def test_nonfinite_and_illegal_response_bounds_reject(self):
        for values in ((math.nan, 0.0, 0.0), (0.0, math.inf, 0.0)):
            with self.subTest(values=values), patch.object(
                    adapter, "evaluate_profile", return_value=values):
                with self.assertRaisesRegex(ValueError, "diagnostics must be finite"):
                    adapter.solve_river_tail(BOARD, OOP, IP, ONE_BET, iterations=10)
        with patch.object(adapter, "evaluate_profile", return_value=(1.0, 0.0, 1.0)):
            with self.assertRaisesRegex(RuntimeError, "legal response bounds"):
                adapter.solve_river_tail(BOARD, OOP, IP, ONE_BET, iterations=10)

    def test_single_actual_trainer_call_and_full_original_hand_dense_charge(self):
        with patch.object(adapter, "_train_original_weight_tail",
                          wraps=_train_original_weight_tail) as trainer:
            result = adapter.solve_river_tail(
                BLOCKER_BOARD, BLOCKER_OOP, BLOCKER_IP, RAISED_WEIGHTED,
                iterations=20, discard=19)
        trainer.assert_called_once()
        self.assertEqual(trainer.call_args.args[3:5], (20, 19))
        self.assertEqual(result["resource_usage"]["full_requested_dense_hand_state_pass_work"],
                         3 * result["public_states"] * (3 * 20 + 3))
        self.assertEqual(result["resource_usage"]["full_requested_world_node_work"],
                         4 * result["world_traversal_nodes"] * 3 * 20)
        self._assert_matches_numeric_replay(
            result, BLOCKER_OOP, BLOCKER_IP, BLOCKER_BOARD, RAISED_WEIGHTED)

    def test_calls_are_local_and_concurrent_results_match(self):
        originals = (postflop_solver.solve_postflop,
                     postflop_solver.train_public_batched,
                     public_cfr.train_public_batched)

        def run(_):
            return adapter.solve_river_tail(
                BOARD, OOP, IP, ONE_BET, iterations=10, discard=5)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.map(run, range(2))
        self.assertEqual(first["strategy"], second["strategy"])
        self.assertEqual(originals, (postflop_solver.solve_postflop,
                                     postflop_solver.train_public_batched,
                                     public_cfr.train_public_batched))


if __name__ == "__main__":
    unittest.main()
