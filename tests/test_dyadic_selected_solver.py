"""Whole-game parity and admission/lifetime controls for integer arithmetic."""
from fractions import Fraction
import gc
import json
from pathlib import Path
import unittest
import weakref
from unittest.mock import patch

from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
from pokerlab.exact_selected_solver import solve_four_street_exact_selected
from scripts.exact_selected_compact_certificate import evaluate_exact
from tests.test_four_street_certificate import _case
from tests.test_selected_operator_solver import request

METRICS = ("value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value",
           "sb_gain", "bb_gain", "nash_conv", "exploitability")


class DyadicSelectedSolverTests(unittest.TestCase):
    def test_complete_four_street_policy_metrics_and_exact_certificate_match(self):
        case = _case(sb="AsAd:.7,QsQd:.3", bb="KsKd:.4,JhJd:.6", stacks=[2.5, 3.25])
        ordinary = solve_four_street_exact_selected(request(case), pair_diagnostics="compact")
        # Integer mode must not quietly route terminal/marginal arithmetic back
        # through the reference Fraction add/multiply loops. Setup remains a
        # separately bounded exact reference normalizer calculation.
        from pokerlab.dyadic_selected_arithmetic import DyadicSelectedArithmeticPlan
        old_terminal = DyadicSelectedArithmeticPlan.terminal
        old_marginals = DyadicSelectedArithmeticPlan.marginals
        calls = []
        def terminal(plan, *args, **kwargs):
            calls.append("terminal")
            with patch.object(ExactSelectedRunoutKernel, "_add", side_effect=AssertionError("Fraction add fallback")), \
                 patch.object(ExactSelectedRunoutKernel, "_mul", side_effect=AssertionError("Fraction multiply fallback")):
                return old_terminal(plan, *args, **kwargs)
        def marginals(plan, *args, **kwargs):
            calls.append("marginal")
            with patch.object(ExactSelectedRunoutKernel, "_add", side_effect=AssertionError("Fraction add fallback")), \
                 patch.object(ExactSelectedRunoutKernel, "_mul", side_effect=AssertionError("Fraction multiply fallback")):
                return old_marginals(plan, *args, **kwargs)
        with patch.object(DyadicSelectedArithmeticPlan, "terminal", new=terminal), \
             patch.object(DyadicSelectedArithmeticPlan, "marginals", new=marginals), \
             patch.object(ExactSelectedRunoutKernel, "pair_probability_exact", side_effect=AssertionError("pair query")):
            integer = solve_four_street_exact_selected(request(case), pair_diagnostics="compact", exact_arithmetic="dyadic")
        self.assertIn("terminal", calls)
        self.assertIn("marginal", calls)
        for field in ("strategy", "worlds", "info_sets", "chance_input_snapshot", *METRICS):
            self.assertEqual(integer[field], ordinary[field], field)
        self.assertEqual(integer["operator_census"]["kernel"]["arithmetic"], "exact-dyadic-integer-buckets-v1")
        self.assertEqual(evaluate_exact(case, integer)["exact_certificate"]["metrics"],
                         evaluate_exact(case, ordinary)["exact_certificate"]["metrics"])

    def test_original_t1000_still_rejects_before_rank_and_training(self):
        fixture = Path(__file__).resolve().parents[1]/"benchmarks/four-street-integration-v1.json"
        case = json.loads(fixture.read_text())["case"]
        from tests.test_exact_selected_solver import request_from_case
        with patch("pokerlab.exact_selected_solver.train_packed", side_effect=AssertionError("training")), \
             patch("pokerlab.exact_selected_kernel.rank_hand", side_effect=AssertionError("ranking")):
            with self.assertRaisesRegex(ValueError, "whole-request.*work"):
                solve_four_street_exact_selected(request_from_case(case, iterations=1000),
                                                pair_diagnostics="compact", exact_arithmetic="dyadic")

    def test_unsupported_arithmetic_rejects_before_input_preparation(self):
        with patch("pokerlab.exact_selected_solver.ExactSelectedRunoutKernel", side_effect=AssertionError("kernel")):
            for mode in ("native", None, True, 1):
                with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "exact_arithmetic"):
                    solve_four_street_exact_selected(request(_case()), exact_arithmetic=mode)

    def test_integer_kernel_has_no_strong_plan_cycle_with_gc_disabled(self):
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            kernel = ExactSelectedRunoutKernel("AsAd", "KsKd", ["2c3d4h5s6c"], arithmetic="dyadic")
            plan = kernel._arithmetic_plan
            kernel_ref = weakref.ref(kernel)
            del kernel
            self.assertIsNone(kernel_ref())
            with self.assertRaises((ValueError, RuntimeError, ReferenceError)):
                plan.marginals((0,))
        finally:
            if was_enabled:
                gc.enable()

    def test_non_dyadic_query_rejects_before_rank_without_reference_fallback(self):
        kernel = ExactSelectedRunoutKernel("AsAd", "KsKd", ["2c3d4h5s6c"], arithmetic="dyadic")
        with patch("pokerlab.exact_selected_kernel.rank_hand", side_effect=AssertionError("ranking")):
            for field in ("reach", "payoff"):
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "dyadic"):
                    kernel.terminal_values_exact((), kind="showdown", player=0,
                        payoff=Fraction(1, 3) if field == "payoff" else 1,
                        opponent_reach=[Fraction(1, 3) if field == "reach" else 1])
        reference = ExactSelectedRunoutKernel("AsAd", "KsKd", ["2c3d4h5s6c"])
        self.assertEqual(reference.terminal_values_exact((), kind="showdown", player=0,
                         payoff=Fraction(1, 3), opponent_reach=[Fraction(1, 3)]), (Fraction(0),))


if __name__ == "__main__":
    unittest.main()
