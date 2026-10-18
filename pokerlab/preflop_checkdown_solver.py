"""Full-board preflop betting with hidden final-board forced checkdown.

This finite heads-up model uses prepared full-board W/T/L categories as hidden
showdown worlds. Betting occurs only before any board cards are revealed; each
nonfolded closed betting line settles immediately at the matched contribution.
"""

from fractions import Fraction

from . import cfr
from .cfr_plus import train as train_cfrplus
from .preflop_checkdown_budget import admit_prepared, options
from .preflop_full_board_equity import BOARDS_PER_PAIR
from .preflop_tree import build_preflop_tree
from .river_tree import _Terminal, _terminal_value


_MAX_PUBLIC_STATES = 250_000
_MAX_DECISION_NODES = 10_000


def solve_prepared_preflop_checkdown(
        equities, *, config=None, iterations=1000, algorithm="cfrplus",
        resource_model="source-inclusive", world_indexing="categorical",
        training_backend="python", build_directory=None):
    """Solve finite preflop betting followed by hidden full-board checkdown.

    The equities argument must be a structurally valid prepared
    FullBoardEquities table. The budget helper validates its exact type and
    admits the requested work before this function allocates a betting tree.
    No board is revealed: each compatible private pair's positive W/T/L
    categories remain hidden weighted worlds at every preflop information set.
    """
    from . import native_fixed_street as native
    native.validate_backend(training_backend, build_directory)
    if type(world_indexing) is not str or world_indexing not in ('categorical', 'pair-mean'):
        raise ValueError('World indexing must be categorical or pair-mean')
    config = options(config, iterations, algorithm, resource_model)
    budget = admit_prepared(equities, config, iterations, algorithm,
                            resource_model, world_indexing=world_indexing)
    tree_bound = budget["tree_upper_bound"]
    decision_bound = tree_bound["decision_nodes"]
    public_state_bound = tree_bound["public_states"]
    if (type(decision_bound) is not int or type(public_state_bound) is not int
            or decision_bound < 0 or public_state_bound < 1
            or decision_bound > _MAX_DECISION_NODES
            or public_state_bound > _MAX_PUBLIC_STATES):
        raise ValueError("Prepared preflop tree forecast exceeds the existing structural limits.")

    native_admission = None
    if training_backend == "native":
        if max(config.stacks) > 1e12:
            raise ValueError("Native starting stacks exceed 1e12 chips")
        shape = native.admit_native_shape(
            public_state_bound, len(equities.pairs) * (1 if world_indexing == 'pair-mean' else 3),
            tree_bound["information_action_slots"], iterations, algorithm)
        native_admission = native.complete_solve_admission(
            shape, budget["total_loop_entries_upper_bound"],
            budget["training_loop_entries_upper_bound"])

    tree = build_preflop_tree(
        config,
        continuation_factory=lambda boundary: _Terminal(
            "showdown", boundary.matched_contributions),
        max_decision_nodes=decision_bound,
        max_public_states=public_state_bound,
    )

    active_hands = [
        sorted({pair[player] for pair in equities.pairs})
        for player in (0, 1)
    ]
    infos = {}
    metadata = {}
    for (player, history), node in tree.nodes.items():
        for hand_index in active_hands[player]:
            key = (player, hand_index, history)
            infos[key] = len(node.actions)
            metadata[key] = node

    information_action_slots = sum(infos.values())
    actual_counts = tree.counts
    if (actual_counts["decision_nodes"] > decision_bound
            or actual_counts["public_states"] > public_state_bound
            or len(infos) > tree_bound["information_sets"]
            or information_action_slots > tree_bound["information_action_slots"]):
        raise AssertionError("Constructed preflop tree exceeded its admitted envelope.")

    if world_indexing == 'pair-mean':
        worlds = tuple(
            (sb_index, bb_index, float(prior),
             float(Fraction(wins - losses, BOARDS_PER_PAIR)))
            for (sb_index, bb_index, prior), (wins, _, losses)
            in zip(equities.pairs, equities.counts)
        )
    else:
        worlds = equities.worlds

    def node_key(node, world):
        return node.player, world[node.player], node.history

    def payoff(node, world):
        return _terminal_value(node, world[3], 0.0)

    native_metadata = None
    if training_backend == "native":
        averages, native_metadata = native.train_native_fixed_street(
            tree.root, worlds, infos, iterations, algorithm,
            pot=0.0, build_directory=build_directory)
        native_metadata["complete_solve_admission"] = native_admission
    elif not infos:
        averages = {}
    elif algorithm == "cfrplus":
        averages = train_cfrplus(
            tree.root, worlds, infos, iterations,
            terminal_value=payoff, node_key=node_key,
        )
    else:
        averages = cfr.train(
            tree.root, worlds, infos, iterations, algorithm,
            terminal_value=payoff, node_key=node_key,
        )

    value_sb = cfr.evaluate(tree.root, worlds, averages, payoff, node_key)
    sb_best_response = cfr.best_response(
        0, tree.root, worlds, averages, payoff, node_key)
    bb_best_response = cfr.best_response(
        1, tree.root, worlds, averages, payoff, node_key)
    sb_gain = max(0.0, sb_best_response - value_sb)
    bb_gain = max(0.0, bb_best_response + value_sb)
    nash_conv = max(0.0, sb_best_response + bb_best_response)

    strategy = []
    for player, hand_index, history in sorted(infos):
        node = metadata[(player, hand_index, history)]
        strategy.append({
            "player": "sb" if player == 0 else "bb",
            "hand": "".join(equities.hands[player][hand_index]),
            "street": "preflop",
            "revealed_board": [],
            "history": list(history),
            "actions": [{
                "name": action.name,
                "amount": action.amount,
                "raise_to": action.raise_to,
                "history_key": action.token,
                "probability": probability,
            } for action, probability in zip(
                node.actions, averages[(player, hand_index, history)])],
        })

    pair_equities = []
    for (sb_index, bb_index, prior), (wins, ties, losses) in zip(
            equities.pairs, equities.counts):
        pair_equities.append({
            "sb_hand": "".join(equities.hands[0][sb_index]),
            "bb_hand": "".join(equities.hands[1][bb_index]),
            "wins": wins,
            "ties": ties,
            "losses": losses,
            "boards": BOARDS_PER_PAIR,
            "pair_probability": float(prior),
            "pair_probability_fraction": [prior.numerator, prior.denominator],
        })

    result = {
        "solver_version": "preflop-full-checkdown-v1",
        "strategy_schema": "preflop-strategy-v1",
        "algorithm": algorithm,
        "iterations": iterations,
        "training_iterations_completed": iterations if infos else 0,
        "config": config.to_dict(),
        "runout_mode": "full-deck-hidden-final-board-checkdown",
        "compatible_pairs": len(equities.pairs),
        "physical_boards": BOARDS_PER_PAIR * len(equities.pairs),
        "training_world_rows": len(worlds),
        "info_sets": len(infos),
        "tree": actual_counts,
        "work_budget": budget,
        "pair_equities": pair_equities,
        "strategy": strategy,
        "value_sb": value_sb,
        "value_bb": -value_sb,
        "sb_best_response_value": sb_best_response,
        "bb_best_response_value": bb_best_response,
        "nash_conv": nash_conv,
        "exploitability": nash_conv / 2.0,
        "sb_best_response_gain": sb_gain,
        "bb_best_response_gain": bb_gain,
        "scope": (
            "Approximate equilibrium of a finite heads-up preflop betting "
            "abstraction with hidden full-deck final-board W/T/L settlement "
            "at every nonfolded closed betting line. All-in and limped lines "
            "go directly to forced checkdown; no board cards are revealed, "
            "and no postflop decisions, antes, rake or multiway play are modeled."
        ),
    }
    if world_indexing == 'pair-mean':
        result['world_indexing'] = 'pair-mean'
    if native_metadata is not None:
        result["training_backend"] = "native"
        result["native_training"] = native_metadata
    return result
