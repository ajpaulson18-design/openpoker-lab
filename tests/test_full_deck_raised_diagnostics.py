"""Production diagnostic checks against exact hand-written full-deck anchors.

Trainer entry points are replaced with a complete deterministic check/call
policy. No training is executed or measured by these tests.
"""
from fractions import Fraction as F
import unittest
from unittest.mock import patch

from pokerlab import matrix_free_turn, postflop_solver
from pokerlab.river_tree import _Node
from scripts.full_deck_raised_fixture import FIXTURE
from scripts import turn_river_validation as rules


def fixed_check_call_profile(root, infos):
    nodes = {}
    pending = [root]
    while pending:
        node = pending.pop()
        if isinstance(node, postflop_solver._Chance):
            pending.extend(node.branches.values())
        elif isinstance(node, _Node):
            nodes[node.player, node.history] = node
            pending.extend(node.children)
    result = {}
    for player, hand_index, history in infos:
        node = nodes[player, history]
        available = {action.name: i for i, action in enumerate(node.actions)}
        chosen = available["check"] if "check" in available else available["call"]
        result[player, hand_index, history] = tuple(float(i == chosen) for i in range(len(node.actions)))
    return result


class FullDeckRaisedProductionDiagnosticsTests(unittest.TestCase):
    def test_both_backends_replay_exact_check_call_values_without_training(self):
        expected = dict(value_oop=F(-2500, 231), value_ip=F(2500, 231),
                        oop_best_response_value=F(2350, 231), ip_best_response_value=F(14975, 231),
                        oop_best_response_gain=F(4850, 231), ip_best_response_gain=F(12475, 231),
                        nash_conv=F(75), exploitability=F(75, 2))
        for backend in ("materialized", "matrix-free"):
            with self.subTest(backend=backend):
                if backend == "materialized":
                    def inject(root, worlds, infos, *args, **kwargs):
                        return fixed_check_call_profile(root, infos)
                    target = "pokerlab.postflop_solver.train_public_batched"
                    solver = postflop_solver.solve_postflop
                    options = dict(traversal="public-batched", diagnostics="public-batched")
                else:
                    def inject(root, infos, *args, **kwargs):
                        return fixed_check_call_profile(root, infos)
                    target = "pokerlab.matrix_free_turn.train_ranked_turn"
                    solver = matrix_free_turn.solve_matrix_free_turn
                    options = {}
                with patch(target, side_effect=inject) as replaced_trainer:
                    result = solver(FIXTURE["board"], FIXTURE["oop"], FIXTURE["ip"], FIXTURE["config"],
                                    river_config=FIXTURE["config"], iterations=10, algorithm="cfrplus", **options)
                self.assertEqual(replaced_trainer.call_count, 1)
                self.assertEqual(len(result["strategy"]), 2404)
                for metric, exact in expected.items():
                    self.assertAlmostEqual(result[metric], float(exact), delta=1e-12, msg=metric)
                independent = rules.replay_policy(result, FIXTURE["oop"], FIXTURE["ip"],
                                                  board=FIXTURE["board"], config=FIXTURE["config"])
                rules.compare_result(result, independent, tolerance=1e-9)


if __name__ == "__main__":
    unittest.main()
