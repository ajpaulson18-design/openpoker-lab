"""Adversarial policy/model boundaries of the fixed turn class adapter."""
from dataclasses import replace
import inspect,math,unittest
from unittest.mock import patch
from pokerlab import postflop_solver,turn_class_tail_adapter as adapter
from pokerlab import turn_class_vector_budget as budget,turn_tail_adapter

class _Phase:
    def __init__(self, plan):
        self.budget = budget.PhaseBudget(plan)
        self.budget.reserve("tree_isomorphism", plan["components"]["tree_isomorphism"])
        self.budget.reserve_storage("maximum_recursion_depth", 9)

    def charge(self, component, amount):
        return self.budget.charge(component, amount)

    def charge_storage(self, name, amount):
        return self.budget.charge_storage(name, amount)


def _replace_first_terminal(node):
    if isinstance(node, adapter._Terminal):
        contributions = list(node.contributions)
        contributions[0] += 1.0
        return replace(node, contributions=tuple(contributions)), True
    if isinstance(node, adapter._Chance):
        branches = dict(node.branches)
        for card, child in branches.items():
            changed, found = _replace_first_terminal(child)
            if found:
                branches[card] = changed
                return replace(node, branches=branches), True
        return node, False
    if isinstance(node, adapter._Node):
        children = list(node.children)
        for index, child in enumerate(children):
            changed, found = _replace_first_terminal(child)
            if found:
                children[index] = changed
                return replace(node, children=tuple(children)), True
        return node, False
    raise TypeError("unrecognized public tree node")


class CompactTurnAdversarialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = budget.plan_request(10, 0, budget.RESOURCE_MODEL)
        board = adapter.cards(adapter.BOARD)
        cls.hands, cls.physical_worlds, cls.selected, cls.pair_count = (
            adapter._enumerate_worlds(
                board, adapter.OOP_RANGE, adapter.IP_RANGE,
                runouts=None, iterations=10,
            )
        )

    def _class_worlds(self, worlds=None, selected=None):
        phase = _Phase(self.plan)
        return adapter._class_worlds(
            self.hands,
            list(self.physical_worlds if worlds is None else worlds),
            self.selected if selected is None else tuple(selected),
            phase,
        )

    def test_lowered_complete_work_cap_stops_before_enumeration_ranking_or_training(self):
        with patch.object(budget, "MAX_VECTOR_WORK", 1), \
             patch.object(adapter, "_enumerate_worlds") as enumerate_mock, \
             patch.object(adapter, "_prefix_hand_index") as layout_mock, \
             patch.object(adapter, "_train_original_weight_tail") as trainer_mock:
            with self.assertRaisesRegex(ValueError, "complete modeled vector-work cap exceeded"):
                adapter.solve_turn_class_tail(
                    iterations=10, discard=0, resource_model=budget.RESOURCE_MODEL)
        enumerate_mock.assert_not_called()
        layout_mock.assert_not_called()
        trainer_mock.assert_not_called()

    def test_class_mapping_rejects_mass_sign_and_missing_support_corruption(self):
        base = list(self.physical_worlds)
        i, j, mass, sign, river = base[0]
        wrong_mass = list(base)
        wrong_mass[0] = (i, j, mass + 0.01, sign, river)
        with self.assertRaisesRegex(ValueError, "mass differs"):
            self._class_worlds(wrong_mass)

        sign_index = next(index for index, world in enumerate(base) if world[3] != 0)
        bad = list(base)
        wi, wj, wm, ws, wr = bad[sign_index]
        bad[sign_index] = (wi, wj, wm, -ws, wr)
        with self.assertRaisesRegex(ValueError, "showdown sign"):
            self._class_worlds(bad)

        with self.assertRaisesRegex(ValueError, "physical deal count"):
            self._class_worlds(base[:-1])

        with self.assertRaisesRegex(ValueError, "48 unique cards"):
            self._class_worlds(base, self.selected[:-1])

    def test_physical_compact_tree_audit_rejects_terminal_payoff_mismatch(self):
        class_worlds = self._class_worlds()
        board = adapter.cards(adapter.BOARD)
        config = adapter._fixed_config()
        physical_root, physical_nodes, _, _, _ = postflop_solver._build_postflop_tree(
            board, config, river_config=config, worlds=self.physical_worlds)
        compact_root, compact_nodes, _, _, _ = postflop_solver._build_postflop_tree(
            board, config, river_config=config, worlds=class_worlds)
        self.assertEqual(len(physical_nodes), 1254)
        self.assertEqual(len(compact_nodes), 188)
        adapter._assert_tree_equivalent(physical_root, compact_root, _Phase(self.plan))
        corrupted, changed = _replace_first_terminal(compact_root)
        self.assertTrue(changed)
        with self.assertRaisesRegex(ValueError, "terminal refunds/payoffs differ"):
            adapter._assert_tree_equivalent(physical_root, corrupted, _Phase(self.plan))

    def _run_without_trainer(self, corruption):
        cached_enum = (self.hands, self.physical_worlds, self.selected, self.pair_count)

        def malformed_tail(_root, _worlds, infos, _iterations, _discard, **_kwargs):
            result = {
                key: [1.0 / action_count] * action_count
                for key, action_count in infos.items()
            }
            first_key = next(iter(result))
            if corruption == "missing":
                del result[first_key]
            elif corruption == "nan":
                result[first_key][0] = math.nan
            else:
                raise AssertionError("unknown test corruption")
            return result

        with patch.object(adapter, "_enumerate_worlds", return_value=cached_enum), \
             patch.object(adapter, "_train_original_weight_tail", side_effect=malformed_tail):
            return adapter.solve_turn_class_tail(
                iterations=10, discard=0, resource_model=budget.RESOURCE_MODEL)

    def test_compact_policy_lift_rejects_missing_row_before_diagnostics(self):
        with patch.object(adapter, "evaluate_profile") as diagnostics:
            with self.assertRaisesRegex(ValueError, "does not cover a physical legal row"):
                self._run_without_trainer("missing")
        diagnostics.assert_not_called()

    def test_compact_policy_lift_rejects_nonfinite_probability_before_acceptance(self):
        with self.assertRaises(ValueError):
            self._run_without_trainer("nan")

    def test_existing_production_admission_caps_and_default_model_are_unchanged(self):
        signature = inspect.signature(turn_tail_adapter.solve_turn_tail)
        compact_signature = inspect.signature(adapter.solve_turn_class_tail)
        self.assertIs(compact_signature.parameters["resource_model"].default, inspect.Parameter.empty)
        self.assertEqual(budget.plan_request(10, 0),
                         budget.plan_request(10, 0, budget.RESOURCE_MODEL))
        self.assertIsNone(signature.parameters["config"].default)
        self.assertIsNone(signature.parameters["river_config"].default)
        self.assertIsNone(signature.parameters["runouts"].default)
        self.assertEqual(signature.parameters["iterations"].default, 1000)
        self.assertEqual(signature.parameters["discard"].default, 0)
        self.assertEqual(budget.RESOURCE_MODEL, "turn-seven-class-vector-v1")
        self.assertEqual(budget.MAX_CANDIDATE_PAIR_ITERATIONS, 3_000_000)
        self.assertEqual(budget.MAX_PHYSICAL_WORLD_ITERATIONS, 3_000_000)
        self.assertEqual(budget.MAX_PUBLIC_STATES, 250_000)
        self.assertEqual(budget.MAX_PUBLIC_DECISIONS, 10_000)
        self.assertEqual(budget.MAX_PREFIX_EDGES, 250_000)
        self.assertEqual(budget.MAX_INFO_ACTION_SLOTS, 1_000_000)
        self.assertEqual(postflop_solver._MAX_WORLD_NODE_WORK, 30_000_000)
        self.assertEqual(postflop_solver._MAX_PUBLIC_STATES, 250_000)
        self.assertEqual(adapter.MAX_INFO_ACTION_SLOTS, 1_000_000)


if __name__ == "__main__":
    unittest.main()
