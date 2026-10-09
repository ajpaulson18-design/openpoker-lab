"""Exact batched CFR traversal over public nodes and private-hand vectors.

This specialized trainer consumes the postflop solver's weighted physical
worlds and fold/showdown terminals. It enumerates every supplied public chance
branch; it is not a chance-sampling implementation. The caller supplies the
public chance-node class to avoid coupling this module to a particular tree
builder. Arbitrary utility callbacks and fixed strategy locks are unsupported.
"""

from collections.abc import Mapping
import math

from .cfr import strategy
from .river_tree import _Terminal


MAX_PREFIX_EDGES = 250_000
_MAX_PRIVATE_HANDS = 52 * 51 // 2


def _aggregate_prefixes(worlds, hand_counts):
    """Aggregate joint deal mass by public prefix and private-hand pair.

    The cap is reserved before allocating either a new prefix row or its edge
    value, keeping scratch aggregation bounded even when the supplied world
    list has many distinct prefix/hand combinations.
    """
    edge_rows = {}
    edge_count = 0
    for world in worlds:
        oop_index, ip_index, mass, sign = world[:4]
        future = tuple(world[4:])
        pair = (oop_index, ip_index)
        for length in range(len(future) + 1):
            prefix = future[:length]
            row = edge_rows.get(prefix)
            edge = None if row is None else row.get(pair)
            if edge is None:
                if edge_count >= MAX_PREFIX_EDGES:
                    raise ValueError(
                        "Public CFR prefix/hand edges exceed 250,000."
                    )
                edge_count += 1
                if row is None:
                    row = {}
                    edge_rows[prefix] = row
                edge = [0.0, 0.0]
                row[pair] = edge
            edge[0] += mass
            edge[1] += mass * sign

    edges = {}
    marginals = {}
    for prefix, row in edge_rows.items():
        prefix_edges = []
        oop_mass = [0.0] * hand_counts[0]
        ip_mass = [0.0] * hand_counts[1]
        for (oop_index, ip_index), (mass, signed_mass) in row.items():
            prefix_edges.append((oop_index, ip_index, mass, signed_mass))
            oop_mass[oop_index] += mass
            ip_mass[ip_index] += mass
        edges[prefix] = tuple(prefix_edges)
        marginals[prefix] = (oop_mass, ip_mass)
    return edges, marginals


def _validate_inputs(worlds, infos, iterations, algorithm, pot, chance_type):
    if algorithm not in ("vanilla", "dcfr", "cfrplus"):
        raise ValueError("Algorithm must be vanilla, dcfr, or cfrplus.")
    if type(iterations) is not int or iterations < 1:
        raise ValueError("Iterations must be a positive integer.")
    if not isinstance(infos, Mapping):
        raise TypeError("infos must map information-set keys to action counts.")
    if not isinstance(chance_type, type):
        raise TypeError("chance_type must be a chance-node class.")
    try:
        pot = float(pot)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Pot must be a finite positive number.") from exc
    if not math.isfinite(pot) or pot <= 0:
        raise ValueError("Pot must be a finite positive number.")
    if isinstance(worlds, (str, bytes)) or not hasattr(worlds, "__len__"):
        raise TypeError("worlds must be a sized sequence of weighted deals.")
    if len(worlds) == 0:
        raise ValueError("At least one weighted physical world is required.")

    max_indices = [-1, -1]
    total_mass = 0.0
    for world in worlds:
        if not isinstance(world, (tuple, list)) or len(world) < 4:
            raise ValueError("Each world needs two hand indices, weight, and showdown sign.")
        for player in (0, 1):
            hand_index = world[player]
            if type(hand_index) is not int or not 0 <= hand_index < _MAX_PRIVATE_HANDS:
                raise ValueError("Private-hand indices must be within the 1,326 Hold'em combos.")
            max_indices[player] = max(max_indices[player], hand_index)
        try:
            mass = float(world[2])
            sign = float(world[3])
            hash(tuple(world[4:]))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("World weights, signs, and future-card prefixes must be valid.") from exc
        if (isinstance(world[2], bool) or not isinstance(world[2], (int, float)) or
                isinstance(world[3], bool) or not isinstance(world[3], (int, float))):
            raise ValueError("World weights and showdown signs must be real numbers.")
        if not math.isfinite(mass) or mass < 0:
            raise ValueError("World weights must be finite and nonnegative.")
        if not math.isfinite(sign) or sign not in (-1.0, 0.0, 1.0):
            raise ValueError("Showdown signs must be -1, 0, or 1.")
        total_mass += mass
        if not math.isfinite(total_mass):
            raise ValueError("Total world weight must be finite.")
    if total_mass <= 0:
        raise ValueError("Weighted worlds must have positive total mass.")

    for key, action_count in infos.items():
        if (not isinstance(key, tuple) or len(key) != 3 or
                type(key[0]) is not int or key[0] not in (0, 1) or
                type(key[1]) is not int or not 0 <= key[1] < _MAX_PRIVATE_HANDS or
                not isinstance(key[2], tuple)):
            raise ValueError("Information-set keys must be (player, hand_index, history) tuples.")
        if type(action_count) is not int or action_count < 1:
            raise ValueError("Information sets must have a positive integer action count.")
        max_indices[key[0]] = max(max_indices[key[0]], key[1])
    hand_counts = [index + 1 for index in max_indices]
    return pot, hand_counts


