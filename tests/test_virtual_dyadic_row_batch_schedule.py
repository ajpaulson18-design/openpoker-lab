"""Independent row-batched pager schedule controls."""
import unittest
from tests.virtual_dyadic_stage_schedule import stage_schedule


class RowBatchScheduleTests(unittest.TestCase):
    def test_frozen_ten_card_virtual_zero_ledger(self):
        s=stage_schedule(ten_card=True,virtual_zero=True,batch_rows=True)
        self.assertEqual((s['rows'],s['slots'],s['logical_read_calls'],s['logical_read_words']),
                         (119196,281066,834372,10555076))
        self.assertEqual((s['virtual_read_calls'],s['virtual_read_words'],s['cache_hits'],
                          s['cache_misses'],s['physical_read_words']),
                         (357588,4629632,476612,1498,6130244))
        self.assertEqual((s['per_sweep_stage_calls'],s['per_sweep_dirty_runs'],
                          s['batched_write_calls'],s['written_words']),
                         (238392,9418,18836,5925444))
        self.assertEqual(s['logical_read_calls']+2*s['per_sweep_stage_calls'],1311156)
        self.assertEqual([p['cache_misses'] for p in s['read_epochs']],[0,0,408,773,317])

    def test_two_dirty_pages_preserve_extent_coverage(self):
        for eleven, expected in ((False, (2390, 5925444, 1495, 6115174)),
                                 (True, (8040, 19448404, 5026, 20578900))):
            with self.subTest(eleven_card=eleven):
                schedule = stage_schedule(ten_card=not eleven, eleven_card=eleven, virtual_zero=True,
                                          batch_rows=True, zero_policy_bootstrap=True,
                                          initial_packed_stage=True, read_pages=7, dirty_pages=2)
                self.assertEqual(tuple(schedule[name] for name in
                                       ('batched_write_calls', 'written_words',
                                        'cache_misses', 'physical_read_words')), expected)

    def test_rejects_unmodeled_profiles(self):
        for arguments in ({'batch_rows':True},{'batch_rows':True,'ten_card':True},
                          {'batch_rows':True,'ten_card':True,'virtual_zero':True,'sweeps':3},
                          {'batch_rows':1,'ten_card':True,'virtual_zero':True}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                stage_schedule(**arguments)


if __name__ == '__main__':
    unittest.main()
