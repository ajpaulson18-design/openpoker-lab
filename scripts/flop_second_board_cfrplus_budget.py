"""Versioned rank-free logical-work admission for the second-board flop game.

This separate envelope models named loops in the unchanged CFR+ recurrence.
It is tied to the fixed 170-world / 608-row census and the authenticated shared
CFR+ and strategy kernels. It is not a trainer or a total work, allocation,
runtime, memory, convergence, or speed bound.
"""
from scripts.flop_class_compact_budget import KERNEL_LF_SHA256, _kernel_hashes


VERSION = "fixed-flop-second-board-cfrplus-logical-work-v1"
MAX_ITERATIONS = 560
LOGICAL_WORK_CAP = 110_000_000

WORLD_COUNT = 170
INFO_ROWS = 608
INFO_ACTION_SLOTS = 1216
DECISIONS = 400
CHANCE_NODES = 68
TERMINALS = 802
MAX_WORLD_VISITS = 33
PHYSICAL_POLICY_ROWS = 16912
PHYSICAL_ACTION_SLOTS = 33824
COMPACT_TREE_SHA256 = "5b8b6d504a35e0023c9150476ba9bb91d10615eae9ec6bb0305071745ab98152"


def admit_second_board_request(iterations, *, source_root=None):
    """Return a fresh JSONable forecast after strict request and kernel checks.

    Invalid iteration values are rejected before reading shared kernel source.
    Work units count named loops, callbacks, and slots, not all arithmetic.
    """
    if type(iterations) is not int or not 1 <= iterations <= MAX_ITERATIONS:
        raise ValueError(
            f"Second-board fixed-flop mode requires integer iterations in [1, {MAX_ITERATIONS}].")
    hashes = _kernel_hashes(source_root)

    # Each world has at most 33 visited nodes. Two regret passes and one
    # averaging pass use the same conservative per-world traversal bound.
    b = WORLD_COUNT * MAX_WORLD_VISITS
    i = INFO_ROWS
    per_sweep = {
        "outer_world_loop_entries": 3 * WORLD_COUNT,
        "chance_child_callback_calls": 3 * b,
        "node_kind_dispatches": 3 * b,
        "information_key_lookups_upper_bound": 3 * b,
        "terminal_value_callback_calls": 2 * b,
        "terminal_contribution_reads": 4 * b,
        "action_and_deterministic_chance_child_recursions_upper_bound": 3 * 2 * b,
        "update_expected_value_action_terms": 2 * 2 * b,
        "owner_regret_update_action_slots": 2 * b,
        "average_profile_action_slots": 2 * b,
        "delta_dictionary_information_key_scans": 2 * i,
        "delta_dictionary_action_slots_zeroed": INFO_ACTION_SLOTS,
        "regret_clipping_information_rows": i,
        "regret_clipping_action_slots": INFO_ACTION_SLOTS,
        "profile_information_rows": 3 * i,
        "strategy_action_slot_touches": 3 * INFO_ACTION_SLOTS * 3,
        "profile_dictionary_update_calls": 3,
    }
    work_per_sweep = sum(per_sweep.values())
    training_work = work_per_sweep * iterations

    setup = {
        "proof_world_rows_pretraining": WORLD_COUNT,
        "pretraining_compact_nodes_visited_upper_bound": WORLD_COUNT * MAX_WORLD_VISITS,
        "information_rows_validated": i,
        "world_rows_converted_and_mass_checked": WORLD_COUNT,
        "world_mass_sum_terms": WORLD_COUNT,
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
    admitted_work = training_work + fixed_work
    storage = {
        "persistent_regret_action_slots": INFO_ACTION_SLOTS,
        "persistent_average_action_slots": INFO_ACTION_SLOTS,
        "current_profile_action_slots_per_profile": INFO_ACTION_SLOTS,
        "largest_single_player_delta_action_slots": 304 * 2,
        "one_updated_regret_row_old_and_new_temporary_action_slots": 2 * 2,
        "final_average_action_slots_while_regrets_and_sums_exist": INFO_ACTION_SLOTS,
        "recursion_stack_node_bound_per_world": MAX_WORLD_VISITS,
    }
    if admitted_work > LOGICAL_WORK_CAP:
        raise ValueError("Second-board fixed-flop admitted logical-work cap exceeded.")

    return {
        "version": VERSION,
        "requested_iterations": iterations,
        "kernel_lf_sha256": hashes,
        "compact_tree_sha256": COMPACT_TREE_SHA256,
        "cfrplus_recurrence": {
            "regret_passes_per_sweep": 2,
            "average_profile_passes_per_sweep": 1,
            "averaging_delay": 0,
            "named_passes_per_sweep": 3,
        },
        "dimensions": {
            "compact_worlds": WORLD_COUNT,
            "compact_information_rows": INFO_ROWS,
            "private_information_action_slots": INFO_ACTION_SLOTS,
            "public_decisions": DECISIONS,
            "chance_nodes": CHANCE_NODES,
            "terminals": TERMINALS,
            "max_world_visits": MAX_WORLD_VISITS,
            "physical_policy_rows": PHYSICAL_POLICY_ROWS,
            "physical_policy_action_slots": PHYSICAL_ACTION_SLOTS,
            "max_world_path_states": MAX_WORLD_VISITS,
            "own_hand_rows_per_player": {"player_0": 304, "player_1": 304},
        },
        "per_sweep": per_sweep,
        "logical_work_per_sweep": work_per_sweep,
        "total_training_work": training_work,
        "fixed_setup_and_output_work": fixed_work,
        "total_admitted_work": admitted_work,
        "fixed_setup": setup,
        "fixed_output": output,
        "partial_storage_bookkeeping": storage,
        "cap": {
            "maximum_iterations": MAX_ITERATIONS,
            "maximum_total_admitted_logical_work": LOGICAL_WORK_CAP,
        },
        "census_and_scope": {
            "compact_public_states": 1270,
            "compact_decisions": DECISIONS,
            "public_action_edges": 800,
            "tree_edges_including_chance": 1269,
            "compact_chance_nodes": CHANCE_NODES,
            "compact_terminals": TERMINALS,
            "compact_worlds": WORLD_COUNT,
            "compact_policy_rows": INFO_ROWS,
            "compact_action_slots": INFO_ACTION_SLOTS,
            "physical_policy_rows": PHYSICAL_POLICY_ROWS,
            "physical_action_slots": PHYSICAL_ACTION_SLOTS,
            "compact_tree_sha256": COMPACT_TREE_SHA256,
            "meaning": (
                "Named logical loop and bookkeeping counts only. All three passes and zero averaging delay "
                "are charged. Setup includes the explicit 170-entry binary64 mass sum. These counts do not "
                "model all arithmetic, runtime, allocation, or RSS and make no speed or strategy-quality claim."
            ),
        },
        "fixed_physical_preparation_census": {
            "oracle_worlds": 5940,
            "physical_public_states": 30812,
            "meaning": (
                "Separate fixed physical preparation census. These counts are not proof-work units, "
                "training-work units, or allocation/RSS bounds."
            ),
        },
    }


def validate_observed_dimensions(census, max_path_states, infos=None, *,
                                 require_compact_tree_hash=False):
    """Validate the new proof census and, when supplied, its information rows.

    The compact tree digest is optional unless explicitly required. This check
    authenticates dimensions and shape only; semantic game proof is separate.
    """
    if type(census) is not dict or type(max_path_states) is not int:
        raise ValueError("Second-board fixed-flop dimensions are malformed.")
    if type(require_compact_tree_hash) is not bool:
        raise ValueError("Second-board fixed-flop digest requirement must be a bool.")
    expected = {
        "compact_public_states": 1270,
        "compact_decisions": DECISIONS,
        "compact_chance_nodes": CHANCE_NODES,
        "compact_terminals": TERMINALS,
        "compact_worlds": WORLD_COUNT,
        "compact_policy_rows": INFO_ROWS,
        "compact_action_slots": INFO_ACTION_SLOTS,
        "physical_policy_rows": PHYSICAL_POLICY_ROWS,
        "physical_action_slots": PHYSICAL_ACTION_SLOTS,
    }
    for key, value in expected.items():
        if type(census.get(key)) is not int or census[key] != value:
            raise ValueError(f"Second-board fixed-flop census mismatch: {key}")
    if not 1 <= max_path_states <= MAX_WORLD_VISITS:
        raise ValueError("Second-board fixed-flop per-world visit bound mismatch.")
    observed_hash = census.get("compact_tree_sha256")
    if require_compact_tree_hash or observed_hash is not None:
        if type(observed_hash) is not str or observed_hash != COMPACT_TREE_SHA256:
            raise ValueError("Second-board fixed-flop compact tree digest mismatch.")
    if infos is not None:
        if type(infos) is not dict or len(infos) != INFO_ROWS:
            raise ValueError("Second-board fixed-flop information rows mismatch.")
        canonical_hands = {0: {"AdAs", "QdQs"}, 1: {"AsKh", "KdKs"}}
        player_rows = [0, 0]
        for key, actions in infos.items():
            if (type(key) is not tuple or len(key) != 3 or
                    type(key[0]) is not int or key[0] not in (0, 1) or
                    type(key[1]) is not str or key[1] not in canonical_hands[key[0]] or
                    type(key[2]) is not tuple or len(key[2]) > 32 or
                    any(type(token) is not str or len(token) > 256 for token in key[2]) or
                    type(actions) is not int or actions != 2):
                raise ValueError("Second-board fixed-flop information-set shape mismatch.")
            player_rows[key[0]] += 1
        if player_rows != [304, 304]:
            raise ValueError("Second-board fixed-flop per-player information-row split mismatch.")
    return True
