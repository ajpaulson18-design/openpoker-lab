"""Pure admission and count-guard tests; no poker imports or solver calls."""
from __future__ import annotations

import copy
import unittest

from pokerlab.turn_class_vector_budget import (
    BoundedTreeCounts,
    COMPONENT_KEYS,
    COMPACT,
    MAX_COMPACT_DENSE_PROXY,
    MAX_COMPACT_WORLD_PROXY,
    MAX_VECTOR_WORK,
    PHYSICAL,
    PhaseBudget,
    RESOURCE_MODEL,
    plan_request,
)


class FixedVectorBudgetTests(unittest.TestCase):
    def test_t6000_plan_covers_full_request_and_reports_schedule(self) -> None:
        plan = plan_request(6000, 2000)
        self.assertEqual(plan["resource_model"], RESOURCE_MODEL)
        self.assertEqual(plan["candidate_pair_iterations"], 54_000)
        self.assertEqual(plan["physical_world_iterations"], 2_376_000)
        self.assertEqual(plan["compact_world_proxy"], 25_920_000)
        self.assertEqual(plan["compact_dense_proxy"], 24_628_104)
        self.assertEqual(plan["trainer_vector_work"], 450_960_288)
        self.assertEqual(plan["complete_vector_work"], 452_960_288)
        self.assertEqual(plan["explicit_list_writes"], 103_971_258)
        self.assertEqual(plan["schedule"], {
            "regret_passes": 12_000,
            "average_passes": 4_000,
            "total_passes": 16_000,
            "reserved_passes": 18_000,
            "average_weight_sum": 16_002_000,
        })
        self.assertLess(plan["complete_vector_work"], MAX_VECTOR_WORK)
        self.assertLess(plan["compact_world_proxy"], MAX_COMPACT_WORLD_PROXY)
        self.assertLess(plan["compact_dense_proxy"], MAX_COMPACT_DENSE_PROXY)
        self.assertFalse(plan["legacy_proxy_enforced"])
        self.assertGreater(plan["legacy_physical_world_proxy"], 30_000_000)
        self.assertEqual(plan["modeled_rank_inputs"], 276)
        self.assertEqual(plan["modeled_rank_loop_cells"], 48_852)
        self.assertEqual(plan["components"]["tree_mapping_layout"], 18_925)
        self.assertEqual(plan["components"]["tree_constructor_work"], 109_830)
        self.assertEqual(plan["components"]["tree_traversals"], 20_966)
        self.assertEqual(plan["components"]["tree_isomorphism"], 45_459)
        self.assertEqual(sum(plan["tree_isomorphism_source_terms"].values()), 45_459)
        self.assertEqual(plan["components"]["physical_enumeration"], 104_312)
        self.assertEqual(sum(plan["physical_enumeration_source_terms"].values()), 104_312)
        self.assertEqual(plan["storage_caps"]["physical_enumeration_peak_world_tuple_fields"], 3960)
        self.assertEqual(plan["storage_caps"]["physical_and_compact_world_tuple_fields"], 2205)
        self.assertNotIn("explicit_list_writes", plan["storage_caps"])
        self.assertEqual(plan["explicit_list_writes"], 103_971_258)

    def test_t790_uses_new_class_proxy_and_marks_old_proxy_informational(self) -> None:
        plan = plan_request(790, 100)
        self.assertLessEqual(plan["compact_world_proxy"], MAX_COMPACT_WORLD_PROXY)
        self.assertLessEqual(plan["compact_dense_proxy"], MAX_COMPACT_DENSE_PROXY)
        self.assertGreater(plan["legacy_physical_world_proxy"], 30_000_000)
        self.assertFalse(plan["legacy_proxy_enforced"])
        self.assertLess(plan["complete_vector_work"], MAX_VECTOR_WORK)

    def test_discard_does_not_reduce_full_t_admission(self) -> None:
        small_discard = plan_request(500, 0)
        large_discard = plan_request(500, 499)
        for key in ("candidate_pair_iterations", "physical_world_iterations",
                    "compact_world_proxy", "compact_dense_proxy", "trainer_vector_work",
                    "complete_vector_work"):
            self.assertEqual(small_discard[key], large_discard[key])
        self.assertGreater(small_discard["schedule"]["average_passes"],
                           large_discard["schedule"]["average_passes"])
        self.assertEqual(small_discard["schedule"]["reserved_passes"], 1500)

    def test_strict_integer_and_resource_model_validation(self) -> None:
        for bad_t, bad_d in ((True, 0), (10, False), (10.0, 0), ("10", 0), (0, 0), (10, -1), (10, 10)):
            with self.subTest(iterations=bad_t, discard=bad_d):
                with self.assertRaises(ValueError):
                    plan_request(bad_t, bad_d)
        with self.assertRaises(ValueError):
            plan_request(10, 0, "other-model")

        class ImplicitOptIn:
            def __eq__(self, other):
                return True

        with self.assertRaises(ValueError):
            plan_request(10, 0, ImplicitOptIn())

    def test_complete_request_cap_preflight(self) -> None:
        # The max T allowed by the full-vector envelope is rejected before any
        # external constructor could be called; this module imports none.
        with self.assertRaisesRegex(ValueError, "vector-work"):
            plan_request(6627, 6626)
        # T=6000 is admitted only by the class proxies; the ordinary physical
        # 30m comparison remains visible and explicitly unenforced.
        plan = plan_request(6000, 5999)
        self.assertEqual(plan["requested"]["iterations"], 6000)
        self.assertFalse(plan["legacy_proxy_enforced"])


