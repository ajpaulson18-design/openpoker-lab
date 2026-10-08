"""Reusable full-traversal CFR, strategy evaluation, and best responses."""


def strategy(regret):
    """Regret-matching strategy for one information set."""
    positive = [max(0.0, value) for value in regret]
    mass = sum(positive)
    return [value / mass for value in positive] if mass else [1.0 / len(regret)] * len(regret)


def _scale_world(world, factor):
    return tuple(world[:2]) + (world[2] * factor,) + tuple(world[3:])


def train(root, worlds, infos, iterations, algorithm="vanilla", terminal_value=None,
          node_key=None, chance_child=lambda node, world: None, locks=None):
    """Train simultaneous CFR policies over weighted worlds.

    Worlds are tuples ``(oop_hand, ip_hand, weight, sign, *public_state)``;
    the caller owns keying, terminal utility, and any public chance transition.
    ``locks`` maps information-set keys to fixed action distributions.
    """
    if terminal_value is None or node_key is None:
        raise TypeError("terminal_value and node_key callbacks are required")
    if algorithm not in ("vanilla", "dcfr"):
        raise ValueError("CFR algorithm must be vanilla or dcfr.")
    if type(iterations) is not int or iterations < 1:
        raise ValueError("CFR iterations must be a positive integer.")
    regrets = {key: [0.0] * count for key, count in infos.items()}
    sums = {key: [0.0] * count for key, count in infos.items()}
    locks = locks or {}

    for iteration in range(1, iterations + 1):
        current = {key: strategy(regret) for key, regret in regrets.items()}
        for key, probabilities in locks.items():
            if key not in current or len(probabilities) != len(current[key]):
                raise ValueError("CFR lock does not match a known information set.")
            current[key] = list(probabilities)
        deltas = {key: [0.0] * count for key, count in infos.items()}

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
                action_values = [traverse(
                    child_node,
                    reach0 * (probabilities[index] if node.player == 0 else 1.0),
                    reach1 * (probabilities[index] if node.player == 1 else 1.0))
                    for index, child_node in enumerate(node.children)]
                expected = sum(probability * value
                               for probability, value in zip(probabilities, action_values))
                opponent_reach = reach1 if node.player == 0 else reach0
                own_reach = reach0 if node.player == 0 else reach1
                utility_sign = 1 if node.player == 0 else -1
                for index, value in enumerate(action_values):
                    deltas[key][index] += chance_weight * opponent_reach * utility_sign * \
                        (value - expected)
                    sums[key][index] += chance_weight * own_reach * probabilities[index] * \
                        (iteration ** 2 if algorithm == "dcfr" else 1.0)
                return expected

            try:
                traverse(root, 1.0, 1.0)
            finally:
                # The recursive closure captures this binding. Break its cycle
                # before returning so final training arrays await no cyclic GC.
                traverse = None

        for key, values in regrets.items():
            updated = [old + delta for old, delta in zip(values, deltas[key])]
            if algorithm == "dcfr":
                positive_discount = iteration ** 1.5 / (iteration ** 1.5 + 1)
                updated = [value * (positive_discount if value > 0 else .5)
                           for value in updated]
            regrets[key] = updated

    averages = {}
    for key, values in sums.items():
        total = sum(values)
        averages[key] = [value / total for value in values] if total else \
            [1.0 / len(values)] * len(values)
    for key, probabilities in locks.items():
        averages[key] = list(probabilities)
    return averages


def evaluate(root, worlds, averages, terminal_value, node_key,
             chance_child=lambda node, world: None):
    """Return OOP's expected value for a strategy profile over weighted worlds."""
    def visit(node, world):
        child = chance_child(node, world)
        if child is not None:
            return visit(child, world)
        if not hasattr(node, "actions"):
            return terminal_value(node, world)
        probabilities = averages[node_key(node, world)]
        return sum(probability * visit(child_node, world)
                   for probability, child_node in zip(probabilities, node.children))

    return sum(world[2] * visit(root, world) for world in worlds)


def best_response(player, root, worlds, averages, terminal_value, node_key,
                  chance_partitions=lambda node, weighted_worlds: None):
    """Compute an information-set best response without hidden-card access.

    Worlds are grouped by the responding player's private hand before any
    maximization. Public chance partitions are summed, never maximized.
    """
    if player not in (0, 1):
        raise ValueError("Best-response player must be 0 (OOP) or 1 (IP).")
    grouped = {}
    for world in worlds:
        grouped.setdefault(world[player], []).append(world)
    result = 0.0

    for own_hand_worlds in grouped.values():
        def visit(node, weighted_worlds):
            if not weighted_worlds:
                return 0.0
            partitions = chance_partitions(node, weighted_worlds)
            if partitions is not None:
                return sum(visit(child, child_worlds) for child, child_worlds in partitions)
            if not hasattr(node, "actions"):
                utility_sign = 1 if player == 0 else -1
                return sum(world[2] * utility_sign * terminal_value(node, world)
                           for world in weighted_worlds)

            if node.player == player:
                return max(visit(child, weighted_worlds) for child in node.children)

            value = 0.0
            for action_index, child in enumerate(node.children):
                branched = []
                for world in weighted_worlds:
                    probabilities = averages[node_key(node, world)]
                    weight = world[2] * probabilities[action_index]
                    if weight:
                        branched.append(_scale_world(world, probabilities[action_index]))
                if branched:
                    value += visit(child, branched)
            return value

        result += visit(root, own_hand_worlds)
    return result
