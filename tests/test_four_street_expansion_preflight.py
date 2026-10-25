from __future__ import annotations

import unittest
from contextlib import ExitStack
from unittest.mock import patch

from pokerlab import preflop_solver
from pokerlab import four_street_solver
from scripts import benchmark_four_street_integration as runner
from scripts import four_street_expansion_preflight as preflight


class FourStreetExpansionPreflightTests(unittest.TestCase):
    def test_candidate_admission_crosschecks_expanded_support_without_training(self):
        calls = []

        def forbidden(*_args, **_kwargs):
            calls.append(True)
            raise AssertionError("preflight entered a production solve or trainer")

        tripwires = (
            (preflop_solver, "solve_preflop"),
            (preflop_solver, "train_public_batched"),
            (preflop_solver, "train_cfrplus"),
            (preflop_solver, "train_planned"),
            (preflop_solver, "train_delayed_public_cfrplus"),
            (preflop_solver, "train_chance_sampled"),
            (preflop_solver, "evaluate_public_profile"),
            (preflop_solver.cfr, "train"),
            (four_street_solver, "solve_four_street"),
            (runner, "solve_four_street"),
        )
        with ExitStack() as stack:
            for owner, name in tripwires:
                stack.enter_context(patch.object(owner, name, side_effect=forbidden))
            result = preflight.prepare_expansion()

        self.assertEqual(calls, [])
        self.assertEqual(result["quality_gate"], None)
        self.assertEqual(result["production_calls_entered"], 0)
        self.assertFalse(result["attempted_training"])
        self.assertIn(result["outcome"], {"admitted", "rejected"})
        if result["outcome"] == "admitted":
            self.assertIsNone(result["first_rejection"])
        else:
            self.assertIsNotNone(result["first_rejection"])

        case, request = result["case"], result["request"]
        baseline_case = runner._literal_case()
        baseline_request = runner._literal_request()
        self.assertEqual(case["id"], "four-street-shared-river-expansion-v2")
        self.assertEqual(case["runouts"], [*baseline_case["runouts"], "5c6d7s8cKc"])
        expected_case = dict(baseline_case)
        expected_case["id"] = case["id"]
        expected_case["runouts"] = case["runouts"]
        self.assertEqual(case, expected_case)
        self.assertEqual(request["runouts"], case["runouts"])
        expected_request = baseline_request.to_dict()
        expected_request["runouts"] = case["runouts"]
        self.assertEqual(request, expected_request)

        independent = result["independent_admission"]
        comparison = result["support_comparison"]
        self.assertEqual(independent["counts"]["worlds"], 26)
        self.assertTrue(comparison["support_matches"])
        self.assertEqual(comparison["worlds_compared"], 26)
        self.assertEqual(comparison["pairs_compared"], 4)

        probabilities = {
            (row["sb_hand"], row["bb_hand"]): row["fraction"]
            for row in independent["pair_probabilities"]
        }
        self.assertEqual(probabilities, {
            ("AdAs", "KdKs"): "21/40",
            ("AdAs", "JdJh"): "7/40",
            ("QdQs", "KdKs"): "9/40",
            ("QdQs", "JdJh"): "3/40",
        })

        signs = {
            tuple(world["board"]): world["sign"]
            for world in independent["world_support"]
            if world["hands"] == ["AdAs", "KdKs"]
        }
        self.assertEqual(signs[("5c", "6d", "7s", "8c", "Jc")], 1)
        self.assertEqual(signs[("5c", "6d", "7s", "8c", "9h")], 0)
        self.assertEqual(signs[("5c", "6d", "7s", "8c", "Kc")], -1)


if __name__ == "__main__":
    unittest.main()
