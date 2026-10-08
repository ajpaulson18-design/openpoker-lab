"""Independent physical-deal and public-policy oracles for turn-to-river CFR."""
import unittest
from itertools import product
from types import SimpleNamespace

from pokerlab.cards import DECK, cards, expand_range
from pokerlab.cfr import best_response
from pokerlab.river_config import RiverConfig
from pokerlab.river_tree import _Terminal, _terminal_value
from pokerlab.turn_solver import _Chance, _enumerate_worlds, solve_turn_river


BOARD = "2c3c4d5h"
OOP_RANGE = "AsKd,QhQc"
IP_RANGE = "JsJd,9s9d"


def _physical_world_oracle(board, oop_range, ip_range, runouts=None):
    board = cards(board, 4)
    ranges = (expand_range(oop_range, board), expand_range(ip_range, board))
    selected = set(DECK if runouts is None else cards(runouts)) - set(board)
    raw = {}
    for hand0, weight0 in ranges[0].items():
        for hand1, weight1 in ranges[1].items():
            if set(hand0).intersection(hand1):
                continue
            for river in selected - set(hand0) - set(hand1):
                raw[("".join(hand0), "".join(hand1), river)] = weight0 * weight1 / 44
    total = sum(raw.values())
    return {key: mass / total for key, mass in raw.items()}


def _strategy_oracle(result, worlds, hands, target=None, pure_policy=None):
    """Replay serialized public rows and independently integrate/maximize policies."""
    rows = {(0 if row["player"] == "oop" else 1,
             "".join(cards(row["hand"], 2)), tuple(row["history"])): row["actions"]
            for row in result["strategy"]}
    pot = result["pot"]
    hand_names = tuple(["".join(hand) for hand in side] for side in hands)

    def terminal(world, contributions, winner=None, player=None):
        matched = min(contributions)
        oop_value = ((1 if winner == 0 else -1) * (pot / 2 + matched)
                     if winner is not None else world[3] * (pot / 2 + matched))
        return oop_value if player in (None, 0) else -oop_value

    def play(history, actor, contributions, group, responder):
        if not group:
            return 0.0
        own_hand = hand_names[actor][group[0][actor]]
        actions = rows[(actor, own_hand, history)]

        def after(action, world, mass_group):
            next_contributions = list(contributions)
            name = action["name"]
            if name in {"bet", "raise", "all_in"}:
                next_contributions[actor] = action["raise_to"]
            elif name == "call":
                next_contributions[actor] += action["amount"]
            if name == "fold":
                return sum(w[2] * terminal(w, next_contributions,
                                           winner=1 - actor, player=responder)
                           for w in mass_group)
            if name == "call" or (name == "check" and history and
                                    history[-1] == "check"):
                if any(token.startswith("river@") for token in history):
                    return sum(w[2] * terminal(w, next_contributions, player=responder)
                               for w in mass_group)
                river_groups = {}
                for world in mass_group:
                    river_groups.setdefault(world[4], []).append(world)
                terminal_history = history + (action["history_key"],)
                return sum(play(terminal_history + (f"river@{river}",), 0,
                                tuple(next_contributions), river_group, responder)
                           for river, river_group in river_groups.items())
            # Betting/checking continues within a street; OOP opens each street.
            return play(history + (action["history_key"],), 1 - actor,
                        tuple(next_contributions), mass_group, responder)

        if actor == responder:
            if pure_policy is not None:
                selected = pure_policy[(actor, own_hand, history)]
                return after(actions[selected], group[0], group)
            return max(after(action, group[0], group) for action in actions)
        value = 0.0
        for action_index, action in enumerate(actions):
            # Opponent policy may vary with its private hand. Scale each world
            # by that hand's probability for the same public action.
            scaled_group = []
            for world in group:
                opponent_hand = hand_names[actor][world[actor]]
                opponent_actions = rows[(actor, opponent_hand, history)]
                probability = opponent_actions[action_index]["probability"]
                if probability:
                    scaled_group.append(tuple(world[:2]) +
                                        (world[2] * probability,) + tuple(world[3:]))
            if not scaled_group:
                continue
            value += after(action, scaled_group[0], scaled_group)
        return value

    # This helper intentionally works only for exact no-raise configurations;
    # each serialized node’s action distribution is still handled generically.
    if target is None:
        value = 0.0
        for world in worlds:
            value += play((), 0, (0.0, 0.0), [world], None)
        return value
    grouped = {}
    for world in worlds:
        grouped.setdefault(world[target], []).append(world)
    return sum(play((), 0, (0.0, 0.0), group, target)
               for group in grouped.values())


