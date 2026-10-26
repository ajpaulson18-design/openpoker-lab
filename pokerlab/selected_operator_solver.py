"""Opt-in four-street integration of streamed, selected-runout payoff queries.

The betting builder, sequence-reach CFR kernels and visible-information vector
diagnostics are shared with the materialized reference. Only chance/payoff
storage changes. This remains a bounded, globally conditioned selected game.
"""

from collections.abc import Mapping
from math import isfinite

from . import preflop_solver as reference
from .postflop_solver import _Chance
from .preflop_tree import build_preflop_tree
from .public_cfr import _train_prepared
from .public_diagnostics import _evaluate_prepared, _normalize_policies
from .river_tree import _Node, _Terminal
from .selected_runout_operator import SelectedRunoutOperator
from .solver_contracts import FourStreetSolveRequest


MAX_OPERATOR_SCAN_ENTRIES = 500_000_000
MAX_INFO_ACTION_SLOTS = 1_000_000


class _Marginals(Mapping):
    """At most one prefix's vectors survive a query, independent of board count."""

    def __init__(self, operator):
        self.operator = operator
        self.marker = None
        self.value = None

    def __getitem__(self, prefix):
        if prefix != self.marker:
            self.value = self.operator.joint_marginals(prefix)
            self.marker = prefix
        return self.value

    def __iter__(self):
        raise TypeError("Marginals are queried, never enumerated.")

    def __len__(self):
        raise TypeError("Marginals have no materialized prefix table.")


def _tokens(board):
    return (() if not board else
            ("".join(board[:3]),) + tuple(board[3:]))


def _prepare(request):
    if not isinstance(request, FourStreetSolveRequest):
        raise TypeError("request must be a FourStreetSolveRequest.")
    if (request.traversal != "public-batched" or
            request.diagnostics != "public-batched" or
            request.resource_model != "public-vector"):
        raise ValueError("Operator solving requires public-batched training/diagnostics and public-vector resources.")
    if type(request.iterations) is not int or not 10 <= request.iterations <= 10_000:
        raise ValueError("Use 10-10,000 solver iterations.")
    operator = SelectedRunoutOperator(request.sb_range, request.bb_range,
                                     request.runouts, iterations=request.iterations)
    pairs = operator.hand_counts[0] * operator.hand_counts[1]
    # Each query can scan the selected index, private pairs, and every
    # pair/board candidate, including when it yields no supported outcome.
    scan_unit = pairs * len(operator.selected) + pairs + len(operator.selected)
    setup_scan_bound = 6 * scan_unit
    if setup_scan_bound > MAX_OPERATOR_SCAN_ENTRIES:
        raise ValueError("Selected operator preparation scan envelope exceeds its limit.")
    selected = operator.reachable_selected()
    # These O(R) records describe PUBLIC TOPOLOGY ONLY. There is no private
    # hand/pair, probability or payoff in this projection. The shared builder
    # reads future-board tokens; actual support and work are charged separately.
    topology = [(0, 0, 1.0, 0, "".join(flop), turn, river)
                for flop, turn, river in selected]
    specs = reference._stage_configs(
        request.flop_actions.to_dict(),
        None if request.turn_actions is None else request.turn_actions.to_dict(),
        None if request.river_actions is None else request.river_actions.to_dict())
    tree = build_preflop_tree(request.preflop_config)
    (root, states, decisions, _, _, template_states, template_decisions) = reference._merge_preflop_tree(
        tree, topology, specs, "public-batched", request.iterations,
        enforce_world_work=False)
    nodes = reference._all_nodes(root)
    infos, metadata = {}, {}
    slots = 0
    legal_marker = None
    legal = None
    for node in nodes:
        prefix = _tokens(reference._revealed_board(node.history))
        if prefix != legal_marker:
            if setup_scan_bound + scan_unit > MAX_OPERATOR_SCAN_ENTRIES:
                raise ValueError("Selected operator preparation scan envelope exceeds its limit.")
            setup_scan_bound += scan_unit
            legal = operator.legal_hands(prefix)
            legal_marker = prefix
        for hand_index in sorted(legal[node.player]):
            if slots + len(node.actions) > MAX_INFO_ACTION_SLOTS:
                raise ValueError("Operator information-set action slots exceed 1,000,000.")
            key = (node.player, hand_index, node.history)
            infos[key] = len(node.actions)
            metadata[key] = node
            slots += len(node.actions)
    terminals = chances = 0
    maximum_actions = 1
    pending = [root]
    while pending:
        node = pending.pop()
        if isinstance(node, _Terminal):
            terminals += 1
        elif isinstance(node, _Chance):
            chances += 1
            pending.extend(node.branches.values())
        else:
            maximum_actions = max(maximum_actions, len(node.children))
            pending.extend(node.children)
    hand_sum = sum(operator.hand_counts)
    # Conservative requested-work envelope. Marginal queries are charged even
    # when the single-prefix cache hits; diagnostics charge missing-policy
    # lookups for every hand/action. Setup support scans are also charged.
    query_bound = (request.iterations * (6 * terminals + 3 * decisions * hand_sum) +
                   3 * terminals + 3 * decisions * hand_sum * maximum_actions +
                   decisions + 4 * len(operator.selected) + 10)
    # Include public-topology builder filtering and emitted pair-probability
    # support. Public construction has its own state/template caps as well.
    scan_bound = query_bound * scan_unit + states * len(operator.selected)
    if scan_bound > MAX_OPERATOR_SCAN_ENTRIES:
        raise ValueError("Selected operator requested scan envelope exceeds 500,000,000 entries.")
    census = {
        "version": "selected-four-street-operator-census-v1",
        "hands": list(operator.hand_counts), "selected_boards": len(operator.selected),
        "reachable_boards": len(selected), "physical_worlds_represented": operator.world_count,
        "stored_complete_worlds": 0, "stored_prefix_pair_edges": 0,
        "operator_input_entries": operator.structural_storage_counts(),
        "public_states": states, "decisions": decisions, "terminals": terminals,
        "chance_nodes": chances, "information_sets": len(infos), "action_slots": slots,
        "regret_and_average_scalar_slots": 2 * slots,
        "serialized_pair_probability_rows_upper_bound": pairs,
        "preparation_scan_upper_bound": setup_scan_bound,
        "maximum_actions": maximum_actions,
        "operator_query_upper_bound": query_bound,
        "pair_runout_scan_upper_bound": scan_bound,
        "scan_limit": MAX_OPERATOR_SCAN_ENTRIES,
        "rank_call_upper_bound": 2 * scan_bound,
        "temporary_template_peak_states": template_states,
        "temporary_template_peak_decisions": template_decisions,
        "scope": "Logical entries and scans, not byte counts, runtime or process RSS. Public tree and strategy rows remain explicit.",
    }
    return operator, root, infos, metadata, specs, census


