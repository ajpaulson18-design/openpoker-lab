"""Differential checks for the opt-in planned CFR traversal."""
import unittest

from pokerlab.cfr import best_response, evaluate, train as train_recursive
from pokerlab.planned_cfr import train as train_planned
from pokerlab.river_config import RiverConfig
from pokerlab.river_tree import _terminal_value
from pokerlab.turn_solver import (
    _Chance, _chance_child, _chance_partitions, _enumerate_worlds, _node_key,
    _tree, solve_turn_river,
)


BOARD = "Js8d4c2h"
OOP = "AsAh:0.5,KsKh:1"
IP = "AcAd:1,KcKd:0.75"
RUNOUTS = ("Ks", "3c")
CONFIG = RiverConfig(
    pot=100, effective_stack=220, bet_sizes=(0.5,), raise_sizes=(),
    max_raises=0, include_all_in=False,
)
RIVER_CONFIG = RiverConfig(
    pot=100, effective_stack=220, bet_sizes=(0.75,), raise_sizes=(),
    max_raises=0, include_all_in=False,
)


def build_fixture(runouts=RUNOUTS):
    """Build a small weighted, blocker-sensitive conditional chance game."""
    hands, worlds, selected, _ = _enumerate_worlds(
        BOARD, OOP, IP, runouts, iterations=100,
    )
    reachable = tuple(card for card in selected if any(w[4] == card for w in worlds))
    root, nodes, _, _ = _tree(CONFIG, RIVER_CONFIG, reachable)
    active_hands = ({w[0] for w in worlds}, {w[1] for w in worlds})
    river_hands = {
        (player, river): {w[player] for w in worlds if w[4] == river}
        for player in (0, 1) for river in reachable
    }
    infos = {}
    for (player, history), node in nodes.items():
        reveal = next((token[6:] for token in history if token.startswith("river@")), None)
        allowed = active_hands[player] if reveal is None else river_hands[(player, reveal)]
        for hand_index in sorted(allowed):
            infos[(player, hand_index, history)] = len(node.actions)
    payoff = lambda node, world: _terminal_value(node, world[3], CONFIG.pot)
    return hands, worlds, root, nodes, infos, payoff


def assert_profiles_equal(test, expected, actual, places=12):
    test.assertEqual(expected.keys(), actual.keys())
    for key in expected:
        test.assertEqual(len(expected[key]), len(actual[key]), key)
        for left, right in zip(expected[key], actual[key]):
            test.assertAlmostEqual(left, right, places=places, msg=repr(key))


