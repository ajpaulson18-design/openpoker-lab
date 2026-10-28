"""Source-frozen paired study of expanded-R and suit-quotient Q storage.

Every child uses the same exact-product chance law and the same
suit-equivariant sorted-chance CFR+ reduction. The comparison changes only
strategy-row storage. Outputs are bounded finite-game evidence, not a general
memory, speed, or equilibrium claim.
"""
from argparse import ArgumentParser
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from math import isfinite
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from unittest.mock import patch

from pokerlab.cards import DECK, cards, expand_range
from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions
from scripts.benchmark_selected_operator import ROOT, _identity, _rss, _write
from scripts.benchmark_equivariant_selected_solver import (
    METRICS, REPLAY_TOLERANCE, _contains_resource_word, _decode, _orbit_check,
    _need, _validate_complete_rows, _verify_payload,
)

ITERATIONS = {
    "symmetric-t10": 10,
    "blocker-18": 10,
    "asymmetric-weighted": 10,
    "mixed-stabilizer": 10,
    "symmetric-t100": 100,
    "payoff-varied-t10": 10,
    "payoff-varied-t100": 100,
    "original-22-t10": 10,
    "original-22-qreject": 1000,
}

# (case, storage, replicate, tracemalloc). The first three symmetric T10 pairs
# alternate order; the separate traced pair is not mixed into timing medians.
SCHEDULE = (
    ("symmetric-t10", "expanded", 0, False),
    ("symmetric-t10", "suit-quotient", 0, False),
    ("symmetric-t10", "suit-quotient", 1, False),
    ("symmetric-t10", "expanded", 1, False),
    ("symmetric-t10", "expanded", 2, False),
    ("symmetric-t10", "suit-quotient", 2, False),
    ("symmetric-t10", "expanded", "traced", True),
    ("symmetric-t10", "suit-quotient", "traced", True),
    ("blocker-18", "expanded", 0, False),
    ("blocker-18", "suit-quotient", 0, False),
    ("asymmetric-weighted", "expanded", 0, False),
    ("asymmetric-weighted", "suit-quotient", 0, False),
    ("mixed-stabilizer", "expanded", 0, False),
    ("mixed-stabilizer", "suit-quotient", 0, False),
    ("symmetric-t100", "expanded", 0, False),
    ("symmetric-t100", "suit-quotient", 0, False),
    ("payoff-varied-t10", "expanded", 0, False),
    ("payoff-varied-t10", "suit-quotient", 0, False),
    ("payoff-varied-t100", "expanded", 0, False),
    ("payoff-varied-t100", "suit-quotient", 0, False),
    ("original-22-t10", "expanded", 0, False),
    ("original-22-t10", "suit-quotient", 0, False),
    ("original-22-qreject", "suit-quotient", 0, False),
)


def _count(value):
    return type(value) is int and value >= 0


def _base_case():
    return json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text(
        encoding="utf-8"))["case"]


def _small_case(identifier, sb_range, bb_range):
    return {"id": identifier, "sb_range": sb_range, "bb_range": bb_range,
        "config": {"starting_stack": [2, 2], "small_blind": .5, "big_blind": 1,
            "raise_sizes": [.5], "max_raises": 1, "include_all_in": False},
        "runouts": ["2c3c4h5s6h", "2d3d4h5s6h"],
        "flop_config": {"bet_sizes": [.5], "raise_sizes": [], "max_raises": 0, "include_all_in": False},
        "turn_config": {"bet_sizes": [.5], "raise_sizes": [], "max_raises": 0, "include_all_in": False},
        "river_config": {"bet_sizes": [.5], "raise_sizes": [], "max_raises": 0, "include_all_in": False}}


def _payoff_varied_case(identifier):
    case = _small_case(identifier, "AcQc,AdQd", "KcJc,KdJd")
    case["runouts"] = ["2c3c7c9hTs", "2d3d7d9hTs"]
    return case


def case_for(name):
    if name == "symmetric-t10" or name == "symmetric-t100":
        return _small_case("suit-exchange-symmetric-v1", "AcAh:1,AdAh:1", "KcKh:1,KdKh:1")
    if name == "blocker-18":
        return _small_case("blocker-conditioned-18-worlds-v1",
            "AcAh,AdAh,2cAh,2dAh", "KcKh,KdKh,3cKh,3dKh")
    if name == "asymmetric-weighted":
        return _small_case("weighted-asymmetric-suit-exchange-v1",
            "AcAh:0.7,AdAh:0.3", "KcKh:0.4,KdKh:0.6")
    if name == "mixed-stabilizer":
        return _small_case("mixed-suit-stabilizer-v1", "AcAd", "KcKd")
    if name == "payoff-varied-t10" or name == "payoff-varied-t100":
        return _payoff_varied_case("payoff-varied-private-flush-v1")
    if name == "original-22-t10" or name == "original-22-qreject":
        return dict(_base_case(), id="original-22-exact-product-study")
    raise ValueError("Unknown fixed suit-quotient study case")


