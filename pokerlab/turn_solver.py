"""Exact finite heads-up turn-to-river games with physical card removal.

Future cards are latent chance outcomes, never part of a turn information set.
Optional selected runouts condition the entire joint physical deal distribution.
This additive library API leaves the existing river and coaching APIs unchanged.
"""
from dataclasses import dataclass

from .cards import DECK, cards, expand_range, rank_hand
from .river_config import RiverConfig
from .river_tree import _Node, _Terminal, _build_tree, _terminal_value
from .cfr import train, evaluate, best_response


@dataclass
class _Chance:
    history: tuple
    branches: dict


def _enumerate_worlds(board, oop_range, ip_range, runouts=None, iterations=10):
    """Return private hands, normalized (i,j,mass,sign,river) worlds and cards.

    Each physical pair has 44 equiprobable rivers before conditioning. A subset
    filters these physical worlds and normalizes once, including private pairs.
    """
    board = cards(board, 4)
    if runouts is None:
        selected = tuple(card for card in DECK if card not in board)
    else:
        selected = cards(runouts)
        if not selected or set(selected).intersection(board):
            raise ValueError("Runouts must be nonempty unique cards outside the turn board.")
        selected = tuple(card for card in DECK if card in selected)
    ranges = (expand_range(oop_range, board), expand_range(ip_range, board))
    hands = tuple(list(value) for value in ranges)
    if len(hands[0]) * len(hands[1]) * iterations > 3_000_000:
        raise ValueError("Exact turn solver allows 3 million candidate hand-pair iterations.")
    worlds, pair_count, ranks = [], 0, {}
    for i, h0 in enumerate(hands[0]):
        for j, h1 in enumerate(hands[1]):
            if set(h0).intersection(h1):
                continue
            available = [card for card in selected if card not in h0 and card not in h1]
            if not available:
                continue
            pair_count += 1
            mass = ranges[0][h0] * ranges[1][h1] / 44
            for river in available:
                for player, index, hand in ((0, i, h0), (1, j, h1)):
                    key = (player, index, river)
                    if key not in ranks:
                        ranks[key] = rank_hand(hand + board + (river,))
                a, b = ranks[(0, i, river)], ranks[(1, j, river)]
                worlds.append((i, j, mass, (a > b) - (a < b), river))
                if len(worlds) * iterations > 3_000_000:
                    raise ValueError("Exact turn solver allows 3 million chance-world iterations.")
    total = sum(world[2] for world in worlds)
    if total <= 0:
        raise ValueError("Ranges and runouts contain no compatible physical deals.")
    return hands, [(i, j, w / total, sign, river)
                   for i, j, w, sign, river in worlds], selected, pair_count


def _chance_child(node, world):
    return node.branches[world[4]] if isinstance(node, _Chance) else None


def _chance_partitions(node, worlds):
    if not isinstance(node, _Chance):
        return None
    groups = {}
    for world in worlds:
        groups.setdefault(world[4], []).append(world)
    return [(node.branches[river], group) for river, group in groups.items()]


def _node_key(node, world):
    return node.player, world[node.player], node.history


def _tree(config, river_config, runouts):
    nodes, chance_nodes = {}, []
    river_node_counts = []

    def settled(history, contributions):
        # Return unmatched chips before the next street. Both street builders
        # keep cumulative commitments; original pot is counted exactly once.
        matched = min(contributions)
        carried = (matched, matched)
        branches = {}
        for river in runouts:
            river_history = history + (f"river@{river}",)
            if any(matched >= stack - 1e-9 for stack in config.stacks):
                branches[river] = _Terminal("showdown", carried)
            else:
                root, count = _build_tree(river_config, starting_history=river_history,
                                         starting_contributions=carried)
                branches[river] = root
                river_node_counts.append(count)
                if sum(river_node_counts) > 10_000:
                    raise ValueError("Turn-to-river tree exceeds 10,000 public decision nodes.")
        chance = _Chance(history, branches)
        chance_nodes.append(chance)
        return chance

    root, turn_nodes = _build_tree(config, showdown_factory=settled)

    def collect(node):
        if isinstance(node, _Chance):
            for child in node.branches.values():
                collect(child)
        elif isinstance(node, _Node):
            nodes[(node.player, node.history)] = node
            for child in node.children:
                collect(child)

    collect(root)
    if len(nodes) > 10_000:
        raise ValueError("Turn-to-river tree exceeds 10,000 public decision nodes.")

    def visited_count(node):
        if isinstance(node, _Chance):
            return max(visited_count(child) for child in node.branches.values())
        if isinstance(node, _Terminal):
            return 0
        return 1 + sum(visited_count(child) for child in node.children)

    return root, nodes, len(chance_nodes), visited_count(root)


