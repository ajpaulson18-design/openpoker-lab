"""Synthetic independent timeline vectors and fail-closed profile mutations."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.verify_training_phase_profile import MAX_PROFILE_BYTES, load_profile, verify_profile


def fixture():
    admission = dict(ten_card=True, bounded_division=True, requested_sweeps=2,
                     rows=119_196, slots=281_066, factored_composed_work=1_902_260_898,
                     factored_composed_entries=374_708, factored_composed_payload_bits=20_958_080)
    events = [dict(phase='plan_preflight', edge='begin', sweep=0, ns=10),
              dict(phase='plan_preflight', edge='end', sweep=0, ns=20)]
    timeline = [('chance_setup', 0), ('owners_setup', 0), ('row_registration', 0),
                ('freeze', 0), ('prelude', 0)]
    for sweep in (1, 2):
        timeline += [(phase, sweep) for phase in
                     ('policy_build', 'policy_emit', 'walk', 'commit', 'checkpoint')]
    timeline += [('average_export', 0), ('footer', 0)]
    for index, (phase, sweep) in enumerate(timeline):
        events += [dict(phase=phase, edge='begin', sweep=sweep, ns=50+10*index),
                   dict(phase=phase, edge='end', sweep=sweep, ns=54+10*index)]
    record = dict(version=1, clock='steady_clock', units='nanoseconds',
                  scope='ten-card-bounded-division-T2', profile_status='complete',
                  diagnostics=dict(capacity=64, event_count=36, clock_reads=43,
                                   max_clock_reads=80, metadata_bytes=1536,
                                   metadata_bytes_reserved=2048, metadata_entries_reserved=256,
                                   work_allowance=8192, failed=False),
                  budgets=dict(solver_work=1_902_260_898, with_profile_work=1_902_269_090,
                               solver_entries=374_708, with_profile_entries=374_964,
                               solver_payload_bits=20_958_080, with_profile_payload_bits=20_974_464),
                  outer=dict(driver_begin_ns=5, driver_end_ns=30, train_begin_ns=40,
                             train_end_ns=230, receipts_begin_ns=240, receipts_end_ns=260),
                  events=events)
    return record, admission


class TrainingPhaseProfileTests(unittest.TestCase):
    def test_known_timeline_partitions_without_double_counting_preflight(self):
        record, admission = fixture()
        result = verify_profile(record, admission)
        self.assertEqual((result['measured_interval_ns'], result['driver_inclusive_ns'],
                          result['plan_preflight_ns'], result['driver_other_ns']), (255, 25, 10, 15))
        self.assertEqual((result['train_inclusive_ns'], result['train_leaf_ns'],
                          result['train_residual_ns'], result['probe_outputs_ns'],
                          result['unattributed_outside_ns']), (190, 68, 122, 20, 20))
        self.assertEqual(sum(part['numerator'] for part in result['fractions_of_measured'].values()), 255)
        self.assertTrue(all(part['denominator'] == 255 for part in result['fractions_of_measured'].values()))
        self.assertEqual([(p['phase'], p['sweep']) for p in result['phases'] if p['phase'] == 'walk'],
                         [('walk', 1), ('walk', 2)])
        self.assertEqual(result['native_producer_calls'], 0)
        self.assertEqual((result['measured_begin_ns'], result['measured_end_ns']), (5, 260))
        self.assertIn('Driver destruction and process exit', result['exclusions'])
        self.assertEqual(record, fixture()[0])

    def test_equal_clock_ticks_are_valid(self):
        record, admission = fixture()
        record['events'][3]['ns'] = record['events'][2]['ns']
        result = verify_profile(record, admission)
        self.assertEqual(result['phases'][1]['ns'], 0)
        self.assertEqual(result['train_leaf_ns'], 64)

    def test_budgets_derive_from_supplied_admission(self):
        record, admission = fixture()
        for name, key in (('work', 'factored_composed_work'),
                          ('entries', 'factored_composed_entries'),
                          ('payload_bits', 'factored_composed_payload_bits')):
            admission[key] += 100
            record['budgets']['solver_'+name] += 100
            record['budgets']['with_profile_'+name] += 100
        verify_profile(record, admission)
        for key in admission.keys()-{'ten_card', 'bounded_division'}:
            bad = copy.deepcopy(admission)
            bad[key] += 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_profile(record, bad)

    def test_phase_order_sweeps_edges_and_event_census(self):
        record, admission = fixture()
        for index, key, value in ((2, 'phase', 'freeze'), (12, 'sweep', 2),
                                  (13, 'edge', 'begin'), (0, 'sweep', 1),
                                  (34, 'phase', 'average_export')):
            bad = copy.deepcopy(record)
            bad['events'][index][key] = value
            with self.subTest(index=index, key=key), self.assertRaises(ValueError):
                verify_profile(bad, admission)
        for count in (0, 35, 37):
            bad = copy.deepcopy(record)
            bad['events'] = (bad['events']+[bad['events'][-1]])[:count]
            with self.subTest(count=count), self.assertRaises(ValueError):
                verify_profile(bad, admission)

    def test_nonmonotonic_nested_and_outside_owner_intervals(self):
        record, admission = fixture()
        for index, value in ((1, 9), (4, 53), (0, 4), (1, 31), (2, 39), (35, 231)):
            bad = copy.deepcopy(record)
            bad['events'][index]['ns'] = value
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                verify_profile(bad, admission)
        for key, value in (('driver_end_ns', 50), ('train_end_ns', 210),
                           ('receipts_begin_ns', 229), ('receipts_end_ns', 239)):
            bad = copy.deepcopy(record)
            bad['outer'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_profile(bad, admission)

    def test_diagnostic_caps_counts_failure_and_underreservation(self):
        record, admission = fixture()
        for key, value in (('capacity', 63), ('event_count', 35), ('clock_reads', 44),
                           ('max_clock_reads', 81), ('metadata_bytes', 2049),
                           ('metadata_bytes_reserved', 2047), ('metadata_entries_reserved', 255),
                           ('work_allowance', 8191), ('failed', True)):
            bad = copy.deepcopy(record)
            bad['diagnostics'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_profile(bad, admission)
        for key in record['budgets']:
            bad = copy.deepcopy(record)
            bad['budgets'][key] -= 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_profile(bad, admission)

    def test_composed_hard_caps(self):
        record, admission = fixture()
        for name, key, cap, extra in (
            ('work', 'factored_composed_work', 2_150_000_000, 8192),
            ('entries', 'factored_composed_entries', 2_000_000, 256),
            ('payload_bits', 'factored_composed_payload_bits', 1_200_000_000, 16384),
        ):
            bad, bad_admission = copy.deepcopy(record), dict(admission)
            bad_admission[key] = cap-extra+1
            bad['budgets']['solver_'+name] = cap-extra+1
            bad['budgets']['with_profile_'+name] = cap+1
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify_profile(bad, bad_admission)

    def test_exact_schemas_reject_missing_and_unknown_fields(self):
        record, admission = fixture()
        for container in ((), ('diagnostics',), ('budgets',), ('outer',), ('events', 0)):
            for operation in ('add', 'remove'):
                bad = copy.deepcopy(record)
                target = bad
                for key in container:
                    target = target[key]
                if operation == 'add':
                    target['unknown'] = 0
                else:
                    del target[next(iter(target))]
                with self.subTest(container=container, operation=operation), self.assertRaises(ValueError):
                    verify_profile(bad, admission)

    def test_strict_numbers_reject_boolean_float_negative_and_nonfinite(self):
        record, admission = fixture()
        paths = [('version',), ('events', 0, 'sweep'), ('events', 0, 'ns')]
        paths += [('diagnostics', key) for key in record['diagnostics'] if key != 'failed']
        paths += [('budgets', key) for key in record['budgets']]
        paths += [('outer', key) for key in record['outer']]
        for path in paths:
            for value in (True, 1.0, -1, float('nan'), float('inf'), 1 << 64):
                bad = copy.deepcopy(record)
                target = bad
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                    verify_profile(bad, admission)
        for key in ('requested_sweeps', 'rows', 'slots', 'factored_composed_work',
                    'factored_composed_entries', 'factored_composed_payload_bits'):
            bad_admission = dict(admission, **{key: True})
            with self.subTest(admission=key), self.assertRaises(ValueError):
                verify_profile(record, bad_admission)

    def test_file_byte_limit_is_checked_before_json_parse(self):
        with TemporaryDirectory(prefix='phase-profile-') as temp:
            path = Path(temp)/'profile.json'
            path.write_bytes(b' '* (MAX_PROFILE_BYTES+1))
            with patch('scripts.verify_training_phase_profile.json.loads', side_effect=AssertionError('parsed')):
                with self.assertRaises(ValueError):
                    load_profile(path)
            path.write_bytes(b'')
            with self.assertRaises(ValueError):
                load_profile(path)

    def test_json_rejects_duplicates_nonfinite_and_malformed_records(self):
        with TemporaryDirectory(prefix='phase-profile-') as temp:
            path = Path(temp)/'profile.json'
            for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{'):
                path.write_bytes(raw)
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    load_profile(path)
            record, admission = fixture()
            path.write_text(json.dumps(record), encoding='utf-8')
            self.assertEqual(verify_profile(load_profile(path), admission), verify_profile(record, admission))


if __name__ == '__main__':
    unittest.main()
