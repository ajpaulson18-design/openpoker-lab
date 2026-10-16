"""Independent fixture and evidence-boundary checks without board ranking."""
import copy
from fractions import Fraction
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pokerlab import flop_checkdown_worlds as worlds
from pokerlab.flop_checkdown_equity import FlopCheckdownEquities, reweight_flop_checkdown_equities
from scripts import benchmark_flop_equity_reuse as benchmark

SPEC = Path(__file__).resolve().parents[1] / "benchmarks/flop-equity-reuse-v1.json"


def _literal_range(text):
    result = []
    for token in text.split(','):
        hand, weight = token.split(':')
        result.append(({hand[:2], hand[2:]}, Fraction.from_float(float(weight))))
    return result


class FlopEquityReuseBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(SPEC.read_text(encoding='utf-8-sig'))

    def test_independent_literal_weight_census_and_frozen_spec(self):
        expected = ((64, 58, Fraction(1185, 64)),
                    (64, 58, Fraction(1185, 64)),
                    (64, 58, Fraction(1195, 64)),
                    (16, 15, Fraction(49, 8)))
        for fixture, (candidates, pairs, total) in zip(self.spec['fixtures'], expected):
            oop = _literal_range(self.spec[fixture['oop_range']])
            ip = _literal_range(self.spec[fixture['ip_range']])
            products = [first_weight * second_weight
                        for first_hand, first_weight in oop
                        for second_hand, second_weight in ip
                        if first_hand.isdisjoint(second_hand)]
            self.assertEqual(len(oop) * len(ip), candidates)
            self.assertEqual(len(products), pairs)
            self.assertEqual(sum(products, Fraction()), total)
            self.assertEqual(Fraction(fixture['expected_normalizer']), total)
        self.assertTrue(benchmark.validate_spec(self.spec))
        changed = copy.deepcopy(self.spec)
        changed['fixtures'][2]['expected_normalizer'] = '1185/64'
        with self.assertRaises(ValueError):
            benchmark.validate_spec(changed)

    def test_payload_comparison_removes_only_preparation_metadata(self):
        fresh = {'work_budget': {'total': 123}, 'value_oop': 0.5, 'strategy': []}
        prepared = {**fresh, 'equity_preparation': {'current_rank_calls': 0}}
        self.assertNotEqual(benchmark._canonical_hash(fresh),
                            benchmark._canonical_hash(prepared))
        self.assertEqual(benchmark._canonical_hash(fresh),
                         benchmark._canonical_hash(benchmark._without_preparation(prepared)))
        changed = {**prepared, 'value_oop': 0.6}
        self.assertNotEqual(benchmark._without_preparation(changed), fresh)
        self.assertIn('equity_preparation', prepared)

    def test_warm_guards_reject_each_ranking_boundary(self):
        for callback in (lambda: worlds.rank_hand(()),
                         lambda: worlds.combinations((), 2),
                         lambda: worlds.FlopCheckdownPlan.build(None)):
            with self.subTest(callback=callback), self.assertRaises(AssertionError):
                benchmark._guard_warm_rank_calls(callback)
        result, counters = benchmark._guard_warm_rank_calls(lambda: 'no ranking')
        self.assertEqual(result, 'no ranking')
        self.assertEqual(counters, {'rank_hand': 0, 'combinations': 0, 'plan_build': 0})

    def test_measured_budget_must_equal_preflight_before_replay(self):
        expected = {'budget_version': 'example', 'total_loop_entries_upper_bound': 100}
        result = {'work_budget': {**expected, 'total_loop_entries_upper_bound': 101}}
        with patch.object(benchmark, 'replay', side_effect=AssertionError('replay started')) as replay:
            with self.assertRaises(AssertionError):
                benchmark._verify_result(result, {}, self.spec,
                                         self.spec['fixtures'][0], expected)
            replay.assert_not_called()
        with patch.object(benchmark, 'replay', return_value={'nash_conv': 0.001}):
            verified = benchmark._verify_result({'work_budget': expected}, {}, self.spec,
                                                self.spec['fixtures'][0], expected)
            self.assertTrue(verified['work_budget_matches_preflight'])
            self.assertTrue(verified['target_met'])

    def test_mock_pipeline_checks_source_before_publication_and_allocation_parity(self):
        # Deliberately synthetic counts exercise orchestration, never physical accuracy.
        plan = worlds.prepare_flop_worlds(self.spec['board'], self.spec['base_oop_range'],
                                         self.spec['base_ip_range'])
        source = FlopCheckdownEquities(plan.board,
                                      tuple(tuple(hands) for hands in plan.hands),
                                      tuple(plan.pairs), ((1980, 0, 0),) * 58,
                                      tuple(plan.budget.items()))

        def selected(case):
            return reweight_flop_checkdown_equities(source, case['oop_range'], case['ip_range'])

        def result(case):
            table = selected(case)
            return table, {'work_budget': {'fixture': case['id']},
                           'pair_equities': table.build()[1], 'value_oop': 0., 'strategy': []}

        def fresh(case):
            _, payload = result(case)
            return payload, benchmark._serialize(payload), 0.02

        def warm(table, case):
            cached, payload = result(case)
            payload['equity_preparation'] = {
                'mode': 'prepared-counts', 'current_rank_calls': 0,
                'current_unordered_board_evaluations': 0, 'source_inclusive_admission': True,
                'validation': 'Structural consistency only; supplied counts require trusted provenance.',
            }
            return cached, payload, benchmark._serialize(payload), 0.01, {
                'rank_hand': 0, 'combinations': 0, 'plan_build': 0}

        def oracle(board, oop, ip, config):
            table = reweight_flop_checkdown_equities(source, oop, ip)
            return {'counts': table.build()[1]}

        def preflight(case, iterations, algorithm):
            return {'fixture_id': case['id'], 'status': 'admitted',
                    'ranking_started': False, 'solver_budget': {'fixture': case['id']}}

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            checkout = workspace / 'checkout'
            checkout.mkdir()
            output = checkout / 'result.json'
            source_checks = []

            def clean_status():
                source_checks.append(not output.exists())
                return '' if not output.exists() else 'untracked result'

            with patch.object(benchmark, 'ROOT', checkout), \
                 patch.object(benchmark, 'OUTPUT_PATH', output), \
                 patch.object(benchmark, 'LIVE_PATH', workspace / 'live.json'), \
                 patch.object(benchmark, '_status', side_effect=clean_status), \
                 patch.object(benchmark, '_revision', return_value=self.spec['baseline_main']), \
                 patch.object(benchmark, '_hashes', return_value={}), \
                 patch.object(benchmark, 'subprocess', SimpleNamespace(
                     run=lambda *args, **kwargs: SimpleNamespace(returncode=0))), \
                 patch.object(benchmark, 'preflight', side_effect=preflight), \
                 patch.object(benchmark, 'prepare_flop_checkdown_equities', return_value=source), \
                 patch.object(benchmark, '_historical_counts', return_value=source.build()[1]), \
                 patch.object(benchmark, 'prepare_oracle', side_effect=oracle), \
                 patch.object(benchmark, 'replay', return_value={'nash_conv': 0.001}), \
                 patch.object(benchmark, '_time_fresh', side_effect=fresh) as fresh_calls, \
                 patch.object(benchmark, '_time_warm', side_effect=warm) as warm_calls:
                report = benchmark.run(copy.deepcopy(self.spec))
            self.assertTrue(source_checks and all(source_checks))
            self.assertEqual(fresh_calls.call_count, 12)
            self.assertEqual(warm_calls.call_count, 13)
            self.assertTrue(report['acceptance_gate_met'])
            self.assertTrue(report['allocation']['matches_previously_verified_prepared_payload'])
            checksum = report.pop('artifact_sha256')
            self.assertEqual(checksum, benchmark._canonical_hash(report))
            self.assertTrue(output.exists())
            self.assertNotIn(b'\r\n', output.read_bytes())


if __name__ == '__main__':
    unittest.main()
