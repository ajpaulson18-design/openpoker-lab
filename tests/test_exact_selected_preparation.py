"""Tests for the shared admitted preparation boundary."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pokerlab.exact_selected_kernel import ExactSelectedKernelLimits
from pokerlab.exact_selected_solver import (
    _prepare_exact_selected, solve_four_street_exact_selected,
)
from tests.test_exact_selected_solver import request_from_case


ROOT = Path(__file__).resolve().parents[1]


def _request():
    case = json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text(encoding="utf-8"))["case"]
    return request_from_case(case)


class ExactSelectedPreparationTests(unittest.TestCase):
    def test_context_contains_admitted_inputs_without_information_rows(self):
        request = _request()
        with patch("pokerlab.exact_selected_solver.layout_census_shared",
                   side_effect=AssertionError("information rows reached packed layout")), \
             patch("pokerlab.exact_selected_solver.train_packed",
                   side_effect=AssertionError("training entered preparation")), \
             patch("pokerlab.exact_selected_kernel.rank_hand",
                   side_effect=AssertionError("ranking entered preparation")), \
             patch("pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.pair_probability_exact",
                   side_effect=AssertionError("pair query entered preparation")):
            prepared = _prepare_exact_selected(request, pair_diagnostics="compact")
        expected = {"kernel", "topology", "direct_receipt", "view", "adapter", "prefix_counts",
            "unique_prefixes", "decisions", "action_hand_queries", "terminal_counts", "layout_upper",
            "admission", "bit_forecast", "action_slots_upper"}
        self.assertTrue(expected.issubset(set(prepared.__dataclass_fields__)))
        self.assertFalse(hasattr(prepared, "infos"))
        self.assertFalse(hasattr(prepared, "menus"))
        self.assertEqual(prepared.kernel.statistics()["rank_calls"], 0)
        self.assertEqual(prepared.admission["kernel"]["whole_request_upper_work"] <=
                         prepared.admission["kernel"]["configured_limit"], True)

    def test_early_bit_bound_rejects_before_rows_rank_pair_or_training(self):
        request = _request()
        limits = ExactSelectedKernelLimits(max_integer_bits=1024)
        with patch("pokerlab.exact_selected_solver.layout_census_shared",
                   side_effect=AssertionError("packed rows allocated")), \
             patch("pokerlab.exact_selected_solver.train_packed",
                   side_effect=AssertionError("training entered")), \
             patch("pokerlab.exact_selected_kernel.rank_hand",
                   side_effect=AssertionError("ranking entered")), \
             patch("pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.pair_probability_exact",
                   side_effect=AssertionError("pair query entered")):
            with self.assertRaisesRegex(ValueError, "Fraction forecast"):
                _prepare_exact_selected(request, kernel_limits=limits, pair_diagnostics="compact")

    def test_solver_uses_shared_preparation_once_and_preserves_live_mode_equivalence(self):
        with patch("pokerlab.exact_selected_solver._prepare_exact_selected",wraps=_prepare_exact_selected) as prepare:
            default=solve_four_street_exact_selected(_request())
        self.assertEqual(prepare.call_count,1)
        explicit=solve_four_street_exact_selected(_request(),pair_diagnostics="expanded",exact_arithmetic="fraction")
        self.assertEqual(default,explicit)
        integer=solve_four_street_exact_selected(_request(),pair_diagnostics="compact",exact_arithmetic="dyadic")
        for field in ("strategy","value_sb","value_bb","sb_best_response_value","bb_best_response_value",
                      "sb_gain","bb_gain","nash_conv","exploitability","worlds","info_sets"):
            self.assertEqual(default[field],integer[field],field)


if __name__ == "__main__":
    unittest.main()
