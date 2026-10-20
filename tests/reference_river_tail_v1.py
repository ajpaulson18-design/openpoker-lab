"""Opt-in research adapter for original-weight CFR+ tails on river starts.

This module reuses the established postflop tree/world helpers and the local
direct-tail accumulator. It leaves all existing solver entry points/defaults
untouched and makes no general convergence or equilibrium claim.
"""
import math

from pokerlab.cards import cards
from pokerlab.postflop_solver import (
    _MAX_PUBLIC_NODES,
    _MAX_PUBLIC_STATES,
    _MAX_WORLD_NODE_WORK,
    _Chance,
    _build_postflop_tree,
    _enumerate_worlds,
    _prefix_hand_index,
)
from pokerlab.public_cfr import MAX_PREFIX_EDGES, _aggregate_prefixes, _validate_inputs
from pokerlab.public_diagnostics import evaluate_profile
from pokerlab.river_config import RiverConfig
from pokerlab.turn_tail_adapter import (
    MAX_DENSE_HAND_STATE_PASS_WORK,
    MAX_INFO_ACTION_SLOTS,
    MAX_ITERATIONS,
    _config,
    _train_original_weight_tail,
)


SOLVER_VERSION = "research-river-tail-adapter-v1"
MAX_WORLD_NODE_WORK = _MAX_WORLD_NODE_WORK


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def solve_river_tail(board, oop_range, ip_range, config=None, *,
                     iterations=1000, discard=0):
    """Train a configured fixed-board river CFR+ original-weight tail.

    This research-only API supports materialized public-vector CFR+ on an
    exactly five-card board. `iterations` is the full requested budget and
    `discard` excludes earlier completed sweeps from the returned average.
    Each retained sweep uses its original linear weight `t`, not `t-discard`.
    """
    if type(iterations) is not int or not 10 <= iterations <= MAX_ITERATIONS:
        raise ValueError("iterations must be an integer from 10 through 10,000.")
    if type(discard) is not int or not 0 <= discard < iterations:
        raise ValueError("discard must be an integer in [0, iterations).")
    board = cards(board)
    if len(board) != 5:
        raise ValueError("River tail solving requires exactly five board cards.")
    config = _config(config, "config") or RiverConfig()

    # Existing enumeration receives full requested T, preserving candidate and
    # world guards even when only the final sweep is retained.
    hands, worlds, selected, pair_count = _enumerate_worlds(
        board, oop_range, ip_range, iterations=iterations)
    _need(not selected, "A river-start game cannot contain future runouts.")

    public_counts = {}
    root, nodes, chance_nodes, visited_nodes, _ = _build_postflop_tree(
        board, config, worlds=worlds, allocation_counts=public_counts)
    if len(worlds) * visited_nodes * iterations * 3 > MAX_WORLD_NODE_WORK:
        raise ValueError("Postflop solver exceeds 30 million world-node iterations.")
    if public_counts["total"] > _MAX_PUBLIC_STATES or len(nodes) > _MAX_PUBLIC_NODES:
        raise ValueError("River tail exceeds the existing public-tree limits.")

    legal_hands = _prefix_hand_index(worlds)
    info_action_slots = sum(
        len(node.actions) * len(legal_hands.get((player, ()), ()))
        for (player, _history), node in nodes.items())
    if info_action_slots > MAX_INFO_ACTION_SLOTS:
        raise ValueError("River tail exceeds 1,000,000 information-set action slots.")

    dense_hand_work = max(map(len, hands)) * public_counts["total"] * (3 * iterations + 3)
    if dense_hand_work > MAX_DENSE_HAND_STATE_PASS_WORK:
        raise ValueError("River tail exceeds 30 million dense hand-state-pass operations.")

    infos, metadata = {}, {}
    for (player, history), node in nodes.items():
        for hand_index in sorted(legal_hands.get((player, ()), ())):
            key = (player, hand_index, history)
            infos[key] = len(node.actions)
            metadata[key] = node

    _, hand_counts = _validate_inputs(worlds, infos, iterations, "cfrplus",
                                      config.pot, _Chance)
    edges, marginals = _aggregate_prefixes(worlds, hand_counts)
    averages = _train_original_weight_tail(
        root, worlds, infos, iterations, discard, pot=config.pot,
        chance_type=_Chance, edges=edges, marginals=marginals,
        hand_counts=hand_counts)

    value, br_oop, br_ip = evaluate_profile(
        root, worlds, averages, pot=config.pot, chance_type=_Chance)
    if not all(math.isfinite(number) for number in (value, br_oop, br_ip)):
        raise ValueError("River-tail diagnostics must be finite.")
    tolerance = 1e-10 * max(1.0, config.pot, abs(value), abs(br_oop), abs(br_ip))
    if br_oop < value - tolerance or br_ip < -value - tolerance:
        raise RuntimeError("Best-response diagnostics violate legal response bounds.")

    gain_oop = max(0.0, br_oop - value)
    gain_ip = max(0.0, br_ip + value)
    nash_conv = gain_oop + gain_ip
    exploitability = nash_conv / 2.0
    if not all(math.isfinite(number) for number in
               (gain_oop, gain_ip, nash_conv, exploitability)):
        raise ValueError("River-tail derived diagnostics must be finite.")

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
    average_weight = (iterations * (iterations + 1) - discard * (discard + 1)) // 2
    return {
        "method": "Direct original-weight CFR+ river tail averaging",
        "algorithm": "cfrplus",
        "solver_version": SOLVER_VERSION,
        "strategy_schema": "postflop-strategy-v1",
        "backend": "exact-public-chance-tree",
        "execution_backend": "direct-original-weight-river-tail-python",
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
        "discard": discard,
        "source_iteration_window": [discard + 1, iterations],
        "averaged_sweeps": iterations - discard,
        "average_weight_sum": average_weight,
        "average_schedule": "direct-original-linear-sweep-weight-own-reach-tail",
        "update_schedule": "alternating-oop-then-ip",
        "requested_regret_passes": 2 * iterations,
        "requested_average_passes": iterations - discard,
        "requested_total_traversal_passes": 3 * iterations - discard,
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
            "full_requested_world_node_work": world_work,
            "full_requested_world_node_work_limit": MAX_WORLD_NODE_WORK,
            "full_requested_dense_hand_state_pass_work": dense_hand_work,
            "full_requested_dense_hand_state_pass_work_limit": MAX_DENSE_HAND_STATE_PASS_WORK,
            "info_action_slots": info_action_slots,
            "info_action_slots_limit": MAX_INFO_ACTION_SLOTS,
            "prefix_hand_edges": sum(len(row) for row in edges.values()),
            "prefix_hand_edge_limit": MAX_PREFIX_EDGES,
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
        "diagnostic_provenance": "Metrics recomputed from this direct original-weight river-tail policy using public-batched diagnostics; numeric convergence diagnostics are not an exact equilibrium certificate.",
        "training_calls": 1,
        "strategy": rows,
    }
