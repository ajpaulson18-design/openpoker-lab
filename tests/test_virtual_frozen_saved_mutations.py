from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from fractions import Fraction
from unittest.mock import patch
import unittest
from tests.test_virtual_frozen_probe_protocol import fixture
from tests.test_virtual_frozen_update_comparison import reference
from tests.virtual_frozen_probe_protocol import parse
from tests.virtual_frozen_update_comparison import compare_saved_update
from tests.virtual_frozen_reference_artifact import write_reference
from tests.virtual_frozen_saved_review import saved_reference, replay_plan
from tests.virtual_frozen_saved_mutations import mutate_native, mutate_expected, expected_witness
from tests.virtual_frozen_expectation import ExactExpectation


class SavedMutationTests(unittest.TestCase):
    def test_all_three_native_mutations_pass_parser_and_fail_exact_comparison(self):
        raw = fixture()
        for kind, error in [('regret_denominator', 'exact regret mismatch'),
                            ('average_scale', 'exact average mass mismatch'),
                            ('visible_history', 'full physical row key mismatch')]:
            with self.subTest(kind=kind):
                changed, _ = mutate_native(raw, kind)
                with patch('subprocess.Popen', side_effect=AssertionError('producer forbidden')):
                    parse(changed)
                    with self.assertRaisesRegex(ValueError, error):
                        compare_saved_update(changed, reference())
        self.assertEqual(raw, fixture())

    def test_zero_regret_frame_is_no_denominator_witness(self):
        raw = fixture().replace(b'fold -2 2', b'fold 0 2').replace(b'call 2 2', b'call 0 2')
        self.assertIsNone(mutate_native(raw, 'regret_denominator'))
        self.assertIsNotNone(mutate_native(raw, 'average_scale'))
        with self.assertRaisesRegex(ValueError, 'unknown'):
            mutate_native(raw, 'unknown')

    def test_streamed_expected_mutant_has_valid_checksum_and_changed_value(self):
        with TemporaryDirectory() as temp:
            source, destination = Path(temp) / 'expected.jsonl', Path(temp) / 'mutant.jsonl'
            row = next(iter(reference().rows.values()))
            key = row.key
            row = SimpleNamespace(**vars(row), average_reach_mass=row.average_mass)
            export = write_reference(source, SimpleNamespace(rows={key: row}), 'expected')
            original = source.read_bytes()
            with patch('subprocess.Popen', side_effect=AssertionError('producer forbidden')):
                receipt = mutate_expected(source, destination, key, export['body_sha256'])
                changed = saved_reference(destination, 'expected')
            self.assertEqual(source.read_bytes(), original)
            self.assertNotEqual(receipt['source_body_sha256'], receipt['mutant_body_sha256'])
            self.assertEqual(changed.rows[key].average_reach_mass, Fraction(4, 5))
            self.assertEqual(changed.rows[key].average_action_masses, (Fraction(2, 5), Fraction(2, 5)))
            self.assertEqual(changed.rows[key].regret_masses, row.regret_masses)
            self.assertEqual(receipt['mutant_bytes'], destination.stat().st_size)

    def test_missing_witness_preserves_failed_mutant_and_original(self):
        with TemporaryDirectory() as temp:
            source, destination = Path(temp) / 'expected.jsonl', Path(temp) / 'mutant.jsonl'
            row = next(iter(reference().rows.values()))
            key = row.key
            expected_row = SimpleNamespace(**vars(row), average_reach_mass=row.average_mass)
            export = write_reference(source, SimpleNamespace(rows={key: expected_row}), 'expected')
            original = source.read_bytes()
            with self.assertRaisesRegex(ValueError, 'witness missing'):
                mutate_expected(source, destination, (1, (24, 37), ()), export['body_sha256'])
            self.assertTrue(destination.exists())
            self.assertEqual(source.read_bytes(), original)

    def test_terminal_witness_rejects_partial_owner_and_peak_remains_within_cap(self):
        owner = ExactExpectation('uniform')
        with self.assertRaisesRegex(ValueError, 'complete unfinished accumulator'):
            expected_witness(owner, None, None, None)
        self.assertFalse(owner._closed)
        self.assertLessEqual(replay_plan()['q_free_witness_peak_entries'], 16_000_000)


if __name__ == '__main__':
    unittest.main()
