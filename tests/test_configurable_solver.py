import json
import unittest

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


class RiverConfigurationTests(unittest.TestCase):
    def test_configuration_is_deterministic_and_json_serializable(self):
        config = RiverConfig(100, 500, (.75, .33, .75), (.75,), 1, True)
        normalized = RiverConfig.from_dict(config.to_dict())
        self.assertEqual(config, normalized)
        self.assertEqual(config.bet_sizes, (.33, .75))
        self.assertEqual(json.dumps(config.to_dict()), json.dumps(normalized.to_dict()))

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


if __name__ == "__main__":
    unittest.main()
