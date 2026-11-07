import unittest
from fractions import Fraction
from tests.virtual_frozen_study_admission import (
    census_study_admission, proposal_shape, WORST_BOARD,
    MAX_RAW_NATIVE_BYTES, MAX_NATIVE_WORK,
)
from tests.virtual_frozen_probe_protocol import MAX_BYTES

class StudyAdmissionTests(unittest.TestCase):
    def test_complete_two_law_census_without_updates(self):
        r = census_study_admission()
        self.assertEqual(r['context_setup_count'], 1)
        self.assertEqual(r['native_eval_calls'], 0)
        self.assertEqual(r['reference_update_calls'], 0)
        self.assertEqual(r['native_requested_work_upper'], 5042 * 500_000_000)
        self.assertEqual(r['native_raw_output_bytes_upper'], 5042 * MAX_BYTES)
        for law in r['laws'].values():
            self.assertEqual(law['calls'], 2520)
            self.assertEqual(law['row_records'], 107080)
            self.assertEqual(law['proposal_prefixes'], 3109)
            self.assertEqual(law['rank_calls_upper'], 120)
    def test_other_laws_and_decks_reject(self):
        deck = (16,17,24,32,33,35,37,43,48)
        with self.assertRaises(ValueError):
            proposal_shape(WORST_BOARD, 'selected', deck)
        with self.assertRaises(ValueError):
            proposal_shape(WORST_BOARD, 'uniform', tuple(range(9)))
        with self.assertRaises(ValueError):
            proposal_shape((17,16,24,32,48), 'uniform', deck)
    def test_unreduced_widths_are_preserved(self):
        deck = (16,17,24,32,33,35,37,43,48)
        ratios = proposal_shape(WORST_BOARD, 'river_weighted', deck)
        self.assertEqual(ratios, ((1,1), (195,12600), (35,12600), (9,12600)))
        self.assertGreater(ratios[1][0].bit_length(), Fraction(*ratios[1]).numerator.bit_length())

if __name__ == '__main__':
    unittest.main()
