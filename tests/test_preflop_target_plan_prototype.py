import unittest
import weakref
from unittest.mock import patch

from pokerlab.postflop_solver import _Chance
from pokerlab.public_cfr import _aggregate_prefixes, _cfrplus_target_deltas
from pokerlab.river_tree import _Action, _Node, _Terminal
from scripts import preflop_target_plan_prototype as prototype


def _fixture():
    fold_a = _Terminal("fold", (0.5, 1.0), 0)
    show_a = _Terminal("showdown", (1.0, 1.0))
    fold_b = _Terminal("fold", (0.5, 1.5), 1)
    show_b = _Terminal("showdown", (1.25, 1.25))
    after_a = _Node(("A", "bb"), 1,
                    (_Action("fold"), _Action("call")), (fold_a, show_a))
    after_b = _Node(("B", "bb"), 1,
                    (_Action("fold"), _Action("call")), (fold_b, show_b))
    chance = _Chance(("board",), {"A": after_a, "B": after_b})
    root = _Node(("preflop",), 0,
                 (_Action("fold"), _Action("continue")),
                 (_Terminal("fold", (0.5, 1.0), 1), chance))
    worlds = (
        (0, 1, 0.10, 1, "A"),
        (0, 3, 0.20, -1, "A"),
        (2, 1, 0.30, -1, "B"),
        (2, 3, 0.40, 1, "B"),
    )
    infos = {
        (0, 0, root.history): 2,
        (0, 2, root.history): 2,
        (1, 1, after_a.history): 2,
        (1, 3, after_a.history): 2,
        (1, 1, after_b.history): 2,
        (1, 3, after_b.history): 2,
    }
    hand_counts = (3, 4)  # dense holes at SB hand 1 and BB hands 0, 2
    edges, _marginals = _aggregate_prefixes(worlds, hand_counts)
    return root, worlds, infos, hand_counts, edges


class PreflopTargetPlanPrototypeTests(unittest.TestCase):
    def test_exact_delta_parity_both_players_and_missing_strategy_rows(self):
        root, _worlds, infos, hand_counts, edges = _fixture()
        plan = prototype.compile_target_plan(
            root, edges, infos, hand_counts, 0.25, _Chance)
        profiles = (
            {
                (0, 0, root.history): [0.7, 0.3],
                (1, 1, ("A", "bb")): [0.25, 0.75],
                (1, 3, ("A", "bb")): [0.8, 0.2],
                (1, 1, ("B", "bb")): [0.4, 0.6],
            },
            {
                (0, 0, root.history): [0.01, 0.99],
                (0, 2, root.history): [0.51, 0.49],
                (1, 3, ("B", "bb")): [0.125, 0.875],
            },
        )
        for current in profiles:
            for target_player in (0, 1):
                with self.subTest(profile=profiles.index(current),
                                  target=target_player):
                    expected = _cfrplus_target_deltas(
                        root, edges, infos, current, target_player,
                        hand_counts, 0.25, _Chance)
                    actual = plan.target_deltas(current, target_player)
                    self.assertEqual(actual, expected)

        self.assertEqual(plan.metadata["chance_records"], 1)
        self.assertEqual(plan.metadata["decision_records"], 3)
        self.assertGreater(plan.metadata["terminal_edge_references"],
                           len(edges[()]))  # same prefix reused by sibling terminals
        self.assertEqual(plan.metadata["key_references"], 3 + 2 * 4)

    def test_caps_reject_during_census_before_record_allocation(self):
        root, _worlds, infos, hand_counts, edges = _fixture()
        with patch.object(prototype, "_PlanRecord",
                          side_effect=AssertionError("compiled record allocated")):
            cases = (
                ("max_records", 1, "record cap"),
                ("max_info_references", 1, "information-row reference cap"),
                ("max_key_references", 1, "key-reference cap"),
                ("max_child_references", 1, "child-reference cap"),
                ("max_terminal_edge_references", 1, "terminal-edge reference cap"),
            )
            for cap_name, cap, error in cases:
                with self.subTest(cap=cap_name):
                    with self.assertRaisesRegex(ValueError, error):
                        prototype.compile_target_plan(
                            root, edges, infos, hand_counts, 0.25, _Chance,
                            **{cap_name: cap})

    def test_info_partition_is_deferred_until_census_passes(self):
        root, _worlds, source_infos, hand_counts, edges = _fixture()

        class CountingDict(dict):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.items_calls = 0

            def items(self):
                self.items_calls += 1
                return super().items()

        infos = CountingDict(source_infos)
        with self.assertRaisesRegex(ValueError, "record cap"):
            prototype.compile_target_plan(root, edges, infos, hand_counts, 0.25,
                                          _Chance, max_records=1)
        self.assertEqual(infos.items_calls, 1)  # validation only, no partition copy

        infos = CountingDict(source_infos)
        prototype.compile_target_plan(root, edges, infos, hand_counts, 0.25, _Chance)
        self.assertEqual(infos.items_calls, 2)  # validation then post-census partition

    def test_cycle_and_unsupported_nodes_fail_closed(self):
        cyclic = _Node(("cycle",), 0, (_Action("next"),), ())
        cyclic.children = (cyclic,)
        with self.assertRaisesRegex(ValueError, "cycle"):
            prototype.compile_target_plan(cyclic, {}, {}, (1, 1), 0.0, _Chance)

        invalid = _Node(("invalid",), 0, (_Action("bad"),), (object(),))
        with self.assertRaisesRegex(TypeError, "unsupported public node"):
            prototype.compile_target_plan(invalid, {}, {}, (1, 1), 0.0, _Chance)
        with self.assertRaisesRegex(ValueError, "half_pot"):
            prototype.compile_target_plan(invalid, {}, {}, (1, 1), 10**10000, _Chance)

    def test_plan_or_error_does_not_leave_recursive_closure_references(self):
        class Token:
            pass

        token = Token()
        token_ref = weakref.ref(token)
        history = (token,)
        root = _Node(history, 0, (_Action("only"),),
                     (_Terminal("showdown", (1.0, 1.0)),))
        infos = {(0, 0, history): 1}
        edges = {(): ((0, 0, 1.0, 1.0),)}
        plan = prototype.compile_target_plan(root, edges, infos, (1, 1), 0.5, _Chance)
        self.assertIsNotNone(token_ref())  # the compiled plan intentionally owns its history
        del plan, root, infos, history, token
        self.assertIsNone(token_ref())

        token = Token()
        token_ref = weakref.ref(token)
        history = (token,)
        root = _Node(history, 0, (_Action("bad"),), (object(),))
        try:
            prototype.compile_target_plan(root, {}, {}, (1, 1), 0.5, _Chance)
        except TypeError:
            pass
        else:
            self.fail("unsupported node should fail during census")
        del root, history, token
        self.assertIsNone(token_ref())


if __name__ == "__main__":
    unittest.main()
