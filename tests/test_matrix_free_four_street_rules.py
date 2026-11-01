import copy
import json
from fractions import Fraction
from itertools import combinations
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import four_street_validation as old_numeric
from scripts import matrix_free_four_street_rules as candidate
from scripts.matrix_free_certificate_budget import Budget
from scripts.matrix_free_selected_payoffs import PayoffModel
from tests.test_four_street_validation import CASE


def _compatible_prefix(model, prefix):
    prefix = set(prefix)
    for board in model.outcomes:
        if not set(board).issuperset(prefix):
            continue
        for hand0 in model.ranges[0]:
            if set(hand0) & set(prefix):
                continue
            for hand1 in model.ranges[1]:
                if set(hand0) & set(hand1) or set(hand1) & set(prefix):
                    continue
                if not ((set(hand0) | set(hand1)) & set(board)):
                    return True
    return False


def _candidate_signature(node, model):
    if isinstance(node, candidate.Decision):
        return ("decision", node.player, node.history, node.board,
                tuple((a.name, a.amount, a.raise_to, a.token) for a in node.actions),
                tuple(_candidate_signature(child, model) for child in node.children))
    if isinstance(node, candidate.Reveal):
        kept = [(prefix, child) for prefix, child in node.branches.items()
                if _compatible_prefix(model, prefix)]
        return ("reveal", node.history, node.board_length,
                tuple((prefix, _candidate_signature(child, model)) for prefix, child in kept))
    if isinstance(node, candidate.Terminal):
        return ("terminal", node.kind, node.committed, node.winner, node.matched)
    raise AssertionError(f"unexpected candidate node {type(node)!r}")


def _old_signature(node):
    if isinstance(node, old_numeric._Decision):
        return ("decision", node.player, node.history, node.board,
                tuple((a.name, a.amount, a.raise_to, a.token) for a in node.actions),
                tuple(_old_signature(child) for child in node.children))
    if isinstance(node, old_numeric.Reveal):
        return ("reveal", node.history, node.board_length,
                tuple((prefix, _old_signature(child)) for prefix, child in node.branches.items()))
    if isinstance(node, old_numeric._Terminal):
        committed = tuple(float(value) for value in node.contributions)
        return ("terminal", node.kind, committed, node.winner,
                float(min(node.contributions)))
    raise AssertionError(f"unexpected old node {type(node)!r}")


def _count_public_nodes(root):
    count = 0
    stack = [root]
    while stack:
        node = stack.pop()
        count += 1
        if isinstance(node, candidate.Decision):
            stack.extend(node.children)
        elif isinstance(node, candidate.Reveal):
            stack.extend(node.branches.values())
    return count


def _reveals(root):
    found = []
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, candidate.Decision):
            stack.extend(reversed(node.children))
        elif isinstance(node, candidate.Reveal):
            found.append(node)
            stack.extend(reversed(tuple(node.branches.values())))
    return found


