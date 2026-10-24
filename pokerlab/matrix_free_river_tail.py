"""Opt-in matrix-free CFR+ original-weight tails for fixed-board river games.

This research API keeps private hands as vectors under the ranked payoff kernel.
It does not construct joint pair worlds or change any existing solver default.
"""
import math

from .cards import cards, expand_range
from .cfr import strategy
from .matrix_free_river import (
    MAX_FALLBACK_PAIR_CHECKS,
    MAX_HAND_STATE_PASS_WORK,
    MAX_INFO_ACTION_SLOTS,
    MAX_PUBLIC_STATES,
    _MAX_ITERATIONS,
)
from .public_cfr import _RankedNoChance, _cfrplus_target_deltas
from .public_diagnostics import evaluate_ranked_profile
from .ranked_river import RankedRiverPayoffs
from .river_config import RiverConfig
from .river_tree import _Node, _Terminal, _build_tree


SOLVER_VERSION = "research-matrix-free-river-tail-v1"


def _validate_schedule(iterations, discard):
    if type(iterations) is not int or not 10 <= iterations <= _MAX_ITERATIONS:
        raise ValueError("iterations must be an integer from 10 through 100000.")
    if type(discard) is not int or not 0 <= discard < iterations:
        raise ValueError("discard must be an integer with 0 <= discard < iterations.")


def _train_tail(root, infos, iterations, discard, *, kernel, marginals, hand_counts):
    """Average completed sweeps t>D with original t and own realization reach."""
    regrets = {key: [0.0] * infos[key] for key in infos}
    sums = {key: [0.0] * infos[key] for key in infos}

    def strategy_map():
        return {key: strategy(row) for key, row in regrets.items()}

    def accumulate(current, sweep_weight):
        def visit(node, reach0, reach1):
            if isinstance(node, _Terminal):
                return
            if not isinstance(node, _Node):
                raise ValueError("Ranked river tail averaging does not support public chance nodes.")
            player = node.player
            action_count = len(node.actions)
            uniform = [1.0 / action_count] * action_count
            probabilities = [
                current.get((player, hand_index, node.history), uniform)
                for hand_index in range(hand_counts[player])
            ]
            own_reach = reach0 if player == 0 else reach1
            for hand_index in range(hand_counts[player]):
                key = (player, hand_index, node.history)
                if key not in sums:
                    continue
                sigma = probabilities[hand_index]
                for action_index in range(action_count):
                    # Preserve the established ranked CFR+ arithmetic order.
                    sums[key][action_index] += (
                        marginals[player][hand_index] * own_reach[hand_index]
                        * sigma[action_index] * sweep_weight
                    )
            for action_index, child in enumerate(node.children):
                if player == 0:
                    next_reach0 = [
                        reach0[index] * probabilities[index][action_index]
                        for index in range(hand_counts[0])
                    ]
                    visit(child, next_reach0, reach1)
                else:
                    next_reach1 = [
                        reach1[index] * probabilities[index][action_index]
                        for index in range(hand_counts[1])
                    ]
                    visit(child, reach0, next_reach1)

        try:
            visit(root, [1.0] * hand_counts[0], [1.0] * hand_counts[1])
        finally:
            visit = None

    for iteration in range(1, iterations + 1):
        current = strategy_map()
        for player in (0, 1):
            deltas = _cfrplus_target_deltas(
                root, {}, infos, current, player, hand_counts,
                kernel.pot / 2.0, _RankedNoChance, terminal_kernel=kernel,
            )
            for key in infos:
                if key[0] == player:
                    regrets[key] = [
                        max(0.0, previous + delta)
                        for previous, delta in zip(regrets[key], deltas[key])
                    ]
            current = strategy_map()
        if iteration > discard:
            accumulate(current, float(iteration))
        current = None

    averages = {}
    for key, row in sums.items():
        total = sum(row)
        averages[key] = ([value / total for value in row] if total > 0.0
                         else [1.0 / infos[key]] * infos[key])
    return averages


