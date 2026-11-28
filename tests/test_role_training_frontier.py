"""Exact transport/accounting cliffs, with no physical preparation."""
import unittest
from unittest.mock import patch
from scripts.forecast_role_training_frontier import forecast


class RoleTrainingFrontierTests(unittest.TestCase):
    def test_existing_T2_contract_bridge(self):
        report = forecast((2,)); row = report['rows'][0]
        self.assertEqual(row['u64_ticket_input_bytes'], 3360)
        self.assertEqual(row['hypothetical_packed_ticket_input_bytes'], 2720)
        self.assertEqual(row['canonical_all_snapshot_bytes'], 542272)
        self.assertEqual(row['canonical_all_snapshot_catalog_work'], 11185120)
        self.assertEqual(row['hypothetical_final_compact_output_bytes'], 286016)
        self.assertEqual(report['unchanged_current_request']['reference']['work'], 499975808)
        self.assertFalse(row['complete_future_native_admission'])

    def test_first_transport_width_and_catalog_cliffs(self):
        rows = {r['epochs']: r for r in forecast()['rows']}
        self.assertEqual(rows[3]['u64_ticket_input_bytes'], 5024)
        self.assertEqual(rows[3]['hypothetical_packed_ticket_input_bytes'], 4064)
        self.assertEqual(rows[3]['canonical_all_snapshot_bytes'], 1001720)
        self.assertEqual(rows[3]['hypothetical_final_compact_output_bytes'], 428824)
        self.assertTrue(rows[3]['partial_budget_flags']['current_compact_numeric_widths'])
        self.assertFalse(rows[3]['partial_budget_flags']['current_u64_ticket_input'])
        self.assertFalse(rows[3]['partial_budget_flags']['reference_source_plus_io_accounting'])
        self.assertFalse(rows[4]['partial_budget_flags']['current_compact_numeric_widths'])
        self.assertFalse(rows[4]['partial_budget_flags']['generic_store_geometry'])
        self.assertTrue(rows[5]['partial_budget_flags']['canonical_all_snapshot_catalog'])
        self.assertFalse(rows[6]['partial_budget_flags']['canonical_all_snapshot_catalog'])
        self.assertTrue(rows[8]['partial_budget_flags']['hypothetical_final_snapshot_catalog'])
        self.assertFalse(rows[9]['partial_budget_flags']['hypothetical_final_snapshot_catalog'])
        self.assertFalse(rows[5]['partial_budget_flags']['canonical_all_snapshots_shared_output_ceiling'])
        self.assertTrue(all(not r['complete_future_native_admission'] for r in rows.values()))

    def test_closed_domain_before_accounting_and_no_preparation(self):
        with patch('tests.virtual_role_walk_reference.resources', side_effect=AssertionError('unadmitted accounting')):
            for value in (None, [], (), (True,), (0,), (1000001,), (2, 1), (2, 2), tuple(range(1, 18))):
                with self.assertRaises(ValueError): forecast(value)
        with (patch('tests.virtual_role_walk_reference.build_law', side_effect=AssertionError('law preparation')),
              patch('tests.virtual_role_walk_reference.build_reference_template', side_effect=AssertionError('tree preparation'))):
            self.assertEqual(forecast((2,))['preparation_calls'], 0)


if __name__ == '__main__': unittest.main()
