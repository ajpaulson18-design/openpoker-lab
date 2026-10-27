"""Contiguous binary64 strategy buffers for selected-operator CFR+.

This is an opt-in storage/traversal implementation of the same alternating
public-vector algorithm. The retained reference kernel is independent of this
layout. No information sets, actions, chance outcomes or reaches are merged.
"""
from array import array

from .postflop_solver import _Chance
from .river_tree import _Node, _Terminal


MAX_ACTION_SLOTS = 1_000_000
MAX_DENSE_DECISION_HAND_SLOTS = 2_000_000
MAX_LAYOUT_LOOP_ENTRIES = 500_000_000
MAX_PUBLIC_STATES = 250_000
MAX_DEPTH = 256


def layout_census(root, infos, hand_counts, iterations):
    """Admit all requested rows, dense holes and buffer work before allocation."""
    if type(iterations) is not int or not 10 <= iterations <= 10_000:
        raise ValueError("Packed CFR+ requires 10-10,000 iterations.")
    if (len(hand_counts) != 2 or any(type(h) is not int or not 1 <= h <= 1326
                                      for h in hand_counts)):
        raise ValueError("Packed CFR+ requires two bounded private-hand dimensions.")
    slots = 0
    for key, count in infos.items():
        if (not isinstance(key, tuple) or len(key) != 3 or type(key[0]) is not int or
                key[0] not in (0, 1) or type(key[1]) is not int or
                not 0 <= key[1] < hand_counts[key[0]] or not isinstance(key[2], tuple) or
                type(count) is not int or count < 1):
            raise ValueError("Malformed packed information-set identity or menu.")
        slots += count
        if slots > MAX_ACTION_SLOTS:
            raise ValueError("Packed action-slot capacity exceeded.")
    states = dense = decisions = decision_width = 0
    pending = [(root, 0)]
    seen = set()
    covered = set()
    while pending:
        node, depth = pending.pop()
        if depth > MAX_DEPTH:
            raise ValueError("Packed public-tree depth exceeded.")
        if id(node) in seen:
            # A shared terminal/continuation can be visited under multiple
            # histories. Require a literal tree here rather than lose recall.
            raise ValueError("Packed layout requires an unshared acyclic public tree.")
        seen.add(id(node))
        states += 1
        if states > MAX_PUBLIC_STATES:
            raise ValueError("Packed public-state capacity exceeded.")
        if isinstance(node, _Terminal):
            continue
        if isinstance(node, _Chance):
            pending.extend((child, depth + 1) for child in node.branches.values())
            continue
        if not isinstance(node, _Node) or node.player not in (0, 1) or not node.children:
            raise ValueError("Malformed packed public decision.")
        if len(node.actions) != len(node.children):
            raise ValueError("Packed action/child menu mismatch.")
        dense += hand_counts[node.player]
        decisions += 1
        decision_width += len(node.actions) + 1
        if dense > MAX_DENSE_DECISION_HAND_SLOTS:
            raise ValueError("Packed decision/hand capacity exceeded.")
        for hand in range(hand_counts[node.player]):
            key = (node.player, hand, node.history)
            if key in infos:
                if infos[key] != len(node.actions) or key in covered:
                    raise ValueError("Packed information-set menu or public-history identity mismatch.")
                covered.add(key)
        pending.extend((child, depth + 1) for child in node.children)
    if covered != set(infos):
        raise ValueError("Packed information sets do not match the complete public tree.")
    # Buffer reset, regret matching, player updates, average/output rows and
    # dense row lookup are separately bounded. Terminal mass/rank work retains
    # the enclosing operator's unchanged requested envelope.
    # Both responding and acting vectors matter, including inactive index
    # holes and unequal ranges. Charging only acting-hand rows would miss the
    # other player's values at asymmetric decisions.
    vector_entries = 12 * sum(hand_counts) * (decision_width + states)
    loops = iterations * (32 * slots + vector_entries) + 8 * slots + 4 * dense + 4 * states
    if loops > MAX_LAYOUT_LOOP_ENTRIES:
        raise ValueError("Packed requested layout loop capacity exceeded.")
    if array("d").itemsize != 8:
        raise RuntimeError("Packed storage requires eight-byte binary64 doubles.")
    return {"version": "selected-packed-cfrplus-v1", "information_sets": len(infos),
            "action_slots": slots, "public_states": states, "decisions": decisions,
            "dense_decision_hand_slots": dense, "numeric_buffers": 4,
            "numeric_buffer_bytes": 4 * slots * 8,
            "dense_lookup_payload_bytes": dense * array("i").itemsize,
            "row_offset_and_count_payload_bytes": 2 * len(infos) * array("I").itemsize,
            "per_sweep_vector_entry_bound": vector_entries,
            "requested_layout_loop_entries": loops, "layout_loop_limit": MAX_LAYOUT_LOOP_ENTRIES,
            "scope": "Array payload bytes only; keys, tree, dictionaries, output, Python headers and recursion scratch excluded."}


