"""Configurable matrix-free CFR+ direct original-weight TURN tail profiles.

Research-only finite-game API. It keeps private hands as vectors and enumerates
public river branches through the established TurnRangePayoffs kernel. It does
not materialize joint private-hand/river worlds or alter existing solver defaults.
"""
import math

from .cards import DECK, cards, expand_range
from .cfr import strategy
from .matrix_free_turn import (
    MAX_FALLBACK_PAIR_CHECKS,
    MAX_HAND_STATE_PASS_WORK,
    MAX_INFO_ACTION_SLOTS,
    MAX_PUBLIC_NODES,
    MAX_PUBLIC_STATES,
    _MAX_ITERATIONS,
    _config,
)
from .postflop_solver import _public_reveals
from .postflop_solver import _Chance
from .public_cfr import _cfrplus_target_deltas
from .public_diagnostics import evaluate_ranked_turn_profile
from .river_config import RiverConfig
from .river_tree import _Node, _Terminal
from .river_tree import _build_tree
from .turn_range_kernel import (
    MAX_HAND_SLOTS,
    STABLE_ROOT_MAX_INTEGER_BITS,
    TurnRangePayoffs,
)


def _validate_schedule(iterations, discard):
    if type(discard) is not int:
        raise ValueError("discard must be an integer with 0 <= discard < iterations.")
    if type(iterations) is not int or not 10 <= iterations <= _MAX_ITERATIONS:
        raise ValueError("iterations must be an integer from 10 through 10000.")
    if not 0 <= discard < iterations:
        raise ValueError("discard must be an integer with 0 <= discard < iterations.")


def _check_diagnostic_values(values, config):
    value, response0, response1 = values[:3]
    if not all(math.isfinite(number) for number in (value, response0, response1)):
        raise ValueError("Turn-tail diagnostics must be finite.")
    tolerance = 1e-10 * max(
        1.0, config.pot, abs(value), abs(response0), abs(response1))
    if response0 < value - tolerance or response1 < -value - tolerance:
        raise RuntimeError("Best-response diagnostics violate legal response bounds.")
    oop_gain = max(0.0, response0 - value)
    ip_gain = max(0.0, response1 + value)
    nash_conv = oop_gain + ip_gain
    exploitability = nash_conv / 2.0
    if not all(math.isfinite(number) for number in
               (oop_gain, ip_gain, nash_conv, exploitability)):
        raise ValueError("Turn-tail derived diagnostics must be finite.")
    return value, response0, response1, oop_gain, ip_gain, nash_conv, exploitability


def _train_tail(
    root, infos, iterations, discard, *, kernel, prefix_marginals, hand_counts, pot
):
    regrets = {key: [0.0] * infos[key] for key in infos}
    sums = {key: [0.0] * infos[key] for key in infos}
    half_pot = float(pot) / 2.0

    def strategy_map():
        return {key: strategy(row) for key, row in regrets.items()}

    def accumulate(current, sweep_weight):
        def visit(node, prefix, reach0, reach1):
            if isinstance(node, _Chance):
                for river in sorted(node.branches):
                    child = node.branches[river]
                    visit(child, prefix + (river,), reach0, reach1)
                return
            if isinstance(node, _Terminal):
                return
            if not isinstance(node, _Node):
                raise ValueError("Unexpected node during TURN tail averaging.")

            player = node.player
            action_count = len(node.actions)
            uniform = [1.0 / action_count] * action_count
            probabilities = [
                current.get((player, hand_index, node.history), uniform)
                for hand_index in range(hand_counts[player])
            ]
            own_mass = prefix_marginals[prefix][player]
            own_reach = reach0 if player == 0 else reach1
            for hand_index in range(hand_counts[player]):
                key = (player, hand_index, node.history)
                if key not in sums:
                    continue
                sigma = probabilities[hand_index]
                for action_index in range(action_count):
                    sums[key][action_index] += (
                        own_mass[hand_index]
                        * own_reach[hand_index]
                        * sigma[action_index]
                        * sweep_weight
                    )

            for action_index, child in enumerate(node.children):
                if player == 0:
                    next_reach0 = [
                        reach0[index] * probabilities[index][action_index]
                        for index in range(hand_counts[0])
                    ]
                    visit(child, prefix, next_reach0, reach1)
                else:
                    next_reach1 = [
                        reach1[index] * probabilities[index][action_index]
                        for index in range(hand_counts[1])
                    ]
                    visit(child, prefix, reach0, next_reach1)

        try:
            visit(root, (), [1.0] * hand_counts[0], [1.0] * hand_counts[1])
        finally:
            visit = None

    for _iteration in range(1, iterations + 1):
        current = strategy_map()
        for player in (0, 1):
            deltas = _cfrplus_target_deltas(
                root,
                {},
                infos,
                current,
                player,
                hand_counts,
                half_pot,
                _Chance,
                prefix_kernel=kernel,
            )
            for key in infos:
                if key[0] == player:
                    regrets[key] = [
                        max(0.0, previous + delta)
                        for previous, delta in zip(regrets[key], deltas[key])
                    ]
            current = strategy_map()
        if _iteration > discard:
            accumulate(current, float(_iteration))
        current = None

    averages = {}
    for key, row in sums.items():
        total = sum(row)
        averages[key] = (
            [value / total for value in row]
            if total > 0.0
            else [1.0 / infos[key]] * infos[key]
        )
    return averages


