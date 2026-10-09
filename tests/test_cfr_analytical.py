"""Analytical Kuhn poker checks for the generic CFR utilities.

Kuhn poker is a tiny imperfect-information game with a known value, making it
useful as an external behavioral check on training, evaluation, and BR logic.
"""
from dataclasses import dataclass
from itertools import permutations, product
import math
import unittest

from pokerlab.cfr import best_response, evaluate, train
from pokerlab.cfr_plus import train as train_plus


@dataclass(frozen=True)
class Node:
    player: int
    history: tuple
    actions: tuple
    children: tuple


@dataclass(frozen=True)
class Terminal:
    history: tuple


def game():
    """Return the Kuhn tree, six equally likely private-card deals and infos."""
    actions_by_history = {
        (): ("check", "bet"),
        ("check",): ("check", "bet"),
        ("bet",): ("fold", "call"),
        ("check", "bet"): ("fold", "call"),
    }
    player_by_history = {(): 0, ("check",): 1, ("bet",): 1,
                         ("check", "bet"): 0}
    terminals = {("check", "check"), ("bet", "fold"), ("bet", "call"),
                 ("check", "bet", "fold"), ("check", "bet", "call")}

    def build(history=()):
        if history in terminals:
            return Terminal(history)
        actions = actions_by_history[history]
        return Node(player_by_history[history], history, actions,
                    tuple(build(history + (action,)) for action in actions))

    worlds = [(a, b, 1 / 6) for a, b in permutations(("J", "Q", "K"), 2)]
    infos = {}
    for history, player in player_by_history.items():
        for hand in ("J", "Q", "K"):
            infos[(player, hand, history)] = 2
    return build(), worlds, infos


def key(node, world):
    return node.player, world[node.player], node.history


def payoff(terminal, world):
    history = terminal.history
    if history in (("check", "check"), ("bet", "call"),
                   ("check", "bet", "call")):
        winner = 0 if "JQK".index(world[0]) > "JQK".index(world[1]) else 1
        amount = 1 if history == ("check", "check") else 2
        return amount if winner == 0 else -amount
    bettor = 0 if history[0] == "bet" else 1
    return 1 if bettor == 0 else -1


def pure_policy_br(player, root, worlds, profile):
    """Independently enumerate this player's 2^6 deterministic policies."""
    own_nodes = [(history, hand) for history, actor in
                 (((), 0), (("check",), 1), (("bet",), 1),
                  (("check", "bet"), 0)) if actor == player
                 for hand in ("J", "Q", "K")]
    best = -math.inf
    for choices in product((0, 1), repeat=len(own_nodes)):
        deterministic = dict(zip(own_nodes, choices))

        def visit(node, world):
            if isinstance(node, Terminal):
                return payoff(node, world) * (1 if player == 0 else -1)
            node_key = (node.history, world[node.player])
            if node.player == player:
                return visit(node.children[deterministic[node_key]], world)
            probs = profile[key(node, world)]
            return sum(p * visit(child, world)
                       for p, child in zip(probs, node.children))

        value = sum(weight * visit(root, world) for *world, weight in worlds)
        best = max(best, value)
    return best


class KuhnPokerAnalyticalTests(unittest.TestCase):
    def test_closed_form_equilibrium_has_exact_value_and_zero_exploitability(self):
        root, worlds, infos = game()
        profile = {}
        oop_open = {"J": 1 / 3, "Q": 0, "K": 1}
        ip_check = {"J": 1 / 3, "Q": 0, "K": 1}
        ip_facing_bet = {"J": 0, "Q": 1 / 3, "K": 1}
        oop_facing_bet = {"J": 0, "Q": 2 / 3, "K": 1}
        for hand in ("J", "Q", "K"):
            profile[(0, hand, ())] = [1 - oop_open[hand], oop_open[hand]]
            profile[(1, hand, ("check",))] = [1 - ip_check[hand], ip_check[hand]]
            profile[(1, hand, ("bet",))] = [1 - ip_facing_bet[hand], ip_facing_bet[hand]]
            profile[(0, hand, ("check", "bet"))] = [1 - oop_facing_bet[hand], oop_facing_bet[hand]]

        self.assertAlmostEqual(evaluate(root, worlds, profile, payoff, key), -1 / 18,
                               places=14)
        self.assertAlmostEqual(best_response(0, root, worlds, profile, payoff, key),
                               -1 / 18, places=14)
        self.assertAlmostEqual(best_response(1, root, worlds, profile, payoff, key),
                               1 / 18, places=14)
        self.assertAlmostEqual(sum(best_response(p, root, worlds, profile, payoff, key)
                                   for p in (0, 1)), 0, places=14)

    def test_value_and_exact_best_responses_match_known_kuhn_equilibrium(self):
        root, worlds, infos = game()
        profile = train(root, worlds, infos, 3000, terminal_value=payoff,
                        node_key=key)
        value = evaluate(root, worlds, profile, payoff, key)
        self.assertAlmostEqual(value, -1 / 18, delta=.004)
        for player in (0, 1):
            with self.subTest(player=player):
                api_br = best_response(player, root, worlds, profile, payoff, key)
                enumerated_br = pure_policy_br(player, root, worlds, profile)
                self.assertAlmostEqual(api_br, enumerated_br, places=12)
        br0 = best_response(0, root, worlds, profile, payoff, key)
        br1 = best_response(1, root, worlds, profile, payoff, key)
        self.assertLess(br0 + br1, .012)

    def test_vanilla_and_dcfr_converge_and_remain_numerically_finite(self):
        root, worlds, infos = game()
        for algorithm in ("vanilla", "dcfr"):
            with self.subTest(algorithm=algorithm):
                profile = train(root, worlds, infos, 30000, algorithm=algorithm,
                                terminal_value=payoff, node_key=key)
                value = evaluate(root, worlds, profile, payoff, key)
                gap = sum(best_response(p, root, worlds, profile, payoff, key)
                          for p in (0, 1))
                self.assertTrue(math.isfinite(value))
                self.assertTrue(math.isfinite(gap))
                self.assertAlmostEqual(value, -1 / 18, delta=.007)
                self.assertLess(gap, .025)

    def test_cfr_plus_converges_deterministically_with_normalized_policies(self):
        root, worlds, infos = game()
        profile = train_plus(root, worlds, infos, 1000, terminal_value=payoff,
                             node_key=key)
        self.assertEqual(profile, train_plus(root, worlds, infos, 1000,
                                             terminal_value=payoff, node_key=key))
        for probabilities in profile.values():
            self.assertTrue(all(math.isfinite(p) and 0 <= p <= 1 for p in probabilities))
            self.assertAlmostEqual(sum(probabilities), 1, places=12)
        value = evaluate(root, worlds, profile, payoff, key)
        gap = sum(best_response(p, root, worlds, profile, payoff, key)
                  for p in (0, 1))
        self.assertAlmostEqual(value, -1 / 18, delta=.001)
        self.assertLess(gap, .001)


if __name__ == "__main__":
    unittest.main()
