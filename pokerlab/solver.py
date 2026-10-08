"""Full-traversal CFR for configurable, heads-up river action abstractions.

The solver's equilibrium claim is limited to the exact configured river tree.
It enumerates compatible private-hand pairs and evaluates best responses at
information-set level, without exposing either player's hidden cards.
"""
from .analysis import number
from .cards import cards, expand_range, rank_hand
from .cfr import best_response as _cfr_best_response
from .cfr import evaluate as _cfr_evaluate
from .cfr import strategy, train as _cfr_train
from .river_config import RiverConfig
from .river_tree import (
    IP,
    OOP,
    _EPSILON,
    _Action,
    _Node,
    _Terminal,
    _add_action,
    _amount_label,
    _build_tree,
    _clean,
    _opening_actions,
    _raise_actions,
    _terminal_value,
)
from .restricted_solver import solve as _solve_restricted


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


def _node_key(node, hand_indexes):
    return node.player, hand_indexes[node.player], node.history


def _collect_nodes(root):
    nodes = {}

    def visit(node):
        if hasattr(node, "actions"):
            nodes[(node.player, tuple(node.history))] = node
        for child in getattr(node, "children", ()):
            visit(child)

    visit(root)
    return nodes


def _deal_value(root, sign, pot, averages, deal, hand_indexes):
    def key(node, world):
        return _node_key(node, (world[0], world[1]))

    def terminal(node, world):
        return _terminal_value(node, world[3], pot)

    world = tuple(deal[:2]) + (1.0, sign) + tuple(deal[4:])
    return _cfr_evaluate(root, [world], averages, terminal, key)


def _best_response_value(player, root, hands, deals, averages, hand_indexes, pot):
    """Compatibility wrapper over the shared chance-aware CFR kernel."""
    def key(node, world):
        return _node_key(node, (world[0], world[1]))

    def terminal(node, world):
        return _terminal_value(node, world[3], pot)

    return _cfr_best_response(player, root, deals, averages, terminal, key)


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


def _solve_configured(board, oop_range, ip_range, pot=100, bet=50, iterations=1000, lock=None,
          config=None, effective_stack=None, bet_sizes=None, raise_sizes=None,
          max_raises=0, include_all_in=True, *, algorithm="vanilla"):
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
    def node_key(node, world):
        return _node_key(node, (world[0], world[1]))

    def terminal_value(node, world):
        return _terminal_value(node, world[3], config.pot)

    cfr_locks = {}
    for (player, history), locked_hands in lock_map.items():
        for hand_index, frequency in locked_hands.items():
            cfr_locks[(player, hand_index, history)] = [1.0 - frequency, frequency]
    averages = _cfr_train(root, deals, infos, iterations, algorithm,
                          terminal_value, node_key, locks=cfr_locks)

    value = _cfr_evaluate(root, deals, averages, terminal_value, node_key)
    br0 = _cfr_best_response(OOP, root, deals, averages, terminal_value, node_key)
    br1 = _cfr_best_response(IP, root, deals, averages, terminal_value, node_key)
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
        "cfr_variant": ("DCFR(1.5,0,2), simultaneous regret-matching updates, reach-weighted quadratic strategy averaging"
                        if algorithm == "dcfr" else
                        "vanilla CFR, simultaneous regret-matching updates, reach-weighted uniform strategy averaging"),
        "algorithm": algorithm,
        "solver_version": "configured-river-v1",
        "strategy_schema": "river-strategy-v1",
        "backend": "exact-public-tree",
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


def _decorate_restricted(result):
    """Expose the same versioned strategy schema for the optimized binary tree.

    The historical entry point has an affordable fixed bet and no stack cap;
    config is None instead of inventing a cap or a full-NLHE configuration.
    """
    bet = result["bet"]
    token = f"bet@{_amount_label(bet)}"
    nodes = (("oop", (), "bet", ("check", "bet")),
             ("oop", ("check", token), "call_after_check", ("fold", "call")),
             ("ip", ("check",), "bet_after_check", ("check", "bet")),
             ("ip", (token,), "call", ("fold", "call")))
    rows = []
    for player, history, probability_key, names in nodes:
        for hand in result[player]:
            p = hand[probability_key]
            actions = []
            for name, probability in zip(names, (1-p, p)):
                amount = bet if name in {"bet", "call"} else 0.
                actions.append({"name": name, "amount": amount, "raise_to": amount,
                                "history_key": token if name == "bet" else name,
                                "probability": probability})
            rows.append({"player": player, "hand": hand["hand"],
                         "history": list(history), "actions": actions})
    result.update(config=None, effective_stack=None, strategy=rows,
                  strategy_schema="river-strategy-v1", backend="optimized-binary-tree",
                  public_nodes=4, tree_actions=8)
    return result


def solve(board, oop_range, ip_range, pot=100, bet=50, iterations=1000, lock=None,
          config=None, effective_stack=None, bet_sizes=None, raise_sizes=None,
          max_raises=0, include_all_in=True, *, algorithm="vanilla"):
    """Solve the supplied river abstraction with vanilla CFR or optional DCFR.

    Existing fixed-bet calls retain the validated optimized kernel. Explicit
    stack/sizing configurations use the finite reusable public action tree.
    Both expose river-strategy-v1 and exact information-set best responses.
    """
    if algorithm not in ("vanilla", "dcfr"):
        raise ValueError("Solver algorithm must be vanilla or dcfr.")
    if config is None and all(value is None for value in
                             (effective_stack, bet_sizes, raise_sizes)) and max_raises == 0:
        return _decorate_restricted(_solve_restricted(
            board, oop_range, ip_range, pot, bet, iterations, lock, algorithm=algorithm))
    return _solve_configured(board, oop_range, ip_range, pot, bet, iterations, lock,
                             config, effective_stack, bet_sizes, raise_sizes,
                             max_raises, include_all_in, algorithm=algorithm)
