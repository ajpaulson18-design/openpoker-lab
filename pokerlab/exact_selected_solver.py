"""Explicit four-street CFR+ integration for exact-product selected chance.

This is a new finite-game law.  The direct public DAG is the only topology;
the packed shared-view trainer consumes exact-kernel callbacks rounded once
under ``exact-product-vectors-binary64-v1``. Default expanded diagnostics retain
a separate quadratic pair stage; explicit compact diagnostics snapshot priors
linearly. Optional suit-quotient storage shares only verified strategy-row
orbits under the explicit equivariant arithmetic contract. Modeled work/entry
units are admission counters, not CPU, allocator, or RSS claims.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from math import ceil, isfinite, log2
from sys import float_info

from . import preflop_solver as reference
from .direct_shared_topology import build_direct_shared_topology
from .exact_selected_float_adapter import (
    CONVERSION_CONTRACT, ExactSelectedFloatAdapter,
)
from .exact_selected_kernel import ExactSelectedKernelLimits, ExactSelectedRunoutKernel
from .packed_operator_cfr import train_packed
from .preflop_solver import _revealed_board
from .public_diagnostics import _evaluate_prepared, _normalize_policies
from .shared_public_topology import DecisionVertex, TerminalVertex
from .shared_topology_view import ChanceCursor, SharedPublicView, layout_census_shared
from .solver_contracts import FourStreetSolveRequest


MAX_WHOLE_REQUEST_WORK = 500_000_000
MAX_OUTPUT_ENTRIES = 2_000_000
MAX_PAIR_CANDIDATES = 1_800_000
MAX_PAIR_BOARD_SCANS = 30_000_000
MAX_WHOLE_REQUEST_ENTRIES = 25_000_000
MAX_DYADIC_INTEGER_PAYLOAD_BITS = 1 << 30


@dataclass(frozen=True, slots=True)
class _ExactSelectedPreparation:
    """Admitted, rank-free preparation shared by solve and census callers."""

    kernel: object
    specs: object
    topology: object
    direct_receipt: object
    view: object
    adapter: object
    reachable: object
    prefix_counts: object
    unique_prefixes: object
    decisions: object
    action_hand_queries: object
    terminal_counts: object
    layout_upper: object
    admission: object
    bit_forecast: object
    action_slots_upper: int
    pair_candidates: int
    output_pairs: int
    iterations: int


def _tokens(board):
    return (() if not board else
            ("".join(board[:3]),) + tuple(board[3:]))


def _strict_float(value, label):
    if type(value) is not Fraction:
        raise TypeError(f"{label} must be an exact Fraction.")
    if value == 0:
        return 0.0
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} is not representable as finite normal binary64.") from exc
    if not isfinite(result) or abs(result) < float_info.min:
        raise ValueError(f"Nonzero {label} converts to zero, subnormal, or nonfinite binary64.")
    return result


class _OnePrefixMarginals(Mapping):
    """At most one exact-converted marginal vector is retained at a time."""
    __slots__ = ("adapter", "marker", "value")

    def __init__(self, adapter):
        self.adapter, self.marker, self.value = adapter, None, None

    def __getitem__(self, prefix):
        if prefix != self.marker:
            self.value = self.adapter.joint_marginals(prefix)
            self.marker = prefix
        return self.value

    def __iter__(self):
        raise TypeError("Exact marginal vectors are queried by prefix, not enumerated.")

    def __len__(self):
        raise TypeError("The exact marginal map is not materialized.")


def _validate_request(request, rank_cache_boards, kernel_limits, pair_diagnostics, exact_arithmetic,
                      training_reduction="default", strategy_storage="expanded"):
    if type(strategy_storage) is not str or strategy_storage not in ("expanded", "suit-quotient"):
        raise ValueError("strategy_storage must be expanded or suit-quotient.")
    if strategy_storage == "suit-quotient" and training_reduction != "suit-equivariant":
        raise ValueError("Suit-quotient strategy storage requires explicit suit-equivariant training_reduction.")
    if type(training_reduction) is not str or training_reduction not in ("default", "suit-equivariant"):
        raise ValueError("training_reduction must be default or suit-equivariant.")
    if type(exact_arithmetic) is not str or exact_arithmetic not in ("fraction", "dyadic"):
        raise ValueError("exact_arithmetic must be fraction or dyadic.")
    if pair_diagnostics not in ("expanded", "compact"):
        raise ValueError("pair_diagnostics must be expanded or compact.")
    if not isinstance(request, FourStreetSolveRequest):
        raise TypeError("request must be a FourStreetSolveRequest.")
    if (request.algorithm != "cfrplus" or request.traversal != "public-batched" or
            request.diagnostics != "public-batched" or request.resource_model != "public-vector"):
        raise ValueError("Exact selected solving requires CFR+, public-batched training/diagnostics, and public-vector resources.")
    if type(request.iterations) is not int or not 10 <= request.iterations <= 10_000:
        raise ValueError("Exact selected solving supports 10 through 10,000 iterations.")
    if type(rank_cache_boards) is not int or not 1 <= rank_cache_boards <= 64:
        raise ValueError("rank_cache_boards must be an integer from 1 through 64.")
    if kernel_limits is not None and not isinstance(kernel_limits, ExactSelectedKernelLimits):
        raise TypeError("kernel_limits must be ExactSelectedKernelLimits or None.")
    # The kernel has the stricter 64-board limit.  Reject here, before its
    # constructor parses ranges or allocates snapshots.
    if len(request.runouts) > 64:
        raise ValueError("Exact selected solving supports at most 64 selected runouts.")


def _binary64_reach_bit_forecast(kernel, payoff_fractions, board_count):
    """Conservative pre-training analogue of the kernel reach bit forecast.

    Any binary64 strategy/reach entry has at most 53 numerator bits and 1,075
    denominator bits. Priors and callback reaches are dyadic Fractions, so
    every denominator is a power of two and their LCM is their maximum, not
    the product or a sum over hands. Numerator growth includes the sum over
    all opponent hands; payoff and board accumulation are included below.
    """
    limit = kernel.limits.max_integer_bits
    h0, h1 = kernel.hand_counts
    normalizer = kernel.normalizer
    player_forecasts = []
    for player, own_count, opp_count in ((0, h0, h1), (1, h1, h0)):
        own, opp = kernel.weights[player], kernel.weights[1-player]
        own_den_bits = max((w.denominator.bit_length() for w in own), default=1)
        opp_den_bits = max((w.denominator.bit_length() + 1075 for w in opp), default=1075)
        max_product_num = max((w.numerator.bit_length() + 53 for w in opp), default=1)
        opp_sum_num = (max_product_num + opp_den_bits +
                       ceil(log2(max(1, opp_count))) + 2)
        max_pay_num = max((p.numerator.bit_length() for p in payoff_fractions), default=1)
        max_pay_den = max((p.denominator.bit_length() for p in payoff_fractions), default=1)
        raw_den = opp_den_bits + own_den_bits + max_pay_den
        raw_num = (opp_sum_num + max((w.numerator.bit_length() for w in own), default=1) +
                   max_pay_num + ceil(log2(max(1, board_count))) + 3)
        final_num = raw_num + normalizer.denominator.bit_length()
        final_den = raw_den + normalizer.numerator.bit_length()
        forecast = max(opp_sum_num, raw_den, raw_num, final_num, final_den)
        player_forecasts.append(forecast)
        if forecast > limit:
            raise ValueError(
                "Exact selected solver binary64-reach Fraction forecast exceeds the configured integer-bit limit.")
    return {"version": "binary64-reach-fraction-bit-forecast-v1",
            "worst_reach_numerator_bits": 53, "worst_reach_denominator_bits": 1075,
            "opponent_denominator_lcm_bound_bits": max(
                max(w.denominator.bit_length() + 1075 for w in kernel.weights[side])
                for side in (0, 1)),
            "payoff_fraction_max_numerator_bits": max(
                (p.numerator.bit_length() for p in payoff_fractions), default=1),
            "payoff_fraction_max_denominator_bits": max(
                (p.denominator.bit_length() for p in payoff_fractions), default=1),
            "board_accumulation_bound": board_count,
            "per_player_max_intermediate_bits_upper": player_forecasts,
            "maximum_intermediate_bits_upper": max(player_forecasts),
            "admitted_integer_bits": limit,
            "scope": "Conservative pre-training rational size forecast; dyadic reach-product denominators use their maximum exponent for the LCM bound."}


def _query_costs(kernel, prefix_boards):
    boards = len(kernel.selected)
    hsum = sum(kernel.hand_counts)
    sort_work = hsum * (ceil(log2(max(2, hsum))) + 1)
    lookup = 64 + 8 * boards
    return {
        "lookup": lookup,
        "legal_per_board": 24 * hsum + 104,
        "marginal_per_board": 20 * hsum + 260,
        "terminal_fixed": 16 + lookup,
        "terminal_per_board": 200 * hsum + 520 + sort_work,
        "terminal_reach": 4 * max(kernel.hand_counts),
        "pair_fixed": 16 + lookup + 2,
        "pair_per_board": 4,
        "sort_work": sort_work,
    }


def _dyadic_reach_bit_forecast(kernel, payoff_fractions, board_count):
    """Admit common-exponent integer buffers for every binary64 callback.

    This adds a logical integer-payload ceiling, while retaining the existing
    conservative logical-loop and Fraction-size admission. It is not a new
    cheaper work model and cannot reopen a request rejected by that model.
    """
    exponents = [[w.denominator.bit_length() - 1 for w in side] for side in kernel.weights]
    side_exponents = [max(side) for side in exponents]
    weight_bits = [max(w.numerator.bit_length() + common - exp
                      for w, exp in zip(weights, powers))
                   for weights, powers, common in zip(kernel.weights, exponents, side_exponents)]
    z_bits = (kernel.normalizer.numerator.bit_length() + sum(side_exponents) -
              (kernel.normalizer.denominator.bit_length() - 1))
    setup_bits = max(*weight_bits, z_bits, sum(side_exponents) + 1)
    payoff_num_bits = max((abs(p.numerator).bit_length() for p in payoff_fractions), default=1)
    payoff_exp = max((p.denominator.bit_length() - 1 for p in payoff_fractions), default=0)
    forecasts = []
    for player in (0, 1):
        opp = 1 - player
        weighted = weight_bits[opp] + 1075
        bucket = weighted + ceil(log2(max(1, kernel.hand_counts[opp]))) + 2
        signed = bucket + 4
        own_product = weight_bits[player] + signed + payoff_num_bits
        summed = own_product + ceil(log2(max(1, board_count))) + 2
        denominator = z_bits + 1074 + payoff_exp
        forecasts.append(max(1075, weighted, bucket, signed, own_product, summed, denominator, z_bits))
    maximum = max(setup_bits, *forecasts)
    if maximum > kernel.limits.max_integer_bits:
        raise ValueError("Dyadic selected whole-request integer-bit forecast exceeded before training.")
    hsum = sum(kernel.hand_counts)
    retained = 8 * hsum + 128
    scratch = 140 * hsum + 800
    payload = retained * setup_bits + scratch * maximum
    if payload > MAX_DYADIC_INTEGER_PAYLOAD_BITS:
        raise ValueError("Dyadic selected whole-request integer-payload admission exceeded before training.")
    return {"version": "dyadic-binary64-callback-bit-forecast-v1",
            "side_weight_max_bits": weight_bits, "normalizer_bits": z_bits,
            "setup_maximum_bits_upper": setup_bits,
            "worst_common_reach_exponent": 1074, "worst_scaled_reach_bits": 1075,
            "per_player_maximum_bits_upper": forecasts, "maximum_bits_upper": maximum,
            "retained_integer_entries_upper": retained, "scratch_integer_entries_upper": scratch,
            "logical_integer_payload_bits_upper": payload,
            "logical_integer_payload_bit_limit": MAX_DYADIC_INTEGER_PAYLOAD_BITS,
            "limbs64_per_value_upper": (maximum + 63) // 64,
            "scope": "Integer payload only, excluding Python headers/allocator and retained Fraction reference inputs. Conservative old logical work admission remains in force; no CPU/RSS guarantee."}


def _layout_upper(topology, kernel, request, layout_counts):
    """Pre-info upper bound matching layout_census_shared's documented units."""
    from .packed_operator_cfr import (
        MAX_ACTION_SLOTS, MAX_DENSE_DECISION_HAND_SLOTS, MAX_LAYOUT_LOOP_ENTRIES,
        MAX_PUBLIC_STATES, MAX_DEPTH,
    )
    hsum = sum(kernel.hand_counts)
    slots = layout_counts["slots"]
    dense = layout_counts["dense"]
    width = layout_counts["width"]
    lookup = layout_counts["lookup"]
    history_entries = layout_counts["history_entries"]
    history_bytes = layout_counts["history_bytes"]
    maximum_actions = layout_counts["maximum_actions"]
    states = topology.census.expanded_logical_visits
    if slots > MAX_ACTION_SLOTS or dense > MAX_DENSE_DECISION_HAND_SLOTS or states > MAX_PUBLIC_STATES:
        raise ValueError("Exact selected direct topology exceeds existing packed public-vector slots/states.")
    if topology.census.maximum_depth > MAX_DEPTH:
        raise ValueError("Exact selected direct topology exceeds existing packed history depth.")
    vector = 12 * hsum * (width + states)
    loops = (request.iterations * (32 * slots + vector) +
             8 * slots + 4 * dense + 4 * states)
    history_work = ((3 * request.iterations + 3 * maximum_actions + 16) * lookup +
                    8 * history_entries + history_bytes)
    if loops > MAX_LAYOUT_LOOP_ENTRIES or history_work > 500_000_000:
        raise ValueError("Exact selected packed topology exceeds the existing requested layout/history envelope.")
    return {"upper_action_slots": slots, "upper_dense_decision_hand_slots": dense,
            "upper_decision_width": width, "upper_vector_entries": vector,
            "upper_requested_layout_loop_entries": loops,
            "upper_history_lookup_work_entries": history_work,
            "upper_history_token_entries": history_entries,
            "upper_history_token_bytes": history_bytes,
            "maximum_actions": maximum_actions,
            "maximum_depth": topology.census.maximum_depth,
            "limits": {"action_slots": MAX_ACTION_SLOTS,
                       "dense_decision_hand_slots": MAX_DENSE_DECISION_HAND_SLOTS,
                       "public_states": MAX_PUBLIC_STATES,
                       "layout_loop_entries": MAX_LAYOUT_LOOP_ENTRIES,
                       "history_lookup_work_entries": 500_000_000}}


