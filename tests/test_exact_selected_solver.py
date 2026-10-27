"""Focused controls for the explicit exact-product four-street solver."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pokerlab.exact_selected_kernel import ExactSelectedKernelLimits
from pokerlab.exact_selected_solver import solve_four_street_exact_selected
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions
from pokerlab.selected_runout_operator import SelectedRunoutOperator
from scripts import four_street_certificate_v3


ROOT = Path(__file__).resolve().parents[1]


def request_from_case(case, *, sb_range=None, bb_range=None, iterations=10):
    return FourStreetSolveRequest(
        sb_range or case["sb_range"], bb_range or case["bb_range"],
        tuple(case["runouts"]),
        preflop_config=PreflopConfig.from_dict(case["config"]),
        flop_actions=PostflopActions(**case["flop_config"]),
        turn_actions=(None if case.get("turn_config") is None
                      else PostflopActions(**case["turn_config"])),
        river_actions=(None if case.get("river_config") is None
                       else PostflopActions(**case["river_config"])),
        iterations=iterations, algorithm="cfrplus", traversal="public-batched",
        diagnostics="public-batched", resource_model="public-vector")


class ExactSelectedSolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text())
        cls.case = cls.manifest["case"]

    def test_twenty_two_world_game_and_independent_v3_certificate(self):
        request = request_from_case(self.case)
        payload = solve_four_street_exact_selected(request)
        certificate = four_street_certificate_v3.evaluate_exact(self.case, payload)
        self.assertEqual(payload["worlds"], 22)
        self.assertEqual(payload["compatible_private_pairs"], 4)
        self.assertEqual(payload["chance_contract"], "exact-product-selected-v1")
        self.assertEqual(payload["conversion_contract"], "exact-product-vectors-binary64-v1")
        self.assertEqual(payload["solver_version"], "preflop-strategy-v1")
        self.assertEqual({row["street"] for row in payload["strategy"]},
                         {"preflop", "flop", "turn", "river"})
        self.assertEqual(payload["operator_census"]["stored_complete_worlds"], 0)
        self.assertEqual(payload["operator_census"]["stored_prefix_pair_edges"], 0)
        self.assertTrue(certificate["source_identity"].startswith("four-street-independent-exact-v3"))
        # A finite-iteration miss is retained as certificate output, not hidden.
        self.assertIn("threshold_met", certificate)
        self.assertLessEqual(
            payload["operator_census"]["whole_request_admission"]["combined_modeled_work_upper"],
            payload["operator_census"]["whole_request_admission"]["whole_request_limit"])

    def test_common_tiny_scale_is_exactly_cancelled_by_global_normalizer(self):
        case = {
            "sb_range": "AsAd:1,QsQd:1", "bb_range": "KsKd:1,JhJd:1",
            "config": {"starting_stack": [4, 3], "raise_sizes": [0.5],
                       "max_raises": 1, "include_all_in": False},
            "runouts": ["2c3c4d7h8h", "2c3c4d7hKc", "Ac2d3h7s8c"],
            "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                            "max_raises": 0, "include_all_in": False},
        }
        with self.assertRaises(ValueError):
            SelectedRunoutOperator("AsAd:1e-200,QsQd:1e-200",
                                   "KsKd:1e-200,JhJd:1e-200", case["runouts"])
        unit = solve_four_street_exact_selected(request_from_case(case))
        scaled_sb, scaled_bb = "AsAd:1e-200,QsQd:1e-200", "KsKd:1e-200,JhJd:1e-200"
        tiny = solve_four_street_exact_selected(request_from_case(
            case, sb_range=scaled_sb, bb_range=scaled_bb))
        tiny_case = dict(case, id="exact-common-tiny-scale-control", sb_range=scaled_sb, bb_range=scaled_bb,
                         turn_config=None, river_config=None)
        certificate = four_street_certificate_v3.evaluate_exact(tiny_case, tiny)
        self.assertEqual(certificate["source_identity"], "four-street-independent-exact-v3")
        self.assertEqual(tiny["private_pair_probabilities"], unit["private_pair_probabilities"])
        self.assertEqual(tiny["strategy"], unit["strategy"])
        for key in ("value_sb", "sb_best_response_value", "bb_best_response_value", "nash_conv"):
            self.assertEqual(tiny[key], unit[key])

    def test_custom_low_bit_limit_rejects_before_training(self):
        request = request_from_case(self.case)
        limits = ExactSelectedKernelLimits(max_integer_bits=1024)
        with patch("pokerlab.exact_selected_solver.train_packed",
                   side_effect=AssertionError("training entered")):
            with self.assertRaisesRegex(ValueError, "Fraction forecast"):
                solve_four_street_exact_selected(request, kernel_limits=limits)

    def test_rejects_legacy_selectors_before_kernel_construction(self):
        request = FourStreetSolveRequest("AsAd", "KsKd", ("2c3c4d7h8h",), iterations=10)
        with patch("pokerlab.exact_selected_solver.ExactSelectedRunoutKernel",
                   side_effect=AssertionError("kernel constructed")):
            with self.assertRaisesRegex(ValueError, "requires CFR"):
                solve_four_street_exact_selected(request)

    def test_blind_all_in_skips_training_and_integrates_hidden_boards(self):
        case = dict(self.case, config={"starting_stack": [0.5, 1.0]})
        result = solve_four_street_exact_selected(request_from_case(case))
        self.assertEqual(result["info_sets"], 0)
        self.assertEqual(result["strategy"], [])
        self.assertEqual(result["operator_census"]["training"]["calls"], 0)
        self.assertEqual(result["operator_census"]["training"]["reason"],
                         "no-information-sets")
        self.assertGreater(result["worlds"], 0)

    def test_pair_support_subnormal_rejects_before_training(self):
        case = {
            "sb_range": "AsAd:1,KsKd:5e-324", "bb_range": "QsQd:1",
            "config": {"starting_stack": [4, 3], "raise_sizes": [0.5],
                       "max_raises": 1, "include_all_in": False},
            "runouts": ["2c3c4d7h8h"],
            "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                            "max_raises": 0, "include_all_in": False},
        }
        request = request_from_case(case)
        with patch("pokerlab.exact_selected_solver.train_packed",
                   side_effect=AssertionError("training entered")):
            with self.assertRaisesRegex(ValueError, "pair probability converts"):
                solve_four_street_exact_selected(request)


if __name__ == "__main__":
    unittest.main()