def request_for(case, iterations):
    return FourStreetSolveRequest(case["sb_range"], case["bb_range"], tuple(case["runouts"]),
        preflop_config=PreflopConfig.from_dict(case["config"]),
        flop_actions=PostflopActions(**case["flop_config"]),
        turn_actions=PostflopActions(**case["turn_config"]),
        river_actions=PostflopActions(**case["river_config"]),
        iterations=iterations, algorithm="cfrplus", traversal="public-batched",
        diagnostics="public-batched", resource_model="public-vector")


def _runtime():
    return {"implementation": platform.python_implementation(),
        "version": platform.python_version(), "sys_version": sys.version,
        "platform": platform.platform(), "machine": platform.machine()}


def _label(entry):
    case, storage, sample, traced = entry
    sample_name = "traced" if traced else str(sample)
    return f"{case}-{storage}-{sample_name}"


def _forbidden(counter, label, calls):
    def reject(*_args, **_kwargs):
        calls[counter] += 1
        raise AssertionError("forbidden production path: " + label)
    return reject


def child(case_name, storage, sample, traced=False):
    if storage not in ("expanded", "suit-quotient"):
        raise ValueError("Unknown strategy storage mode")
    case = case_for(case_name)
    solve_request = request_for(case, ITERATIONS[case_name])
    calls = {"equivariant_trainer_calls": 0, "quotient_trainer_calls": 0,
        "quotient_plan_calls": 0, "rank_calls": 0, "pair_query_calls": 0,
        "native_calls": 0, "world_producer_calls": 0, "popen_calls": 0}
    from pokerlab import exact_selected_solver as solver
    from pokerlab import exact_selected_kernel as kernel_module
    from pokerlab import equivariant_packed_cfr as equivariant_module
    from pokerlab import suit_quotient_cfr as quotient_module
    from pokerlab import suit_quotient_plan as plan_module
    equivariant_train = equivariant_module.train_equivariant_packed
    quotient_train = quotient_module.train_suit_quotient
    plan_init = plan_module.SuitQuotientPlan.__init__
    rank = kernel_module.rank_hand

    def count_equivariant(*args, **kwargs):
        calls["equivariant_trainer_calls"] += 1
        return equivariant_train(*args, **kwargs)

    def count_quotient(*args, **kwargs):
        calls["quotient_trainer_calls"] += 1
        return quotient_train(*args, **kwargs)

    def count_plan(self, *args, **kwargs):
        calls["quotient_plan_calls"] += 1
        return plan_init(self, *args, **kwargs)

    def count_rank(*args, **kwargs):
        calls["rank_calls"] += 1
        return rank(*args, **kwargs)

    def forbid_pair(*_args, **_kwargs):
        calls["pair_query_calls"] += 1
        raise AssertionError("forbidden pair-probability query")

    forbidden = (
        ("world_producer_calls", "pokerlab.preflop_solver._enumerate_physical_worlds"),
        ("world_producer_calls", "pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds"),
        ("world_producer_calls", "pokerlab.preflop_solver._merge_preflop_tree"),
        ("native_calls", "pokerlab.native_selected_operator.train_native_selected"),
        ("native_calls", "pokerlab.native_selected_dag.train_native_selected_dag"),
        ("native_calls", "pokerlab.native_public_cfr.train_native_public"),
        ("popen_calls", "subprocess.Popen"),
    )
    start = 0.0
    seconds = 0.0
    allocation = None
    payload = None
    try:
        with ExitStack() as stack:
            for counter, target in forbidden:
                stack.enter_context(patch(target, new=_forbidden(counter, target, calls)))
            stack.enter_context(patch.object(equivariant_module, "train_equivariant_packed", new=count_equivariant))
            stack.enter_context(patch.object(quotient_module, "train_suit_quotient", new=count_quotient))
            stack.enter_context(patch.object(plan_module.SuitQuotientPlan, "__init__", new=count_plan))
            stack.enter_context(patch.object(kernel_module, "rank_hand", new=count_rank))
            stack.enter_context(patch.object(ExactSelectedRunoutKernel,
                "pair_probability_exact", new=forbid_pair))
            if traced:
                tracemalloc.start()
            start = time.perf_counter()
            try:
                payload = solver.solve_four_street_exact_selected(solve_request,
                    rank_cache_boards=64, pair_diagnostics="compact", exact_arithmetic="dyadic",
                    training_reduction="suit-equivariant", strategy_storage=storage)
            finally:
                seconds = time.perf_counter() - start
                allocation = tracemalloc.get_traced_memory()[1] if traced else None
                if traced:
                    tracemalloc.stop()
        status, error = "complete", None
    except ValueError as exc:
        allowed = (case_name == "original-22-qreject" and storage == "suit-quotient" and
                   not any(calls.values()) and _contains_resource_word(str(exc)))
        status = "pretraining-rejected" if allowed else "failed"
        error = {"type": type(exc).__name__, "message": str(exc)}
        payload = None
    except Exception as exc:
        status, error, payload = "failed", {"type": type(exc).__name__, "message": str(exc)}, None
    if traced and tracemalloc.is_tracing():
        tracemalloc.stop()
    return {"case": case_name, "storage": storage, "sample": sample,
        "iterations": ITERATIONS[case_name], "traced": traced, "status": status,
        "error": error, "seconds": seconds, "python_peak_allocation_bytes": allocation,
        "process_lifetime_peak_working_set_bytes": _rss(), "actual_calls": calls,
        "payload": payload, "runtime": _runtime()}


