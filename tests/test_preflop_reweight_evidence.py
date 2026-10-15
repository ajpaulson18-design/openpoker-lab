"""Published evidence must stay pinned even if its internal checksum is valid."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from scripts import benchmark_preflop_equity_reweight as benchmark


class ReweightEvidenceTests(unittest.TestCase):
    def test_changed_fixture_rejects_under_original_benchmark_name(self):
        config = json.loads(benchmark.CONFIG.read_text(encoding='utf-8'))
        benchmark.validate_config(config)
        config['cases'][0]['sb_range'] = 'AsAd:1'
        with self.assertRaisesRegex(ValueError, 'exact declared v1 fixture'):
            benchmark.validate_config(config)

    def historical_git(self, *args):
        if args[0] == 'rev-parse':
            return benchmark.PUBLISHED[args[1].split('/')[-1]]
        raise AssertionError(args)

    def test_changed_published_blob_rejects_before_loading_counts(self):
        with patch.object(benchmark, 'git', return_value='untrusted-blob'):
            with self.assertRaisesRegex(ValueError, 'Git blob mismatch'):
                benchmark.reference_counts()

    def test_changed_checksum_rejects_even_with_expected_git_identity(self):
        def fake_git(*args):
            if args[0] == 'rev-parse':
                return self.historical_git(*args)
            return json.dumps({'schema_version': 1, 'benchmark_id': 'preflop-push-fold-v1',
                               'artifact_sha256': 'changed'})
        with patch.object(benchmark, 'git', side_effect=fake_git):
            with self.assertRaisesRegex(ValueError, 'checksum/schema'):
                benchmark.reference_counts()

    def test_checksum_includes_count_mutations(self):
        original = {'counts': {'wins': 7, 'ties': 1, 'losses': 2}}
        changed = deepcopy(original)
        changed['counts']['wins'] += 1
        self.assertNotEqual(benchmark.checksum(original), benchmark.checksum(changed))


if __name__ == '__main__':
    unittest.main()
