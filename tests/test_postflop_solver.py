"""Independent physical chance and serialized-policy checks for postflop CFR."""
import unittest
from types import SimpleNamespace

from pokerlab.cards import DECK, cards, expand_range, rank_hand
from pokerlab.cfr import best_response
from pokerlab.river_config import RiverConfig
from pokerlab.postflop_solver import (
    _build_postflop_tree, _enumerate_worlds, solve_postflop,
)


FLOP = "Js8d4c"
OOP_RANGE = "AsAh:0.5,KsKh:1"
IP_RANGE = "AcAd:1,KcKd:0.75"
ORDERED_RUNOUTS = (("As", "3c"), ("3c", "As"), ("5h", "9s"))


def _physical_worlds(board, oop_range, ip_range, runouts=None):
    """Enumerate and normalize ordered physical private-hand/runout worlds."""
    board = cards(board)
    future_count = 5 - len(board)
    oop_hands = expand_range(oop_range, board)
    ip_hands = expand_range(ip_range, board)
    if future_count == 2:
        remaining = tuple(card for card in DECK if card not in board)
        selected = tuple(runouts) if runouts is not None else tuple(
            (turn, river) for turn in remaining for river in remaining if turn != river
        )
        denominator = 45 * 44
    elif future_count == 1:
        remaining = tuple(card for card in DECK if card not in board)
        selected = tuple(runouts) if runouts is not None else remaining
        denominator = 44
    else:
        selected = ((),)
        denominator = 1

    hands = (list(oop_hands), list(ip_hands))
    worlds = []
    compatible_pairs = 0
    for i, hand0 in enumerate(hands[0]):
        for j, hand1 in enumerate(hands[1]):
            if not set(hand0).isdisjoint(hand1):
                continue
            pair_worlds = []
            for future in selected:
                future = tuple(future) if isinstance(future, (tuple, list)) else (future,)
                if len(set(future)) != len(future):
                    continue
                if set(future).intersection(board + hand0 + hand1):
                    continue
                if len(future) != future_count:
                    continue
                pair_worlds.append(future)
            if not pair_worlds:
                continue
            compatible_pairs += 1
            raw_mass = oop_hands[hand0] * ip_hands[hand1] / denominator
            for future in pair_worlds:
                final_board = board + tuple(sorted(future))
                rank0 = rank_hand(hand0 + final_board)
                rank1 = rank_hand(hand1 + final_board)
                sign = (rank0 > rank1) - (rank0 < rank1)
                worlds.append((i, j, raw_mass, sign, *future))
    normalizer = sum(world[2] for world in worlds)
    normalized = [world[:2] + (world[2] / normalizer,) + world[3:]
                  for world in worlds]
    return hands, normalized, compatible_pairs


