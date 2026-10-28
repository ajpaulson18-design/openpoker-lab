"""Suit-quotiented zero-delay CFR+ for the admitted shared four-street game.

The trainer stores one row per distinct global-suit orbit and verifies every
physical member contributes the same binary64 update before changing a Q row.
It is an opt-in research trajectory; it does not change the literal trainer.
"""
from array import array

from .equivariant_packed_cfr import (
    NUMERICAL_REDUCTION, _add, _canonicalize_result, _div, _finite, _mul,
    _sorted_chance_sum, _sub, _vector,
)
from .exact_selected_float_adapter import ExactSelectedFloatAdapter
from .river_tree import _Terminal
from .shared_public_topology import ChanceVertex, DecisionVertex, TerminalVertex
from .shared_topology_view import (
    ChanceCursor, DecisionCursor, SharedPublicView,
    MAX_HISTORY_LOOKUP_ENTRIES,
)
from .packed_operator_cfr import (
    MAX_ACTION_SLOTS, MAX_DENSE_DECISION_HAND_SLOTS, MAX_DEPTH,
    MAX_LAYOUT_LOOP_ENTRIES, MAX_PUBLIC_STATES,
)
from .suit_quotient_plan import _prefix


def layout_census_suit_quotient(view, plan, hand_counts, iterations):
    """Return the unchanged expanded-R layout receipt without retaining R rows."""
    _validate_inputs(view, plan, hand_counts, iterations)
    slots = rows = history_entries = history_bytes = 0
    for key, menu in plan.iter_rows():
        rows += 1
        slots += len(menu)
        history_entries += len(key[2])
        history_bytes += sum(len(token.encode("utf-8")) for token in key[2])

    states = dense = decisions = decision_width = lookup_work = 0
    maximum_actions = 1
    for occurrence in view.topology.iter_occurrences():
        states += 1
        if states > MAX_PUBLIC_STATES or occurrence.depth > MAX_DEPTH:
            raise ValueError("Shared logical state/depth capacity exceeded.")
        node = view.topology.vertices[occurrence.vertex_id]
        if isinstance(node, ChanceVertex):
            continue
        if isinstance(node, TerminalVertex):
            continue
        if not isinstance(node, DecisionVertex) or not node.child_ids:
            raise ValueError("Malformed shared decision cursor.")
        player, count = node.player, len(node.child_ids)
        maximum_actions = max(maximum_actions, count)
        hand_count = hand_counts[player]
        dense += hand_count
        decisions += 1
        decision_width += count + 1
        lookup_work += hand_count * (len(occurrence.history) + 3)
        if dense > MAX_DENSE_DECISION_HAND_SLOTS:
            raise ValueError("Shared logical decision/hand capacity exceeded.")
        # Authenticate that row streaming covers precisely this occurrence's
        # positive physical support, including rows with zero current reach.
        prefix = _prefix(occurrence.history)
        supported = plan.supported_hand_indices(prefix, player)
        if any(type(hand) is not int or not 0 <= hand < hand_count for hand in supported):
            raise ValueError("Suit plan support exceeds the admitted hand dimension.")

    vector_entries = 12 * sum(hand_counts) * (decision_width + states)
    loops = (iterations * (32 * slots + vector_entries) +
             8 * slots + 4 * dense + 4 * states)
    history_work = ((3 * iterations + 3 * maximum_actions + 16) * lookup_work +
                    8 * history_entries + history_bytes)
    if (slots > MAX_ACTION_SLOTS or loops > MAX_LAYOUT_LOOP_ENTRIES or
            history_work > MAX_HISTORY_LOOKUP_ENTRIES):
        raise ValueError("Shared requested layout/history loop capacity exceeded.")
    if array("d").itemsize != 8:
        raise RuntimeError("Shared packed storage requires eight-byte binary64 doubles.")
    from .equivariant_packed_cfr import equivariant_additional_census
    extra = equivariant_additional_census(view, hand_counts, iterations)
    legacy = {
        "version": "selected-shared-topology-packed-v1",
        "information_sets": rows,
        "action_slots": slots,
        "public_states": states,
        "decisions": decisions,
        "dense_decision_hand_slots": dense,
        "retained_dense_lookup_slots": 0,
        "semantic_row_lookup_entries": rows,
        "semantic_row_history_token_entries": history_entries,
        "semantic_row_history_token_bytes": history_bytes,
        "numeric_buffers": 4,
        "numeric_buffer_bytes": 4 * slots * 8,
        "dense_lookup_payload_bytes": 0,
        "row_offset_and_count_payload_bytes": 2 * rows * array("I").itemsize,
        "per_sweep_vector_entry_bound": vector_entries,
        "requested_layout_loop_entries": loops,
        "layout_loop_limit": MAX_LAYOUT_LOOP_ENTRIES,
        "history_lookup_work_entries": history_work,
        "history_lookup_work_limit": MAX_HISTORY_LOOKUP_ENTRIES,
        "maximum_actions": maximum_actions,
        "lazy_training_and_diagnostic_cursor_bound": (3 * iterations + 4) * states,
        "setup_occurrence_walks": 3,
        "retained_terminal_records": sum(t is not None for t in view._terminals),
        "scope": "Logical work and scalar payloads; original bridge construction, history keys, metadata, dictionaries, cursors and complete output remain separate memory costs.",
    }
    qslots = plan._receipt["quotient_action_slots"]
    return {
        "version": "suit-quotient-packed-cfr-layout-v1",
        "information_sets": len(plan.keys),
        "action_slots": qslots,
        "retained_dense_lookup_slots": 0,
        "semantic_row_lookup_entries": len(plan.keys),
        "retained_expanded_row_lookup_entries": 0,
        "numeric_buffers": 4,
        "numeric_buffer_bytes": 4 * qslots * 8,
        "q_offset_count_tuple_entries": 2 * len(plan.keys),
        "expanded_layout_equivalent": legacy,
        "expanded_information_rows": rows,
        "expanded_action_slots": slots,
        "quotient_information_rows": len(plan.keys),
        "quotient_action_slots": qslots,
        "q_numeric_buffer_bytes": 4 * qslots * 8,
        "expanded_policy_shadow_rows": rows,
        "expanded_policy_shadow_action_slots": slots,
        "member_checks": 2 * iterations * sum(plan.sizes),
        "iterations": iterations,
        "public_states": states,
        "decisions": decisions,
        "per_sweep_vector_entry_bound": vector_entries,
        "requested_layout_loop_entries": loops,
        "layout_loop_limit": MAX_LAYOUT_LOOP_ENTRIES,
        "history_lookup_work_entries": history_work,
        "history_lookup_work_limit": MAX_HISTORY_LOOKUP_ENTRIES,
        "maximum_actions": maximum_actions,
        "lazy_training_and_diagnostic_cursor_bound": (3 * iterations + 4) * states,
        "setup_occurrence_walks": 3,
        "retained_terminal_records": legacy["retained_terminal_records"],
        "scope": "Four Q binary64 buffers; expanded legacy layout is a nested scalar census. Tuple entries are logical counts, not array payload bytes or RSS.",
        "equivariant_version": "suit-equivariant-packed-reference-layout-v1",
        "numerical_reduction": NUMERICAL_REDUCTION,
        "equivariant_additional_admission": extra,
        "suit_quotient_version": "suit-quotient-cfrplus-v1",
    }