def _validate_child(raw, expected):
    case_name, storage, sample, traced = expected
    _need(type(raw) is dict and raw.get("case") == case_name and
        raw.get("storage") == storage and raw.get("sample") == sample and
        raw.get("iterations") == ITERATIONS[case_name] and raw.get("traced") is traced and
        raw.get("runtime") == _runtime(), "child identity/runtime mismatch")
    _need(type(raw.get("seconds")) in (int, float) and type(raw["seconds"]) is not bool and
        isfinite(raw["seconds"]) and raw["seconds"] > 0, "child timer missing or invalid")
    _need(type(raw.get("process_lifetime_peak_working_set_bytes")) is int and
        raw["process_lifetime_peak_working_set_bytes"] > 0, "child process peak missing")
    allocation = raw.get("python_peak_allocation_bytes")
    _need((type(allocation) is int and allocation > 0) if traced else allocation is None,
        "tracemalloc measurement mismatch")
    calls = raw.get("actual_calls")
    call_keys = {"equivariant_trainer_calls", "quotient_trainer_calls", "quotient_plan_calls",
        "rank_calls", "pair_query_calls", "native_calls", "world_producer_calls", "popen_calls"}
    _need(type(calls) is dict and set(calls) == call_keys and
        all(type(value) is int and value >= 0 for value in calls.values()) and
        not any(calls[key] for key in ("pair_query_calls", "native_calls", "world_producer_calls", "popen_calls")),
        "forbidden pair/world/native path entered")
    _need(raw.get("status") in ("complete", "pretraining-rejected", "failed"), "unknown child status")
    if raw["status"] == "pretraining-rejected":
        _need(case_name == "original-22-qreject" and storage == "suit-quotient" and
            type(raw.get("error")) is dict and raw["error"].get("type") == "ValueError" and
            _contains_resource_word(raw["error"].get("message", "")) and
            raw.get("payload") is None and not any(calls.values()),
            "unexpected/non-early resource rejection")
        return
    _need(raw["status"] == "complete" and raw.get("error") is None and
        type(raw.get("payload")) is dict, "child solve failed: " + str(raw.get("error")))
    expected_equiv = int(storage == "expanded")
    expected_q = int(storage == "suit-quotient")
    _need(calls["equivariant_trainer_calls"] == expected_equiv and
        calls["quotient_trainer_calls"] == expected_q and
        calls["quotient_plan_calls"] == expected_q and calls["rank_calls"] > 0,
        "wrong quotient/reference trainer, plan, or rank call count")
    payload = raw["payload"]
    _need(payload.get("chance_contract") == "exact-product-selected-v1" and
        payload.get("conversion_contract") == "exact-product-vectors-binary64-v1" and
        payload.get("training_reduction") == "suit-equivariant-sorted-chance-binary64-v1" and
        payload.get("pair_diagnostics") == "compact-exact-product-inputs-v1" and
        "private_pair_probabilities" not in payload and
        payload.get("strategy_storage", "expanded") ==
        ("suit-quotient-packed-v1" if storage == "suit-quotient" else "expanded"),
        "payload contract/storage/reduction mismatch")
    _need(all(type(payload.get(key)) in (int, float) and type(payload[key]) is not bool and
        isfinite(payload[key]) for key in METRICS), "payload metrics missing or nonfinite")
    census = payload.get("operator_census")
    _need(_count(payload.get("info_sets")) and _count(payload.get("worlds")) and
        type(census) is dict and census.get("stored_complete_worlds") == 0 and
        census.get("stored_prefix_pair_edges") == 0, "solver retained complete worlds or pair edges")
    admission, kernel_stats, adapter_stats = (census.get("whole_request_admission"),
        census.get("kernel"), census.get("float_adapter"))
    _need(type(admission) is dict and type(kernel_stats) is dict and type(adapter_stats) is dict,
        "solver omitted whole-request or actual resource receipts")
    kernel_bound = admission["kernel"]["whole_request_upper_work"]
    adapter_bound = admission["adapter"]["whole_request_work_upper"]
    retained = admission["retained_storage"]
    _need(all(_count(value) for value in (kernel_bound, adapter_bound,
        admission["combined_modeled_work_upper"], admission["whole_request_limit"],
        kernel_stats["work_units_cumulative"], kernel_stats["storage_entries_peak"],
        adapter_stats["modeled_work_entries"], adapter_stats["retained_mapping_entries"],
        retained["kernel_peak_upper"], retained["adapter_peak_upper"],
        retained["whole_request_peak_upper"], retained["entry_limit"])) and
        kernel_stats["work_units_cumulative"] <= kernel_bound and
        adapter_stats["modeled_work_entries"] <= adapter_bound and
        admission["combined_modeled_work_upper"] <= admission["whole_request_limit"] and
        kernel_stats["storage_entries_peak"] <= retained["kernel_peak_upper"] and
        adapter_stats["retained_mapping_entries"] <= retained["adapter_peak_upper"] and
        retained["whole_request_peak_upper"] <= retained["entry_limit"],
        "actual kernel/adapter/whole-request work or storage exceeded its admitted upper bound")
    packed = census["packed_layout_actual"]
    expanded = packed.get("expanded_layout_equivalent", packed)
    upper = census["packed_layout_upper"]
    _need(type(packed) is dict and type(expanded) is dict and type(upper) is dict and
        all(_count(expanded.get(name)) for name in ("requested_layout_loop_entries", "action_slots")) and
        all(_count(upper.get(name)) for name in ("upper_requested_layout_loop_entries", "upper_action_slots")) and
        _count(packed.get("numeric_buffers")) and packed["numeric_buffers"] == 4 and
        expanded["requested_layout_loop_entries"] <= upper["upper_requested_layout_loop_entries"] and
        expanded["action_slots"] <= upper["upper_action_slots"] and packed["numeric_buffers"] == 4,
        "actual packed work/action slots exceeded admitted limits")
    extra = admission["equivariant_additional_admission"]
    observed_extra = packed["equivariant_additional_admission"]
    _need(all(_count(mapping.get(name)) for mapping, names in (
        (extra, ("modeled_work_upper", "whole_request_additional_work_upper", "additional_retained_entries_upper")),
        (observed_extra, ("modeled_work_upper", "additional_retained_entries_upper")),
        (retained, ("equivariant_extra_entries_upper",))) for name in names) and
        extra["modeled_work_upper"] <= extra["whole_request_additional_work_upper"] and
        extra["additional_retained_entries_upper"] <= retained["equivariant_extra_entries_upper"] and
        observed_extra["modeled_work_upper"] <= extra["whole_request_additional_work_upper"] and
        observed_extra["additional_retained_entries_upper"] <= retained["equivariant_extra_entries_upper"],
        "equivariant whole-request work/storage exceeded admission")
    dyadic, bit_bound = kernel_stats["integer_arithmetic"], census["bit_forecast"]["dyadic_integer"]
    _need(all(_count(value) for value in (dyadic["peak_operand_bits"], dyadic["peak_forecast_bits"],
        dyadic["peak_integer_payload_bits"], dyadic["integer_payload_bit_limit"],
        dyadic["modeled_limb_work_upper"], bit_bound["maximum_bits_upper"],
        bit_bound["logical_integer_payload_bits_upper"], bit_bound["whole_request_limb_work_upper"])) and
        dyadic["peak_operand_bits"] <= bit_bound["maximum_bits_upper"] and
        dyadic["peak_forecast_bits"] <= bit_bound["maximum_bits_upper"] and
        dyadic["peak_integer_payload_bits"] <= bit_bound["logical_integer_payload_bits_upper"] and
        dyadic["peak_integer_payload_bits"] <= dyadic["integer_payload_bit_limit"] and
        dyadic["modeled_limb_work_upper"] <= bit_bound["whole_request_limb_work_upper"],
        "actual dyadic arithmetic exceeded admitted bits/payload/work")
    training = census["training"]
    _need(_count(training.get("calls")) and training["calls"] == 1 and training["layout"] == packed and
        _count(kernel_stats.get("rank_calls")) and
        calls["equivariant_trainer_calls"] + calls["quotient_trainer_calls"] == training["calls"] and
        calls["rank_calls"] == kernel_stats["rank_calls"], "trainer/rank calls differ from receipt")
    if storage == "suit-quotient":
        quotient = census.get("suit_quotient_storage")
        _need(type(quotient) is dict and all(_count(quotient.get(name)) for name in (
            "quotient_information_rows", "quotient_action_slots", "expanded_information_rows",
            "expanded_action_slots", "supported_member_count", "iterations",
            "four_quotient_numeric_buffers_projected_payload_bytes", "group_size")) and
            all(_count(packed.get(name)) for name in ("information_sets", "action_slots",
                "semantic_row_lookup_entries", "retained_expanded_row_lookup_entries",
                "numeric_buffer_bytes", "quotient_information_rows", "quotient_action_slots",
                "member_checks", "expanded_information_rows", "expanded_action_slots",
                "expanded_policy_shadow_rows", "expanded_policy_shadow_action_slots")) and
            packed["semantic_row_lookup_entries"] == packed["quotient_information_rows"] and
            packed["retained_expanded_row_lookup_entries"] == 0 and
            packed["numeric_buffer_bytes"] == 32 * packed["quotient_action_slots"] and
            packed["information_sets"] == packed["quotient_information_rows"] and
            packed["action_slots"] == packed["quotient_action_slots"] and
            quotient["retained_expanded_row_lookup_entries"] == 0 and
            quotient["iterations"] == raw["iterations"] and
            packed["member_checks"] == 2 * raw["iterations"] * quotient["supported_member_count"] and
            quotient["quotient_action_slots"] == packed["quotient_action_slots"] and
            quotient["four_quotient_numeric_buffers_projected_payload_bytes"] == packed["numeric_buffer_bytes"] and
            packed["expanded_information_rows"] == quotient["expanded_information_rows"] and
            packed["expanded_action_slots"] == quotient["expanded_action_slots"] and
            packed["expanded_policy_shadow_rows"] == quotient["expanded_information_rows"] and
            packed["expanded_policy_shadow_action_slots"] == quotient["expanded_action_slots"] and
            packed["expanded_layout_equivalent"]["information_sets"] == quotient["expanded_information_rows"] and
            packed["expanded_layout_equivalent"]["action_slots"] == quotient["expanded_action_slots"],
            "Q buffer receipt/expanded shadow census mismatch")
        if case_name in ("payoff-varied-t10", "payoff-varied-t100"):
            _need(quotient["group_size"] == 2,
                "payoff-varied private-flush fixture lost its global c/d G2")
    else:
        _need("suit_quotient_storage" not in census and _count(payload.get("info_sets")) and
            all(_count(packed.get(name)) for name in ("information_sets", "action_slots", "numeric_buffer_bytes")) and
            packed["information_sets"] == payload["info_sets"] and
            packed["numeric_buffer_bytes"] == 32 * packed["action_slots"],
            "expanded R storage receipt mismatch")
    _validate_complete_rows(payload, case_for(case_name))
    if case_name == "blocker-18":
        _need(payload["worlds"] == 18, "blocker fixture no longer has exactly 18 compatible pair-board worlds")
    if case_name in ("payoff-varied-t10", "payoff-varied-t100"):
        expected_case = case_for(case_name)
        expected_hands = [{"".join(hand): float(weight).hex()
            for hand, weight in expand_range(expected_case[key]).items()}
            for key in ("sb_range", "bb_range")]
        observed_hands = [{row["hand"]: row["weight_hex"] for row in side}
            for side in payload["chance_input_snapshot"]["ranges"]]
        expected_runouts = []
        for runout in expected_case["runouts"]:
            parsed = cards(runout, 5)
            flop = tuple(sorted(parsed[:3], key=DECK.index))
            expected_runouts.append(flop + parsed[3:])
        expected_runouts.sort(key=lambda board: tuple(DECK.index(card) for card in board))
        observed_runouts = [tuple(board) for board in payload.get("selected_runouts", ())]
        _need(payload["worlds"] == 8 and
            observed_runouts == expected_runouts and
            observed_hands == expected_hands,
            "payoff-varied fixture changed its two-hand/two-board/eight-world shape")
    return None


