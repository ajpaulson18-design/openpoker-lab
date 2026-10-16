"""Cheap integrity and admission checks for the paired pair-mean benchmark."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pokerlab import preflop_full_board_equity as equity
from scripts import benchmark_preflop_pair_mean as benchmark

PINNED_COUNTS = {
    ("AdAs", "KdKs"): (1_410_336, 9_308, 292_660),
    ("QdQs", "AsKh"): (968_267, 7_226, 736_811),
    ("QdQs", "KdKs"): (292_846, 9_336, 1_410_122),
}


class PreflopPairMeanBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(benchmark.SPEC.read_text(encoding="utf-8"))

    def test_frozen_spec_checksum_and_fixture_tampering(self):
        self.assertEqual(benchmark.checksum(self.spec), benchmark.SPEC_SHA256)
        self.assertIs(benchmark.validate_spec(self.spec), self.spec)
        altered = copy.deepcopy(self.spec)
        altered["case_definitions"][0]["compatible_pairs"] += 1
        with self.assertRaisesRegex(ValueError, "exact frozen preflop pair-mean specification"):
            benchmark.validate_spec(altered)
        altered = copy.deepcopy(self.spec)
        altered["algorithms"].reverse()
        with self.assertRaisesRegex(ValueError, "exact frozen preflop pair-mean specification"):
            benchmark.validate_spec(altered)

    def test_all_modes_algorithms_and_checkpoints_preflight_without_ranking(self):
        provenance = [{"fixture": "mocked pinned PR125 evidence"}]
        with patch.object(benchmark, "_load_pinned_oracles",
                          return_value=(PINNED_COUNTS, provenance)) as loader, \
             patch.object(equity, "rank_hand",
                          side_effect=AssertionError("preflight ranked a hand")) as rank, \
             patch.object(equity, "_board_combinations",
                          side_effect=AssertionError("preflight enumerated boards")) as boards, \
             patch.object(equity.PreflopEquityPlan, "build",
                          side_effect=AssertionError("preflight built physical worlds")) as build:
            prepared, actual_provenance = benchmark.prepare_cases(self.spec)

        loader.assert_called_once_with(self.spec)
        rank.assert_not_called()
        boards.assert_not_called()
        build.assert_not_called()
        self.assertEqual(actual_provenance, provenance)
        self.assertEqual([item["case"]["compatible_pairs"] for item in prepared],
                         [1, 3, 3, 4])
        expected = {
            (algorithm, iterations, mode)
            for algorithm in self.spec["algorithms"]
            for iterations in self.spec["checkpoints"]
            for mode in benchmark.MODES
        }
        for item in prepared:
            self.assertEqual(len(item["admissions"]), len(expected))
            actual = {(row["algorithm"], row["iterations"], row["mode"])
                      for row in item["admissions"]}
            self.assertEqual(actual, expected)
            self.assertTrue(all(row["prepared_counts"]["total_loop_entries_upper_bound"]
                                <= 500_000_000 for row in item["admissions"]))

    def test_payload_comparison_records_policy_gap_but_only_gates_scalars(self):
        scalar_fields = {field: 0.25 for field in benchmark.METRICS}
        categorical = {
            **scalar_fields, "config": {"starting_stack": [3, 3]},
            "algorithm": "cfrplus", "iterations": 3000,
            "training_iterations_completed": 3000, "tree": {"decision_nodes": 1},
            "info_sets": 2, "compatible_pairs": 1, "physical_boards": 1_712_304,
            "training_world_rows": 3, "pair_equities": [{"sb_hand": "AdAs"}],
            "solver_version": "preflop-full-checkdown-v1",
            "strategy_schema": "preflop-strategy-v1",
            "runout_mode": "full-deck-hidden-final-board-checkdown", "scope": "test",
            "strategy": [{"player": "sb", "hand": "AdAs", "street": "preflop",
                          "revealed_board": [], "history": [],
                          "actions": [{"name": "fold", "amount": 0, "raise_to": 0,
                                       "history_key": "fold", "probability": 0.5},
                                      {"name": "call", "amount": 0.5, "raise_to": 1,
                                       "history_key": "call", "probability": 0.5}]}],
        }
        mean = copy.deepcopy(categorical)
        mean["world_indexing"] = "pair-mean"
        mean["training_world_rows"] = 1
        mean["strategy"][0]["actions"][0]["probability"] = 0.5001
        mean["strategy"][0]["actions"][1]["probability"] = 0.4999
        result = benchmark.compare_payloads(
            categorical, mean,
            {"acceptance": {"cross_mode_scalar_absolute_tolerance": 1e-8}},
        )
        self.assertTrue(result["meets_scalar_agreement_gate"])
        self.assertAlmostEqual(result["max_policy_probability_gap"], 0.0001)
        self.assertEqual(result["scalar_absolute_gaps"], {field: 0 for field in benchmark.METRICS})

        changed_game = copy.deepcopy(mean)
        changed_game["physical_boards"] += 1
        with self.assertRaisesRegex(ValueError, "physical/game field"):
            benchmark.compare_payloads(categorical, changed_game,
                                       {"acceptance": {"cross_mode_scalar_absolute_tolerance": 1e-8}})
        changed_policy = copy.deepcopy(mean)
        changed_policy["strategy"][0]["hand"] = "KsKd"
        with self.assertRaisesRegex(ValueError, "Private information or public history"):
            benchmark.compare_payloads(categorical, changed_policy,
                                       {"acceptance": {"cross_mode_scalar_absolute_tolerance": 1e-8}})

    def test_replay_failure_keeps_raw_timings_and_prevents_acceptance(self):
        spec = {'algorithms': ['cfrplus'], 'checkpoints': [10], 'final_repeats': 2,
                'traced_case': 'fixture', 'traced_algorithm': 'cfrplus',
                'trace_scope': 'mocked'}
        item = {'case': {'id': 'fixture'}, 'table': None, 'counts': [],
                'derivations': [], 'admissions': []}
        timing = {'seconds': 0.125, 'python_peak_bytes': None,
                  'serialized_bytes_utf8': 12, 'payload_sha256': 'retained'}
        state = {'revision': 'fixture', 'status': []}
        with patch.object(benchmark, 'validate_spec', side_effect=lambda x: x), \
             patch.object(benchmark.baseline, 'snapshot', return_value=state), \
             patch.object(benchmark, 'source_hashes', return_value={'fixture': 'stable'}), \
             patch.object(benchmark, 'prepare_cases', return_value=([item], [])), \
             patch.object(benchmark, 'measure', return_value=({'fixture': True}, timing)), \
             patch.object(benchmark.baseline, 'assess', side_effect=ValueError('replay failure')), \
             patch.object(benchmark, 'compare_payloads', return_value={'meets_scalar_agreement_gate': False}):
            report = benchmark.run(spec)
        self.assertFalse(report['all_final_gates_pass'])
        self.assertEqual(len(report['errors']), 6)
        profile = report['cases'][0]['profiles'][0]
        self.assertEqual(profile['paired_sample_orders'],
                         [['categorical', 'pair-mean'], ['pair-mean', 'categorical']])
        for rows in profile['modes'].values():
            self.assertEqual(len(rows['samples']), 2)
            self.assertEqual(rows['samples'][0]['seconds'], 0.125)
            self.assertEqual(rows['payload'], {'fixture': True})
            self.assertEqual(rows['checks'], [])

    def test_dirty_checkout_rejects_before_preparation(self):
        dirty = {"revision": "fixture-revision", "status": [" M pokerlab/example.py"]}
        with patch.object(benchmark.baseline, "snapshot", return_value=dirty):
            with patch.object(benchmark, "source_hashes", return_value={"fixture": "stable"}):
                with patch.object(benchmark, "prepare_cases",
                                  side_effect=AssertionError("preparation started")) as prepare:
                    with self.assertRaisesRegex(ValueError, "clean committed source"):
                        benchmark.run(self.spec)
        prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()