def solve_matrix_free_turn_tail(
    board,
    oop_range,
    ip_range,
    config=None,
    *,
    river_config=None,
    runouts=None,
    iterations=1000,
    discard=0,
):
    """Solve a configured TURN game with a fixed CFR+ original-weight tail.

    Discard removes sweeps only from the final average. Every requested sweep
    and all three per-sweep training passes remain in resource admission.
    """
    _validate_schedule(iterations, discard)
    board = cards(board)
    if len(board) != 4:
        raise ValueError("Matrix-free TURN tail solving requires a four-card board.")
    config = _config(config, "config") or RiverConfig()
    river_config = _config(river_config, "river_config") or config
    if river_config.pot != config.pot or river_config.stacks != config.stacks:
        raise ValueError("Turn and river configs must preserve the original pot and stack caps.")

    normalized_runouts = None if runouts is None else tuple(cards(runouts))
    expanded = (expand_range(oop_range, board), expand_range(ip_range, board))
    hands = (tuple(expanded[0]), tuple(expanded[1]))
    weights = (
        tuple(expanded[0][hand] for hand in hands[0]),
        tuple(expanded[1][hand] for hand in hands[1]),
    )
    kernel = TurnRangePayoffs(
        board,
        hands,
        weights,
        pot=config.pot,
        runouts=normalized_runouts,
        fallback_pair_limit=MAX_FALLBACK_PAIR_CHECKS,
    )

    public_counts = {"decision": 0, "terminal": 0, "chance": 0, "total": 0}

    def reserve(kind):
        if public_counts["total"] >= MAX_PUBLIC_STATES:
            raise ValueError("Matrix-free TURN tail exceeds 250,000 public states.")
        if kind == "decision" and public_counts["decision"] >= MAX_PUBLIC_NODES:
            raise ValueError("Matrix-free TURN tail exceeds 10,000 public decision nodes.")
        public_counts[kind] += 1
        public_counts["total"] += 1

    def is_all_in(contributions):
        matched = min(contributions)
        return any(matched >= stack - 1e-9 for stack in config.stacks)

    def turn_settled(history, contributions):
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
                    river_config,
                    starting_history=river_history,
                    starting_contributions=carried,
                    allocation_hook=reserve,
                )
        return _Chance(tuple(history), branches, 4, "river")

    root, _ = _build_tree(
        config,
        showdown_factory=turn_settled,
        allocation_hook=reserve,
    )

    nodes = []
    turn_fold_terminals = 0
    terminal_count = 0
    pending = [(root, ())]
    while pending:
        node, prefix = pending.pop()
        if isinstance(node, _Chance):
            pending.extend(
                (child, prefix + (card,))
                for card, child in reversed(tuple(node.branches.items()))
            )
        elif isinstance(node, _Node):
            nodes.append(node)
            pending.extend((child, prefix) for child in reversed(node.children))
        elif isinstance(node, _Terminal):
            terminal_count += 1
            if node.kind == "fold" and not prefix:
                turn_fold_terminals += 1
        else:
            raise ValueError("Unexpected node in the configured TURN tree.")

    prefix_marginals = {(): kernel.joint_marginals()}
    for river in sorted(kernel.branch_probabilities):
        prefix_marginals[(river,)] = kernel.joint_marginals((river,))

    info_action_slots = 0
    for node in nodes:
        prefix = _public_reveals(node.history)
        marginals = prefix_marginals.get(prefix)
        if marginals is None:
            continue
        info_action_slots += len(node.actions) * sum(
            mass > 0.0 for mass in marginals[node.player]
        )
        if info_action_slots > MAX_INFO_ACTION_SLOTS:
            raise ValueError(
                "Matrix-free TURN tail exceeds 1,000,000 information-set action slots."
            )

    passes_per_iteration = 3
    full_passes = iterations * passes_per_iteration + 3
    max_hands = max(map(len, hands))
    kernel_public_states = public_counts["total"]
    base_work = max_hands * kernel_public_states * full_passes
    exceptional_root_fold_work = 0
    if kernel.exceptional_conditioning:
        exceptional_root_fold_work = (
            turn_fold_terminals
            * (
                4 * max_hands * len(kernel.branch_probabilities)
                + 2 * kernel.hand_slots
            )
            * full_passes
        )
    hand_state_pass_work = base_work + exceptional_root_fold_work
    if hand_state_pass_work > MAX_HAND_STATE_PASS_WORK:
        raise ValueError(
            "Matrix-free TURN tail exceeds 30 million hand-state-pass operations."
        )

    infos = {}
    metadata = {}
    for node in nodes:
        prefix = _public_reveals(node.history)
        marginals = prefix_marginals.get(prefix)
        if marginals is None:
            continue
        player = node.player
        for hand_index, marginal in enumerate(marginals[player]):
            if marginal <= 0.0:
                continue
            key = (player, hand_index, node.history)
            infos[key] = len(node.actions)
            metadata[key] = node

    hand_counts = (len(hands[0]), len(hands[1]))
    averages = _train_tail(
        root,
        infos,
        iterations,
        discard,
        kernel=kernel,
        prefix_marginals=prefix_marginals,
        hand_counts=hand_counts,
        pot=config.pot,
    )
    diagnostic = evaluate_ranked_turn_profile(
        root,
        averages,
        terminal_kernel=kernel,
        chance_type=_Chance,
    )
    (
        value,
        br0,
        br1,
        oop_gain,
        ip_gain,
        nash_conv,
        exploitability,
    ) = _check_diagnostic_values(diagnostic, config)

    rows = []
    for key in sorted(infos):
        player, hand_index, history = key
        node = metadata[key]
        reveals = _public_reveals(history)
        board_now = board + reveals
        rows.append({
            "player": "oop" if player == 0 else "ip",
            "hand": "".join(hands[player][hand_index]),
            "street": "river" if reveals else "turn",
            "board": list(board_now),
            "history": list(history),
            "actions": [
                {
                    "name": action.name,
                    "amount": action.amount,
                    "raise_to": action.raise_to,
                    "history_key": action.token,
                    "probability": probability,
                }
                for action, probability in zip(node.actions, averages[key])
            ],
        })

    selected = (
        [card for card in DECK if card not in board]
        if normalized_runouts is None
        else sorted(normalized_runouts, key=DECK.index)
    )
    reachable = sorted(kernel.branch_probabilities)
    tail_weight = (iterations * (iterations + 1) - discard * (discard + 1)) // 2
    result = {
        "method": "Direct original-weight CFR+ tail averaging",
        "algorithm": "cfrplus",
        "solver_version": "research-matrix-free-turn-tail-v1",
        "strategy_schema": "postflop-strategy-v1",
        "backend": "exact-public-chance-tree",
        "execution_backend": "matrix-free-original-weight-tail-python",
        "diagnostics_backend": "public-batched-python",
        "resource_model": "matrix-free-turn-hand-vectors-v1",
        "board": list(board),
        "config": config.to_dict(),
        "street_configs": {
            "turn": config.to_dict(),
            "river": river_config.to_dict(),
        },
        "turn_config": config.to_dict(),
        "river_config": river_config.to_dict(),
        "runouts": selected,
        "reachable_runouts": reachable,
        "runout_mode": "full-deck" if runouts is None else "conditioned-subset",
        "chance_note": (
            "Private ranges are normalized before river filtering; compatible "
            "joint range and river mass is conditioned once across selected "
            "river branches."
        ),
        "iterations": iterations,
        "requested_iterations": iterations,
        "discard": discard,
        "source_iteration_window": [discard + 1, iterations],
        "averaged_sweeps": iterations - discard,
        "average_weight_sum": tail_weight,
        "average_schedule": "direct-original-linear-sweep-weight-own-reach-tail",
        "update_schedule": "alternating-oop-then-ip",
        "requested_regret_passes": 2 * iterations,
        "requested_average_passes": iterations - discard,
        "requested_total_traversal_passes": 3 * iterations - discard,
        "admitted_training_passes_per_iteration": 3,
        "compatible_world_count": kernel.compatible_world_count,
        "worlds": kernel.compatible_world_count,
        "worlds_materialized": 0,
        "info_sets": len(infos),
        "public_nodes": public_counts["decision"],
        "public_states": public_counts["total"],
        "terminal_nodes": public_counts["terminal"],
        "chance_nodes": public_counts["chance"],
        "tree_actions": sum(len(node.actions) for node in nodes),
        "public_state_limit": MAX_PUBLIC_STATES,
        "public_node_limit": MAX_PUBLIC_NODES,
        "pot": config.pot,
        "effective_stack": config.to_dict()["effective_stack"],
        "value_oop": value,
        "value_ip": -value,
        "oop_best_response_value": br0,
        "ip_best_response_value": br1,
        "oop_best_response_gain": max(0.0, br0 - value),
        "ip_best_response_gain": max(0.0, br1 + value),
        "nash_conv": nash_conv,
        "exploitability": exploitability,
        "scope": (
            "Research profile for the configured heads-up turn/river game; "
            "no preflop, multiway play, rake, or general exact-equilibrium claim."
        ),
        "diagnostic_provenance": (
            "Metrics are recomputed from the direct original-weight tail policy "
            "using matrix-free public-batched diagnostics; these numeric "
            "diagnostics are not an exact equilibrium certificate."
        ),
        "training_calls": 1,
        "strategy": rows,
        "resource_usage": {
            "hand_state_pass_work": hand_state_pass_work,
            "base_hand_state_pass_work": base_work,
            "exceptional_root_fold_pass_work": exceptional_root_fold_work,
            "hand_slots": kernel.hand_slots,
            "kernel_public_states": kernel_public_states,
            "turn_fold_terminals": turn_fold_terminals,
            "info_action_slots": info_action_slots,
            "fallback_pair_checks": kernel.fallback_pair_checks,
            "stable_root_fold_calls": kernel.stable_root_fold_calls,
            "stable_root_fold_pair_checks": kernel.stable_root_fold_pair_checks,
            "hand_counts": [len(hands[0]), len(hands[1])],
            "compatible_world_count": kernel.compatible_world_count,
            "limits": {
                "hand_state_pass_work": MAX_HAND_STATE_PASS_WORK,
                "info_action_slots": MAX_INFO_ACTION_SLOTS,
                "fallback_pair_checks": MAX_FALLBACK_PAIR_CHECKS,
                "hand_slots": MAX_HAND_SLOTS,
                "stable_root_fold_pair_checks": kernel.stable_root_pair_limit,
                "stable_root_integer_bits_bound": STABLE_ROOT_MAX_INTEGER_BITS,
                "public_states": MAX_PUBLIC_STATES,
                "public_nodes": MAX_PUBLIC_NODES,
            },
        },
    }
    if kernel.exceptional_conditioning:
        result["conditioning_mode"] = "scaled-branch-mass-and-conditioned-folds"
    if kernel.stable_root_fold_calls:
        result["root_fold_mode"] = "exact-normalized-binary64-pairs"
    return result
