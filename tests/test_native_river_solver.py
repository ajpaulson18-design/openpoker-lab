"""No-training admission and serialization checks for the native river API."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from pokerlab import native_fixed_street
from pokerlab import native_river_solver as adapter
from pokerlab import postflop_solver
from pokerlab.native_fixed_street import admit_native_shape
from pokerlab.river_config import RiverConfig
from scripts import turn_river_validation as independent


BOARD = "AhKdQcJs2d"
OOP = "AsTc:1,3c4c:0.25,9c9d:0.75,5c6c:0.5"
IP = "AsKh:0.5,QhTh:0.75,8c8d:0.25,6c7d:1"
CONFIG = RiverConfig(pot=100, effective_stack=(120, 80), bet_sizes=(0.33,),
                     raise_sizes=(0.25,), max_raises=1, include_all_in=True)
SHORT_BOARD = "9h8h7h2c2d"
SHORT_OOP = "6h5h:0.75,AhKh:0.25,9c9d:1,2h2s:0.5"
SHORT_IP = "JhTh:0.5,QhKh:1,8c8d:0.75,7c7d:0.25"
SHORT_CONFIG = RiverConfig(pot=100, effective_stack=(70, 80), bet_sizes=(0.25,),
                           raise_sizes=(0.25,), max_raises=1, include_all_in=True)


class NativeRiverAdapterTests(unittest.TestCase):
    def test_invalid_request_rejects_before_tree_or_executable_lookup(self):
        with patch.object(adapter, "_build_postflop_tree", side_effect=AssertionError("tree")), \
             patch.object(native_fixed_street, "_backend", side_effect=AssertionError("backend")):
            for kwargs, message in (
                    ({"iterations": True, "build_directory": "unused"}, "iterations"),
                    ({"iterations": 9, "build_directory": "unused"}, "iterations"),
                    ({"iterations": 10.0, "build_directory": "unused"}, "iterations"),
                    ({"iterations": 10, "build_directory": None}, "build_directory")):
                with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, message):
                    adapter.solve_native_river(BOARD, OOP, IP, CONFIG, **kwargs)
            with self.assertRaisesRegex(ValueError, "five board cards"):
                adapter.solve_native_river(BOARD[:-2], OOP, IP, CONFIG,
                                           iterations=10, build_directory="unused")

    def test_mocked_native_profile_replays_with_independent_numeric_rules(self):
        captured = {}

        def fake_native(root, worlds, infos, iterations, algorithm, *, pot,
                        build_directory, reduction):
            captured.update(worlds=worlds, infos=infos, iterations=iterations,
                            algorithm=algorithm, build_directory=build_directory,
                            reduction=reduction)
            active = [set(), set()]
            for h0, h1, _mass, _signed in worlds:
                active[0].add(h0)
                active[1].add(h1)
            slots = sum(count for count in infos.values())
            states = sum(1 for _ in native_fixed_street._walk(root, pot))
            action_names = set()
            unequal_terminals = []
            pending = [root]
            while pending:
                node = pending.pop()
                if isinstance(node, postflop_solver._Node):
                    action_names.update(action.name for action in node.actions)
                    pending.extend(node.children)
                elif isinstance(node, postflop_solver._Terminal):
                    if node.contributions[0] != node.contributions[1]:
                        unequal_terminals.append(node.contributions)
            captured.update(action_names=action_names,
                            unequal_terminals=unequal_terminals)
            admission = admit_native_shape(
                states, len(worlds), slots, iterations, algorithm,
                reduction=reduction,
                hand_counts=(len(active[0]), len(active[1])))
            averages = {key: [1.0 / actions] * actions
                        for key, actions in infos.items()}
            return averages, {"backend": "mock-native", "reduction": reduction,
                              "admission": admission}

        with patch.object(adapter.native_fixed_street,
                          "train_native_fixed_street", side_effect=fake_native):
            result = adapter.solve_native_river(
                BOARD, OOP, IP, CONFIG, iterations=100,
                build_directory="explicit-build-dir")

        self.assertEqual(captured["iterations"], 100)
        self.assertEqual(captured["algorithm"], "cfrplus")
        self.assertEqual(captured["reduction"], "public-batched")
        self.assertTrue(all(len(key) == 3 and isinstance(key[1], int)
                            for key in captured["infos"]))
        self.assertTrue(all(len(world) == 4 for world in captured["worlds"]))
        self.assertTrue(all(abs(world[3]) <= world[2] for world in captured["worlds"]))
        self.assertEqual(result["strategy_schema"], "postflop-strategy-v1")
        self.assertEqual(result["solver_version"], adapter.SOLVER_VERSION)
        self.assertEqual(result["iterations"], result["requested_iterations"])
        self.assertEqual(result["requested_regret_passes"], 200)
        self.assertEqual(result["requested_average_passes"], 100)
        self.assertEqual(result["requested_total_traversal_passes"], 300)
        self.assertEqual(
            result["resource_usage"]["native_training_admission"]["requested_iterations"],
            100)
        self.assertEqual(result["training_calls"], 1)
        self.assertEqual(result["native_training"]["backend"], "mock-native")

        replay = independent.replay_policy(result, OOP, IP, board=BOARD, config=CONFIG)
        for metric in ("value_oop", "value_ip", "oop_best_response_value",
                       "ip_best_response_value", "oop_best_response_gain",
                       "ip_best_response_gain", "nash_conv", "exploitability"):
            self.assertAlmostEqual(result[metric], replay[metric], delta=1e-9)
        self.assertEqual(result["worlds"], result["compatible_pairs"])
        self.assertEqual(result["chance_nodes"], 0)

    def test_short_unequal_stack_all_in_refund_tree_is_replayed(self):
        captured = {}

        def uniform_native(root, worlds, infos, iterations, algorithm, *, pot,
                           build_directory, reduction):
            active = [set(), set()]
            for h0, h1, _mass, _signed in worlds:
                active[0].add(h0)
                active[1].add(h1)
            slots = sum(infos.values())
            states = sum(1 for _ in native_fixed_street._walk(root, pot))
            admission = admit_native_shape(
                states, len(worlds), slots, iterations, algorithm,
                reduction=reduction,
                hand_counts=(len(active[0]), len(active[1])))
            actions, unequal = set(), []
            pending = [root]
            while pending:
                node = pending.pop()
                if isinstance(node, postflop_solver._Node):
                    actions.update(action.name for action in node.actions)
                    pending.extend(node.children)
                elif isinstance(node, postflop_solver._Terminal):
                    if node.contributions[0] != node.contributions[1]:
                        unequal.append(node.contributions)
            captured.update(actions=actions, unequal=unequal)
            return ({key: [1.0 / count] * count for key, count in infos.items()},
                    {"backend": "mock-native", "reduction": reduction,
                     "admission": admission})

        with patch.object(adapter.native_fixed_street,
                          "train_native_fixed_street", side_effect=uniform_native):
            result = adapter.solve_native_river(
                SHORT_BOARD, SHORT_OOP, SHORT_IP, SHORT_CONFIG, iterations=10,
                build_directory="explicit-build-dir")
        self.assertIn("all_in", captured["actions"])
        self.assertTrue(captured["unequal"])
        replay = independent.replay_policy(
            result, SHORT_OOP, SHORT_IP, board=SHORT_BOARD, config=SHORT_CONFIG)
        for metric in ("value_oop", "value_ip", "oop_best_response_value",
                       "ip_best_response_value", "nash_conv", "exploitability"):
            self.assertAlmostEqual(result[metric], replay[metric], delta=1e-9)

    def test_full_requested_world_and_dense_guards_precede_native_launch(self):
        with patch.object(native_fixed_street, "train_native_fixed_street",
                          side_effect=AssertionError("Rejected request reached trainer")):
            for constant, cap, message in (
                ("_RIVER_WORLD_NODE_WORK", 4_199, "world-node"),
                ("MAX_DENSE_HAND_STATE_PASS_WORK", 3_563, "dense hand-state"),
                ("MAX_INFO_ACTION_SLOTS", 103, "action slots"),
            ):
                with self.subTest(resource=constant), patch.object(adapter, constant, cap):
                    with self.assertRaisesRegex(ValueError, message):
                        adapter.solve_native_river(BOARD, OOP, IP, CONFIG,
                                                   iterations=10, build_directory="unused")

    def test_native_shape_rejection_precedes_executable_lookup(self):
        with patch.object(native_fixed_street, "_backend",
                          side_effect=AssertionError("Rejected request reached backend")), \
             patch.object(native_fixed_street, "admit_native_shape",
                          side_effect=ValueError("native modeled work rejection")):
            with self.assertRaisesRegex(ValueError, "native modeled work"):
                adapter.solve_native_river(BOARD, OOP, IP, CONFIG,
                                           iterations=10, build_directory="unused")

    def test_candidate_admission_precedes_ranking_and_public_tree(self):
        with patch.object(postflop_solver, "_MAX_CANDIDATE_HAND_ITERATIONS", 159), \
             patch.object(postflop_solver, "rank_hand", side_effect=AssertionError("ranking")), \
             patch.object(adapter, "_build_postflop_tree", side_effect=AssertionError("tree")), \
             patch.object(native_fixed_street, "_backend", side_effect=AssertionError("backend")):
            with self.assertRaisesRegex(ValueError, "candidate"):
                adapter.solve_native_river(BOARD, OOP, IP, CONFIG,
                                           iterations=10, build_directory="unused")

    def test_invalid_range_rejects_before_public_tree_construction(self):
        with patch.object(adapter, "_build_postflop_tree",
                          side_effect=AssertionError("tree must not be built")):
            with self.assertRaises((TypeError, ValueError)):
                adapter.solve_native_river(BOARD, "not-a-range", IP, CONFIG,
                                           iterations=10,
                                           build_directory="explicit-build-dir")


if __name__ == "__main__":
    unittest.main()
