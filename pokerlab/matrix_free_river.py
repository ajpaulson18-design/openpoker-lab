"""Matrix-free CFR for the configured fixed-board river abstraction.

This backend keeps per-hand vectors and evaluates showdown/fold terminals with
the ranked payoff kernel. It never materializes compatible private-hand pairs.
"""
import math
from numbers import Real

from .cards import cards, expand_range
from .public_cfr import train_ranked_river
from .public_diagnostics import evaluate_ranked_profile
from .ranked_river import RankedRiverPayoffs
from .river_config import RiverConfig
from .river_tree import _Node, _build_tree


MAX_HAND_STATE_PASS_WORK = 30_000_000
MAX_INFO_ACTION_SLOTS = 1_000_000
MAX_PUBLIC_STATES = 250_000
MAX_FALLBACK_PAIR_CHECKS = 30_000_000
_MAX_ITERATIONS = 10_000


def _target_value(value):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("Target exploitability must be a finite nonnegative real number.")
    try:
        target = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Target exploitability must be a finite nonnegative real number.") from exc
    if not math.isfinite(target) or target < 0:
        raise ValueError("Target exploitability must be a finite nonnegative real number.")
    return target


def solve_matrix_free_river(board, oop_range, ip_range, config=None, *,
                            iterations=1000, algorithm="cfrplus",
                            target_exploitability=None, check_interval=100):
    """Solve a configured five-card-board game without constructing pair worlds.

    Target mode measures exploitability as NashConv / 2 at checkpoints. The
    full requested iteration budget is admitted before training; checks begin
    no earlier than iteration 10. A checkpoint runs after completed iterations.
    """
    board = cards(board)
    if len(board) != 5:
        raise ValueError("Matrix-free ranked solving requires a complete five-card board.")
    if config is None:
        config = RiverConfig()
    elif isinstance(config, dict):
        config = RiverConfig.from_dict(config)
    elif not isinstance(config, RiverConfig):
        raise TypeError("config must be a RiverConfig or configuration object.")
    if type(iterations) is not int or not 10 <= iterations <= _MAX_ITERATIONS:
        raise ValueError("Iterations must be an integer from 10 through 10000.")
    if algorithm not in ("vanilla", "dcfr", "cfrplus"):
        raise ValueError("Algorithm must be vanilla, dcfr, or cfrplus.")
    if type(check_interval) is not int or check_interval < 1:
        raise ValueError("Check interval must be a positive integer.")
    target = None if target_exploitability is None else _target_value(target_exploitability)

    ranges = (expand_range(oop_range, board), expand_range(ip_range, board))
    hands = (tuple(ranges[0]), tuple(ranges[1]))
    weights = (tuple(ranges[0][hand] for hand in hands[0]),
               tuple(ranges[1][hand] for hand in hands[1]))
    kernel = RankedRiverPayoffs(board, hands, weights, pot=config.pot,
                                fallback_pair_limit=MAX_FALLBACK_PAIR_CHECKS)

    public_counts = {"decision": 0, "terminal": 0, "total": 0}

    def reserve(kind):
        if public_counts["total"] >= MAX_PUBLIC_STATES:
            raise ValueError("Matrix-free river exceeds 250,000 public states.")
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
    # Reserve both resource envelopes before allocating strategy rows.
    info_action_slots = sum(
        len(node.actions) * sum(value > 0.0 for value in marginals[player])
        for node in nodes for player in (node.player,)
    )
    if info_action_slots > MAX_INFO_ACTION_SLOTS:
        raise ValueError("Matrix-free river exceeds 1,000,000 information-set action slots.")
    # Training does two vector traversals per vanilla/DCFR iteration (three
    # for CFR+); each diagnostic performs profile evaluation and two BR passes.
    diagnostic_checks = (iterations // check_interval + 1) if target is not None else 1
    passes = 3 if algorithm == "cfrplus" else 2
    hand_state_pass_work = (max(map(len, hands)) * public_counts["total"] *
                            (iterations * passes + 3 * diagnostic_checks))
    if hand_state_pass_work > MAX_HAND_STATE_PASS_WORK:
        raise ValueError("Matrix-free river exceeds 30 million hand-state pass operations.")

    infos, metadata = {}, {}
    for node in nodes:
        player, history = node.player, node.history
        for hand_index, marginal in enumerate(marginals[player]):
            if marginal <= 0.0:
                continue
            key = (player, hand_index, history)
            infos[key] = len(node.actions)
            metadata[key] = node

    checkpoints = []
    last_diagnostic = None
    target_reached = False

    def diagnose(profile):
        value, response0, response1 = evaluate_ranked_profile(
            root, profile, terminal_kernel=kernel)
        if not all(math.isfinite(number) for number in (value, response0, response1)):
            raise ValueError("Diagnostics must be finite; refusing to report convergence.")
        tolerance = 1e-10 * max(1.0, config.pot, abs(value), abs(response0), abs(response1))
        if response0 < value - tolerance or response1 < -value - tolerance:
            raise RuntimeError("Best-response diagnostics violate legal response bounds.")
        nash_conv = max(0.0, (response0 - value) + (response1 + value))
        exploitability = nash_conv / 2.0
        if not math.isfinite(nash_conv) or not math.isfinite(exploitability):
            raise ValueError("Diagnostics must be finite; refusing to report convergence.")
        return value, response0, response1, nash_conv, exploitability

    def checkpoint(iteration, profile):
        nonlocal last_diagnostic, target_reached
        if iteration < 10:
            return False
        last_diagnostic = diagnose(profile)
        value, response0, response1, nash_conv, exploitability = last_diagnostic
        checkpoints.append({
            "iteration": iteration, "value_oop": value,
            "oop_best_response_value": response0,
            "ip_best_response_value": response1,
            "nash_conv": nash_conv, "exploitability": exploitability,
        })
        target_reached = exploitability <= target
        return target_reached

    if target is None:
        averages = train_ranked_river(root, infos, iterations, algorithm,
                                      terminal_kernel=kernel)
        last_diagnostic = diagnose(averages)
        actual_iterations = iterations
    else:
        averages = train_ranked_river(
            root, infos, iterations, algorithm, terminal_kernel=kernel,
            checkpoint_interval=check_interval, checkpoint_callback=checkpoint)
        if last_diagnostic is None:
            raise RuntimeError("Target diagnostics did not produce a final checkpoint.")
        actual_iterations = checkpoints[-1]["iteration"]

    value, response0, response1, nash_conv, exploitability = last_diagnostic
    rows = []
    for key in sorted(infos):
        player, hand_index, history = key
        node = metadata[key]
        rows.append({
            "player": "oop" if player == 0 else "ip",
            "hand": "".join(hands[player][hand_index]),
            "street": "river", "board": list(board),
            "history": list(history),
            "actions": [{"name": action.name, "amount": action.amount,
                         "raise_to": action.raise_to, "history_key": action.token,
                         "probability": probability}
                        for action, probability in zip(node.actions, averages[key])],
        })

    result = {
        "method": "full-traversal CFR", "algorithm": algorithm,
        "solver_version": "matrix-free-river-v1",
        "strategy_schema": "postflop-strategy-v1",
        "execution_backend": "matrix-free-ranked-python",
        "terminal_backend": "ranked-river-python",
        "resource_model": "river-hand-vectors-v1",
        "backend": "exact-public-chance-tree", "board": list(board),
        "config": config.to_dict(), "street_configs": {"river": config.to_dict()},
        "turn_config": None, "river_config": config.to_dict(),
        "runouts": [], "reachable_runouts": [], "runout_mode": "none",
        "chance_note": "Compatible private-pair range products normalized once; board is complete.",
        "iterations": actual_iterations, "deals": kernel.compatible_pair_count,
        "compatible_pairs": kernel.compatible_pair_count,
        "worlds_materialized": 0, "info_sets": len(infos),
        "public_nodes": len(nodes), "public_states": public_counts["total"],
        "terminal_nodes": public_counts["terminal"],
        "public_state_limit": MAX_PUBLIC_STATES, "chance_nodes": 0,
        "world_traversal_nodes": len(nodes),
        "tree_actions": sum(len(node.actions) for node in nodes),
        "pot": config.pot, "effective_stack": config.to_dict()["effective_stack"],
        "value_oop": value, "value_ip": -value,
        "oop_best_response_value": response0,
        "ip_best_response_value": response1,
        "oop_best_response_gain": max(0.0, response0 - value),
        "ip_best_response_gain": max(0.0, response1 + value),
        "nash_conv": nash_conv, "exploitability": exploitability,
        "scope": "Approximate equilibrium of the configured heads-up river abstraction; no preflop, multiway play, or rake.",
        "strategy": rows,
        "resource_usage": {
            "hand_state_pass_work": hand_state_pass_work,
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
    if algorithm == "cfrplus":
        result["update_schedule"] = "alternating-oop-then-ip"
        result["average_schedule"] = "linear-post-sweep-own-reach"
        result["training_passes_per_iteration"] = 3
    if target is not None:
        result["convergence"] = {
            "target_exploitability": target, "max_iterations": iterations,
            "achieved": exploitability,
            "stop_reason": "target-reached" if target_reached else "iteration-limit",
            "checkpoints": checkpoints,
        }
    return result