def _policy_metric_certificate_identity(left, right, left_verification, right_verification):
    _need(left["chance_input_snapshot"] == right["chance_input_snapshot"],
        "paired storage runs used different chance input snapshots")
    lrows = {(r["player"], r["hand"], tuple(r["history"])): r for r in left["strategy"]}
    rrows = {(r["player"], r["hand"], tuple(r["history"])): r for r in right["strategy"]}
    _need(set(lrows) == set(rrows), "storage modes produced different complete row identities")
    for key, lrow in lrows.items():
        rrow = rrows[key]
        la, ra = lrow["actions"], rrow["actions"]
        _need([{k: v for k, v in action.items() if k != "probability"} for action in la] ==
            [{k: v for k, v in action.items() if k != "probability"} for action in ra],
            "storage modes produced different action menus")
        _need([action["probability"].hex() for action in la] ==
            [action["probability"].hex() for action in ra],
            "expanded and quotient policy probabilities differ")
    _need(all(left[key] == right[key] for key in METRICS),
        "expanded and quotient reported metrics differ")
    lcert = left_verification["exact_compact_certificate"]["exact_certificate"]
    rcert = right_verification["exact_compact_certificate"]["exact_certificate"]
    _need(lcert["metrics"] == rcert["metrics"] and lcert["threshold"] == rcert["threshold"] and
        lcert["threshold_met"] == rcert["threshold_met"], "paired exact certificate or threshold flags differ")
    return {"complete_rows": len(lrows), "policy_bitwise_identical": True,
        "metric_values_identical": True, "metric_absolute_differences": {key: 0.0 for key in METRICS},
        "exact_certificate_metrics_identical": True, "exact_threshold_flags_identical": True,
        "threshold_met": lcert["threshold_met"]}