def _cfrplus_target_deltas(root, edges, infos, current, target_player,
                           hand_counts, half_pot, chance_type):
    """Return one player's regret deltas without constructing opponent values."""
    deltas = {key: [0.0] * count for key, count in infos.items()
              if key[0] == target_player}
    target_count = hand_counts[target_player]
    opponent = 1 - target_player

    def visit(node, prefix, opponent_reach):
        if isinstance(node, chance_type):
            value = [0.0] * target_count
            for card, child in node.branches.items():
                child_value = visit(child, prefix + (card,), opponent_reach)
                for index, result in enumerate(child_value):
                    value[index] += result
            return value

        if isinstance(node, _Terminal):
            value = [0.0] * target_count
            if node.kind == "fold":
                player0_sign = 1.0 if node.winner == 0 else -1.0
                payoff = player0_sign * (half_pot + min(node.contributions))
                for oop_index, ip_index, mass, _signed_mass in edges[prefix]:
                    if target_player == 0:
                        value[oop_index] += mass * opponent_reach[ip_index] * payoff
                    else:
                        value[ip_index] -= mass * opponent_reach[oop_index] * payoff
            else:
                scale = half_pot + min(node.contributions)
                for oop_index, ip_index, mass, signed_mass in edges[prefix]:
                    if target_player == 0:
                        value[oop_index] += signed_mass * opponent_reach[ip_index] * scale
                    else:
                        value[ip_index] -= signed_mass * opponent_reach[oop_index] * scale
            return value

        player = node.player
        action_count = len(node.actions)
        uniform = [1.0 / action_count] * action_count
        probabilities = [current.get((player, hand_index, node.history), uniform)
                         for hand_index in range(hand_counts[player])]

        if player == target_player:
            action_values = [visit(child, prefix, opponent_reach)
                             for child in node.children]
            value = [0.0] * target_count
            for hand_index in range(target_count):
                sigma = probabilities[hand_index]
                expected = sum(sigma[action] * action_values[action][hand_index]
                               for action in range(action_count))
                value[hand_index] = expected
                row = deltas.get((player, hand_index, node.history))
                if row is not None:
                    for action in range(action_count):
                        row[action] += action_values[action][hand_index] - expected
            return value

        value = [0.0] * target_count
        for action_index, child in enumerate(node.children):
            child_reach = [opponent_reach[hand_index] *
                           probabilities[hand_index][action_index]
                           for hand_index in range(hand_counts[opponent])]
            child_value = visit(child, prefix, child_reach)
            for hand_index, result in enumerate(child_value):
                value[hand_index] += result
        return value

    try:
        visit(root, (), [1.0] * hand_counts[opponent])
    finally:
        # Avoid retaining recursive frames and their private-hand working arrays.
        visit = None
    return deltas