class PlannedCFRTests(unittest.TestCase):
    def test_profiles_values_and_exact_best_responses_match_recursive_reference(self):
        hands, worlds, root, _, infos, payoff = build_fixture()
        self.assertEqual(len(worlds), 6)  # one private hand blocks the Ks branch
        self.assertAlmostEqual(sum(world[2] for world in worlds), 1.0, places=14)
        pair_mass = {}
        for oop_index, ip_index, weight, _, river in worlds:
            pair = ("".join(hands[0][oop_index]), "".join(hands[1][ip_index]))
            pair_mass[pair] = pair_mass.get(pair, 0.0) + weight
            if pair[0] == "KhKs":
                self.assertNotEqual(river, "Ks")
        self.assertEqual(set(pair_mass), {
            ("AhAs", "AcAd"), ("AhAs", "KcKd"),
            ("KhKs", "AcAd"), ("KhKs", "KcKd"),
        })
        for pair, mass in {
            ("AhAs", "AcAd"): 2 / 7,
            ("AhAs", "KcKd"): 3 / 14,
            ("KhKs", "AcAd"): 2 / 7,
            ("KhKs", "KcKd"): 3 / 14,
        }.items():
            self.assertAlmostEqual(pair_mass[pair], mass, places=14)
        for algorithm in ("vanilla", "dcfr"):
            for iterations in (20, 100):
                with self.subTest(algorithm=algorithm, iterations=iterations):
                    recursive = train_recursive(
                        root, worlds, infos, iterations, algorithm, payoff,
                        _node_key, _chance_child,
                    )
                    planned = train_planned(
                        root, worlds, infos, iterations, algorithm, payoff,
                        _node_key, _chance_child,
                    )
                    assert_profiles_equal(self, recursive, planned)

                    recursive_value = evaluate(
                        root, worlds, recursive, payoff, _node_key, _chance_child,
                    )
                    planned_value = evaluate(
                        root, worlds, planned, payoff, _node_key, _chance_child,
                    )
                    self.assertAlmostEqual(recursive_value, planned_value, places=12)
                    for player in (0, 1):
                        recursive_br = best_response(
                            player, root, worlds, recursive, payoff, _node_key,
                            _chance_partitions,
                        )
                        planned_br = best_response(
                            player, root, worlds, planned, payoff, _node_key,
                            _chance_partitions,
                        )
                        self.assertAlmostEqual(recursive_br, planned_br, places=12)

    def test_custom_node_key_and_chance_child_callbacks_are_honored(self):
        def custom_node_key(node, world):
            return ("custom",) + _node_key(node, world)

        _, worlds, root, nodes, _, payoff = build_fixture()
        active_hands = ({w[0] for w in worlds}, {w[1] for w in worlds})
        river_hands = {
            (player, river): {w[player] for w in worlds if w[4] == river}
            for player in (0, 1) for river in RUNOUTS
        }
        infos = {}
        for (player, history), node in nodes.items():
            reveal = next((token[6:] for token in history if token.startswith("river@")), None)
            allowed = active_hands[player] if reveal is None else river_hands[(player, reveal)]
            for hand_index in sorted(allowed):
                key = custom_node_key(node, (hand_index, hand_index, 1.0, 0, "3c"))
                infos[key] = len(node.actions)

        callback_calls = {"recursive": 0, "planned": 0}

        def chance_forced_to_3c(label):
            def choose(node, world):
                callback_calls[label] += 1
                if isinstance(node, _Chance):
                    return node.branches["3c"]
                return None
            return choose

        for algorithm in ("vanilla", "dcfr"):
            recursive = train_recursive(
                root, worlds, infos, 20, algorithm, payoff, custom_node_key,
                chance_forced_to_3c("recursive"),
            )
            planned = train_planned(
                root, worlds, infos, 20, algorithm, payoff, custom_node_key,
                chance_forced_to_3c("planned"),
            )
            assert_profiles_equal(self, recursive, planned)
        self.assertGreater(callback_calls["recursive"], 0)
        self.assertGreater(callback_calls["planned"], 0)

    def test_nonuniform_locked_strategy_is_exact_for_both_algorithms(self):
        _, worlds, root, _, infos, payoff = build_fixture()
        locked_key = (0, 0, ())
        self.assertEqual(infos[locked_key], 2)
        locks = {locked_key: [0.2, 0.8]}
        for algorithm in ("vanilla", "dcfr"):
            with self.subTest(algorithm=algorithm):
                recursive = train_recursive(
                    root, worlds, infos, 100, algorithm, payoff, _node_key,
                    _chance_child, locks,
                )
                planned = train_planned(
                    root, worlds, infos, 100, algorithm, payoff, _node_key,
                    _chance_child, locks,
                )
                assert_profiles_equal(self, recursive, planned)
                self.assertEqual(planned[locked_key], [0.2, 0.8])

    def test_operation_cap_rejects_invalid_and_oversized_plans_early(self):
        _, worlds, root, _, infos, payoff = build_fixture()
        for value in (0, True, -1):
            with self.subTest(limit=value), self.assertRaises(ValueError):
                train_planned(root, worlds, infos, 20, "vanilla", payoff,
                              _node_key, _chance_child, max_plan_ops=value)
        with self.assertRaisesRegex(ValueError, "operation limit"):
            train_planned(root, worlds, infos, 20, "vanilla", payoff,
                          _node_key, _chance_child, max_plan_ops=1)

    def test_public_turn_api_profiles_values_and_best_responses_match(self):
        for algorithm in ("vanilla", "dcfr"):
            recursive = solve_turn_river(
                BOARD, OOP, IP, CONFIG, river_config=RIVER_CONFIG,
                runouts=RUNOUTS, iterations=20, algorithm=algorithm,
                traversal="recursive",
            )
            planned = solve_turn_river(
                BOARD, OOP, IP, CONFIG, river_config=RIVER_CONFIG,
                runouts=RUNOUTS, iterations=20, algorithm=algorithm,
                traversal="planned",
            )
            self.assertEqual(planned["execution_backend"], "planned-python")
            self.assertEqual(recursive["execution_backend"], "recursive-python")
            self.assertEqual(len(recursive["strategy"]), len(planned["strategy"]))
            for expected, actual in zip(recursive["strategy"], planned["strategy"]):
                self.assertEqual(
                    (expected["player"], expected["hand"], expected["street"],
                     expected["board"], expected["history"]),
                    (actual["player"], actual["hand"], actual["street"],
                     actual["board"], actual["history"]),
                )
                self.assertEqual(len(expected["actions"]), len(actual["actions"]))
                for left, right in zip(expected["actions"], actual["actions"]):
                    self.assertEqual(left["history_key"], right["history_key"])
                    self.assertAlmostEqual(left["probability"], right["probability"], places=12)
            for key in ("value_oop", "value_ip", "oop_best_response_value",
                        "ip_best_response_value", "nash_conv", "exploitability"):
                self.assertAlmostEqual(recursive[key], planned[key], places=12, msg=key)

    def test_public_api_rejects_unknown_traversal(self):
        with self.assertRaisesRegex(ValueError, "Traversal"):
            solve_turn_river(
                BOARD, OOP, IP, CONFIG, river_config=RIVER_CONFIG,
                runouts=RUNOUTS, iterations=10, traversal="compiled-native",
            )


if __name__ == "__main__":
    unittest.main()
