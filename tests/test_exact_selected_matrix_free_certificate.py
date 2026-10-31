"""Independent complete-policy and hidden-information integration anchors."""
from contextlib import ExitStack
from copy import deepcopy
from fractions import Fraction
import unittest
from unittest.mock import patch

from scripts import exact_selected_matrix_free_certificate as candidate
from scripts import four_street_certificate_v3 as literal
from scripts import four_street_validation as physical
from scripts.matrix_free_certificate_budget import Budget
from scripts.matrix_free_four_street_rules import Action, Decision, Reveal, Terminal
from tests.test_four_street_certificate import _case, _payload, _check_call
from tests.test_four_street_validation import CASE, _fractional_boundary_case


def _compact(case, chooser=_check_call):
    model = physical.build_model(case)
    payload = _payload(model, chooser)
    del payload["compatible_private_pairs"]
    del payload["private_pair_probabilities"]
    ranges = physical._case_inputs(case)[-1]
    payload.update(chance_contract="exact-product-selected-v1",
        conversion_contract="exact-product-vectors-binary64-v1",
        pair_diagnostics="compact-exact-product-inputs-v1",
        chance_input_snapshot={"contract": "exact-product-selected-v1", "ranges": [
            [{"hand": "".join(hand), "weight_hex": float(weight).hex()} for hand, weight in side.items()]
            for side in ranges]})
    return model, payload


def _literal_payload(case, compact):
    model = physical.build_model(case)
    expanded = deepcopy(compact)
    expanded["compatible_private_pairs"] = model.counts["compatible_pairs"]
    expanded["private_pair_probabilities"] = [
        {"sb_hand": row["sb_hand"], "bb_hand": row["bb_hand"],
         "probability": float(Fraction(row["fraction"]))}
        for row in model.counts["pair_probabilities"]]
    return expanded


