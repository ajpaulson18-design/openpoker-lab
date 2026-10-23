"""Pure no-training preflight for two fixed held-out river cases.

The production tree builder supplies only the public action structure. Independent
physical worlds, ranks, numeric replay, and exact scan/partition audit come from
the validation helpers. No solver, trainer, profile evaluator, best-response
evaluator, or production hand-ranking routine is called. The production terminal
payoff helper appears only in a differential refund/utility comparison.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from pokerlab.cards import cards, expand_range
from pokerlab.river_config import RiverConfig
from pokerlab.river_tree import _Node, _Terminal, _build_tree, _terminal_value
from scripts import preflop_validation as rank_reference
from scripts import turn_rational_certificate as exact_reference
from scripts import turn_river_validation as validator


T = 10_000
PASSES = 3
TARGET_NASH_CONV = 1 / 1000
CASES = (
    {
        "id": "river-unpaired-blocker-tie-raise",
        "board": "AhKdQcJs2d",
        "oop": "AsTc:1,3c4c:0.25,9c9d:0.75,5c6c:0.5",
        "ip": "AsKh:0.5,QhTh:0.75,8c8d:0.25,6c7d:1",
        "config": {
            "pot": 100,
            "effective_stack": [120, 80],
            "bet_sizes": [0.33],
            "raise_sizes": [0.25],
            "max_raises": 1,
            "include_all_in": True,
        },
    },
    {
        "id": "river-paired-short-spr-rank-extremes",
        "board": "9h8h7h2c2d",
        "oop": "6h5h:0.75,AhKh:0.25,9c9d:1,2h2s:0.5",
        "ip": "JhTh:0.5,QhKh:1,8c8d:0.75,7c7d:0.25",
        "config": {
            "pot": 100,
            "effective_stack": [70, 80],
            "bet_sizes": [0.25],
            "raise_sizes": [0.25],
            "max_raises": 1,
            "include_all_in": True,
        },
    },
)



LIMITS = {
    "max_materialized_world_node_work": 30_000_000,
    "max_matrix_free_hand_state_pass_work": 30_000_000,
    "max_public_decision_nodes": 10_000,
    "max_public_states": 250_000,
    "max_info_action_slots": 1_000_000,
    "max_ranked_fallback_pair_checks": 30_000_000,
    "max_world_count": 200_000,
    "max_oracle_modeled_world_node_work": 8_000_000,
    "exact_work": 100_000,
    "exact_depth": 64,
    "exact_fraction_bits": 65_536,
}


def _production_action(action):
    return {
        "name": action.name,
        "amount": action.amount,
        "raise_to": action.raise_to,
        "history_key": action.token,
    }


def _independent_action(action):
    return {
        "name": action.name,
        "amount": action.amount,
        "raise_to": action.raise_to,
        "history_key": action.token,
    }


def _tree_signature(node, *, independent, pot):
    if independent:
        decision_type = validator._Decision
        terminal_type = validator._Terminal
    else:
        decision_type = _Node
        terminal_type = _Terminal

    if isinstance(node, decision_type):
        actions = (
            [_independent_action(action) for action in node.actions]
            if independent
            else [_production_action(action) for action in node.actions]
        )
        if len(actions) != len(node.children):
            raise AssertionError("Public decision action and child counts differ.")
        return {
            "kind": "decision",
            "history": list(node.history),
            "player": node.player,
            "actions": actions,
            "children": [
                _tree_signature(child, independent=independent, pot=pot)
                for child in node.children
            ],
        }
    if isinstance(node, terminal_type):
        signs = [-1, 0, 1]
        if independent:
            utilities = [
                validator._terminal_payoff(
                    node, {"sign": sign, "pot": pot}
                )
                for sign in signs
            ]
        else:
            utilities = [
                _terminal_value(node, sign, pot)
                for sign in signs
            ]
        return {
            "kind": "terminal",
            "terminal_kind": node.kind,
            "winner": node.winner,
            "contributions": list(node.contributions),
            "utilities_by_showdown_sign": utilities,
        }
    raise TypeError(
        f"unexpected {'independent' if independent else 'production'} "
        f"river-tree node: {type(node)!r}"
    )


def _walk(root, *, independent):
    decision_type = validator._Decision if independent else _Node
    terminal_type = validator._Terminal if independent else _Terminal
    pending = [(root, 1)]
    decisions = terminals = action_slots = max_depth = 0
    action_names = Counter()
    nodes = []
    while pending:
        node, depth = pending.pop()
        max_depth = max(max_depth, depth)
        if isinstance(node, decision_type):
            decisions += 1
            nodes.append(node)
            action_slots += len(node.actions)
            action_names.update(action.name for action in node.actions)
            pending.extend((child, depth + 1) for child in reversed(node.children))
        elif isinstance(node, terminal_type):
            terminals += 1
        else:
            raise TypeError(
                f"unexpected {'independent' if independent else 'production'} "
                f"river-tree node: {type(node)!r}"
            )
    return decisions, terminals, action_slots, max_depth, action_names, nodes


def _uniform_production_artifact(case, board, root, worlds, config):
    rows = []
    policies = {}
    _, _, _, _, _, nodes = _walk(root, independent=False)
    supported_hands = [
        sorted({world["hands"][player] for world in worlds})
        for player in (0, 1)
    ]
    for node in nodes:
        player = node.player
        for hand in supported_hands[player]:
            probabilities = [1.0 / len(node.actions)] * len(node.actions)
            key = (player, "".join(hand), node.history)
            if key in policies:
                raise AssertionError("Duplicate production information-set identity.")
            policies[key] = tuple(probabilities)
            rows.append({
                "player": "oop" if player == 0 else "ip",
                "hand": "".join(hand),
                "street": "river",
                "board": list(board),
                "history": list(node.history),
                "actions": [
                    dict(action, probability=probability)
                    for action, probability in zip(
                        [_production_action(action) for action in node.actions],
                        probabilities,
                    )
                ],
            })

    result = {
        "board": list(board),
        "config": config.to_dict(),
        "street_configs": {"river": config.to_dict()},
        "turn_config": None,
        "river_config": config.to_dict(),
        "runouts": [],
        "runout_mode": "none",
        "reachable_runouts": [],
        "strategy": rows,
        "info_sets": len(policies),
        "deals": len({
            (world["hands"][0], world["hands"][1]) for world in worlds
        }),
        "compatible_pairs": len({
            (world["hands"][0], world["hands"][1]) for world in worlds
        }),
        "worlds": len(worlds),
        "compatible_world_count": len(worlds),
    }
    return result, policies, nodes


def _exact_summary(outcome):
    return {
        "work": outcome["work"],
        "work_limit": outcome["work_limit"],
        "tree_depth": outcome["tree_depth"],
        "depth_limit": outcome["depth_limit"],
        "maximum_fraction_bits": outcome["maximum_fraction_bits"],
        "fraction_bit_limit": outcome["fraction_bit_limit"],
        "work_by_kind": dict(sorted(outcome["work_by_kind"].items())),
        "metrics": {
            key: str(value)
            for key, value in sorted(outcome["metrics"].items())
        },
    }


def census(case):
    board = cards(case["board"], 5)
    config = RiverConfig.from_dict(case["config"])
    ranges = (expand_range(case["oop"], board), expand_range(case["ip"], board))
    worlds, selected = validator._worlds(board, ranges, None)
    if selected:
        raise AssertionError("Complete river cases must not select future runouts.")

    independent_root = validator._public_tree(
        board,
        validator._config(config, "config"),
        validator._config(config, "config"),
        (),
        worlds,
    )
    production_root, _ = _build_tree(config)
    independent_walk = _walk(independent_root, independent=True)
    production_walk = _walk(production_root, independent=False)
    independent_counts = independent_walk[:5]
    production_counts = production_walk[:5]

    production_signature = _tree_signature(
        production_root, independent=False, pot=config.pot
    )
    independent_signature = _tree_signature(
        independent_root, independent=True, pot=config.pot
    )
    if production_signature != independent_signature:
        raise AssertionError(
            "Production and independent trees differ in a public history, "
            "ordered action metadata, terminal state, refund, or utility."
        )
    if production_counts[:4] != independent_counts[:4]:
        raise AssertionError({
            "independent_counts": list(independent_counts[:4]),
            "production_counts": list(production_counts[:4]),
        })
    if production_counts[4] != independent_counts[4]:
        raise AssertionError("Production and independent action-name counts differ.")

    result, policies, production_nodes = _uniform_production_artifact(
        case, board, production_root, worlds, config
    )
    if len(production_nodes) != len(independent_walk[5]):
        raise AssertionError("Production and independent decision-node totals differ.")

    float_replay = validator.replay_policy(
        result, case["oop"], case["ip"], board=board, config=config
    )
    metrics = (
        "value_oop", "value_ip", "oop_best_response_value",
        "ip_best_response_value", "oop_best_response_gain",
        "ip_best_response_gain", "nash_conv", "exploitability",
    )
    result.update({name: float_replay[name] for name in metrics})
    comparison = validator.compare_result(result, float_replay, tolerance=1e-9)
    if any(value != 0 for value in comparison.values()):
        raise AssertionError("Uniform production-tree policy failed independent replay.")

    exact_outcomes = {}
    expected_limits = (100_000, 64, 65_536)
    for mode in ("scan", "partition"):
        outcome = exact_reference.evaluate_exact(
            independent_root,
            worlds,
            policies,
            config.pot,
            result=result,
            chance_grouping=mode,
            max_work=exact_reference.MAX_EXACT_WORK,
            max_depth=exact_reference.MAX_EXACT_DEPTH,
            max_bits=exact_reference.MAX_FRACTION_BITS,
        )
        actual_limits = (
            outcome["work_limit"],
            outcome["depth_limit"],
            outcome["fraction_bit_limit"],
        )
        if actual_limits != expected_limits:
            raise AssertionError((actual_limits, expected_limits))
        exact_outcomes[mode] = outcome
    if exact_outcomes["scan"]["metrics"] != exact_outcomes["partition"]["metrics"]:
        raise AssertionError("Exact scan and partition metrics differ.")

    hmax = max(map(len, ranges))
    states = independent_counts[0] + independent_counts[1]
    slots = sum(
        len(node.actions)
        * len({
            world["hands"][node.player]
            for world in worlds
            if world["board"][:len(node.board)] == node.board
        })
        for node in independent_walk[5]
    )
    matrixfree_work = hmax * states * (T * PASSES + 3)
    materialized_work = len(worlds) * independent_counts[0] * T * PASSES

    hand_ranks = {
        "oop": {
            "".join(hand): list(rank_reference.independent_rank(board + hand))
            for hand in ranges[0]
        },
        "ip": {
            "".join(hand): list(rank_reference.independent_rank(board + hand))
            for hand in ranges[1]
        },
    }
    rank_lookup = [
        {hand: tuple(rank) for hand, rank in hand_ranks[player].items()}
        for player in ("oop", "ip")
    ]
    ties = sorted([
        ["".join(h0), "".join(h1)]
        for h0 in ranges[0]
        for h1 in ranges[1]
        if set(h0).isdisjoint(h1)
        and rank_lookup[0]["".join(h0)] == rank_lookup[1]["".join(h1)]
    ])
    collision_pairs = sorted([
        ["".join(h0), "".join(h1), sorted(set(h0) & set(h1))]
        for h0 in ranges[0]
        for h1 in ranges[1]
        if set(h0) & set(h1)
    ])
    if len(worlds) != len(ranges[0]) * len(ranges[1]) - len(collision_pairs):
        raise AssertionError("Physical pair count did not match independent blockers.")

    action_names = independent_counts[4]
    info_hand_counts = [
        len({world["hands"][player] for world in worlds})
        for player in (0, 1)
    ]
    exact_summary = {
        mode: _exact_summary(outcome)
        for mode, outcome in exact_outcomes.items()
    }
    assertions = {
        "exactly_four_unique_hands_each": len(ranges[0]) == len(ranges[1]) == 4,
        "all_range_weights_positive_and_each_player_unequal": (
            all(len(set(side.values())) > 1 for side in ranges)
            and all(weight > 0 for side in ranges for weight in side.values())
        ),
        "physical_pair_count_matches_blockers": (
            len(worlds) == len(ranges[0]) * len(ranges[1]) - len(collision_pairs)
        ),
        "at_least_one_cross_range_card_collision": bool(collision_pairs),
        "public_tree_matches_independent_numeric_tree": (
            production_signature == independent_signature
        ),
        "production_tree_matches_full_independent_tree": (
            production_signature == independent_signature
        ),
        "raise_action_present": action_names["raise"] > 0,
        "bet_action_present": action_names["bet"] > 0,
        "all_in_action_present": action_names["all_in"] > 0,
        "10k_materialized_work_within_30m": materialized_work <= 30_000_000,
        "10k_matrix_free_work_within_30m": matrixfree_work <= 30_000_000,
        "uniform_full_policy_replay_matches_all_metrics": all(
            value == 0 for value in comparison.values()
        ),
        "uniform_scan_and_partition_exact_audits_agree": (
            exact_outcomes["scan"]["metrics"]
            == exact_outcomes["partition"]["metrics"]
        ),
        "uniform_exact_smoke_within_work_depth_bits_caps": (
            exact_outcomes["scan"]["work"] <= exact_outcomes["scan"]["work_limit"]
            and exact_outcomes["scan"]["tree_depth"] <= exact_outcomes["scan"]["depth_limit"]
            and exact_outcomes["scan"]["maximum_fraction_bits"] <= exact_outcomes["scan"]["fraction_bit_limit"]
        ),
        "uniform_exact_smokes_within_work_depth_bits_caps": all(
            outcome["work"] <= outcome["work_limit"]
            and outcome["tree_depth"] <= outcome["depth_limit"]
            and outcome["maximum_fraction_bits"] <= outcome["fraction_bit_limit"]
            for outcome in exact_outcomes.values()
        ),
    }
    if case["id"] == "river-unpaired-blocker-tie-raise":
        assertions["unpaired_board"] = len({card[0] for card in board}) == 5
        assertions["at_least_one_exact_hand_rank_tie"] = bool(ties)
    if case["id"] == "river-paired-short-spr-rank-extremes":
        assertions["paired_board"] = len({card[0] for card in board}) < 5
        assertions["short_spr_below_one"] = max(config.stacks) / config.pot < 1
        assertions["all_hand_categories_straight_flush_through_quads"] = (
            {5, 6, 7, 8}.issubset({
                rank[0] for side in hand_ranks.values() for rank in side.values()
            })
        )
    if not all(assertions.values()):
        raise AssertionError({case["id"]: assertions})

    exact_mode_summaries = {
        mode: {
            "work": outcome["work"],
            "tree_depth": outcome["tree_depth"],
            "maximum_fraction_bits": outcome["maximum_fraction_bits"],
            "nash_conv": str(outcome["metrics"]["nash_conv"]),
        }
        for mode, outcome in exact_outcomes.items()
    }
    names = action_names
    return {
        "id": case["id"],
        "board": list(board),
        "ranges": {"oop": case["oop"], "ip": case["ip"]},
        "weights_are_positive_unequal": True,
        "range_hand_counts": [len(ranges[0]), len(ranges[1])],
        "compatible_physical_pairs": len(worlds),
        "overlapping_holding_pairs_excluded": collision_pairs,
        "ties_by_independent_best_five_rank": ties,
        "independent_rank_categories": sorted({
            rank[0] for side in hand_ranks.values() for rank in side.values()
        }),
        "independent_best_five_ranks": hand_ranks,
        "config": config.to_dict(),
        "tree": {
            "decision_nodes": independent_counts[0],
            "terminal_nodes": independent_counts[1],
            "public_states": states,
            "max_depth_nodes": independent_counts[3],
            "action_slots_per_public_node_sum": independent_counts[2],
            "action_name_counts": dict(sorted(names.items())),
            "info_sets_for_uniform_supported_rows": len(policies),
            "supported_hands_by_player": info_hand_counts,
            "supported_information_action_slots": slots,
        },
        "test_metadata": {
            "status": "PASS",
            "solver_training_calls": 0,
            "assertions": assertions,
        },
        "fixed_cfrplus_t10000_preflight": {
            "iterations": T,
            "passes_per_iteration": PASSES,
            "threshold_nash_conv": TARGET_NASH_CONV,
            "configured_solver_target": None,
            "matrix_free_hand_state_pass_work": matrixfree_work,
            "matrix_free_limit": LIMITS["max_matrix_free_hand_state_pass_work"],
            "matrix_free_admitted": (
                matrixfree_work <= LIMITS["max_matrix_free_hand_state_pass_work"]
            ),
            "materialized_world_node_work": materialized_work,
            "materialized_limit": LIMITS["max_materialized_world_node_work"],
            "materialized_admitted": (
                materialized_work <= LIMITS["max_materialized_world_node_work"]
            ),
            "other_caps": {
                "max_world_count": LIMITS["max_world_count"],
                "max_oracle_modeled_world_node_work":
                    LIMITS["max_oracle_modeled_world_node_work"],
                "max_public_states": LIMITS["max_public_states"],
                "max_public_decisions": LIMITS["max_public_decision_nodes"],
                "max_info_action_slots": LIMITS["max_info_action_slots"],
                "max_fallback_pair_checks":
                    LIMITS["max_ranked_fallback_pair_checks"],
                "exact_work": exact_outcomes["scan"]["work"],
                "exact_work_limit": exact_outcomes["scan"]["work_limit"],
                "exact_tree_depth": exact_outcomes["scan"]["tree_depth"],
                "exact_depth_limit": exact_outcomes["scan"]["depth_limit"],
                "exact_fraction_bits": exact_outcomes["scan"]["maximum_fraction_bits"],
                "exact_fraction_bit_limit": exact_outcomes["scan"]["fraction_bit_limit"],
                "exact_work_by_kind": dict(sorted(
                    exact_outcomes["scan"]["work_by_kind"].items())),
                "exact_modes": exact_mode_summaries,
            },
        },
        "uniform_policy_smoke_replay": {
            "checked_information_sets": float_replay["checked_information_sets"],
            "worlds": float_replay["worlds"],
            "public_node_count": float_replay["public_node_count"],
            "compare_result_differences": comparison,
            "exact_fraction_work": exact_outcomes["scan"]["work"],
            "exact_nash_conv": str(
                exact_outcomes["scan"]["metrics"]["nash_conv"]
            ),
            "exact_modes": exact_mode_summaries,
            "this_is_a_preflight_profile_not_training_evidence": True,
        },
    }


def preflight_all():
    return {
        "schema": "river-heldout-quality-preflight-v1",
        "purpose": "No-training fixed-case legality and resource census only",
        "limits": dict(LIMITS),
        "cases": [census(case) for case in CASES],
        "interpretation": (
            "A successful structural/exact smoke preflight only shows these fixed "
            "models fit the existing guards. It is not solver training, a quality "
            "result, or an equilibrium certificate. The 1/1000 NashConv reporting "
            "threshold is fixed before any future training; misses must be retained."
        ),
    }
