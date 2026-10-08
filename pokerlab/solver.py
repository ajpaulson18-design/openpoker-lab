"""Full-traversal CFR for configurable, heads-up river action abstractions.

The solver's equilibrium claim is limited to the exact configured river tree.
It enumerates compatible private-hand pairs and evaluates best responses at
information-set level, without exposing either player's hidden cards.
"""
from dataclasses import dataclass
import math

from .analysis import number
from .cards import cards, expand_range, rank_hand
from .river_config import RiverConfig


OOP, IP = 0, 1
_EPSILON = 1e-9


def _clean(value):
    value = round(float(value), 9)
    return 0.0 if value == 0 else value


def _amount_label(value):
    return format(_clean(value), ".9f").rstrip("0").rstrip(".")


@dataclass(frozen=True)
class _Action:
    name: str
    amount: float = 0.0
    raise_to: float = 0.0
    full_raise: bool = False

    @property
    def token(self):
        if self.name in {"bet", "raise", "all_in"}:
            return f"{self.name}@{_amount_label(self.raise_to)}"
        return self.name


@dataclass
class _Node:
    history: tuple
    player: int
    actions: tuple
    children: tuple


@dataclass(frozen=True)
class _Terminal:
    kind: str
    contributions: tuple
    winner: int | None = None


def strategy(regret):
    positive = [max(0.0, value) for value in regret]
    mass = sum(positive)
    return [value / mass for value in positive] if mass else [1.0 / len(regret)] * len(regret)


def terminal_utilities(pot, bet, sign):
    """Compatibility helper for the prior one-bet/no-raise solver."""
    half = pot / 2
    return {"check_check": sign * half, "bet_fold": half, "bet_call": sign * (half + bet),
            "check_bet_fold": -half, "check_bet_call": sign * (half + bet)}


def _normalized_config(pot, bet, config, effective_stack, bet_sizes, raise_sizes,
                      max_raises, include_all_in):
    if config is not None:
        if any(value is not None for value in (effective_stack, bet_sizes, raise_sizes)) or \
                max_raises != 0 or include_all_in is not True:
            raise ValueError("Pass either config or individual action-tree options, not both.")
        if isinstance(config, RiverConfig):
            return config
        return RiverConfig.from_dict(config)

    uses_config_options = (effective_stack is not None or bet_sizes is not None or
                           raise_sizes is not None or max_raises != 0)
    pot = number(pot, "Pot", .01)
    if bet_sizes is None:
        bet = number(bet, "Bet", .000000001)
        bet_sizes = (bet / pot,)
    # The historical fixed-size entry point retains its exact two-action tree.
    all_in_option = include_all_in if uses_config_options else False
    return RiverConfig(
        pot=pot,
        effective_stack=effective_stack if effective_stack is not None else 1_000_000,
        bet_sizes=bet_sizes,
        raise_sizes=raise_sizes or (),
        max_raises=max_raises,
        include_all_in=all_in_option,
    )


def _add_action(actions, name, target, committed, stack, full_raise=False):
    target = _clean(min(stack, max(committed, target)))
    if target <= committed + _EPSILON:
        return
    if target >= stack - _EPSILON:
        name = "all_in"
    if any(abs(existing.raise_to - target) <= _EPSILON for existing in actions):
        return
    actions.append(_Action(name, _clean(target - committed), target, full_raise))


def _opening_actions(config, committed, total_pot, player):
    stack = config.stacks[player]
    actions = []
    for fraction in config.bet_sizes:
        target = committed + fraction * total_pot
        _add_action(actions, "bet", target, committed, stack)
    if config.include_all_in:
        _add_action(actions, "all_in", stack, committed, stack)
    return tuple(sorted(actions, key=lambda action: action.raise_to))


