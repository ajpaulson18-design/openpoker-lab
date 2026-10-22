"""Versioned logical-work admission for explicit compact fixed-flop CFR+.

This is a rank-free forecast, not a trainer or a total memory/runtime bound.
The formula is valid only for the pinned shared CFR+ and strategy kernels and
the proved fixed 126-world, 466-row game. The legacy 140-sweep admission is
unchanged; this module describes a separately opted-in resource policy.
"""
from hashlib import sha256
from pathlib import Path


VERSION = "fixed-flop-class-cfrplus-logical-work-v1"
MAX_ITERATIONS = 560
LOGICAL_WORK_CAP = 76_000_000
WORLD_COUNT = 126
INFO_ROWS = 466
INFO_ACTION_SLOTS = 932
DECISIONS = 316
PUBLIC_ACTION_EDGES = 632
CHANCE_NODES = 58
TERMINALS = 627
TREE_EDGES_INCLUDING_CHANCE = 1000
MAX_WORLD_VISITS = 33
PHYSICAL_POLICY_ROWS = 16912
PHYSICAL_ACTION_SLOTS = 33824

# SHA256 after CRLF -> LF normalization. These files determine the shared
# recurrence and strategy-loop structure charged below.
KERNEL_LF_SHA256 = {
    "pokerlab/cfr_plus.py": "93694ac893f314a5264393410d61580d0c74d8d0ca0d65c9ea522d442a12e5f6",
    "pokerlab/cfr.py": "92017d8a3f6086fa5892a2a5ed99bb86f0734c01d03799e40866216b7797b1cb",
}


def _kernel_hashes(source_root):
    root = Path(source_root) if source_root is not None else Path(__file__).resolve().parents[1]
    observed = {}
    for relative, expected in KERNEL_LF_SHA256.items():
        path = root / relative
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError(f"Shared kernel exceeds source bound: {relative}")
            raw = path.read_bytes()
        except OSError as exc:
            raise ValueError(f"Cannot authenticate shared kernel {relative}") from exc
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError(f"Shared kernel exceeds source bound: {relative}")
        digest = sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
        if digest != expected:
            raise ValueError(f"Shared kernel source changed: {relative}")
        observed[relative] = digest
    return observed


