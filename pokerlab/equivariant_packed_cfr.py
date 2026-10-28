"""Suit-equivariant binary64 reference traversal for shared packed CFR+.

This is an unquotiented reference trajectory. At every chance target-vector
node it sorts finite child components before an explicitly ordered reduction,
so the reduction does not depend on the ordering of suit-isomorphic branches.
It does not merge public vertices, information sets, actions, or hands.
"""
from array import array
import math

from .exact_selected_float_adapter import ExactSelectedFloatAdapter
from .river_tree import _Terminal
from .shared_public_topology import ChanceVertex, DecisionVertex, TerminalVertex
from .shared_topology_view import (
    ChanceCursor, DecisionCursor, SharedPublicView, layout_census_shared,
)

MAX_EQUIVARIANT_MODELED_WORK = 500_000_000
MAX_EQUIVARIANT_RETAINED_ENTRIES = 25_000_000
NUMERICAL_REDUCTION = "suit-equivariant-sorted-chance-binary64-v1"


def _finite(value, label):
    """Validate a binary64 component and give every zero the +0 encoding."""
    if type(value) is not float or not math.isfinite(value):
        raise ValueError(f"{label} must be finite binary64 before arithmetic or comparison.")
    return 0.0 if value == 0.0 else value


def _add(left, right, label="CFR+ sum"):
    left = _finite(left, label)
    right = _finite(right, label)
    return _finite(left + right, label)


def _sub(left, right, label="CFR+ difference"):
    left = _finite(left, label)
    right = _finite(right, label)
    return _finite(left - right, label)


def _mul(left, right, label="CFR+ product"):
    left = _finite(left, label)
    right = _finite(right, label)
    return _finite(left * right, label)


def _div(left, right, label="CFR+ quotient"):
    left = _finite(left, label)
    right = _finite(right, label)
    if right == 0.0:
        raise ValueError(f"{label} has a zero denominator.")
    return _finite(left / right, label)


def _vector(values, size, label):
    if type(values) not in (list, tuple) or len(values) != size:
        raise ValueError(f"{label} has an invalid vector dimension.")
    return [_finite(value, label) for value in values]


def _sorted_chance_sum(child_vectors, size):
    """Sort each finite hand component, then add left-to-right from +0."""
    components = [[] for _ in range(size)]
    for child_index, child in enumerate(child_vectors):
        values = _vector(child, size, f"chance child {child_index}")
        for hand, value in enumerate(values):
            components[hand].append(value)
    result = []
    for hand_components in components:
        hand_components.sort()
        total = 0.0
        for value in hand_components:
            total = _add(total, value, "sorted chance reduction")
        result.append(total)
    return result


def equivariant_layout_census(view, infos, hand_counts, iterations):
    """Admit legacy packed layout plus sorted-chance work and nested scratch.

    The additional model charges two target traversals per iteration. For each
    logical chance occurrence it charges validation and explicit summation for
    every child/hand component plus a conservative ``n * bit_length(n)`` sort
    bound. Scratch uses maximum logical depth times maximum chance degree times
    maximum hand dimension, covering simultaneously live recursive frames.
    These are modeled work and logical entries, not CPU, allocator bytes, or
    RSS claims.
    """
    legacy = layout_census_shared(view, infos, hand_counts, iterations)
    additional = equivariant_additional_census(view, hand_counts, iterations)
    return {**legacy,
        "equivariant_version": "suit-equivariant-packed-reference-layout-v1",
        "numerical_reduction": NUMERICAL_REDUCTION,
        "equivariant_additional_admission": additional}