def _preflight_work(kernel, adapter, request, prefix_counts, decision_counts,
                    action_hand_queries, terminal_counts, pair_candidates,
                    layout_upper, unique_prefixes, topology_states,
                    topology_entries, compact_prior_entries=0):
    costs = _query_costs(kernel, prefix_counts)
    # Setup support queries and complete legacy-compatible pair output.
    future_kernel = sum(costs["lookup"] + n * costs["legal_per_board"]
                        for n in unique_prefixes.values())
    board_count = prefix_counts[()]
    pair_cost = costs["pair_fixed"] + board_count * costs["pair_per_board"]
    pair_work = pair_candidates * pair_cost
    # Training average marginal calls: one per logical decision occurrence
    # per sweep. Diagnostic missing-policy lookups: three traversals, and for
    # each action/own-hand fallback lookup, regardless of wrapper cache hits.
    marginal_work = 0
    marginal_calls = 0
    effective_iterations = request.iterations if sum(decision_counts.values()) else 0
    for prefix, count in decision_counts.items():
        calls = effective_iterations * count + 3 * action_hand_queries[prefix]
        marginal_calls += calls
        bp = prefix_counts.get(prefix, 0)
        marginal_work += calls * (costs["lookup"] + bp * costs["marginal_per_board"])
    # CFR+ performs two responder traversals per iteration; diagnostics are
    # bounded as six terminal passes, all weighted by prefix-matching boards.
    terminal_work = terminal_calls = 0
    for prefix, count in terminal_counts.items():
        calls = (2 * effective_iterations + 6) * count
        terminal_calls += calls
        bp = prefix_counts.get(prefix, 0)
        terminal_work += calls * (costs["terminal_fixed"] +
                                  bp * costs["terminal_per_board"] +
                                  costs["terminal_reach"])
    kernel_total = kernel.statistics()["work_units_cumulative"] + future_kernel + pair_work + marginal_work + terminal_work
    kernel_limit = kernel.limits.max_modeled_work
    if kernel_total > kernel_limit:
        raise ValueError("Exact selected whole-request kernel work admission exceeded before information/training allocation.")

    vertices = len(adapter._vertices)
    terminal_vertices = len(adapter._records)
    hsum = sum(kernel.hand_counts)
    adapter_base = 8 * vertices + 8
    adapter_retained = 8 * terminal_vertices + 2 * hsum + 16
    adapter_call_cost = 8 + 4 * hsum
    adapter_calls = marginal_calls + terminal_calls
    adapter_work = adapter_base + adapter_call_cost * adapter_calls
    adapter_temp = 2 * hsum
    if adapter_work > adapter._max_work or adapter_retained + adapter_temp > adapter._max_storage:
        raise ValueError("Exact selected whole-request adapter work/storage admission exceeded before training.")

    output_entries = (compact_prior_entries + 8 * pair_candidates + 20 * layout_upper["upper_dense_decision_hand_slots"] +
                      2 * layout_upper["upper_history_token_entries"] +
                      12 * layout_upper["upper_action_slots"] + 8192)
    if output_entries > MAX_OUTPUT_ENTRIES:
        raise ValueError("Exact selected serialized pair/policy output entry limit exceeded before training.")
    if pair_candidates > MAX_PAIR_CANDIDATES:
        raise ValueError("Exact selected pair-output candidate limit exceeded before training.")
    compact_snapshot_work = 4 * compact_prior_entries
    whole_work = (kernel_total + adapter_work + compact_snapshot_work +
                  layout_upper["upper_requested_layout_loop_entries"] +
                  layout_upper["upper_history_lookup_work_entries"] +
                  4 * topology_states)
    if whole_work > MAX_WHOLE_REQUEST_WORK:
        raise ValueError("Exact selected whole-request modeled work admission exceeded before information/training allocation.")
    hsum = sum(kernel.hand_counts)
    rows = layout_upper["upper_dense_decision_hand_slots"]
    slots = layout_upper["upper_action_slots"]
    prefixes = len(prefix_counts)
    kernel_peak = max(
        kernel.statistics()["storage_entries_peak"],
        kernel._input_entries + kernel._cache_reserved_entries + 140 * hsum + 800)
    adapter_peak = adapter._retained + 2 * hsum
    # Count all selected prefixes, including prefixes with terminals but no
    # decision rows. Include map entries, keys and bounded bookkeeping slots.
    prefix_counters = 64 * prefixes + 8192
    legal_support = len(unique_prefixes) * (2 * hsum + 8)
    pair_output_entries = 8 * pair_candidates
    shared_base = (kernel_peak + adapter_peak + topology_entries + prefix_counters +
                   pair_output_entries + compact_prior_entries)
    histories = layout_upper["upper_history_token_entries"]
    info_and_menus = 12 * rows + histories
    packed_training = 4 * slots + 12 * rows
    averages = 3 * rows + slots
    normalized_policies = 3 * rows + slots
    depth = layout_upper["maximum_depth"] + 1
    actions = layout_upper["maximum_actions"]
    # Parent action vectors, row-offset/probability temporaries, reach vectors,
    # cursor histories and traversal frames coexist along a bounded path.
    callback_scratch = (depth * (4 * actions + 24) * hsum +
                        4 * depth * depth * (actions + 1) + 256)
    serialized_rows = 20 * rows + 2 * histories + 12 * slots + 8192
    phase_entries = {
        "rank_free_prefix_support_peak": shared_base + legal_support,
        "information_and_menu_peak": shared_base + legal_support + info_and_menus,
        "training_peak": shared_base + info_and_menus + packed_training + averages + callback_scratch,
        "diagnostic_peak": shared_base + info_and_menus + averages + normalized_policies + callback_scratch,
        "serialization_peak": shared_base + info_and_menus + averages + serialized_rows,
    }
    retained_peak = max(phase_entries.values())
    if retained_peak > MAX_WHOLE_REQUEST_ENTRIES:
        raise ValueError("Exact selected whole-request retained/scratch entry admission exceeded before pair or information allocation.")
    return {"version": "exact-product-selected-four-street-admission-v1",
            "kernel": {"constructor_and_rank_free_support_actual_work": kernel.statistics()["work_units_cumulative"],
                       "future_legal_support_upper_work": future_kernel,
                       "serialized_pair_candidate_board_scan_upper_work": pair_work,
                       "training_and_diagnostic_marginal_upper_work": marginal_work,
                       "training_and_diagnostic_terminal_upper_work": terminal_work,
                       "whole_request_upper_work": kernel_total,
                       "configured_limit": kernel_limit,
                       "terminal_calls_upper": terminal_calls,
                       "marginal_calls_upper": marginal_calls},
            "adapter": {"constructor_work_upper": adapter_base,
                        "terminal_and_marginal_calls_upper": adapter_calls,
                        "whole_request_work_upper": adapter_work,
                        "retained_entries_upper": adapter_retained,
                        "temporary_peak_entries_upper": adapter_temp,
                        "configured_work_limit": adapter._max_work,
                        "configured_entry_limit": adapter._max_storage},
            "pair_output": {"candidate_pairs_scanned": pair_candidates,
                            "board_scan_work_upper": pair_work,
                            "output_entry_upper": 8 * pair_candidates,
                            "quadratic_diagnostic_stage": True},
            "retained_storage": {"version": "exact-product-selected-retained-entries-v1",
                                 "kernel_peak_upper": kernel_peak,
                                 "adapter_peak_upper": adapter_peak,
                                 "direct_topology_vertices_plus_edges": topology_entries,
                                 "prefix_counters_upper": prefix_counters,
                                 "legal_support_entries_upper": legal_support,
                                 "pair_output_entries_upper": pair_output_entries,
                                 "compact_prior_snapshot_entries_upper": compact_prior_entries,
                                 "information_and_menu_entries_upper": info_and_menus,
                                 "packed_numeric_and_lookup_entries_upper": packed_training,
                                 "average_rows_entries_upper": averages,
                                 "normalized_policy_entries_upper": normalized_policies,
                                 "callback_scratch_entries_upper": callback_scratch,
                                 "serialized_strategy_entries_upper": serialized_rows,
                                 "phase_upper_bounds": phase_entries,
                                 "whole_request_peak_upper": retained_peak,
                                 "entry_limit": MAX_WHOLE_REQUEST_ENTRIES,
                                 "scope": "Logical retained and scratch slots across overlapping solve phases; not Python bytes or RSS."},
            "packed_layout": layout_upper,
            "direct_topology_occurrence_walk_upper": 4 * topology_states,
            "compact_input_snapshot_work_upper": compact_snapshot_work,
            "combined_modeled_work_upper": whole_work,
            "whole_request_limit": MAX_WHOLE_REQUEST_WORK,
            "scope": "Whole-request logical bounds include exact kernel rank/card sweeps, pair diagnostic board scans, adapter conversions, direct-topology occurrence traversal, packed layout/training loops, semantic-history lookup and serialized entries. Units are not runtime or memory bytes."}


