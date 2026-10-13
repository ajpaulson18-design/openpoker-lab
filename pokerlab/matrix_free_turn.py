"""Matrix-free CFR for configured turn-to-river abstractions.

This bounded heads-up backend keeps private-hand vectors and exact public river
branches. It does not construct joint private-hand/runout worlds and supports no
preflop, multiway, or rake model.
"""
import math
from numbers import Real

from .cards import DECK, cards, expand_range
from .postflop_solver import _Chance, _public_reveals
from .public_cfr import train_ranked_turn
from .public_diagnostics import evaluate_ranked_turn_profile
from .river_config import RiverConfig
from .river_tree import _Node, _Terminal, _build_tree
from .turn_range_kernel import MAX_HAND_SLOTS, TurnRangePayoffs

MAX_HAND_STATE_PASS_WORK = 30_000_000
MAX_INFO_ACTION_SLOTS = 1_000_000
MAX_PUBLIC_STATES = 250_000
MAX_PUBLIC_NODES = 10_000
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


def _config(value, label):
    if value is None:
        return None
    if isinstance(value, dict):
        return RiverConfig.from_dict(value)
    if not isinstance(value, RiverConfig):
        raise TypeError(f"{label} must be a RiverConfig or configuration object.")
    return value


def solve_matrix_free_turn(board, oop_range, ip_range, config=None, *,
                           river_config=None, runouts=None, iterations=1000,
                           algorithm="cfrplus", target_exploitability=None,
                           check_interval=100):
    """Solve a configured turn start with exact matrix-free river payoffs.

    Target mode reports NashConv / 2 and checks only completed iterations at or
    after iteration 10. Resource admission always uses the full iteration cap.
    """
    board = cards(board)
    if len(board) != 4:
        raise ValueError("Matrix-free turn solving requires a four-card board.")
    config = _config(config, "config") or RiverConfig()
    river_config = _config(river_config, "river_config") or config
    if river_config.pot != config.pot or river_config.stacks != config.stacks:
        raise ValueError("Turn and river configs must preserve the original pot and stack caps.")
    if type(iterations) is not int or not 10 <= iterations <= _MAX_ITERATIONS:
        raise ValueError("Iterations must be an integer from 10 through 10000.")
    if algorithm not in ("vanilla", "dcfr", "cfrplus"):
        raise ValueError("Algorithm must be vanilla, dcfr, or cfrplus.")
    if type(check_interval) is not int or check_interval < 1:
        raise ValueError("Check interval must be a positive integer.")
    target = None if target_exploitability is None else _target_value(target_exploitability)

    normalized_runouts = None if runouts is None else tuple(cards(runouts))
    expanded = (expand_range(oop_range, board), expand_range(ip_range, board))
    hands = (tuple(expanded[0]), tuple(expanded[1]))
    weights = (tuple(expanded[0][hand] for hand in hands[0]),
               tuple(expanded[1][hand] for hand in hands[1]))
    kernel = TurnRangePayoffs(
        board, hands, weights, pot=config.pot, runouts=normalized_runouts,
        fallback_pair_limit=MAX_FALLBACK_PAIR_CHECKS,
    )

    public_counts = {"decision": 0, "terminal": 0, "chance": 0, "total": 0}

    def reserve(kind):
        if public_counts["total"] >= MAX_PUBLIC_STATES:
            raise ValueError("Matrix-free turn exceeds 250,000 public states.")
        if kind == "decision" and public_counts["decision"] >= MAX_PUBLIC_NODES:
            raise ValueError("Matrix-free turn exceeds 10,000 public decision nodes.")
        public_counts[kind] += 1
        public_counts["total"] += 1

    def is_all_in(contributions):
        matched = min(contributions)
        return any(matched >= stack - 1e-9 for stack in config.stacks)

    def turn_settled(history, contributions):
        # Return unmatched excess before the fresh river street begins.
        matched = min(contributions)
        carried = (matched, matched)
        reserve("chance")
        branches = {}
        for river in sorted(kernel.branch_probabilities):
            river_history = tuple(history) + (f"river@{river}",)
            if is_all_in(carried):
                reserve("terminal")
                branches[river] = _Terminal("showdown", carried)
            else:
                branches[river], _ = _build_tree(
                    river_config, starting_history=river_history,
                    starting_contributions=carried, allocation_hook=reserve,
                )
        return _Chance(tuple(history), branches, 4, "river")

    root, _ = _build_tree(config, showdown_factory=turn_settled,
                          allocation_hook=reserve)

    nodes = []
    turn_fold_terminals = 0
    pending = [(root, ())]
    while pending:
        node, prefix = pending.pop()
        if isinstance(node, _Chance):
            pending.extend((child, prefix + (card,))
                           for card, child in reversed(tuple(node.branches.items())))
        elif isinstance(node, _Node):
            nodes.append(node)
            pending.extend((child, prefix) for child in reversed(node.children))
        elif isinstance(node, _Terminal) and node.kind == "fold" and not prefix:
            turn_fold_terminals += 1

    root_marginals = kernel.joint_marginals()
    prefix_marginals = {(): root_marginals}
    for river in kernel.branch_probabilities:
        prefix_marginals[(river,)] = kernel.joint_marginals((river,))

    # Reserve the strategy table's slot envelope before creating information rows.
    info_action_slots = 0
    for node in nodes:
        prefix = _public_reveals(node.history)
        marginals = prefix_marginals.get(prefix)
        if marginals is None:
            continue
        info_action_slots += len(node.actions) * sum(
            value > 0.0 for value in marginals[node.player]
        )
        if info_action_slots > MAX_INFO_ACTION_SLOTS:
            raise ValueError("Matrix-free turn exceeds 1,000,000 information-set action slots.")

    diagnostic_checks = (iterations // check_interval + 1) if target is not None else 1
    passes = 3 if algorithm == "cfrplus" else 2
    kernel_public_states = public_counts["total"]
    hand_state_pass_work = (
        max(map(len, hands)) * kernel_public_states *
        (iterations * passes + 3 * diagnostic_checks)
    )
    if hand_state_pass_work > MAX_HAND_STATE_PASS_WORK:
        raise ValueError("Matrix-free turn exceeds 30 million hand-state pass operations.")

    infos, metadata = {}, {}
    for node in nodes:
        prefix = _public_reveals(node.history)
        marginals = prefix_marginals.get(prefix)
        if marginals is None:
            continue
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
        value, response0, response1 = evaluate_ranked_turn_profile(
            root, profile, terminal_kernel=kernel, chance_type=_Chance,
        )
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
        averages = train_ranked_turn(
            root, infos, iterations, algorithm, terminal_kernel=kernel,
            chance_type=_Chance,
        )
        last_diagnostic = diagnose(averages)
        actual_iterations = iterations
    else:
        averages = train_ranked_turn(
            root, infos, iterations, algorithm, terminal_kernel=kernel,
            chance_type=_Chance, checkpoint_interval=check_interval,
            checkpoint_callback=checkpoint,
        )
        if last_diagnostic is None:
            raise RuntimeError("Target diagnostics did not produce a final checkpoint.")
        actual_iterations = checkpoints[-1]["iteration"]

    value, response0, response1, nash_conv, exploitability = last_diagnostic
    rows = []
    for key in sorted(infos):
        player, hand_index, history = key
        reveals = _public_reveals(history)
        public_board = board + reveals
        node = metadata[key]
        rows.append({
            "player": "oop" if player == 0 else "ip",
            "hand": "".join(hands[player][hand_index]),
            "street": "river" if reveals else "turn",
            "board": list(public_board), "history": list(history),
            "actions": [{
                "name": action.name, "amount": action.amount,
                "raise_to": action.raise_to, "history_key": action.token,
                "probability": probability,
            } for action, probability in zip(node.actions, averages[key])],
        })

    selected = ([card for card in DECK if card not in board]
                if normalized_runouts is None else
                sorted(normalized_runouts, key=DECK.index))
    result = {
        "method": "full-traversal CFR", "algorithm": algorithm,
        "solver_version": "matrix-free-turn-v1",
        "strategy_schema": "postflop-strategy-v1",
        "execution_backend": "matrix-free-ranked-python",
        "terminal_backend": "ranked-turn-python",
        "resource_model": "turn-hand-vectors-v1",
        "backend": "exact-public-chance-tree", "board": list(board),
        "config": config.to_dict(),
        "street_configs": {"turn": config.to_dict(), "river": river_config.to_dict()},
        "turn_config": config.to_dict(), "river_config": river_config.to_dict(),
        "runouts": selected,
        "reachable_runouts": sorted(kernel.branch_probabilities),
        "runout_mode": "full-deck" if runouts is None else "conditioned-subset",
        "chance_note": (
            "Private ranges are normalized before river filtering; compatible joint "
            "range and river mass is conditioned once across selected river branches."
        ),
        "iterations": actual_iterations,
        "compatible_world_count": kernel.compatible_world_count,
        "worlds_materialized": 0, "info_sets": len(infos),
        "public_nodes": len(nodes), "public_states": public_counts["total"],
        "terminal_nodes": public_counts["terminal"],
        "public_state_limit": MAX_PUBLIC_STATES,
        "chance_nodes": public_counts["chance"],
        "diagnostics_backend": "public-batched-python",
        "tree_actions": sum(len(node.actions) for node in nodes),
        "pot": config.pot, "effective_stack": config.to_dict()["effective_stack"],
        "value_oop": value, "value_ip": -value,
        "oop_best_response_value": response0,
        "ip_best_response_value": response1,
        "oop_best_response_gain": max(0.0, response0 - value),
        "ip_best_response_gain": max(0.0, response1 + value),
        "nash_conv": nash_conv, "exploitability": exploitability,
        "scope": "Approximate equilibrium of the configured heads-up turn and river abstraction; no preflop, multiway play, or rake.",
        "strategy": rows,
        "resource_usage": {
            "hand_state_pass_work": hand_state_pass_work,
            "hand_slots": kernel.hand_slots,
            "kernel_public_states": kernel_public_states,
            "turn_fold_terminals": turn_fold_terminals,
            "info_action_slots": info_action_slots,
            "fallback_pair_checks": kernel.fallback_pair_checks,
            "hand_counts": [len(hands[0]), len(hands[1])],
            "compatible_world_count": kernel.compatible_world_count,
            "limits": {
                "hand_state_pass_work": MAX_HAND_STATE_PASS_WORK,
                "info_action_slots": MAX_INFO_ACTION_SLOTS,
                "fallback_pair_checks": MAX_FALLBACK_PAIR_CHECKS,
                "hand_slots": MAX_HAND_SLOTS,
                "public_states": MAX_PUBLIC_STATES,
                "public_nodes": MAX_PUBLIC_NODES,
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