def _pair_comparison(left, right, left_verification, right_verification):
    identity = _policy_metric_certificate_identity(left, right,
        left_verification, right_verification)
    expanded_bytes = left["operator_census"]["packed_layout_actual"]["numeric_buffer_bytes"]
    quotient_bytes = right["operator_census"]["packed_layout_actual"]["numeric_buffer_bytes"]
    qreceipt = right["operator_census"]["suit_quotient_storage"]
    expanded_rows = left["operator_census"]["packed_layout_actual"]["information_sets"]
    quotient_rows = right["operator_census"]["packed_layout_actual"]["information_sets"]
    group_size = qreceipt["group_size"]
    if group_size == 1:
        _need(quotient_bytes == expanded_bytes and quotient_rows == expanded_rows,
            "identity-group Q storage changed row/buffer dimensions")
    return {**identity,
        "expanded_four_buffer_payload_bytes": expanded_bytes,
        "quotient_four_buffer_payload_bytes": quotient_bytes,
        "four_buffer_payload_bytes_saved": expanded_bytes - quotient_bytes,
        "suit_group_size": group_size,
        "expanded_information_rows": expanded_rows,
        "quotient_information_rows": quotient_rows,
        "quotient_action_slots": qreceipt["quotient_action_slots"],
        "quotient_member_checks": right["operator_census"]["packed_layout_actual"]["member_checks"],
        "retained_expanded_row_lookup_entries": qreceipt["retained_expanded_row_lookup_entries"],
        "expanded_shadow_action_slots": qreceipt["expanded_action_slots"],
        "numeric_buffer_count_per_mode": 4,
        "identity_group_storage_overhead": ({
            "applies": True,
            "quotient_to_expanded_q_buffer_payload_ratio": quotient_bytes / expanded_bytes if expanded_bytes else None,
            "quotient_to_expanded_row_count_ratio": quotient_rows / expanded_rows if expanded_rows else None,
            "interpretation": "Identity-group case retains one Q row per physical row; measured differences include plan and validation overhead."
        } if group_size == 1 else {"applies": False}),
        "payload_only_scope": "Four-array numeric payload comparison only; not a complete-call memory or RSS claim."}