def _prepare_exact_selected(request, *, rank_cache_boards=1, kernel_limits=None,
                            pair_diagnostics="expanded", exact_arithmetic="fraction",
                            training_reduction="default", strategy_storage="expanded"):
    """Build and admit the direct exact-selected solve without ranking or rows.

    This shared preparation stage preserves every existing input, topology,
    layout, bit, work, and retained-entry guard in its original order. It does
    not issue pair-probability queries, rank hands, allocate information rows,
    or enter training.
    """
    _validate_request(request, rank_cache_boards, kernel_limits, pair_diagnostics, exact_arithmetic,
                      training_reduction, strategy_storage)
    kernel = ExactSelectedRunoutKernel(request.sb_range, request.bb_range,
                                       request.runouts,
                                       rank_cache_boards=rank_cache_boards,
                                       limits=kernel_limits, arithmetic=exact_arithmetic)
    specs = reference._stage_configs(
        request.flop_actions.to_dict(),
        None if request.turn_actions is None else request.turn_actions.to_dict(),
        None if request.river_actions is None else request.river_actions.to_dict())
    reachable = kernel.reachable_selected()
    if not reachable:
        raise ValueError("Exact selected ranges have no reachable complete board.")
    topology, direct_receipt = build_direct_shared_topology(
        request.preflop_config, specs, reachable)
    view = SharedPublicView(topology)
    adapter = ExactSelectedFloatAdapter(kernel, view)

    prefix_counts = {(): len(kernel.selected)}
    for flop, turn, river in kernel.selected:
        prefix_counts[("".join(flop),)] = prefix_counts.get(("".join(flop),), 0) + 1
        prefix_counts[("".join(flop), turn)] = prefix_counts.get(("".join(flop), turn), 0) + 1
        prefix_counts[("".join(flop), turn, river)] = prefix_counts.get(
            ("".join(flop), turn, river), 0) + 1

    decisions = Counter()
    action_hand_queries = Counter()
    terminal_counts = Counter()
    layout_counts = {"slots": 0, "dense": 0, "width": 0, "lookup": 0,
                     "history_entries": 0, "history_bytes": 0,
                     "maximum_actions": 1}
    infos_upper = action_slots_upper = 0
    for occurrence in topology.iter_occurrences():
        vertex = topology.vertices[occurrence.vertex_id]
        prefix = _tokens(_revealed_board(occurrence.history))
        if isinstance(vertex, DecisionVertex):
            decisions[prefix] += 1
            action_hand_queries[prefix] += len(vertex.actions) * kernel.hand_counts[vertex.player]
            hand_count = kernel.hand_counts[vertex.player]
            action_count = len(vertex.actions)
            infos_upper += hand_count
            action_slots_upper += hand_count * action_count
            layout_counts["slots"] += hand_count * action_count
            layout_counts["dense"] += hand_count
            layout_counts["width"] += action_count + 1
            layout_counts["lookup"] += hand_count * (len(occurrence.history) + 3)
            layout_counts["history_entries"] += hand_count * len(occurrence.history)
            layout_counts["history_bytes"] += hand_count * sum(
                len(x.encode("utf-8")) for x in occurrence.history)
            layout_counts["maximum_actions"] = max(layout_counts["maximum_actions"], action_count)
        elif isinstance(vertex, TerminalVertex):
            terminal_counts[prefix] += 1
        if prefix not in prefix_counts:
            raise RuntimeError("Direct topology produced a history outside selected-board prefixes.")
    layout_upper = _layout_upper(topology, kernel, request, layout_counts)
    if action_slots_upper > layout_upper["upper_action_slots"] or infos_upper > 2_000_000:
        raise ValueError("Exact selected information-row/output capacity exceeded before allocation.")

    # Snapshot original terminal scale Fractions and preflight every possible
    # binary64 reach denominator before constructing information rows/training.
    payoffs = []
    for vertex in topology.vertices:
        if isinstance(vertex, TerminalVertex):
            payoffs.append(Fraction.from_float(float(min(vertex.contributions))))
    bit_forecast = _binary64_reach_bit_forecast(kernel, payoffs, len(kernel.selected))
    if exact_arithmetic == "dyadic":
        bit_forecast["dyadic_integer"] = _dyadic_reach_bit_forecast(kernel, payoffs, len(kernel.selected))
    payoffs = None

    # Pair probabilities are an explicitly bounded O(H0*H1*B) compatibility
    # diagnostic. They are computed and strict-conversion checked before CFR,
    # so support loss can never be discovered after spending training work.
    h0, h1 = kernel.hand_counts
    pair_candidates = h0 * h1
    output_pairs = pair_candidates if pair_diagnostics == "expanded" else 0
    if output_pairs > MAX_PAIR_CANDIDATES:
        raise ValueError("Exact selected pair-output candidate limit exceeded before training.")
    if output_pairs * len(kernel.selected) > MAX_PAIR_BOARD_SCANS:
        raise ValueError("Exact selected pair-output board-scan cap exceeded before training.")
    unique_prefixes = {prefix: prefix_counts[prefix] for prefix in decisions}
    layout_upper["upper_action_slots"] = action_slots_upper
    admission = _preflight_work(kernel, adapter, request, prefix_counts,
                                decisions, action_hand_queries, terminal_counts,
                                output_pairs, layout_upper, unique_prefixes,
                                topology.census.expanded_logical_visits,
                                32 * len(topology.vertices) + 16 * topology.census.unique_edges + 8192,
                                compact_prior_entries=(6 * sum(kernel.hand_counts) + 32
                                    if pair_diagnostics == "compact" else 0))
    if exact_arithmetic == "dyadic":
        integer_forecast = bit_forecast["dyadic_integer"]
        integer_forecast["whole_request_limb_work_upper"] = (
            admission["kernel"]["whole_request_upper_work"] *
            integer_forecast["limbs64_per_value_upper"] ** 2)
        integer_forecast["limb_work_scope"] = (
            "Existing conservative logical kernel-operation upper times worst admitted 64-bit limb width squared; "
            "an envelope for the counted integer query-core/completed Fraction-output subset model only. "
            "It excludes Fraction GCD/LCM input/bit preflights, setup normalization, adapter conversion and runtime; "
            "not a complete arithmetic/CPU bound or smaller replacement admission.")
    if training_reduction == "suit-equivariant":
        # Preflight uses no information dictionary and precedes every pair/
        # information-row/training allocation. The later explicit layout and
        # trainer each repeat the bounded extra census: reserve three scans.
        from .equivariant_packed_cfr import equivariant_additional_census, NUMERICAL_REDUCTION
        extra = equivariant_additional_census(view, kernel.hand_counts, request.iterations)
        extra_work = extra["modeled_work_upper"] + 2 * extra["setup_work_upper"]
        combined = admission["combined_modeled_work_upper"] + extra_work
        if combined > MAX_WHOLE_REQUEST_WORK:
            raise ValueError("Equivariant exact selected whole-request additional work admission exceeded before information/training allocation.")
        retained = admission["retained_storage"]
        phases = {name: value + extra["additional_retained_entries_upper"]
                  for name, value in retained["phase_upper_bounds"].items()}
        peak = max(phases.values())
        if peak > MAX_WHOLE_REQUEST_ENTRIES:
            raise ValueError("Equivariant exact selected whole-request phase storage admission exceeded before information/training allocation.")
        admission["retained_storage"] = {**retained, "phase_upper_bounds": phases,
            "whole_request_peak_upper": peak,
            "equivariant_extra_entries_upper": extra["additional_retained_entries_upper"]}
        admission["equivariant_additional_admission"] = {**extra,
            "setup_census_passes_reserved": 3,
            "whole_request_additional_work_upper": extra_work,
            "numerical_reduction": NUMERICAL_REDUCTION}
        admission["combined_modeled_work_upper"] = combined
    return _ExactSelectedPreparation(
        kernel=kernel, specs=specs, topology=topology, direct_receipt=direct_receipt, view=view,
        adapter=adapter, reachable=reachable, prefix_counts=prefix_counts,
        unique_prefixes=unique_prefixes, decisions=decisions,
        action_hand_queries=action_hand_queries, terminal_counts=terminal_counts,
        layout_upper=layout_upper, admission=admission, bit_forecast=bit_forecast,
        action_slots_upper=action_slots_upper, pair_candidates=pair_candidates,
        output_pairs=output_pairs, iterations=request.iterations)