def _raise_actions(config, contributions, player, previous_full_raise, raises_made):
    committed = contributions[player]
    opponent = contributions[1 - player]
    call_amount = opponent - committed
    call_target = opponent
    max_target = config.stacks[player]
    minimum_target = opponent + previous_full_raise
    pot_after_call = config.pot + sum(contributions) + call_amount
    actions = []
    if max_target <= call_target + _EPSILON:
        return ()
    for fraction in config.raise_sizes:
        requested_target = call_target + fraction * pot_after_call
        target = requested_target
        if target < minimum_target:
            target = minimum_target
        if target > max_target:
            target = max_target
        increment = target - call_target
        is_full = increment + _EPSILON >= previous_full_raise
        if is_full:
            _add_action(actions, "raise", target, committed, max_target, True)
        elif requested_target + _EPSILON >= max_target or minimum_target > max_target:
            _add_action(actions, "all_in", max_target, committed, max_target, False)
    if config.include_all_in and max_target > call_target + _EPSILON:
        all_in_increment = max_target - call_target
        _add_action(actions, "all_in", max_target, committed, max_target,
                    all_in_increment + _EPSILON >= previous_full_raise)
    return tuple(sorted(actions, key=lambda action: action.raise_to))


def _build_tree(config):
    """Build a finite public tree. Raise depth counts every raise action."""
    node_count = 0

    def build(history, player, contributions, previous_full_raise, raises_made,
              raise_reopened, checks):
        nonlocal node_count
        if contributions[player] >= config.stacks[player] - _EPSILON:
            return _Terminal("showdown", contributions)
        node_count += 1
        if node_count > 10_000:
            raise ValueError("Configured action tree exceeds 10,000 public nodes.")
        opponent = 1 - player
        committed, other = contributions[player], contributions[opponent]
        if abs(committed - other) <= _EPSILON:
            check = _Action("check")
            if checks == 1:
                check_child = _Terminal("showdown", contributions)
            else:
                check_child = build(history + (check.token,), opponent, contributions,
                                    previous_full_raise, raises_made, raise_reopened, checks + 1)
            actions = [check]
            children = [check_child]
            for action in _opening_actions(config, committed,
                                           config.pot + sum(contributions), player):
                next_contributions = list(contributions)
                next_contributions[player] = action.raise_to
                actions.append(action)
                children.append(build(history + (action.token,), opponent,
                                      tuple(next_contributions), action.amount, 0, True, 0))
        else:
            call_amount = other - committed
            actual_call = min(call_amount, config.stacks[player] - committed)
            call_contributions = list(contributions)
            call_contributions[player] = committed + actual_call
            actions = [_Action("fold"), _Action("call", _clean(actual_call),
                                               call_contributions[player])]
            children = [_Terminal("fold", contributions, opponent),
                        _Terminal("showdown", tuple(call_contributions))]
            if raise_reopened and raises_made < config.max_raises and \
                    other < config.stacks[opponent] - _EPSILON:
                for action in _raise_actions(config, contributions, player,
                                             previous_full_raise, raises_made):
                    next_contributions = list(contributions)
                    next_contributions[player] = action.raise_to
                    actions.append(action)
                    increment = action.raise_to - other
                    full_raise = increment + _EPSILON >= previous_full_raise
                    next_full_raise = increment if full_raise else previous_full_raise
                    children.append(build(history + (action.token,), opponent,
                                          tuple(next_contributions), next_full_raise,
                                          raises_made + 1, full_raise, 0))
        return _Node(history, player, tuple(actions), tuple(children))

    return build((), OOP, (0.0, 0.0), 0.0, 0, True, 0), node_count


def _terminal_value(terminal, sign, pot):
    matched = min(terminal.contributions)
    if terminal.kind == "fold":
        winner_sign = 1 if terminal.winner == OOP else -1
        return winner_sign * (pot / 2 + matched)
    return sign * (pot / 2 + matched)


def _node_key(node, hand_indexes):
    return node.player, hand_indexes[node.player], node.history


def _collect_nodes(root):
    nodes = {}

    def visit(node):
        if not isinstance(node, _Node):
            return
        nodes[(node.player, node.history)] = node
        for child in node.children:
            visit(child)

    visit(root)
    return nodes


