import json
import unittest

from scripts import benchmark_preflop_prepared_budget as benchmark


class PreparedBenchmarkFixtureTests(unittest.TestCase):
    def test_removing_long_checkpoint_rejects_under_same_benchmark_version(self):
        config = json.loads(benchmark.CONFIG.read_text(encoding='utf-8'))
        benchmark.validate_config(config)
        config['checkpoints'].remove(10000)
        with self.assertRaisesRegex(ValueError, 'exact prepared-budget v1 fixture'):
            benchmark.validate_config(config)

    def test_weakening_cfrplus_gate_rejects_under_same_benchmark_version(self):
        config = json.loads(benchmark.CONFIG.read_text(encoding='utf-8'))
        config['cfrplus_final_exploitability_chip_limit'] = 0.005
        with self.assertRaises(ValueError):
            benchmark.validate_config(config)


if __name__ == '__main__':
    unittest.main()
