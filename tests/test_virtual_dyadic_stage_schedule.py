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


if __name__ == '__main__':
    unittest.main()
