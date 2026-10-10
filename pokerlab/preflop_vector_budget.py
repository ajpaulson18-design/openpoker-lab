"""Conservative, data-dependent admission bounds for vector preflop work.

    The counters conservatively envelope modeled vector-backend validation,
    aggregation, row setup/normalization, training, and diagnostic loops plus
    dense reference slots. They are not bytecode counts, elapsed-time estimates,
    or process-RSS predictions. World enumeration and tree construction remain
    governed by their existing independent guards. This estimator is separate
    from trainer/evaluator traversal helpers.
"""

from collections.abc import Mapping

from .river_tree import _Node, _Terminal


VECTOR_BUDGET_VERSION = "preflop-public-vector-budget-v1"
MAX_PREFIX_EDGES = 250_000
MAX_DENSE_PREFIX_SLOTS = 2_000_000
MAX_INFO_ACTION_SLOTS = 1_000_000
MAX_TOTAL_LOOP_ENTRIES = 500_000_000
_MAX_HAND_INDEX = 1326


def estimate_vector_budget(root, worlds, infos, iterations, algorithm, *, chance_type, averaging_delay=0, checkpoint_interval=None):
    """Return JSON-safe conservative loop/allocation bounds for vector work.

    Bounds include one aggregation for training and one for requested vector
    diagnostics when information sets exist. No-information-set training is
    skipped, so it has no trainer aggregation or iterative work; diagnostics
    still receive one aggregation and their complete tree traversals.
    """
    if type(iterations) is not int or iterations < 1:
        raise ValueError("iterations must be a positive integer")
    if algorithm not in ("vanilla", "dcfr", "cfrplus"):
        raise ValueError("algorithm must be vanilla, dcfr, or cfrplus")
    if type(averaging_delay) is not int or not 0 <= averaging_delay < iterations:
        raise ValueError("averaging_delay must be an integer in [0, iterations)")
    if averaging_delay and algorithm != "cfrplus":
        raise ValueError("positive averaging_delay requires cfrplus")
    if checkpoint_interval is not None:
        if type(checkpoint_interval) is not int or checkpoint_interval < 1:
            raise ValueError("checkpoint interval must be a positive integer")
        if algorithm != "cfrplus" or not averaging_delay:
            raise ValueError("checkpoint admission requires positive-delay CFR+")
    if not isinstance(chance_type, type):
        raise TypeError("chance_type must be a node class")
    if not isinstance(worlds, (tuple, list)) or not worlds:
        raise ValueError("worlds must be a nonempty sized sequence")
    if not isinstance(infos, Mapping):
        raise TypeError("infos must be a mapping")

    max_indices = [-1, -1]
    for world in worlds:
        if not isinstance(world, (tuple, list)) or len(world) < 4:
            raise ValueError("each world needs two hands, mass, and sign")
        for player in (0, 1):
            hand = world[player]
            if type(hand) is not int or not 0 <= hand < _MAX_HAND_INDEX:
                raise ValueError("world hand index is outside the 1,326-combo range")
            max_indices[player] = max(max_indices[player], hand)
        if not isinstance(world[4:], (tuple, list)):
            raise ValueError("world future cards must be a sequence")
        try:
            hash(tuple(world[4:]))
        except TypeError as exc:
            raise ValueError("world future-card prefixes must be hashable") from exc
    infos_action_slots = 0
    for key, actions in infos.items():
        if (not isinstance(key, tuple) or len(key) != 3 or
                type(key[0]) is not int or key[0] not in (0, 1) or
                type(key[1]) is not int or not 0 <= key[1] < _MAX_HAND_INDEX or
                not isinstance(key[2], tuple) or type(actions) is not int or actions < 1):
            raise ValueError("infos must map (player, hand, history) to positive action counts")
        infos_action_slots += actions
        if infos_action_slots > MAX_INFO_ACTION_SLOTS:
            raise ValueError("Vector budget information-set action slots exceed 1,000,000")
        max_indices[key[0]] = max(max_indices[key[0]], key[1])

    # Build coverage counts only after the action-slot cap has passed.
    info_hands_by_node = {}
    for key in infos:
        marker = (key[0], key[2])
        info_hands_by_node[marker] = info_hands_by_node.get(marker, 0) + 1
    hand_counts = tuple(index + 1 for index in max_indices)
    if min(hand_counts) < 1:
        raise ValueError("both players need at least one hand index")
    hand_sum = sum(hand_counts)

    # Sparse prefix/pair census. Reserve every unique edge before adding it.
    prefix_pairs = {}
    aggregation_entries = 0
    prefix_edges = 0
    for world in worlds:
        future = tuple(world[4:])
        pair = (world[0], world[1])
        aggregation_entries += len(future) + 1
        for length in range(len(future) + 1):
            prefix = future[:length]
            row = prefix_pairs.get(prefix)
            if row is None or pair not in row:
                if prefix_edges >= MAX_PREFIX_EDGES:
                    raise ValueError("Vector budget prefix edges exceed 250,000")
                if row is None:
                    if (len(prefix_pairs) + 1) * hand_sum > MAX_DENSE_PREFIX_SLOTS:
                        raise ValueError("Vector budget dense prefix slots exceed 2,000,000")
                    row = set()
                    prefix_pairs[prefix] = row
                row.add(pair)
                prefix_edges += 1
    prefix_count = len(prefix_pairs)
    dense_prefix_slots = prefix_count * hand_sum
    if dense_prefix_slots > MAX_DENSE_PREFIX_SLOTS:
        raise ValueError("Vector budget dense prefix slots exceed 2,000,000")
    if prefix_edges > MAX_PREFIX_EDGES:
        raise ValueError("Vector budget prefix edges exceed 250,000")

    counts = {"decision_nodes": 0, "chance_nodes": 0, "terminal_nodes": 0,
              "action_edges": 0, "chance_edges": 0,
              "terminal_prefix_edge_visits": 0,
              "decision_dense_hand_action_cells": 0,
              "diagnostic_missing_policy_lookups": 0,
              "diagnostic_uniform_fallback_slots": 0,
              "visitor_loop_entries": 0,
              "average_pass_loop_entries": 0}
    active = set()

    def walk(node, prefix):
        ident = id(node)
        if ident in active:
            raise ValueError("public tree contains a cycle")
        active.add(ident)
        try:
            if isinstance(node, chance_type):
                branches = getattr(node, "branches", None)
                if not isinstance(branches, Mapping):
                    raise ValueError("chance nodes need a branch mapping")
                counts["chance_nodes"] += 1
                counts["chance_edges"] += len(branches)
                counts["visitor_loop_entries"] += 8 + hand_sum + len(branches) * (hand_sum + 4)
                counts["average_pass_loop_entries"] += 4 + len(branches) * 2
                for card, child in branches.items():
                    walk(child, prefix + (card,))
            elif isinstance(node, _Terminal):
                counts["terminal_nodes"] += 1
                edge_count = len(prefix_pairs.get(prefix, ()))
                counts["terminal_prefix_edge_visits"] += edge_count
                counts["visitor_loop_entries"] += 8 + hand_sum + 2 * edge_count
                counts["average_pass_loop_entries"] += 4
            elif isinstance(node, _Node):
                if (node.player not in (0, 1) or len(node.actions) != len(node.children)
                        or not node.children):
                    raise ValueError("decision action and child counts must match")
                counts["decision_nodes"] += 1
                action_count = len(node.children)
                counts["action_edges"] += action_count
                counts["decision_dense_hand_action_cells"] += hand_counts[node.player] * action_count
                own_hands = hand_counts[node.player]
                opponent_hands = hand_counts[1 - node.player]
                counts["visitor_loop_entries"] += (
                    8 + 6 * own_hands + 3 * opponent_hands +
                    action_count * (4 * own_hands + opponent_hands + 4)
                )
                counts["average_pass_loop_entries"] += (
                    4 + 2 * own_hands + action_count * (2 * own_hands + 4)
                )
                present_hands = info_hands_by_node.get((node.player, node.history), 0)
                if present_hands > hand_counts[node.player]:
                    raise ValueError("information-set hand count exceeds dense hand dimension")
                missing_lookups = 2 * action_count * (hand_counts[node.player] - present_hands)
                counts["diagnostic_missing_policy_lookups"] += missing_lookups
                counts["diagnostic_uniform_fallback_slots"] += missing_lookups * action_count
                for child in node.children:
                    walk(child, prefix)
            else:
                raise TypeError("tree contains an unsupported public node")
        finally:
            active.remove(ident)

    try:
        walk(root, ())
    finally:
        # Break the recursive closure cycle promptly, including on bad trees.
        walk = None
    tree_visits = sum(counts[key] for key in
                      ("decision_nodes", "chance_nodes", "terminal_nodes"))
    terminal_edges = counts["terminal_prefix_edge_visits"]
    action_edges = counts["action_edges"]
    chance_edges = counts["chance_edges"]

    # Conservative node envelopes: chance=8+Hsum+B*(Hsum+4); terminal=
    # 8+Hsum+2E; decision=8+6H+3J+A*(4H+J+4). These include loop entries
    # and exits, dense vector setup/access, action reach/value work, and sparse
    # terminal edges. Target-player sweeps are bounded by the full visitor.
    visitor_bound = counts["visitor_loop_entries"]
    # Average-only pass envelopes: chance=4+2B; terminal=4; decision=
    # 4+2H+A*(2H+4), covering own-reach/action row accumulation.
    average_only_bound = counts["average_pass_loop_entries"]
    regret_matching_bound = len(infos) + infos_action_slots * 3
    regret_update_bound = len(infos) * 3 + infos_action_slots * 3

    training_setup_entries = 0
    if not infos:
        training_traversals_per_iteration = 0
        per_iteration = 0
        trainer_aggregation_count = 0
    elif algorithm == "cfrplus":
        training_traversals_per_iteration = 3
        # Two target traversals, an average-only traversal, three policy
        # rematches, two positive-regret updates, and average row writes.
        per_iteration = (2 * visitor_bound + average_only_bound +
                         3 * regret_matching_bound +
                         2 * regret_update_bound + 1)
        training_setup_entries = 4 * len(infos) + 4 * infos_action_slots
        trainer_aggregation_count = 1
    else:
        training_traversals_per_iteration = 1
        # Full visitor, one regret match, delta initialization/update,
        # averaging, plus DCFR's per-action discount work (covered by the
        # shared regret-update envelope for vanilla too).
        per_iteration = (visitor_bound + regret_matching_bound +
                         regret_update_bound + 1)
        training_setup_entries = 4 * len(infos) + 4 * infos_action_slots
        trainer_aggregation_count = 1
    training_loop_entries = training_setup_entries + iterations * per_iteration
    if algorithm == "cfrplus" and averaging_delay and infos:
        # Initial full match; target partitions together rematch each row once
        # per sweep. Only positive-weight averages traverse. The update
        # envelope remains conservative for the two target-player passes.
        training_setup_entries += 4 * len(infos)
        training_loop_entries = (
            training_setup_entries + regret_matching_bound +
            iterations * (2 * visitor_bound + regret_matching_bound +
                          2 * regret_update_bound + 4) +
            (iterations - averaging_delay) * average_only_bound
        )
        training_traversals_per_iteration = None

    # The public evaluator does one profile and two responder traversals. Its
    # policy() lookup can synthesize a dense fallback row for unreachable
    # hands; charge every dense hand/action lookup even when absent from infos.
    # Each missing policy lookup eagerly constructs default marginal arrays
    # for both players, even when the prefix exists. It occurs in profile and
    # once in the responder traversal where this node's player is opponent.
    missing_policy_lookups = counts["diagnostic_missing_policy_lookups"]
    diagnostics_fallback_slots = missing_policy_lookups * hand_sum
    diagnostics_setup_entries = (2 * len(infos) + 3 * infos_action_slots +
                                 missing_policy_lookups * 2)
    diagnostics_loop_entries = (3 * visitor_bound + diagnostics_fallback_slots +
                                counts["diagnostic_uniform_fallback_slots"] +
                                2 * missing_policy_lookups + diagnostics_setup_entries)
    checkpoint_count = ((iterations + checkpoint_interval - 1) // checkpoint_interval
                        if checkpoint_interval is not None and infos else 0)
    # Every callback may normalize a fresh policy, including zero-weight
    # epochs. The solver evaluates only completed positive-average epochs.
    # Count those scheduled diagnostics independently, plus one conservative
    # final evaluation even when its checkpoint will actually be reused.
    checkpoint_diagnostics = (checkpoint_count - averaging_delay // checkpoint_interval
                              if checkpoint_count else 0)
    snapshot_bound = checkpoint_count * (2 * len(infos) + 4 * infos_action_slots)
    checkpoint_orchestration_bound = 16 * checkpoint_count
    training_loop_entries += snapshot_bound + checkpoint_orchestration_bound
    diagnostic_evaluations = checkpoint_diagnostics + 1
    diagnostics_loop_entries *= diagnostic_evaluations
    diagnostics_setup_entries *= diagnostic_evaluations
    diagnostics_fallback_slots *= diagnostic_evaluations
    # Prefix aggregation repeats for diagnostics. It validates worlds/infos,
    # reserves sparse edges, finalizes every edge, and allocates dense marginal
    # entries once for each public prefix.
    aggregation_count = trainer_aggregation_count + diagnostic_evaluations
    aggregation_loop_entries = aggregation_count * (
        aggregation_entries + prefix_edges * 2 + dense_prefix_slots +
        4 * len(worlds) + len(infos)
    )
    total_loop_entries = (training_loop_entries + diagnostics_loop_entries +
                          aggregation_loop_entries)
    if total_loop_entries > MAX_TOTAL_LOOP_ENTRIES:
        raise ValueError("Vector budget estimated loop entries exceed 500,000,000")

    result = {
        "budget_version": ("preflop-public-vector-convergence-budget-v3"
                           if checkpoint_interval is not None else
                           "preflop-public-vector-delayed-budget-v2"
                           if averaging_delay else VECTOR_BUDGET_VERSION),
        "world_count": len(worlds),
        "iterations": iterations,
        "algorithm": algorithm,
        "hand_counts": list(hand_counts),
        "public_prefixes": prefix_count,
        "prefix_edges": prefix_edges,
        "prefix_edge_limit": MAX_PREFIX_EDGES,
        "dense_prefix_slots": dense_prefix_slots,
        "dense_prefix_slot_limit": MAX_DENSE_PREFIX_SLOTS,
        "information_sets": len(infos),
        "information_set_action_slots": infos_action_slots,
        "information_set_action_slot_limit": MAX_INFO_ACTION_SLOTS,
        "decision_nodes": counts["decision_nodes"],
        "chance_nodes": counts["chance_nodes"],
        "terminal_nodes": counts["terminal_nodes"],
        "action_edges": action_edges,
        "chance_edges": chance_edges,
        "terminal_prefix_edge_visits": terminal_edges,
        "diagnostic_missing_policy_lookups": missing_policy_lookups,
        "aggregation_count": aggregation_count,
        "aggregation_loop_entries_upper_bound": aggregation_loop_entries,
        "training_traversals_per_iteration": training_traversals_per_iteration,
        "visitor_loop_entries_per_traversal_upper_bound": visitor_bound,
        "training_loop_entries_upper_bound": training_loop_entries,
        "training_setup_loop_entries_upper_bound": training_setup_entries,
        "diagnostics_loop_entries_upper_bound": diagnostics_loop_entries,
        "diagnostics_setup_loop_entries_upper_bound": diagnostics_setup_entries,
        "diagnostics_dense_fallback_slot_upper_bound": diagnostics_fallback_slots,
        "diagnostics_uniform_fallback_slot_upper_bound": counts["diagnostic_uniform_fallback_slots"] * diagnostic_evaluations,
        "total_loop_entries_upper_bound": total_loop_entries,
        "total_loop_entry_limit": MAX_TOTAL_LOOP_ENTRIES,
        "loop_entry_scope": (
            "Conservative modeled vector-backend validation, aggregation, row setup/normalization, "
            "training, and diagnostic loop envelope; not bytecode count, runtime, or process RSS. "
            "World enumeration and tree construction use separate existing guards."
        ),
    }
    if averaging_delay:
        result.update({
            "averaging_delay": averaging_delay,
            "training_regret_passes": 2 * iterations if infos else 0,
            "training_average_passes": iterations - averaging_delay if infos else 0,
            "training_policy_match_rows": (iterations + 1) * len(infos) if infos else 0,
        })
    if checkpoint_interval is not None:
        result.update({
            "checkpoint_interval": checkpoint_interval,
            "checkpoint_count_upper_bound": checkpoint_count,
            "checkpoint_snapshot_loop_entries_upper_bound": snapshot_bound,
            "checkpoint_orchestration_loop_entries_upper_bound": checkpoint_orchestration_bound,
            "checkpoint_diagnostics_upper_bound": checkpoint_diagnostics,
            "diagnostic_evaluations_upper_bound": diagnostic_evaluations,
            "convergence_budget_scope": "Full requested iteration ceiling, every scheduled snapshot, every positive-average exact check and one extra conservative final diagnostic; early stopping never bypasses admission.",
        })
    return result
