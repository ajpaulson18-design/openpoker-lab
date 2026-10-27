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
MAX_RANK_CACHE_BOOKKEEPING_ENTRIES = 1_000_000_000


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


def _prepare(request, *, rank_cache_boards=1, strategy_storage="rows", native_executable=None):
    if not isinstance(request, FourStreetSolveRequest):
        raise TypeError("request must be a FourStreetSolveRequest.")
    if (request.traversal != "public-batched" or
            request.diagnostics != "public-batched" or
            request.resource_model != "public-vector"):
        raise ValueError("Operator solving requires public-batched training/diagnostics and public-vector resources.")
    if type(request.iterations) is not int or not 10 <= request.iterations <= 10_000:
        raise ValueError("Use 10-10,000 solver iterations.")
    if strategy_storage not in ("rows", "packed"):
        raise ValueError("strategy_storage must be rows or packed.")
    if strategy_storage == "packed" and request.algorithm != "cfrplus":
        raise ValueError("Packed strategy storage currently requires CFR+.")
    if native_executable is not None and (strategy_storage != "packed" or request.algorithm != "cfrplus"):
        raise ValueError("Native selected training requires explicit packed CFR+ storage.")
    operator = SelectedRunoutOperator(request.sb_range, request.bb_range,
                                     request.runouts, iterations=request.iterations,
                                     rank_cache_boards=rank_cache_boards)
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
    if rank_cache_boards > 1:
        # One LRU lookup per requested sign, with constant-time move/evict.
        # On a miss, building vectors scans every private hand. Keep the old
        # scan/rank envelope intact; disclose this additional loop envelope.
        lookup_bound = (2 * request.iterations + 3) * terminals * pairs * len(operator.selected)
        build_bound = lookup_bound * hand_sum
        bookkeeping_bound = 4 * lookup_bound + build_bound
        if bookkeeping_bound > MAX_RANK_CACHE_BOOKKEEPING_ENTRIES:
            raise ValueError("Board-rank cache bookkeeping envelope exceeds 1,000,000,000 entries.")
        census["rank_cache_admission"] = {
            "version": "selected-board-rank-lru-v1", "board_capacity": rank_cache_boards,
            "retained_rank_slots": rank_cache_boards * hand_sum,
            "retained_plus_construction_reference_slots": operator.rank_cache_requested_entries,
            "entry_limit": 8192, "board_key_slots": rank_cache_boards,
            "rank_vector_reference_slots": 2 * rank_cache_boards,
            "lookup_upper_bound": lookup_bound, "rank_vector_scan_upper_bound": build_bound,
            "bookkeeping_upper_bound": bookkeeping_bound,
            "bookkeeping_limit": MAX_RANK_CACHE_BOOKKEEPING_ENTRIES,
            "scope": "Logical slots/loops; default scan/rank caps remain unchanged. No bytes or RSS guarantee.",
        }
    if strategy_storage == "packed":
        from .packed_operator_cfr import layout_census
        census["strategy_storage"] = layout_census(root, infos, operator.hand_counts, request.iterations)
    if native_executable is not None:
        from .native_selected_operator import prepare
        census["native_operator_admission"] = prepare(root, infos, request.iterations, operator=operator)[-1]
    return operator, root, infos, metadata, specs, census


def _validate_public_topology(request, strategy_storage, native_executable, public_topology):
    if public_topology not in ("literal", "shared"):
        raise ValueError("public_topology must be literal or shared.")
    if public_topology == "shared" and (
            strategy_storage != "packed" or native_executable is not None or
            not isinstance(request, FourStreetSolveRequest) or request.algorithm != "cfrplus"):
        raise ValueError("Shared topology requires explicit Python packed CFR+ training.")


def census_four_street_operator(request, *, rank_cache_boards=1, strategy_storage="rows",
                                 native_executable=None, public_topology="literal"):
    """Rank-free bounded preparation and strategy-storage census; no training."""
    _validate_public_topology(request, strategy_storage, native_executable, public_topology)
    prepared = _prepare(request, rank_cache_boards=rank_cache_boards, strategy_storage=strategy_storage,
                        native_executable=native_executable)
    operator, root, infos, _metadata, _specs, census = prepared
    if public_topology == "shared":
        from dataclasses import asdict
        from .shared_public_topology import compile_shared_public_topology
        from .shared_topology_view import SharedPublicView, layout_census_shared
        topology = compile_shared_public_topology(root)
        census["shared_public_topology"] = asdict(topology.census)
        census["shared_strategy_storage"] = layout_census_shared(
            SharedPublicView(topology), infos, operator.hand_counts, request.iterations)
    return census


