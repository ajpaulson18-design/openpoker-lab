"""Saved T750/250 three-hand TURN evidence checks; outside pinned source sets.

The sole production call is complete. Verification never trains.
"""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

from scripts import benchmark_turn_three_hand_tail as runner
from scripts import turn_river_validation as rules
from scripts import turn_three_hand_reference as reference
from pokerlab import cfr, postflop_solver, turn_tail_adapter


EXPECTED_GENERATION_HEAD = "03d54fefaad2aa6247f9d627e112e40688c0ead1"
EXPECTED_REPORT_SHA256 = "1827e2163b897c5a1c5274e4a300ee365d8234fdf38235647772d63300953a7a"
EXPECTED_POLICY_SHA256 = "c02e37dedf886f586e8b0ce9a98e86d079a32322d6e2ba4eb5beaab127dd6789"
METRIC_NAMES = (
    "value_oop", "value_ip", "oop_best_response_value",
    "ip_best_response_value", "oop_best_response_gain",
    "ip_best_response_gain", "nash_conv", "exploitability",
)
SCOPE = (
    "One fixed 396-world configured three-hand TURN CFR+ direct-tail profile. "
    "Exact evidence applies to exact row-normalized binary64 probabilities for "
    "this serialized policy; it does not establish a known equilibrium value or "
    "general convergence."
)


def _repo_root():
    return Path(turn_tail_adapter.__file__).resolve().parents[1]


def _literal_worlds():
    """Rebuild the fixed physical law without reference.model() world fields."""
    board = ("Js", "8d", "4c", "2h")
    oop_hands = (("As", "Ah"), ("Ks", "Kh"), ("Qs", "Qh"))
    ip_hands = (("Ac", "Ad"), ("Kc", "Kd"), ("Qc", "Qd"))
    mass_numerators = ((8, 6, 4), (16, 12, 8), (12, 9, 6))
    rank = {card: "23456789TJQKA".index(card[0]) + 2 for card in rules.DECK}
    worlds = []
    for oi, oop in enumerate(oop_hands):
        for ii, ip in enumerate(ip_hands):
            pair_mass = Fraction(mass_numerators[oi][ii], 81)
            dead = set(board) | set(oop) | set(ip)
            rivers = [card for card in rules.DECK if card not in dead]
            for river in rivers:
                if oi == ii:
                    sign = 0
                else:
                    lower_index = max(oi, ii)
                    lower_rank = (14, 13, 12)[lower_index]
                    if rank[river] == lower_rank:
                        oop_wins = oi > ii
                    else:
                        oop_wins = oi < ii
                    sign = 1 if oop_wins else -1
                worlds.append({"hands": (oop, ip), "river": river,
                               "weight": pair_mass / 44, "sign": sign})
    if len(worlds) != 396 or sum((world["weight"] for world in worlds), Fraction()) != 1:
        raise AssertionError("Literal fixed world law is malformed")
    return worlds


def _policy_probabilities(payload):
    rows = {}
    for row in payload["strategy"]:
        hand = frozenset(row["hand"][index:index + 2]
                         for index in range(0, len(row["hand"]), 2))
        key = (0 if row["player"] == "oop" else 1, hand, tuple(row["history"]))
        if key in rows:
            raise AssertionError("Saved policy has duplicate player/hand/history row")
        raw = [Fraction.from_float(float(action["probability"]))
               for action in row["actions"]]
        total = sum(raw, Fraction())
        if total <= 0:
            raise AssertionError("Saved policy row has no positive probability mass")
        rows[key] = tuple(probability / total for probability in raw)
    return rows


def _profile_value_from_public_tree(root, worlds, payload):
    """Exact profile sum using independent public rules and literal world law."""
    probabilities = _policy_probabilities(payload)

    def value(node, world):
        if isinstance(node, rules._Chance):
            child = node.branches.get(world["river"])
            if child is None:
                raise AssertionError("Independent tree omitted a physical river")
            return value(child, world)
        if isinstance(node, rules._Terminal):
            winner_sign = (1 if node.winner == 0 else -1) if node.kind == "fold" else world["sign"]
            matched = min(Fraction.from_float(float(part)) for part in node.contributions)
            return winner_sign * (Fraction(50) + matched)
        if not isinstance(node, rules._Decision):
            raise AssertionError(f"Unknown public node type: {type(node)!r}")
        hand = frozenset(world["hands"][node.player])
        key = (node.player, hand, node.history)
        action_probs = probabilities[key]
        if len(action_probs) != len(node.children):
            raise AssertionError("Saved action slots differ from independent rules tree")
        return sum((p * value(child, world)
                    for p, child in zip(action_probs, node.children)), Fraction())

    return sum((world["weight"] * value(root, world) for world in worlds), Fraction())


