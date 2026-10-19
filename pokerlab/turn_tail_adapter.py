"""Research-only direct original-weight CFR+ tail solver for turn starts.

This prototype intentionally supports one materialized public-vector backend.
It reuses the established turn tree, world, prefix, CFR+ delta, and diagnostic
helpers while keeping all training state local to each invocation.
"""
import math

from .cards import cards
from .postflop_solver import (
    _enumerate_worlds,
    _build_postflop_tree,
    _prefix_hand_index,
    _public_reveals,
    _MAX_WORLD_NODE_WORK,
    _MAX_PUBLIC_STATES,
    _MAX_PUBLIC_NODES,
)
from .public_cfr import (
    MAX_PREFIX_EDGES,
    _aggregate_prefixes,
    _validate_inputs,
    _cfrplus_target_deltas,
)
from .public_diagnostics import evaluate_profile
from .river_config import RiverConfig
from .postflop_solver import _Chance
from .river_tree import _Node, _Terminal
from .cfr import strategy


MAX_INFO_ACTION_SLOTS = 1_000_000
MAX_DENSE_HAND_STATE_PASS_WORK = 30_000_000
MAX_ITERATIONS = 10_000
def _config(value, label):
    if value is None:
        return None
    if isinstance(value, dict):
        return RiverConfig.from_dict(value)
    if not isinstance(value, RiverConfig):
        raise TypeError(f"{label} must be a RiverConfig or configuration object.")
    return value


def _train_original_weight_tail(root, worlds, infos, iterations, discard, *,
                                pot, chance_type, edges, marginals, hand_counts):
    """Train CFR+ using prevalidated world/infos/prefix structures.

    The prepared edges, marginals, and hand counts are an internal context
    produced by ``solve_turn_tail`` (or an equivalent validated test fixture);
    this helper does not validate their mutual consistency.
    """
    _validate_inputs(worlds, infos, iterations, "cfrplus", pot, chance_type)
    if type(discard) is not int or not 0 <= discard < iterations:
        raise ValueError("discard must be an integer in [0, iterations).")
    regrets = {key: [0.0] * infos[key] for key in infos}
    sums = {key: [0.0] * infos[key] for key in infos}
    half_pot = float(pot) / 2.0

    def strategy_map():
        return {key: strategy(row) for key, row in regrets.items()}

    def accumulate_original_weight_tail(current, average_weight):
        def visit(node, prefix, reach0, reach1):
            if isinstance(node, chance_type):
                for card, child in node.branches.items():
                    visit(child, prefix + (card,), reach0, reach1)
                return
            if isinstance(node, _Terminal):
                return
            if not isinstance(node, _Node):
                raise ValueError("Unexpected node in public CFR+ average traversal")

            player = node.player
            action_count = len(node.actions)
            uniform = [1.0 / action_count] * action_count
            probabilities = [current.get((player, hand_index, node.history), uniform)
                             for hand_index in range(hand_counts[player])]
            own_mass = marginals[prefix][player]
            own_reach = reach0 if player == 0 else reach1
            for hand_index in range(hand_counts[player]):
                key = (player, hand_index, node.history)
                if key not in sums:
                    continue
                sigma = probabilities[hand_index]
                for action in range(action_count):
                    sums[key][action] += (own_mass[hand_index] * own_reach[hand_index] *
                                          sigma[action] * average_weight)

            for action_index, child in enumerate(node.children):
                if player == 0:
                    next_reach0 = [reach0[index] * probabilities[index][action_index]
                                   for index in range(hand_counts[0])]
                    visit(child, prefix, next_reach0, reach1)
                else:
                    next_reach1 = [reach1[index] * probabilities[index][action_index]
                                   for index in range(hand_counts[1])]
                    visit(child, prefix, reach0, next_reach1)

        try:
            visit(root, (), [1.0] * hand_counts[0], [1.0] * hand_counts[1])
        finally:
            visit = None

    for iteration in range(1, iterations + 1):
        current = strategy_map()
        for player in (0, 1):
            deltas = _cfrplus_target_deltas(
                root, edges, infos, current, player, hand_counts, half_pot, chance_type)
            for key in infos:
                if key[0] == player:
                    regrets[key] = [max(0.0, old + delta)
                                    for old, delta in zip(regrets[key], deltas[key])]
            current = strategy_map()
        if iteration > discard:
            accumulate_original_weight_tail(current, float(iteration))
        current = None

    averages = {}
    for key, row in sums.items():
        total = sum(row)
        averages[key] = ([value / total for value in row] if total else
                         [1.0 / infos[key]] * infos[key])
    return averages


