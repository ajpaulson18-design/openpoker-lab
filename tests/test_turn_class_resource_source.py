"""Source-derived bounded resource checks for the compact turn adapter."""
from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch


from pokerlab import postflop_solver, turn_class_vector_budget as budget
from pokerlab import turn_tail_adapter, turn_class_tail_adapter as adapter

class CompactResourceSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resource_model = budget.RESOURCE_MODEL
        cls.info_inputs = []
        original_make_infos = adapter._make_infos

        def capture_infos(nodes, legal_hands, phase):
            cls.info_inputs.append((nodes, legal_hands))
            return original_make_infos(nodes, legal_hands, phase)

        def uniform_without_cfr(_root, _worlds, infos, _iterations, _discard, **_kwargs):
            return {key: [1.0 / count] * count for key, count in infos.items()}

        # Build the real bounded fixture and meter its complete preparation.
        # The only substituted operation is CFR+: its replacement is uniform.
        with patch.object(adapter, "_make_infos", side_effect=capture_infos), \
             patch.object(adapter, "_train_original_weight_tail",
                          side_effect=uniform_without_cfr) as cls.trainer_mock:
            cls.result = adapter.solve_turn_class_tail(
                iterations=10, discard=0, resource_model=cls.resource_model)
        cls.trainer_mock.assert_called_once()

    def _plan(self):
        return budget.plan_request(10, 0, self.resource_model)

    def test_runtime_bills_match_independent_counts_from_actual_prep_and_lift(self):
        usage = self.result["resource_usage"]["resource_accounting"]
        observed = usage["observed"]
        plan = self._plan()

        # Reconstruct the _make_infos work from the actual physical and compact
        # tree/input maps captured during this bounded call.
        info_bill = 0
        info_rows = 0
        for nodes, legal_hands in self.info_inputs:
            info_bill += 3 + 2
            for (player, history) in nodes:
                info_bill += 10 + len(history)
                prefix = adapter._public_reveals(history)
                info_rows += len(legal_hands.get((player, prefix), ()))
            info_bill += 7 * sum(
                len(legal_hands.get((player, adapter._public_reveals(history)), ()))
                for player, history in nodes
            )

        rows = self.result["strategy"]
        lift_bill = (
            30 * len(rows)
            + 5 * sum(len(row["history"]) for row in rows)
            + 12 * sum(len(row["actions"]) for row in rows)
        )
        self.assertEqual(len(self.info_inputs), 2)
        self.assertEqual(info_rows, 4092)
        self.assertEqual(info_bill, 50_297)
        self.assertEqual(observed["info_layout"], info_bill)
        self.assertEqual(lift_bill, 295_257)
        self.assertEqual(observed["lift_serialization"], lift_bill)
        self.assertEqual(observed["class_mapping"], 28_435)
        self.assertEqual(plan["setup_component_total"], 1_970_224)
        self.assertEqual(plan["components"]["meter_overhead"], 754_090)
        self.assertEqual(self.result["info_sets"], 3606)
        self.assertEqual(self.result["worlds"], 396)
        self.assertEqual(self.result["training_representation"]["policy_rows"], 486)
        self.assertEqual(self.result["training_representation"]["action_slots"], 1086)

    def test_whole_work_and_named_storage_ledgers_stay_within_pre_reservations(self):
        usage = self.result["resource_usage"]["resource_accounting"]
        planned, reserved, observed = usage["planned"], usage["reserved"], usage["observed"]
        self.assertEqual(set(planned), set(reserved))
        self.assertEqual(set(planned), set(observed))
        for component in planned:
            self.assertLessEqual(observed[component], reserved[component], component)
            self.assertLessEqual(reserved[component], planned[component], component)

        plan = self._plan()
        requirements = plan["storage_requirements"]
        caps = plan["storage_caps"]
        storage_reserved = usage["storage_reserved"]
        storage_observed = usage["storage_observed"]
        self.assertEqual(len(caps), 97)
        self.assertEqual(len(requirements), 97)
        self.assertIsNot(requirements, caps)
        self.assertEqual(requirements["class_blocked_card_set_entries"], 40)
        self.assertEqual(requirements["class_label_tuple_peak_fields"], 7)
        self.assertEqual(set(requirements), set(caps))
        self.assertTrue(set(requirements).issubset(storage_reserved))
        for name, required in requirements.items():
            self.assertGreaterEqual(storage_reserved[name], required, name)
            self.assertLessEqual(storage_reserved[name], caps[name], name)
            self.assertLessEqual(storage_observed.get(name, 0), storage_reserved[name], name)
        for name, amount in storage_observed.items():
            self.assertLessEqual(amount, storage_reserved[name], name)

    def test_every_under_requirement_cap_rejects_during_pure_planning(self):
        requirements = budget._storage_requirements()
        baseline_caps = budget._storage_caps()
        self.assertEqual(set(requirements), set(baseline_caps))
        for name, required in requirements.items():
            with self.subTest(storage=name):
                caps = dict(baseline_caps)
                caps[name] = required - 1
                with patch.object(budget, "_storage_caps", return_value=caps):
                    with self.assertRaisesRegex(ValueError, name):
                        budget.plan_request(10, 0, self.resource_model)

    def test_one_under_requirement_cap_stops_caller_before_any_model_work(self):
        requirements = budget._storage_requirements()
        caps = dict(budget._storage_caps())
        name = sorted(requirements)[0]
        caps[name] = requirements[name] - 1
        with patch.object(budget, "_storage_caps", return_value=caps), \
             patch.object(adapter, "cards") as card_parse_mock, \
             patch.object(adapter, "_enumerate_worlds") as enumerate_mock, \
             patch.object(adapter, "_build_postflop_tree") as tree_mock, \
             patch.object(adapter, "_train_original_weight_tail") as trainer_mock:
            with self.assertRaisesRegex(ValueError, name):
                adapter.solve_turn_class_tail(
                    iterations=10, discard=0, resource_model=self.resource_model)
        card_parse_mock.assert_not_called()
        enumerate_mock.assert_not_called()
        tree_mock.assert_not_called()
        trainer_mock.assert_not_called()

    def test_inflated_requirement_above_literal_ceiling_is_rejected(self):
        requirements = dict(budget._storage_requirements())
        caps = budget._storage_caps()
        name = "class_blocked_card_set_entries"
        self.assertEqual(caps[name], 40)
        requirements[name] = caps[name] + 1
        with patch.object(budget, "_storage_requirements", return_value=requirements):
            with self.assertRaisesRegex(ValueError, name):
                budget.plan_request(10, 0, self.resource_model)

    def test_legacy_defaults_caps_and_plan_default_remain_compatible(self):
        plan = self._plan()
        self.assertEqual(plan, budget.plan_request(10, 0))
        signature = inspect.signature(turn_tail_adapter.solve_turn_tail)
        self.assertEqual(signature.parameters["iterations"].default, 1000)
        self.assertEqual(signature.parameters["discard"].default, 0)
        self.assertIsNone(signature.parameters["config"].default)
        self.assertIsNone(signature.parameters["river_config"].default)
        self.assertIsNone(signature.parameters["runouts"].default)
        self.assertEqual(postflop_solver._MAX_WORLD_NODE_WORK, 30_000_000)
        self.assertEqual(postflop_solver._MAX_PUBLIC_STATES, 250_000)
        self.assertEqual(budget.MAX_CANDIDATE_PAIR_ITERATIONS, 3_000_000)
        self.assertEqual(budget.MAX_PHYSICAL_WORLD_ITERATIONS, 3_000_000)
        self.assertEqual(budget.MAX_PUBLIC_STATES, 250_000)
        self.assertEqual(budget.MAX_PUBLIC_DECISIONS, 10_000)
        self.assertEqual(budget.MAX_PREFIX_EDGES, 250_000)
        self.assertEqual(budget.MAX_INFO_ACTION_SLOTS, 1_000_000)


if __name__ == "__main__":
    unittest.main()
