"""Admission, immutable table and malformed native-response boundaries."""
from dataclasses import FrozenInstanceError
from fractions import Fraction
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pokerlab import native_preflop_equity as native
from pokerlab.preflop_full_board_equity import BOARDS_PER_PAIR, plan_preflop_equities
from scripts import build_native_preflop as builder
from pokerlab.preflop_push_fold import solve_prepared_push_fold
from scripts.preflop_push_fold_validation import replay


class NativePreparationBoundaryTests(unittest.TestCase):
    def response(self):
        return {'schema_version': 1, 'mode': 'count',
                'counts': [[1410336, 9308, 292660]],
                'boards_per_pair': BOARDS_PER_PAIR, 'rank_calls': 2 * BOARDS_PER_PAIR}

    def test_admission_rejects_before_backend_or_native_work(self):
        for sb, bb in [('random', 'random'), ('AA', 'KK'), ('AsAd', 'AsKh'), ('invalid', 'KdKs')]:
            with self.subTest(sb=sb, bb=bb), patch.object(native, '_invoke', side_effect=AssertionError('native started')):
                with self.assertRaises(ValueError):
                    native.prepare_native_preflop_equities(sb, bb, build_directory='unused')

    def test_table_exact_priors_masses_and_metadata_are_separate(self):
        plan = plan_preflop_equities('AsAd:1,QdQs:.5', 'KdKs:1,AsKh:.25')
        physical = {('AdAs', 'KdKs'): [1410336, 9308, 292660],
                    ('QdQs', 'KdKs'): [292846, 9336, 1410122],
                    ('QdQs', 'AsKh'): [968267, 7226, 736811]}
        count_rows = [physical[(''.join(plan.hands[0][i]), ''.join(plan.hands[1][j]))] for i, j, _ in plan.pairs]
        response = self.response(); response.update(counts=count_rows, rank_calls=6 * BOARDS_PER_PAIR)
        with patch.object(native, '_invoke', return_value=(response, {'compiler': 'local-test'})) as invoke:
            prepared = native.prepare_native_preflop_equities('AsAd:1,QdQs:.5', 'KdKs:1,AsKh:.25', build_directory='unused')
        self.assertEqual(invoke.call_args.args[0], 'COUNT')
        table = prepared.equities; table.validate()
        self.assertEqual(table.hands, plan.hands); self.assertEqual(table.pairs, plan.pairs)
        self.assertEqual(table.budget, plan.budget)
        self.assertEqual(tuple(prior for _, _, prior in table.pairs), (Fraction(8, 13), Fraction(4, 13), Fraction(1, 13)))
        for (i, j, prior), (wins, ties, losses) in zip(table.pairs, table.counts):
            expected = [(i, j, float(prior * Fraction(count, BOARDS_PER_PAIR)), sign)
                        for sign, count in zip((-1, 0, 1), (losses, ties, wins)) if count]
            self.assertEqual([row for row in table.worlds if row[:2] == (i, j)], expected)
        self.assertEqual(prepared.metadata['board_evaluations'], 3 * BOARDS_PER_PAIR)
        self.assertEqual(prepared.metadata['rank_calls'], 6 * BOARDS_PER_PAIR)
        prepared.metadata['build']['compiler'] = 'mutated'
        self.assertEqual(prepared.metadata['build']['compiler'], 'local-test')
        with self.assertRaises(FrozenInstanceError):
            prepared.equities = None

    def test_bad_native_count_rows_or_work_census_reject(self):
        invalid = [dict(counts=[]), dict(counts=[[True, 0, BOARDS_PER_PAIR - 1]]),
                   dict(counts=[[BOARDS_PER_PAIR, 0, -1]]), dict(counts=[[1, 2, 3]]),
                   dict(counts=[(1410336, 9308, 292660)]), dict(rank_calls=True),
                   dict(rank_calls=0), dict(boards_per_pair=True), dict(extra='unexpected')]
        for change in invalid:
            response = self.response(); response.update(change)
            with self.subTest(change=change), patch.object(native, '_invoke', return_value=(response, {})):
                with self.assertRaises(ValueError):
                    native.prepare_native_preflop_equities('AsAd', 'KdKs', build_directory='unused')

    def test_rank_validation_before_backend_and_response_shape(self):
        with patch.object(native, '_invoke', side_effect=AssertionError('native started')):
            for hands in ([], ['AsAsKdKs2c'], ['AsKd'], ['AsKdQcJhTs9d8c7s']):
                with self.subTest(hands=hands), self.assertRaises(ValueError):
                    native.rank_native_hands(hands, build_directory='unused')
        for ranks in ([[8, 14, 0, 0, 0, True]], [[9, 14, 0, 0, 0, 0]], [], [[8, 14]], [[8, 15, 0, 0, 0, 0]]):
            with patch.object(native, '_invoke', return_value=({'schema_version': 1, 'mode': 'rank', 'ranks': ranks}, {})):
                with self.assertRaises(ValueError):
                    native.rank_native_hands(['AsKsQsJsTs'], build_directory='unused')

    def test_process_failure_malformed_or_oversize_response_never_falls_back(self):
        manifest = {'executable_sha256': 'digest', 'source_sha256': 'source'}
        def run_with(payload, returncode=0):
            def fake_run(command, **kwargs):
                self.assertEqual(command, ['native-test'])
                kwargs['stdout'].write(payload); kwargs['stderr'].write(b'explicit-error')
                return SimpleNamespace(returncode=returncode)
            return fake_run
        responses = [b'not json', b'[]', b'{"schema_version":true,"mode":"count"}',
                     b'{"schema_version":1,"mode":"rank"}',
                     b'{"schema_version":1,"schema_version":1,"mode":"count"}',
                     b'{"schema_version":1,"mode":"count","value":NaN}',
                     b'x' * (native.MAX_OUTPUT_BYTES + 1)]
        for response in responses:
            with self.subTest(response=response[:40]), patch.object(native, '_backend', return_value=(Path('native-test'), manifest)), \
                    patch.object(native, '_sha', return_value='digest'), patch.object(native, '_source_hashes', return_value=('source', 'lf')), \
                    patch.object(native.subprocess, 'run', side_effect=run_with(response)):
                with self.assertRaises(ValueError): native._invoke('COUNT', [(0, 1, 2, 3)], 'unused')
        with patch.object(native, '_backend', return_value=(Path('native-test'), manifest)), \
                patch.object(native.subprocess, 'run', side_effect=run_with(b'', 2)):
            with self.assertRaisesRegex(RuntimeError, 'explicit-error'):
                native._invoke('COUNT', [(0, 1, 2, 3)], 'unused')
        with patch.object(native, '_backend', return_value=(Path('native-test'), manifest)), \
                patch.object(native.subprocess, 'run', side_effect=subprocess.TimeoutExpired('native-test', 120)):
            with self.assertRaises(subprocess.TimeoutExpired): native._invoke('COUNT', [(0, 1, 2, 3)], 'unused')

    def test_manifest_rejects_changed_source_binary_and_nonlocal_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'own.c'; source.write_bytes(b'owned source\n')
            executable = root / 'native-preflop-equity'; executable.write_bytes(b'not executed')
            with patch.object(native, 'SOURCE', source):
                raw, lf = native._source_hashes()
                manifest = {'schema_version': 1, 'protocol': native.PROTOCOL, 'source_sha256': raw,
                            'source_lf_sha256': lf, 'executable': executable.name,
                            'executable_sha256': native._sha(executable), 'compiler': 'cc',
                            'compiler_version': 'version', 'flags': ['-O3'], 'platform': 'test'}
                path = root / 'native-preflop-manifest.json'
                path.write_text(json.dumps(manifest), encoding='utf-8')
                self.assertTrue(native._backend(root)[0].samefile(executable))
                for key, value in [('source_sha256', 'changed'), ('executable_sha256', 'changed'),
                                   ('executable', '../other'), ('schema_version', True)]:
                    broken = dict(manifest); broken[key] = value
                    path.write_text(json.dumps(broken), encoding='utf-8')
                    with self.subTest(key=key), self.assertRaises(ValueError): native._backend(root)

    def test_missing_compiler_fails_explicitly_without_install_or_fallback(self):
        with patch.object(builder.shutil, 'which', return_value=None), patch.object(builder.subprocess, 'run', side_effect=AssertionError('process started')):
            with self.assertRaisesRegex(RuntimeError, 'compiler unavailable'): builder.build('unused')


class NativeFullBoardIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = os.environ.get('OPENPOKER_NATIVE_BUILD_DIR')
        if not cls.directory:
            raise unittest.SkipTest('OPENPOKER_NATIVE_BUILD_DIR is unset')

    def test_player_role_reversal_swaps_win_loss_counts(self):
        prepared = native.prepare_native_preflop_equities('KdKs', 'AdAs', build_directory=self.directory)
        self.assertEqual(prepared.equities.counts, ((292660, 9308, 1410336),))

    def test_published_physical_counts_and_own_hand_replay(self):
        # The three physical counts were independently exhaustively enumerated
        # in PR125. The fourth is its global c/h image with QQ fixed.
        expected = {('AdAs', 'KdKs'): (1410336, 9308, 292660),
                    ('QdQs', 'AsKh'): (968267, 7226, 736811),
                    ('QdQs', 'AsKc'): (968267, 7226, 736811),
                    ('QdQs', 'KdKs'): (292846, 9336, 1410122)}
        for bb in ('AsKh:.25,KsKd:1', 'AsKh:.125,AsKc:.125,KsKd:1'):
            with self.subTest(bb=bb):
                prepared = native.prepare_native_preflop_equities('AsAd:1,QsQd:.5', bb, build_directory=self.directory)
                table = prepared.equities
                for (i, j, _), row in zip(table.pairs, table.counts):
                    self.assertEqual(row, expected[(''.join(table.hands[0][i]), ''.join(table.hands[1][j]))])
                counts = [{'sb_hand': ''.join(table.hands[0][i]), 'bb_hand': ''.join(table.hands[1][j]),
                           'wins': row[0], 'ties': row[1], 'losses': row[2],
                           'boards': BOARDS_PER_PAIR, 'pair_probability': float(prior)}
                          for (i, j, prior), row in zip(table.pairs, table.counts)]
                for stacks in (2, [3, 2], [2, 3]):
                    config = {'small_blind': .5, 'big_blind': 1, 'starting_stack': stacks}
                    result = solve_prepared_push_fold(table, config=config, iterations=2000)
                    checked = replay(result, 'AsAd:1,QsQd:.5', bb, config, counts)
                    self.assertLessEqual(checked['exploitability'], .005)


if __name__ == '__main__':
    unittest.main()