def solve_four_street_exact_selected(request, *, rank_cache_boards=1, kernel_limits=None,
                                    pair_diagnostics="expanded", exact_arithmetic="fraction",
                                    training_reduction="default", strategy_storage="expanded"):
    """Solve one bounded four-street game under exact-product selected chance.

    Requires CFR+, direct shared topology, packed public-vector training, and
    public-batched diagnostics. The exact prior law differs from legacy
    per-occurrence binary64 normalization; this API never silently replaces
    the legacy solver.

    Suit-quotient storage additionally requires the explicit equivariant
    reduction; it verifies whole-game suit closure and every member increment.
    Complete policy output and independent diagnostics remain expanded.
    """
    prepared = _prepare_exact_selected(request, rank_cache_boards=rank_cache_boards,
                                       kernel_limits=kernel_limits,
                                       pair_diagnostics=pair_diagnostics,
                                       exact_arithmetic=exact_arithmetic,
                                       training_reduction=training_reduction, strategy_storage=strategy_storage)
    quotient_plan = None
    quotient_receipt = None
    if strategy_storage == "suit-quotient":
        from .suit_quotient_plan import SuitQuotientPlan
        quotient_plan = SuitQuotientPlan(prepared, request.iterations)
        quotient_receipt = quotient_plan.receipt
        # The plan independently rejects against remaining whole-request work
        # and retained entries before support/row allocation. Credit no savings
        # against the old expanded bounds; report its additional costs instead.
        prepared.admission["combined_modeled_work_upper"] += quotient_receipt["whole_request_additional_work_upper"]
        retained = prepared.admission["retained_storage"]
        extra_entries = quotient_receipt["whole_request_additional_entries_upper"]
        phases = {name: value + extra_entries for name, value in retained["phase_upper_bounds"].items()}
        prepared.admission["retained_storage"] = {**retained,
            "phase_upper_bounds": phases, "whole_request_peak_upper": max(phases.values()),
            "suit_quotient_extra_entries_upper": extra_entries}
        prepared.admission["suit_quotient_additional_admission"] = quotient_plan.admission
    kernel, specs, topology, direct_receipt = (prepared.kernel, prepared.specs,
                                               prepared.topology, prepared.direct_receipt)
    view, adapter, reachable = prepared.view, prepared.adapter, prepared.reachable
    unique_prefixes = prepared.unique_prefixes
    layout_upper, admission, bit_forecast = (prepared.layout_upper, prepared.admission,
                                             prepared.bit_forecast)
    action_slots_upper, pair_candidates, output_pairs = (prepared.action_slots_upper,
                                                          prepared.pair_candidates,
                                                          prepared.output_pairs)
    del prepared
    h0, h1 = kernel.hand_counts
    pair_rows = []
    supported_pair_count = 0
    for i in range(h0 if pair_diagnostics == "expanded" else 0):
        for j in range(h1):
            probability = kernel.pair_probability_exact(i, j)
            if probability:
                supported_pair_count += 1
                pair_rows.append({"sb_hand": "".join(kernel.hands[0][i]),
                                  "bb_hand": "".join(kernel.hands[1][j]),
                                  "probability": _strict_float(probability, "exact pair probability")})
    if len(pair_rows) != supported_pair_count:
        raise RuntimeError("Exact pair output lost positive support.")

    # Rank-free legal support is queried only after the whole-request kernel,
    # adapter, layout and output envelopes have passed.
    infos, menus = {}, {}
    if quotient_plan is None:
        legal_by_prefix = {}
        for prefix in unique_prefixes:
            legal_by_prefix[prefix] = kernel.legal_hands(prefix)
        for occurrence in topology.iter_occurrences():
            vertex = topology.vertices[occurrence.vertex_id]
            if not isinstance(vertex, DecisionVertex):
                continue
            prefix = _tokens(_revealed_board(occurrence.history))
            for hand in sorted(legal_by_prefix[prefix][vertex.player]):
                key = (vertex.player, hand, occurrence.history)
                infos[key] = len(vertex.actions)
                menus[key] = vertex.actions
        legal_by_prefix.clear()
        legal_by_prefix = None
    if sum(infos.values()) > action_slots_upper:
        raise RuntimeError("Exact information rows exceeded the admitted direct-topology upper bound.")
    if quotient_plan is not None:
        from .suit_quotient_cfr import layout_census_suit_quotient, train_suit_quotient
        packed_layout = layout_census_suit_quotient(view, quotient_plan, kernel.hand_counts, request.iterations)
        admitted_extra = {name: value for name, value in
            admission["equivariant_additional_admission"].items() if name not in
            ("setup_census_passes_reserved", "whole_request_additional_work_upper", "numerical_reduction")}
        if packed_layout["equivariant_additional_admission"] != admitted_extra:
            raise RuntimeError("Quotient equivariant layout changed after pre-row admission.")
        trainer = train_suit_quotient
    elif training_reduction == "suit-equivariant":
        from .equivariant_packed_cfr import equivariant_layout_census, train_equivariant_packed
        packed_layout = equivariant_layout_census(view, infos, kernel.hand_counts, request.iterations)
        admitted_extra = {name: value for name, value in
            admission["equivariant_additional_admission"].items() if name not in
            ("setup_census_passes_reserved", "whole_request_additional_work_upper", "numerical_reduction")}
        actual_extra = packed_layout["equivariant_additional_admission"]
        if admitted_extra != actual_extra:
            raise RuntimeError("Equivariant layout changed after pre-row admission.")
        trainer = train_equivariant_packed
    else:
        packed_layout = layout_census_shared(view, infos, kernel.hand_counts, request.iterations)
        trainer = train_packed
    training_root = view.root
    marginals = _OnePrefixMarginals(adapter)
    try:
        if infos or (quotient_plan is not None and quotient_plan.keys):
            averages, training_receipt = trainer(
                training_root, infos if quotient_plan is None else quotient_plan, request.iterations, operator=adapter,
                marginals=marginals, return_receipt=True, shared_view=view)
            if training_receipt != packed_layout:
                raise RuntimeError("Packed training layout changed after whole-request admission.")
            training_summary = {"calls": 1, "reason": "information-sets-present",
                                "iterations": request.iterations,
                                "layout": training_receipt}
        else:
            averages, training_receipt = {}, packed_layout
            training_summary = {"calls": 0, "reason": "no-information-sets",
                                "iterations": 0, "layout": training_receipt}
        if quotient_plan is not None:
            # Four Q numeric buffers and recursive helpers have been released
            # by the trainer before expanded geometry is reconstructed for
            # the unchanged diagnostics and complete policy serialization.
            for key, menu in quotient_plan.iter_rows():
                infos[key] = len(menu)
                menus[key] = menu
            if len(infos) != quotient_receipt["expanded_information_rows"]:
                raise RuntimeError("Expanded quotient output geometry lost supported rows.")
            quotient_plan = None
        policies, _ = _normalize_policies(averages)
        profile, br0, br1 = _evaluate_prepared(
            training_root, policies, pot=2 * view.anchor,
            chance_type=ChanceCursor,
            hand_counts=kernel.hand_counts, edges={}, marginals=marginals,
            prefix_kernel=adapter)
        if not all(isfinite(x) for x in (profile, br0, br1)):
            raise ValueError("Exact selected public diagnostics returned a nonfinite value.")
    finally:
        kernel.clear_rank_cache()
        quotient_plan = None

    policies = None
    adapter_receipt = adapter.receipt()
    anchor = view.anchor
    # Callback/view snapshots and marginal vectors have no serialization role.
    training_root = marginals = adapter = view = trainer = None
    serialization_keys = sorted(infos)
    info_count = len(infos)
    infos.clear()
    rows = []
    for key in serialization_keys:
        player, hand, history = key
        board = _revealed_board(history)
        actions = menus.pop(key)
        probabilities = averages.pop(key)
        rows.append({"player": "sb" if player == 0 else "bb",
                     "hand": "".join(kernel.hands[player][hand]),
                     "street": {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(board)],
                     "revealed_board": list(board), "history": list(history),
                     "actions": [{"name": action.name, "amount": action.amount,
                                  "raise_to": action.raise_to, "history_key": action.token,
                                  "probability": probability}
                                 for action, probability in zip(actions, probabilities)]})
    gain0, gain1 = max(0.0, br0 - profile), max(0.0, br1 + profile)
    kernel_stats = kernel.statistics()
    if kernel_stats["work_units_cumulative"] > admission["kernel"]["whole_request_upper_work"]:
        raise RuntimeError("Exact kernel work exceeded its whole-request admission.")
    if exact_arithmetic == "dyadic":
        actual_integer = kernel_stats["integer_arithmetic"]
        integer_upper = bit_forecast["dyadic_integer"]
        if (actual_integer["peak_operand_bits"] > integer_upper["maximum_bits_upper"] or
                actual_integer["peak_forecast_bits"] > integer_upper["maximum_bits_upper"] or
                actual_integer["peak_integer_payload_bits"] > integer_upper["logical_integer_payload_bits_upper"] or
                actual_integer["modeled_limb_work_upper"] > integer_upper["whole_request_limb_work_upper"]):
            raise RuntimeError("Dyadic integer arithmetic exceeded its whole-request bit/payload/work forecast.")
    if adapter_receipt["modeled_work_entries"] > admission["adapter"]["whole_request_work_upper"]:
        raise RuntimeError("Exact adapter work exceeded its whole-request admission.")
    census = {
        "version": "exact-product-selected-four-street-census-v1",
        "chance_contract": "exact-product-selected-v1",
        "kernel": dict(kernel_stats), "kernel_work_admission": admission["kernel"],
        "float_adapter": dict(adapter_receipt), "adapter_work_admission": admission["adapter"],
        "exact_pair_output": admission["pair_output"],
        "direct_topology": direct_receipt,
        "packed_layout_upper": layout_upper,
        "packed_layout_actual": packed_layout,
        "training": training_summary,
        "bit_forecast": bit_forecast,
        "whole_request_admission": admission,
        "stored_complete_worlds": 0, "stored_prefix_pair_edges": 0,
        "scope": admission["scope"],
    }
    if quotient_receipt is not None:
        census["suit_quotient_storage"] = quotient_receipt
    result = {
        "method": "full-traversal CFR+", "solver_version": "preflop-strategy-v1",
        "strategy_schema": "preflop-strategy-v1", "algorithm": request.algorithm,
        "execution_backend": "exact-product-selected-direct-packed-python",
        "representation_version": "exact-product-selected-v1",
        "numerical_model": "binary64-local-nine-decimal-whole-hand-v1",
        "chance_contract": "exact-product-selected-v1",
        "conversion_contract": CONVERSION_CONTRACT,
        "preflop_config": request.preflop_config.to_dict(),
        "postflop_action_configs": {s: {k: list(v) if isinstance(v, tuple) else v
                                         for k, v in spec.actions} for s, spec in specs.items()},
        "runout_mode": "conditioned-ordered-selected-runouts",
        "selected_runouts": [list(f + (t, r)) for f, t, r in kernel.selected],
        "reachable_runouts": [list(f + (t, r)) for f, t, r in reachable],
        "iterations": request.iterations, "candidate_private_pairs": pair_candidates,
        "compatible_private_pairs": supported_pair_count,
        "worlds": kernel.statistics()["support_pair_board_occurrences"],
        "pair_runout_preflight_checks": output_pairs * len(kernel.selected),
        "private_pair_probabilities": pair_rows,
        "public_states": topology.census.expanded_logical_visits,
        "decisions": topology.census.decision_occurrences,
        "info_sets": info_count, "value_sb": profile, "value_bb": -profile,
        "sb_best_response_value": br0, "bb_best_response_value": br1,
        "sb_gain": gain0, "bb_gain": gain1, "nash_conv": gain0 + gain1,
        "exploitability": (gain0 + gain1) / 2,
        "operator_census": census, "public_topology": "direct-shared-public-topology-v1",
        "public_batched_training_pot_anchor": anchor,
        "public_batched_training_view_states": len(topology.vertices),
        "strategy": rows,
        "scope": ("Explicit exact-product selected finite four-street game. Its global exact product prior "
                  "differs from legacy rounded per-occurrence normalization. CFR uses once-rounded binary64 "
                  "vectors; finite-iteration accuracy remains a separate certificate question. No full-deck, "
                  "unrestricted NLHE, or commercial-scale claim."),
    }
    if training_reduction == "suit-equivariant":
        result["training_reduction"] = "suit-equivariant-sorted-chance-binary64-v1"
        result["scope"] += (" Training uses explicitly ordered action arithmetic and sorted finite chance components "
                            "with canonical positive zero. This is a distinct binary64 trajectory; diagnostics and "
                            "strict completed-query conversion retain their existing contracts.")
    if strategy_storage == "suit-quotient":
        result["strategy_storage"] = "suit-quotient-packed-v1"
        result["scope"] += (" Training retains four quotient-action buffers and validates distinct member increments "
                            "before each phase commit. Complete policies and diagnostics remain expanded; "
                            "no whole-solve peak-memory or universal compression/speed claim follows.")
    if pair_diagnostics == "compact":
        result.pop("private_pair_probabilities")
        result.pop("compatible_private_pairs")
        result["pair_diagnostics"] = "compact-exact-product-inputs-v1"
        result["chance_input_snapshot"] = {
            "contract": "exact-product-selected-v1",
            "ranges": [[{"hand": "".join(hand), "weight_hex": float(weight).hex()}
                        for hand, weight in zip(hands, weights)]
                       for hands, weights in zip(kernel.hands, kernel.weights)],
        }
        result["operator_census"]["exact_pair_output"]["quadratic_diagnostic_stage"] = False
        result["operator_census"]["exact_pair_output"]["format"] = "compact-exact-product-inputs-v1"
        result["scope"] += (" Compact diagnostics preserve linear input snapshots and omit the private-pair table; "
                            "independent bounded verification separately reconstructs its own physical support.")
    if rank_cache_boards > 1:
        result["rank_cache"] = {"board_capacity": rank_cache_boards,
                                "hits": kernel_stats["rank_cache_hits"],
                                "misses": kernel_stats["rank_cache_misses"],
                                "evictions": kernel_stats["rank_cache_evictions"],
                                "released_after_diagnostics": True}
    return result