def _serialized_oracle(result, worlds, hands, *, responder=None):
    """Replay serialized public policies and independently integrate BRs.

    A response may condition on its hand and revealed board, but groups worlds
    by public turn/river before maximizing; unrevealed cards stay summed chance.
    """
    rows = {
        (0 if row["player"] == "oop" else 1,
         "".join(cards(row["hand"], 2)), tuple(row["history"])): row["actions"]
        for row in result["strategy"]
    }
    hand_names = tuple(tuple("".join(hand) for hand in side) for side in hands)
    pot = result["pot"]
    stack_caps = result["config"]["effective_stack"]
    if not isinstance(stack_caps, list):
        stack_caps = [stack_caps, stack_caps]

    def terminal(world, contributions, winner=None, player=None):
        matched = min(contributions)
        oop_value = ((1 if winner == 0 else -1) * (pot / 2 + matched)
                     if winner is not None else world[3] * (pot / 2 + matched))
        return oop_value if player in (None, 0) else -oop_value

    def split_hands(group, player):
        grouped = {}
        for world in group:
            grouped.setdefault(world[player], []).append(world)
        return grouped

    def settle(history, contributions, group, player):
        # An all-in call settles immediately, with the final rank already
        # attached to each physical world. Otherwise expose exactly one card.
        if any(min(contributions) >= cap - 1e-9 for cap in stack_caps):
            return sum(world[2] * terminal(world, contributions, player=player)
                       for world in group)
        revealed = sum(token.startswith(("turn@", "river@")) for token in history)
        if revealed >= len(worlds[0]) - 4:
            return sum(world[2] * terminal(world, contributions, player=player)
                       for world in group)
        future_index = 4 + revealed
        card_token = "turn@" if future_index == 4 else "river@"
        by_card = {}
        for world in group:
            by_card.setdefault(world[future_index], []).append(world)
        value = 0.0
        for card, card_worlds in by_card.items():
            value += play(history + (f"{card_token}{card}",), 0,
                          contributions, card_worlds, player)
        return value

    def after(action, world, group, history, actor, contributions, player):
        updated = list(contributions)
        name = action["name"]
        if name in {"bet", "raise", "all_in"}:
            updated[actor] = action["raise_to"]
        elif name == "call":
            updated[actor] += action["amount"]
        if name == "fold":
            return sum(item[2] * terminal(item, updated, winner=1 - actor,
                                          player=player) for item in group)
        action_history = history + (action["history_key"],)
        if name == "call" or (name == "check" and history and history[-1] == "check"):
            return settle(action_history, tuple(updated), group, player)
        return play(action_history, 1 - actor, tuple(updated), group, player)

    def play(history, actor, contributions, group, player):
        if not group:
            return 0.0
        if player == actor:
            # A best response can select a different action for each private
            # hand, but must integrate all future public-card worlds first.
            total = 0.0
            for own_hand, own_group in split_hands(group, actor).items():
                actions = rows[(actor, hand_names[actor][own_hand], history)]
                total += max(after(action, own_group[0], own_group, history,
                                   actor, contributions, player)
                             for action in actions)
            return total

        value = 0.0
        for action_index in range(len(rows[(actor,
                                           hand_names[actor][group[0][actor]],
                                           history)])):
            scaled = []
            for world in group:
                actions = rows[(actor, hand_names[actor][world[actor]], history)]
                probability = actions[action_index]["probability"]
                if probability:
                    scaled.append(world[:2] +
                                  (world[2] * probability,) + world[3:])
            if scaled:
                actions = rows[(actor, hand_names[actor][scaled[0][actor]], history)]
                value += after(actions[action_index], scaled[0], scaled, history,
                               actor, contributions, player)
        return value

    if responder is None:
        return play((), 0, (0.0, 0.0), worlds, None)
    return sum(play((), 0, (0.0, 0.0), group, responder)
               for group in split_hands(worlds, responder).values())


def _assert_results_equal(test, left, right):
    test.assertEqual(len(left["strategy"]), len(right["strategy"]))
    for expected, actual in zip(left["strategy"], right["strategy"]):
        test.assertEqual((expected["player"], expected["hand"], expected["street"],
                          expected["board"], expected["history"]),
                         (actual["player"], actual["hand"], actual["street"],
                          actual["board"], actual["history"]))
        test.assertEqual(len(expected["actions"]), len(actual["actions"]))
        for e_action, a_action in zip(expected["actions"], actual["actions"]):
            test.assertEqual(e_action["history_key"], a_action["history_key"])
            test.assertAlmostEqual(e_action["probability"], a_action["probability"],
                                   places=12)
    for field in ("value_oop", "oop_best_response_value", "ip_best_response_value",
                  "nash_conv", "exploitability"):
        test.assertAlmostEqual(left[field], right[field], places=12, msg=field)


