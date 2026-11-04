from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
import json
import unittest
from tests.test_virtual_frozen_probe_protocol import fixture, BOARD
from tests.test_virtual_frozen_update_comparison import reference
from tests.virtual_frozen_reference_artifact import write_reference, read_reference, artifact_allowance
from tests.virtual_frozen_saved_review import (canonical_boards, read_call, digest, metadata,
    _bootstrap, check_export, replay_plan, replay_saved_numeric, observed_success)
from tests.virtual_frozen_saved_review import read_observation, saved_reference, unlinked_path
from tests.virtual_frozen_saved_review import bounded_inventory, check_plan


class SavedReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def call(self):
        from tests.virtual_frozen_probe_protocol import request
        directory = self.root / 'call'
        directory.mkdir()
        requested = request('EVAL', 'UNIFORM', BOARD)
        (directory / 'request.bin').write_bytes(requested)
        (directory / 'stdout.bin').write_bytes(fixture())
        (directory / 'stderr.bin').write_bytes(b'')
        receipt = {'version': 'bounded-child-observation-v1', 'status': 'exited',
                   'returncode': 0, 'actual_exit_observed': True, 'automatic_retries': 0,
                   'failures': [], 'request_sha256': digest(requested),
                   'streams': [{'observed_bytes': len(raw), 'saved_bytes': len(raw),
                                'sha256': digest(raw)} for raw in (fixture(), b'')]}
        self.put(directory / 'process.json', receipt)
        return directory, receipt

    def put(self, path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def test_complete_enumeration_without_preparation_or_processes(self):
        with patch('subprocess.Popen', side_effect=AssertionError('producer/process forbidden')):
            boards = tuple(canonical_boards())
        self.assertEqual(len(boards), 2520)
        self.assertEqual(len(set(boards)), 2520)
        self.assertEqual(boards[0], BOARD)
        self.assertEqual(boards[-1], (37, 43, 48, 35, 33))
        self.assertTrue(all(b[0] < b[1] < b[2] and len(set(b)) == 5 for b in boards))
        self.assertEqual(replay_plan()['native_producer_calls'], 0)

    def test_real_framing_saved_observation_never_launches(self):
        call, _ = self.call()
        with patch('subprocess.Popen', side_effect=AssertionError('producer/process forbidden')):
            raw, result = read_call(call, 'EVAL', 'UNIFORM', BOARD)
        self.assertEqual(raw, fixture())
        self.assertEqual(result['status'], 'COMPLETE')

    def test_exit_and_request_mutations_reject(self):
        call, receipt = self.call()
        for field, value in [('actual_exit_observed', False), ('returncode', 1),
                             ('returncode', False), ('failures', ['stream_limit']),
                             ('status', 'timeout'), ('automatic_retries', 1),
                             ('request_sha256', '0' * 64)]:
            with self.subTest(field=field, value=value):
                self.put(call / 'process.json', {**receipt, field: value})
                with self.assertRaises(ValueError):
                    read_call(call, 'EVAL', 'UNIFORM', BOARD)
        self.put(call / 'process.json', receipt)
        (call / 'request.bin').write_bytes(b'wrong request\n')
        with self.assertRaisesRegex(ValueError, 'canonical request'):
            read_call(call, 'EVAL', 'UNIFORM', BOARD)

    def test_stream_drift_and_consistently_recorded_stderr_reject(self):
        call, receipt = self.call()
        (call / 'stdout.bin').write_bytes(fixture() + b'end\n')
        with self.assertRaisesRegex(ValueError, 'stream size/digest'):
            read_call(call, 'EVAL', 'UNIFORM', BOARD)
        (call / 'stdout.bin').write_bytes(fixture())
        (call / 'stderr.bin').write_bytes(b'error')
        receipt['streams'][1] = {'observed_bytes': 5, 'saved_bytes': 5, 'sha256': digest(b'error')}
        self.put(call / 'process.json', receipt)
        with self.assertRaisesRegex(ValueError, 'stderr is nonempty'):
            read_call(call, 'EVAL', 'UNIFORM', BOARD)

    def test_build_observation_empty_request_is_checked_without_parsing(self):
        call, receipt = self.call()
        (call / 'request.bin').write_bytes(b'')
        receipt['request_sha256'] = digest(b'')
        self.put(call / 'process.json', receipt)
        with patch('subprocess.Popen', side_effect=AssertionError('rebuild forbidden')):
            self.assertEqual(read_observation(call, b''), [fixture(), b''])
        self.put(call / 'process.json', {**receipt, 'actual_exit_observed': False})
        with self.assertRaisesRegex(ValueError, 'successful exit'):
            read_observation(call, b'')

    def test_reparse_reference_and_call_parent_reject_before_codec(self):
        path = self.root / 'ref.jsonl'
        write_reference(path, reference(), 'sampled')
        original = Path.lstat
        for linked in (path, self.root):
            def info(candidate):
                value = original(candidate)
                return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=1024) if candidate == linked else value
            with self.subTest(linked=str(linked)):
                with patch.object(Path, 'lstat', autospec=True, side_effect=info):
                    with patch('tests.virtual_frozen_saved_review.read_reference', side_effect=AssertionError('codec entered')):
                        with self.assertRaisesRegex(ValueError, 'linked/reparse'):
                            saved_reference(path, 'sampled')

    def test_export_receipt_drift(self):
        path = self.root / 'ref.jsonl'
        receipt = write_reference(path, reference(), 'sampled')
        saved = read_reference(path, byte_limit=artifact_allowance('sampled', 868, 2078)['bytes'])
        check_export(saved, receipt)
        for field, value in [('bytes', receipt['bytes'] + 1), ('body_sha256', '0' * 64), ('slots', 1)]:
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, 'semantic export receipt'):
                    check_export(saved, {**receipt, field: value})

    def test_bootstrap_final_receipt_and_exact_compiled_bytes_required(self):
        root = self.root.resolve()
        script = 'scripts/run_virtual_frozen_source_only.py'
        stage, identity = 'trusted code', 'a' * 64
        source = {'files': {script: {'raw_sha256': identity}}}
        boot = {'version': 'project-source-only-bootstrap-v1', 'root': str(root),
                'entry_module': 'study', 'compiled': {script: identity},
                'trusted_first_stage': {'bootstrap_path': str(root / script),
                    'bootstrap_sha256': identity, 'command_sha256': digest(stage.encode())},
                'interpreter': {'isolated': 1, 'no_site': 1, 'dont_write_bytecode': True, 'optimize': 0},
                'initial_cache_scan': {'project_bytecode_files': 0},
                'final_cache_scan': {'project_bytecode_files': 0}}
        _bootstrap(boot, source, root, stage, identity, 'study')
        for field, value in [('root', str(root / 'elsewhere')), ('entry_module', 'unittest'),
                             ('compiled', {script: 'b' * 64}), ('compiled', {}),
                             ('final_cache_scan', {}), ('trusted_first_stage', {})]:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    _bootstrap({**boot, field: value}, source, root, stage, identity, 'study')

    def test_incomplete_q_free_corpus_rejects_without_any_producer(self):
        row = next(iter(reference().rows.values()))
        key = row.key
        row = SimpleNamespace(**vars(row), average_reach_mass=row.average_mass)
        expected = SimpleNamespace(rows={key: row})
        write_reference(self.root / 'expected.jsonl', expected, 'expected')
        with patch('subprocess.Popen', side_effect=AssertionError('producer/process forbidden')):
            with self.assertRaisesRegex(ValueError, 'complete q-free'):
                replay_saved_numeric(self.root, {})

    def test_duplicate_nonfinite_oversize_metadata_and_missing_exit_reject(self):
        path = self.root / 'receipt.json'
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '[]'):
            with self.subTest(raw=raw):
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    metadata(path)
        path.write_bytes(b'x' * 11)
        with self.assertRaisesRegex(ValueError, 'bound/link'):
            metadata(path, cap=10)
        with self.assertRaises(ValueError):
            observed_success({'returncode': 0, 'failures': []})

    def test_whole_inventory_rejects_total_bytes_before_loading(self):
        (self.root / 'one.bin').write_bytes(b'a' * 10)
        nested = self.root / 'nested'
        nested.mkdir()
        (nested / 'two.bin').write_bytes(b'b' * 10)
        self.assertEqual(bounded_inventory(self.root, 20), {'nodes': 3, 'files': 2, 'bytes': 20})
        with self.assertRaisesRegex(ValueError, 'total byte admission'):
            bounded_inventory(self.root, 19)

    def test_saved_plan_and_cumulative_receipt_must_keep_original_caps(self):
        from tests.virtual_frozen_whole_study import LIMITS, FILE_FAMILIES
        from tests.virtual_frozen_reference_artifact import reference_study_allowance
        families = {**FILE_FAMILIES, 'reference_artifacts': reference_study_allowance()['all_reference_artifact_bytes_upper']}
        families['archive_with_headers_upper'] = sum(families.values()) + (128 << 20)
        uses = {name: 1 for name in LIMITS}
        uses['artifact_bytes'] = sum(families.values())
        plan = {'version': 'virtual-frozen-whole-study-admission-v1', 'native_eval_requests': 5040,
                'native_admit_requests': 2, 'limits': dict(LIMITS), 'uses': uses, 'file_families': families}
        result = {'numeric_reserved': {name: 0 for name in uses},
                  'files_reserved': {name: 0 for name in families}}
        check_plan(plan, result)
        with self.assertRaisesRegex(ValueError, 'cumulative allowance exceeded'):
            check_plan(plan, {**result, 'numeric_reserved': {**result['numeric_reserved'], 'native_work': 2}})
        with self.assertRaisesRegex(ValueError, 'unchanged saved resource plan'):
            check_plan({**plan, 'limits': {**LIMITS, 'native_work': LIMITS['native_work'] + 1}}, result)
        with self.assertRaisesRegex(ValueError, 'file allowances'):
            check_plan({**plan, 'file_families': {**families, 'unbounded': 1 << 50}}, result)


if __name__ == '__main__':
    unittest.main()
