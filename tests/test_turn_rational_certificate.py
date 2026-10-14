"""Exact arithmetic, information-set, and resource-bound regressions."""
import copy
import unittest
from fractions import Fraction as F

from scripts import turn_river_validation as validator
from scripts.audit_turn_rational_certificate import FLOAT_TOLERANCE
from scripts.river_analytical import equilibrium, metrics as analytical_metrics
from scripts.turn_rational_certificate import (
    MAX_EXACT_DEPTH, MAX_EXACT_WORK, MAX_FRACTION_BITS, evaluate_exact,
)


BOARD = ("2c", "7d", "9h", "Js", "Kd")


def _action(name, amount=0.0, target=0.0):
    return validator._Action(name, amount, target)


def _worlds(signs, weights, *, oop_hands=None, ip_hands=None, rivers=None):
    oop_hands = oop_hands or [("Ah", "As")] * len(signs)
    ip_hands = ip_hands or [("Qh", "Qs")] * len(signs)
    rivers = rivers or [None] * len(signs)
    return [{"hands": (tuple(oop_hands[i]), tuple(ip_hands[i])),
             "river": rivers[i], "weight": F(weights[i]), "sign": signs[i],
             "board": BOARD}
            for i in range(len(signs))]


def _serialized_row(player, hand, history, actions, probabilities):
    return {
        "player": "oop" if player == 0 else "ip",
        "hand": hand,
        "street": "river",
        "board": list(BOARD),
        "history": list(history),
        "actions": [
            {"name": action.name, "amount": action.amount,
             "raise_to": action.raise_to, "history_key": action.token,
             "probability": float(probability)}
            for action, probability in zip(actions, probabilities)
        ],
    }


def _equilibrium_anchor():
    """Complete 100-chip one-bet anchor with the production all-in token."""
    analytic, expected_value = equilibrium(F(1, 2), pot=100, bet=100)
    check = _action("check")
    bet = _action("all_in", 100.0, 100.0)
    fold = _action("fold")
    call = _action("call", 100.0, 100.0)
    showdown_check = validator._Terminal("showdown", (0.0, 0.0))
    after_ip_bet_fold = validator._Terminal("fold", (0.0, 100.0), winner=1)
    after_ip_bet_call = validator._Terminal("showdown", (100.0, 100.0))
    oop_after_check_bet = validator._Decision(
        0, ("check", bet.token), BOARD, (fold, call),
        (after_ip_bet_fold, after_ip_bet_call))
    ip_after_check = validator._Decision(
        1, ("check",), BOARD, (check, bet),
        (showdown_check, oop_after_check_bet))
    after_oop_bet_fold = validator._Terminal("fold", (100.0, 0.0), winner=0)
    after_oop_bet_call = validator._Terminal("showdown", (100.0, 100.0))
    ip_after_oop_bet = validator._Decision(
        1, (bet.token,), BOARD, (fold, call),
        (after_oop_bet_fold, after_oop_bet_call))
    root = validator._Decision(0, (), BOARD, (check, bet),
                               (ip_after_check, ip_after_oop_bet))

    nuts, air, catcher = "AhAs", "3c4c", "QhQs"
    policies = {
        (0, nuts, ()): analytic[(0, "nuts", ())],
        (0, air, ()): analytic[(0, "air", ())],
        (1, catcher, ("check",)): analytic[(1, "catcher", ("check",))],
        (1, catcher, (bet.token,)): analytic[(1, "catcher", ("bet",))],
        (0, nuts, ("check", bet.token)): analytic[(0, "nuts", ("check", "bet"))],
        (0, air, ("check", bet.token)): analytic[(0, "air", ("check", "bet"))],
    }
    result = {"strategy": [
        _serialized_row(0, nuts, (), (check, bet), policies[(0, nuts, ())]),
        _serialized_row(0, air, (), (check, bet), policies[(0, air, ())]),
        _serialized_row(1, catcher, ("check",), (check, bet),
                        policies[(1, catcher, ("check",))]),
        _serialized_row(1, catcher, (bet.token,), (fold, call),
                        policies[(1, catcher, (bet.token,))]),
        _serialized_row(0, nuts, ("check", bet.token), (fold, call),
                        policies[(0, nuts, ("check", bet.token))]),
        _serialized_row(0, air, ("check", bet.token), (fold, call),
                        policies[(0, air, ("check", bet.token))]),
    ]}
    worlds = _worlds((1, -1), (F(1, 2), F(1, 2)),
                     oop_hands=(("Ah", "As"), ("3c", "4c")))
    config = {
        "pot": 100.0, "effective_stack": [100.0, 100.0],
        "bet_sizes": [1.0], "raise_sizes": [], "max_raises": 0,
        "include_all_in": False,
    }
    metrics = {
        "value_oop": 25.0, "value_ip": -25.0,
        "oop_best_response_value": 25.0, "ip_best_response_value": -25.0,
        "oop_best_response_gain": 0.0, "ip_best_response_gain": 0.0,
        "nash_conv": 0.0, "exploitability": 0.0,
    }
    result = {
        "strategy": result["strategy"], "board": list(BOARD), "runouts": [],
        "runout_mode": "none", "reachable_runouts": [],
        "info_sets": 6, "worlds": 2, "compatible_pairs": 2,
        "config": config, **metrics,
    }
    return root, worlds, policies, result, expected_value


