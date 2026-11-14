"""Candidate exact terminal-partition response for the fixed preflop model.

The independent literal response scan remains the authority. This alternative
first sums hidden-opponent contributions per own hand and terminal history,
then enumerates the same complete legal pure own-hand policies. No maximizing
over hidden opponent hands occurs. Call only with a validated exact policy and
authenticated physical game; this helper does not authenticate source counts.
"""
from fractions import Fraction
from itertools import product

from scripts.preflop_mixed_pure_response import INFO_MENUS, TERMINALS

MAX_PAIRS = 84
MAX_OWN_HANDS = (22, 6)
MAX_EXACT_BITS = 65_536


def _bounded(value):
    if type(value) is not Fraction or max(abs(value.numerator).bit_length(),
                                         value.denominator.bit_length()) > MAX_EXACT_BITS:
        raise ValueError("Partitioned response exceeds its exact arithmetic bound")
    return value


def best_response(policy, game, player, *, statistics=None):
    """Return value, exact own-hand choices and census for validated input.

    This is an optional candidate calculation, never the independent checker.
    The fixed fourteen terminal histories include all off-path decisions. Ties
    use the reference's first complete pure policy in literal menu order.
    """
    if type(player) is not int or player not in (0, 1):
        raise ValueError("Responding player must be an exact 0 or 1")
    if type(game) is not dict or not all(k in game for k in ("sb_hands", "bb_hands", "pairs")):
        raise ValueError("Requires a validated physical game")
    own_hands = game["sb_hands"] if player == 0 else game["bb_hands"]
    pairs = game["pairs"]
    if not 1 <= len(own_hands) <= MAX_OWN_HANDS[player] or len(set(own_hands)) != len(own_hands):
        raise ValueError("Partitioned response private-hand census exceeds its cap")
    if not 1 <= len(pairs) <= MAX_PAIRS:
        raise ValueError("Partitioned response pair census exceeds its cap")
    if statistics is not None and (type(statistics) is not dict or statistics):
        raise ValueError("Use an empty statistics dictionary")
    side = "sb_hand" if player == 0 else "bb_hand"
    opponent_side = "bb_hand" if player == 0 else "sb_hand"
    if any(pair[side] not in own_hands for pair in pairs):
        raise ValueError("Physical pair references an unknown responding hand")
    infos = tuple((history, actions) for (owner, history), actions in INFO_MENUS.items()
                  if owner == player)
    # Own pure choices influence reach only through public action matching.
    requirements = []
    for path, _constant, _multiplier in TERMINALS:
        history = []
        own = []
        for index, action in enumerate(path):
            if index % 2 == player:
                own.append((tuple(history), action))
            history.append(action)
        requirements.append(tuple(own))
    counters = {"pair_terminal_contributions": 0, "opponent_probability_products": 0,
                "pure_response_policies_enumerated": 0, "pure_terminal_checks": 0}
    total, response_rows = Fraction(), []
    for hand in own_hands:
        coefficients = [Fraction() for _ in TERMINALS]
        for pair in pairs:
            if pair[side] != hand:
                continue
            prior = _bounded(pair["prior"])
            mean = _bounded(pair["showdown_mean"])
            if prior <= 0 or not -1 <= mean <= 1:
                raise ValueError("Invalid exact physical pair prior or signed mean")
            for index, (path, constant, multiplier) in enumerate(TERMINALS):
                reach, history = Fraction(1), []
                for turn, action in enumerate(path):
                    if turn % 2 != player:
                        probability = _bounded(policy[(1 - player, pair[opponent_side], tuple(history))][action])
                        if not 0 <= probability <= 1:
                            raise ValueError("Invalid opponent action probability")
                        reach = _bounded(reach * probability)
                        counters["opponent_probability_products"] += 1
                    history.append(action)
                signed = constant + multiplier * mean
                if player == 1:
                    signed = -signed
                coefficients[index] = _bounded(coefficients[index] + _bounded(prior * reach * signed))
                counters["pair_terminal_contributions"] += 1
        best_value, best_choices, enumerated = None, None, 0
        for selected in product(*(actions for _history, actions in infos)):
            choices = {history: action for (history, _actions), action in zip(infos, selected)}
            value = Fraction()
            for coefficient, required in zip(coefficients, requirements):
                counters["pure_terminal_checks"] += 1
                if all(choices[history] == action for history, action in required):
                    value = _bounded(value + coefficient)
            enumerated += 1
            if best_value is None or value > best_value:
                best_value, best_choices = value, choices
        expected = 48 if player == 0 else 36
        if enumerated != expected:
            raise AssertionError("Literal complete-policy census changed")
        total = _bounded(total + best_value)
        counters["pure_response_policies_enumerated"] += enumerated
        response_rows.append({"hand": hand, "pure_policies_enumerated": enumerated,
                              "best_response_own_utility_fraction": str(best_value),
                              "best_actions": [{"history": list(history), "action": best_choices[history]}
                                               for history, _actions in infos]})
    if statistics is not None:
        statistics.update(counters)
    return total, response_rows, counters["pure_response_policies_enumerated"]
