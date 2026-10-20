"""Independent fixed-game replay for the saved 100k long-tail bundle.

The handwritten evaluator below uses only the six serialized rows, two hidden
OOP hands, and five terminal histories. It does not call solver, numeric replay,
exact-audit, or river-analysis helpers to compute game metrics.
"""
from contextlib import ExitStack
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import benchmark_river_direct_long_tail as runner


REPO = runner.ROOT
REPORT_SHA256 = "94542aa030f36aac4e84fbaa24e0261c1b3556e701033dab31b7eff97308bbdf"
POLICY_SHA256 = "b82aad9c8eeaeb1fa475c7501f3d9665aedc26d5051231bb273bf2973f068442"
FROZEN_HEAD = "0450ff9fbfa434f1ad59b88606e7ed347cd90ab6"
OLD_REPORT_SHA256 = "68a0fe3ff150c37c47784cc22cfe928f19974f27208ee16dee61c53ee81a35a5"
OLD_POLICY_SHA256 = "2f558f363f716c0dc67794d329d167254b7b65bcf339cd8480d61e7e8fe53117"
THRESHOLD = Fraction(1, 1000)


def _fprob(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AssertionError("Serialized action probability is not numeric")
    probability = Fraction(value)
    if not 0 <= probability <= 1:
        raise AssertionError("Serialized action probability is outside [0, 1]")
    return probability


def _independent_five_history_metrics(policy):
    """Compute value/BRs directly for the fixed two-world one-bet river game."""
    board = ["2c", "7d", "9h", "Js", "Kd"]
    expected = {
        ("oop", "AhAs", ()): [("check", "check", 0.0, 0.0),
                                ("all_in", "all_in@100", 100.0, 100.0)],
        ("oop", "AhAs", ("check", "all_in@100")): [("fold", "fold", 0.0, 0.0),
                                                      ("call", "call", 100.0, 100.0)],
        ("oop", "3c4c", ()): [("check", "check", 0.0, 0.0),
                               ("all_in", "all_in@100", 100.0, 100.0)],
        ("oop", "3c4c", ("check", "all_in@100")): [("fold", "fold", 0.0, 0.0),
                                                      ("call", "call", 100.0, 100.0)],
        ("ip", "QhQs", ("all_in@100",)): [("fold", "fold", 0.0, 0.0),
                                             ("call", "call", 100.0, 100.0)],
        ("ip", "QhQs", ("check",)): [("check", "check", 0.0, 0.0),
                                      ("all_in", "all_in@100", 100.0, 100.0)],
    }
    rows = {}
    for row in policy["strategy"]:
        key = (row.get("player"), row.get("hand"), tuple(row.get("history", ())))
        if key in rows or key not in expected:
            raise AssertionError(f"Unexpected or duplicate public information row: {key}")
        if row.get("street") != "river" or row.get("board") != board:
            raise AssertionError("Saved row has wrong street or board")
        actions = row.get("actions")
        if type(actions) is not list or len(actions) != 2:
            raise AssertionError("Fixed game requires two legal actions per row")
        got = [(a.get("name"), a.get("history_key"), a.get("amount"), a.get("raise_to"))
               for a in actions]
        if got != expected[key]:
            raise AssertionError(f"Legal action identity differs at {key}: {got!r}")
        probs = [_fprob(a.get("probability")) for a in actions]
        total = sum(probs, Fraction(0))
        if total <= 0:
            raise AssertionError("Action row has zero probability mass")
        rows[key] = tuple(p / total for p in probs)
    if set(rows) != set(expected) or len(policy["strategy"]) != 6:
        raise AssertionError("Policy must contain exactly the six fixed public rows")

    # Each compatible physical pair has mass 1/2. On this fixed board AhAs
    # wins every showdown against QhQs, while 3c4c loses every showdown.
    worlds = (("AhAs", Fraction(1, 2), 1), ("3c4c", Fraction(1, 2), -1))
    profile = Fraction(0)
    oop_br = Fraction(0)
    # IP owns a single private hand, so each of its two information sets is
    # optimized after aggregating both hidden OOP hands and their reach.
    ip_after_bet_fold = Fraction(0)
    ip_after_bet_call = Fraction(0)
    ip_after_check_check = Fraction(0)
    ip_after_check_bet = Fraction(0)

    for hand, world_mass, sign in worlds:
        root_check, root_bet = rows[("oop", hand, ())]
        oop_fold_after_ip_bet, oop_call_after_ip_bet = rows[
            ("oop", hand, ("check", "all_in@100"))]
        ip_fold, ip_call = rows[("ip", "QhQs", ("all_in@100",))]
        ip_check, ip_bet = rows[("ip", "QhQs", ("check",))]

        # Five terminal utilities to OOP: check/check = +/-50; a fold to
        # either pot-sized wager = +/-50; a called all-in showdown = +/-150.
        showdown = Fraction(50 * sign)
        called = Fraction(150 * sign)
        profile_world = (
            root_check * (ip_check * showdown + ip_bet * (
                oop_fold_after_ip_bet * -50 + oop_call_after_ip_bet * called))
            + root_bet * (ip_fold * 50 + ip_call * called)
        )
        profile += world_mass * profile_world

        # OOP best response: choose at root per hand, and if checking then
        # choose fold/call at the later visible response using its own cards.
        bet_value = ip_fold * 50 + ip_call * called
        check_value = ip_check * showdown + ip_bet * max(Fraction(-50), called)
        oop_br += world_mass * max(bet_value, check_value)

        # Accumulate the hidden-hand mass/payoff alternatives at IP's two
        # public decisions. IP's own best response chooses one action at each.
        bet_reach = world_mass * root_bet
        ip_after_bet_fold += bet_reach * 50
        ip_after_bet_call += bet_reach * called
        check_reach = world_mass * root_check
        ip_after_check_check += check_reach * showdown
        ip_after_check_bet += check_reach * (
            oop_fold_after_ip_bet * -50 + oop_call_after_ip_bet * called)

    ip_br = -(
        min(ip_after_bet_fold, ip_after_bet_call)
        + min(ip_after_check_check, ip_after_check_bet)
    )
    gain_oop = oop_br - profile
    gain_ip = ip_br + profile
    if gain_oop < 0 or gain_ip < 0:
        raise AssertionError("Independent legal response has negative gain")
    nash = gain_oop + gain_ip
    return {
        "value_oop": profile,
        "value_ip": -profile,
        "oop_best_response_value": oop_br,
        "ip_best_response_value": ip_br,
        "oop_best_response_gain": gain_oop,
        "ip_best_response_gain": gain_ip,
        "nash_conv": nash,
        "exploitability": nash / 2,
    }


class RiverDirectLongTailSavedTests(unittest.TestCase):
    def test_saved_bundle_reconstructs_without_any_training(self):
        targets = runner._targets(REPO)
        report_raw = targets["report"].read_bytes()
        policy_raw = targets["policy"].read_bytes()
        self.assertEqual(sha256(report_raw).hexdigest(), REPORT_SHA256)
        self.assertEqual(sha256(policy_raw).hexdigest(), POLICY_SHA256)
        report = json.loads(report_raw)
        policy = json.loads(policy_raw)
        self.assertEqual(policy["board"], ["2c", "7d", "9h", "Js", "Kd"])
        self.assertEqual(policy["config"], {
            "pot": 100.0, "effective_stack": 100.0, "bet_sizes": [1.0],
            "raise_sizes": [], "max_raises": 0, "include_all_in": False,
        })
        self.assertEqual(policy["street_configs"], {"river": policy["config"]})
        self.assertEqual(policy["runouts"], [])
        self.assertEqual(policy["solver_version"], "research-river-long-tail-adapter-v1")
        self.assertEqual(policy["training_calls"], 1)

        with ExitStack() as stack:
            for target in (
                "pokerlab.river_tail_adapter.solve_river_tail",
                "pokerlab.river_tail_adapter._train_original_weight_tail",
                "pokerlab.turn_tail_adapter.solve_turn_tail",
                "pokerlab.turn_tail_adapter._train_original_weight_tail",
                "scripts.benchmark_turn_tail.capture",
                "pokerlab.postflop_solver.solve_postflop",
                "pokerlab.matrix_free_turn.solve_matrix_free_turn",
                "pokerlab.postflop_solver.train_public_batched",
                "pokerlab.matrix_free_turn.train_ranked_turn",
            ):
                stack.enter_context(patch(target, side_effect=AssertionError("Training called")))
            rebuilt = runner.verify(REPO)

        self.assertEqual(rebuilt["generation_head"], FROZEN_HEAD)
        producer = report["historical_producer_source_sha256"]
        self.assertEqual(producer["tests/reference_river_tail_v1.py"],
                         "42cde1771cf477e65652bf912f0877661ebb267c029e7fc281492d0234ebc778")
        self.assertEqual(producer["scripts/benchmark_river_direct_long_tail.py"],
                         report["verification_source_sha256"]["scripts/benchmark_river_direct_long_tail.py"])
        self.assertEqual((rebuilt["completed_training_calls"], rebuilt["iterations"],
                          rebuilt["discard"], rebuilt["averaged_sweeps"],
                          rebuilt["average_weight_sum"]),
                         (1, 100_000, 3_000, 97_000, 4_995_548_500))
        self.assertEqual((policy["requested_regret_passes"],
                          policy["requested_average_passes"],
                          policy["requested_total_traversal_passes"]),
                         (200_000, 97_000, 297_000))
        self.assertEqual((policy["worlds"], policy["compatible_pairs"],
                          policy["public_states"], policy["public_nodes"],
                          policy["terminal_nodes"], policy["chance_nodes"],
                          policy["world_traversal_nodes"], policy["tree_actions"],
                          policy["info_sets"]), (2, 2, 9, 4, 5, 0, 4, 8, 6))
        self.assertEqual(policy["resource_usage"], {
            "full_requested_world_node_work": 2_400_000,
            "full_requested_world_node_work_limit": 30_000_000,
            "full_requested_dense_hand_state_pass_work": 5_400_054,
            "full_requested_dense_hand_state_pass_work_limit": 30_000_000,
            "info_action_slots": 12, "info_action_slots_limit": 1_000_000,
            "prefix_hand_edges": 2, "prefix_hand_edge_limit": 250_000,
        })

        old_report_path = REPO / "benchmarks" / "results" / "river-direct-tail-v1.json"
        old_policy_path = REPO / "benchmarks" / "results" / "river-direct-tail-v1-polarised.json"
        old_report_raw, old_policy_raw = old_report_path.read_bytes(), old_policy_path.read_bytes()
        self.assertEqual(sha256(old_report_raw).hexdigest(), OLD_REPORT_SHA256)
        self.assertEqual(sha256(old_policy_raw).hexdigest(), OLD_POLICY_SHA256)
        old_report, old_policy = json.loads(old_report_raw), json.loads(old_policy_raw)

        independent_new = _independent_five_history_metrics(policy)
        independent_old = _independent_five_history_metrics(old_policy)
        recorded_new = report["results"]["exact_metrics_fractions"]
        recorded_old = old_report["results"][runner.FIXTURE_ID]["exact_metrics_fractions"]
        self.assertEqual({key: str(value) for key, value in independent_new.items()}, recorded_new)
        self.assertEqual({key: str(value) for key, value in independent_old.items()}, recorded_old)
        for independently_computed in (independent_old, independent_new):
            self.assertLessEqual(-independently_computed["ip_best_response_value"], Fraction(25))
            self.assertLessEqual(Fraction(25), independently_computed["oop_best_response_value"])
            self.assertEqual(independently_computed["nash_conv"],
                             independently_computed["oop_best_response_value"]
                             + independently_computed["ip_best_response_value"])

        gap = independent_new["nash_conv"]
        self.assertGreater(gap, 0)
        self.assertLessEqual(gap, THRESHOLD)
        self.assertTrue(report["results"]["exact_threshold_met"])
        self.assertFalse(report["results"]["exact_nash_conv_zero"])
        self.assertEqual(report["results"]["known_value_fraction"], "25")
        self.assertTrue(report["results"]["known_value_in_response_interval"])
        self.assertEqual(report["results"]["exact_certificate"]["work_limit"], 100_000)
        self.assertEqual(report["results"]["exact_certificate"]["depth_limit"], 64)
        self.assertEqual(report["results"]["exact_certificate"]["fraction_bit_limit"], 65_536)


if __name__ == "__main__":
    unittest.main()
