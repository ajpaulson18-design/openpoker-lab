"""Exact synthetic turn/chance/river proof for own-realization tail extraction."""
from fractions import Fraction as F
import unittest

from scripts.river_tail_realization import reconstruct_tail


D, T = 1, 3
CHANCE_MASS = {"2c": F(1, 3), "3c": F(2, 3)}
HAND = {"oop": "OOP-hand", "ip": "IP-hand"}


def _actions(tokens):
    return [dict(name=token, amount=F(0), raise_to=F(0), history_key=token,
                 probability=F(0)) for token in tokens]


def _specifications():
    specs = [("oop", (), ("o-check", "o-bet")),
             ("ip", ("o-check",), ("i-check", "i-bet"))]
    for ip_turn in ("i-check", "i-bet"):
        for river in ("2c", "3c"):
            history = ("o-check", ip_turn, "river@" + river)
            specs.append(("ip", history, ("ip-river-check", "ip-river-bet")))
            for ip_river in ("ip-river-check", "ip-river-bet"):
                specs.append(("oop", history + (ip_river,),
                              ("oop-river-fold", "oop-river-call")))
    return specs


SPECS = _specifications()
KEYS = tuple((player, HAND[player], history) for player, history, _ in SPECS)
TOKENS = {key: tokens for (player, history, tokens), key in zip(SPECS, KEYS)}
MARGINAL = {key: F(index + 1, index + 7) for index, key in enumerate(KEYS)}


def _sweep_policy(iteration):
    policy = {}
    for index, key in enumerate(KEYS):
        # Every row varies over sweeps, including opponent decisions.
        first = F(((index + 2) * (iteration + 1)) % 7 + 1, 8)
        policy[key] = (first, 1 - first)
    return policy


def _reach(policy, key, acting_player):
    player, hand, history = key
    reach = F(1)
    for index, token in enumerate(history):
        ancestor = (acting_player, HAND[acting_player], history[:index])
        if ancestor not in policy:
            continue
        choices = TOKENS[ancestor]
        matches = [action_index for action_index, action in enumerate(choices)
                   if action == token]
        if len(matches) == 1:
            reach *= policy[ancestor][matches[0]]
    return reach


def _chance_reach(key):
    for token in key[2]:
        if token.startswith("river@"):
            return CHANCE_MASS[token[6:]]
    return F(1)


def _average(first_iteration, last_iteration, *, include_opponent_reach=False,
             include_chance_reach=False):
    sweeps = {iteration: _sweep_policy(iteration)
              for iteration in range(1, T + 1)}
    rows = []
    for key in KEYS:
        player, hand, history = key
        tokens = TOKENS[key]
        totals = [F(0) for _ in tokens]
        denominator = F(0)
        for iteration in range(first_iteration, last_iteration + 1):
            policy = sweeps[iteration]
            weight = F(iteration) * MARGINAL[key] * _reach(policy, key, player)
            if include_opponent_reach:
                opponent = "ip" if player == "oop" else "oop"
                weight *= _reach(policy, key, opponent)
            if include_chance_reach:
                weight *= _chance_reach(key)
            denominator += weight
            for action_index, probability in enumerate(policy[key]):
                totals[action_index] += weight * probability
        probabilities = tuple(total / denominator for total in totals)
        river = next((token[6:] for token in history
                      if token.startswith("river@")), None)
        board = ["Js", "8d", "4c", "2h"] + ([river] if river else [])
        row = dict(player=player, hand=hand,
                   street="river" if river else "turn",
                   board=board, history=list(history),
                   actions=_actions(tokens))
        for action, probability in zip(row["actions"], probabilities):
            action["probability"] = probability
        rows.append(row)
    return rows


def _by_key(rows):
    return {(row["player"], row["hand"], tuple(row["history"])): tuple(
        action["probability"] for action in row["actions"]) for row in rows}


class TurnTailRealizationTests(unittest.TestCase):
    def test_exact_turn_chance_river_tail_matches_direct_original_weight_sum(self):
        prefix = _average(1, D)
        full = _average(1, T)
        observed_rows, ledger = reconstruct_tail(prefix, full, D, T)
        observed = _by_key(observed_rows)
        expected = _by_key(_average(D + 1, T))
        self.assertEqual(observed, expected)
        self.assertEqual(ledger["raw_negative_child_count"], 0)
        self.assertEqual(ledger["maximum_reconstruction_discrepancy"], F(0))
        self.assertEqual(len(observed), len(KEYS))
        self.assertTrue(any("river@2c" in key[2] for key in observed))
        self.assertTrue(any("river@3c" in key[2] for key in observed))
        self.assertTrue(any(key[0] == "oop" and len(key[2]) == 4 for key in observed))
        self.assertTrue(any(key[0] == "ip" and len(key[2]) == 3 for key in observed))
        self.assertEqual(len(set(MARGINAL.values())), len(KEYS))

    def test_opponent_reach_weighting_breaks_rows_but_fixed_chance_cancels_locally(self):
        correct = _by_key(_average(1, T))
        incorrectly_weighted = _by_key(_average(1, T, include_opponent_reach=True))
        target = ("ip", HAND["ip"], ("o-check",))
        self.assertNotEqual(correct[target], incorrectly_weighted[target])

        # A fixed public river chance mass is constant within that information
        # set and therefore cancels from its normalized behavioral row. It
        # would still be the wrong own-realization flow scale to carry forward.
        river_row = next(key for key in KEYS
                         if key[0] == "ip" and "river@3c" in key[2])
        chance_weighted = _by_key(_average(1, T, include_chance_reach=True))
        self.assertEqual(correct[river_row], chance_weighted[river_row])
        tail_sweeps = range(D + 1, T + 1)
        own_flow = sum((F(t) * MARGINAL[river_row] *
                        _reach(_sweep_policy(t), river_row, "ip") for t in tail_sweeps), F(0))
        chance_scaled_flow = own_flow * CHANCE_MASS["3c"]
        self.assertNotEqual(own_flow, chance_scaled_flow)


if __name__ == "__main__":
    unittest.main()
