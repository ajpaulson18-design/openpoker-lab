"""Rank-free admission, producer isolation, and bounded lossless artifact tests."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import benchmark_weighted_full_deck_flop as bench


class WeightedFlopBenchmarkBoundaryTests(unittest.TestCase):
    def test_full_requested_geometry_is_admitted_without_ranking_or_solving(self):
        with patch.object(bench.production, 'rank_hand', side_effect=AssertionError('ranking')), \
             patch.object(bench.production, '_enumerate_worlds', side_effect=AssertionError('producer worlds')), \
             patch.object(bench.production, 'solve_postflop', side_effect=AssertionError('solving')):
            forecast = bench.preflight(bench.load_spec())
        self.assertEqual(forecast['worlds'], 5940)
        self.assertEqual(forecast['public_nodes'], 9512)
        self.assertEqual(forecast['max_world_node_iterations'], 28512000)
        self.assertEqual(forecast['plan_operations'], 148500)

    def test_dirty_source_refuses_before_geometry_or_oracle_preparation(self):
        state = {'revision': 'dirty', 'status': [' M source'], 'source_hashes': {}}
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(bench, 'snapshot', return_value=state), \
             patch.object(bench, 'preflight') as forecast, \
             patch.object(bench, 'prepare_reference') as oracle:
            report = bench.run(Path(temp)/'evidence')
        self.assertEqual(report['status'], 'error')
        self.assertEqual(report['samples'], [])
        forecast.assert_not_called(); oracle.assert_not_called()

    def test_producer_isolation_blocks_imported_aliases(self):
        with bench.independent_guard() as calls:
            with self.assertRaisesRegex(AssertionError, 'production helper'):
                bench.production.rank_hand(('As','Ad','Ks','Kd','Qs','Qd','Js'))
            with self.assertRaisesRegex(AssertionError, 'production helper'):
                bench.production.best_response(None)
        self.assertEqual(sum(calls.values()), 2)

    def test_lossless_file_hashes_and_local_paths_are_checked(self):
        payload = {'strategy': [{'hand':'AdAs','actions':[{'probability':.5}]}]}
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            row = bench.store_payload(directory, 'policy.json.gz', payload)
            self.assertEqual(bench.read_payload(directory, row), payload)
            for name in ('../policy.json.gz', '/policy.json.gz', 'sub/policy.json.gz', 'sub\\policy.json.gz'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    bench.read_payload(directory, dict(row,file=name))
            changed = dict(row, payload_sha256='changed')
            with self.assertRaisesRegex(ValueError, 'raw policy checksum'):
                bench.read_payload(directory, changed)
            path = directory / row['file']; path.write_bytes(path.read_bytes()+b'x')
            with self.assertRaisesRegex(ValueError, 'Compressed evidence checksum'):
                bench.read_payload(directory, row)


if __name__ == '__main__':
    unittest.main()
