"""Independent raised-river histories and exhaustive legal pure responses."""
from fractions import Fraction as F
from itertools import product
import math
import unittest

from pokerlab.matrix_free_river import solve_matrix_free_river
from scripts import turn_river_validation as validator
from scripts.turn_rational_certificate import evaluate_exact

B = "bet@100"
R = "all_in@200"
HANDS = ("AhAs", "3c4c")
CATCHER = "QhQs"


def literal_profile_value(policy, *, peek_ip=False):
    """Nine terminal histories; OOP signs +1/-1, equal original priors."""
    total = F(0)
    for hand, sign in zip(HANDS, (1, -1)):
        check, bet = policy[0, hand, ()]
        ip_fold, ip_call, ip_raise = policy[1, CATCHER, (B,)]
        if peek_ip:
            ip_fold, ip_call, ip_raise = (
                (F(1), F(0), F(0)) if sign == 1 else (F(0), F(0), F(1)))
        oop_fold_raise, oop_call_raise = policy[0, hand, (B, R)]
        wager_value = ip_fold * 50 + ip_call * sign * 150 + ip_raise * (
            -oop_fold_raise * 150 + oop_call_raise * sign * 250)
        ip_check, ip_bet = policy[1, CATCHER, ("check",)]
        oop_fold, oop_call, oop_raise = policy[0, hand, ("check", B)]
        ip_fold_raise, ip_call_raise = policy[1, CATCHER, ("check", B, R)]
        checked_value = ip_check * sign * 50 + ip_bet * (
            -oop_fold * 50 + oop_call * sign * 150 + oop_raise * (
                ip_fold_raise * 150 + ip_call_raise * sign * 250))
        total += (check * checked_value + bet * wager_value) / 2
    return total


def exhaustive_response(policy, player):
    keys = sorted(key for key in policy if key[0] == player)
    count = math.prod(len(policy[key]) for key in keys)
    best = None
    for choices in product(*(range(len(policy[key])) for key in keys)):
        candidate = dict(policy)
        for key, action in zip(keys, choices):
            candidate[key] = tuple(F(index == action) for index in range(len(policy[key])))
        value = literal_profile_value(candidate) * (1 if player == 0 else -1)
        best = value if best is None else max(best, value)
    return count, best


class RiverRationalIndependentReviewTests(unittest.TestCase):
    def test_raised_private_information_matches_literal_exhaustive_responses(self):
        board_text = "2c7d9hJsKd"
        oop, ip = "AsAh,3c4c", "QsQh"
        config = dict(pot=100, effective_stack=200, bet_sizes=[1], raise_sizes=[1],
                      max_raises=1, include_all_in=False)
        result = solve_matrix_free_river(board_text, oop, ip, config, iterations=10)
        expected_actions = {
            (0, ()): ("check", B), (0, (B, R)): ("fold", "call"),
            (0, ("check", B)): ("fold", "call", R),
            (1, (B,)): ("fold", "call", R), (1, ("check",)): ("check", B),
            (1, ("check", B, R)): ("fold", "call"),
        }
        literal = {}
        for row in result["strategy"]:
            player = 0 if row["player"] == "oop" else 1
            history = tuple(row["history"])
            tokens = tuple(action["history_key"] for action in row["actions"])
            self.assertEqual(tokens, expected_actions[player, history])
            selected = B if not history else "check" if tokens[0] == "check" else "call"
            values = tuple(F(token == selected) for token in tokens)
            literal[player, row["hand"], history] = values
            for action, value in zip(row["actions"], values):
                action["probability"] = float(value)
        self.assertEqual(len(literal), 9)
        self.assertEqual(literal_profile_value(literal), F(0))
        self.assertEqual(exhaustive_response(literal, 0), (144, F(50)))
        self.assertEqual(exhaustive_response(literal, 1), (12, F(0)))
        self.assertEqual(-literal_profile_value(literal, peek_ip=True), F(100))
        expected = dict(
            value_oop=F(0), value_ip=F(0), oop_best_response_value=F(50),
            ip_best_response_value=F(0), oop_best_response_gain=F(50),
            ip_best_response_gain=F(0), nash_conv=F(50), exploitability=F(25))
        result.update({key: float(value) for key, value in expected.items()})
        replay = validator.replay_policy(result, oop, ip, board=board_text, config=config)
        validator.compare_result(result, replay, tolerance=1e-12)
        board = validator.cards(board_text)
        numeric_config = validator._config(config, "config")
        ranges = (validator.expand_range(oop, board), validator.expand_range(ip, board))
        worlds, selected = validator._worlds(board, ranges, None)
        root = validator._public_tree(board, numeric_config, numeric_config, selected, worlds)
        policies = validator._validate_policy(
            result, root, validator._collect_nodes(root), worlds, board, selected,
            runouts_were_omitted=True)
        exact = evaluate_exact(root, worlds, policies, 100, result=result)
        self.assertEqual(exact["metrics"], expected)
        self.assertEqual(exact["lower_value_bound"], F(0))
        self.assertEqual(exact["upper_value_bound"], F(50))
        self.assertFalse(exact["threshold_met"])


if __name__ == "__main__":
    unittest.main()