def census_four_street_operator(request):
    """Rank-free bounded preparation and strategy-storage census; no training."""
    return _prepare(request)[-1]


def solve_four_street_operator(request):
    """Return replay-compatible complete policy using no stored physical worlds.

    The existing request's public-vector selectors are required explicitly.
    No native, sampled, delayed-average or full-deck mode is inferred.
    """
    operator, root, infos, metadata, specs, census = _prepare(request)
    training_root, anchor, view_states = reference._positive_pot_training_view(root)
    operator.pot = 2 * anchor
    marginals = _Marginals(operator)
    try:
        averages = (_train_prepared(
            training_root, infos, request.iterations, request.algorithm,
            pot=operator.pot, chance_type=_Chance, hand_counts=operator.hand_counts,
            edges={}, marginals=marginals, prefix_kernel=operator) if infos else {})
        policies, _ = _normalize_policies(averages)
        value, br0, br1 = _evaluate_prepared(
            training_root, policies, pot=operator.pot, chance_type=_Chance,
            hand_counts=operator.hand_counts, edges={}, marginals=marginals,
            prefix_kernel=operator)
    finally:
        training_root = None
    if not all(isfinite(x) for x in (value, br0, br1)):
        raise ValueError("Operator diagnostics returned a nonfinite value.")
    rows = []
    for key in sorted(infos):
        player, hand, history = key
        node = metadata[key]
        board = reference._revealed_board(history)
        rows.append({
            "player": "sb" if player == 0 else "bb", "hand": "".join(operator.hands[player][hand]),
            "street": {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(board)],
            "revealed_board": list(board), "history": list(history),
            "actions": [{"name": a.name, "amount": a.amount, "raise_to": a.raise_to,
                         "history_key": a.token, "probability": p}
                        for a, p in zip(node.actions, averages[key])],
        })
    gain0, gain1 = max(0.0, br0 - value), max(0.0, br1 + value)
    pair_probabilities = operator.pair_probabilities()
    reachable = operator.reachable_selected()
    if (operator.query_pair_runout_checks > census["pair_runout_scan_upper_bound"] or
            operator.rank_calls > census["rank_call_upper_bound"]):
        raise RuntimeError("Operator exceeded its admitted work envelope.")
    return {
        "method": "full-traversal CFR", "solver_version": "preflop-strategy-v1",
        "strategy_schema": "preflop-strategy-v1", "algorithm": request.algorithm,
        "execution_backend": "selected-operator-public-python",
        "representation_version": "selected-runout-operator-v1",
        "numerical_model": "binary64-local-nine-decimal-whole-hand-v1",
        "preflop_config": request.preflop_config.to_dict(),
        "postflop_action_configs": {s: {k: list(v) if isinstance(v, tuple) else v
                                         for k, v in spec.actions} for s, spec in specs.items()},
        "runout_mode": "conditioned-ordered-selected-runouts",
        "selected_runouts": [list(f + (t, r)) for f, t, r in operator.selected],
        "reachable_runouts": [list(f + (t, r)) for f, t, r in reachable],
        "iterations": request.iterations,
        "candidate_private_pairs": operator.hand_counts[0] * operator.hand_counts[1],
        "compatible_private_pairs": operator.compatible_pairs,
        "worlds": operator.world_count, "pair_runout_preflight_checks": operator.preflight_checks,
        "private_pair_probabilities": pair_probabilities,
        "public_states": census["public_states"], "decisions": census["decisions"],
        "info_sets": len(infos), "value_sb": value, "value_bb": -value,
        "sb_best_response_value": br0, "bb_best_response_value": br1,
        "sb_gain": gain0, "bb_gain": gain1, "nash_conv": gain0 + gain1,
        "exploitability": (gain0 + gain1) / 2,
        "operator_census": census, "public_batched_training_pot_anchor": anchor,
        "operator_statistics": {
            "post_constructor_pair_board_checks": operator.query_pair_runout_checks,
            "rank_calls": operator.rank_calls,
            "rank_vector_peak_entries": operator.rank_scratch_peak,
        },
        "public_batched_training_view_states": view_states,
        "scope": "Conditioned finite heads-up four-street game with streamed chance/payoff queries. Binary64 reduction order may differ; no full-deck, convergence or commercial-scale claim.",
        "strategy": rows,
    }
