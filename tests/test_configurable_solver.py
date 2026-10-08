import json
import itertools
import unittest

from pokerlab.cards import cards, expand_range, rank_hand
from pokerlab.equilibrium import InfoSet, solve_equilibrium
from pokerlab.river_config import RiverConfig
from pokerlab.solver import (
    _Terminal,
    _build_tree,
    _terminal_value,
    solve,
)

BOARD = "Js8d4c2h2s"


def find_node(root, history):
    if getattr(root, "history", None) == history:
        return root
    for child in getattr(root, "children", ()):
        found = find_node(child, history)
        if found is not None:
            return found
    return None


def public_result_oracle(result, board, oop_range, ip_range):
    """Exhaustively evaluate legal pure policies from public strategy rows."""
    board_cards = cards(board, 5)
    ranges = (expand_range(oop_range, board_cards), expand_range(ip_range, board_cards))
    hands = (list(ranges[0]), list(ranges[1]))
    hand_names = tuple(["".join(hand) for hand in side] for side in hands)
    ranks = tuple([rank_hand(hand + board_cards) for hand in side] for side in hands)
    deals = []
    for i, oop_hand in enumerate(hands[0]):
        for j, ip_hand in enumerate(hands[1]):
            if set(oop_hand).isdisjoint(ip_hand):
                sign = (ranks[0][i] > ranks[1][j]) - (ranks[0][i] < ranks[1][j])
                deals.append((i, j, ranges[0][oop_hand] * ranges[1][ip_hand], sign))
    total_weight = sum(deal[2] for deal in deals)
    deals = [(i, j, weight / total_weight, sign) for i, j, weight, sign in deals]
    rows = {(row["player"], "".join(cards(row["hand"], 2)), tuple(row["history"])): row["actions"]
            for row in result["strategy"]}
    start_pot = result["pot"]
    player_names = ("oop", "ip")

    def payoff(kind, winner, sign, contributions, target):
        matched = min(contributions)
        if kind == "fold":
            oop_value = (1 if winner == 0 else -1) * (start_pot / 2 + matched)
        else:
            oop_value = sign * (start_pot / 2 + matched)
        return oop_value if target == 0 else -oop_value

    def deal_value(i, j, sign, policy=None, target=0):
        def play(history, actor, contributions):
            actor_hand = hand_names[actor][i if actor == 0 else j]
            actions = rows[(player_names[actor], actor_hand, history)]
            if policy is not None and actor == target:
                action_indexes = (policy[(actor_hand, history)],)
            else:
                action_indexes = range(len(actions))
            value = 0.0
            for action_index in action_indexes:
                action = actions[action_index]
                name = action["name"]
                next_contributions = list(contributions)
                if name in {"bet", "raise", "all_in"}:
                    next_contributions[actor] = action["raise_to"]
                if name == "call":
                    next_contributions[actor] += action["amount"]
                if name == "fold":
                    branch = payoff("fold", 1 - actor, sign, next_contributions, target)
                elif name == "call" or (name == "check" and history and history[-1] == "check"):
                    branch = payoff("showdown", None, sign, next_contributions, target)
                else:
                    branch = play(history + (action["history_key"],), 1 - actor,
                                  next_contributions)
                if policy is None or actor != target:
                    branch *= action["probability"]
                value += branch
            return value

        return play((), 0, (0.0, 0.0))

    expected_oop_value = sum(weight * deal_value(i, j, sign)
                             for i, j, weight, sign in deals)
    best_responses = []
    for responder in (0, 1):
        infos = [(hand_name, history, len(actions))
                 for (player, hand_name, history), actions in rows.items()
                 if player == player_names[responder]]
        policy_values = []
        for choices in itertools.product(*(range(action_count)
                                           for _, _, action_count in infos)):
            policy = {(hand_name, history): action_index
                      for (hand_name, history, _), action_index in zip(infos, choices)}
            policy_values.append(sum(weight * deal_value(i, j, sign, policy, responder)
                                     for i, j, weight, sign in deals))
        best_responses.append(max(policy_values))
    return expected_oop_value, tuple(best_responses)