def _chance_toy():
    """Decision precedes public chance; clairvoyance would add ten chips."""
    a, b = _action("a"), _action("b")
    # World L has mass 1/3 and world R mass 2/3. Both actions have EV zero.
    # A clairvoyant chooses +15 in L and +7.5 in R, worth exactly 10.
    a_chance = validator._Chance(("a",), {
        "L": validator._Terminal("showdown", (10.0, 10.0)),
        "R": validator._Terminal("showdown", (2.5, 2.5)),
    })
    b_chance = validator._Chance(("b",), {
        "L": validator._Terminal("showdown", (10.0, 10.0)),
        "R": validator._Terminal("showdown", (2.5, 2.5)),
    })
    root = validator._Decision(0, (), BOARD, (a, b), (a_chance, b_chance))
    # The sign is selected per action's public chance branch by dedicated
    # worlds in the test below, so use separate tree leaves for action signs.
    a_chance.branches["R"] = validator._Terminal("fold", (2.5, 2.5), winner=1)
    b_chance.branches["L"] = validator._Terminal("fold", (10.0, 10.0), winner=1)
    b_chance.branches["R"] = validator._Terminal("fold", (2.5, 2.5), winner=0)
    policies = {(0, "AhAs", ()): (1.0, 0.0)}
    result = {"strategy": [_serialized_row(0, "AhAs", (), (a, b), (1.0, 0.0))]}
    worlds = _worlds((1, -1), (F(1, 3), F(2, 3)),
                     oop_hands=(("Ah", "As"), ("Ah", "As")),
                     ip_hands=(("Kh", "Ks"), ("Qh", "Qs")),
                     rivers=("L", "R"))
    return root, worlds, policies, result


def _hidden_hand_toy(player):
    first, second = _action("first"), _action("second")
    if player == 0:
        # OOP's one visible decision sees two hidden IP hands. A public card
        # arrives only after the decision and changes which action is best.
        hands = ((("Ah", "As"), ("Kh", "Ks")),
                 (("Ah", "As"), ("Qh", "Qs")))
        key_hand = "AhAs"
    else:
        # Symmetric test: IP sees two hidden OOP hands at its one decision.
        hands = ((("Ah", "As"), ("Qh", "Qs")),
                 (("Kc", "Kd"), ("Qh", "Qs")))
        key_hand = "QhQs"
    # Pot 10 and matched 5 yield +/-10 at showdown. The second action is a
    # constant +5 OOP fold-win, or -5 when IP is the responder.
    showdown = validator._Chance(("first",), {
        "L": validator._Terminal("showdown", (5.0, 5.0)),
        "R": validator._Terminal("showdown", (5.0, 5.0)),
    })
    constant_sign = 0 if player == 0 else 1
    fixed = validator._Terminal("fold", (0.0, 0.0), winner=constant_sign)
    fixed_chance = validator._Chance(("second",), {"L": fixed, "R": fixed})
    root = validator._Decision(player, (), BOARD, (first, second),
                               (showdown, fixed_chance))
    worlds = _worlds((1, -1), (F(1, 2), F(1, 2)),
                     oop_hands=tuple(pair[0] for pair in hands),
                     ip_hands=tuple(pair[1] for pair in hands), rivers=("L", "R"))
    policy = (0.5, 0.5)
    policies = {(player, key_hand, ()): policy}
    result = {"strategy": [_serialized_row(player, key_hand, (),
                                           (first, second), policy)]}
    return root, worlds, policies, result