def _validate_inputs(view, plan, hand_counts, iterations):
    if type(view) is not SharedPublicView:
        raise TypeError("Suit quotient training requires the admitted SharedPublicView.")
    from .suit_quotient_plan import SuitQuotientPlan
    if type(plan) is not SuitQuotientPlan:
        raise TypeError("Suit quotient training requires an admitted SuitQuotientPlan.")
    plan.validate_owner()
    if plan.topology is not view.topology:
        raise ValueError("Suit quotient plan belongs to a different public topology.")
    owner = plan.validate_owner()
    if (type(hand_counts) not in (tuple, list) or len(hand_counts) != 2 or
            any(type(count) is not int or not 1 <= count <= 1326 for count in hand_counts)):
        raise ValueError("Suit quotient training requires two hand dimensions from 1 through 1,326.")
    if tuple(hand_counts) != tuple(owner.hand_counts):
        raise ValueError("Suit quotient plan owner has different hand dimensions.")
    if type(iterations) is not int or not 10 <= iterations <= 10_000:
        raise ValueError("Suit quotient training requires 10 through 10,000 iterations.")
    if plan._receipt["iterations"] != iterations:
        raise ValueError("Suit quotient training iteration count differs from plan admission.")


def train_suit_quotient(root, plan, iterations, *, operator, marginals,
                        return_receipt=False, shared_view=None):
    """Train CFR+ in Q storage while checking complete physical orbit updates."""
    if type(operator) is not ExactSelectedFloatAdapter:
        raise TypeError("Suit quotient training requires ExactSelectedFloatAdapter.")
    if type(shared_view) is not SharedPublicView:
        raise TypeError("Suit quotient training requires the admitted SharedPublicView.")
    if getattr(operator, "view", None) is not shared_view:
        raise ValueError("Suit quotient adapter does not belong to the supplied shared view.")
    if plan.validate_owner() is not operator.kernel:
        raise ValueError("Suit quotient plan and exact adapter have different kernel owners.")
    hand_counts = operator.hand_counts
    _validate_inputs(shared_view, plan, hand_counts, iterations)
    expected_root = shared_view.root
    if isinstance(expected_root, _Terminal):
        valid_root = root is expected_root
    else:
        valid_root = (type(root) is type(expected_root) and
                      type(root) in (ChanceCursor, DecisionCursor) and
                      root.view is shared_view and root.vertex_id == expected_root.vertex_id and
                      root.history == expected_root.history)
    if not valid_root:
        raise ValueError("Suit quotient root is not the admitted shared topology root.")

    # Preinitialize every potentially large object and closure so exceptions
    # keep no array alive through their traceback, even with cyclic GC disabled.
    census = regrets = sums = current = deltas = None
    seen = q_policy = result = None
    rematch = target_values = average = row_slots = responder = average_pass = None
    completed = False
    member_checks = 0
    try:
        census = _layout_census_validated(shared_view, plan, hand_counts, iterations)
        qslots = plan._receipt["quotient_action_slots"]
        if array("d").itemsize != 8:
            raise RuntimeError("Suit quotient storage requires binary64 doubles.")
        regrets = array("d", [0.0]) * qslots
        sums = array("d", [0.0]) * qslots
        current = array("d", [0.0]) * qslots
        deltas = array("d", [0.0]) * qslots
        seen = [0] * len(plan.keys)

        def row_slots(node):
            prefix = _prefix(node.history)
            supported = plan.supported_hand_indices(prefix, node.player)
            result_slots = [None] * hand_counts[node.player]
            for hand in supported:
                location = plan.locate((node.player, hand, node.history))
                if plan.menus[location[0]] != node.actions:
                    raise ValueError("Suit quotient orbit changed the ordered action menu.")
                result_slots[hand] = location
            return result_slots

        def rematch():
            for offset, count in zip(plan.offsets, plan.counts):
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
                return _vector(operator.values(node, opponent_reach, target, prefix),
                               hand_counts[target], "terminal callback")
            if not isinstance(node, DecisionCursor):
                raise TypeError("Unsupported node in suit quotient traversal.")
            player, count = node.player, len(node.children)
            slots = row_slots(node)
            probabilities = []
            for location in slots:
                if location is not None:
                    _, offset, _ = location
                    probabilities.append([_finite(current[offset + action], "strategy probability")
                                          for action in range(count)])
                else:
                    p = _div(1.0, float(count), "uniform absent-row probability")
                    probabilities.append([p] * count)
            if player == target:
                action_vectors = [target_values(child, prefix, opponent_reach, target)
                                  for child in node.children]
                value = [0.0] * hand_counts[target]
                for hand, location in enumerate(slots):
                    expected = 0.0
                    for action in range(count):
                        product = _mul(probabilities[hand][action], action_vectors[action][hand],
                                       "acting-player action value")
                        expected = _add(expected, product, "acting-player action dot product")
                    value[hand] = expected
                    if location is not None:
                        q, offset, bit = location
                        prior = seen[q]
                        if prior & bit:
                            raise ValueError("Duplicate Q member in CFR+ responder phase.")
                        for action in range(count):
                            difference = _sub(action_vectors[action][hand], expected,
                                              "counterfactual regret increment")
                            increment = _add(0.0, difference, "first orbit regret increment")
                            if prior == 0:
                                deltas[offset + action] = increment
                            else:
                                if deltas[offset + action].hex() != increment.hex():
                                    raise ValueError("Suit-orbit CFR+ regret increments differ across members.")
                        seen[q] |= bit
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

        # A member bit is used once per row; action deltas are staged in the
        # four-array workspace so no persistent regret changes precede checks.
        def responder(target):
            nonlocal member_checks
            active_q = [q for q, key in enumerate(plan.keys) if key[0] == target]
            for q in active_q:
                seen[q] = 0
                offset, count = plan.offsets[q], plan.counts[q]
                for action in range(count):
                    deltas[offset + action] = 0.0
            target_values(root, (), [1.0] * hand_counts[1 - target], target)
            for q in active_q:
                if seen[q] != plan.expected_masks[q]:
                    raise ValueError("Incomplete Q member coverage in CFR+ responder phase.")
                member_checks += plan.sizes[q]
            for q in active_q:
                offset, count = plan.offsets[q], plan.counts[q]
                for action in range(count):
                    increment = _finite(deltas[offset + action], "regret delta")
                    regret = _add(regrets[offset + action], increment, "CFR+ regret update")
                    _finite(regret if regret > 0.0 else 0.0, "prospective CFR+ regret")
            for q in active_q:
                offset, count = plan.offsets[q], plan.counts[q]
                for action in range(count):
                    increment = _finite(deltas[offset + action], "regret delta")
                    regret = _add(regrets[offset + action], increment, "CFR+ regret update")
                    regrets[offset + action] = regret if regret > 0.0 else 0.0

        def average(node, prefix, reach0, reach1, factor):
            if isinstance(node, _Terminal):
                return
            if isinstance(node, ChanceCursor):
                for card, child in node.branches.items():
                    average(child, prefix + (card,), reach0, reach1, factor)
                return
            if not isinstance(node, DecisionCursor):
                raise TypeError("Unsupported node in suit quotient averaging traversal.")
            player, count = node.player, len(node.children)
            slots = row_slots(node)
            for hand, location in enumerate(slots):
                if location is not None:
                    q, offset, bit = location
                    prior = seen[q]
                    if prior & bit:
                        raise ValueError("Duplicate Q member in averaging phase.")
                    own_mass = _finite(marginals[prefix][player][hand], "own marginal")
                    own_reach = _finite((reach0 if player == 0 else reach1)[hand], "own reach")
                    for action in range(count):
                        contribution = _mul(own_mass, own_reach, "own-reach weighted marginal")
                        contribution = _mul(contribution, current[offset + action], "average strategy mass")
                        contribution = _mul(contribution, factor, "iteration-weighted average")
                        contribution = _add(0.0, contribution, "first orbit average contribution")
                        if prior == 0:
                            deltas[offset + action] = contribution
                        elif deltas[offset + action].hex() != contribution.hex():
                            raise ValueError("Suit-orbit average contributions differ across members.")
                    seen[q] |= bit
            for action, child in enumerate(node.children):
                own = reach0 if player == 0 else reach1
                changed = []
                for hand, location in enumerate(slots):
                    probability = (_finite(current[location[1] + action], "strategy probability")
                        if location is not None else
                        _div(1.0, float(count), "uniform absent-row average probability"))
                    changed.append(_mul(own[hand], probability, "own reach update"))
                average(child, prefix, changed if player == 0 else reach0,
                        changed if player == 1 else reach1, factor)

        def average_pass(factor):
            for q in range(len(seen)):
                seen[q] = 0
            for offset, count in zip(plan.offsets, plan.counts):
                for action in range(count):
                    deltas[offset + action] = 0.0
            average(root, (), [1.0] * hand_counts[0], [1.0] * hand_counts[1], factor)
            if tuple(seen) != plan.expected_masks:
                raise ValueError("Incomplete Q member coverage in averaging phase.")
            for offset, count in zip(plan.offsets, plan.counts):
                for action in range(count):
                    _add(sums[offset + action], _finite(deltas[offset + action],
                        "average delta"), "average-strategy accumulation")
            for offset, count in zip(plan.offsets, plan.counts):
                for action in range(count):
                    sums[offset + action] = _add(sums[offset + action], _finite(
                        deltas[offset + action], "average delta"),
                        "average-strategy accumulation")

        for iteration in range(1, iterations + 1):
            rematch()
            responder(0)
            rematch()
            responder(1)
            rematch()
            average_pass(float(iteration))
            member_checks += sum(plan.sizes)

        q_policy = {}
        for q, key in enumerate(plan.keys):
            offset, count = plan.offsets[q], plan.counts[q]
            total = 0.0
            for action in range(count):
                total = _add(total, sums[offset + action], "average output normalizer")
            if total:
                q_policy[key] = [_div(_finite(sums[offset + action], "average output"), total,
                                      "average output probability") for action in range(count)]
            else:
                q_policy[key] = [_div(1.0, float(count), "uniform average output") for _ in range(count)]
        _canonicalize_result(q_policy)
        if member_checks != census["member_checks"]:
            raise RuntimeError(f"Suit quotient member-check receipt differs from admitted traversal count: {member_checks} != {census['member_checks']}.")
        if any(len(buffer) != qslots for buffer in (regrets, sums, current, deltas)):
            raise RuntimeError("Suit quotient numeric buffer length differs from admitted Q slots.")
        # Drop all Q numeric workspaces before expanded result dictionaries and
        # lists are streamed from physical support.
        regrets = sums = current = deltas = seen = None
        rematch = target_values = average = row_slots = responder = average_pass = None
        result = {}
        for key, _menu in plan.iter_rows():
            q, _offset, _bit = plan.locate(key)
            result[key] = list(q_policy[plan.keys[q]])
        _canonicalize_result(result)
        completed = True
    finally:
        rematch = target_values = average = row_slots = responder = average_pass = None
        regrets = sums = current = deltas = seen = None
        if q_policy is not None:
            q_policy.clear()
        q_policy = None
        if not completed:
            result = None
    return (result, census) if return_receipt else result


def _layout_census_validated(view, plan, hand_counts, iterations):
    # Keep the validation order identical to the public census API.
    return layout_census_suit_quotient(view, plan, hand_counts, iterations)