def admit_compact_request(iterations, *, source_root=None):
    """Return a fresh JSONable forecast after validating request and kernel.

    Invalid iteration requests are rejected before source reads. All charged
    work is a named loop/callback/slot count; units are not CPU operations.
    """
    if type(iterations) is not int or not 1 <= iterations <= MAX_ITERATIONS:
        raise ValueError(f"Compact fixed-flop mode requires integer iterations in [1, {MAX_ITERATIONS}].")
    hashes = _kernel_hashes(source_root)

    # For any world, bound all visited nodes by 33. Thus each traversal pass
    # charges B=W*33. Decision, terminal and action work are safely bounded by
    # B even though their exact per-world counts are smaller.
    b = WORLD_COUNT * MAX_WORLD_VISITS
    i = INFO_ROWS
    per_sweep = {
        "outer_world_loop_entries": 3 * WORLD_COUNT,
        "chance_child_callback_calls": 3 * b,
        "node_kind_dispatches": 3 * b,
        "information_key_lookups_upper_bound": 3 * b,
        "terminal_value_callback_calls": 2 * b,
        "terminal_contribution_reads": 4 * b,
        # Per selected-world traversal, action plus deterministic chance
        # recursion is bounded by 2D+C <= 2(D+C) <= 2S. This charges all three
        # traversals (two regret updates and one average traversal).
        "action_and_deterministic_chance_child_recursions_upper_bound": 3 * 2 * b,
        "update_expected_value_action_terms": 2 * 2 * b,
        "owner_regret_update_action_slots": 2 * b,
        "average_profile_action_slots": 2 * b,
        "delta_dictionary_information_key_scans": 2 * i,
        "delta_dictionary_action_slots_zeroed": INFO_ACTION_SLOTS,
        "regret_clipping_information_rows": i,
        "regret_clipping_action_slots": INFO_ACTION_SLOTS,
        "profile_information_rows": 3 * i,
        # cfr.strategy: positive-part projection, mass sum, then normalized
        # division or uniform fallback, each iterating the two action slots.
        "strategy_action_slot_touches": 3 * INFO_ACTION_SLOTS * 3,
        "profile_dictionary_update_calls": 3,
    }
    work_per_sweep = sum(per_sweep.values())
    total_work = work_per_sweep * iterations

    # These are fixed, separately named counters, not part of T-scaled work.
    setup = {
        "proof_world_rows_pretraining": WORLD_COUNT,
        "pretraining_compact_nodes_visited_upper_bound": WORLD_COUNT * MAX_WORLD_VISITS,
        "information_rows_validated": i,
        "world_rows_converted_and_mass_checked": WORLD_COUNT,
        "regret_and_average_rows_initialized": 2 * i,
        "regret_and_average_action_slots_initialized": 2 * INFO_ACTION_SLOTS,
    }
    output = {
        "average_rows_finalized": i,
        "average_action_slots_summed": INFO_ACTION_SLOTS,
        "average_action_slots_divided_or_fallback_written": INFO_ACTION_SLOTS,
        "compact_output_action_slots": INFO_ACTION_SLOTS,
        "physical_policy_rows_lifted_and_diagnosed": PHYSICAL_POLICY_ROWS,
        "physical_policy_action_slots_lifted_and_diagnosed": PHYSICAL_ACTION_SLOTS,
    }
    fixed_work = sum(setup.values()) + sum(output.values())
    total_admitted_work = total_work + fixed_work
    storage = {
        "persistent_regret_action_slots": INFO_ACTION_SLOTS,
        "persistent_average_action_slots": INFO_ACTION_SLOTS,
        "current_profile_action_slots_per_profile": INFO_ACTION_SLOTS,
        "largest_single_player_delta_action_slots": 234 * 2,
        "one_updated_regret_row_old_and_new_temporary_action_slots": 2 * 2,
        "final_average_action_slots_while_regrets_and_sums_exist": INFO_ACTION_SLOTS,
        "recursion_stack_node_bound_per_world": MAX_WORLD_VISITS,
    }
    passes = 3 * iterations
    legacy_reference = {
        "physical_world_iterations_informational_only": 5940 * passes,
        "physical_decision_world_iterations_informational_only": 12 * 5940 * passes,
        "old_caps_enforced_by_this_mode": False,
    }
    if total_admitted_work > LOGICAL_WORK_CAP:
        raise ValueError("Compact fixed-flop admitted logical-work cap exceeded.")

    return {
        "version": VERSION,
        "requested_iterations": iterations,
        "kernel_lf_sha256": hashes,
        "dimensions": {
            "compact_worlds": WORLD_COUNT,
            "compact_information_rows": INFO_ROWS,
            "private_information_action_slots": INFO_ACTION_SLOTS,
            "public_decisions": DECISIONS,
            "public_action_edges": PUBLIC_ACTION_EDGES,
            "chance_nodes": CHANCE_NODES,
            "terminals": TERMINALS,
            "tree_edges_including_chance": TREE_EDGES_INCLUDING_CHANCE,
            "max_world_visits": MAX_WORLD_VISITS,
        },
        "per_sweep": per_sweep,
        "logical_work_per_sweep": work_per_sweep,
        "total_training_work": total_work,
        "fixed_setup_and_output_work": fixed_work,
        "total_admitted_work": total_admitted_work,
        "fixed_setup": setup,
        "fixed_output_and_diagnostics": output,
        "fixed_physical_preparation_reference": {
            "physical_worlds": 5940,
            "physical_public_states": 30812,
            "meaning": "Fixed proof/preparation census reference; detailed proof arithmetic is not modeled by these named counters.",
        },
        "storage_bookkeeping": storage,
        "legacy_physical_proxy_reference": legacy_reference,
        "cap": {"maximum_iterations": MAX_ITERATIONS, "maximum_total_admitted_logical_work": LOGICAL_WORK_CAP},
        "interpretation": (
            "Named logical loop and callback counts only. Fixed setup and output counters are included "
            "in total_admitted_work; physical preparation/replay arithmetic is represented only by a "
            "separate census reference. Storage entries are partial bookkeeping, not a total memory, "
            "CPU-time, RSS, convergence, or speed bound. Legacy physical caps are not enforced here."
        ),
    }


def validate_observed_dimensions(census, max_path_states, infos=None):
    """Strictly check proof-derived dimensions before compact training."""
    if not isinstance(census, dict) or type(max_path_states) is not int:
        raise ValueError("Compact fixed-flop dimensions are malformed.")
    expected = {
        "compact_public_states": 1001, "compact_decisions": DECISIONS,
        "compact_chance_nodes": CHANCE_NODES, "compact_terminals": TERMINALS,
        "compact_worlds": WORLD_COUNT, "compact_policy_rows": INFO_ROWS,
        "compact_action_slots": INFO_ACTION_SLOTS,
        "physical_policy_rows": PHYSICAL_POLICY_ROWS,
        "physical_action_slots": PHYSICAL_ACTION_SLOTS,
    }
    for key, value in expected.items():
        if type(census.get(key)) is not int or census[key] != value:
            raise ValueError(f"Compact fixed-flop census mismatch: {key}")
    if not 1 <= max_path_states <= MAX_WORLD_VISITS:
        raise ValueError("Compact fixed-flop per-world visit bound mismatch.")
    if infos is not None:
        if not isinstance(infos, dict) or len(infos) != INFO_ROWS:
            raise ValueError("Compact fixed-flop information rows mismatch.")
        player_rows = [0, 0]
        for key, actions in infos.items():
            if (not isinstance(key, tuple) or not key or type(key[0]) is not int or
                    key[0] not in (0, 1) or type(actions) is not int or actions != 2):
                raise ValueError("Compact fixed-flop information-set shape mismatch.")
            player_rows[key[0]] += 1
        if player_rows != [232, 234]:
            raise ValueError("Compact fixed-flop per-player information-row split mismatch.")
    return True