def _protected_verification(case, payload):
    calls = {"production_solver": 0, "reference_trainer": 0, "quotient_trainer": 0,
        "quotient_plan": 0, "kernel_constructor": 0, "rank": 0, "pair_query": 0,
        "world_producer": 0, "native": 0, "popen": 0}
    from pokerlab import exact_selected_solver as solver
    from pokerlab import exact_selected_kernel as kernel_module
    from pokerlab import equivariant_packed_cfr as equivariant_module
    from pokerlab import suit_quotient_cfr as quotient_module
    from pokerlab import suit_quotient_plan as plan_module
    def fail(counter, label):
        return _forbidden(counter, label, calls)
    forbidden = (
        ("production_solver", "pokerlab.exact_selected_solver.solve_four_street_exact_selected"),
        ("world_producer", "pokerlab.preflop_solver._enumerate_physical_worlds"),
        ("world_producer", "pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds"),
        ("native", "pokerlab.native_selected_operator.train_native_selected"),
        ("native", "pokerlab.native_selected_dag.train_native_selected_dag"),
        ("native", "pokerlab.native_public_cfr.train_native_public"),
        ("popen", "subprocess.Popen"),
    )
    with ExitStack() as stack:
        for counter, target in forbidden:
            stack.enter_context(patch(target, new=fail(counter, target)))
        stack.enter_context(patch.object(solver, "train_packed", new=fail("reference_trainer", "packed trainer")))
        stack.enter_context(patch.object(equivariant_module, "train_equivariant_packed",
            new=fail("reference_trainer", "equivariant trainer")))
        stack.enter_context(patch.object(quotient_module, "train_suit_quotient",
            new=fail("quotient_trainer", "Q trainer")))
        stack.enter_context(patch.object(plan_module.SuitQuotientPlan, "__init__",
            new=fail("quotient_plan", "Q plan constructor")))
        stack.enter_context(patch.object(kernel_module, "ExactSelectedRunoutKernel",
            new=fail("kernel_constructor", "kernel constructor")))
        stack.enter_context(patch.object(solver, "ExactSelectedRunoutKernel",
            new=fail("kernel_constructor", "solver kernel constructor")))
        stack.enter_context(patch.object(kernel_module, "rank_hand", new=fail("rank", "production rank")))
        stack.enter_context(patch.object(ExactSelectedRunoutKernel, "pair_probability_exact",
            new=fail("pair_query", "production pair query")))
        result = _verify_payload(case, payload)
    _need(not any(calls.values()), "production solve/trainer/kernel/rank/pair path entered during verification")
    result["forbidden_production_calls"] = calls
    return result


def _pair_key(entry):
    return entry[0], entry[2], entry[3]


