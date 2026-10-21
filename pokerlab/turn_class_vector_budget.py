"""No-ranking admission planner for the fixed seven-class TURN experiment.

The values here are logical work/slot reservations, not time, memory-byte, or
RSS estimates. This module deliberately imports no poker or ranking code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import MutableMapping
from typing import Any, Iterator, Mapping
from types import MappingProxyType


RESOURCE_MODEL = "turn-seven-class-vector-v1"

# Fixed fixture dimensions. The physical counts remain independently guarded;
# the compact dimensions describe only the training representation.
PHYSICAL = {
    "worlds": 396, "rivers": 48, "pairs": 9,
    "states": 3039, "decisions": 1254, "terminals": 1780,
    "chance_nodes": 5, "chance_edges": 240, "decision_edges": 2798,
    "policy_rows": 3606, "action_slots": 8046, "prefix_edges": 405,
    "marginal_slots": 294, "legal_prefix_memberships": 282, "depth": 9,
}
COMPACT = {
    "worlds": 45, "rivers": 7, "pairs": 9,
    "states": 456, "decisions": 188, "terminals": 263,
    "chance_nodes": 5, "chance_edges": 35, "decision_edges": 420,
    "policy_rows": 486, "action_slots": 1086, "prefix_edges": 54,
    "marginal_slots": 48, "legal_prefix_memberships": 42, "depth": 9,
}

MAX_CANDIDATE_PAIR_ITERATIONS = 3_000_000
MAX_PHYSICAL_WORLD_ITERATIONS = 3_000_000
MAX_PUBLIC_STATES = 250_000
MAX_PUBLIC_DECISIONS = 10_000
MAX_PREFIX_EDGES = 250_000
MAX_INFO_ACTION_SLOTS = 1_000_000
MAX_COMPACT_WORLD_PROXY = 30_000_000
MAX_COMPACT_DENSE_PROXY = 30_000_000
MAX_VECTOR_WORK = 500_000_000
ONE_TIME_WORK_RESERVE = 2_000_000
MAX_EXPLICIT_LIST_WRITES = 200_000_000

# Source-shaped training envelope for I=486, S=1086, V=22064, A=7222,
# R=3744, U=4716. Full requested T is charged even when discard is large.
TRAINING_FIXED = 6_288
TRAINING_PER_ITERATION = 75_159

# Source-derived census terms for the fixed flow. ``final_diagnostics`` is the
# independently enumerated full-physical visitor/fallback envelope. Other
# components retain explicit operation counts from the source census rather
# than presenting a runtime or byte estimate.
_MODELED_RANK_INPUTS = 276
_RANK_LOOP_CELLS = 48_852  # 276 inputs * 177 conservative source-loop entries
_PHYSICAL_ENUMERATION_TERMS = {
    "parser": 164, "selected_rivers": 100, "hand_arrays": 16,
    "pair_scan": 45, "pair_mass": 9, "pair_river_tests": 432,
    "private_hand_concatenations": 1728, "disjoint_membership_checks": 1728,
    "legal_world_tuples": 396, "pair_future_entries": 396,
    "world_loop_entries": 396, "rank_cache_lookups": 792,
    "rank_cache_key_fields": 2376, "rank_board_tuples": 792,
    "rank_input_tuple_fields": 3588, "rank_cache_mapping_fields": 552,
    "rank_source_loop_and_container_fields": 84456,
    "raw_world_tuple_fields": 2376, "normalizer_entries": 396,
    "normalized_world_tuple_fields": 3564, "top_helper_entries": 10,
}
_PHYSICAL_ENUMERATION = sum(_PHYSICAL_ENUMERATION_TERMS.values())
_TREE_MAPPING_LAYOUT = 16_453 + 2_472
_TREE_CONSTRUCTOR_WORK = (111_981 - 16_453) + (16_774 - 2_472)
_TREE_TRAVERSALS = 3 * (
    PHYSICAL["states"] + PHYSICAL["decision_edges"] + PHYSICAL["chance_edges"]
    + COMPACT["states"] + COMPACT["decision_edges"] + COMPACT["chance_edges"]
) + 2
_TREE_ISOMORPHISM_TERMS = {
    "node_pairs": PHYSICAL["states"],
    "decision_actor_checks": PHYSICAL["decisions"],
    "action_edge_fields": 5 * PHYSICAL["decision_edges"],
    "terminal_fields": 4 * PHYSICAL["terminals"],
    "chance_edge_fields": 2 * PHYSICAL["chance_edges"],
    "branch_set_entries": 2 * (48 + 7) * PHYSICAL["chance_nodes"],
    "history_fields": 3 * (6297 + 45),
}
_TREE_ISOMORPHISM = sum(_TREE_ISOMORPHISM_TERMS.values())
_PREFIX_LAYOUTS = 9 * (PHYSICAL["worlds"] + COMPACT["worlds"])
_VALIDATION_AGGREGATION = (
    2 * (6 * PHYSICAL["worlds"] + 2 * PHYSICAL["prefix_edges"]
         + PHYSICAL["marginal_slots"] + PHYSICAL["policy_rows"])
    + (6 * COMPACT["worlds"] + 2 * COMPACT["prefix_edges"]
       + COMPACT["marginal_slots"] + COMPACT["policy_rows"])
    + 2 * (PHYSICAL["worlds"] + PHYSICAL["policy_rows"])
    + 2 * (COMPACT["worlds"] + COMPACT["policy_rows"])
)
_CLASS_PARTITION = 4 * (3 * 48 + 2 * 52 + 4 * 12 + 2 * 4) + 64
_CLASS_MAPPING = 27_356 - 372 + _CLASS_PARTITION + 63 + 108  # owned source subtotal plus old shape charges
_INFO_LAYOUT = 10 * (1254 + 188) + (6297 + 926) + 7 * (3606 + 486) + 10
_REPORTING = 4096  # bounded header/configuration/planner/ledger logical fields
# Whole adapter meter calls: tree compare, infos, lift, class/one-off phases,
# storage and reservation checks; plus bounded tree-hook implementation fields.
_METER_OVERHEAD = 20 * (15458 + 5538 + 3607 + 200 + 200 + 200 + 3039) + 10 * 18925
_LIFT_SERIALIZATION = 30 * 3606 + 5 * 18105 + 12 * 8046
_FINAL_DIAGNOSTICS = 501_372

COMPONENT_KEYS = (
    "input_validation", "physical_enumeration", "tree_mapping_layout",
    "tree_constructor_work",
    "tree_traversals", "tree_isomorphism", "class_mapping", "info_layout",
    "reporting", "meter_overhead", "prefix_layouts",
    "validation_aggregation", "trainer_vector_work", "lift_serialization",
    "final_diagnostics",
)
COMPONENT_SET = frozenset(COMPONENT_KEYS)

_BASE_COMPONENTS = {
    "input_validation": 2 * (PHYSICAL["worlds"] + PHYSICAL["policy_rows"])
                         + 2 * (COMPACT["worlds"] + COMPACT["policy_rows"]),
    "physical_enumeration": _PHYSICAL_ENUMERATION,
    "tree_mapping_layout": _TREE_MAPPING_LAYOUT,
    "tree_constructor_work": _TREE_CONSTRUCTOR_WORK,
    "tree_traversals": _TREE_TRAVERSALS,
    "tree_isomorphism": _TREE_ISOMORPHISM,
    "class_mapping": _CLASS_MAPPING,
    "info_layout": _INFO_LAYOUT,
    "reporting": _REPORTING,
    "meter_overhead": _METER_OVERHEAD,
    "prefix_layouts": _PREFIX_LAYOUTS,
    "validation_aggregation": _VALIDATION_AGGREGATION,
    "trainer_vector_work": 0,  # filled per request
    "lift_serialization": _LIFT_SERIALIZATION,
    "final_diagnostics": _FINAL_DIAGNOSTICS,
}


def _strict_int(value: Any, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer (booleans are not accepted)")
    return value


def _tree_hook_shape(kind: str) -> dict[str, int]:
    shape = PHYSICAL if kind == "physical" else COMPACT if kind == "compact" else None
    if shape is None:
        raise ValueError("kind must be 'physical' or 'compact'")
    return {
        "decision": shape["decisions"],
        "chance": shape["chance_nodes"],
        "terminal": shape["terminals"],
        "total": shape["states"],
    }


class BoundedTreeCounts(MutableMapping[str, int]):
    """Bounded counter mapping passed directly to the tree constructor.

    The constructor calls ``counts.update(decision=0, ...)`` before allocation,
    then reserves each node by incrementing its category and ``total`` before
    materializing it. Each write is rejected as soon as it would exceed this
    fixed representation's reviewed shape.
    """

    def __init__(self, kind: str) -> None:
        expected = _tree_hook_shape(kind)
        self.kind = kind
        self._expected = dict(PHYSICAL if kind == "physical" else COMPACT)
        self._caps = {
            "decision": expected["decision"],
            "chance": expected["chance"],
            "terminal": expected["terminal"],
            "total": expected["total"],
        }
        self._values = {key: 0 for key in ("decision", "chance", "terminal", "total")}

    def __getitem__(self, key: str) -> int:
        if key not in self._values:
            raise KeyError(key)
        return self._values[key]

    def __setitem__(self, key: str, value: int) -> None:
        if key not in self._values:
            raise KeyError(key)
        if type(value) is not int or value < 0:
            raise ValueError("tree counter values must be nonnegative strict integers")
        if value < self._values[key]:
            raise ValueError("tree counters cannot decrease after reservation")
        if value > self._caps[key]:
            raise ValueError(f"{self.kind} {key} node cap exceeded before allocation")
        self._values[key] = value

    def __delitem__(self, key: str) -> None:
        raise ValueError("tree count keys cannot be removed")

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def update(self, *args: Any, **kwargs: int) -> None:
        incoming = dict(*args, **kwargs)
        if set(incoming) != set(self._values):
            raise ValueError("tree counter reset must provide exactly four fixed keys")
        if any(type(value) is not int or value != 0 for value in incoming.values()):
            raise ValueError("tree counters can only be initialized to zero")
        if any(self._values.values()):
            raise ValueError("tree counters cannot be reset after allocation starts")
        self._values = {key: 0 for key in self._values}

    @property
    def expected(self) -> dict[str, int]:
        return dict(self._expected)

    def preflight(self) -> "BoundedTreeCounts":
        if any(self._values.values()):
            raise ValueError("preflight must happen before the tree starts allocating")
        return self

    def verify_public_counts(self, observed: Mapping[str, Any]) -> dict[str, int]:
        expected = _tree_hook_shape(self.kind)
        if not isinstance(observed, Mapping) or set(observed) != set(expected):
            raise ValueError("allocation_counts must contain exactly decision/chance/terminal/total")
        for key, value in observed.items():
            if (type(value) is not int or value != self._values[key]
                    or value != expected[key]):
                raise ValueError(f"unexpected {self.kind} tree {key} count")
        return dict(self._values)

    def verify(self, observed: Mapping[str, Any]) -> dict[str, int]:
        """Verify all fixed census fields, including native allocation hook counts."""
        if not isinstance(observed, Mapping):
            raise ValueError("tree census must be a mapping")
        expected = self.expected
        if set(observed) == {"decision", "chance", "terminal", "total"}:
            return self.verify_public_counts(observed)
        if set(observed) != set(expected):
            raise ValueError("tree census fields do not match the fixed model")
        for key, value in observed.items():
            if type(value) is not int or value != expected[key]:
                raise ValueError(f"unexpected {self.kind} tree {key} count")
        return dict(expected)


def _storage_requirements() -> dict[str, int]:
    result: dict[str, int] = {}
    for label, shape in (("physical", PHYSICAL), ("compact", COMPACT)):
        for key in ("worlds", "states", "decisions", "terminals", "chance_nodes",
                    "chance_edges", "decision_edges", "policy_rows", "action_slots",
                    "prefix_edges", "marginal_slots", "legal_prefix_memberships"):
            result[f"{label}_{key}"] = shape[key]
    result["physical_and_compact_public_states"] = PHYSICAL["states"] + COMPACT["states"]
    result["physical_and_compact_policy_rows"] = PHYSICAL["policy_rows"] + COMPACT["policy_rows"]
    result["physical_and_compact_action_slots"] = PHYSICAL["action_slots"] + COMPACT["action_slots"]
    result["physical_and_compact_prefix_edges"] = PHYSICAL["prefix_edges"] + COMPACT["prefix_edges"]
    result["physical_and_compact_world_tuple_fields"] = 5 * (PHYSICAL["worlds"] + COMPACT["worlds"])
    result["physical_pair_future_list_peak_entries"] = PHYSICAL["rivers"]
    result["modeled_rank_cache_entries"] = _MODELED_RANK_INPUTS
    result["rank_cache_key_fields"] = 3 * _MODELED_RANK_INPUTS
    result["rank_cache_result_fields"] = 6 * _MODELED_RANK_INPUTS
    result["rank_input_tuple_peak_fields"] = 7
    result["physical_enumeration_peak_world_tuple_fields"] = 10 * PHYSICAL["worlds"]
    result["physical_selected_rivers"] = PHYSICAL["rivers"]
    result["physical_and_compact_tree_nodes"] = PHYSICAL["states"] + COMPACT["states"]
    result["physical_and_compact_tree_action_objects"] = 3218
    result["physical_and_compact_tree_action_tuple_fields"] = 2 * 3218
    result["physical_and_compact_tree_temporary_action_list_fields"] = 2 * 3218
    result["output_policy_rows"] = PHYSICAL["policy_rows"]
    result["output_action_slots"] = PHYSICAL["action_slots"]
    result["live_training_action_maps"] = 5 * COMPACT["action_slots"] + COMPACT["action_slots"]
    result["live_training_delta_action_slots"] = 2 * (COMPACT["action_slots"] // 2)
    result["maximum_recursion_depth"] = COMPACT["depth"]
    result["physical_output_board_slots"] = 18_012
    result["physical_output_row_dict_fields"] = 21_636
    result["physical_output_action_dict_fields"] = 40_230
    # `evaluate_profile` normalizes a fresh policy and rebuilds physical prefix
    # tables while the lifted result is still live. These are explicit peak
    # coexistence reservations, not Python byte/RSS estimates.
    result["lifted_probability_slots"] = PHYSICAL["action_slots"]
    result["diagnostic_normalized_probability_slots"] = PHYSICAL["action_slots"]
    result["lifted_and_diagnostic_probability_slots"] = 2 * PHYSICAL["action_slots"]
    result["lifted_policy_key_fields"] = 3 * PHYSICAL["policy_rows"]
    result["diagnostic_normalized_policy_key_fields"] = 0  # keys are reused by normalization
    result["lifted_and_diagnostic_policy_dict_entries"] = 2 * PHYSICAL["policy_rows"]
    result["diagnostic_concurrent_prefix_edges"] = 2 * PHYSICAL["prefix_edges"]
    result["diagnostic_concurrent_marginal_slots"] = 2 * PHYSICAL["marginal_slots"]
    result["diagnostic_recursion_depth"] = PHYSICAL["depth"]
    result["diagnostic_live_visit_frames"] = PHYSICAL["depth"] + 1
    result["diagnostic_peak_numeric_vector_slots"] = 132
    result["diagnostic_peak_list_tuple_fields"] = 159
    result["diagnostic_peak_policy_fallback_slots"] = 9
    result["diagnostic_prefix_tuple_width"] = 1
    result["compact_average_slots_during_diagnostics"] = COMPACT["action_slots"]
    result["class_validation_key_tuple_fields"] = 2376
    result["class_validation_map_and_set_entries"] = 1224
    result["class_member_temporary_tuple_fields"] = 72
    result["physical_and_compact_info_metadata_entries"] = 8184
    result["information_key_tuple_fields"] = 12276
    result["sorted_hand_list_peak_fields"] = 3
    result["prefix_legal_map_key_fields"] = 228
    result["prefix_legal_map_entries"] = 114
    result["prefix_legal_memberships"] = 324
    result["tree_decision_index_key_fields"] = 2884
    result["stored_and_transient_tree_history_fields"] = 7394
    result["both_prefix_edge_tuple_fields"] = 1836
    result["both_prefix_edge_container_slots"] = 468
    result["prefix_aggregation_edge_mass_slots"] = 918
    result["prefix_aggregation_edge_key_fields"] = 918
    result["prefix_aggregation_edge_mapping_entries"] = 459
    result["prefix_aggregation_outer_map_entries"] = 171
    result["physical_output_history_slots"] = 18105
    result["physical_output_container_slots"] = 11652
    result["class_blocked_card_set_entries"] = 40
    result["tree_equivalence_branch_set_entries"] = 55
    result["class_validation_sign_value_fields"] = 396
    result["class_validation_pair_key_fields"] = 36
    result["class_validation_pair_value_fields"] = 18
    result["class_partition_temporary_set_entries"] = 96
    result["private_hand_tuple_fields"] = 36
    result["private_hand_range_container_fields"] = 28
    result["training_live_row_map_entries"] = 3402
    result["training_peak_numeric_vector_slots"] = 216
    result["training_peak_probability_reference_slots"] = 30
    result["training_peak_action_child_references"] = 30
    result["training_peak_lookup_tuple_fields"] = 30
    result["training_live_frame_prefix_fields"] = 10
    result["class_label_tuple_peak_fields"] = 7
    return result


# Reviewed exact-equal ceilings are literal data, independent of the requirement
# calculation. A requirement increase must not silently widen its own ceiling.
_STORAGE_CEILINGS = MappingProxyType({
    "both_prefix_edge_container_slots": 468,
    "both_prefix_edge_tuple_fields": 1836,
    "class_blocked_card_set_entries": 40,
    "class_label_tuple_peak_fields": 7,
    "class_member_temporary_tuple_fields": 72,
    "class_partition_temporary_set_entries": 96,
    "class_validation_key_tuple_fields": 2376,
    "class_validation_map_and_set_entries": 1224,
    "class_validation_pair_key_fields": 36,
    "class_validation_pair_value_fields": 18,
    "class_validation_sign_value_fields": 396,
    "compact_action_slots": 1086,
    "compact_average_slots_during_diagnostics": 1086,
    "compact_chance_edges": 35,
    "compact_chance_nodes": 5,
    "compact_decision_edges": 420,
    "compact_decisions": 188,
    "compact_legal_prefix_memberships": 42,
    "compact_marginal_slots": 48,
    "compact_policy_rows": 486,
    "compact_prefix_edges": 54,
    "compact_states": 456,
    "compact_terminals": 263,
    "compact_worlds": 45,
    "diagnostic_concurrent_marginal_slots": 588,
    "diagnostic_concurrent_prefix_edges": 810,
    "diagnostic_live_visit_frames": 10,
    "diagnostic_normalized_policy_key_fields": 0,
    "diagnostic_normalized_probability_slots": 8046,
    "diagnostic_peak_list_tuple_fields": 159,
    "diagnostic_peak_numeric_vector_slots": 132,
    "diagnostic_peak_policy_fallback_slots": 9,
    "diagnostic_prefix_tuple_width": 1,
    "diagnostic_recursion_depth": 9,
    "information_key_tuple_fields": 12276,
    "lifted_and_diagnostic_policy_dict_entries": 7212,
    "lifted_and_diagnostic_probability_slots": 16092,
    "lifted_policy_key_fields": 10818,
    "lifted_probability_slots": 8046,
    "live_training_action_maps": 6516,
    "live_training_delta_action_slots": 1086,
    "maximum_recursion_depth": 9,
    "modeled_rank_cache_entries": 276,
    "output_action_slots": 8046,
    "output_policy_rows": 3606,
    "physical_action_slots": 8046,
    "physical_and_compact_action_slots": 9132,
    "physical_and_compact_info_metadata_entries": 8184,
    "physical_and_compact_policy_rows": 4092,
    "physical_and_compact_prefix_edges": 459,
    "physical_and_compact_public_states": 3495,
    "physical_and_compact_tree_action_objects": 3218,
    "physical_and_compact_tree_action_tuple_fields": 6436,
    "physical_and_compact_tree_nodes": 3495,
    "physical_and_compact_tree_temporary_action_list_fields": 6436,
    "physical_and_compact_world_tuple_fields": 2205,
    "physical_chance_edges": 240,
    "physical_chance_nodes": 5,
    "physical_decision_edges": 2798,
    "physical_decisions": 1254,
    "physical_enumeration_peak_world_tuple_fields": 3960,
    "physical_legal_prefix_memberships": 282,
    "physical_marginal_slots": 294,
    "physical_output_action_dict_fields": 40230,
    "physical_output_board_slots": 18012,
    "physical_output_container_slots": 11652,
    "physical_output_history_slots": 18105,
    "physical_output_row_dict_fields": 21636,
    "physical_pair_future_list_peak_entries": 48,
    "physical_policy_rows": 3606,
    "physical_prefix_edges": 405,
    "physical_selected_rivers": 48,
    "physical_states": 3039,
    "physical_terminals": 1780,
    "physical_worlds": 396,
    "prefix_aggregation_edge_key_fields": 918,
    "prefix_aggregation_edge_mapping_entries": 459,
    "prefix_aggregation_edge_mass_slots": 918,
    "prefix_aggregation_outer_map_entries": 171,
    "prefix_legal_map_entries": 114,
    "prefix_legal_map_key_fields": 228,
    "prefix_legal_memberships": 324,
    "private_hand_range_container_fields": 28,
    "private_hand_tuple_fields": 36,
    "rank_cache_key_fields": 828,
    "rank_cache_result_fields": 1656,
    "rank_input_tuple_peak_fields": 7,
    "sorted_hand_list_peak_fields": 3,
    "stored_and_transient_tree_history_fields": 7394,
    "training_live_frame_prefix_fields": 10,
    "training_live_row_map_entries": 3402,
    "training_peak_action_child_references": 30,
    "training_peak_lookup_tuple_fields": 30,
    "training_peak_numeric_vector_slots": 216,
    "training_peak_probability_reference_slots": 30,
    "tree_decision_index_key_fields": 2884,
    "tree_equivalence_branch_set_entries": 55
})


def _storage_caps() -> dict[str, int]:
    return dict(_STORAGE_CEILINGS)


def plan_request(iterations: int, discard: int,
                 resource_model: str = RESOURCE_MODEL) -> dict[str, Any]:
    """Preflight a complete fixed-fixture request without importing poker code."""
    if type(resource_model) is not str or resource_model != RESOURCE_MODEL:
        raise ValueError("unsupported resource model")
    t = _strict_int(iterations, "iterations")
    d = _strict_int(discard, "discard")
    if t <= 0 or d < 0 or d >= t:
        raise ValueError("require iterations > 0 and 0 <= discard < iterations")

    candidate_iterations = 9 * t
    physical_world_iterations = PHYSICAL["worlds"] * t
    if candidate_iterations > MAX_CANDIDATE_PAIR_ITERATIONS:
        raise ValueError("physical candidate-pair iteration cap exceeded")
    if physical_world_iterations > MAX_PHYSICAL_WORLD_ITERATIONS:
        raise ValueError("physical world iteration cap exceeded")
    if (PHYSICAL["states"] > MAX_PUBLIC_STATES
            or PHYSICAL["decisions"] > MAX_PUBLIC_DECISIONS
            or PHYSICAL["prefix_edges"] > MAX_PREFIX_EDGES
            or PHYSICAL["action_slots"] > MAX_INFO_ACTION_SLOTS):
        raise ValueError("fixed physical tree exceeds an unchanged structural cap")

    compact_world_proxy = COMPACT["worlds"] * 32 * 3 * t
    compact_dense_proxy = 3 * COMPACT["states"] * (3 * t + 3)
    if compact_world_proxy > MAX_COMPACT_WORLD_PROXY:
        raise ValueError("compact world proxy cap exceeded")
    if compact_dense_proxy > MAX_COMPACT_DENSE_PROXY:
        raise ValueError("compact dense proxy cap exceeded")

    trainer_vector_work = TRAINING_FIXED + TRAINING_PER_ITERATION * t
    complete_vector_work = trainer_vector_work + ONE_TIME_WORK_RESERVE
    if complete_vector_work > MAX_VECTOR_WORK:
        raise ValueError("complete modeled vector-work cap exceeded")
    # Reserve the full-T average-pass envelope; discard changes the actual
    # schedule metadata, but cannot relax complete-request admission.
    explicit_list_writes = 17_328 * t + 3_258
    if explicit_list_writes > MAX_EXPLICIT_LIST_WRITES:
        raise ValueError("explicit-list-write cap exceeded")

    components = dict(_BASE_COMPONENTS)
    components["trainer_vector_work"] = trainer_vector_work
    setup_component_total = sum(components.values()) - trainer_vector_work
    if setup_component_total > ONE_TIME_WORK_RESERVE:
        raise ValueError("one-time component reservations exceed setup reserve")

    requirements = _storage_requirements()
    storage_caps = _storage_caps()
    if set(storage_caps) != set(requirements):
        raise ValueError("logical storage cap inventory differs from requirements")
    for name, needed in requirements.items():
        ceiling = storage_caps[name]
        if type(ceiling) is not int or ceiling < needed:
            raise ValueError("logical storage preflight failed: " + name)

    # The old physical API's proxy is retained for comparison only. This new
    # class-model plan must not claim that the old physical guard passed.
    legacy_physical_world_proxy = PHYSICAL["worlds"] * 32 * 3 * t
    return {
        "resource_model": RESOURCE_MODEL,
        "requested": {"iterations": t, "discard": d},
        "fixture": {"physical": dict(PHYSICAL), "compact": dict(COMPACT)},
        "candidate_pair_iterations": candidate_iterations,
        "physical_world_iterations": physical_world_iterations,
        "modeled_rank_inputs": _MODELED_RANK_INPUTS,
        "modeled_rank_loop_cells": _RANK_LOOP_CELLS,
        "physical_enumeration_source_terms": dict(_PHYSICAL_ENUMERATION_TERMS),
        "tree_isomorphism_source_terms": dict(_TREE_ISOMORPHISM_TERMS),
        "compact_world_proxy": compact_world_proxy,
        "compact_dense_proxy": compact_dense_proxy,
        "legacy_physical_world_proxy": legacy_physical_world_proxy,
        "legacy_proxy_enforced": False,
        "trainer_vector_work": trainer_vector_work,
        "one_time_work_reserve": ONE_TIME_WORK_RESERVE,
        "complete_vector_work": complete_vector_work,
        "explicit_list_writes": explicit_list_writes,
        "explicit_list_write_limit": MAX_EXPLICIT_LIST_WRITES,
        "modeled_rank_key_constructions": 2 * _MODELED_RANK_INPUTS + 240,
        "schedule": {
            "regret_passes": 2 * t,
            "average_passes": t - d,
            "total_passes": 3 * t - d,
            "reserved_passes": 3 * t,
            "average_weight_sum": t * (t + 1) // 2 - d * (d + 1) // 2,
        },
        "components": components,
        "component_allowance_total": sum(components.values()),
        "setup_component_total": setup_component_total,
        "storage_requirements": requirements,
        "storage_caps": storage_caps,
    }


@dataclass
class PhaseBudget:
    """Runtime ledger for comparing observed fixed counts with plan ceilings."""

    plan: Mapping[str, Any]
    observed: dict[str, int] = field(default_factory=dict)
    reserved: dict[str, int] = field(default_factory=dict)
    storage_reserved: dict[str, int] = field(default_factory=dict)
    storage_observed: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        components = self.plan.get("components")
        if not isinstance(components, Mapping) or set(components) != set(COMPONENT_KEYS):
            raise ValueError("plan has an invalid component ledger")
        self.observed = {key: 0 for key in COMPONENT_KEYS}
        self.reserved = {key: 0 for key in COMPONENT_KEYS}
        self.storage_reserved = {}
        self.storage_observed = {}

    def reserve(self, component: str, amount: int) -> int:
        """Record a pre-call reservation; this is not an observed work count."""
        if component not in COMPONENT_SET:
            raise ValueError("unknown work component")
        value = _strict_int(amount, "reservation")
        if value < 0:
            raise ValueError("reservation cannot be negative")
        new_total = self.reserved[component] + value
        if new_total > self.plan["components"][component]:
            raise ValueError(f"{component} reservation exceeds planned allowance")
        self.reserved[component] = new_total
        return new_total

    def charge(self, component: str, amount: int) -> int:
        if component not in COMPONENT_SET:
            raise ValueError("unknown work component")
        value = _strict_int(amount, "charge")
        if value < 0:
            raise ValueError("charge cannot be negative")
        new_total = self.observed[component] + value
        ceiling = self.reserved[component] or self.plan["components"][component]
        if new_total > ceiling:
            raise ValueError(f"{component} observed work exceeds planned allowance")
        self.observed[component] = new_total
        return new_total

    def charge_storage(self, name: str, amount: int) -> int:
        caps = self.plan.get("storage_caps")
        if not isinstance(caps, Mapping) or name not in caps:
            raise ValueError("unknown storage counter")
        value = _strict_int(amount, "storage charge")
        if value < 0:
            raise ValueError("storage charge cannot be negative")
        high_water = max(self.storage_observed.get(name, 0), value)
        ceiling = self.storage_reserved.get(name, caps[name])
        if high_water > ceiling:
            raise ValueError(f"{name} exceeds its planned logical-slot cap")
        self.storage_observed[name] = high_water
        return high_water

    def reserve_storage(self, name: str, amount: int) -> int:
        """Record planned live slots separately from observed high-water slots."""
        caps = self.plan.get("storage_caps")
        if not isinstance(caps, Mapping) or name not in caps:
            raise ValueError("unknown storage counter")
        value = _strict_int(amount, "storage reservation")
        if value < 0 or value > caps[name]:
            raise ValueError(f"{name} storage reservation exceeds its cap")
        reserved = max(self.storage_reserved.get(name, 0), value)
        self.storage_reserved[name] = reserved
        return reserved

    def verify(self) -> dict[str, Any]:
        if sum(self.plan["components"].values()) != self.plan["component_allowance_total"]:
            raise ValueError("component plan total changed")
        if any(self.reserved[k] > self.plan["components"][k]
               or self.observed[k] > (self.reserved[k] or self.plan["components"][k])
               for k in COMPONENT_KEYS):
            raise ValueError("observed phase work exceeds plan")
        return {
            "planned": dict(self.plan["components"]),
            "reserved": dict(self.reserved),
            "observed": dict(self.observed),
            "storage_caps": dict(self.plan["storage_caps"]),
            "storage_reserved": dict(self.storage_reserved),
            "storage_observed": dict(self.storage_observed),
        }