class MatrixFreeCertificateTests(unittest.TestCase):
    def test_complete_profile_and_both_responses_match_unchanged_literal_oracle(self):
        case = _case()
        _, payload = _compact(case)
        expected = literal.evaluate_exact(case, _literal_payload(case, payload))
        before = deepcopy(payload)
        forbidden = ("scripts.four_street_validation.build_model",
            "scripts.four_street_validation._physical_support",
            "scripts.four_street_validation._build_graph",
            "pokerlab.exact_selected_solver.solve_four_street_exact_selected",
            "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.__init__",
            "pokerlab.cards.rank_hand")
        with ExitStack() as guards:
            for name in forbidden:
                guards.enter_context(patch(name, side_effect=AssertionError("forbidden path " + name)))
            result = candidate.evaluate_exact(case, payload)
        self.assertEqual(result["metrics"], expected["metrics"])
        self.assertEqual(result["normalized_policy_rows"], expected["normalized_policy_rows"])
        self.assertEqual(result["normalized_policy_sha256"], expected["normalized_policy_sha256"])
        self.assertEqual(result["threshold_met"], expected["threshold_met"])
        self.assertEqual(payload, before)
        self.assertEqual(result["operator"]["stored_worlds"], 0)
        self.assertEqual(result["operator"]["stored_pairs"], 0)

    def test_normalized_binary64_row_fractions_preserve_old_policy_identity(self):
        case = _case(stacks=3)
        _, payload = _compact(case)
        for row in payload["strategy"]:
            values = [0.25, 0.75 + 1e-16] if len(row["actions"]) == 2 else [1 / len(row["actions"])] * len(row["actions"])
            for action, value in zip(row["actions"], values):
                action["probability"] = value
        expected = literal.evaluate_exact(case, _literal_payload(case, payload))
        result = candidate.evaluate_exact(case, payload)
        self.assertEqual(result["metrics"], expected["metrics"])
        self.assertEqual(result["normalized_policy_sha256"], expected["normalized_policy_sha256"])

    def test_weighted_blocked_fractional_and_all_in_games_match_literal(self):
        cases = [deepcopy(CASE), _fractional_boundary_case(),
                 _case("AdKs", "AhQc", runouts=("2c3c4d7h8h",)),
                 _case(runouts=("2c3c4d7h8h", "As2c3d7h8h")),
                 _case(stacks=(0.5, 1))]
        for case in cases:
            with self.subTest(case=case["id"], sb=case["sb_range"], stacks=case["config"]["starting_stack"]):
                _, payload = _compact(case)
                expected = literal.evaluate_exact(case, _literal_payload(case, payload))
                result = candidate.evaluate_exact(case, payload)
                self.assertEqual(result["metrics"], expected["metrics"])
                self.assertEqual(result["normalized_policy_sha256"], expected["normalized_policy_sha256"])
                self.assertEqual(result["threshold_met"], expected["threshold_met"])
                self.assertLessEqual(result["budget"]["work"], result["forecast"]["whole_work_upper"])
                self.assertLessEqual(result["budget"]["entries"], result["forecast"]["whole_entries_upper"])

    def test_physical_row_completeness_includes_unplayed_actions(self):
        case = _case()
        _, payload = _compact(case)
        # Deterministic check/call leaves many physically supported branches unplayed.
        self.assertTrue(any(any(action["probability"] == 0 for action in row["actions"])
                            for row in payload["strategy"]))
        bad = deepcopy(payload)
        bad["strategy"].pop()
        bad["info_sets"] -= 1
        with self.assertRaisesRegex(ValueError, "row count"):
            candidate.evaluate_exact(case, bad)
        for mutate in (lambda p: p["strategy"].append(deepcopy(p["strategy"][0])),
                       lambda p: p["strategy"][0]["actions"][0].update(raise_to=999),
                       lambda p: p["strategy"][0].update(revealed_board=["As"]),
                       lambda p: p["chance_input_snapshot"]["ranges"][0][0].update(weight_hex="0x1p+0")):
            bad = deepcopy(payload); mutate(bad)
            with self.assertRaises(ValueError): candidate.evaluate_exact(case, bad)

    def test_hidden_river_outcomes_are_summed_before_own_hand_maximum(self):
        actions = (Action("A", 0, 0, "A"), Action("B", 0, 0, "B"))
        boards = (("2c", "3d", "4h", "7s", "8c"), ("2c", "3d", "4h", "7s", "9c"))
        def branch(name, reverse):
            return Reveal((name,), 5, {board: Terminal("fold", (0.5, 0.5),
                (i + reverse) % 2, board, (name, "river@" + board[-1]), 0.5)
                for i, board in enumerate(boards)})
        root = Decision(0, (), (), actions, (branch("A", 0), branch("B", 1)))
        class HiddenKernel:
            hands = ((("Ad", "As"),), (("Kd", "Ks"),))
            def terminal(self, player, reach, prefix, matched, winner):
                return (Fraction(1, 2) if winner == player else Fraction(-1, 2),)
        policies = {(0, "AdAs", ()): (Fraction(1), Fraction(0))}
        value = candidate._walk(root, 0, policies, HiddenKernel(), Budget(), best_response=True)
        self.assertEqual(value, (Fraction(0),))
        self.assertNotEqual(value, (Fraction(1),))  # Impossible clairvoyant result.

    def test_zero_own_policy_probability_does_not_remove_legal_deviation(self):
        actions = (Action("A", 0, 0, "A"), Action("B", 0, 0, "B"))
        children = tuple(Terminal("fold", (1, 1), winner, (), (name,), 1)
                         for name, winner in (("A", 1), ("B", 0)))
        root = Decision(0, (), (), actions, children)
        class Kernel:
            hands = ((("Ad", "As"),), (("Kd", "Ks"),))
            def terminal(self, player, reach, prefix, matched, winner):
                return (Fraction(1) if winner == player else Fraction(-1),)
        policies = {(0, "AdAs", ()): (Fraction(1), Fraction(0))}
        self.assertEqual(candidate._walk(root, 0, policies, Kernel(), Budget(), best_response=False), (Fraction(-1),))
        self.assertEqual(candidate._walk(root, 0, policies, Kernel(), Budget(), best_response=True), (Fraction(1),))

    def test_reduce_only_work_rejects_before_ranking_and_inert_payload_required(self):
        case = _case()
        _, payload = _compact(case)
        with patch("scripts.matrix_free_selected_payoffs.independent_rank", side_effect=AssertionError("rank entered")):
            with self.assertRaisesRegex(ValueError, "work limit"):
                candidate.evaluate_exact(case, payload, limits={"work": 1})
        bad = deepcopy(payload); bad["custom"] = object()
        with self.assertRaisesRegex(ValueError, "inert"):
            candidate.evaluate_exact(case, bad)

    def test_negative_exact_response_gain_is_rejected_instead_of_repaired(self):
        case = _case()
        _, payload = _compact(case)
        with patch.object(candidate, "_walk", side_effect=[(Fraction(1),), (Fraction(0),), (Fraction(0),)]):
            with self.assertRaisesRegex(ValueError, "negative exact"):
                candidate.evaluate_exact(case, payload)

    def test_zero_work_counter_names_and_limits_cannot_allocate_without_bound(self):
        budget = Budget()
        for i in range(256):
            budget.charge("counter_" + str(i), 0)
        with self.assertRaisesRegex(ValueError, "counter-family"):
            budget.charge("one_more", 0)
        class Hostile(dict):
            def keys(self): raise AssertionError("custom mapping entered")
        with self.assertRaisesRegex(ValueError, "plain mapping"):
            Budget(Hostile())

    def test_whole_walk_forecast_rejects_cap_minus_one_before_ranks_or_walk(self):
        case = _case()
        _, payload = _compact(case)
        admitted = candidate.evaluate_exact(case, payload)
        for field, limit in (("work", admitted["forecast"]["whole_work_upper"] - 1),
                             ("entries", admitted["forecast"]["whole_entries_upper"] - 1)):
            with self.subTest(field=field), \
                 patch.object(candidate, "_walk", side_effect=AssertionError("walk entered")), \
                 patch("scripts.matrix_free_selected_payoffs.independent_rank", side_effect=AssertionError("rank entered")):
                with self.assertRaisesRegex(ValueError, "whole-request walk forecast"):
                    candidate.evaluate_exact(case, payload, limits={field: limit})


if __name__ == "__main__":
    unittest.main()