def _diagnose(root, averages, kernel, config):
    value, response0, response1 = evaluate_ranked_profile(
        root, averages, terminal_kernel=kernel)
    if not all(math.isfinite(number) for number in (value, response0, response1)):
        raise ValueError("River-tail diagnostics must be finite.")
    tolerance = 1e-10 * max(1.0, config.pot, abs(value), abs(response0), abs(response1))
    if response0 < value - tolerance or response1 < -value - tolerance:
        raise RuntimeError("Best-response diagnostics violate legal response bounds.")
    oop_gain = max(0.0, response0 - value)
    ip_gain = max(0.0, response1 + value)
    nash_conv = oop_gain + ip_gain
    exploitability = nash_conv / 2.0
    if not all(math.isfinite(number) for number in
               (oop_gain, ip_gain, nash_conv, exploitability)):
        raise ValueError("River-tail derived diagnostics must be finite.")
    return value, response0, response1, oop_gain, ip_gain, nash_conv, exploitability


def solve_matrix_free_river_tail(board, oop_range, ip_range, config=None, *,
                                 iterations=1000, discard=0):
    """Solve a configured river CFR+ game with an original-weight tail average.

    Every requested sweep updates both players. Only completed sweeps t>discard
    enter the final average, with weight t, own reach and joint hand marginals.
    Admission retains the full 3*T+3 envelope regardless of discard. This API
    has no target stopping and makes no general accuracy or performance promise.
    """
    _validate_schedule(iterations, discard)
    board = cards(board)
    if len(board) != 5:
        raise ValueError("Matrix-free river tail solving requires a complete five-card board.")
    if config is None:
        config = RiverConfig()
    elif isinstance(config, dict):
        config = RiverConfig.from_dict(config)
    elif not isinstance(config, RiverConfig):
        raise TypeError("config must be a RiverConfig or configuration object.")

    ranges = (expand_range(oop_range, board), expand_range(ip_range, board))
    hands = (tuple(ranges[0]), tuple(ranges[1]))
    weights = (tuple(ranges[0][hand] for hand in hands[0]),
               tuple(ranges[1][hand] for hand in hands[1]))
    kernel = RankedRiverPayoffs(board, hands, weights, pot=config.pot,
                                fallback_pair_limit=MAX_FALLBACK_PAIR_CHECKS)
    public_counts = {"decision": 0, "terminal": 0, "total": 0}

    def reserve(kind):
        if public_counts["total"] >= MAX_PUBLIC_STATES:
            raise ValueError("Matrix-free river tail exceeds 250,000 public states.")
        public_counts[kind] += 1
        public_counts["total"] += 1

    root, _decision_count = _build_tree(config, allocation_hook=reserve)
    nodes = []
    pending = [root]
    while pending:
        node = pending.pop()
        if isinstance(node, _Node):
            nodes.append(node)
            pending.extend(reversed(node.children))

    marginals = kernel.joint_marginals()
    # Reserve both envelopes before allocating information-set strategy rows.
    info_action_slots = sum(
        len(node.actions) * sum(value > 0.0 for value in marginals[node.player])
        for node in nodes
    )
    if info_action_slots > MAX_INFO_ACTION_SLOTS:
        raise ValueError("Matrix-free river tail exceeds 1,000,000 information-set action slots.")
    admitted_passes = 3 * iterations + 3
    hand_state_pass_work = (
        max(map(len, hands)) * public_counts["total"] * admitted_passes
    )
    if hand_state_pass_work > MAX_HAND_STATE_PASS_WORK:
        raise ValueError("Matrix-free river tail exceeds 30 million hand-state pass operations.")

    infos, metadata = {}, {}
    for node in nodes:
        player, history = node.player, node.history
        for hand_index, marginal in enumerate(marginals[player]):
            if marginal <= 0.0:
                continue
            key = (player, hand_index, history)
            infos[key] = len(node.actions)
            metadata[key] = node

    averages = _train_tail(
        root, infos, iterations, discard, kernel=kernel, marginals=marginals,
        hand_counts=tuple(map(len, hands)),
    )
    value, response0, response1, oop_gain, ip_gain, nash_conv, exploitability = _diagnose(
        root, averages, kernel, config)
    rows = []
    for key in sorted(infos):
        player, hand_index, history = key
        node = metadata[key]
        rows.append({
            "player": "oop" if player == 0 else "ip",
            "hand": "".join(hands[player][hand_index]),
            "street": "river", "board": list(board), "history": list(history),
            "actions": [{
                "name": action.name, "amount": action.amount,
                "raise_to": action.raise_to, "history_key": action.token,
                "probability": probability,
            } for action, probability in zip(node.actions, averages[key])],
        })

    return {
        "method": "Direct original-weight CFR+ river tail averaging",
        "algorithm": "cfrplus", "solver_version": SOLVER_VERSION,
        "strategy_schema": "postflop-strategy-v1",
        "backend": "exact-public-chance-tree",
        "execution_backend": "matrix-free-original-weight-river-tail-python",
        "terminal_backend": "ranked-river-python",
        "diagnostics_backend": "public-batched-python",
        "resource_model": "river-hand-vectors-v1",
        "board": list(board), "config": config.to_dict(),
        "street_configs": {"river": config.to_dict()},
        "turn_config": None, "river_config": config.to_dict(),
        "runouts": [], "reachable_runouts": [], "runout_mode": "none",
        "chance_note": "Compatible private-pair range products normalized once; board is complete.",
        "iterations": iterations, "requested_iterations": iterations,
        "discard": discard, "source_iteration_window": [discard + 1, iterations],
        "averaged_sweeps": iterations - discard,
        "average_weight_sum": (iterations * (iterations + 1) - discard * (discard + 1)) // 2,
        "average_schedule": "direct-original-linear-sweep-weight-own-reach-tail",
        "update_schedule": "alternating-oop-then-ip",
        "requested_regret_passes": 2 * iterations,
        "requested_average_passes": iterations - discard,
        "requested_total_traversal_passes": 3 * iterations - discard,
        "admitted_training_passes_per_iteration": 3,
        "deals": kernel.compatible_pair_count,
        "compatible_pairs": kernel.compatible_pair_count,
        "worlds_materialized": 0, "info_sets": len(infos),
        "public_nodes": len(nodes), "public_states": public_counts["total"],
        "terminal_nodes": public_counts["terminal"],
        "public_state_limit": MAX_PUBLIC_STATES, "chance_nodes": 0,
        "world_traversal_nodes": len(nodes),
        "tree_actions": sum(len(node.actions) for node in nodes),
        "pot": config.pot, "effective_stack": config.to_dict()["effective_stack"],
        "value_oop": value, "value_ip": -value,
        "oop_best_response_value": response0, "ip_best_response_value": response1,
        "oop_best_response_gain": oop_gain, "ip_best_response_gain": ip_gain,
        "nash_conv": nash_conv, "exploitability": exploitability,
        "scope": "Research profile for a configured heads-up river game; no preflop, multiway play, rake, or general exact-equilibrium claim.",
        "diagnostic_provenance": "Metrics recomputed from this original-weight tail policy using matrix-free diagnostics; numeric diagnostics are not an exact equilibrium certificate.",
        "training_calls": 1, "strategy": rows,
        "resource_usage": {
            "hand_state_pass_work": hand_state_pass_work,
            "admitted_traversal_passes": admitted_passes,
            "info_action_slots": info_action_slots,
            "fallback_pair_checks": kernel.fallback_pair_checks,
            "hand_counts": [len(hands[0]), len(hands[1])],
            "limits": {
                "hand_state_pass_work": MAX_HAND_STATE_PASS_WORK,
                "info_action_slots": MAX_INFO_ACTION_SLOTS,
                "fallback_pair_checks": MAX_FALLBACK_PAIR_CHECKS,
                "public_states": MAX_PUBLIC_STATES,
            },
        },
    }