class RiverConfigurationTests(unittest.TestCase):
    def test_configuration_is_deterministic_and_json_serializable(self):
        config = RiverConfig(100, 500, (.75, .33, .75), (.75,), 1, True)
        normalized = RiverConfig.from_dict(config.to_dict())
        self.assertEqual(config, normalized)
        self.assertEqual(config.bet_sizes, (.33, .75))
        self.assertEqual(json.dumps(config.to_dict()), json.dumps(normalized.to_dict()))

    def test_per_player_effective_stack_caps_round_trip(self):
        config = RiverConfig(100, (500, 120), (3,), (), 0, False)
        self.assertEqual(config.stacks, (500, 120))
        self.assertEqual(config.to_dict()["effective_stack"], [500, 120])
        self.assertEqual(RiverConfig.from_dict(config.to_dict()), config)

    def test_solve_exposes_per_player_stack_caps_and_short_call_amount(self):
        result = solve(BOARD, "AsAh", "KcKd", iterations=50,
                       config=RiverConfig(100, (500, 120), (3,), (), 0, False))
        self.assertEqual(result["effective_stack"], [500, 120])
        facing_bet = next(row for row in result["strategy"]
                          if row["player"] == "ip" and row["history"] == ["bet@300"])
        call = next(action for action in facing_bet["actions"] if action["name"] == "call")
        self.assertEqual(call["amount"], 120)
        self.assertAlmostEqual(sum(action["probability"] for action in facing_bet["actions"]), 1)

    def test_multiple_bet_sizes_are_distinct_and_change_tree(self):
        single, _ = _build_tree(RiverConfig(100, 500, (.5,), (), 0, False))
        several, _ = _build_tree(RiverConfig(100, 500, (.33, .75, 1), (), 0, False))
        root = find_node(several, ())
        self.assertEqual([action.raise_to for action in root.actions[1:]], [33, 75, 100])
        self.assertGreater(len(root.children), len(find_node(single, ()).children))

    def test_first_bet_is_configured_fraction_of_current_pot(self):
        root, _ = _build_tree(RiverConfig(100, 500, (.75,), (), 0, False))
        self.assertEqual(root.actions[1].amount, 75)
        self.assertEqual(root.actions[1].raise_to, 75)

    def test_raise_fraction_uses_pot_after_call_and_raise_to_total(self):
        root, _ = _build_tree(RiverConfig(100, 500, (.75,), (.75,), 1, False))
        facing_bet = find_node(root, ("bet@75",))
        raise_action = next(action for action in facing_bet.actions if action.name == "raise")
        self.assertEqual(raise_action.raise_to, 262.5)
        self.assertEqual(raise_action.amount, 262.5)
        self.assertEqual(100 + 75 + 75, 250)
        self.assertEqual(raise_action.raise_to, 0 + 75 + .75 * 250)

    def test_minimum_full_raise_is_enforced_by_normalizing_small_sizes(self):
        root, _ = _build_tree(RiverConfig(100, 500, (.1,), (.01,), 1, False))
        facing_bet = find_node(root, ("bet@10",))
        raise_action = next(action for action in facing_bet.actions if action.name == "raise")
        self.assertEqual(raise_action.raise_to, 20)
        self.assertTrue(raise_action.full_raise)

    def test_raise_to_uses_existing_commitment_after_a_prior_raise(self):
        root, _ = _build_tree(RiverConfig(100, 500, (.75,), (.75, .1), 2, False))
        facing_first_bet = find_node(root, ("bet@75",))
        first_raise = next(action for action in facing_first_bet.actions
                           if action.name == "raise" and action.raise_to == 262.5)
        facing_raise = find_node(root, ("bet@75", first_raise.token))
        second_raise = next(action for action in facing_raise.actions
                            if action.name == "raise")
        self.assertEqual(second_raise.raise_to, 450)
        self.assertEqual(second_raise.amount, 375)

    def test_short_all_in_is_allowed_but_does_not_reopen_raising(self):
        root, _ = _build_tree(RiverConfig(100, 120, (.75,), (.75,), 2, True))
        facing_bet = find_node(root, ("bet@75",))
        shove = next(action for action in facing_bet.actions if action.name == "all_in")
        self.assertEqual(shove.raise_to, 120)
        self.assertFalse(shove.full_raise)
        response = find_node(root, ("bet@75", shove.token))
        self.assertEqual([action.name for action in response.actions], ["fold", "call"])

    def test_stack_clipped_configured_short_raise_does_not_require_separate_shove(self):
        root, _ = _build_tree(RiverConfig(100, 120, (.75,), (.75, 1), 1, False))
        facing_bet = find_node(root, ("bet@75",))
        shoves = [action for action in facing_bet.actions if action.name == "all_in"]
        self.assertEqual(len(shoves), 1)
        shove = shoves[0]
        self.assertEqual(shove.raise_to, 120)
        self.assertFalse(shove.full_raise)

    def test_min_raise_above_stack_normalizes_to_short_all_in_without_shove_flag(self):
        root, _ = _build_tree(RiverConfig(100, 120, (.75,), (.01,), 1, False))
        facing_bet = find_node(root, ("bet@75",))
        shove = next(action for action in facing_bet.actions if action.name == "all_in")
        self.assertEqual(shove.raise_to, 120)
        self.assertFalse(shove.full_raise)

    def test_full_all_in_raise_is_marked_as_a_full_raise(self):
        root, _ = _build_tree(RiverConfig(100, 200, (.75,), (.75,), 2, True))
        facing_bet = find_node(root, ("bet@75",))
        shove = next(action for action in facing_bet.actions if action.name == "all_in")
        self.assertEqual(shove.raise_to, 200)
        self.assertTrue(shove.full_raise)

    def test_effective_stack_limits_all_actions(self):
        root, _ = _build_tree(RiverConfig(100, 80, (.75, 1), (.75,), 2, True))
        self.assertEqual([action.raise_to for action in root.actions[1:]], [75, 80])
        node = find_node(root, ("all_in@80",))
        self.assertIsNotNone(node)
        self.assertTrue(all(action.raise_to <= 80 for action in node.actions))

    def test_bet_sizes_collapsing_to_all_in_are_deduplicated(self):
        root, _ = _build_tree(RiverConfig(100, 50, (.75, 1), (), 0, True))
        self.assertEqual(len(root.actions), 2)
        self.assertEqual(root.actions[1].name, "all_in")
        self.assertEqual(root.actions[1].raise_to, 50)

    def test_rounding_duplicate_chip_actions_are_removed(self):
        root, _ = _build_tree(RiverConfig(100, 500, (.5, .50000000001), (), 0, False))
        self.assertEqual(len(root.actions), 2)

    def test_maximum_raise_depth_is_enforced(self):
        no_raise, _ = _build_tree(RiverConfig(100, 500, (.75,), (.75,), 0, False))
        facing_bet = find_node(no_raise, ("bet@75",))
        self.assertEqual([action.name for action in facing_bet.actions], ["fold", "call"])
        one_raise, _ = _build_tree(RiverConfig(100, 500, (.75,), (.75,), 1, False))
        facing_raise = find_node(one_raise, ("bet@75", "raise@262.5"))
        self.assertEqual([action.name for action in facing_raise.actions], ["fold", "call"])

    def test_uncalled_excess_is_returned_at_fold_or_showdown(self):
        # IP's 300 commitment is reduced to the matched 100; the 200 excess is returned.
        folded = _Terminal("fold", (100, 300), winner=1)
        showdown = _Terminal("showdown", (120, 300))
        self.assertEqual(_terminal_value(folded, 1, 100), -150)
        self.assertEqual(_terminal_value(showdown, 1, 100), 170)

    def test_short_stack_call_returns_uncalled_bet_excess(self):
        root, _ = _build_tree(RiverConfig(100, (500, 120), (3,), (), 0, False))
        facing_bet = find_node(root, ("bet@300",))
        call = next(action for action in facing_bet.actions if action.name == "call")
        self.assertEqual(call.amount, 120)
        terminal = facing_bet.children[1]
        self.assertEqual(terminal.contributions, (300, 120))
        self.assertEqual(_terminal_value(terminal, 1, 100), 170)
        self.assertEqual(_terminal_value(terminal, -1, 100), -170)

    def test_invalid_raise_depth_and_empty_bet_configuration_are_rejected(self):
        with self.assertRaises(ValueError):
            RiverConfig(max_raises=-1)
        with self.assertRaises(ValueError):
            RiverConfig(bet_sizes=())