class TurnSolverPhysicalChanceTests(unittest.TestCase):
    def test_full_deck_has_44_rivers_per_compatible_private_pair(self):
        hands, worlds, selected, pair_count = _enumerate_worlds(
            BOARD, OOP_RANGE, IP_RANGE)
        self.assertEqual(len(selected), 48)
        self.assertEqual(pair_count, 4)
        self.assertEqual(len(worlds), 4 * 44)
        expected = _physical_world_oracle(BOARD, OOP_RANGE, IP_RANGE)
        actual = {
            ("".join(hands[0][i]), "".join(hands[1][j]), river): mass
            for i, j, mass, _, river in worlds
        }
        self.assertEqual(actual.keys(), expected.keys())
        for key in expected:
            self.assertAlmostEqual(actual[key], expected[key], places=14)

    def test_selected_runouts_condition_the_joint_world_distribution_once(self):
        runouts = ("As", "Js", "9c")
        hands, worlds, _, pair_count = _enumerate_worlds(
            BOARD, OOP_RANGE, IP_RANGE, runouts)
        actual = {("".join(hands[0][i]), "".join(hands[1][j]), river): mass
                  for i, j, mass, _, river in worlds}
        expected = _physical_world_oracle(BOARD, OOP_RANGE, IP_RANGE, runouts)
        self.assertEqual(pair_count, 4)
        self.assertEqual(actual.keys(), expected.keys())
        for key in expected:
            self.assertAlmostEqual(actual[key], expected[key], places=14)
        pair_mass = {}
        for (hand0, hand1, _), mass in actual.items():
            pair_mass[(hand0, hand1)] = pair_mass.get((hand0, hand1), 0.0) + mass
        expected_masses = {
            ("AsKd", "JdJs"): 1 / 8,
            ("AsKd", "9d9s"): 2 / 8,
            ("QcQh", "JdJs"): 2 / 8,
            ("QcQh", "9d9s"): 3 / 8,
        }
        for pair, expected_mass in expected_masses.items():
            self.assertAlmostEqual(pair_mass[pair], expected_mass)

    def test_river_restarts_with_oop_after_check_check_and_bet_call(self):
        config = RiverConfig(pot=10, effective_stack=10, bet_sizes=(0.5,),
                             include_all_in=False)
        result = solve_turn_river(BOARD, "AsKd", "JsJd", config,
                                  runouts=("9c",), iterations=10)
        rows = {(tuple(row["history"]), row["player"]): row
                for row in result["strategy"]}
        self.assertIn((("check", "check", "river@9c"), "oop"), rows)
        self.assertIn((("bet@5", "call", "river@9c"), "oop"), rows)
        self.assertEqual(rows[(("check", "check", "river@9c"), "oop")]["board"],
                         ["2c", "3c", "4d", "5h", "9c"])

    def test_value_and_best_responses_match_public_policy_oracle(self):
        config = RiverConfig(pot=10, effective_stack=10, bet_sizes=(0.5,),
                             include_all_in=False)
        runouts = ("8c", "9c")
        hands, worlds, _, _ = _enumerate_worlds(
            BOARD, OOP_RANGE, IP_RANGE, runouts)
        for algorithm in ("vanilla", "dcfr"):
            result = solve_turn_river(BOARD, OOP_RANGE, IP_RANGE, config,
                                      runouts=runouts, iterations=10,
                                      algorithm=algorithm)
            self.assertAlmostEqual(result["value_oop"],
                                   _strategy_oracle(result, worlds, hands), places=9)
            self.assertAlmostEqual(result["oop_best_response_value"],
                                   _strategy_oracle(result, worlds, hands, target=0), places=9)
            self.assertAlmostEqual(result["ip_best_response_value"],
                                   _strategy_oracle(result, worlds, hands, target=1), places=9)

    def test_best_response_cannot_peek_at_unrevealed_river(self):
        root = SimpleNamespace(
            player=0, history=(), actions=("a", "b"),
            children=(
                _Chance((), {"8c": SimpleNamespace(payoff=1),
                             "9c": SimpleNamespace(payoff=-1)}),
                _Chance((), {"8c": SimpleNamespace(payoff=-1),
                             "9c": SimpleNamespace(payoff=1)}),
            ),
        )
        worlds = [(0, 0, 0.5, 0, "8c"), (0, 0, 0.5, 0, "9c")]
        chance_child = lambda node, world: node.branches.get(world[4]) \
            if isinstance(node, _Chance) else None
        chance_partitions = lambda node, group: [
            (node.branches[river], [world for world in group if world[4] == river])
            for river in ("8c", "9c") if any(world[4] == river for world in group)
        ] if isinstance(node, _Chance) else None
        legal = best_response(
            0, root, worlds, {}, lambda terminal, world: terminal.payoff,
            lambda node, world: (node.player, world[node.player], node.history),
            chance_partitions,
        )
        # An illegal clairvoyant response would choose a different action on
        # each hidden runout and earn 1. The legal turn response averages first.
        self.assertAlmostEqual(legal, 0.0)
        self.assertGreater(1.0, legal)

    def test_reported_best_responses_match_exhaustive_pure_policies(self):
        config = RiverConfig(pot=10, effective_stack=10, bet_sizes=(0.5,),
                             include_all_in=False)
        result = solve_turn_river(BOARD, "AsKd", "JsJd", config,
                                  runouts=("9c",), iterations=10)
        hands, worlds, _, _ = _enumerate_worlds(
            BOARD, "AsKd", "JsJd", ("9c",))
        for target, name in ((0, "oop"), (1, "ip")):
            rows = [row for row in result["strategy"] if row["player"] == name]
            keys = [(target, "".join(cards(row["hand"], 2)), tuple(row["history"]))
                    for row in rows]
            action_counts = [len(row["actions"]) for row in rows]
            best = max(
                _strategy_oracle(result, worlds, hands, target=target,
                                 pure_policy=dict(zip(keys, choices)))
                for choices in product(*(range(count) for count in action_counts))
            )
            expected = result["oop_best_response_value"] if target == 0 else \
                result["ip_best_response_value"]
            self.assertAlmostEqual(best, expected, places=9)

    def test_river_bet_uses_original_pot_plus_both_matched_turn_bets(self):
        config = RiverConfig(pot=10, effective_stack=20, bet_sizes=(0.5,),
                             include_all_in=False)
        result = solve_turn_river(BOARD, "AsKd", "JsJd", config,
                                  runouts=("9c",), iterations=10)
        row = next(row for row in result["strategy"]
                   if row["player"] == "oop" and
                   row["history"] == ["bet@5", "call", "river@9c"])
        # Starting river pot is 10 + 5 + 5 = 20; a half-pot bet adds 10
        # to OOP's existing 5 commitment, so total commitment is 15.
        self.assertEqual(next(action["raise_to"] for action in row["actions"]
                              if action["name"] == "bet"), 15)

    def test_asymmetric_all_in_returns_uncalled_excess_and_still_runs_out(self):
        terminal = _Terminal("showdown", (5, 15))
        self.assertEqual(_terminal_value(terminal, 1, 10), 10)
        self.assertEqual(_terminal_value(terminal, -1, 10), -10)
        self.assertEqual(_terminal_value(_Terminal("fold", (5, 15), winner=0), 1, 10), 10)
        self.assertEqual(_terminal_value(_Terminal("fold", (5, 15), winner=1), 1, 10), -10)
        config = RiverConfig(pot=10, effective_stack=(5, 20), bet_sizes=(0.5,),
                             include_all_in=False)
        result = solve_turn_river(BOARD, "AsKd", "JsJd", config,
                                  runouts=("9c", "Tc"), iterations=10)
        self.assertEqual(result["worlds"], 2)
        self.assertEqual(result["reachable_runouts"], ["9c", "Tc"])
        # The short stack's all-in/call line settles directly into public chance;
        # it cannot create new river decisions or charge the unmatched excess.
        all_in_response = next(row for row in result["strategy"]
                               if row["player"] == "ip" and
                               row["history"] == ["all_in@5"])
        self.assertIn("call", [action["name"] for action in all_in_response["actions"]])
        self.assertFalse(any(row["history"][:2] == ["all_in@5", "call"] and
                             row["history"][2].startswith("river@")
                             for row in result["strategy"]))

    def test_rejects_runouts_that_are_private_or_publicly_invalid(self):
        config = RiverConfig(pot=10, effective_stack=10, bet_sizes=(0.5,))
        with self.assertRaises(ValueError):
            solve_turn_river(BOARD, "AsKd", "JsJd", config,
                             runouts=("As",), iterations=10)
        with self.assertRaises(ValueError):
            solve_turn_river(BOARD, "AsKd", "JsJd", config,
                             runouts=("9c", "9c"), iterations=10)
        with self.assertRaises(ValueError):
            solve_turn_river(BOARD, "AsKd", "JsJd", config,
                             runouts=("2c",), iterations=10)

    def test_rejects_a_river_abstraction_that_changes_turn_pot_or_stack_caps(self):
        turn = RiverConfig(pot=10, effective_stack=(20, 30), bet_sizes=(0.5,))
        river = RiverConfig(pot=11, effective_stack=(20, 30), bet_sizes=(0.5,))
        with self.assertRaises(ValueError):
            solve_turn_river(BOARD, "AsKd", "JsJd", turn,
                             river_config=river, runouts=("9c",), iterations=10)
        river = RiverConfig(pot=10, effective_stack=(20, 31), bet_sizes=(0.5,))
        with self.assertRaises(ValueError):
            solve_turn_river(BOARD, "AsKd", "JsJd", turn,
                             river_config=river, runouts=("9c",), iterations=10)

    def test_both_algorithms_reduce_gap_on_a_hand_computable_tree(self):
        config = RiverConfig(pot=10, effective_stack=10, bet_sizes=(0.5,),
                             include_all_in=False)
        for algorithm in ("vanilla", "dcfr"):
            early = solve_turn_river(BOARD, "AsKd", "JsJd", config,
                                     runouts=("9c",), iterations=10,
                                     algorithm=algorithm)
            later = solve_turn_river(BOARD, "AsKd", "JsJd", config,
                                     runouts=("9c",), iterations=100,
                                     algorithm=algorithm)
            self.assertLess(later["nash_conv"], early["nash_conv"])


if __name__ == "__main__":
    unittest.main()
