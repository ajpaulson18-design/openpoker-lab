"""Exact graph-only suit closure, malformed graph and bounded admission controls."""
from dataclasses import replace
from itertools import permutations
import unittest
from unittest.mock import patch

from pokerlab.shared_public_topology import (
    ActionRecord, ChanceVertex, DecisionVertex, SharedPublicTopology, TerminalVertex, TopologyLimits,
)
from pokerlab.suit_public_automorphism import verify_public_suit_automorphisms


IDENTITY = (tuple("cdhs"),)
SWAP = (tuple("cdhs"), tuple("dchs"))


def action(name="check", amount=0., raise_to=0.):
    return ActionRecord(name, amount, raise_to, False, name)


def graph(vertices, root=0, history=()):
    # The verifier independently derives graph order, reachability and depth;
    # it must not trust the producer census, so no census is needed here.
    return SharedPublicTopology(tuple(vertices), root, history, None, TopologyLimits())


def symmetric():
    return graph((ChanceVertex("flop", 4, (("2c3c4h", 1), ("2d3d4h", 2))),
        DecisionVertex(0, (action(),), (3,)), DecisionVertex(0, (action(),), (3,)),
        TerminalVertex("showdown", (1., 1.), None)))


class SuitPublicAutomorphismTests(unittest.TestCase):
    def test_symmetric_shared_graph_closes_without_expanding_occurrences(self):
        topology = symmetric()
        with patch.object(SharedPublicTopology, "iter_occurrences", side_effect=AssertionError("expanded occurrences")):
            receipt = verify_public_suit_automorphisms(topology, SWAP)
        self.assertTrue(receipt["full_public_graph_automorphism"])
        self.assertEqual(receipt["transformed_signature_insertions"], 0)
        self.assertEqual(receipt["expanded_occurrences_visited"], 0)
        self.assertEqual(receipt["unique_vertices"], 4)
        self.assertEqual(receipt["identity_signature_count"], 3)
        self.assertEqual(receipt["transformed_signature_lookups"], 8)
        self.assertEqual(receipt["additional_retained_entries_upper"], receipt["retained_entries_upper"])

    def test_physical_symmetric_four_street_graph_without_rank_or_worlds(self):
        from pokerlab.exact_selected_solver import _prepare_exact_selected
        from tests.test_four_street_certificate import _case
        from tests.test_selected_operator_solver import request
        case = _case(sb="AcAh:1,AdAh:1", bb="KcKh:1,KdKh:1", stacks=[2, 2])
        case["runouts"] = ["2c3c4h5s6h", "2d3d4h5s6h"]
        with patch("pokerlab.exact_selected_kernel.rank_hand", side_effect=AssertionError("rank")), \
             patch("pokerlab.preflop_solver._enumerate_physical_worlds", side_effect=AssertionError("worlds")):
            prepared = _prepare_exact_selected(request(case), pair_diagnostics="compact")
            with patch.object(SharedPublicTopology, "iter_occurrences", side_effect=AssertionError("expanded occurrences")):
                result = verify_public_suit_automorphisms(prepared.topology, SWAP)
        self.assertTrue(result["full_public_graph_automorphism"])
        self.assertEqual(result["unique_vertices"], len(prepared.topology.vertices))

    def test_terminal_payoff_difference_rejects(self):
        top = symmetric()
        vertices = list(top.vertices)
        vertices[2] = replace(vertices[2], child_ids=(4,))
        vertices.append(TerminalVertex("showdown", (1.5, 1.5), None))
        with self.assertRaisesRegex(ValueError, "missing.*signature|root signature"):
            verify_public_suit_automorphisms(graph(vertices), SWAP)

    def test_terminal_winner_difference_rejects(self):
        top = graph((ChanceVertex("flop", 4, (("2c3c4h", 1), ("2d3d4h", 2))),
            TerminalVertex("fold", (1., 1.), 0), TerminalVertex("fold", (1., 1.), 1)))
        with self.assertRaisesRegex(ValueError, "signature"):
            verify_public_suit_automorphisms(top, SWAP)

    def test_money_menu_and_player_differences_reject(self):
        for changed in (DecisionVertex(1, (action(),), (3,)),
                        DecisionVertex(0, (action(amount=.5),), (3,)),
                        DecisionVertex(0, (action("call"),), (3,))):
            with self.subTest(changed=changed):
                vertices = list(symmetric().vertices);vertices[2] = changed
                with self.assertRaisesRegex(ValueError, "signature"):
                    verify_public_suit_automorphisms(graph(vertices), SWAP)

    def test_context_sensitive_continuation_difference_rejects(self):
        top = graph((ChanceVertex("flop", 4, (("2c3c4h", 1), ("2d3d4h", 2))),
            ChanceVertex("turn", 5, (("5c", 3),)), ChanceVertex("turn", 5, (("5c", 3),)),
            TerminalVertex("showdown", (1., 1.), None)))
        with self.assertRaisesRegex(ValueError, "signature"):
            verify_public_suit_automorphisms(top, SWAP)

    def test_chance_branch_order_is_irrelevant_but_turn_river_positions_are_not(self):
        original = symmetric()
        reverse = replace(original, vertices=(replace(original.vertices[0], branches=tuple(reversed(original.vertices[0].branches))),) + original.vertices[1:])
        self.assertEqual(verify_public_suit_automorphisms(original, SWAP), verify_public_suit_automorphisms(reverse, SWAP))
        top = graph((ChanceVertex("turn", 5, (("5c", 1), ("5d", 2))),
            ChanceVertex("river", 6, (("6h", 3),)), ChanceVertex("river", 6, (("6s", 3),)),
            TerminalVertex("showdown", (1., 1.), None)))
        with self.assertRaisesRegex(ValueError, "signature"):
            verify_public_suit_automorphisms(top, SWAP)

    def test_changed_initial_history_rejects(self):
        top = graph((TerminalVertex("showdown", (1., 1.), None),), history=("flop@2c3c4h",))
        with self.assertRaisesRegex(ValueError, "initial public history"):
            verify_public_suit_automorphisms(top, SWAP)

    def test_shared_child_keeps_distinct_action_histories(self):
        top = graph((DecisionVertex(0, (action("check"), action("call")), (1, 1)),
                     TerminalVertex("showdown", (1., 1.), None)))
        before = tuple(occ.history for occ in top.iter_occurrences())
        receipt = verify_public_suit_automorphisms(top, tuple(permutations("cdhs")))
        self.assertEqual(before, ((), ("check",), ("call",)))
        self.assertEqual(tuple(occ.history for occ in top.iter_occurrences()), before)
        self.assertEqual(receipt["unique_edges"], 2)
        self.assertIn("No history or information rows are merged", receipt["scope"])

    def test_cycle_unreachable_and_invalid_ids_reject(self):
        cases = (graph((DecisionVertex(0, (action(),), (0,)),)),
                 graph((TerminalVertex("showdown", (1., 1.), None), TerminalVertex("showdown", (1., 1.), None))),
                 graph((DecisionVertex(0, (action(),), (2,)),)))
        for top in cases:
            with self.subTest(top=top), self.assertRaises(ValueError):
                verify_public_suit_automorphisms(top, IDENTITY)

    def test_malformed_menus_duplicate_labels_and_nonfinite_money_reject(self):
        cases = (graph((DecisionVertex(0, (action(),), ()),)),
            graph((DecisionVertex(0, (action(), action()), (1, 1)), TerminalVertex("showdown", (1., 1.), None))),
            graph((ChanceVertex("flop", 4, (("2c3c4h", 1), ("2c3c4h", 1))), TerminalVertex("showdown", (1., 1.), None))),
            graph((TerminalVertex("showdown", (float("nan"), 1.), None),)),
            graph((TerminalVertex("showdown", (1., -1.), None),)))
        for top in cases:
            with self.subTest(top=top), self.assertRaises(ValueError):
                verify_public_suit_automorphisms(top, IDENTITY)

    def test_improper_group_rejects(self):
        for group in (("dchs",), ("cdhs", "cdhs"), ("cdhs", "ccss"), ("cdhs", "dhcs")):
            with self.subTest(group=group), self.assertRaises(ValueError):
                verify_public_suit_automorphisms(symmetric(), group)

    def test_caps_reject_before_signature_interning(self):
        with self.assertRaisesRegex(ValueError, "admission"):
            verify_public_suit_automorphisms(symmetric(), SWAP, max_additional_work=1)
        with patch("pokerlab.suit_public_automorphism._children", side_effect=AssertionError("graph arrays reached")):
            with self.assertRaisesRegex(ValueError, "before local validation"):
                verify_public_suit_automorphisms(symmetric(), SWAP, max_additional_entries=1)

    def test_remaining_caller_budgets_reject_and_default_receipt_is_unchanged(self):
        top = symmetric()
        normal = verify_public_suit_automorphisms(top, SWAP)
        explicit = verify_public_suit_automorphisms(top, SWAP,
            max_additional_work=500_000_000, max_additional_entries=2_000_000)
        self.assertEqual(normal, explicit)
        for limits in ({"max_additional_work": 1}, {"max_additional_entries": 1}):
            with self.subTest(limits=limits), self.assertRaisesRegex(ValueError, "admission"):
                verify_public_suit_automorphisms(top, SWAP, **limits)
        fitted = verify_public_suit_automorphisms(top, SWAP,
            max_additional_work=normal["modeled_work_upper"],
            max_additional_entries=normal["additional_retained_entries_upper"])
        self.assertEqual(fitted["modeled_work_upper"], normal["modeled_work_upper"])
        self.assertEqual(fitted["modeled_work_limit"], normal["modeled_work_upper"])
        self.assertEqual(fitted["retained_entry_limit"], normal["additional_retained_entries_upper"])

    def test_remaining_caller_limits_are_exact_positive_bounded_integers(self):
        for key, ceiling in (("max_additional_work", 500_000_000), ("max_additional_entries", 2_000_000)):
            for value in (True, False, 0, -1, 1., None, ceiling + 1):
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, key):
                    verify_public_suit_automorphisms(symmetric(), SWAP, **{key: value})

    def test_tiny_work_rejects_before_group_composition_money_or_children(self):
        with patch("pokerlab.suit_public_automorphism._group", side_effect=AssertionError("group composition")), \
             patch("pokerlab.suit_public_automorphism._number", side_effect=AssertionError("money validation")), \
             patch("pokerlab.suit_public_automorphism._children", side_effect=AssertionError("child validation")):
            with self.assertRaisesRegex(ValueError, "before subgroup validation"):
                verify_public_suit_automorphisms(symmetric(), SWAP, max_additional_work=1)

    def test_signature_budget_reserved_before_money_and_child_validation(self):
        normal = verify_public_suit_automorphisms(symmetric(), SWAP)
        self.assertEqual(normal["modeled_work_upper"], normal["validation_work_upper"] + normal["signature_work_upper"])
        with patch("pokerlab.suit_public_automorphism._number", side_effect=AssertionError("money validation")), \
             patch("pokerlab.suit_public_automorphism._children", side_effect=AssertionError("child validation")):
            with self.assertRaisesRegex(ValueError, "before monetary/child validation"):
                verify_public_suit_automorphisms(symmetric(), SWAP,
                    max_additional_work=normal["validation_work_upper"])

    def test_signed_zero_money_identity_is_not_silently_canonicalized(self):
        top = graph((ChanceVertex("flop", 4, (("2c3c4h", 1), ("2d3d4h", 2))),
            TerminalVertex("showdown", (0., 0.), None), TerminalVertex("showdown", (-0., 0.), None)))
        with self.assertRaisesRegex(ValueError, "signature"):
            verify_public_suit_automorphisms(top, SWAP)


if __name__ == "__main__":
    unittest.main()
