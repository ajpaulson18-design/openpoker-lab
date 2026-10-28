"""Full-history batched lookup parity, work sharing and fail-closed controls."""
import unittest
from unittest.mock import patch

from pokerlab.exact_selected_solver import _prepare_exact_selected, solve_four_street_exact_selected
from pokerlab.suit_quotient_plan import SuitQuotientPlan, _prefix
from pokerlab.shared_public_topology import DecisionVertex
from scripts.exact_selected_compact_certificate import evaluate_exact
from tests.test_equivariant_selected_solver import symmetric_case, METRICS
from tests.test_selected_operator_solver import request


def solve(case, lookup):
    return solve_four_street_exact_selected(request(case), pair_diagnostics="compact",
        exact_arithmetic="dyadic", training_reduction="suit-equivariant",
        strategy_storage="suit-quotient", quotient_lookup=lookup)


class BatchedSuitRowLookupTests(unittest.TestCase):
    def test_every_member_and_hole_matches_reference_without_per_hand_history_replay(self):
        from pokerlab import suit_quotient_plan as module
        case = symmetric_case()
        case.update(sb_range="AcAh,AdAh,2cAh,2dAh", bb_range="KcKh,KdKh,3cKh,3dKh")
        value = _prepare_exact_selected(request(case), pair_diagnostics="compact",
            exact_arithmetic="dyadic", training_reduction="suit-equivariant")
        plan = SuitQuotientPlan(value, 10)
        for occurrence in value.topology.iter_occurrences():
            vertex = value.topology.vertices[occurrence.vertex_id]
            if not isinstance(vertex, DecisionVertex):
                continue
            prefix = _prefix(occurrence.history)
            expected = [None] * value.kernel.hand_counts[vertex.player]
            for hand in plan.supported_hand_indices(prefix, vertex.player):
                expected[hand] = plan.locate((vertex.player, hand, occurrence.history))
            with patch.object(SuitQuotientPlan, "_decision_at_history", autospec=True,
                    side_effect=SuitQuotientPlan._decision_at_history) as routes, \
                 patch.object(module, "_history", wraps=module._history) as transforms, \
                 patch.object(SuitQuotientPlan, "locate", side_effect=AssertionError("per-row path")):
                actual = plan.locate_decision_rows(vertex.player, occurrence.history, vertex.actions)
            self.assertEqual(actual, expected)
            self.assertEqual(routes.call_count, 1)
            self.assertEqual(transforms.call_count, len(plan.group))

    def test_complete_payoff_varying_and_identity_games_match_policy_metrics_and_exact_br(self):
        for mode in ("private-flush", "asymmetric"):
            case = symmetric_case()
            if mode == "private-flush":
                case.update(sb_range="AcQc,AdQd", bb_range="KcJc,KdJd",
                            runouts=["2c3c7c9hTs", "2d3d7d9hTs"])
            else:
                case.update(sb_range="AcAh:0.7,AdAh:0.3", bb_range="KcKh:0.4,KdKh:0.6")
            with self.subTest(game=mode):
                reference, batched = solve(case, "per-row"), solve(case, "per-decision")
                for field in ("strategy", *METRICS):
                    self.assertEqual(reference[field], batched[field], field)
                left, right = (evaluate_exact(case, value)["exact_certificate"]
                               for value in (reference, batched))
                for field in ("metrics", "threshold_met", "normalized_policy_sha256"):
                    self.assertEqual(left[field], right[field], field)
                self.assertEqual(reference["operator_census"]["whole_request_admission"],
                                 batched["operator_census"]["whole_request_admission"])

    def test_malformed_actor_history_menu_and_mode_reject(self):
        value = _prepare_exact_selected(request(symmetric_case()), pair_diagnostics="compact",
            training_reduction="suit-equivariant")
        plan = SuitQuotientPlan(value, 10)
        key, menu = next(plan.iter_rows())
        for args in ((True, key[2], menu), (key[0], ("flop@",), menu),
                     (1-key[0], key[2], menu), (key[0], key[2], ())):
            with self.subTest(args=args), self.assertRaises(ValueError):
                plan.locate_decision_rows(*args)
        with patch("pokerlab.exact_selected_solver.ExactSelectedRunoutKernel", side_effect=AssertionError("kernel")):
            for mode in (None, True, "cached"):
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    solve(symmetric_case(), mode)

    def test_batched_member_corruption_still_rejects_phase_before_result(self):
        original = SuitQuotientPlan.locate_decision_rows
        def duplicate(plan, player, history, menu):
            rows = original(plan, player, history, menu)
            result = []
            for item in rows:
                result.append(None if item is None else (item[0], item[1], 1))
            return result
        with patch.object(SuitQuotientPlan, "locate_decision_rows", new=duplicate):
            with self.assertRaisesRegex(ValueError, "Duplicate Q member"):
                solve(symmetric_case(), "per-decision")


if __name__ == "__main__":
    unittest.main()