def solve_four_street_operator(request, *, rank_cache_boards=1, strategy_storage="rows",
                               native_executable=None, public_topology="literal"):
    """Return replay-compatible complete policy using no stored physical worlds.

    The existing request's public-vector selectors are required explicitly.
    No native, sampled, delayed-average or full-deck mode is inferred.
    """
    _validate_public_topology(request, strategy_storage, native_executable, public_topology)
    operator, root, infos, metadata, specs, census = _prepare(
        request, rank_cache_boards=rank_cache_boards, strategy_storage=strategy_storage,
        native_executable=native_executable)
    shared_view = None
    chance_type = _Chance
    if public_topology == "shared":
        from collections import namedtuple
        from dataclasses import asdict
        from .shared_public_topology import compile_shared_public_topology, DecisionVertex
        from .shared_topology_view import (
            SharedPublicView, ChanceCursor, layout_census_shared,
        )
        topology = compile_shared_public_topology(root)
        shared_view = SharedPublicView(topology)
        shared_layout = layout_census_shared(shared_view, infos, operator.hand_counts, request.iterations)
        # Preserve the entire semantic key set and action output while dropping
        # every metadata reference to the expanded source tree before training.
        Menu = namedtuple("SharedSerializationMenu", "actions")
        menus = tuple(Menu(vertex.actions) if isinstance(vertex, DecisionVertex) else None
                      for vertex in topology.vertices)
        for occurrence in topology.iter_occurrences():
            node = topology.vertices[occurrence.vertex_id]
            if isinstance(node, DecisionVertex):
                menu = menus[occurrence.vertex_id]
                for hand in range(operator.hand_counts[node.player]):
                    key = (node.player, hand, occurrence.history)
                    if key in metadata:
                        metadata[key] = menu
        node = menu = occurrence = menus = None
        root = None
        training_root, anchor, view_states = shared_view.root, shared_view.anchor, 0
        chance_type = ChanceCursor
        census["shared_public_topology"] = asdict(topology.census)
        census["shared_strategy_storage"] = shared_layout
        topology = None
    else:
        training_root, anchor, view_states = reference._positive_pot_training_view(root)
    operator.pot = 2 * anchor
    marginals = _Marginals(operator)
    native_training = None
    try:
        if native_executable is not None:
            from .native_selected_operator import train_native_selected, executable_identity
            if infos:
                averages, native_training = train_native_selected(
                    training_root, infos, request.iterations, operator=operator, executable=native_executable)
                for name, expected in census["native_operator_admission"].items():
                    if native_training[name] != expected:
                        raise RuntimeError("Native operator preparation changed from admission.")
                native_training["calls"] = 1
            else:
                native_training = {"calls": 0, "reason": "no-information-sets",
                                   "identity": executable_identity(native_executable)}
                averages = {}
        elif strategy_storage == "packed" and infos:
            from .packed_operator_cfr import train_packed
            averages, layout = train_packed(training_root, infos, request.iterations,
                                            operator=operator, marginals=marginals, return_receipt=True,
                                            shared_view=shared_view)
            expected_layout = (census["shared_strategy_storage"] if shared_view is not None
                               else census["strategy_storage"])
            if layout != expected_layout:
                raise RuntimeError("Packed training view and admitted source layout differ.")
        else:
            averages = (_train_prepared(
            training_root, infos, request.iterations, request.algorithm,
            pot=operator.pot, chance_type=_Chance, hand_counts=operator.hand_counts,
                edges={}, marginals=marginals, prefix_kernel=operator) if infos else {})
        policies, _ = _normalize_policies(averages)
        value, br0, br1 = _evaluate_prepared(
            training_root, policies, pot=operator.pot, chance_type=chance_type,
            hand_counts=operator.hand_counts, edges={}, marginals=marginals,
            prefix_kernel=operator)
    finally:
        training_root = None
        shared_view = None
        operator.clear_rank_cache()
    if not all(isfinite(x) for x in (value, br0, br1)):
        raise ValueError("Operator diagnostics returned a nonfinite value.")
    rows = []
    serialization_keys = sorted(infos)
    info_count = len(infos)
    if strategy_storage == "packed":
        # Diagnostics are complete. Do not overlap obsolete policy/lookup
        # dictionaries and the original tree root with complete JSON rows.
        policies = None
        infos.clear()
        root = None
    for key in serialization_keys:
        player, hand, history = key
        node = metadata.pop(key) if strategy_storage == "packed" else metadata[key]
        probabilities = averages.pop(key) if strategy_storage == "packed" else averages[key]
        board = reference._revealed_board(history)
        rows.append({
            "player": "sb" if player == 0 else "bb", "hand": "".join(operator.hands[player][hand]),
            "street": {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(board)],
            "revealed_board": list(board), "history": list(history),
            "actions": [{"name": a.name, "amount": a.amount, "raise_to": a.raise_to,
                         "history_key": a.token, "probability": p}
                        for a, p in zip(node.actions, probabilities)],
        })
    serialization_keys = None
    gain0, gain1 = max(0.0, br0 - value), max(0.0, br1 + value)
    pair_probabilities = operator.pair_probabilities()
    reachable = operator.reachable_selected()
    if (operator.query_pair_runout_checks > census["pair_runout_scan_upper_bound"] or
            operator.rank_calls > census["rank_call_upper_bound"]):
        raise RuntimeError("Operator exceeded its admitted work envelope.")
    result = {
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
        "info_sets": info_count, "value_sb": value, "value_bb": -value,
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
    if rank_cache_boards > 1:
        stats = {
            "board_capacity": rank_cache_boards,
            "hits": operator.rank_cache_hits, "misses": operator.rank_cache_misses,
            "evictions": operator.rank_cache_evictions,
            "retained_peak_rank_slots": operator.rank_cache_retained_peak_entries,
            "retained_plus_construction_peak_reference_slots": operator.rank_scratch_peak,
            "released_after_diagnostics": True,
        }
        if stats["hits"] + stats["misses"] > census["rank_cache_admission"]["lookup_upper_bound"]:
            raise RuntimeError("Rank cache exceeded its admitted lookup bound.")
        result["rank_cache"] = stats
    if strategy_storage == "packed":
        result["strategy_storage"] = "packed-binary64-cfrplus-v1"
        result["execution_backend"] = "selected-operator-packed-python"
    if native_training is not None:
        result["native_training"] = native_training
        result["execution_backend"] = ("selected-operator-packed-cpp" if native_training["calls"]
                                        else "selected-operator-python-no-information-sets")
        result["operator_statistics"]["scope"] = "Python preparation/diagnostics only; native counters are reported separately."
    if public_topology == "shared":
        result["public_topology"] = "shared-public-topology-v1"
        result["execution_backend"] = "selected-operator-packed-shared-python"
    return result