class MatrixFreeFourStreetRulesTests(unittest.TestCase):
    def test_public_tree_matches_old_literal_rules_after_physical_branch_filter(self):
        model = candidate.build_public_model(CASE, Budget())
        literal = old_numeric.build_model(CASE)
        self.assertEqual(_candidate_signature(model.root, model), _old_signature(literal.root))
        self.assertEqual(model.counts["actual_public_nodes"], _count_public_nodes(model.root))
        self.assertEqual(model.counts["actual_public_nodes"], model.counts["public_nodes"])
        self.assertEqual(model.counts["actual_action_slots"], model.counts["actions"])
        self.assertEqual(model.counts["actual_reveal_edges"], model.counts["reveal_edges"])

    def test_short_all_in_and_fractional_local_rounding_match_literal_rules(self):
        short_all_in = {
            **CASE, "id": "matrix-free-short-all-in-control",
            "sb_range": "AsAd", "bb_range": "KsKd",
            "config": {"starting_stack": [2, 1], "small_blind": 0.5,
                        "big_blind": 1, "max_raises": 0},
            "runouts": ["2c3c4d7h8h"],
        }
        short_blind = {
            **short_all_in, "id": "matrix-free-short-blind-control",
            "config": {"starting_stack": [0.5, 20], "small_blind": 0.5,
                        "big_blind": 1, "max_raises": 0},
        }
        record = json.loads((Path(__file__).resolve().parents[1] /
                             "benchmarks" / "preflop-rounding-boundary-v1.json")
                            .read_text(encoding="utf-8"))
        fractional = {"id": record["fixture_id"], "sb_range": record["sb"],
                      "bb_range": record["bb"], "config": record["config"],
                      "runouts": record["runouts"], "flop_config": record["flop_config"],
                      "turn_config": record["turn_config"],
                      "river_config": record["river_config"]}
        for case in (short_all_in, short_blind, fractional):
            with self.subTest(case=case["id"]):
                model = candidate.build_public_model(case, Budget())
                literal = old_numeric.build_model(case)
                self.assertEqual(_candidate_signature(model.root, model),
                                 _old_signature(literal.root))

    def test_ranges_preserve_insertion_order_and_outcomes_canonicalize_only_flop(self):
        case = copy.deepcopy(CASE)
        case["sb_range"] = "KsKh,AsAd"
        case["bb_range"] = "QsQh"
        case["runouts"] = ["4d3c2c7h8h", "4d3c2c7hKc"]
        model = candidate.build_public_model(case)
        self.assertEqual(list(model.ranges[0]), [("Kh", "Ks"), ("Ad", "As")])
        self.assertEqual(model.outcomes[0][:3], ("2c", "3c", "4d"))
        self.assertEqual(model.outcomes[0][3:], ("7h", "8h"))
        self.assertEqual(model.case["runouts"][0], "2c 3c 4d 7h 8h")

    def test_terminal_carries_full_public_context_and_kind(self):
        case = copy.deepcopy(CASE)
        case["config"]["starting_stack"] = [0.4, 0.4]
        model = candidate.build_public_model(case)
        self.assertIsInstance(model.root, candidate.Terminal)
        self.assertEqual(model.root.kind, "showdown")
        self.assertIsNone(model.root.winner)
        self.assertEqual(model.root.board, ())
        self.assertEqual(model.root.history, ())
        self.assertEqual(model.root.matched, 0.4)
        self.assertEqual(model.decisions, ())

    def test_zero_support_selected_prefixes_are_retained_for_payoff_owner_to_filter(self):
        case = copy.deepcopy(CASE)
        case["sb_range"] = "AsAd"
        case["bb_range"] = "KsKd"
        case["runouts"] = ["As2c3c4d5h", "2c3c4d7h8h"]
        model = candidate.build_public_model(case)
        reveal = next(reveal for reveal in _reveals(model.root)
                      if reveal.board_length == 3)
        self.assertIn(("2c", "3c", "As"), reveal.branches)
        self.assertFalse(_compatible_prefix(model, ("2c", "3c", "As")))
        self.assertEqual(model.counts["selected_outcomes"], 2)
        payoffs = PayoffModel(model.ranges, model.outcomes, Budget())
        support = payoffs.prefix_support(("2c", "3c", "As"))
        self.assertEqual(support, ((False,), (False,)))

    def test_terminal_snapshot_is_accepted_by_matrix_free_payoff_interface(self):
        model = candidate.build_public_model(CASE)
        payoffs = PayoffModel(model.ranges, model.outcomes, Budget())
        leaves = []
        stack = [model.root]
        while stack:
            node = stack.pop()
            if isinstance(node, candidate.Terminal):
                leaves.append(node)
            elif isinstance(node, candidate.Decision):
                stack.extend(node.children)
            elif isinstance(node, candidate.Reveal):
                stack.extend(node.branches.values())
        self.assertTrue(leaves)
        for terminal in leaves[:12]:
            for player in (0, 1):
                vector = payoffs.terminal(
                    player, (1.0,) * len(model.ranges[1 - player]), terminal.board,
                    terminal.matched, terminal.winner)
                self.assertEqual(len(vector), len(model.ranges[player]))

    def test_live_tree_decisions_preserve_full_histories_without_aliasing(self):
        model = candidate.build_public_model(CASE)
        keys = [(node.player, node.history) for node in model.decisions]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(node.history == node.history[:len(node.history)]
                            for node in model.decisions))
        self.assertTrue(all(len(node.board) in (0, 3, 4, 5) for node in model.decisions))

    def test_range_work_rejection_precedes_range_expansion(self):
        with patch.object(candidate, "expand_range", side_effect=AssertionError("parser entered")):
            with self.assertRaisesRegex(ValueError, "work limit"):
                candidate.build_public_model(CASE, Budget({"work": 1}))

    def test_reveal_scan_work_is_reserved_before_prefix_generation(self):
        class TightRevealBudget(Budget):
            def charge(self, kind, n=1):
                if kind == "public_census_reveal_scan":
                    self.limits["work"] = self.work + n - 1
                return super().charge(kind, n)

        with patch.object(candidate, "_reveal_prefixes",
                          side_effect=AssertionError("prefix scan entered before admission")) as scan:
            with self.assertRaisesRegex(ValueError, "work limit"):
                candidate.build_public_model(CASE, TightRevealBudget())
        scan.assert_not_called()

    def test_untrusted_numeric_types_are_rejected_without_float_hooks(self):
        class HostileFloat(float):
            called = False

            def __float__(self):
                type(self).called = True
                raise AssertionError("untrusted __float__ hook ran")

        class HostileReal:
            called = False

            def __float__(self):
                type(self).called = True
                raise AssertionError("untrusted __float__ hook ran")

        for value in (True, HostileFloat(20.0), HostileReal()):
            case = copy.deepcopy(CASE)
            case["config"]["starting_stack"] = value
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaisesRegex(ValueError, "exact int, float or Fraction"):
                    candidate.build_public_model(case)
        self.assertFalse(HostileFloat.called)
        self.assertFalse(HostileReal.called)

    def test_oversized_fraction_input_is_rejected_before_float_conversion(self):
        case = copy.deepcopy(CASE)
        case["config"]["starting_stack"] = Fraction(1 << candidate.MAX_NUMERIC_INPUT_BITS, 1)
        with self.assertRaisesRegex(ValueError, "fraction exceeds"):
            candidate.build_public_model(case)

    def test_action_menu_budget_is_reserved_before_generation(self):
        class TightActionBudget(Budget):
            def charge(self, kind, n=1):
                if kind == "public_action_menu_rule_work_upper":
                    self.limits["work"] = self.work + n - 1
                return super().charge(kind, n)

        with patch.object(candidate, "_actions_for",
                          side_effect=AssertionError("action generator entered before admission")) as gen:
            with self.assertRaisesRegex(ValueError, "work limit"):
                candidate.build_public_model(CASE, TightActionBudget())
        gen.assert_not_called()

    def test_hand_board_and_public_shape_caps_reject(self):
        with self.assertRaisesRegex(ValueError, "16-holding research cap"):
            candidate.build_public_model({**CASE, "sb_range": "random"})
        with self.assertRaisesRegex(ValueError, "1 through 64 outcomes"):
            candidate.build_public_model({**CASE, "runouts": [CASE["runouts"][0]] * 65})
        with self.assertRaisesRegex(ValueError, "reduce-only"):
            candidate.build_public_model(CASE, limits={"public_nodes": 250_001})
        with patch.object(candidate, "Decision",
                          side_effect=AssertionError("public graph materialized")):
            with self.assertRaisesRegex(ValueError, "public graph exceeds 1 nodes"):
                candidate.build_public_model(CASE, limits={"public_nodes": 1})

    def test_maximum_declared_hands_and_board_count_without_world_expansion(self):
        from pokerlab.cards import DECK

        hands = ["".join(hand) for hand in list(combinations(DECK, 2))[:16]]
        boards = ["".join(board) for board in list(combinations(DECK, 5))[:64]]
        case = copy.deepcopy(CASE)
        case["sb_range"] = ",".join(hands)
        case["bb_range"] = ",".join(hands)
        case["runouts"] = boards
        case["config"]["starting_stack"] = [0.25, 0.25]
        with patch.object(old_numeric, "_physical_support",
                          side_effect=AssertionError("old physical support entered")), \
                patch.object(candidate.money_rules, "independent_rank",
                             side_effect=AssertionError("rank entered")):
            model = candidate.build_public_model(case)
        self.assertEqual(tuple(map(len, model.ranges)), (16, 16))
        self.assertEqual(len(model.outcomes), 64)
        self.assertFalse(model.counts["private_worlds_materialized"])
        self.assertFalse(model.counts["physical_support_filtered"])
        self.assertIsInstance(model.root, candidate.Terminal)


if __name__ == "__main__":
    unittest.main()