def train_public_batched(root, worlds, infos, iterations, algorithm="vanilla",
                         *, pot, chance_type):
    """Train exact vanilla CFR, DCFR, or alternating CFR+ over the supplied tree.

    ``worlds`` contains tuples ``(oop_index, ip_index, mass, sign, *future)``;
    masses are the caller's joint range/blocker/chance weights. ``infos`` maps
    ``(player, hand_index, full_public_history)`` to an action count. Terminal
    utilities are specialized to the repository's fold/showdown node shape.

    The result maps each information-set key to its average action policy. This
    trainer has no lock or arbitrary callback API; use the shared CFR kernel
    when those features are required. Sparse prefix/hand edges are capped at
    ``MAX_PREFIX_EDGES``.
    """
    pot, hand_counts = _validate_inputs(
        worlds, infos, iterations, algorithm, pot, chance_type,
    )
    edges, marginals = _aggregate_prefixes(worlds, hand_counts)

    keys = list(infos)
    regrets = {key: [0.0] * infos[key] for key in keys}
    sums = {key: [0.0] * infos[key] for key in keys}
    half_pot = pot / 2.0

    def visitor(current, deltas, target_player=None, average_factor=0.0,
                average_only=False):
        def visit(node, prefix, reach0, reach1):
            if average_only:
                if isinstance(node, chance_type):
                    for card, child in node.branches.items():
                        visit(child, prefix + (card,), reach0, reach1)
                    return
                if isinstance(node, _Terminal):
                    return
                player = node.player
                action_count = len(node.actions)
                uniform = [1.0 / action_count] * action_count
                for hand_index in range(hand_counts[player]):
                    key = (player, hand_index, node.history)
                    if key in sums:
                        sigma = current.get(key, uniform)
                        own_mass = marginals[prefix][player][hand_index]
                        own_reach = reach0[hand_index] if player == 0 else reach1[hand_index]
                        for action in range(action_count):
                            sums[key][action] += (own_mass * own_reach * sigma[action] *
                                                  average_factor)
                for action_index, child in enumerate(node.children):
                    if player == 0:
                        child_reach0 = [reach0[i] * current.get(
                            (player, i, node.history), uniform)[action_index]
                            for i in range(hand_counts[0])]
                        visit(child, prefix, child_reach0, reach1)
                    else:
                        child_reach1 = [reach1[i] * current.get(
                            (player, i, node.history), uniform)[action_index]
                            for i in range(hand_counts[1])]
                        visit(child, prefix, reach0, child_reach1)
                return
            if isinstance(node, chance_type):
                value0 = [0.0] * hand_counts[0]
                value1 = [0.0] * hand_counts[1]
                for card, child in node.branches.items():
                    child0, child1 = visit(child, prefix + (card,), reach0, reach1)
                    for index, value in enumerate(child0):
                        value0[index] += value
                    for index, value in enumerate(child1):
                        value1[index] += value
                return value0, value1

            if isinstance(node, _Terminal):
                value0 = [0.0] * hand_counts[0]
                value1 = [0.0] * hand_counts[1]
                if node.kind == "fold":
                    winner_sign = 1.0 if node.winner == 0 else -1.0
                    payoff_mass = winner_sign * (half_pot + min(node.contributions))
                    for oop_index, ip_index, mass, _signed_mass in edges[prefix]:
                        value0[oop_index] += mass * reach1[ip_index] * payoff_mass
                        value1[ip_index] -= mass * reach0[oop_index] * payoff_mass
                else:
                    payoff_scale = half_pot + min(node.contributions)
                    for oop_index, ip_index, mass, signed_mass in edges[prefix]:
                        value0[oop_index] += signed_mass * reach1[ip_index] * payoff_scale
                        value1[ip_index] -= signed_mass * reach0[oop_index] * payoff_scale
                return value0, value1

            player = node.player
            action_count = len(node.actions)
            uniform = [1.0 / action_count] * action_count
            probabilities = [current.get((player, hand_index, node.history), uniform)
                             for hand_index in range(hand_counts[player])]
            value0 = [0.0] * hand_counts[0]
            value1 = [0.0] * hand_counts[1]
            action_values0 = []
            action_values1 = []

            for action_index, child in enumerate(node.children):
                if player == 0:
                    child_reach0 = [reach0[index] * probabilities[index][action_index]
                                    for index in range(hand_counts[0])]
                    child_reach1 = reach1
                else:
                    child_reach0 = reach0
                    child_reach1 = [reach1[index] * probabilities[index][action_index]
                                    for index in range(hand_counts[1])]
                child0, child1 = visit(child, prefix, child_reach0, child_reach1)
                action_values0.append(child0)
                action_values1.append(child1)

            if player == 0:
                own_mass = marginals[prefix][0]
                for hand_index in range(hand_counts[0]):
                    sigma = probabilities[hand_index]
                    expected = sum(sigma[action] * action_values0[action][hand_index]
                                   for action in range(action_count))
                    value0[hand_index] = expected
                    key = (player, hand_index, node.history)
                    if key in deltas and (target_player is None or target_player == player):
                        for action in range(action_count):
                            deltas[key][action] += action_values0[action][hand_index] - expected
                    if target_player is None and average_factor and key in sums:
                        for action in range(action_count):
                            sums[key][action] += (own_mass[hand_index] * reach0[hand_index] *
                                                  sigma[action] * average_factor)
                for hand_index in range(hand_counts[1]):
                    value1[hand_index] = sum(action_values1[action][hand_index]
                                             for action in range(action_count))
            else:
                own_mass = marginals[prefix][1]
                for hand_index in range(hand_counts[1]):
                    sigma = probabilities[hand_index]
                    expected = sum(sigma[action] * action_values1[action][hand_index]
                                   for action in range(action_count))
                    value1[hand_index] = expected
                    key = (player, hand_index, node.history)
                    if key in deltas and (target_player is None or target_player == player):
                        for action in range(action_count):
                            deltas[key][action] += action_values1[action][hand_index] - expected
                    if target_player is None and average_factor and key in sums:
                        for action in range(action_count):
                            sums[key][action] += (own_mass[hand_index] * reach1[hand_index] *
                                                  sigma[action] * average_factor)
                for hand_index in range(hand_counts[0]):
                    value0[hand_index] = sum(action_values0[action][hand_index]
                                             for action in range(action_count))
            return value0, value1

        try:
            visit(root, (), [1.0] * hand_counts[0], [1.0] * hand_counts[1])
        finally:
            visit = None

    for iteration in range(1, iterations + 1):
        current = {key: strategy(row) for key, row in regrets.items()}
        deltas = ({} if algorithm == "cfrplus" else
                  {key: [0.0] * infos[key] for key in keys})
        average_factor = iteration * iteration if algorithm == "dcfr" else 1.0
        if algorithm == "cfrplus":
            for player in (0, 1):
                deltas = _cfrplus_target_deltas(
                    root, edges, infos, current, player, hand_counts,
                    half_pot, chance_type,
                )
                for key in keys:
                    if key[0] == player:
                        regrets[key] = [max(0.0, old + delta)
                                        for old, delta in zip(regrets[key], deltas[key])]
                current = {key: strategy(row) for key, row in regrets.items()}
            visitor(current, {}, average_factor=float(iteration), average_only=True)
        else:
            visitor(current, deltas, average_factor=average_factor)
            for key in keys:
                updated = [old + delta for old, delta in zip(regrets[key], deltas[key])]
                if algorithm == "dcfr":
                    positive_discount = iteration ** 1.5 / (iteration ** 1.5 + 1.0)
                    updated = [value * (positive_discount if value > 0 else 0.5)
                               for value in updated]
                regrets[key] = updated

    averages = {}
    for key in keys:
        total = sum(sums[key])
        averages[key] = ([value / total for value in sums[key]] if total else
                         [1.0 / infos[key]] * infos[key])
    return averages
