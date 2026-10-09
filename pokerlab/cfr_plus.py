"""Reference alternating CFR+ trainer for finite weighted-world games.

This module is deliberately separate from the existing simultaneous CFR
backends. Its average policy is the profile after each completed alternating
sweep, weighted by linear iteration weight and the acting player's reach.
"""
from math import fsum, isclose, isfinite

from .cfr import strategy


def _validate_distribution(probabilities, count):
    try:
        values = [float(value) for value in probabilities]
    except (TypeError, ValueError, OverflowError):
        return False
    return len(values) == count and all(isfinite(value) and value >= 0 for value in values) and \
        isclose(sum(values), 1.0, rel_tol=1e-9, abs_tol=1e-9)


def train(root, worlds, infos, iterations, algorithm="cfrplus", terminal_value=None,
          node_key=None, chance_child=lambda node, world: None, locks=None,
          *, delay=0):
    """Train alternating CFR+ over fixed weighted worlds.

    ``infos`` maps information-set keys to action counts. The first key element
    must be the acting player (0 or 1), which allows each sweep to freeze the
    other player's policy while updating one player's regrets. World layout
    matches :func:`pokerlab.cfr.train`.

    Regret deltas are aggregated across all worlds before CFR+ clipping. At the
    end of a completed sweep, both players' current policies are averaged once
    using ``max(iteration - delay, 0)`` and own-player reach. Locks are fixed
    policies and receive no cumulative average mass.
    """
    if terminal_value is None or node_key is None:
        raise TypeError("terminal_value and node_key callbacks are required")
    if algorithm != "cfrplus":
        raise ValueError("CFR+ algorithm must be 'cfrplus'.")
    if type(iterations) is not int or iterations < 1:
        raise ValueError("CFR+ iterations must be a positive integer.")
    if type(delay) is not int or delay < 0:
        raise ValueError("CFR+ averaging delay must be a nonnegative integer.")

    counts = {}
    for key, count in infos.items():
        if not isinstance(key, tuple) or not key or type(key[0]) is not int or key[0] not in (0, 1):
            raise ValueError("CFR+ information-set keys must start with player 0 or 1.")
        if type(count) is not int or count < 1:
            raise ValueError("CFR+ action counts must be positive integers.")
        counts[key] = count
    if not counts:
        raise ValueError("CFR+ requires at least one information set.")
    worlds = tuple(worlds)
    if not worlds:
        raise ValueError("CFR+ requires at least one weighted world.")
    try:
        masses = [world[2] for world in worlds if len(world) >= 3]
    except (TypeError, IndexError):
        raise ValueError("CFR+ worlds must contain at least three fields.") from None
    invalid_masses = len(masses) != len(worlds) or any(
        isinstance(mass, bool) or not isinstance(mass, (int, float)) or
        not isfinite(mass) or mass < 0 for mass in masses)
    try:
        total_mass = fsum(masses) if not invalid_masses else 0.0
    except (OverflowError, ValueError):
        total_mass = float("inf")
    if invalid_masses or not isfinite(total_mass) or total_mass <= 0:
        raise ValueError("CFR+ world masses must be finite, nonnegative, and have positive total.")

    locked = {}
    for key, probabilities in (locks or {}).items():
        try:
            probabilities = tuple(float(value) for value in probabilities)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("CFR+ lock must match an information set and sum to one.") from None
        if key not in counts or not _validate_distribution(probabilities, counts[key]):
            raise ValueError("CFR+ lock must match an information set and sum to one.")
        locked[key] = probabilities

    regrets = {key: [0.0] * count for key, count in counts.items()}
    sums = {key: [0.0] * count for key, count in counts.items()}

    def profile():
        current = {key: strategy(row) for key, row in regrets.items()}
        current.update(locked)
        return current

    def update_player(player, current):
        deltas = {key: [0.0] * count for key, count in counts.items()
                  if key[0] == player and key not in locked}
        for world in worlds:
            chance_weight = world[2]

            def traverse(node, reach0, reach1):
                child = chance_child(node, world)
                if child is not None:
                    return traverse(child, reach0, reach1)
                if not hasattr(node, "actions"):
                    return terminal_value(node, world)
                key = node_key(node, world)
                probabilities = current[key]
                values = [traverse(
                    child_node,
                    reach0 * (probabilities[index] if node.player == 0 else 1.0),
                    reach1 * (probabilities[index] if node.player == 1 else 1.0))
                    for index, child_node in enumerate(node.children)]
                expected = sum(probability * value
                               for probability, value in zip(probabilities, values))
                if node.player == player and key not in locked:
                    opponent_reach = reach1 if player == 0 else reach0
                    utility_sign = 1 if player == 0 else -1
                    row = deltas[key]
                    for index, value in enumerate(values):
                        row[index] += chance_weight * opponent_reach * utility_sign * \
                            (value - expected)
                return expected

            try:
                traverse(root, 1.0, 1.0)
            finally:
                traverse = None
        for key, delta in deltas.items():
            regrets[key] = [max(0.0, old + change)
                            for old, change in zip(regrets[key], delta)]

    def accumulate_average(current, iteration_weight):
        if iteration_weight <= 0:
            return
        for world in worlds:
            chance_weight = world[2]

            def traverse(node, reach0, reach1):
                child = chance_child(node, world)
                if child is not None:
                    return traverse(child, reach0, reach1)
                if not hasattr(node, "actions"):
                    return
                key = node_key(node, world)
                probabilities = current[key]
                own_reach = reach0 if node.player == 0 else reach1
                if key not in locked:
                    row = sums[key]
                    factor = chance_weight * own_reach * iteration_weight
                    for index, probability in enumerate(probabilities):
                        row[index] += factor * probability
                for index, child_node in enumerate(node.children):
                    traverse(child_node,
                             reach0 * (probabilities[index] if node.player == 0 else 1.0),
                             reach1 * (probabilities[index] if node.player == 1 else 1.0))

            try:
                traverse(root, 1.0, 1.0)
            finally:
                traverse = None

    for iteration in range(1, iterations + 1):
        # Player 0 updates against the frozen start-of-sweep profile.
        update_player(0, profile())
        # Player 1 observes player 0's newly updated policy.
        update_player(1, profile())
        # Average one completed profile, including both players exactly once.
        accumulate_average(profile(), max(iteration - delay, 0))

    averages = {}
    for key, values in sums.items():
        total = sum(values)
        averages[key] = [value / total for value in values] if total else \
            [1.0 / counts[key]] * counts[key]
    averages.update({key: list(values) for key, values in locked.items()})
    return averages
