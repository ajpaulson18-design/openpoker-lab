"""Evidence-boundary regressions; orchestration uses a saved verified policy."""
import copy
from dataclasses import replace
from fractions import Fraction
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pokerlab import flop_checkdown_worlds as worlds
from pokerlab.flop_checkdown_equity import FlopCheckdownEquities
from pokerlab.flop_suit_equity import remap_flop_checkdown_equities_by_suit, flop_suit_remap_provenance
from scripts import benchmark_flop_suit_equity as benchmark

ROOT = Path(__file__).resolve().parents[1]


class FlopSuitBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((ROOT / 'benchmarks/flop-suit-equity-v1.json').read_text(encoding='utf-8-sig'))
        cls.cases = benchmark.validate_spec(cls.spec)
        cls.policy = json.loads((ROOT / 'benchmarks/results/flop-weighted-eight-hand-v1-policies/'
                                'weighted-8x8-stack24-raises2-t4000.json').read_text())
        if benchmark.canonical_hash(cls.policy) != benchmark.HIST_POLICY:
            raise AssertionError('Saved independently verified policy differs from the pinned baseline')
        plan = worlds.prepare_flop_worlds(cls.spec['source_board'], cls.spec['source_oop_range'],
                                         cls.spec['source_ip_range'])
        counts = tuple((row['wins'], row['ties'], row['losses'])
                       for row in cls.policy['pair_equities'])
        cls.source = FlopCheckdownEquities(plan.board, tuple(tuple(h) for h in plan.hands),
                                          tuple(plan.pairs), counts, tuple(plan.budget.items()))
        cls.source.validate()

    def test_fixed_case_census_and_changed_board_texture(self):
        self.assertEqual(len(self.cases), 27)
        images = self.cases[:24]
        self.assertEqual(len({(c['board'], c['oop_range'], c['ip_range']) for c in images}), 24)
        self.assertEqual(len({c['board'] for c in images}), 12)
        self.assertEqual([c['expected_compatible_pairs'] for c in self.cases], [1] * 24 + [58, 58, 2])
        mixed = self.cases[-1]
        _, priors, total = benchmark.pair_census(mixed['board'], mixed['oop_range'], mixed['ip_range'])
        self.assertEqual(total, Fraction(3, 4))
        self.assertEqual(set(priors.values()), {Fraction(1, 3), Fraction(2, 3)})
        changed = copy.deepcopy(self.spec)
        changed['source_board'] = '2c3d4d'
        with self.assertRaises(ValueError):
            benchmark.validate_spec(changed)

    def test_provenance_must_name_the_actual_target_table_board(self):
        case = self.cases[0]
        target = remap_flop_checkdown_equities_by_suit(
            self.source, case['board'], case['oop_range'], case['ip_range'])
        rows = flop_suit_remap_provenance(self.source, case['board'], case['oop_range'], case['ip_range'])
        self.assertEqual(len(benchmark.verify_provenance(rows, self.source, target)), 1)
        different_board = replace(target, board=('2c', '3c', '4h'))
        different_board.validate()
        with self.assertRaises(AssertionError):
            benchmark.verify_provenance(rows, self.source, different_board)

    def _forward_policy(self, case):
        result = copy.deepcopy(self.policy)
        mapping = case['source_map']
        board = list(benchmark.expand_board(case['board']))
        result['board'] = board
        for row in result['pair_equities']:
            for key in ('oop_hand', 'ip_hand'):
                row[key] = ''.join(sorted(benchmark.map_card(row[key][i:i+2], mapping) for i in (0, 2)))
        for row in result['strategy']:
            row['hand'] = ''.join(sorted(benchmark.map_card(row['hand'][i:i+2], mapping) for i in (0, 2)))
            row['board'] = list(board)
        return result

    def test_inverse_policy_mapping_preserves_values_and_checks_actual_row_boards(self):
        case = self.cases[24]
        mapped = self._forward_policy(case)
        restored = benchmark.inverse_map_result(
            mapped, case['source_map'], self.spec['source_oop_range'],
            self.spec['source_ip_range'], self.spec['source_board'])
        self.assertEqual(benchmark.canonical_hash(restored), benchmark.HIST_POLICY)
        changed = copy.deepcopy(mapped)
        changed['strategy'][0]['board'] = ['2d', '3d', '4s']
        with self.assertRaises(AssertionError):
            benchmark.inverse_map_result(changed, case['source_map'], self.spec['source_oop_range'],
                                         self.spec['source_ip_range'], self.spec['source_board'])
        changed = copy.deepcopy(mapped)
        changed['value_oop'] += .01
        restored = benchmark.inverse_map_result(changed, case['source_map'], self.spec['source_oop_range'],
                                                 self.spec['source_ip_range'], self.spec['source_board'])
        self.assertNotEqual(benchmark.canonical_hash(restored), benchmark.HIST_POLICY)

    def test_measured_budget_rejects_before_replay_and_warm_rank_guards_work(self):
        with patch.object(benchmark, 'replay', side_effect=AssertionError('replay started')) as replay:
            with self.assertRaises(AssertionError):
                benchmark.verify_result({'work_budget': {'total': 101}}, {}, self.spec, {'total': 100})
            replay.assert_not_called()
        for callback in (lambda: worlds.rank_hand(()), lambda: worlds.combinations((), 2),
                         lambda: worlds.FlopCheckdownPlan.build(None)):
            with self.assertRaises(AssertionError):
                benchmark.guard_warm(callback)

    def test_mock_pipeline_retains_all_cases_and_checks_source_before_publication(self):
        # Replay/training are mocked here; physical accuracy belongs to the formal oracle run.
        def transferred(case):
            return remap_flop_checkdown_equities_by_suit(
                self.source, case['board'], case['oop_range'], case['ip_range'])

        def budget(case):
            return self.policy['work_budget'] if case['group'] == 'whole-range-image' else {'fixture': case['id']}

        def preflight(case, iterations, algorithm):
            return {'fixture_id': case['id'], 'status': 'admitted',
                    'ranking_started': False, 'solver_budget': budget(case)}

        def warm(table, case):
            target = transferred(case)
            provenance = flop_suit_remap_provenance(
                table, case['board'], case['oop_range'], case['ip_range'])
            if case['group'] == 'whole-range-image':
                result = self._forward_policy(case)
            else:
                result = {'board': list(target.board), 'work_budget': budget(case),
                          'pair_equities': target.build()[1], 'strategy': []}
            result['equity_preparation'] = {'mode': 'prepared-counts'}
            payload = benchmark.serialize({'result': result, 'provenance': provenance})
            return target, provenance, result, payload, .01, {
                'rank_hand': 0, 'combinations': 0, 'plan_build': 0}

        def oracle(board, oop, ip, config):
            table = remap_flop_checkdown_equities_by_suit(self.source, board, oop, ip)
            return {'counts': table.build()[1]}

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            checkout = workspace / 'checkout'
            checkout.mkdir()
            output = checkout / 'report.json'
            source_checks = []

            def clean_status():
                source_checks.append(not output.exists())
                return '' if not output.exists() else 'untracked report'

            with patch.object(benchmark, 'ROOT', checkout), \
                 patch.object(benchmark, 'OUTPUT_PATH', output), \
                 patch.object(benchmark, 'LIVE_PATH', workspace / 'live.json'), \
                 patch.object(benchmark, 'status', side_effect=clean_status), \
                 patch.object(benchmark, 'revision', return_value=self.spec['baseline_main']), \
                 patch.object(benchmark, 'source_hashes', return_value={}), \
                 patch.object(benchmark, 'subprocess', SimpleNamespace(
                     run=lambda *args, **kwargs: SimpleNamespace(returncode=0))), \
                 patch.object(benchmark, 'preflight', side_effect=preflight), \
                 patch.object(benchmark, 'prepare_flop_checkdown_equities', return_value=self.source), \
                 patch.object(benchmark, 'historical_report', return_value=(
                     {}, {'oracle_pair_counts': self.source.build()[1]})), \
                 patch.object(benchmark, 'prepare_oracle', side_effect=oracle), \
                 patch.object(benchmark, 'replay', return_value={'nash_conv': .001}), \
                 patch.object(benchmark, 'warm_call', side_effect=warm) as warm_calls:
                report = benchmark.run(copy.deepcopy(self.spec))
            self.assertTrue(source_checks and all(source_checks))
            self.assertEqual(warm_calls.call_count, 82)
            self.assertEqual(len(report['results']), 27)
            self.assertTrue(report['acceptance_gate_met'])
            self.assertTrue(report['allocation']['matches_timed_verified_call'])
            self.assertTrue(output.exists())
            self.assertNotIn(b'\r\n', output.read_bytes())
            checksum = report.pop('artifact_sha256')
            self.assertEqual(checksum, benchmark.canonical_hash(report))


if __name__ == '__main__':
    unittest.main()