class FixedTreeCountGuardTests(unittest.TestCase):
    def test_native_tree_hook_counts_and_full_fixed_census(self) -> None:
        for kind, shape in (("physical", PHYSICAL), ("compact", COMPACT)):
            guard = BoundedTreeCounts(kind)
            self.assertIs(guard.preflight(), guard)
            guard.update(decision=0, chance=0, terminal=0, total=0)
            for key, source_key in (("decision", "decisions"), ("chance", "chance_nodes"),
                                    ("terminal", "terminals")):
                guard[key] = shape[source_key]
            guard["total"] = shape["states"]
            native = {key: guard[key] for key in guard}
            self.assertEqual(guard.verify_public_counts(native), native)
            self.assertEqual(guard.verify(shape), shape)

    def test_tree_count_guard_rejects_mutated_missing_extra_and_bool_counts(self) -> None:
        guard = BoundedTreeCounts("compact")
        correct = {"decision": 188, "chance": 5, "terminal": 263, "total": 456}
        for mutate in (
            lambda row: row.update(total=455),
            lambda row: row.update(decision=True),
            lambda row: row.pop("chance"),
            lambda row: row.update(unexpected=0),
        ):
            row = copy.deepcopy(correct)
            mutate(row)
            with self.subTest(row=row):
                with self.assertRaises(ValueError):
                    guard.verify_public_counts(row)
        with self.assertRaises(ValueError):
            BoundedTreeCounts("other")
        guard["total"] = 1
        with self.assertRaisesRegex(ValueError, "cannot be reset"):
            guard.update(decision=0, chance=0, terminal=0, total=0)

    def test_tree_reserve_counter_rejects_before_next_node_is_materialized(self) -> None:
        counts = BoundedTreeCounts("compact").preflight()
        # Mirrors the production hook order: the counter write is performed
        # before the caller appends/materializes a node.
        counts["total"] = counts.expected["states"]
        allocated = []

        def reserve_then_allocate(kind: str) -> None:
            if counts["total"] >= counts.expected["states"]:
                raise ValueError("public-state cap exceeded before allocation")
            counts[kind] += 1
            counts["total"] += 1
            allocated.append(kind)

        with self.assertRaisesRegex(ValueError, "before allocation"):
            reserve_then_allocate("decision")
        self.assertEqual(allocated, [])

    def test_partial_tree_counter_self_verification_and_decrements_reject(self) -> None:
        partial = BoundedTreeCounts("compact").preflight()
        partial.update(decision=0, chance=0, terminal=0, total=0)
        partial["decision"] = 1
        partial["total"] = 1
        with self.assertRaises(ValueError):
            partial.verify_public_counts(partial)
        with self.assertRaisesRegex(ValueError, "cannot decrease"):
            partial["decision"] = 0


class PhaseBudgetTests(unittest.TestCase):
    def test_phase_ledger_separates_reservations_from_observations(self) -> None:
        plan = plan_request(10, 3)
        budget = PhaseBudget(plan)
        budget.charge("physical_enumeration", 9)
        budget.reserve("trainer_vector_work", plan["trainer_vector_work"])
        budget.charge("trainer_vector_work", 100)
        budget.reserve_storage("physical_enumeration_peak_world_tuple_fields", 3960)
        budget.charge_storage("physical_enumeration_peak_world_tuple_fields", 3960)
        budget.charge_storage("physical_worlds", PHYSICAL["worlds"])
        budget.charge_storage("compact_policy_rows", COMPACT["policy_rows"])
        ledger = budget.verify()
        self.assertEqual(tuple(ledger["planned"]), COMPONENT_KEYS)
        self.assertEqual(ledger["observed"]["physical_enumeration"], 9)
        self.assertEqual(ledger["planned"]["physical_enumeration"],
                         plan["components"]["physical_enumeration"])
        self.assertEqual(ledger["observed"]["trainer_vector_work"], 100)
        self.assertEqual(ledger["reserved"]["trainer_vector_work"], plan["trainer_vector_work"])
        self.assertEqual(ledger["storage_observed"]["physical_worlds"], 396)
        self.assertEqual(ledger["storage_observed"]["compact_policy_rows"], 486)
        self.assertEqual(ledger["storage_reserved"]["physical_enumeration_peak_world_tuple_fields"], 3960)
        self.assertEqual(ledger["storage_observed"]["physical_enumeration_peak_world_tuple_fields"], 3960)

    def test_phase_work_and_storage_caps_reject_before_recording_excess(self) -> None:
        plan = plan_request(10, 0)
        budget = PhaseBudget(plan)
        planned = plan["components"]["physical_enumeration"]
        budget.charge("physical_enumeration", planned)
        with self.assertRaisesRegex(ValueError, "exceeds planned"):
            budget.charge("physical_enumeration", 1)
        self.assertEqual(budget.observed["physical_enumeration"], planned)
        with self.assertRaises(ValueError):
            budget.charge("trainer_vector_work", True)
        with self.assertRaisesRegex(ValueError, "logical-slot cap"):
            budget.charge_storage("compact_action_slots", COMPACT["action_slots"] + 1)
        with self.assertRaisesRegex(ValueError, "reservation exceeds"):
            budget.reserve_storage("physical_worlds", PHYSICAL["worlds"] + 1)
        with self.assertRaises(ValueError):
            budget.charge_storage("physical_action_slots", False)
        with self.assertRaises(ValueError):
            budget.charge_storage("unknown", 1)

    def test_a_lowered_component_ceiling_rejects_full_reservation(self) -> None:
        plan = plan_request(10, 0)
        lowered = copy.deepcopy(plan)
        lowered["components"]["trainer_vector_work"] -= 1
        budget = PhaseBudget(lowered)
        with self.assertRaisesRegex(ValueError, "reservation exceeds"):
            budget.reserve("trainer_vector_work", plan["trainer_vector_work"])


if __name__ == "__main__":
    unittest.main()
