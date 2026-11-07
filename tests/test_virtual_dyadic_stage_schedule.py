"""Fixed-fixture guards for the independent stage-schedule oracle."""
import unittest
from tests.virtual_dyadic_stage_schedule import stage_schedule


class StageScheduleTests(unittest.TestCase):
    def test_nine_card_complete_coverage_and_call_counts(self):
        actual = stage_schedule()
        self.assertEqual((actual['direct_write_calls'], actual['batched_write_calls'], actual['written_words']),
                         (232805, 4103, 1820190))

    def test_ten_card_complete_coverage_and_call_counts(self):
        actual = stage_schedule(ten_card=True)
        self.assertEqual((actual['direct_write_calls'], actual['batched_write_calls'], actual['written_words']),
                         (1124988, 19560, 8888166))

    def test_virtual_zero_epochs(self):
        for ten_card, expected in ((False, (306, 1242654, 3954, 1213460)),
                                   (True, (1498, 6130244, 18836, 5925444))):
            with self.subTest(ten_card=ten_card):
                actual = stage_schedule(ten_card=ten_card, virtual_zero=True)
                self.assertEqual((actual['cache_misses'], actual['physical_read_words'],
                                  actual['batched_write_calls'], actual['written_words']), expected)
                self.assertEqual(actual['read_epochs'][0]['cache_misses'], 0)
                self.assertEqual(actual['read_epochs'][1]['cache_misses'], 0)
                self.assertEqual(actual['initialization_calls'], 0)


if __name__ == '__main__':
    unittest.main()
