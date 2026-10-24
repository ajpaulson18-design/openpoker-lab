"""Compiled river policy controls, enabled only with an explicit native build."""
from contextlib import ExitStack
from fractions import Fraction
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pokerlab import native_river_solver as adapter
from pokerlab import native_fixed_street, public_diagnostics
from pokerlab.river_tail_adapter import solve_river_tail
from pokerlab.river_config import RiverConfig
from scripts import benchmark_river_heldout_quality as evidence
from scripts import turn_river_validation as rules

BUILD_DIRECTORY = os.environ.get("OPENPOKER_NATIVE_TRAIN_BUILD_DIR")
NATIVE_AVAILABLE = bool(BUILD_DIRECTORY and Path(BUILD_DIRECTORY).is_dir())
WIDER_CASE = {
    "id": "river-eight-hand-weighted-blockers",
    "board": "AhKdQcJs2d",
    "oop": "AsTc:1,3c4c:0.25,9c9d:0.75,5c6c:0.5,AcTs:0.5,KhKs:0.75,7c8c:0.25,ThTd:1",
    "ip": "AsKh:0.5,QhTh:0.75,8c8d:0.25,6c7d:1,Ac9s:0.75,KcKs:0.5,3c5c:1,9hTc:0.25",
    "config": evidence.CASES[0]["config"],
}


@unittest.skipUnless(NATIVE_AVAILABLE, "Explicit native trainer build not configured")
class CompiledNativeRiverTests(unittest.TestCase):
    def _compare_and_replay(self, case):
        config = RiverConfig.from_dict(case["config"])
        audited = []
        for iterations in (10, 100):
            with self.subTest(case=case["id"], iterations=iterations):
                actual = adapter.solve_native_river(
                    case["board"], case["oop"], case["ip"], config,
                    iterations=iterations, build_directory=BUILD_DIRECTORY)
                expected = solve_river_tail(
                    case["board"], case["oop"], case["ip"], config,
                    iterations=iterations, discard=0)
                self.assertEqual(len(actual["strategy"]), len(expected["strategy"]))
                for row, reference in zip(actual["strategy"], expected["strategy"]):
                    self.assertEqual({key: value for key, value in row.items() if key != "actions"},
                                     {key: value for key, value in reference.items() if key != "actions"})
                    self.assertEqual(len(row["actions"]), len(reference["actions"]))
                    for action, reference_action in zip(row["actions"], reference["actions"]):
                        self.assertEqual({key: value for key, value in action.items() if key != "probability"},
                                         {key: value for key, value in reference_action.items() if key != "probability"})
                        self.assertLessEqual(abs(action["probability"] - reference_action["probability"]), 1e-9)
                for metric in evidence.METRICS:
                    self.assertLessEqual(abs(actual[metric] - expected[metric]), 1e-8, metric)
                self.assertEqual(actual["native_training"]["reduction"], "public-batched")
                self.assertEqual(actual["native_training"]["admission"]["requested_iterations"], iterations)
                self.assertEqual(actual["average_weight_sum"], iterations * (iterations + 1) // 2)
                self.assertEqual(actual["source_iteration_window"], [1, iterations])
                self.assertEqual(actual["worlds"], expected["worlds"])
                self.assertEqual(actual["info_sets"], expected["info_sets"])

                with tempfile.TemporaryDirectory(prefix="native-river-saved-") as output:
                    path = Path(output) / "policy.json"
                    path.write_bytes(evidence._pretty_json_bytes(actual))
                    saved = json.loads(path.read_bytes())
                with ExitStack() as stack:
                    for owner, name in (
                        (adapter, "solve_native_river"),
                        (adapter, "_enumerate_worlds"),
                        (adapter, "_build_postflop_tree"),
                        (adapter, "evaluate_profile"),
                        (native_fixed_street, "train_native_fixed_street"),
                        (public_diagnostics, "evaluate_profile"),
                    ):
                        stack.enter_context(patch.object(owner, name,
                            side_effect=AssertionError("Production helper reached independent replay")))
                    board = rules.cards(case["board"], 5)
                    oracle = rules.replay_policy(saved, case["oop"], case["ip"], board=board, config=config)
                    for metric in evidence.METRICS:
                        self.assertLessEqual(abs(saved[metric] - oracle[metric]), 1e-9, metric)
                    ranges = (rules.expand_range(case["oop"], board), rules.expand_range(case["ip"], board))
                    worlds, selected = rules._worlds(board, ranges, None)
                    tree = rules._public_tree(board, rules._config(config, "config"),
                                              rules._config(config, "config"), selected, worlds)
                    nodes = rules._collect_nodes(tree)
                    policies = rules._validate_policy(saved, tree, nodes, worlds, board, selected,
                                                       runouts_were_omitted=True)
                    exact, _ = evidence._exact_result(tree, worlds, policies, config, saved)
                    self.assertEqual(exact["status"], "admitted")
                    self.assertEqual(exact["chance_groupings"]["scan"]["metrics_fraction"],
                                     exact["chance_groupings"]["partition"]["metrics_fraction"])
                    metrics = {key: Fraction(value) for key, value in exact["metrics_fraction"].items()}
                    for metric in evidence.METRICS:
                        self.assertLessEqual(abs(float(metrics[metric]) - saved[metric]), 1e-9, metric)
                    lower = Fraction(exact["lower_value_bound_fraction"])
                    upper = Fraction(exact["upper_value_bound_fraction"])
                    self.assertEqual(metrics["nash_conv"], upper - lower)
                    self.assertLessEqual(lower, metrics["value_oop"])
                    self.assertLessEqual(metrics["value_oop"], upper)
                    audited.append((actual, oracle, exact))
        return audited

    def test_two_weighted_blocker_tie_raise_and_refund_games(self):
        for case in evidence.CASES:
            self._compare_and_replay(case)

    def test_eight_hand_ranges_preserve_full_policy_and_physical_responses(self):
        self._compare_and_replay(WIDER_CASE)

    def test_board_royal_flush_known_zero_value_is_inside_exact_interval(self):
        # The board gives every private hand the same royal flush. Either player
        # guarantees zero by checking/calling without folding, hence game value 0.
        # A finite trained policy can retain fold mistakes and a nonzero gap.
        case = {
            "id": "board-royal-flush-zero-equilibrium-value",
            "board": "AcKcQcJcTc",
            "oop": "2d3d:0.75,4d5d:0.25",
            "ip": "6h7h:1,8h9h:0.5",
            "config": evidence.CASES[0]["config"],
        }
        audited = self._compare_and_replay(case)
        self.assertEqual(len(audited), 2)
        for actual, oracle, exact in audited:
            self.assertLessEqual(Fraction(exact["lower_value_bound_fraction"]), 0)
            self.assertGreaterEqual(Fraction(exact["upper_value_bound_fraction"]), 0)
            self.assertGreaterEqual(oracle["oop_best_response_value"], -1e-9)
            self.assertGreaterEqual(oracle["ip_best_response_value"], -1e-9)


if __name__ == "__main__":
    unittest.main()
