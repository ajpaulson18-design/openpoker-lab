import unittest
from itertools import product

from pokerlab.cfr import best_response, evaluate
from pokerlab.public_diagnostics import evaluate_profile
from pokerlab.river_tree import _Terminal


class _Node:
    def __init__(self, player, history, children):
        self.player = player
        self.history = history
        self.children = children
        self.actions = tuple(range(len(children)))


class _Chance:
    def __init__(self, branches):
        self.branches = branches


class PublicDiagnosticsTests(unittest.TestCase):
    def test_generated_turn_tree_matches_world_reference(self):
        from pokerlab.postflop_solver import (
            _Chance as PostflopChance, _build_postflop_tree, _chance_child,
            _chance_partitions, _enumerate_worlds, _node_key, _prefix_hand_index,
            _public_reveals, _terminal_value,
        )
        from pokerlab.river_config import RiverConfig

        board = ("As", "Kd", "7c", "2h")
        config = RiverConfig(pot=20, effective_stack=30, bet_sizes=(0.5,),
                             raise_sizes=(0.5,), max_raises=1, include_all_in=False)
        _, worlds, _, _ = _enumerate_worlds(
            board, "QhQs,JhJs", "AcQc,TcTh", ("3c", "4c", "5c", "6c"), 1,
        )
        root, nodes, *_ = _build_postflop_tree(board, config, worlds=worlds)
        legal = _prefix_hand_index(worlds)
        infos = {}
        for (player, history), node in nodes.items():
            for hand in legal.get((player, _public_reveals(history)), ()):
                infos[(player, hand, history)] = len(node.actions)
        averages = {key: [1 / count] * count for key, count in infos.items()}
        payoff = lambda node, world: _terminal_value(node, world[3], config.pot)
        reference = (
            evaluate(root, worlds, averages, payoff, _node_key,
                     lambda node, world: _chance_child(node, world)),
            best_response(0, root, worlds, averages, payoff, _node_key,
                          _chance_partitions),
            best_response(1, root, worlds, averages, payoff, _node_key,
                          _chance_partitions),
        )
        actual = evaluate_profile(root, worlds, averages, pot=config.pot,
                                  chance_type=PostflopChance)
        for got, want in zip(actual, reference):
            self.assertAlmostEqual(got, want, places=10)

    def test_profile_and_best_responses_with_chance_and_asymmetric_ranges(self):
        # OOP chooses check/bet; after the public card IP chooses fold/call.
        # A second public card has a different showdown result.
        root = _Node(0, ("start",), [])
        check = _Chance({
            10: _Node(1, ("check", 10), [
                _Terminal("fold", (0.0, 0.0), 0),
                _Terminal("showdown", (2.0, 2.0)),
            ]),
            11: _Node(1, ("check", 11), [
                _Terminal("fold", (0.0, 0.0), 0),
                _Terminal("showdown", (2.0, 2.0)),
            ]),
        })
        bet = _Chance({
            10: _Node(1, ("bet", 10), [
                _Terminal("fold", (1.0, 0.0), 0),
                _Terminal("showdown", (3.0, 3.0)),
            ]),
            11: _Node(1, ("bet", 11), [
                _Terminal("fold", (1.0, 0.0), 0),
                _Terminal("showdown", (3.0, 3.0)),
            ]),
        })
        root.children = [check, bet]
        worlds = [
            (0, 1, 0.30, 1, 10), (0, 2, 0.20, -1, 10),
            (1, 2, 0.50, 0, 11),
        ]
        avg = {
            (0, 0, ("start",)): [0.65, 0.35],
            (0, 1, ("start",)): [0.4, 0.6],
            (1, 1, ("check", 10)): [0.2, 0.8],
            (1, 2, ("check", 10)): [0.7, 0.3],
            (1, 1, ("check", 11)): [0.5, 0.5],
            (1, 2, ("check", 11)): [0.1, 0.9],
            (1, 1, ("bet", 10)): [0.8, 0.2],
            (1, 2, ("bet", 10)): [0.3, 0.7],
            (1, 1, ("bet", 11)): [0.6, 0.4],
            (1, 2, ("bet", 11)): [0.2, 0.8],
        }

        def payoff(node, world):
            if node.kind == "fold":
                return (1 if node.winner == 0 else -1) * (5 + min(node.contributions))
            return world[3] * (5 + min(node.contributions))

        def key(node, world):
            return node.player, world[node.player], node.history

        def chance_child(node, world):
            if isinstance(node, _Chance):
                return node.branches[world[4]]
            return None

        def partitions(node, weighted):
            if not isinstance(node, _Chance):
                return None
            return [(node.branches[card], [w for w in weighted if w[4] == card])
                    for card in node.branches]

        expected = evaluate(root, worlds, avg, payoff, key, chance_child)
        br0 = best_response(0, root, worlds, avg, payoff, key, partitions)
        br1 = best_response(1, root, worlds, avg, payoff, key, partitions)
        got = evaluate_profile(root, worlds, avg, pot=10, chance_type=_Chance)
        for actual, reference in zip(got, (expected, br0, br1)):
            self.assertAlmostEqual(actual, reference)

        # Independent pure-policy enumeration: every responder hand/history
        # gets one deterministic action, with the supplied fixed opponent
        # policy applied along each compatible physical world.
        def world_value(node, world, responder, choices):
            if isinstance(node, _Chance):
                return world_value(node.branches[world[4]], world, responder, choices)
            if isinstance(node, _Terminal):
                return world[2] * payoff(node, world)
            key = key_for(node, world)
            if node.player == responder:
                return world_value(node.children[choices[key]], world, responder, choices)
            return sum(prob * world_value(child, world, responder, choices)
                       for prob, child in zip(avg[key], node.children))

        def key_for(node, world):
            return node.player, world[node.player], node.history

        for responder, expected_br in ((0, br0), (1, br1)):
            keys = sorted(k for k in avg if k[0] == responder)
            maximum = float("-inf")
            for actions in product(range(2), repeat=len(keys)):
                choices = dict(zip(keys, actions))
                total = sum(world_value(root, world, responder, choices)
                            for world in worlds)
                utility_sign = 1 if responder == 0 else -1
                maximum = max(maximum, utility_sign * total)
            self.assertAlmostEqual(maximum, expected_br)

    def test_zero_mass_and_uniform_missing_policy(self):
        root = _Node(0, ("h",), [
            _Terminal("showdown", (0, 0)),
            _Terminal("showdown", (0, 0)),
        ])
        worlds = [(0, 1, 1.0, 1)]
        with self.assertRaisesRegex(ValueError, "missing a reachable"):
            evaluate_profile(root, worlds, {}, pot=2, chance_type=_Chance)
        result = evaluate_profile(root, worlds, {(0, 0, ("h",)): [0.5, 0.5]},
                                  pot=2, chance_type=_Chance)
        self.assertEqual(result, (1.0, 1.0, -1.0))


if __name__ == "__main__":
    unittest.main()