def train_packed(root, infos, iterations, *, operator, marginals, return_receipt=False):
    """Train zero-delay alternating CFR+ without per-row numeric dictionaries."""
    hand_counts = operator.hand_counts
    census = layout_census(root, infos, hand_counts, iterations)
    keys = tuple(infos)
    offsets, counts = array("I"), array("I")
    locations = {}
    cursor = 0
    for key in keys:
        offsets.append(cursor)
        counts.append(infos[key])
        locations[key] = cursor
        cursor += infos[key]
    rows = {}
    pending = [root]
    while pending:
        node = pending.pop()
        if isinstance(node, _Chance):
            pending.extend(node.branches.values())
        elif isinstance(node, _Node):
            rows[id(node)] = array("i", (locations.get((node.player, h, node.history), -1)
                                         for h in range(hand_counts[node.player])))
            pending.extend(node.children)
    # The temporary semantic-key -> offset map is not retained in training.
    locations = None
    regrets = array("d", [0.0]) * cursor
    sums = array("d", [0.0]) * cursor
    current = array("d", [0.0]) * cursor
    deltas = array("d", [0.0]) * cursor

    def rematch():
        for offset, count in zip(offsets, counts):
            positive = [max(0.0, regrets[offset + a]) for a in range(count)]
            mass = sum(positive)
            for a in range(count):
                current[offset + a] = positive[a] / mass if mass else 1.0 / count

    def target_values(node, prefix, opponent_reach, target):
        if isinstance(node, _Chance):
            value = [0.0] * hand_counts[target]
            for card, child in node.branches.items():
                child_value = target_values(child, prefix + (card,), opponent_reach, target)
                for h, result in enumerate(child_value):
                    value[h] += result
            return value
        if isinstance(node, _Terminal):
            return operator.values(node, opponent_reach, target, prefix)
        player, count = node.player, len(node.children)
        slots = rows[id(node)]
        uniform = [1.0 / count] * count
        probabilities = [current[offset:offset + count] if offset >= 0 else uniform
                         for offset in slots]
        if player == target:
            actions = [target_values(child, prefix, opponent_reach, target) for child in node.children]
            value = [0.0] * hand_counts[target]
            for h, offset in enumerate(slots):
                expected = sum(probabilities[h][a] * actions[a][h] for a in range(count))
                value[h] = expected
                if offset >= 0:
                    for a in range(count):
                        deltas[offset + a] += actions[a][h] - expected
            return value
        value = [0.0] * hand_counts[target]
        for a, child in enumerate(node.children):
            changed = [opponent_reach[h] * probabilities[h][a] for h in range(hand_counts[player])]
            child_value = target_values(child, prefix, changed, target)
            for h, result in enumerate(child_value):
                value[h] += result
        return value

    def average(node, prefix, reach0, reach1, factor):
        if isinstance(node, _Terminal):
            return
        if isinstance(node, _Chance):
            for card, child in node.branches.items():
                average(child, prefix + (card,), reach0, reach1, factor)
            return
        player, count = node.player, len(node.children)
        slots = rows[id(node)]
        for h, offset in enumerate(slots):
            if offset >= 0:
                own_mass = marginals[prefix][player][h]
                own_reach = (reach0 if player == 0 else reach1)[h]
                for a in range(count):
                    sums[offset + a] += own_mass * own_reach * current[offset + a] * factor
        for a, child in enumerate(node.children):
            own = reach0 if player == 0 else reach1
            changed = [own[h] * (current[offset + a] if offset >= 0 else 1.0 / count)
                       for h, offset in enumerate(slots)]
            average(child, prefix, changed if player == 0 else reach0,
                    changed if player == 1 else reach1, factor)

    try:
        for iteration in range(1, iterations + 1):
            rematch()
            for player in (0, 1):
                for key, offset, count in zip(keys, offsets, counts):
                    if key[0] == player:
                        for a in range(count):
                            deltas[offset + a] = 0.0
                target_values(root, (), [1.0] * hand_counts[1-player], player)
                for key, offset, count in zip(keys, offsets, counts):
                    if key[0] == player:
                        for a in range(count):
                            regrets[offset + a] = max(0.0, regrets[offset + a] + deltas[offset + a])
                rematch()
            average(root, (), [1.0] * hand_counts[0], [1.0] * hand_counts[1], float(iteration))
        result = {}
        for key, offset, count in zip(keys, offsets, counts):
            row = sums[offset:offset + count]
            total = sum(row)
            result[key] = [value / total for value in row] if total else [1.0 / count] * count
    finally:
        # Break recursive closure cycles on success and exceptions; no buffers
        # or history-to-slot plan survives the training operation.
        target_values = average = rematch = None
        regrets = sums = current = deltas = None
        rows.clear()
        keys = offsets = counts = None
    return (result, census) if return_receipt else result