def equivariant_additional_census(view, hand_counts, iterations):
    """Preflight only extra sorted-chance work/scratch before information rows.

    This helper deliberately does not call the legacy layout census or inspect
    ``infos``. Whole-solver preparation can use it before allocating expanded
    information rows, then call :func:`equivariant_layout_census` after rows
    exist and verify that the same additional receipt was returned.
    """
    if type(view) is not SharedPublicView:
        raise TypeError("Equivariant extra admission requires SharedPublicView.")
    if (type(hand_counts) not in (tuple, list) or len(hand_counts) != 2 or
            any(type(count) is not int or not 1 <= count <= 1326 for count in hand_counts)):
        raise ValueError("Equivariant extra admission requires two hand counts from 1 through 1,326.")
    if type(iterations) is not int or not 10 <= iterations <= 10_000:
        raise ValueError("Equivariant extra admission requires 10 through 10,000 iterations.")
    maximum_hand_count = max(hand_counts)
    chance_occurrences = 0
    chance_branches = 0
    logical_occurrences = 0
    history_token_entries = 0
    maximum_chance_degree = 0
    maximum_depth = 0
    maximum_actions = 1
    sort_component_upper = 0
    child_component_upper = 0
    decision_occurrences = 0
    dense_action_slots_upper = 0
    dense_decision_hand_slots = 0
    decision_width = 0
    logical_visits = 0
    for occurrence in view.topology.iter_occurrences():
        logical_occurrences += 1
        history_token_entries += len(occurrence.history)
        logical_visits += 1
        maximum_depth = max(maximum_depth, occurrence.depth + 1)
        vertex = view.topology.vertices[occurrence.vertex_id]
        if isinstance(vertex, ChanceVertex):
            degree = len(vertex.branches)
            chance_occurrences += 1
            chance_branches += degree
            maximum_chance_degree = max(maximum_chance_degree, degree)
            child_component_upper += degree * maximum_hand_count
            sort_component_upper += degree * max(1, degree.bit_length()) * maximum_hand_count
        elif isinstance(vertex, DecisionVertex):
            decision_occurrences += 1
            maximum_actions = max(maximum_actions, len(vertex.actions))
            player_hands = hand_counts[vertex.player]
            dense_decision_hand_slots += player_hands
            dense_action_slots_upper += len(vertex.actions) * player_hands
            decision_width += len(vertex.actions) + 1

    two_target_passes = 2 * iterations
    reduction_work = two_target_passes * (
        sort_component_upper + 8 * child_component_upper)
    scalar_validation_work = (
        64 * iterations * (dense_action_slots_upper +
            sum(hand_counts) * (decision_width + logical_visits)) +
        32 * dense_action_slots_upper + 32 * logical_visits)
    setup_work = (4 * logical_occurrences + history_token_entries +
                  2 * chance_branches + 4 * decision_occurrences)
    additional_work = reduction_work + scalar_validation_work + setup_work

    # Each recursive frame may retain its chance children while descending;
    # target-player decision frames may also retain action child vectors.
    per_depth_vectors = ((3 * maximum_chance_degree +
                          2 * maximum_actions + 8) * maximum_hand_count +
                         3 * maximum_chance_degree + 32)
    scratch_entries = maximum_depth * per_depth_vectors
    additional_entries = scratch_entries + 8 * (chance_occurrences + decision_occurrences)
    if additional_work > MAX_EQUIVARIANT_MODELED_WORK:
        raise ValueError("Equivariant CFR+ additional modeled work exceeds 500 million units.")
    if additional_entries > MAX_EQUIVARIANT_RETAINED_ENTRIES:
        raise ValueError("Equivariant CFR+ additional retained/scratch entries exceed 25 million.")
    return {
            "version": "suit-equivariant-packed-extra-admission-v1",
            "chance_occurrences": chance_occurrences,
            "chance_branch_occurrences": chance_branches,
            "decision_occurrences": decision_occurrences,
            "logical_occurrences_scanned": logical_occurrences,
            "history_token_entries_scanned": history_token_entries,
            "maximum_chance_degree": maximum_chance_degree,
            "maximum_logical_depth_frames": maximum_depth,
            "maximum_hand_dimension": maximum_hand_count,
            "target_passes": two_target_passes,
            "dense_action_slots_upper": dense_action_slots_upper,
            "dense_decision_hand_slots_upper": dense_decision_hand_slots,
            "decision_width_upper": decision_width,
            "logical_visits_upper": logical_visits,
            "sort_component_work_upper": sort_component_upper,
            "child_component_work_upper": child_component_upper,
            "reduction_work_upper": reduction_work,
            "scalar_validation_work_upper": scalar_validation_work,
            "setup_work_upper": setup_work,
            "modeled_work_upper": additional_work,
            "modeled_work_limit": MAX_EQUIVARIANT_MODELED_WORK,
            "per_depth_scratch_entries_upper": scratch_entries,
            "additional_retained_entries_upper": additional_entries,
            "additional_retained_entries_limit": MAX_EQUIVARIANT_RETAINED_ENTRIES,
            "scope": "Standalone conservative work/entry admission for sorted chance reductions and recursive vector scratch; excludes allocator bytes, CPU time, and process memory."}


