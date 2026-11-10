"""Focused Q32 controller admission and independent schedule controls."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from tests.virtual_dyadic_stage_schedule import stage_schedule
from tests.virtual_dyadic_directory_trace import directory_trace
from tests.virtual_frozen_run_control import run_bounded_child, run_bounded_quality32_replay


class Quality32CohortTests(unittest.TestCase):
    def test_exact_schedule(self):
        q=stage_schedule(virtual_zero=True,sweeps=32,batch_rows=True,quality32=True)
        self.assertEqual((q['average_words'],q['regret_words'],q['written_words'],
                          q['physical_read_words'],q['logical_read_calls']+32*q['per_sweep_stage_calls']),
                         (258694,348036,19415360,30657954,3931620))
        d=directory_trace(ten_card=False,sweeps=32,quality32=True)
        self.assertEqual((d['logical_reads'],d['misses']),(3174600,18942))

    def test_named_profile_only(self):
        for kwargs in ({'sweeps':32,'virtual_zero':True,'batch_rows':True},
                       {'sweeps':31,'virtual_zero':True,'batch_rows':True,'quality32':True},
                       {'sweeps':32,'virtual_zero':False,'batch_rows':True,'quality32':True},
                       {'sweeps':32,'virtual_zero':True,'batch_rows':False,'quality32':True},
                       {'sweeps':32,'virtual_zero':True,'batch_rows':True,'quality32':1}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):stage_schedule(**kwargs)
        with self.assertRaises(ValueError):directory_trace(ten_card=False,sweeps=32)

    def test_generic_timeout_unchanged(self):
        with TemporaryDirectory() as tmp:
            out=Path(tmp)/'not-created'
            with self.assertRaises(ValueError):run_bounded_child(['python'],b'',out,stdout_limit=1,timeout=900)
            self.assertFalse(out.exists())

    def test_named_replay_command_preflight(self):
        command=['python','--module','scripts.verify_virtual_dyadic_training','--saved','saved.bin','--proof9-quality32']
        with patch('tests.virtual_frozen_run_control._run_streamed_child',return_value='observed') as observe:
            self.assertEqual(run_bounded_quality32_replay(command,b'',Path('unused')),'observed')
            self.assertEqual(observe.call_args.kwargs['timeout'],900)
        for changed,request in ((command,b'x'),(command+['--row-batched'],b''),
                                (['python','--module','other','--saved','x','--proof9-quality32'],b'')):
            with self.assertRaises(ValueError):run_bounded_quality32_replay(changed,request,Path('unused'))


if __name__=='__main__':unittest.main()