class PostflopSolverTests(unittest.TestCase):
    def test_selected_flop_worlds_and_independent_profile_and_response_oracle(self):
        config = RiverConfig(pot=20, effective_stack=80, bet_sizes=(0.5,),
                             include_all_in=False)
        hands, worlds, pairs = _physical_worlds(
            FLOP, OOP_RANGE, IP_RANGE, ORDERED_RUNOUTS)
        self.assertEqual(sum(world[2] for world in worlds), 1.0)
        self.assertEqual(pairs, 4)
        self.assertEqual(len(worlds), 8)  # ordered swaps remain separate worlds

        for algorithm in ("vanilla", "dcfr"):
            recursive = solve_postflop(
                FLOP, OOP_RANGE, IP_RANGE, config, runouts=ORDERED_RUNOUTS,
                iterations=10, algorithm=algorithm, traversal="recursive",
            )
            planned = solve_postflop(
                FLOP, OOP_RANGE, IP_RANGE, config, runouts=ORDERED_RUNOUTS,
                iterations=10, algorithm=algorithm, traversal="planned",
            )
            self.assertEqual(recursive["deals"], pairs)
            self.assertEqual(recursive["compatible_pairs"], pairs)
            self.assertEqual(recursive["worlds"], len(worlds))
            self.assertEqual(recursive["runout_mode"], "conditioned-ordered-subset")
            _assert_results_equal(self, recursive, planned)
            self.assertAlmostEqual(recursive["value_oop"],
                                   _serialized_oracle(recursive, worlds, hands), places=9)
            self.assertAlmostEqual(recursive["oop_best_response_value"],
                                   _serialized_oracle(recursive, worlds, hands,
                                                      responder=0), places=9)
            self.assertAlmostEqual(recursive["ip_best_response_value"],
                                   _serialized_oracle(recursive, worlds, hands,
                                                      responder=1), places=9)

    def test_public_turn_facade_and_backends_match(self):
        board = "2c3c4d5h"
        oop, ip = "AsKd,QhQc", "JsJd,9s9d"
        runouts = ("8c", "9c")
        config = RiverConfig(pot=10, effective_stack=20, bet_sizes=(0.5,),
                             include_all_in=False)
        for algorithm in ("vanilla", "dcfr"):
            recursive = solve_postflop(
                board, oop, ip, config, runouts=runouts, iterations=10,
                algorithm=algorithm, traversal="recursive",
            )
            planned = solve_postflop(
                board, oop, ip, config, runouts=runouts, iterations=10,
                algorithm=algorithm, traversal="planned",
            )
            self.assertEqual(recursive["execution_backend"], "recursive-python")
            self.assertEqual(planned["execution_backend"], "planned-python")
            _assert_results_equal(self, recursive, planned)

    def test_pot_and_stack_commitments_carry_across_flop_turn_river(self):
        base = dict(pot=10, effective_stack=50, include_all_in=False)
        flop = RiverConfig(bet_sizes=(0.5,), **base)
        turn = RiverConfig(bet_sizes=(0.75,), **base)
        river = RiverConfig(bet_sizes=(0.25,), **base)
        result = solve_postflop(
            "2c3c4d", "AsKd", "JsJd", flop, turn_config=turn.to_dict(),
            river_config=river.to_dict(), runouts=(("5h", "9s"),), iterations=10,
        )
        rows = {(row["player"], tuple(row["history"])): row
                for row in result["strategy"]}

        def bet_target(history):
            actions = rows[("oop", history)]["actions"]
            return next(action["raise_to"] for action in actions
                        if action["name"] == "bet")

        self.assertEqual(bet_target(()), 5)
        self.assertEqual(bet_target(("bet@5", "call", "turn@5h")), 20)
        self.assertEqual(bet_target(("bet@5", "call", "turn@5h", "bet@20",
                                     "call", "river@9s")), 32.5)

    def test_full_physical_short_stack_flop_fits_public_and_work_guards(self):
        board, oop, ip = "2c3c4d", "AsKd", "JsJd"
        config = RiverConfig(pot=10, effective_stack=5, bet_sizes=(0.5,),
                             include_all_in=True)
        hands, worlds, selected, pairs = _enumerate_worlds(
            board, oop, ip, iterations=10)
        self.assertEqual(pairs, 1)
        # The public selection excludes only the three known flop cards. Each
        # compatible private pair then has 45 x 44 physical ordered runouts.
        self.assertEqual(len(selected), 49 * 48)
        self.assertEqual(len(worlds), 45 * 44)
        root, nodes, _, visited, plan_ops = _build_postflop_tree(
            cards(board), config, worlds=worlds)
        self.assertLessEqual(len(nodes), 10_000)
        self.assertLessEqual(len(worlds) * visited * 10, 30_000_000)
        self.assertLessEqual(len(worlds) * plan_ops, 250_000)
        # A full CFR solve is intentionally omitted here; this checks exact
        # physical enumeration and the independent documented tree/work guards.

    def test_full_physical_short_stack_flop_solve_returns_normalized_profile(self):
        result = solve_postflop(
            "2c3c4d", "AsKd", "JsJd",
            RiverConfig(pot=10, effective_stack=5, bet_sizes=(0.5,),
                        include_all_in=True),
            iterations=10, algorithm="vanilla", traversal="recursive",
        )
        self.assertEqual(result["worlds"], 45 * 44)
        self.assertEqual(result["deals"], 1)
        self.assertEqual(result["public_nodes"], 8104)
        self.assertAlmostEqual(result["value_oop"] + result["value_ip"], 0.0,
                               places=12)
        self.assertGreaterEqual(result["nash_conv"], 0.0)
        self.assertTrue(result["nash_conv"] < float("inf"))
        self.assertAlmostEqual(result["exploitability"],
                               result["nash_conv"] / 2, places=12)
        for row in result["strategy"]:
            probabilities = [action["probability"] for action in row["actions"]]
            self.assertTrue(all(0.0 <= probability <= 1.0
                                for probability in probabilities))
            self.assertAlmostEqual(sum(probabilities), 1.0, places=12)

    def test_nested_best_response_cannot_peek_at_unrevealed_turn_or_river(self):
        class Chance:
            def __init__(self, card_index, branches):
                self.card_index = card_index
                self.branches = branches

        def leaf(value):
            return SimpleNamespace(payoff=value)

        turns, rivers = ("8c", "9c"), ("5h", "6h")
        worlds = [(0, 0, 0.25, 0, turn, river)
                  for turn in turns for river in rivers]
        root_children = []
        for root_choice in (1, -1):
            turn_branches = {}
            for turn_index, turn in enumerate(turns):
                turn_effect = root_choice * (1 if turn_index == 0 else -1)
                river_actions = []
                for river_choice in (1, -1):
                    river_branches = {
                        river: leaf(turn_effect + river_choice *
                                    (1 if river_index == 0 else -1))
                        for river_index, river in enumerate(rivers)
                    }
                    river_actions.append(Chance(5, river_branches))
                decision = SimpleNamespace(
                    player=0, history=(f"turn@{turn}",),
                    actions=("x", "y"), children=tuple(river_actions),
                )
                turn_branches[turn] = decision
            root_children.append(Chance(4, turn_branches))
        root = SimpleNamespace(player=0, history=(), actions=("a", "b"),
                               children=tuple(root_children))

        def child_for_world(node, world):
            if isinstance(node, Chance):
                return node.branches[world[node.card_index]]
            return None

        def partitions(node, weighted_worlds):
            if not isinstance(node, Chance):
                return None
            groups = {}
            for world in weighted_worlds:
                groups.setdefault(world[node.card_index], []).append(world)
            return [(node.branches[card], group) for card, group in groups.items()]

        # Hand integration is trivial here (one hand per player). The known
        # answer sums both chance layers before maximizing at each public node.
        legal = best_response(
            0, root, worlds, {}, lambda terminal, world: terminal.payoff,
            lambda node, world: (node.player, world[node.player], node.history),
            partitions,
        )
        # A clairvoyant policy could choose root action after seeing turn and
        # the later action after seeing river, earning 2; legal choices each
        # precede their corresponding hidden chance event and earn exactly 0.
        self.assertAlmostEqual(legal, 0.0, places=12)
        self.assertGreater(2.0, legal)

    def test_rejects_invalid_ordered_runouts_and_cross_street_configs(self):
        config = RiverConfig(pot=10, effective_stack=20, bet_sizes=(0.5,))
        bad_runouts = (
            (("5h", "5h"),),
            (("2c", "9s"),),
            (("5h", "9s"), ("5h", "9s")),
            (("5h",),),
        )
        for runouts in bad_runouts:
            with self.subTest(runouts=runouts), self.assertRaises(ValueError):
                solve_postflop("2c3c4d", "AsKd", "JsJd", config,
                               runouts=runouts, iterations=10)
        other_pot = RiverConfig(pot=11, effective_stack=20, bet_sizes=(0.5,))
        with self.assertRaisesRegex(ValueError, "pot and stack caps"):
            solve_postflop("2c3c4d", "AsKd", "JsJd", config,
                           turn_config=other_pot, iterations=10)
        with self.assertRaisesRegex(ValueError, "Unknown river configuration"):
            solve_postflop("2c3c4d", "AsKd", "JsJd", config,
                           turn_config={"pot": 10, "effective_stack": 20,
                                        "unexpected": True}, iterations=10)
        with self.assertRaises(ValueError):
            solve_postflop("2c3c4d5h9s", "AsKd", "JsJd", config,
                           runouts=(), iterations=10)


if __name__ == "__main__":
    unittest.main()