def _deal_value(root, sign, pot, averages, deal, hand_indexes):
    i, j, _, _ = deal

    def visit(node):
        if isinstance(node, _Terminal):
            return _terminal_value(node, sign, pot)
        probs = averages[_node_key(node, (i, j))]
        return sum(probability * visit(child)
                   for probability, child in zip(probs, node.children))

    return visit(root)


def _best_response_value(player, root, hands, deals, averages, hand_indexes, pot):
    """Best response with opponent hands aggregated before each private-hand max."""
    own_index = player
    result = 0.0
    compatible_by_own = [[] for _ in hands[player]]
    for deal in deals:
        i, j, weight, sign = deal
        own_hand = i if own_index == OOP else j
        compatible_by_own[own_hand].append((i, j, weight, sign))

    for own_hand, own_deals in enumerate(compatible_by_own):
        if not own_deals:
            continue

        def visit(node, weighted_deals):
            if isinstance(node, _Terminal):
                return sum(weight * ((1 if player == OOP else -1) *
                                     _terminal_value(node, sign, pot))
                           for _, _, weight, sign in weighted_deals)
            if node.player == player:
                return max(visit(child, weighted_deals) for child in node.children)
            value = 0.0
            for action_index, child in enumerate(node.children):
                branched = []
                for i, j, weight, sign in weighted_deals:
                    probs = averages[_node_key(node, (i, j))]
                    next_weight = weight * probs[action_index]
                    if next_weight:
                        branched.append((i, j, next_weight, sign))
                if branched:
                    value += visit(child, branched)
            return value

        result += visit(root, own_deals)
    return result


def _lock_frequencies(lock, hands, nodes, config):
    lock = lock or {}
    if set(lock) - {"ip_bet", "ip_call"}:
        raise ValueError("Available node locks are ip_bet and ip_call.")
    if lock and (len(config.bet_sizes) != 1 or config.max_raises != 0):
        raise ValueError("Legacy IP node locks require one bet size and no raises.")
    hand_indexes = {"".join(hand): index for index, hand in enumerate(hands[IP])}
    locks, report = {}, {}
    targets = {"ip_bet": ("check",), "ip_call": None}
    for public_name, value in lock.items():
        if isinstance(value, dict):
            unknown = set(value) - set(hand_indexes)
            if unknown:
                raise ValueError(f"Node lock contains hands outside the IP range: {sorted(unknown)}")
            values = {hand_indexes[hand]: number(frequency, public_name, 0, 1)
                      for hand, frequency in value.items()}
        else:
            frequency = number(value, public_name, 0, 1)
            values = {index: frequency for index in range(len(hands[IP]))}
        if public_name == "ip_bet":
            node_history = targets[public_name]
        else:
            matching = [history for (player, history), node in nodes.items()
                        if player == IP and node.actions and node.actions[0].name == "fold"
                        and len(history) == 1 and history[0].startswith(("bet@", "all_in@"))]
            if len(matching) != 1:
                raise ValueError("ip_call lock requires exactly one OOP opening-bet size.")
            node_history = matching[0]
        node = nodes.get((IP, node_history))
        if node is None or len(node.actions) != 2:
            raise ValueError(f"{public_name} lock does not match a two-action IP node.")
        locks[(IP, node_history)] = values
        report[public_name] = {hands[IP][i] and "".join(hands[IP][i]): values[i]
                               for i in sorted(values)} if isinstance(value, dict) else next(iter(values.values()))
    return locks, report


