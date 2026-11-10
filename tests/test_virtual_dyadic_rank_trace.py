"""Fixed controls for independent rank-free cache schedules."""
import unittest
from tests.virtual_dyadic_rank_trace import rank_trace


class RankTraceTests(unittest.TestCase):
    def test_named_ten_card_trace(self):
        r=rank_trace()
        self.assertEqual((r['queries'],r['searches'],r['cache_hits'],r['cache_misses'],r['cache_evictions']),
                         (412080,79560,412063,17,0))
        self.assertEqual((r['entries'],r['lookup_work'],r['update_work'],r['setup_work'],r['parent_cache_lookup_work']),
                         (66,3500640,4216,84,4331258))
        self.assertEqual((r['native_calls'],r['rank_calls']),(0,0))

    def test_named_eleven_card_trace(self):
        r=rank_trace(eleven_card=True)
        self.assertEqual((r['queries'],r['searches'],r['cache_hits'],r['cache_misses'],r['cache_evictions']),
                         (1357440,262080,1357384,56,0))
        self.assertEqual((r['entries'],r['lookup_work'],r['update_work'],r['setup_work'],r['parent_cache_lookup_work']),
                         (144,13628160,32256,240,16391422))
        self.assertEqual((r['native_calls'],r['rank_calls']),(0,0))

    def test_fixture_flag_must_be_boolean(self):
        with self.assertRaises(ValueError):
            rank_trace(eleven_card=1)


if __name__=='__main__':
    unittest.main()
