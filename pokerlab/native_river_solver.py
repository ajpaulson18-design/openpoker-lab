"""Explicit source-built native CFR+ adapter for fixed-board river research.

This API is intentionally separate from the production solver APIs. Python
owns the game, physical worlds, diagnostics, and serialized policy contract;
the native fixed-street trainer receives only a validated public tree and
weighted private-hand pairs.
"""

import math

from . import native_fixed_street
from .cards import cards
from .postflop_solver import (
    _MAX_CANDIDATE_HAND_ITERATIONS,
    _MAX_WORLD_ITERATIONS,
    _MAX_PUBLIC_NODES,
    _MAX_PUBLIC_STATES,
    _build_postflop_tree,
    _enumerate_worlds,
    _prefix_hand_index,
)
from .public_cfr import MAX_PREFIX_EDGES, _aggregate_prefixes, _validate_inputs
from .public_diagnostics import evaluate_profile
from .river_config import RiverConfig
from .river_tail_adapter import MAX_WORLD_NODE_WORK as _RIVER_WORLD_NODE_WORK
from .turn_tail_adapter import (
    MAX_DENSE_HAND_STATE_PASS_WORK,
    MAX_INFO_ACTION_SLOTS,
    _config,
)
from .postflop_solver import _Chance


SOLVER_VERSION = "research-native-river-cfrplus-v1"
EXECUTION_BACKEND = "native-fixed-street-public-batched-river"


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def solve_native_river(board, oop_range, ip_range, config=None, *,
                       iterations=1000, build_directory=None):
    """Solve one configured fixed-board river game with explicit native CFR+.

    This research API accepts a complete five-card board and 10 through 10,000
    requested CFR+ iterations. The full requested budget is admitted before
    looking up the explicitly built native executable. No fallback or implicit
    compilation occurs. It makes no accuracy or performance promise.
    """
    if type(iterations) is not int or not 10 <= iterations <= 10_000:
        raise ValueError("iterations must be an integer from 10 through 10,000.")
    if build_directory is None:
        raise ValueError("An explicit native training build_directory is required.")

    board = cards(board)
    if len(board) != 5:
        raise ValueError("Native river solving requires exactly five board cards.")
    config = _config(config, "config") or RiverConfig()
    native_fixed_street.validate_backend("native", build_directory)

    # This existing enumerator charges candidate pairs and worlds against the
    # complete requested T before allocating/ranking the resulting worlds.
    hands, worlds, selected, pair_count = _enumerate_worlds(
        board, oop_range, ip_range, iterations=iterations)
    _need(not selected, "A river-start game cannot contain future runouts.")

    public_counts = {}
    root, nodes, chance_nodes, visited_nodes, _ = _build_postflop_tree(
        board, config, worlds=worlds, allocation_counts=public_counts)
    if chance_nodes:
        raise ValueError("A fixed-board native river tree cannot contain chance nodes.")
    if len(worlds) * visited_nodes * iterations * 3 > _RIVER_WORLD_NODE_WORK:
        raise ValueError("River solver exceeds 30 million world-node iterations.")
    if public_counts["total"] > _MAX_PUBLIC_STATES or len(nodes) > _MAX_PUBLIC_NODES:
        raise ValueError("River solver exceeds existing public-tree limits.")

    legal_hands = _prefix_hand_index(worlds)
    info_action_slots = sum(
        len(node.actions) * len(legal_hands.get((player, ()), ()))
        for (player, _history), node in nodes.items())
    if info_action_slots > MAX_INFO_ACTION_SLOTS:
        raise ValueError("River solver exceeds 1,000,000 information-set action slots.")

    dense_hand_work = max(map(len, hands)) * public_counts["total"] * (3 * iterations + 3)
    if dense_hand_work > MAX_DENSE_HAND_STATE_PASS_WORK:
        raise ValueError("River solver exceeds 30 million dense hand-state-pass operations.")

    infos, metadata = {}, {}
    for (player, history), node in nodes.items():
        for hand_index in sorted(legal_hands.get((player, ()), ())):
            key = (player, hand_index, history)
            infos[key] = len(node.actions)
            metadata[key] = node

    # Retain the historical prefix-edge admission even though native training
    # does not consume prefix rows. This is structural work only and remains a
    # separately disclosed charge.
    _, hand_counts = _validate_inputs(worlds, infos, iterations, "cfrplus",
                                      config.pot, _Chance)
    edges, _ = _aggregate_prefixes(worlds, hand_counts)
    prefix_edges = sum(len(row) for row in edges.values())
    if prefix_edges > MAX_PREFIX_EDGES:
        raise ValueError("River solver exceeds 250,000 prefix/hand edges.")

    # Native public-batched worlds use signed mass. Keep the physical worlds
    # intact for Python diagnostics and serialize only this transformed copy.
    native_worlds = [
        (h0, h1, mass, mass * sign)
        for h0, h1, mass, sign in worlds
    ]
    native_hand_counts = tuple(
        len({world[player] for world in native_worlds}) for player in (0, 1)
    )
    native_admission = native_fixed_street.admit_native_shape(
        public_counts["total"], len(native_worlds), info_action_slots,
        iterations, "cfrplus", reduction="public-batched",
        hand_counts=native_hand_counts,
    )
    averages, native_receipt = native_fixed_street.train_native_fixed_street(
        root, native_worlds, infos, iterations, "cfrplus", pot=config.pot,
        build_directory=build_directory, reduction="public-batched",
    )
    # Defend the API boundary against a trainer receipt for a different request.
    if native_receipt.get("admission", {}).get("requested_iterations") != iterations:
        raise RuntimeError("Native trainer receipt does not match full requested iterations.")
    if native_receipt.get("admission") != native_admission:
        raise RuntimeError("Native trainer admission changed during the solve.")

    value, br_oop, br_ip = evaluate_profile(
        root, worlds, averages, pot=config.pot, chance_type=_Chance)
    if not all(math.isfinite(number) for number in (value, br_oop, br_ip)):
        raise ValueError("Native river diagnostics must be finite.")
    tolerance = 1e-10 * max(1.0, config.pot, abs(value), abs(br_oop), abs(br_ip))
    if br_oop < value - tolerance or br_ip < -value - tolerance:
        raise RuntimeError("Best-response diagnostics violate legal response bounds.")

    gain_oop = max(0.0, br_oop - value)
    gain_ip = max(0.0, br_ip + value)
    nash_conv = gain_oop + gain_ip
    exploitability = nash_conv / 2.0
    if not all(math.isfinite(number) for number in
               (gain_oop, gain_ip, nash_conv, exploitability)):
        raise ValueError("Native river derived diagnostics must be finite.")

    rows = []
    for player, hand_index, history in sorted(infos):
        node = metadata[(player, hand_index, history)]
        rows.append({
            "player": "oop" if player == 0 else "ip",
            "hand": "".join(hands[player][hand_index]),
            "street": "river", "board": list(board), "history": list(history),
            "actions": [{
                "name": action.name, "amount": action.amount,
                "raise_to": action.raise_to, "history_key": action.token,
                "probability": probability,
            } for action, probability in zip(node.actions, averages[(player, hand_index, history)])],
        })

    world_work = len(worlds) * visited_nodes * iterations * 3
    admission_summary = {
        "requested_iterations": iterations,
        "requested_regret_passes": 2 * iterations,
        "requested_average_passes": iterations,
        "requested_total_traversal_passes": 3 * iterations,
        "native_admission": native_admission,
        "historical_river_limits": {
            "candidate_pair_iterations": _MAX_CANDIDATE_HAND_ITERATIONS,
            "world_iterations": _MAX_WORLD_ITERATIONS,
            "world_node_work": _RIVER_WORLD_NODE_WORK,
            "dense_hand_state_pass_work": MAX_DENSE_HAND_STATE_PASS_WORK,
            "information_action_slots": MAX_INFO_ACTION_SLOTS,
            "prefix_hand_edges": MAX_PREFIX_EDGES,
            "public_nodes": _MAX_PUBLIC_NODES,
            "public_states": _MAX_PUBLIC_STATES,
        },
        "note": "Historical river guards and native envelope are separately admitted; no combined native complete-solve bound is claimed.",
    }
    return {
        "method": "Native fixed-tree CFR+ river",
        "algorithm": "cfrplus",
        "solver_version": SOLVER_VERSION,
        "strategy_schema": "postflop-strategy-v1",
        "backend": "exact-public-chance-tree",
        "execution_backend": EXECUTION_BACKEND,
        "diagnostics_backend": "public-batched-python",
        "board": list(board),
        "config": config.to_dict(),
        "street_configs": {"river": config.to_dict()},
        "turn_config": None,
        "river_config": config.to_dict(),
        "runouts": [],
        "reachable_runouts": [],
        "runout_mode": "none",
        "chance_note": "Compatible private-pair range products normalized once; board is complete.",
        "iterations": iterations,
        "requested_iterations": iterations,
        "discard": 0,
        "source_iteration_window": [1, iterations],
        "averaged_sweeps": iterations,
        "average_weight_sum": iterations * (iterations + 1) // 2,
        "average_schedule": "native-linear-completed-sweep-own-reach",
        "update_schedule": "alternating-oop-then-ip",
        "requested_regret_passes": 2 * iterations,
        "requested_average_passes": iterations,
        "requested_total_traversal_passes": 3 * iterations,
        "deals": pair_count,
        "compatible_pairs": pair_count,
        "worlds": len(worlds),
        "worlds_materialized": len(worlds),
        "info_sets": len(infos),
        "public_nodes": len(nodes),
        "public_states": public_counts["total"],
        "terminal_nodes": public_counts["terminal"],
        "chance_nodes": chance_nodes,
        "world_traversal_nodes": visited_nodes,
        "tree_actions": sum(len(node.actions) for node in nodes.values()),
        "public_state_limit": _MAX_PUBLIC_STATES,
        "public_node_limit": _MAX_PUBLIC_NODES,
        "public_batch_edge_limit": MAX_PREFIX_EDGES,
        "resource_usage": {
            "candidate_hand_pair_iterations": len(hands[0]) * len(hands[1]) * iterations,
            "candidate_hand_pair_iteration_limit": _MAX_CANDIDATE_HAND_ITERATIONS,
            "world_iterations": len(worlds) * iterations,
            "world_iteration_limit": _MAX_WORLD_ITERATIONS,
            "full_requested_world_node_work": world_work,
            "full_requested_world_node_work_limit": _RIVER_WORLD_NODE_WORK,
            "full_requested_dense_hand_state_pass_work": dense_hand_work,
            "full_requested_dense_hand_state_pass_work_limit": MAX_DENSE_HAND_STATE_PASS_WORK,
            "info_action_slots": info_action_slots,
            "info_action_slots_limit": MAX_INFO_ACTION_SLOTS,
            "prefix_hand_edges": prefix_edges,
            "prefix_hand_edge_limit": MAX_PREFIX_EDGES,
            "native_training_admission": native_admission,
            "admission_summary": admission_summary,
            "diagnostics": "Python public-batched metrics are computed after native training; diagnostic work is outside native training admission.",
        },
        "pot": config.pot,
        "effective_stack": config.to_dict()["effective_stack"],
        "value_oop": value,
        "value_ip": -value,
        "oop_best_response_value": br_oop,
        "ip_best_response_value": br_ip,
        "oop_best_response_gain": gain_oop,
        "ip_best_response_gain": gain_ip,
        "nash_conv": nash_conv,
        "exploitability": exploitability,
        "scope": "Research profile for a configured heads-up river game; no preflop, multiway play, rake, or general exact-equilibrium claim.",
        "diagnostic_provenance": "Metrics recomputed in Python from the native CFR+ policy using the original physical worlds; numeric convergence diagnostics are not an exact equilibrium certificate.",
        "training_calls": 1,
        "native_training": native_receipt,
        "strategy": rows,
    }