class ConfiguredStrategyTests(unittest.TestCase):
    def setUp(self):
        self.config = RiverConfig(100, 500, (.33, 1), (.75,), 1, False)

    def test_information_sets_and_strategy_histories_distinguish_bet_sizes(self):
        result = solve(BOARD, "AsAh,KsKh", "AcAd,KcKd", iterations=200,
                       config=self.config)
        ip_histories = {tuple(row["history"]) for row in result["strategy"]
                        if row["player"] == "ip"}
        self.assertIn(("bet@33",), ip_histories)
        self.assertIn(("bet@100",), ip_histories)
        self.assertIn(("check",), ip_histories)

    def test_strategy_actions_are_legal_explicit_and_normalized(self):
        equilibrium = solve_equilibrium(BOARD, "AsAh,KsKh", "AcAd,KcKd",
                                        iterations=200, config=self.config)
        infoset = InfoSet("ip", "AcAd", ("bet@33",))
        actions = equilibrium.legal_actions(infoset)
        self.assertEqual({action.name for action in actions}, {"fold", "call", "raise"})
        self.assertEqual(next(a for a in actions if a.name == "raise").raise_to, 157.5)
        distribution = equilibrium.strategy_at(infoset)
        self.assertAlmostEqual(sum(probability for _, probability in distribution), 1)
        self.assertTrue(all(0 <= probability <= 1 for _, probability in distribution))

    def test_sized_history_keys_are_required_when_action_name_is_ambiguous(self):
        equilibrium = solve_equilibrium(BOARD, "AsAh", "KcKd", iterations=50,
                                        config=self.config)
        with self.assertRaises(ValueError):
            equilibrium.legal_actions(InfoSet("ip", "KcKd", ("bet",)))
        token = next(action.history_key for action in
                     equilibrium.legal_actions(InfoSet("oop", "AsAh"))
                     if action.name == "bet" and action.raise_to == 33)
        self.assertEqual(token, "bet@33")
        self.assertEqual(equilibrium.legal_actions(InfoSet("ip", "KcKd", (token,)))[0].name,
                         "fold")

    def test_config_property_returns_a_defensive_serializable_copy(self):
        equilibrium = solve_equilibrium(BOARD, "AsAh", "KcKd", iterations=50,
                                        config=self.config)
        reported = equilibrium.config
        reported["bet_sizes"].append(99)
        self.assertEqual(equilibrium.config["bet_sizes"], [.33, 1.0])

    def test_best_response_and_nashconv_work_with_multi_size_raise_tree(self):
        result = solve(BOARD, "AsAh,KsKh", "AcAd,KcKd", iterations=300,
                       config=RiverConfig(100, 500, (.33, .75), (.75,), 1, False))
        self.assertAlmostEqual(result["value_oop"] + result["value_ip"], 0)
        self.assertAlmostEqual(result["nash_conv"],
                               result["oop_best_response_value"] +
                               result["ip_best_response_value"])
        self.assertGreaterEqual(result["nash_conv"], 0)
        self.assertGreater(result["info_sets"], 0)

    def test_more_training_reduces_multi_size_exploitability(self):
        config = RiverConfig(100, 300, (.5, 1), (.75,), 1, False)
        low = solve(BOARD, "AsAh,KsKh,QsQh", "AcAd,KcKd,QcQd",
                    iterations=10, config=config)
        high = solve(BOARD, "AsAh,KsKh,QsQh", "AcAd,KcKd,QcQd",
                     iterations=1800, config=config)
        self.assertGreater(low["nash_conv"], 0)
        self.assertLess(high["nash_conv"], low["nash_conv"] / 2)

    def test_best_response_matches_independent_oracle_on_multi_size_tree(self):
        oop_range = "AsAh:0.5,KsKh:1"
        ip_range = "AcAd:1,KcKd:0.75"
        result = solve(BOARD, oop_range, ip_range, iterations=120,
                       config=RiverConfig(100, 300, (.33, .75), (), 0, False))
        value, (br_oop, br_ip) = public_result_oracle(result, BOARD, oop_range, ip_range)
        self.assertAlmostEqual(value, result["value_oop"], places=8)
        self.assertAlmostEqual(br_oop + br_ip, result["nash_conv"], places=8)
        self.assertGreaterEqual(br_oop, value - 1e-9)
        self.assertGreaterEqual(br_ip, -value - 1e-9)

    def test_best_response_matches_independent_oracle_on_raise_enabled_tree(self):
        oop_range = "AsAh:0.5,KsKh:1"
        ip_range = "AcAd:1,KcKd:0.75"
        result = solve(BOARD, oop_range, ip_range, iterations=120,
                       config=RiverConfig(100, 300, (.75,), (.75,), 1, False))
        value, (br_oop, br_ip) = public_result_oracle(result, BOARD, oop_range, ip_range)
        self.assertAlmostEqual(value, result["value_oop"], places=8)
        self.assertAlmostEqual(br_oop + br_ip, result["nash_conv"], places=8)
        self.assertGreaterEqual(br_oop, value - 1e-9)
        self.assertGreaterEqual(br_ip, -value - 1e-9)

    def test_public_policy_oracle_preserves_card_removal_weights(self):
        oop_range = "AsAh,KsKh"
        ip_range = "AsKd,AcAd"
        result = solve(BOARD, oop_range, ip_range, iterations=80,
                       config=RiverConfig(100, 200, (.5, 1), (), 0, False))
        self.assertEqual(result["deals"], 3)
        value, (br_oop, br_ip) = public_result_oracle(result, BOARD, oop_range, ip_range)
        self.assertAlmostEqual(value, result["value_oop"], places=8)
        self.assertAlmostEqual(br_oop + br_ip, result["nash_conv"], places=8)

    def test_exhaustive_pure_policy_does_not_peek_at_opponent_hand(self):
        oop_range = "AsAh"
        ip_range = "AcAd,JhJc"
        tie_hand = "".join(cards("AcAd", 2))
        result = solve(BOARD, oop_range, ip_range, iterations=20,
                       config=RiverConfig(100, 200, (.5,), (), 0, False))
        for row in result["strategy"]:
            if row["player"] != "ip":
                continue
            if row["history"] == ["bet@50"]:
                selected = "fold" if row["hand"] == tie_hand else "call"
                row["actions"] = [dict(action, probability=float(action["name"] == selected))
                                   for action in row["actions"]]
            elif row["history"] == ["check"]:
                row["actions"] = [dict(action, probability=float(action["name"] == "check"))
                                   for action in row["actions"]]

        _, (legal_oop_br, _) = public_result_oracle(result, BOARD, oop_range, ip_range)
        # The tie hand folds to a bet, while the stronger hand calls it. A
        # cheating response bets only into the tie and checks into the winner.
        opponent_weights = expand_range(ip_range, cards(BOARD, 5))
        deal_mass = sum(weight for weight in opponent_weights.values())
        tie_fold_value = result["pot"] / 2
        strong_check_value = -result["pot"] / 2
        cheating_value = sum(
            opponent_weights[hand] / deal_mass *
            (tie_fold_value if "".join(hand) == tie_hand else strong_check_value)
            for hand in opponent_weights
        )
        self.assertAlmostEqual(legal_oop_br, -25.0, places=8)
        self.assertAlmostEqual(cheating_value, 0.0, places=8)
        self.assertGreater(cheating_value, legal_oop_br)

    def test_scalar_bet_metadata_requires_one_shared_actual_opening_amount(self):
        legacy = solve(BOARD, "AsAh", "KcKd", pot=100, bet=50, iterations=20)
        self.assertEqual(legacy["bet"], 50)

        clipped = solve(BOARD, "AsAh", "KcKd", iterations=20,
                        config=RiverConfig(100, 50, (1,), (), 0, False))
        self.assertEqual(clipped["bet"], 50)
        self.assertEqual(clipped["strategy"][0]["actions"][1]["raise_to"], 50)

        multiple_sizes = solve(BOARD, "AsAh", "KcKd", iterations=20,
                               config=RiverConfig(100, 300, (.5, 1), (), 0, False))
        self.assertIsNone(multiple_sizes["bet"])

        asymmetric = solve(BOARD, "AsAh", "KcKd", iterations=20,
                           config=RiverConfig(100, (120, 50), (.75,), (.75,), 1, True))
        self.assertIsNone(asymmetric["bet"])
        oop_open = next(row for row in asymmetric["strategy"]
                        if row["player"] == "oop" and row["history"] == [])
        ip_open = next(row for row in asymmetric["strategy"]
                       if row["player"] == "ip" and row["history"] == ["check"])
        self.assertEqual(oop_open["actions"][1]["raise_to"], 75)
        self.assertEqual(ip_open["actions"][1]["raise_to"], 50)


if __name__ == "__main__":
    unittest.main()