class TurnRationalCertificateTests(unittest.TestCase):
    def test_known_one_bet_profile_has_exact_value_25_and_exhaustive_br_anchor(self):
        root, worlds, policies, result, expected_value = _equilibrium_anchor()
        original = copy.deepcopy(result)
        float_oracle = validator.replay_policy(
            result, "AsAh:1,3c4c:1", "QsQh:1", board=BOARD,
            config=result["config"])
        float_deltas = validator.compare_result(
            result, float_oracle, tolerance=FLOAT_TOLERANCE)
        self.assertTrue(all(abs(delta) <= FLOAT_TOLERANCE
                            for delta in float_deltas.values()))
        self.assertEqual(float_oracle["value_oop"], F(25))
        exact = evaluate_exact(root, worlds, policies, 100, result=result)
        self.assertEqual(expected_value, F(25))
        self.assertEqual(exact["metrics"]["value_oop"], F(25))
        self.assertEqual(exact["metrics"]["oop_best_response_value"], F(25))
        self.assertEqual(exact["metrics"]["ip_best_response_value"], F(-25))
        self.assertEqual(exact["lower_value_bound"], F(25))
        self.assertEqual(exact["upper_value_bound"], F(25))
        self.assertEqual(exact["metrics"]["nash_conv"], F(0))
        self.assertTrue(exact["threshold_met"])
        # Separate exhaustive 16/4 pure-response crosscheck from the tiny
        # analytical anchor, not from the floating poker replay.
        profile = equilibrium(F(1, 2), pot=100, bet=100)[0]
        value, oop_br, ip_br = analytical_metrics(profile, F(1, 2), 100, 100)
        self.assertEqual((value, oop_br, ip_br), (F(25), F(25), F(-25)))
        self.assertEqual(len(exact["normalization_ledger"]), 6)
        self.assertEqual(result, original)
        off_path = next(entry for entry in exact["normalization_ledger"]
                        if entry["player"] == "oop" and entry["hand"] == "AhAs"
                        and entry["history"] == ["check", "all_in@100"])
        self.assertEqual([action["name"] for action in off_path["actions"]],
                         ["fold", "call"])

    def test_public_chance_is_summed_before_turn_max_even_on_zero_reach_branch(self):
        root, worlds, policies, result = _chance_toy()
        exact = evaluate_exact(root, worlds, policies, 10, result=result)
        self.assertEqual(exact["metrics"]["oop_best_response_value"], F(0))
        self.assertEqual(exact["metrics"]["value_oop"], F(0))
        # This independently calculated clairvoyant value incorrectly chooses
        # the best action separately in each hidden future world.
        clairvoyant = (worlds[0]["weight"] * F(15) +
                       worlds[1]["weight"] * F(15, 2))
        self.assertEqual(clairvoyant, F(10))
        self.assertNotEqual(exact["metrics"]["oop_best_response_value"], clairvoyant)
        self.assertEqual(exact["work_by_kind"]["chance_group_entries_scanned"], 12)

    def test_hidden_opponent_hand_cannot_split_one_own_information_set(self):
        for player in (0, 1):
            with self.subTest(player=player):
                root, worlds, policies, result = _hidden_hand_toy(player)
                exact = evaluate_exact(root, worlds, policies, 10, result=result)
                response = (exact["metrics"]["oop_best_response_value"] if player == 0
                            else exact["metrics"]["ip_best_response_value"])
                self.assertEqual(response, F(5))
                self.assertEqual(exact["tree_nodes"], 7)
                # Independent worldwise choices would be worth 7.5 chips:
                # OOP selects +10/-5 and IP selects -5/-10.
                clairvoyant = F(15, 2)
                self.assertLess(response, clairvoyant)

    def test_exact_row_normalization_ledger_preserves_input_and_records_amounts(self):
        root, worlds, policies, result, _ = _equilibrium_anchor()
        before_result = copy.deepcopy(result)
        before_policies = copy.deepcopy(policies)
        key = (0, "3c4c", ())
        policies[key] = (0.5000000001, 0.5)
        row = next(row for row in result["strategy"]
                   if row["player"] == "oop" and row["hand"] == "3c4c"
                   and not row["history"])
        row["actions"][0]["probability"] = 0.5000000001
        row["actions"][1]["probability"] = 0.5
        changed_result = copy.deepcopy(result)
        changed_policies = copy.deepcopy(policies)
        exact = evaluate_exact(root, worlds, policies, 100, result=result)
        self.assertGreater(exact["max_row_adjustment"], 0)
        self.assertTrue(any(action["adjustment_fraction"] != "0"
                            for entry in exact["normalization_ledger"]
                            for action in entry["actions"]))
        self.assertEqual(result, changed_result)
        self.assertEqual(policies, changed_policies)
        self.assertNotEqual(result, before_result)
        self.assertNotEqual(policies, before_policies)
        self.assertTrue(any(action["amount"] == 100.0
                            for row in exact["normalized_policy_rows"]
                            for action in row["actions"]))

    def test_work_depth_and_fraction_bit_caps_reject_without_mutation(self):
        root, worlds, policies, result, _ = _equilibrium_anchor()
        snapshots = (copy.deepcopy(worlds), copy.deepcopy(policies), copy.deepcopy(result))
        with self.assertRaisesRegex(ValueError, "work limit"):
            evaluate_exact(root, worlds, policies, 100, result=result, max_work=1)
        with self.assertRaisesRegex(ValueError, "depth limit"):
            evaluate_exact(root, worlds, policies, 100, result=result, max_depth=2)
        huge_worlds = copy.deepcopy(worlds)
        huge_worlds[0]["weight"] = F(1, 1 << 20)
        with self.assertRaisesRegex(ValueError, "bit limit"):
            evaluate_exact(root, huge_worlds, policies, 100, result=result, max_bits=8)
        for limits in (
                {"max_work": MAX_EXACT_WORK + 1},
                {"max_depth": MAX_EXACT_DEPTH + 1},
                {"max_bits": MAX_FRACTION_BITS + 1},
                {"max_work": True}, {"max_depth": 0}, {"max_bits": 1.5}):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                evaluate_exact(root, worlds, policies, 100, result=result, **limits)
        self.assertEqual(worlds, snapshots[0])
        self.assertEqual(policies, snapshots[1])
        self.assertEqual(result, snapshots[2])


if __name__ == "__main__":
    unittest.main()