def solve_turn_tail(board, oop_range, ip_range, config=None, *, river_config=None,
                    runouts=None, iterations=1000, discard=0):
    """Solve a configured turn game and return its original-weight CFR+ tail profile."""
    if type(iterations) is not int or not 10 <= iterations <= MAX_ITERATIONS:
        raise ValueError("iterations must be an integer from 10 through 10,000.")
    if type(discard) is not int or not 0 <= discard < iterations:
        raise ValueError("discard must be an integer with 0 <= discard < iterations.")
    board = cards(board)
    if len(board) != 4:
        raise ValueError("Turn tail solving requires a four-card board.")
    config = _config(config, "config") or RiverConfig()
    river_config = _config(river_config, "river_config") or config
    if river_config.pot != config.pot or river_config.stacks != config.stacks:
        raise ValueError("Turn and river configs must preserve original pot and stack caps.")

    # Pass full T to every existing candidate/world admission guard.
    hands, worlds, selected, pair_count = _enumerate_worlds(
        board, oop_range, ip_range, runouts=runouts, iterations=iterations)
    public_counts = {}
    root, nodes, chance_nodes, visited_nodes, _ = _build_postflop_tree(
        board, config, river_config=river_config, worlds=worlds,
        allocation_counts=public_counts)
    original_world_work = len(worlds) * visited_nodes * iterations * 3
    if original_world_work > _MAX_WORLD_NODE_WORK:
        raise ValueError("Postflop solver exceeds 30 million world-node iterations.")

    legal_hands = _prefix_hand_index(worlds)
    info_action_slots = 0
    for (player, history), node in nodes.items():
        prefix = _public_reveals(history)
        info_action_slots += len(node.actions) * len(legal_hands.get((player, prefix), ()))
        if info_action_slots > MAX_INFO_ACTION_SLOTS:
            raise ValueError("Turn tail exceeds 1,000,000 information-set action slots.")
    dense_hand_work = (max(map(len, hands)) * public_counts["total"] *
                       (3 * iterations + 3))
    if dense_hand_work > MAX_DENSE_HAND_STATE_PASS_WORK:
        raise ValueError("Turn tail exceeds 30 million dense hand-state-pass operations.")

    infos, metadata = {}, {}
    for (player, history), node in nodes.items():
        prefix = _public_reveals(history)
        for hand_index in sorted(legal_hands.get((player, prefix), ())):
            key = (player, hand_index, history)
            infos[key] = len(node.actions)
            metadata[key] = node

    # Reuse exactly the existing public-CFR validation and prefix-edge cap.
    _, hand_counts = _validate_inputs(worlds, infos, iterations, "cfrplus",
                                      config.pot, _Chance)
    edges, marginals = _aggregate_prefixes(worlds, hand_counts)
    averages = _train_original_weight_tail(
        root, worlds, infos, iterations, discard, pot=config.pot,
        chance_type=_Chance, edges=edges, marginals=marginals,
        hand_counts=hand_counts)

    value, br0, br1 = evaluate_profile(root, worlds, averages,
                                       pot=config.pot, chance_type=_Chance)
    if not all(math.isfinite(number) for number in (value, br0, br1)):
        raise ValueError("Turn-tail diagnostics must be finite.")
    tolerance = 1e-10 * max(1.0, config.pot, abs(value), abs(br0), abs(br1))
    if br0 < value - tolerance or br1 < -value - tolerance:
        raise RuntimeError("Best-response diagnostics violate legal response bounds.")
    oop_gain = max(0.0, br0 - value)
    ip_gain = max(0.0, br1 + value)
    nash_conv = oop_gain + ip_gain
    exploitability = nash_conv / 2.0
    if not all(math.isfinite(number) for number in
               (oop_gain, ip_gain, nash_conv, exploitability)):
        raise ValueError("Turn-tail derived diagnostics must be finite.")

    rows = []
    for key in sorted(infos):
        player, hand_index, history = key
        node = metadata[key]
        board_now = board + _public_reveals(history)
        rows.append({
            "player": "oop" if player == 0 else "ip",
            "hand": "".join(hands[player][hand_index]),
            "street": "river" if len(board_now) == 5 else "turn",
            "board": list(board_now), "history": list(history),
            "actions": [{"name": action.name, "amount": action.amount,
                         "raise_to": action.raise_to, "history_key": action.token,
                         "probability": probability}
                        for action, probability in zip(node.actions, averages[key])],
        })
    reachable_futures = {tuple(world[4:]) for world in worlds}
    reachable = [card for card in selected if (card,) in reachable_futures]
    tail_weight = (iterations * (iterations + 1) - discard * (discard + 1)) // 2
    return {
        "method": "Direct original-weight CFR+ tail averaging",
        "algorithm": "cfrplus", "solver_version": "research-turn-tail-adapter-v1",
        "strategy_schema": "postflop-strategy-v1",
        "backend": "exact-public-chance-tree", "execution_backend": "direct-original-weight-tail-python",
        "diagnostics_backend": "public-batched-python", "board": list(board),
        "config": config.to_dict(),
        "street_configs": {"turn": config.to_dict(), "river": river_config.to_dict()},
        "turn_config": config.to_dict(), "river_config": river_config.to_dict(),
        "runouts": list(selected), "reachable_runouts": reachable,
        "runout_mode": "full-deck" if runouts is None else "conditioned-subset",
        "chance_note": "Joint private-pair/river physical worlds normalized once; selected river outcomes condition the joint mass.",
        "iterations": iterations, "requested_iterations": iterations,
        "discard": discard, "source_iteration_window": [discard + 1, iterations],
        "averaged_sweeps": iterations - discard,
        "average_weight_sum": tail_weight,
        "average_schedule": "direct-original-linear-sweep-weight-own-reach-tail",
        "update_schedule": "alternating-oop-then-ip",
        "requested_regret_passes": 2 * iterations,
        "requested_average_passes": iterations - discard,
        "requested_total_traversal_passes": 3 * iterations - discard,
        "deals": pair_count, "compatible_pairs": pair_count,
        "worlds": len(worlds), "worlds_materialized": len(worlds),
        "info_sets": len(infos), "public_nodes": len(nodes),
        "public_states": public_counts["total"],
        "terminal_nodes": public_counts["terminal"], "chance_nodes": chance_nodes,
        "world_traversal_nodes": visited_nodes,
        "tree_actions": sum(len(node.actions) for node in nodes.values()),
        "public_state_limit": _MAX_PUBLIC_STATES,
        "public_node_limit": _MAX_PUBLIC_NODES,
        "public_batch_edge_limit": MAX_PREFIX_EDGES,
        "resource_usage": {
            "full_requested_world_node_work": original_world_work,
            "full_requested_world_node_work_limit": _MAX_WORLD_NODE_WORK,
            "full_requested_dense_hand_state_pass_work": dense_hand_work,
            "full_requested_dense_hand_state_pass_work_limit": MAX_DENSE_HAND_STATE_PASS_WORK,
            "info_action_slots": info_action_slots,
            "info_action_slots_limit": MAX_INFO_ACTION_SLOTS,
            "prefix_hand_edges": sum(len(row) for row in edges.values()),
            "prefix_hand_edge_limit": MAX_PREFIX_EDGES,
        },
        "pot": config.pot, "effective_stack": config.to_dict()["effective_stack"],
        "value_oop": value, "value_ip": -value,
        "oop_best_response_value": br0, "ip_best_response_value": br1,
        "oop_best_response_gain": oop_gain, "ip_best_response_gain": ip_gain,
        "nash_conv": nash_conv, "exploitability": exploitability,
        "scope": "Research profile for a configured heads-up turn/river game; no preflop, multiway play, rake, or general exact-equilibrium claim.",
        "diagnostic_provenance": "Metrics recomputed from the direct original-weight tail policy using public-batched diagnostics; numeric convergence diagnostics are not an exact equilibrium certificate.",
        "training_calls": 1,
        "strategy": rows,
    }
