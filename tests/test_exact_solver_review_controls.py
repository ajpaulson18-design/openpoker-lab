"""Independent review controls for exact-product four-street integration."""
import gc
import weakref
from contextlib import ExitStack
from fractions import Fraction
import unittest
from unittest.mock import patch

from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
from pokerlab.exact_selected_solver import solve_four_street_exact_selected
from tests.test_exact_selected_solver import request_from_case
from tests.test_selected_operator_solver import CASE
from scripts.four_street_certificate_v3 import evaluate_exact


class ExactSolverIndependentReviewTests(unittest.TestCase):
    def test_prompt_kernel_release_on_success_training_error_and_diagnostic_error(self):
        original = ExactSelectedRunoutKernel
        references = []
        def construct(*args, **kwargs):
            kernel = original(*args, **kwargs)
            references.append(weakref.ref(kernel))
            return kernel
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            with patch("pokerlab.exact_selected_solver.ExactSelectedRunoutKernel", side_effect=construct):
                case = dict(CASE, sb_range="AsAd", bb_range="KsKd", runouts=["2c3c4d7h8h"])
                result = solve_four_street_exact_selected(request_from_case(case))
                self.assertGreater(result["info_sets"], 0)
                self.assertIsNone(references[-1]())
                def fail(*args, **kwargs):
                    raise RuntimeError("independent review injected failure")
                for target in ("train_packed", "_evaluate_prepared"):
                    # A recording Mock would itself keep adapter argument refs;
                    # replace with a plain function to measure solver ownership.
                    with self.subTest(target=target), patch("pokerlab.exact_selected_solver." + target, new=fail):
                        with self.assertRaisesRegex(RuntimeError, "injected failure"):
                            solve_four_street_exact_selected(request_from_case(case))
                    self.assertIsNone(references[-1]())
        finally:
            if was_enabled:
                gc.enable()

    def test_whole_request_work_and_entries_reject_before_pair_infos_or_training(self):
        req = request_from_case(CASE)
        for limit in ("MAX_WHOLE_REQUEST_WORK", "MAX_WHOLE_REQUEST_ENTRIES"):
            with self.subTest(limit=limit), ExitStack() as stack:
                stack.enter_context(patch("pokerlab.exact_selected_solver." + limit, 1))
                stack.enter_context(patch.object(ExactSelectedRunoutKernel, "pair_probability_exact",
                    side_effect=AssertionError("pair output entered before rejected admission")))
                stack.enter_context(patch("pokerlab.exact_selected_solver.layout_census_shared",
                    side_effect=AssertionError("infos constructed before rejected admission")))
                stack.enter_context(patch("pokerlab.exact_selected_solver.train_packed",
                    side_effect=AssertionError("training entered before rejected admission")))
                with self.assertRaisesRegex(ValueError, "whole-request"):
                    solve_four_street_exact_selected(req)

    def test_fractional_money_hidden_ties_and_blocked_index_holes_have_exact_replay(self):
        case = dict(CASE, id="independent-exact-fractional-money", sb_range="AsAd:1,AhAc:.25,2c3c:.5", bb_range="AsKd:1,KcKh:.5",
            config={"small_blind": .123456789, "big_blind": .345678901,
                    "starting_stack": [2.5, 2], "raise_sizes": [.5],
                    "max_raises": 1, "include_all_in": True},
            runouts=["TcJcQcKcAc", "2c3c4d7h8h"],
            turn_config=CASE["flop_config"], river_config=CASE["flop_config"])
        result = solve_four_street_exact_selected(request_from_case(case))
        cert = evaluate_exact(case, result)
        self.assertTrue(all(row["absolute_difference"] <= 1e-9
                            for row in cert["floating_comparison"].values()))
        self.assertLessEqual(abs(result["value_sb"]-float(Fraction(cert["metrics"]["value_sb"]))),1e-9)
        self.assertLessEqual(abs(result["sb_best_response_value"]-float(Fraction(cert["metrics"]["sb_best_response_value"]))),1e-9)
        self.assertLessEqual(abs(result["bb_best_response_value"]-float(Fraction(cert["metrics"]["bb_best_response_value"]))),1e-9)
        keys = [(row["player"], row["hand"],tuple(row["history"])) for row in result["strategy"]]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertTrue(all(tuple(row["revealed_board"]) == tuple(card for token in row["history"]
            if token.startswith(("flop@", "turn@", "river@")) for card in ([token.split("@",1)[1][i:i+2] for i in range(0,len(token.split("@",1)[1]),2)]))
            for row in result["strategy"]))

    def test_bit_forecast_rejects_before_pair_or_information_support(self):
        from pokerlab.exact_selected_kernel import ExactSelectedKernelLimits
        with patch.object(ExactSelectedRunoutKernel, "pair_probability_exact", side_effect=AssertionError("pair entered")), \
             patch.object(ExactSelectedRunoutKernel, "legal_hands", side_effect=AssertionError("info support entered")), \
             patch("pokerlab.exact_selected_solver.train_packed", side_effect=AssertionError("training entered")):
            with self.assertRaisesRegex(ValueError, "Fraction forecast"):
                solve_four_street_exact_selected(request_from_case(CASE),
                    kernel_limits=ExactSelectedKernelLimits(max_integer_bits=1024))

    def test_no_information_admission_still_counts_selected_prefix_storage(self):
        case = dict(CASE, sb_range="AsAd", bb_range="KsKd", config={"starting_stack": [.5,1]},
                    runouts=["2c3c4d7h8h"])
        one = solve_four_street_exact_selected(request_from_case(case))
        many = solve_four_street_exact_selected(request_from_case(dict(case,
                    runouts=["2c3c4d7h8h", "2c3c4d7h9s", "2d3d4h7s8c"])))
        self.assertEqual(one["info_sets"],0)
        self.assertEqual(many["info_sets"],0)
        self.assertEqual(many["operator_census"]["training"]["calls"],0)
        one_storage=one["operator_census"]["whole_request_admission"]["retained_storage"]
        many_storage=many["operator_census"]["whole_request_admission"]["retained_storage"]
        self.assertGreater(many_storage["prefix_counters_upper"],one_storage["prefix_counters_upper"])
        self.assertGreater(many_storage["callback_scratch_entries_upper"],0)
        self.assertEqual(many_storage["legal_support_entries_upper"],0)

    def test_hostile_reach_iterator_is_bounded_before_ranking(self):
        kernel = ExactSelectedRunoutKernel("AsAd", "KsKd", ["2c3c4d7h8h"])
        class Reach:
            yielded = 0
            def __len__(self):
                return 1
            def __iter__(self):
                while True:
                    self.yielded += 1
                    if self.yielded > 2:
                        raise AssertionError("unbounded reach consumption")
                    yield 1.0
        reach = Reach()
        with patch("pokerlab.exact_selected_kernel.rank_hand", side_effect=AssertionError("rank before length rejection")):
            with self.assertRaisesRegex(ValueError, "bounded iterator"):
                kernel.terminal_values_exact((), kind="showdown", payoff=1, player=0, opponent_reach=reach)
        self.assertEqual(reach.yielded,2)


if __name__ == "__main__":
    unittest.main()
