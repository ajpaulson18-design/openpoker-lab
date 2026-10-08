"""Opt-in Python CFR traversal plans for static finite chance-world games.

The recursive kernel remains the independent reference. This backend evaluates
terminal utilities and resolves each world's chance transitions once per solve,
then performs iterative value/reach passes. Callbacks must be deterministic and
terminal utilities must remain constant throughout training. Plans are local to
one call and their operation count is bounded to control retained memory.
"""
from .cfr import strategy

MAX_PLAN_OPS = 250_000


def _plans(root, worlds, key_indexes, terminal_value, node_key, chance_child,
           max_plan_ops):
    plans = []
    operation_count = 0
    for world in worlds:
        operations = []

        def visit(node):
            nonlocal operation_count
            child = chance_child(node, world)
            if child is not None:
                return visit(child)
            if hasattr(node, "actions"):
                children = tuple(visit(child) for child in node.children)
                op = (node.player, key_indexes[node_key(node, world)], children)
            else:
                op = (None, terminal_value(node, world), ())
            operation_count += 1
            if operation_count > max_plan_ops:
                raise ValueError("Planned CFR exceeds the retained traversal operation limit.")
            operations.append(op)
            return len(operations) - 1

        try:
            root_index = visit(root)
        finally:
            # The compiler's recursive closure must not retain the callback,
            # key map and last operation array after this world is prepared.
            visit = None
        order, pending = [], [root_index]
        while pending:
            index = pending.pop()
            order.append(index)
            pending.extend(reversed(operations[index][2]))
        plans.append((operations, order, root_index, world[2]))
    return plans


def train(root, worlds, infos, iterations, algorithm="vanilla", terminal_value=None,
          node_key=None, chance_child=lambda node, world: None, locks=None,
          *, max_plan_ops=MAX_PLAN_OPS):
    """Match recursive CFR updates using bounded precomputed traversal plans."""
    if terminal_value is None or node_key is None:
        raise TypeError("terminal_value and node_key callbacks are required")
    if algorithm not in ("vanilla", "dcfr"):
        raise ValueError("CFR algorithm must be vanilla or dcfr.")
    if type(iterations) is not int or iterations < 1:
        raise ValueError("CFR iterations must be a positive integer.")
    if type(max_plan_ops) is not int or max_plan_ops < 1:
        raise ValueError("Traversal operation limit must be a positive integer.")
    keys = list(infos)
    key_indexes = {key: index for index, key in enumerate(keys)}
    counts = [infos[key] for key in keys]
    locked = {}
    for key, probabilities in (locks or {}).items():
        if key not in infos or len(probabilities) != infos[key]:
            raise ValueError("CFR lock does not match a known information set.")
        locked[key_indexes[key]] = list(probabilities)
    plans = _plans(root, worlds, key_indexes, terminal_value, node_key, chance_child,
                   max_plan_ops)
    regrets = [[0.] * count for count in counts]
    sums = [[0.] * count for count in counts]

    for iteration in range(1, iterations + 1):
        current = [strategy(row) for row in regrets]
        for index, probabilities in locked.items():
            current[index] = probabilities
        deltas = [[0.] * count for count in counts]
        average_factor = iteration * iteration if algorithm == "dcfr" else 1.
        for operations, order, root_index, chance_weight in plans:
            values = [0.] * len(operations)
            for index, (player, info_or_value, children) in enumerate(operations):
                if player is None:
                    values[index] = info_or_value
                else:
                    values[index] = sum(p * values[child] for p, child in
                                        zip(current[info_or_value], children))
            reach0, reach1 = [0.] * len(operations), [0.] * len(operations)
            reach0[root_index] = reach1[root_index] = 1.
            for index in order:
                player, info, children = operations[index]
                if player is None:
                    continue
                r0, r1 = reach0[index], reach1[index]
                own, opponent = (r0, r1) if player == 0 else (r1, r0)
                utility_sign = 1 if player == 0 else -1
                probabilities = current[info]
                regret_row, sum_row = deltas[info], sums[info]
                expected = values[index]
                for action, child in enumerate(children):
                    probability = probabilities[action]
                    regret_row[action] += chance_weight * opponent * utility_sign * \
                        (values[child] - expected)
                    sum_row[action] += chance_weight * own * probability * average_factor
                    reach0[child] = r0 * probability if player == 0 else r0
                    reach1[child] = r1 * probability if player == 1 else r1
        positive_discount = iteration ** 1.5 / (iteration ** 1.5 + 1)
        for index, row in enumerate(regrets):
            updated = [old + delta for old, delta in zip(row, deltas[index])]
            if algorithm == "dcfr":
                updated = [value * (positive_discount if value > 0 else .5)
                           for value in updated]
            regrets[index] = updated
    averages = {}
    for index, key in enumerate(keys):
        total = sum(sums[index])
        averages[key] = [value / total for value in sums[index]] if total else \
            [1. / counts[index]] * counts[index]
    for index, probabilities in locked.items():
        averages[keys[index]] = list(probabilities)
    return averages