def run(output):
    output = Path(output).resolve()
    _need(output != ROOT and ROOT not in output.parents and not output.exists(),
        "Use a new external output directory")
    source = _identity()
    _need(not source["status"], "Freeze and clean the full source closure before the fixed study")
    output.mkdir(parents=True)
    _write(output / "source-before.json", source)
    _write(output / "protocol.json", {"version": "suit-quotient-storage-fixed-study-v1",
        "source_commit": source["commit"], "source_sha256": source["sha256"],
        "runtime": _runtime(), "schedule": SCHEDULE,
        "cases": {name: deepcopy(case_for(name)) for name in ITERATIONS},
        "rank_cache_boards": 64, "exact_arithmetic": "dyadic",
        "training_reduction": "suit-equivariant-sorted-chance-binary64-v1",
        "pair_diagnostics": "compact", "replay_tolerance": REPLAY_TOLERANCE,
        "independent_verification": {"numeric": "scripts.preflop_validation.replay_policy",
            "certificate_wrapper": "scripts.exact_selected_compact_certificate.evaluate_exact",
            "certificate_source_identity": "four-street-independent-exact-v3"},
        "retry_policy": "none; preserve raw child stdout/stderr and first failure",
        "scope": "Paired expanded-R versus suit-quotient storage under one exact-product chance law and one sorted-chance reduction; bounded game-specific evidence."})
    samples, verifications, orbit_checks, failure = [], {}, {}, None
    for entry in SCHEDULE:
        case_name, storage, sample, traced = entry
        label = _label(entry)
        command = [sys.executable, "-B", "-m", "scripts.benchmark_suit_quotient_solver",
            "--child", case_name, "--storage", storage, "--sample", str(sample)]
        if traced:
            command.append("--traced")
        process = None
        try:
            process = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
            (output / (label + ".json")).write_bytes(process.stdout)
            (output / (label + ".stderr.txt")).write_bytes(process.stderr)
            _need(process.returncode == 0, "child exited with status " + str(process.returncode))
            raw = _decode(process.stdout)
            _validate_child(raw, entry)
            samples.append({"artifact": label + ".json",
                **{key: value for key, value in raw.items() if key != "payload"}})
            if raw["status"] == "complete":
                _need(_identity() == source, "source closure changed before independent verification")
                verification = _protected_verification(case_for(case_name), raw["payload"])
                _write(output / (label + "-verification.json"), verification)
                verifications[label] = verification
                if storage == "suit-quotient" and raw["payload"]["operator_census"][
                        "suit_quotient_storage"]["group_size"] > 1:
                    orbit = _orbit_check(raw["payload"], require_equal=True)
                    _need(orbit["orbit_rows_checked"] > 0 and
                        orbit["maximum_probability_difference"] == 0.0,
                        "completed quotient fixture lost bitwise suit-orbit symmetry")
                    _write(output / (label + "-orbit.json"), orbit)
                    orbit_checks[label] = orbit
                _need(verification.get("payload_metrics_within_tolerance") is True,
                    "independent numeric replay metric gap exceeds tolerance: " +
                    repr(verification.get("payload_metric_absolute_differences")))
            print(label, raw["status"], flush=True)
        except Exception as exc:
            failure = {"artifact": label, "type": type(exc).__name__, "message": str(exc),
                "returncode": None if process is None else process.returncode}
            _write(output / (label + "-failure.json"), failure)
            break

    comparisons = {}
    try:
        if failure is None:
            paired_keys = {_pair_key(entry) for entry in SCHEDULE
                           if entry[0] != "original-22-qreject"}
            for case_name, replicate, traced in sorted(paired_keys,
                                                       key=lambda value: (value[0], str(value[1]), value[2])):
                left_entry = (case_name, "expanded", replicate, traced)
                right_entry = (case_name, "suit-quotient", replicate, traced)
                left_label, right_label = _label(left_entry), _label(right_entry)
                left_raw = _decode((output / (left_label + ".json")).read_bytes())
                right_raw = _decode((output / (right_label + ".json")).read_bytes())
                _need(left_raw["status"] == right_raw["status"] == "complete",
                    "paired child did not complete")
                comparisons[left_label + "__vs__" + right_label] = _pair_comparison(
                    left_raw["payload"], right_raw["payload"], verifications[left_label],
                    verifications[right_label])

            symmetric_checks = {}
            baseline_sample = 0
            for storage in ("expanded", "suit-quotient"):
                base_label = _label(("symmetric-t10", storage, baseline_sample, False))
                baseline = _decode((output / (base_label + ".json")).read_bytes())["payload"]
                checks = {}
                for replicate, traced in ((1, False), (2, False), ("traced", True)):
                    label = _label(("symmetric-t10", storage, replicate, traced))
                    other = _decode((output / (label + ".json")).read_bytes())["payload"]
                    checks[str(replicate)] = _policy_metric_certificate_identity(baseline, other,
                        verifications[base_label], verifications[label])
                symmetric_checks[storage] = {"replicate_policy_metrics_and_certificate_identical": True,
                                             "replicate_pairs": checks}
            comparisons["symmetric-t10-repeat-controls"] = symmetric_checks
            medians = {}
            for storage in ("expanded", "suit-quotient"):
                rows = [_decode((output / (_label(("symmetric-t10", storage, i, False)) + ".json")).read_bytes())
                        for i in range(3)]
                medians[storage] = {"full_call_seconds": statistics.median(row["seconds"] for row in rows),
                    "process_lifetime_peak_working_set_bytes": [row["process_lifetime_peak_working_set_bytes"] for row in rows]}
            paired_time_deltas = []
            paired_time_ratios = []
            for replicate in range(3):
                expanded_raw = _decode((output / (_label(("symmetric-t10", "expanded", replicate, False)) + ".json")).read_bytes())
                quotient_raw = _decode((output / (_label(("symmetric-t10", "suit-quotient", replicate, False)) + ".json")).read_bytes())
                paired_time_deltas.append(quotient_raw["seconds"] - expanded_raw["seconds"])
                paired_time_ratios.append(quotient_raw["seconds"] / expanded_raw["seconds"])
            comparisons["symmetric-t10-three-pair-medians"] = {
                "expanded": medians["expanded"], "suit_quotient": medians["suit-quotient"],
                "median_time_ratio_q_over_expanded": medians["suit-quotient"]["full_call_seconds"] /
                    medians["expanded"]["full_call_seconds"],
                "paired_q_minus_expanded_seconds": paired_time_deltas,
                "median_paired_q_minus_expanded_seconds": statistics.median(paired_time_deltas),
                "median_paired_time_ratio_q_over_expanded": statistics.median(paired_time_ratios),
                "interpretation": "Fixture-specific complete-call timing only; no general speed claim."}
            traced = {}
            for storage in ("expanded", "suit-quotient"):
                raw = _decode((output / (_label(("symmetric-t10", storage, "traced", True)) + ".json")).read_bytes())
                traced[storage] = {"full_call_seconds": raw["seconds"],
                    "python_peak_allocation_bytes": raw["python_peak_allocation_bytes"],
                    "process_lifetime_peak_working_set_bytes": raw["process_lifetime_peak_working_set_bytes"]}
            comparisons["separate-traced-pair"] = traced
    except Exception as exc:
        failure = {"stage": "post-run-comparison", "type": type(exc).__name__,
            "message": str(exc), "prior_failure": failure}
        if not (output / "post-run-failure.json").exists():
            _write(output / "post-run-failure.json", failure)

    source_after = None
    try:
        source_after = _identity()
        _write(output / "source-after.json", source_after)
        _need(source_after == source, "source closure changed during the paired study")
    except Exception as exc:
        failure = {"stage": "source-after-audit", "type": type(exc).__name__,
            "message": str(exc), "prior_failure": failure}
        if not (output / "post-run-failure.json").exists():
            _write(output / "post-run-failure.json", failure)
        if not (output / "source-after.json").exists():
            try:
                _write(output / "source-after.json", _identity())
            except Exception:
                _write(output / "source-after.json", None)

    certs = {label: {"threshold_met": value["exact_compact_certificate"]["exact_certificate"]["threshold_met"],
        "metrics": value["exact_compact_certificate"]["exact_certificate"]["metrics"],
        "verification_artifact": label + "-verification.json"}
        for label, value in verifications.items()}
    report = {"version": "suit-quotient-storage-fixed-study-report-v1",
        "source_commit": source["commit"], "runtime": _runtime(),
        "schedule_planned": len(SCHEDULE), "schedule_attempted": len(samples),
        "samples": samples, "certificates": certs, "paired_comparisons": comparisons,
        "quotient_orbit_checks": orbit_checks,
        "finite_iteration_threshold_misses_retained": [label for label, row in certs.items()
            if not row["threshold_met"]],
        "pretraining_rejection_retained": any(row.get("status") == "pretraining-rejected" for row in samples),
        "failure": failure,
        "scope": "Finite game and source/runtime specific. Policy/metric/certificate identity is required for paired storage modes. Four-buffer byte deltas exclude all other memory and do not establish whole-call savings."}
    _write(output / "report.json", report)
    manifest = {"source_commit": source["commit"], "sha256": {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.iterdir()) if path.is_file()}}
    _write(output / "manifest.json", manifest)
    digest = hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest()
    return {"outcome": "complete" if failure is None and len(samples) == len(SCHEDULE) else "failed",
        "manifest_sha256": digest, "failure": failure}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", choices=tuple(ITERATIONS))
    parser.add_argument("--storage", choices=("expanded", "suit-quotient"))
    parser.add_argument("--sample", default="0")
    parser.add_argument("--traced", action="store_true")
    args = parser.parse_args()
    if args.child:
        sample = args.sample if args.sample == "traced" else int(args.sample)
        result = child(args.child, args.storage, sample, args.traced)
    else:
        if args.output is None:
            parser.error("--output is required")
        result = run(args.output)
    print(json.dumps(result, allow_nan=False))
    return 0 if args.child or result["outcome"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
