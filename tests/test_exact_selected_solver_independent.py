"""Independent exact-game replay of the research four-street solver."""
from fractions import Fraction
import unittest
from unittest.mock import patch

from scripts.four_street_certificate_v3 import evaluate_exact
from tests.test_four_street_certificate import _case
from tests.test_selected_operator_solver import request


class IndependentExactFourStreetSolverTests(unittest.TestCase):
    def test_four_street_policy_and_best_responses_against_exact_certificate(self):
        from pokerlab.exact_selected_solver import solve_four_street_exact_selected
        case = _case()
        payload = solve_four_street_exact_selected(request(case, iterations=10))
        self.assertEqual({row['street'] for row in payload['strategy']},
                         {'preflop', 'flop', 'turn', 'river'})
        audit = evaluate_exact(case, payload)
        for name in ('value_sb', 'sb_best_response_value', 'bb_best_response_value', 'nash_conv'):
            self.assertAlmostEqual(payload[name], float(Fraction(audit['metrics'][name])), delta=1e-9, msg=name)
        self.assertIsInstance(audit['threshold_met'], bool)

    def test_request_rejected_before_ranking_under_low_work_budget(self):
        from pokerlab.exact_selected_kernel import ExactSelectedKernelLimits
        from pokerlab.exact_selected_solver import solve_four_street_exact_selected
        case = _case()
        with patch('pokerlab.exact_selected_kernel.rank_hand', side_effect=AssertionError('rank before admission')):
            with self.assertRaises(ValueError):
                solve_four_street_exact_selected(request(case, iterations=10),
                    kernel_limits=ExactSelectedKernelLimits(max_modeled_work=1000))

    def test_twenty_two_world_fixture_admits_without_legacy_worlds(self):
        import json
        from pathlib import Path
        from pokerlab.exact_selected_solver import solve_four_street_exact_selected
        path = Path(__file__).resolve().parents[1] / 'benchmarks/four-street-integration-v1.json'
        case = json.loads(path.read_text(encoding='utf-8'))['case']
        with patch('pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds',
                   side_effect=AssertionError('legacy world producer')):
            payload = solve_four_street_exact_selected(request(case, iterations=10))
        self.assertEqual(payload['worlds'], 22)
        self.assertEqual({row['street'] for row in payload['strategy']},
                         {'preflop', 'flop', 'turn', 'river'})
        audit = evaluate_exact(case, payload)
        for name in ('value_sb', 'sb_best_response_value', 'bb_best_response_value', 'nash_conv'):
            self.assertAlmostEqual(payload[name], float(Fraction(audit['metrics'][name])), delta=1e-9, msg=name)

    def test_pair_support_underflow_rejects_before_ranking(self):
        from pokerlab.exact_selected_solver import solve_four_street_exact_selected
        case = _case(sb='AsAd:1,KsKd:1e-200', bb='QsQd:1,JhJc:1e-200')
        with patch('pokerlab.exact_selected_kernel.rank_hand', side_effect=AssertionError('rank before pair support admission')):
            with self.assertRaisesRegex(ValueError, 'pair probability'):
                solve_four_street_exact_selected(request(case, iterations=10))

    def test_blind_all_in_no_decisions_exact_certificate(self):
        from pokerlab.exact_selected_solver import solve_four_street_exact_selected
        case = _case(stacks=[0.5, 1.0])
        payload = solve_four_street_exact_selected(request(case, iterations=10))
        self.assertEqual(payload['strategy'], [])
        self.assertEqual(payload['info_sets'], 0)
        audit = evaluate_exact(case, payload)
        self.assertAlmostEqual(payload['value_sb'], float(Fraction(audit['metrics']['value_sb'])), delta=1e-12)
        self.assertAlmostEqual(payload['nash_conv'], float(Fraction(audit['metrics']['nash_conv'])), delta=1e-12)

    def test_training_failure_releases_rank_cache(self):
        from pokerlab.exact_selected_solver import solve_four_street_exact_selected
        from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
        calls = []
        clear = ExactSelectedRunoutKernel.clear_rank_cache
        def observe(kernel):
            calls.append(kernel)
            clear(kernel)
        with patch.object(ExactSelectedRunoutKernel, 'clear_rank_cache', autospec=True, side_effect=observe), \
             patch('pokerlab.exact_selected_solver.train_packed', side_effect=RuntimeError('synthetic training error')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic training error'):
                solve_four_street_exact_selected(request(_case(), iterations=10))
        self.assertEqual(len(calls), 1)
