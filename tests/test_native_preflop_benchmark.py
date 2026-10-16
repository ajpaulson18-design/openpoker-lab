"""Benchmark admission, provenance and failure-retention regression checks."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import benchmark_native_preflop as benchmark


class NativeBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(benchmark.CONFIG.read_text(encoding='utf-8'))
        cls.preflights = benchmark.preflight_cases(cls.config)
        cls.counts = {('AdAs', 'KdKs'): (1410336, 9308, 292660),
                      ('QdQs', 'AsKh'): (968267, 7226, 736811),
                      ('QdQs', 'KdKs'): (292846, 9336, 1410122)}
        cls.references = {}
        for item in cls.preflights:
            table, rows, _ = benchmark.reference_table(item, cls.counts)
            result = benchmark.solve_prepared_push_fold(table, config=item['case']['config'], iterations=2000)
            cls.references[item['case']['id']] = table, result

    def test_fixed_spec_pair_roles_exact_priors_and_caps(self):
        benchmark.validate_spec(self.config)
        self.assertEqual(set(self.counts), {('AdAs', 'KdKs'), ('QdQs', 'AsKh'), ('QdQs', 'KdKs')})
        self.assertEqual([len(item['plan'].pairs) for item in self.preflights], [3, 3, 3, 4])
        self.assertEqual([item['budget']['total_loop_entries_upper_bound'] for item in self.preflights],
                         [370245216, 370245216, 370245216, 493147312])
        altered = json.loads(json.dumps(self.config)); altered['iterations'] = 2001
        with self.assertRaises(ValueError): benchmark.validate_spec(altered)
        split, _, derived = benchmark.reference_table(self.preflights[-1], self.counts)
        self.assertEqual(derived[0]['global_suit_map'], {'c': 'h', 'd': 'd', 'h': 'c', 's': 's'})
        self.assertEqual(split.counts[1], split.counts[2])

    def test_pinned_loader_roles_blobs_and_checksums_without_git_history(self):
        fixtures = {row['path']: (benchmark.ROOT / row['path']).read_bytes()
                    for row in self.config['historical_source']['pairs']}
        def invoke(args, **kwargs):
            revision, path = args[-1].split(':', 1)
            self.assertEqual(revision, benchmark.PINNED)
            if args[1] == 'rev-parse':
                return benchmark.PINNED_BLOBS[path] + '\n'
            self.assertEqual(args[1], 'show')
            return fixtures[path]
        with patch.object(benchmark, 'subprocess', SimpleNamespace(check_output=invoke)):
            counts, records = benchmark._load_pinned_oracles(self.config)
            self.assertEqual(counts, self.counts)
            self.assertEqual(len(records), 3)
            first = next(iter(fixtures))
            corrupted = json.loads(fixtures[first]); corrupted['counts']['wins'] += 1
            fixtures[first] = json.dumps(corrupted).encode()
            with self.assertRaisesRegex(ValueError, 'checksum failed'):
                benchmark._load_pinned_oracles(self.config)

    def run_mock_pipeline(self, *, quality_miss=False):
        manifest = {'executable_sha256': 'pinned-test-build'}
        def native_call(case, directory):
            table, result = self.references[case['id']]
            metadata = {'build': manifest}
            prepared = SimpleNamespace(equities=table, metadata=metadata)
            serialized = json.dumps({'result': result, 'equity_preparation': metadata}, sort_keys=True, separators=(',', ':'))
            return prepared, result, serialized
        def python_call(case):
            table, result = self.references[case['id']]
            return table, result, json.dumps(result, sort_keys=True, separators=(',', ':'))
        quality_calls = 0
        original_quality = benchmark.quality
        def check_quality(*args):
            nonlocal quality_calls
            quality_calls += 1
            checked = original_quality(*args)
            if quality_miss and quality_calls == 5:
                checked = dict(checked, passed=False, exploitability_passed=False)
            return checked
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory); build = root / 'local-build'; build.mkdir()
            stack.enter_context(patch.object(benchmark, 'git_snapshot', return_value={'revision': 'frozen-test', 'status': []}))
            stack.enter_context(patch.object(benchmark, 'source_hashes', return_value={'test': 'unchanged'}))
            stack.enter_context(patch.object(benchmark, '_load_pinned_oracles', return_value=(self.counts, [])))
            stack.enter_context(patch.object(benchmark.native, '_backend', return_value=(build / 'native-test', manifest)))
            stack.enter_context(patch.object(benchmark, '_invoke_native', side_effect=native_call))
            stack.enter_context(patch.object(benchmark, '_invoke_python', side_effect=python_call))
            stack.enter_context(patch.object(benchmark, 'quality', side_effect=check_quality))
            report = benchmark.run(self.config, build, root / 'report.json', root / 'live.json')
            saved = json.loads((root / 'report.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['artifact_sha256'], benchmark.checksum({k: v for k, v in saved.items() if k != 'artifact_sha256'}))
            self.assertEqual(len(report['samples']), 15)
            self.assertEqual(sum(s['backend'] == 'native' for s in report['samples']), 12)
            self.assertEqual(sum(s['backend'] == 'python' for s in report['samples']), 3)
            self.assertTrue(report['provenance']['native_build_identity_unchanged'])
            self.assertTrue(report['tracemalloc_matches_measured_native_call'])
            self.assertTrue(all(all(s['checks'].values()) for s in report['samples']))
            return report

    def test_complete_pipeline_checks_every_profile_and_publishes_checksum(self):
        self.assertTrue(self.run_mock_pipeline()['passed'])

    def test_measured_quality_miss_retained_without_losing_later_samples(self):
        report = self.run_mock_pipeline(quality_miss=True)
        self.assertFalse(report['passed'])
        self.assertTrue(any('quality gate failed' in message for message in report['failures']))

    def test_admission_and_output_guards_precede_backend_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(benchmark.native, '_backend', side_effect=AssertionError('backend started')):
                with self.assertRaises(ValueError):
                    benchmark.run(self.config, root, benchmark.ROOT / 'README.md', root.parent / 'live.json')
                with patch.object(benchmark, 'git_snapshot', return_value={'revision': 'frozen', 'status': []}), \
                        patch.object(benchmark, 'source_hashes', return_value={}), \
                        patch.object(benchmark, '_admit', side_effect=ValueError('admission rejected')):
                    with self.assertRaisesRegex(ValueError, 'admission rejected'):
                        benchmark.run(self.config, root, root.parent / 'report.json', root.parent / 'live.json')


if __name__ == '__main__':
    unittest.main()
