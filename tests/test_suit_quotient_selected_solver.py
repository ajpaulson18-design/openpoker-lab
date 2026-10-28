"""Complete four-street solver controls for actual quotient training storage."""
import unittest
from unittest.mock import patch

from pokerlab.exact_selected_solver import solve_four_street_exact_selected
from scripts.exact_selected_compact_certificate import evaluate_exact
from tests.test_equivariant_selected_solver import symmetric_case, METRICS
from tests.test_selected_operator_solver import request


def solve(case, storage):
    return solve_four_street_exact_selected(request(case), pair_diagnostics="compact",
        exact_arithmetic="dyadic", training_reduction="suit-equivariant", strategy_storage=storage)


class SuitQuotientSelectedSolverTests(unittest.TestCase):
    def compare(self, case):
        literal = solve(case, "expanded")
        quotient = solve(case, "suit-quotient")
        for field in ("strategy", *METRICS):
            self.assertEqual(literal[field], quotient[field], field)
        left = evaluate_exact(case, literal)["exact_certificate"]
        right = evaluate_exact(case, quotient)["exact_certificate"]
        for field in ("metrics", "threshold", "threshold_met", "source_identity", "normalized_policy_sha256"):
            self.assertEqual(left[field], right[field], field)
        return literal, quotient

    def test_actual_exchanged_hands_match_complete_reference_and_physical_certificate(self):
        _, result = self.compare(symmetric_case())
        receipt = result["operator_census"]["suit_quotient_storage"]
        self.assertEqual(receipt["group_size"], 2)
        self.assertEqual(2 * receipt["quotient_information_rows"], result["info_sets"])
        self.assertEqual(receipt["retained_expanded_row_lookup_entries"], 0)
        admission = result["operator_census"]["whole_request_admission"]
        self.assertLessEqual(admission["combined_modeled_work_upper"], admission["whole_request_limit"])
        self.assertLessEqual(admission["retained_storage"]["whole_request_peak_upper"],
                             admission["retained_storage"]["entry_limit"])

    def test_identity_group_keeps_every_row_and_same_certificate(self):
        case = symmetric_case()
        case.update(sb_range="AcAh:0.7,AdAh:0.3", bb_range="KcKh:0.4,KdKh:0.6")
        _, result = self.compare(case)
        receipt = result["operator_census"]["suit_quotient_storage"]
        self.assertEqual(receipt["group_size"], 1)
        self.assertEqual(receipt["quotient_information_rows"], result["info_sets"])

    def test_unequal_orbit_sizes_preserve_reference_and_certificate(self):
        case = symmetric_case()
        case.update(sb_range="AcAd", bb_range="KcKd")
        self.compare(case)

    def test_blocked_four_hand_ranges_preserve_hidden_support_and_certificate(self):
        case = symmetric_case()
        case.update(sb_range="AcAh,AdAh,2cAh,2dAh", bb_range="KcKh,KdKh,3cKh,3dKh")
        _, result = self.compare(case)
        self.assertEqual(result["worlds"], 18)
        layout = result["operator_census"]["packed_layout_actual"]
        shadow = layout["expanded_layout_equivalent"]
        self.assertGreater(shadow["dense_decision_hand_slots"], shadow["information_sets"])
        self.assertLess(layout["numeric_buffer_bytes"], shadow["numeric_buffer_bytes"])

    def test_forced_all_in_with_no_rows_enters_no_trainer(self):
        case = symmetric_case()
        case["config"]["starting_stack"] = [.5, 1]
        with patch("pokerlab.suit_quotient_cfr.train_suit_quotient", side_effect=AssertionError("training")):
            result = solve(case, "suit-quotient")
        self.assertEqual(result["info_sets"], 0)
        self.assertEqual(result["strategy"], [])
        self.assertEqual(result["operator_census"]["training"]["calls"], 0)

    def test_quotient_never_calls_expanded_layout(self):
        with patch("pokerlab.shared_topology_view.layout_census_shared", side_effect=AssertionError("expanded layout")), \
             patch("pokerlab.exact_selected_solver.layout_census_shared", side_effect=AssertionError("expanded layout")), \
             patch("pokerlab.equivariant_packed_cfr.layout_census_shared", side_effect=AssertionError("expanded layout")):
            result = solve(symmetric_case(), "suit-quotient")
        self.assertGreater(result["info_sets"], 0)

    def test_unsupported_storage_or_missing_explicit_arithmetic_rejects_before_kernel(self):
        with patch("pokerlab.exact_selected_solver.ExactSelectedRunoutKernel", side_effect=AssertionError("kernel")):
            for storage in (True, None, "auto", "suit-quotient"):
                with self.subTest(storage=storage), self.assertRaises(ValueError):
                    solve_four_street_exact_selected(request(symmetric_case()), strategy_storage=storage)


if __name__ == "__main__":
    unittest.main()