def train_equivariant_packed(root, infos, iterations, *, operator, marginals,
                             return_receipt=False, shared_view=None):
    """Train unquotiented zero-delay alternating CFR+ under sorted chance sums."""
    if type(operator) is not ExactSelectedFloatAdapter:
        raise TypeError("Equivariant packed training requires ExactSelectedFloatAdapter.")
    if type(shared_view) is not SharedPublicView:
        raise TypeError("Equivariant packed training requires the admitted SharedPublicView.")
    if getattr(operator, "view", None) is not shared_view:
        raise ValueError("Equivariant adapter does not belong to the supplied shared view.")
    hand_counts = operator.hand_counts
    expected_root = shared_view.root
    if isinstance(expected_root, _Terminal):
        valid_root = root is expected_root
    else:
        valid_root = (type(root) is type(expected_root) and
                      type(root) in (ChanceCursor, DecisionCursor) and
                      root.view is shared_view and root.vertex_id == expected_root.vertex_id and
                      root.history == expected_root.history)
    if not valid_root:
        raise ValueError("Equivariant packed root is not the admitted shared topology root.")
    census = keys = offsets = counts = locations = None
    regrets = sums = current = deltas = None
    target_values = average = rematch = row_offsets = None
    result = None
    completed = False
    try:
        census = equivariant_layout_census(shared_view, infos, hand_counts, iterations)

        keys = tuple(infos)
        offsets, counts = array("I"), array("I")
        locations = {}
        cursor = 0
        for key in keys:
            offsets.append(cursor)
            counts.append(infos[key])
            locations[key] = cursor
            cursor += infos[key]

        def row_offsets(node):
            return tuple(locations.get((node.player, hand, node.history), -1)
                         for hand in range(hand_counts[node.player]))

        regrets = array("d", [0.0]) * cursor
        sums = array("d", [0.0]) * cursor
        current = array("d", [0.0]) * cursor
        deltas = array("d", [0.0]) * cursor
        result = None

        def rematch():
            for offset, count in zip(offsets, counts):
                positive = []
                mass = 0.0
                for action in range(count):
                    regret = _finite(regrets[offset + action], "regret")
                    value = regret if regret > 0.0 else 0.0
                    positive.append(value)
                    mass = _add(mass, value, "regret-matching mass")
                for action, value in enumerate(positive):
                    current[offset + action] = (_div(value, mass, "regret-matching probability")
                        if mass else _div(1.0, float(count), "uniform regret-matching probability"))

        def target_values(node, prefix, opponent_reach, target):
            if isinstance(node, ChanceCursor):
                child_vectors = []
                for card, child in node.branches.items():
                    child_vectors.append(target_values(child, prefix + (card,), opponent_reach, target))
                return _sorted_chance_sum(child_vectors, hand_counts[target])
            if isinstance(node, _Terminal):
                values = operator.values(node, opponent_reach, target, prefix)
                return _vector(values, hand_counts[target], "terminal callback")
            if not isinstance(node, DecisionCursor):
                raise TypeError("Unsupported node in equivariant shared traversal.")
            player, count = node.player, len(node.children)
            slots = row_offsets(node)
            probabilities = []
            for offset in slots:
                if offset >= 0:
                    probabilities.append([_finite(current[offset + action], "strategy probability")
                                          for action in range(count)])
                else:
                    probability = _div(1.0, float(count), "uniform absent-row probability")
                    probabilities.append([probability] * count)
            if player == target:
                action_vectors = [target_values(child, prefix, opponent_reach, target)
                                  for child in node.children]
                value = [0.0] * hand_counts[target]
                for hand, offset in enumerate(slots):
                    expected = 0.0
                    for action in range(count):
                        product = _mul(probabilities[hand][action], action_vectors[action][hand],
                                       "acting-player action value")
                        expected = _add(expected, product, "acting-player action dot product")
                    value[hand] = expected
                    if offset >= 0:
                        for action in range(count):
                            difference = _sub(action_vectors[action][hand], expected,
                                              "counterfactual regret increment")
                            deltas[offset + action] = _add(deltas[offset + action], difference,
                                                           "counterfactual regret accumulation")
                return value
            value = [0.0] * hand_counts[target]
            for action, child in enumerate(node.children):
                changed_reach = [_mul(opponent_reach[hand], probabilities[hand][action],
                                      "opponent reach update")
                                 for hand in range(hand_counts[player])]
                child_value = target_values(child, prefix, changed_reach, target)
                for hand, component in enumerate(child_value):
                    value[hand] = _add(value[hand], component, "opponent action value sum")
            return value

        def average(node, prefix, reach0, reach1, factor):
            if isinstance(node, _Terminal):
                return
            if isinstance(node, ChanceCursor):
                for card, child in node.branches.items():
                    average(child, prefix + (card,), reach0, reach1, factor)
                return
            if not isinstance(node, DecisionCursor):
                raise TypeError("Unsupported node in equivariant averaging traversal.")
            player, count = node.player, len(node.children)
            slots = row_offsets(node)
            for hand, offset in enumerate(slots):
                if offset >= 0:
                    own_mass = _finite(marginals[prefix][player][hand], "own marginal")
                    own_reach = _finite((reach0 if player == 0 else reach1)[hand], "own reach")
                    for action in range(count):
                        contribution = _mul(own_mass, own_reach, "own-reach weighted marginal")
                        contribution = _mul(contribution, current[offset + action], "average strategy mass")
                        contribution = _mul(contribution, factor, "iteration-weighted average")
                        sums[offset + action] = _add(sums[offset + action], contribution,
                                                      "average-strategy accumulation")
            for action, child in enumerate(node.children):
                own = reach0 if player == 0 else reach1
                changed = []
                for hand, offset in enumerate(slots):
                    probability = (current[offset + action] if offset >= 0 else
                        _div(1.0, float(count), "uniform absent-row average probability"))
                    changed.append(_mul(own[hand], probability, "own reach update"))
                average(child, prefix, changed if player == 0 else reach0,
                        changed if player == 1 else reach1, factor)

        if array("d").itemsize != 8:
            raise RuntimeError("Equivariant packed storage requires binary64 doubles.")
        for iteration in range(1, iterations + 1):
            rematch()
            for player in (0, 1):
                for key, offset, count in zip(keys, offsets, counts):
                    if key[0] == player:
                        for action in range(count):
                            deltas[offset + action] = 0.0
                target_values(root, (), [1.0] * hand_counts[1 - player], player)
                for key, offset, count in zip(keys, offsets, counts):
                    if key[0] == player:
                        for action in range(count):
                            increment = _finite(deltas[offset + action], "regret delta")
                            regret = _add(regrets[offset + action], increment, "CFR+ regret update")
                            regrets[offset + action] = regret if regret > 0.0 else 0.0
                rematch()
            average(root, (), [1.0] * hand_counts[0], [1.0] * hand_counts[1], float(iteration))
        result = {}
        for key, offset, count in zip(keys, offsets, counts):
            total = 0.0
            for action in range(count):
                total = _add(total, sums[offset + action], "average output normalizer")
            if total:
                result[key] = [_div(_finite(sums[offset + action], "average output"), total,
                                    "average output probability") for action in range(count)]
            else:
                result[key] = [_div(1.0, float(count), "uniform average output") for _ in range(count)]
        _canonicalize_result(result)
        completed = True
    finally:
        target_values = average = rematch = row_offsets = None
        regrets = sums = current = deltas = None
        keys = offsets = counts = locations = None
        if not completed:
            result = None
    return (result, census) if return_receipt else result


def _canonicalize_result(result):
    for key, row in result.items():
        for index, value in enumerate(row):
            row[index] = _finite(value, f"serialized strategy {key!r}")
