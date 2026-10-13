"""Independent serialized turn/river policy replay checks."""
from copy import deepcopy
from fractions import Fraction
from itertools import product
import unittest

from pokerlab.matrix_free_river import solve_matrix_free_river
from pokerlab.matrix_free_turn import solve_matrix_free_turn
from pokerlab.postflop_solver import solve_postflop
from pokerlab.river_config import RiverConfig
from scripts.river_analytical import (
    equilibrium as polar_equilibrium, metrics as polar_metrics, serialized_profile,
)
from scripts.turn_river_validation import (
    _Chance, _Decision, _Terminal, _best_response,
    compare_result, replay_policy,
)


class TurnRiverIndependentValidationTests(unittest.TestCase):
    def test_river_polarized_anchor_matches_independent_rational_game(self):
        board = "2c7d9hJsKd"
        config = RiverConfig(100, 500, (1.0,), (), 0, False)
        result = solve_matrix_free_river(
            board, "AsAh,3c4c", "QsQh", config,
            iterations=300, algorithm="cfrplus",
        )
        replay = replay_policy(result, "AsAh,3c4c", "QsQh",
                               board=board, config=config)
        known = polar_metrics(serialized_profile(result))
        self.assertEqual(replay["world_count"], 2)
        for field, expected in zip(("value_oop", "oop_best_response_value",
                                    "ip_best_response_value"), known):
            self.assertAlmostEqual(replay[field], float(expected), delta=1e-9)
        self.assertAlmostEqual(replay["nash_conv"], float(known[1] + known[2]), delta=1e-9)
        self.assertTrue(compare_result(result, replay))

    def test_known_rational_equilibrium_profile_has_zero_gap(self):
        board = "2c7d9hJsKd"
        oop, ip = "AsAh,3c4c", "QsQh"
        config = RiverConfig(100, 500, (1.0,), (), 0, False)
        result = solve_matrix_free_river(board, oop, ip, config,
                                         iterations=10, algorithm="vanilla")
        profile, known_value = polar_equilibrium()
        anchored = deepcopy(result)
        for row in anchored["strategy"]:
            player = 0 if row["player"] == "oop" else 1
            label = ("nuts" if row["hand"] == "AhAs" else
                     "air" if row["hand"] == "3c4c" else "catcher")
            history = tuple(token.split("@")[0] for token in row["history"])
            key = (player, label, history)
            expected = profile[key]
            names = tuple(action["name"] for action in row["actions"])
            canonical = ("check", "bet") if "check" in names else ("fold", "call")
            for action, name in zip(row["actions"], names):
                action["probability"] = float(expected[canonical.index(name)])
        replay = replay_policy(anchored, oop, ip, board=board, config=config)
        self.assertAlmostEqual(replay["value_oop"], float(known_value), delta=1e-9)
        self.assertAlmostEqual(replay["nash_conv"], 0.0, delta=1e-9)
        self.assertAlmostEqual(replay["exploitability"], 0.0, delta=1e-9)

    def test_turn_weighted_blocker_replay_for_all_algorithms(self):
        board = "2c5d9hJc"
        oop = "AsAh:0.7,KsKh:0.3,QsQh:0.5"
        ip = "AsKc:0.2,AhKd:0.6,QcQd:1,TcTh:0.4"
        config = RiverConfig(20, (18, 32), (0.5,), (0.5,), 1, True)
        runouts = ("As", "Kc", "7s")
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                result = solve_matrix_free_turn(
                    board, oop, ip, config, runouts=runouts,
                    iterations=10, algorithm=algorithm,
                )
                replay = replay_policy(result, oop, ip, board=board,
                                       config=config, runouts=runouts)
                self.assertTrue(compare_result(result, replay, 1e-9))
                self.assertEqual(replay["world_count"], result["compatible_world_count"])
                self.assertAlmostEqual(sum(replay["river_probabilities"].values()), 1.0)
                self.assertGreater(max(replay["river_probabilities"].values()) -
                                   min(replay["river_probabilities"].values()), 0.0)

    def test_river_weighted_blocker_replay_for_all_algorithms_and_distinct_sizing(self):
        board = "2c7d9hJsKd"
        oop = "AsAh:0.7,KsKh:0.3,QsQh:0.5"
        ip = "AsKc:0.2,QcQd:1,TcTh:0.4"
        config = RiverConfig(17.3, (29.1, 41.7), (0.13, 0.37),
                             (0.41,), 1, True)
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                result = solve_matrix_free_river(
                    board, oop, ip, config, iterations=10, algorithm=algorithm,
                )
                replay = replay_policy(result, oop, ip, board=board, config=config)
                self.assertTrue(compare_result(result, replay, 1e-9))

    def test_turn_all_in_calls_continue_to_river_without_river_decisions(self):
        board = "2c5d9hJc"
        oop, ip = "AsAh", "KsKh"
        config = RiverConfig(20, (5, 10), (0.5,), (), 0, True)
        result = solve_matrix_free_turn(board, oop, ip, config,
                                        iterations=10, algorithm="vanilla")
        replay = replay_policy(result, oop, ip, board=board, config=config)
        self.assertTrue(compare_result(result, replay))
        self.assertEqual(replay["worlds"], 44)
        self.assertFalse(any(row["street"] == "river" and
                             row["history"][:1] == ["all_in@5"]
                             for row in result["strategy"]))

    def test_turn_replay_with_distinct_decimal_river_sizing(self):
        board = "2c5d9hJc"
        oop, ip = "AsAh,KsKh", "QcQd,TcTh"
        config = RiverConfig(17.3, (29.1, 41.7), (0.13, 0.37), (0.41,), 1, True)
        river = RiverConfig(17.3, (29.1, 41.7), (0.23, 0.61), (0.17,), 1, True)
        result = solve_matrix_free_turn(
            board, oop, ip, config, river_config=river,
            runouts=("As", "Kc", "7s"), iterations=10, algorithm="dcfr",
        )
        replay = replay_policy(result, oop, ip, board=board,
                               config=config, river_config=river,
                               runouts=("As", "Kc", "7s"))
        self.assertTrue(compare_result(result, replay))

    def test_short_all_in_raise_does_not_reopen_action(self):
        board = "2c7d9hJsKd"
        oop, ip = "AsAh", "QcQh"
        config = RiverConfig(100, (100, 15), (0.1,), (1.0,), 2, True)
        result = solve_matrix_free_river(board, oop, ip, config,
                                         iterations=10, algorithm="vanilla")
        replay = replay_policy(result, oop, ip, board=board, config=config)
        self.assertTrue(compare_result(result, replay))
        row = next(row for row in result["strategy"]
                   if row["player"] == "oop" and
                   row["history"] == ["bet@10", "all_in@15"])
        self.assertEqual([action["name"] for action in row["actions"]], ["fold", "call"])

    def test_orphan_private_hands_are_checked_only_on_supported_river_prefixes(self):
        board = "2c5d9hJc"
        oop, ip = "AsAh,KsKh", "AsKc,KdTc"
        config = RiverConfig(20, 40, (0.5,), (), 0, False)
        runouts = ("Kd", "Kh")
        result = solve_matrix_free_turn(board, oop, ip, config,
                                        runouts=runouts, iterations=10,
                                        algorithm="vanilla")
        replay = replay_policy(result, oop, ip, board=board,
                               config=config, runouts=runouts)
        self.assertTrue(compare_result(result, replay))
        as_ah = [row for row in result["strategy"] if row["player"] == "oop" and
                 row["hand"] == "AhAs" and row["street"] == "river"]
        ks_kh = [row for row in result["strategy"] if row["player"] == "oop" and
                 row["hand"] == "KhKs" and row["street"] == "river"]
        self.assertEqual({row["board"][-1] for row in as_ah}, {"Kh"})
        self.assertEqual({row["board"][-1] for row in ks_kh}, {"Kd"})

    def test_turn_best_response_sums_hidden_rivers_before_maximizing(self):
        worlds = [
            {"hands": (("As", "Ah"), ("Ks", "Kh")), "river": "2s",
             "weight": Fraction(1, 2), "sign": 1},
            {"hands": (("As", "Ah"), ("Ks", "Kh")), "river": "3s",
             "weight": Fraction(1, 2), "sign": -1},
        ]
        left = _Chance((), {
            "2s": _Terminal("fold", (0.0, 0.0), 0),
            "3s": _Terminal("fold", (0.0, 0.0), 1),
        })
        right = _Chance((), {
            "2s": _Terminal("fold", (0.0, 0.0), 1),
            "3s": _Terminal("fold", (0.0, 0.0), 0),
        })
        root = _Decision(0, (), (), (None, None), (left, right))
        self.assertEqual(_best_response(root, worlds, {}, 0, 2.0), 0.0)

    def test_materialized_turn_result_replays_against_same_independent_oracle(self):
        board = "2c5d9hJc"
        oop, ip = "AsAh:0.7,KsKh:0.3", "AsKc:0.2,QcQd:1"
        config = RiverConfig(30, (28, 37), (0.37,), (0.41,), 1, True)
        runouts = ("As", "Kc", "7s")
        result = solve_postflop(
            board, oop, ip, config, runouts=runouts, iterations=10,
            algorithm="dcfr", traversal="public-batched",
            diagnostics="public-batched",
        )
        replay = replay_policy(result, oop, ip, board=board,
                               config=config, runouts=runouts)
        self.assertTrue(compare_result(result, replay, 1e-9))

    def test_full_deck_single_pair_has_all_44_legal_rivers(self):
        board = "2c5d9hJc"
        oop, ip = "AsAh", "KsKh"
        config = RiverConfig(10, 20, (0.5,), (), 0, False)
        result = solve_matrix_free_turn(board, oop, ip, config,
                                        iterations=10, algorithm="vanilla")
        replay = replay_policy(result, oop, ip, board=board, config=config)
        self.assertEqual(replay["world_count"], 44)
        self.assertEqual(len(replay["river_probabilities"]), 44)
        self.assertTrue(all(abs(value - 1 / 44) < 1e-15
                            for value in replay["river_probabilities"].values()))
        self.assertTrue(compare_result(result, replay))

    def test_tiny_policy_best_responses_match_exhaustive_pure_rows(self):
        board = "2c7d9hJsKd"
        oop, ip = "AsAh,3c4c", "QsQh"
        config = RiverConfig(20, 40, (0.5,), (), 0, False)
        result = solve_matrix_free_river(board, oop, ip, config,
                                         iterations=10, algorithm="vanilla")
        baseline = replay_policy(result, oop, ip, board=board, config=config)
        for player, target in (("oop", "oop_best_response_value"),
                               ("ip", "ip_best_response_value")):
            rows = [index for index, row in enumerate(result["strategy"])
                    if row["player"] == player]
            action_counts = [len(result["strategy"][index]["actions"]) for index in rows]
            values = []
            for choices in product(*(range(count) for count in action_counts)):
                changed = deepcopy(result)
                for index, selected in zip(rows, choices):
                    actions = changed["strategy"][index]["actions"]
                    actions[:] = [dict(action, probability=float(i == selected))
                                  for i, action in enumerate(actions)]
                values.append(replay_policy(changed, oop, ip, board=board,
                                            config=config)["value_oop"])
            expected = max(values) if player == "oop" else -min(values)
            self.assertAlmostEqual(baseline[target], expected, delta=1e-9)

    def test_rejects_policy_and_metric_corruption(self):
        board = "2c5d9hJc"
        oop, ip = "AsAh", "KsKh"
        config = RiverConfig(10, 20, (0.5,), (), 0, False)
        result = solve_matrix_free_turn(board, oop, ip, config,
                                        runouts=("3c",), iterations=10,
                                        algorithm="vanilla")
        replay = replay_policy(result, oop, ip, board=board, config=config,
                               runouts=("3c",))
        mutations = []
        corrupt = deepcopy(result); corrupt["strategy"].pop(); mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"].append(deepcopy(corrupt["strategy"][0])); mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["board"] = ["As"]; mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["street"] = "flop"; mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["history"] = ["future@3c"]; mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["future_card"] = "3c"; mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["actions"].reverse(); mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["actions"][0]["name"] = "future_card"; mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["actions"][0]["amount"] = True; mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["actions"][0]["raise_to"] += 1; mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["actions"][0]["history_key"] = "future@3c"; mutations.append(corrupt)
        for bad_probability in (2.0, 1.1, -0.1, float("nan"), float("inf")):
            corrupt = deepcopy(result)
            corrupt["strategy"][0]["actions"][0]["probability"] = bad_probability
            mutations.append(corrupt)
        for corrupt in mutations:
            with self.subTest(corrupt=corrupt["strategy"][0]):
                with self.assertRaises(ValueError):
                    replay_policy(corrupt, oop, ip, board=board, config=config,
                                  runouts=("3c",))
        corrupt = deepcopy(result)
        corrupt["value_oop"] += 0.01
        with self.assertRaises(ValueError):
            compare_result(corrupt, replay)
        corrupt = deepcopy(result)
        corrupt["nash_conv"] = float("nan")
        with self.assertRaises(ValueError):
            compare_result(corrupt, replay)


if __name__ == "__main__":
    unittest.main()