def solve_turn_river(board, oop_range, ip_range, config=None, *, river_config=None,
                     runouts=None, iterations=1000, algorithm="vanilla"):
    """Solve a configured two-street game with exact public chance and responses.

    Config pot is the starting turn pot; stacks cap total additional commitments
    across both streets. River config may change sizing, never pot or stack caps.
    Selected runouts define a conditional study game, including altered private
    deal priors, rather than approximating an unconditional full-deck solution.
    """
    board = cards(board, 4)
    if algorithm not in ("vanilla", "dcfr"):
        raise ValueError("Solver algorithm must be vanilla or dcfr.")
    if type(iterations) is not int or not 10 <= iterations <= 10_000:
        raise ValueError("Use 10–10,000 solver iterations.")
    config = RiverConfig() if config is None else config
    if not isinstance(config, RiverConfig):
        config = RiverConfig.from_dict(config)
    river_config = config if river_config is None else river_config
    if not isinstance(river_config, RiverConfig):
        river_config = RiverConfig.from_dict(river_config)
    if river_config.pot != config.pot or river_config.stacks != config.stacks:
        raise ValueError("River config must preserve the starting turn pot and total stack caps.")
    hands, worlds, selected, pair_count = _enumerate_worlds(
        board, oop_range, ip_range, runouts, iterations)
    # Cards with no compatible world cannot be reached and add no public tree.
    reachable = tuple(card for card in selected if any(w[4] == card for w in worlds))
    root, nodes, chance_nodes, visited_nodes = _tree(config, river_config, reachable)
    if len(worlds) * visited_nodes * iterations > 30_000_000:
        raise ValueError("Turn solver workload exceeds 30 million world-node iterations.")
    active_hands = ({w[0] for w in worlds}, {w[1] for w in worlds})
    river_hands = {(player, river): {w[player] for w in worlds if w[4] == river}
                   for player in (0, 1) for river in reachable}
    infos, metadata = {}, {}
    for (player, history), node in nodes.items():
        reveal = next((token[6:] for token in history if token.startswith("river@")), None)
        allowed = active_hands[player] if reveal is None else river_hands[(player, reveal)]
        for index in sorted(allowed):
            key = (player, index, history)
            infos[key] = len(node.actions)
            metadata[key] = (node, reveal)
    payoff = lambda node, world: _terminal_value(node, world[3], config.pot)
    averages = train(root, worlds, infos, iterations, algorithm, payoff, _node_key,
                     _chance_child)
    value = evaluate(root, worlds, averages, payoff, _node_key, _chance_child)
    br0 = best_response(0, root, worlds, averages, payoff, _node_key, _chance_partitions)
    br1 = best_response(1, root, worlds, averages, payoff, _node_key, _chance_partitions)
    rows = []
    for key in sorted(infos):
        player, index, history = key
        node, reveal = metadata[key]
        rows.append({
            "player": "oop" if player == 0 else "ip", "hand": "".join(hands[player][index]),
            "street": "turn" if reveal is None else "river",
            "board": list(board + (() if reveal is None else (reveal,))),
            "history": list(history),
            "actions": [{"name": a.name, "amount": a.amount, "raise_to": a.raise_to,
                         "history_key": a.token, "probability": p}
                        for a, p in zip(node.actions, averages[key])],
        })
    gap = max(0., br0 + br1)
    return {
        "method": "full-traversal CFR", "algorithm": algorithm,
        "solver_version": "configured-turn-river-v1", "strategy_schema": "postflop-strategy-v1",
        "backend": "exact-public-chance-tree", "board": list(board),
        "config": config.to_dict(), "river_config": river_config.to_dict(),
        "runouts": list(selected), "reachable_runouts": list(reachable),
        "runout_mode": "full-deck" if runouts is None else "conditioned-subset",
        "chance_note": "Joint private-pair/river physical weights normalized once; 44 rivers per pair before subset conditioning.",
        "iterations": iterations, "deals": pair_count, "worlds": len(worlds),
        "info_sets": len(infos), "public_nodes": len(nodes), "chance_nodes": chance_nodes,
        "world_traversal_nodes": visited_nodes,
        "tree_actions": sum(len(n.actions) for n in nodes.values()),
        "pot": config.pot, "effective_stack": config.to_dict()["effective_stack"],
        "value_oop": value, "value_ip": -value,
        "oop_best_response_value": br0, "ip_best_response_value": br1,
        "oop_best_response_gain": max(0., br0 - value),
        "ip_best_response_gain": max(0., br1 + value),
        "nash_conv": gap, "exploitability": gap / 2,
        "scope": "Approximate equilibrium of the configured heads-up turn-to-river action abstraction; no flop, preflop or rake.",
        "strategy": rows,
    }
