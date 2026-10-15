import json
import unittest

from scripts import benchmark_preflop_suit_remap as benchmark


def count_rows():
    return [
        {'sb_hand': 'AdAs', 'bb_hand': 'KdKs', 'wins': 1_410_336,
         'ties': 9_308, 'losses': 292_660, 'boards': 1_712_304},
        {'sb_hand': 'QdQs', 'bb_hand': 'AsKh', 'wins': 968_267,
         'ties': 7_226, 'losses': 736_811, 'boards': 1_712_304},
        {'sb_hand': 'QdQs', 'bb_hand': 'KdKs', 'wins': 292_846,
         'ties': 9_336, 'losses': 1_410_122, 'boards': 1_712_304},
    ]


class SuitBenchmarkTests(unittest.TestCase):
    def test_four_pair_3000_iteration_request_keeps_original_work_guard(self):
        config = json.loads(benchmark.CONFIG.read_text(encoding='utf-8'))
        config['iterations'] = 3000
        counts = count_rows()
        table = benchmark.reference.trusted_reference_table(counts)
        split = benchmark.cases(config, counts)[-1]
        with self.assertRaisesRegex(ValueError, '500,000,000 modeled loop entries'):
            benchmark.run_case(table, split, config)

    def test_fixture_mutation_rejected_under_same_version(self):
        config = json.loads(benchmark.CONFIG.read_text(encoding='utf-8'))
        benchmark.validate_config(config)
        config['split_game']['bb_range'] = 'AsKh:0.25,KsKd:1'
        with self.assertRaisesRegex(ValueError, 'exact v1 suit fixture'):
            benchmark.validate_config(config)

    def test_all_24_images_preserve_role_labelled_count_rows(self):
        config = json.loads(benchmark.CONFIG.read_text(encoding='utf-8'))
        fixtures = benchmark.cases(config, count_rows())
        self.assertEqual(len(fixtures), 25)
        self.assertEqual(len({(r['sb_range'], r['bb_range']) for r in fixtures[:24]}), 24)
        for case in fixtures[:24]:
            self.assertEqual(len(case['counts']), 3)
            for original, transformed in zip(count_rows(), case['counts']):
                self.assertEqual(tuple(original[k] for k in ('wins', 'ties', 'losses')),
                                 tuple(transformed[k] for k in ('wins', 'ties', 'losses')))
                self.assertEqual(transformed['sb_hand'][0], original['sb_hand'][0])
                self.assertEqual(transformed['bb_hand'][0], original['bb_hand'][0])

    def test_split_ak_weights_preserve_original_normalized_game(self):
        config = json.loads(benchmark.CONFIG.read_text(encoding='utf-8'))
        split = benchmark.cases(config, count_rows())[-1]
        rows = {(r['sb_hand'], r['bb_hand']): r for r in split['counts']}
        self.assertEqual(set(rows), {('AdAs', 'KdKs'), ('QdQs', 'AsKh'),
                                     ('QdQs', 'AsKc'), ('QdQs', 'KdKs')})
        for key in ('wins', 'ties', 'losses', 'boards'):
            self.assertEqual(rows['QdQs', 'AsKh'][key], rows['QdQs', 'AsKc'][key])
        self.assertEqual(rows['QdQs', 'AsKh']['pair_probability'], 1 / 26)
        self.assertEqual(rows['QdQs', 'AsKc']['pair_probability'], 1 / 26)


if __name__ == '__main__':
    unittest.main()