def _expected_fixed_report_fields():
    """Specification values, entered independently of the saved report."""
    return {
        "iterations": 750,
        "discard": 250,
        "averaged_sweeps": 500,
        "average_weight_sum": 250_250,
        "requested_regret_passes": 1_500,
        "requested_average_passes": 500,
        "requested_total_traversal_passes": 2_000,
        "full_requested_world_node_work": 28_512_000,
        "full_requested_world_node_work_limit": 30_000_000,
        "full_requested_dense_hand_state_pass_work": 20_540_601,
        "full_requested_dense_hand_state_pass_work_limit": 30_000_000,
        "info_action_slots": 8_046,
        "info_action_slots_limit": 1_000_000,
        "prefix_hand_edges": 405,
        "prefix_hand_edge_limit": 250_000,
        "completed_training_calls": 1,
    }


def _assert_exact_metric_identities(test, metrics):
    test.assertEqual(set(metrics), set(METRIC_NAMES))
    values = {key: Fraction(value) for key, value in metrics.items()}
    test.assertEqual(values["value_oop"] + values["value_ip"], 0)
    test.assertGreaterEqual(values["oop_best_response_gain"], 0)
    test.assertGreaterEqual(values["ip_best_response_gain"], 0)
    test.assertEqual(values["oop_best_response_gain"],
                     values["oop_best_response_value"] - values["value_oop"])
    test.assertEqual(values["ip_best_response_gain"],
                     values["ip_best_response_value"] - values["value_ip"])
    test.assertEqual(values["nash_conv"],
                     values["oop_best_response_gain"] + values["ip_best_response_gain"])
    test.assertEqual(values["exploitability"] * 2, values["nash_conv"])
    return values


class SavedThreeHandTailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = _repo_root()
        cls.targets = runner._targets(cls.root)

    def test_pinned_hashes_and_read_only_full_replay(self):
        self.assertRegex(EXPECTED_GENERATION_HEAD, r"^[0-9a-f]{40}$")
        self.assertRegex(EXPECTED_REPORT_SHA256, r"^[0-9a-f]{64}$")
        self.assertRegex(EXPECTED_POLICY_SHA256, r"^[0-9a-f]{64}$")
        report_raw = runner._read_bounded(self.targets["report"])
        policy_raw = runner._read_bounded(self.targets["policy"])
        self.assertEqual(hashlib.sha256(report_raw).hexdigest(), EXPECTED_REPORT_SHA256)
        report = json.loads(report_raw)
        self.assertEqual(report["generation_head"], EXPECTED_GENERATION_HEAD)
        self.assertEqual(report["policy_sha256"], EXPECTED_POLICY_SHA256)
        self.assertEqual(hashlib.sha256(policy_raw).hexdigest(), EXPECTED_POLICY_SHA256)
        self.assertEqual(report["schema"], "turn-three-hand-direct-tail-v1")
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["fixture_id"], "turn-three-hand-physical-v1")
        self.assertEqual(report["fixture"], reference.FIXTURE)

        for name, expected in _expected_fixed_report_fields().items():
            self.assertEqual(report[name], expected, name)
        self.assertEqual(report["scope"], SCOPE)
        self.assertEqual(report["policy_file"], runner.POLICY_NAME)
        self.assertGreaterEqual(report["actual_complete_call_seconds"], 0)
        self.assertEqual(report["control_before_training"]["training_calls"], 0)

        with mock.patch.object(turn_tail_adapter, "solve_turn_tail",
                               side_effect=AssertionError("saved verify called producer")), \
             mock.patch.object(turn_tail_adapter, "_train_original_weight_tail",
                               side_effect=AssertionError("saved verify called adapter trainer")), \
             mock.patch.object(cfr, "train",
                               side_effect=AssertionError("saved verify called CFR trainer")), \
             mock.patch.object(cfr, "evaluate",
                               side_effect=AssertionError("saved verify called evaluator")), \
             mock.patch.object(cfr, "best_response",
                               side_effect=AssertionError("saved verify called best response")), \
             mock.patch.object(postflop_solver, "solve_postflop",
                               side_effect=AssertionError("saved verify called production solver")), \
             mock.patch.object(postflop_solver, "_build_postflop_tree",
                               side_effect=AssertionError("saved verify called production tree")):
            verified = runner.verify(self.root)
        self.assertEqual(runner._canonical(verified), report_raw)

        results = verified["results"]
        exact = _assert_exact_metric_identities(self, results["exact_metrics_fractions"])
        self.assertEqual(results["profile_value_fraction"], str(exact["value_oop"]))
        self.assertEqual(results["exact_nash_conv_zero"], exact["nash_conv"] == 0)
        self.assertEqual(results["exact_threshold_met"],
                         exact["nash_conv"] <= Fraction(1, 1000))
        self.assertGreater(exact["nash_conv"], 0)
        self.assertFalse(results["exact_threshold_met"])
        self.assertFalse(results["exact_nash_conv_zero"])

        counters = results["exact_counters"]
        bounds = {
            "structural_node_visits": 27_351,
            "weighted_row_operations": 3_610_332,
            "active_world_node_visits": 92_664,
            "consumed_policy_rows": 38_016,
            "policy_edge_multiplications": 85_536,
            "terminal_world_contributions": 48_708,
            "exact_fraction_operations": 1_000_000,
            "max_fraction_bits": 65_536,
        }
        for name, cap in bounds.items():
            self.assertGreaterEqual(counters[name], 0, name)
            self.assertLessEqual(counters[name], cap, name)
        for name, expected in {
            "structural_node_visits": 27_351,
            "rank_keys": 276,
            "five_card_calls": 5_796,
            "independent_showdown_sign_checks": 396,
            "policy_rows": 3_606,
            "policy_action_slots": 8_046,
            "public_nodes": 3_039,
            "public_decisions": 1_254,
            "terminal_nodes": 1_780,
            "chance_nodes": 5,
            "chance_edges": 240,
            "depth": 9,
            "chance_grouping": False,
        }.items():
            self.assertEqual(counters[name], expected, name)

        # Independently fixed full-request admission and API profile metadata.
        payload = json.loads(policy_raw)
        expected_profile = {
            "iterations": 750, "requested_iterations": 750, "discard": 250,
            "source_iteration_window": [251, 750], "averaged_sweeps": 500,
            "average_weight_sum": 250_250,
            "requested_regret_passes": 1_500,
            "requested_average_passes": 500,
            "requested_total_traversal_passes": 2_000,
            "deals": 9, "compatible_pairs": 9, "worlds": 396,
            "worlds_materialized": 396, "info_sets": 3_606,
            "public_nodes": 1_254, "public_states": 3_039,
            "terminal_nodes": 1_780, "chance_nodes": 5,
            "world_traversal_nodes": 32, "tree_actions": 2_798,
            "public_state_limit": 250_000, "public_node_limit": 10_000,
            "public_batch_edge_limit": 250_000, "training_calls": 1,
        }
        for name, expected in expected_profile.items():
            self.assertEqual(payload[name], expected, name)
        self.assertEqual(len(payload["strategy"]), 3_606)
        self.assertEqual(payload["resource_usage"], {
            "full_requested_world_node_work": 28_512_000,
            "full_requested_world_node_work_limit": 30_000_000,
            "full_requested_dense_hand_state_pass_work": 20_540_601,
            "full_requested_dense_hand_state_pass_work_limit": 30_000_000,
            "info_action_slots": 8_046,
            "info_action_slots_limit": 1_000_000,
            "prefix_hand_edges": 405,
            "prefix_hand_edge_limit": 250_000,
        })

        # Independent profile replay uses literal masses/signs and the numeric
        # rules tree, while preserving each source binary64 probability exactly.
        independent_profile = _profile_value_from_public_tree(
            reference.model()[5], _literal_worlds(), json.loads(policy_raw))
        self.assertEqual(independent_profile, exact["value_oop"])
        self.assertEqual(independent_profile, Fraction(results["profile_value_fraction"]))


if __name__ == "__main__":
    unittest.main()
