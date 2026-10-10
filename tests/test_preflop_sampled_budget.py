import gc
import unittest
import weakref
from unittest.mock import patch

from pokerlab.postflop_solver import _Chance
from pokerlab.river_tree import _Action, _Node, _Terminal
from pokerlab import preflop_sampled_budget as budget


class PreflopSampledBudgetTests(unittest.TestCase):
    def toy(self):
        terminal = _Terminal("showdown", (1, 1))
        deeper = _Node(("a",), 1, (_Action("fold"), _Action("call")),
                       (terminal, terminal))
        chance = _Chance((), {"a": deeper, "b": terminal})
        root = _Node((), 0, (_Action("fold"), _Action("call")),
                     (terminal, chance))
        return root

    def test_hand_counted_all_actions_and_worst_single_chance_branch(self):
        result = budget.estimate_sampled_budget(
            self.toy(), {"one-info": 2}, 10, 3, chance_type=_Chance)
        # Root + fold + chance + deeper decision + its two terminals.
        self.assertEqual(result["node_visits_per_draw_upper_bound"], 6)
        self.assertEqual(result["action_cells_per_draw_upper_bound"], 4)
        self.assertEqual(result["world_draws"], 30)
        self.assertEqual(result["total_node_visits_upper_bound"], 180)
        self.assertEqual(result["total_action_cells_upper_bound"], 120)

    def test_caps_and_empty_policy(self):
        for name in ("MAX_SAMPLED_NODE_VISITS", "MAX_SAMPLED_ACTION_CELLS"):
            with patch.object(budget, name, 1):
                with self.assertRaisesRegex(ValueError, "Sampled training exceeds"):
                    budget.estimate_sampled_budget(self.toy(), {"x": 2}, 1, 1,
                                                   chance_type=_Chance)
                result = budget.estimate_sampled_budget(self.toy(), {}, 10000, 256,
                                                         chance_type=_Chance)
                self.assertEqual(result["world_draws"], 0)

    def test_cycle_rejection_and_prompt_tree_release(self):
        old = gc.isenabled()
        gc.disable()
        try:
            root = self.toy()
            ref = weakref.ref(root)
            budget.estimate_sampled_budget(root, {"x": 2}, 1, 1, chance_type=_Chance)
            del root
            self.assertIsNone(ref())
            root = self.toy()
            root.children = (root,)
            root.actions = (_Action("loop"),)
            with self.assertRaisesRegex(ValueError, "cycle"):
                budget.estimate_sampled_budget(root, {"x": 1}, 1, 1,
                                               chance_type=_Chance)
            # Remove the deliberately created input cycle before testing whether
            # the census itself retains a recursive closure.
            root.children = (_Terminal("showdown", (1, 1)),)
            ref = weakref.ref(root)
            del root
            self.assertIsNone(ref())
        finally:
            if old:
                gc.enable()


if __name__ == "__main__":
    unittest.main()