def _legacy_rows(root, averages, hands):
    nodes = _collect_nodes(root)

    def frequencies(player, hand_index, selector):
        matching = [(node, averages[(player, hand_index, history)])
                    for (owner, history), node in nodes.items() if owner == player and selector(history, node)]
        return matching

    oop_rows, ip_rows = [], []
    for index, hand in enumerate(hands[OOP]):
        root_strategies = frequencies(OOP, index, lambda history, node: not history)
        facing = frequencies(OOP, index, lambda history, node: len(history) == 2
                             and history[0] == "check"
                             and node.actions[0].name == "fold")
        row = {"hand": "".join(hand), "bet": 0.0, "call_after_check": 0.0}
        if root_strategies:
            node, probs = root_strategies[0]
            row["bet"] = sum(p for action, p in zip(node.actions, probs)
                             if action.name in {"bet", "all_in"})
        if facing:
            node, probs = facing[0]
            row["call_after_check"] = sum(p for action, p in zip(node.actions, probs)
                                           if action.name == "call")
        oop_rows.append(row)
    for index, hand in enumerate(hands[IP]):
        after_check = frequencies(IP, index, lambda history, node: history == ("check",))
        facing = frequencies(IP, index, lambda history, node: len(history) == 1
                             and node.actions[0].name == "fold")
        row = {"hand": "".join(hand), "bet_after_check": 0.0, "call": 0.0}
        if after_check:
            node, probs = after_check[0]
            row["bet_after_check"] = sum(p for action, p in zip(node.actions, probs)
                                         if action.name in {"bet", "all_in"})
        if facing:
            node, probs = facing[0]
            row["call"] = sum(p for action, p in zip(node.actions, probs)
                              if action.name == "call")
        ip_rows.append(row)
    return oop_rows, ip_rows


