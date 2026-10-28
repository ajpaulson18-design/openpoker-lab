"""Compact production diagnostics retain the exact four-street policy game."""
from copy import deepcopy
from fractions import Fraction
import unittest
from unittest.mock import patch
from pokerlab.exact_selected_solver import solve_four_street_exact_selected
from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
from scripts.exact_selected_compact_certificate import evaluate_exact
from scripts.four_street_certificate_v3 import evaluate_exact as expanded_exact
from tests.test_four_street_certificate import _case
from tests.test_selected_operator_solver import request

class CompactExactPolicyTests(unittest.TestCase):
    def test_compact_has_identical_policy_and_metrics_without_any_pair_queries(self):
        case = _case(sb="AsAd:.7,QsQd:.3",bb="KsKd:.4,JhJd:.6")
        expanded = solve_four_street_exact_selected(request(case))
        with patch.object(ExactSelectedRunoutKernel,"pair_probability_exact",side_effect=AssertionError("production pair query")):
            compact = solve_four_street_exact_selected(request(case),pair_diagnostics="compact")
        self.assertNotIn("private_pair_probabilities",compact)
        self.assertNotIn("compatible_private_pairs",compact)
        for field in ("strategy","worlds","info_sets","value_sb","value_bb","sb_best_response_value","bb_best_response_value","nash_conv"):
            self.assertEqual(compact[field],expanded[field],field)
        self.assertEqual(compact["operator_census"]["exact_pair_output"]["candidate_pairs_scanned"],0)
        self.assertEqual(compact["pair_runout_preflight_checks"],0)
        original = expanded_exact(case,expanded)
        audit = evaluate_exact(case,compact)
        self.assertEqual(audit["exact_certificate"]["metrics"],original["metrics"])
        self.assertEqual(audit["production_pair_rows"],0)
        self.assertEqual(audit["verification_only_reconstructed_pairs"],4)

    def test_full_ranges_blind_all_in_omit_pair_table_and_training(self):
        from math import comb
        case = _case(sb="random",bb="random",stacks=[.5,1])
        with patch.object(ExactSelectedRunoutKernel,"pair_probability_exact",side_effect=AssertionError("pair query")), \
             patch("pokerlab.exact_selected_solver.train_packed",side_effect=AssertionError("no decision training")):
            result = solve_four_street_exact_selected(request(case),pair_diagnostics="compact")
        self.assertEqual(result["strategy"],[])
        self.assertEqual(result["worlds"],comb(47,2)*comb(45,2))
        self.assertEqual(result["operator_census"]["training"]["calls"],0)
        self.assertEqual([len(side) for side in result["chance_input_snapshot"]["ranges"]],[1326,1326])
        self.assertEqual(result["operator_census"]["kernel"]["rank_calls"],2*comb(47,2))
        self.assertAlmostEqual(result["value_sb"],0,delta=1e-12)
        self.assertAlmostEqual(result["nash_conv"],0,delta=1e-12)
        with patch("scripts.four_street_validation.build_model",side_effect=AssertionError("oversized physical verification")):
            with self.assertRaises(ValueError):
                evaluate_exact(case,result)

    def test_forged_inputs_or_pair_table_reject(self):
        case = _case()
        result = solve_four_street_exact_selected(request(case),pair_diagnostics="compact")
        changes = []
        altered = deepcopy(result); altered["chance_input_snapshot"]["ranges"][0][0]["weight_hex"] = (.5).hex(); changes.append(altered)
        altered = deepcopy(result); altered["chance_input_snapshot"]["ranges"][0] *= 2; changes.append(altered)
        altered = deepcopy(result); altered["private_pair_probabilities"] = []; changes.append(altered)
        altered = deepcopy(result); altered["selected_runouts"] = []; changes.append(altered)
        for payload in changes:
            with self.subTest(payload=payload.get("selected_runouts")),self.assertRaises(ValueError):
                evaluate_exact(case,payload)

    def test_unsupported_mode_rejects_before_kernel(self):
        with patch("pokerlab.exact_selected_solver.ExactSelectedRunoutKernel",side_effect=AssertionError("kernel")):
            with self.assertRaisesRegex(ValueError,"pair_diagnostics"):
                solve_four_street_exact_selected(request(_case()),pair_diagnostics="hidden")