def solve(board, oop_range, ip_range, pot=100, bet=50, iterations=1000, lock=None,
          config=None, effective_stack=None, bet_sizes=None, raise_sizes=None,
          max_raises=0, include_all_in=True):
    """Solve an exact configured river abstraction by vanilla full-traversal CFR.

    Legacy ``pot``/``bet`` calls remain supported. New trees should pass a
    :class:`RiverConfig` or its ``to_dict()`` representation as ``config``.
    """
    board = cards(board, 5)
    config = _normalized_config(pot, bet, config, effective_stack, bet_sizes,
                                raise_sizes, max_raises, include_all_in)
    if type(iterations) is not int or not 10 <= iterations <= 10000:
        raise ValueError("Use 10–10,000 solver iterations.")
    r0, r1 = expand_range(oop_range, board), expand_range(ip_range, board)
    if len(r0) * len(r1) * iterations > 3_000_000:
        raise ValueError("This exact solver allows 3 million hand-pair iterations. Narrow ranges or reduce iterations.")
    hands = (list(r0), list(r1))
    ranks0 = [rank_hand(hand + board) for hand in hands[OOP]]
    ranks1 = [rank_hand(hand + board) for hand in hands[IP]]
    deals = [(i, j, r0[h0] * r1[h1],
              (ranks0[i] > ranks1[j]) - (ranks0[i] < ranks1[j]))
             for i, h0 in enumerate(hands[OOP]) for j, h1 in enumerate(hands[IP])
             if not set(h0).intersection(h1)]
    mass = sum(deal[2] for deal in deals)
    if not mass:
        raise ValueError("Ranges contain no compatible pair of hands.")
    deals = [(i, j, weight / mass, sign) for i, j, weight, sign in deals]
    root, public_nodes = _build_tree(config)
    if len(deals) * public_nodes * iterations > 30_000_000:
        raise ValueError("Configured solver workload exceeds 30 million deal-node iterations.")
    nodes = _collect_nodes(root)
    lock_map, lock_report = _lock_frequencies(lock, hands, nodes, config)
    infos = {}
    for (player, history), node in nodes.items():
        for hand_index in range(len(hands[player])):
            infos[(player, hand_index, history)] = len(node.actions)
    regrets = {key: [0.0] * count for key, count in infos.items()}
    sums = {key: [0.0] * count for key, count in infos.items()}

    for _ in range(iterations):
        current = {key: strategy(regret) for key, regret in regrets.items()}
        for (player, history), locked_hands in lock_map.items():
            node = nodes[(player, history)]
            for hand_index, frequency in locked_hands.items():
                key = (player, hand_index, history)
                current[key] = [1.0 - frequency, frequency]
        deltas = {key: [0.0] * count for key, count in infos.items()}

        for i, j, deal_weight, sign in deals:
            hand_indexes = (i, j)

            def traverse(node, reach0, reach1):
                if isinstance(node, _Terminal):
                    return _terminal_value(node, sign, config.pot)
                key = _node_key(node, hand_indexes)
                probs = current[key]
                action_values = []
                for action_index, child in enumerate(node.children):
                    action_values.append(traverse(
                        child,
                        reach0 * (probs[action_index] if node.player == OOP else 1.0),
                        reach1 * (probs[action_index] if node.player == IP else 1.0)))
                expected = sum(p * value for p, value in zip(probs, action_values))
                opponent_reach = reach1 if node.player == OOP else reach0
                own_reach = reach0 if node.player == OOP else reach1
                sign_for_player = 1 if node.player == OOP else -1
                for action_index, value in enumerate(action_values):
                    deltas[key][action_index] += deal_weight * opponent_reach * \
                        sign_for_player * (value - expected)
                    sums[key][action_index] += deal_weight * own_reach * probs[action_index]
                return expected

            traverse(root, 1.0, 1.0)
        for key, values in regrets.items():
            regrets[key] = [old + delta for old, delta in zip(values, deltas[key])]

    averages = {}
    for key, values in sums.items():
        total = sum(values)
        averages[key] = [value / total for value in values] if total else \
            [1.0 / len(values)] * len(values)
    # Enforce exact locked frequencies in the reported strategy.
    for (player, history), locked_hands in lock_map.items():
        for hand_index, frequency in locked_hands.items():
            averages[(player, hand_index, history)] = [1.0 - frequency, frequency]

    value = sum(weight * _deal_value(root, sign, config.pot, averages, deal,
                                     (deal[0], deal[1]))
                for deal in deals for _, _, weight, sign in (deal,))
    br0 = _best_response_value(OOP, root, hands, deals, averages, None, config.pot)
    br1 = _best_response_value(IP, root, hands, deals, averages, None, config.pot)
    gap = max(0.0, br0 + br1)
    oop_rows, ip_rows = _legacy_rows(root, averages, hands)
    opening_bets = []
    for player, history in ((OOP, ()), (IP, ("check",))):
        node = nodes.get((player, history))
        if node is None:
            opening_bets = []
            break
        opening_bets.extend(action.raise_to for action in node.actions
                            if action.name in {"bet", "all_in"})
    scalar_bet = opening_bets[0] if opening_bets and all(
        abs(amount - opening_bets[0]) <= _EPSILON for amount in opening_bets) else None
    strategy_rows = []
    for (player, history), node in sorted(nodes.items(), key=lambda item: (item[0][0], item[0][1])):
        for hand_index, hand in enumerate(hands[player]):
            probs = averages[(player, hand_index, history)]
            strategy_rows.append({
                "player": "oop" if player == OOP else "ip",
                "hand": "".join(hand),
                "history": list(history),
                "actions": [{"name": action.name, "amount": action.amount,
                             "raise_to": action.raise_to,
                             "history_key": action.token, "probability": probability}
                            for action, probability in zip(node.actions, probs)],
            })
    return {
        "method": "full-traversal CFR",
        "cfr_variant": "vanilla CFR, simultaneous regret-matching updates, reach-weighted uniform strategy averaging",
        "config": config.to_dict(),
        "info_sets": len(infos),
        "public_nodes": public_nodes,
        "tree_actions": sum(len(node.actions) for node in nodes.values()),
        "iterations": iterations,
        "deals": len(deals),
        "pot": config.pot,
        "effective_stack": config.to_dict()["effective_stack"],
        "bet": scalar_bet,
        "value_oop": value,
        "value_ip": -value,
        "oop_best_response_value": br0,
        "ip_best_response_value": br1,
        "nash_conv": gap,
        "exploitability": gap / 2,
        "oop_best_response_gain": max(0.0, br0 - value),
        "gap_note": "Unrestricted best-response gap; with node locks, this is not a convergence certificate for the locked game.",
        "lock": lock_report,
        "scope": "Approximate equilibrium of the configured heads-up river action abstraction; no earlier streets or rake.",
        "oop": oop_rows,
        "ip": ip_rows,
        "strategy": strategy_rows,
    }
