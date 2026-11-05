from pathlib import Path
import json,sys,tempfile,unittest,os
from tests.virtual_frozen_run_control import RunClaim,run_bounded_child,run_bounded_probe_batch

class RunControlTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd().parent);self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def command(self,code):return [sys.executable,'-B','-c',code]
    def test_exclusive_claim_and_terminal_receipt_never_overwrite(self):
        path=self.root/'claim';claim=RunClaim(path,'a'*40);raw=(path/'claim.json').read_bytes()
        self.assertEqual(json.loads(raw)['controller_pid'],os.getpid())
        with self.assertRaises(FileExistsError):RunClaim(path,'b'*40)
        claim.finish('failed',{'first_error':'preserved'})
        with self.assertRaises(ValueError):claim.finish('complete',{})
        self.assertEqual((path/'claim.json').read_bytes(),raw)
        self.assertEqual(json.loads((path/'terminal.json').read_bytes())['status'],'failed')
    def test_actual_exit_and_request_stdout_stderr_are_saved(self):
        path=self.root/'child'
        receipt=run_bounded_child(self.command('import sys;sys.stdout.buffer.write(sys.stdin.buffer.read());sys.stderr.write("evidence");sys.exit(7)'),b'request\n',path,stdout_limit=64)
        self.assertEqual(receipt['status'],'exited');self.assertEqual(receipt['returncode'],7)
        self.assertTrue(receipt['actual_exit_observed']);self.assertEqual(receipt['automatic_retries'],0)
        self.assertEqual((path/'stdout.bin').read_bytes(),b'request\n')
        self.assertEqual((path/'stderr.bin').read_bytes(),b'evidence')
        with self.assertRaises(FileExistsError):run_bounded_child(self.command('pass'),b'',path,stdout_limit=64)
    def test_output_overflow_is_killed_and_saved_prefix_stays_bounded(self):
        path=self.root/'overflow'
        receipt=run_bounded_child(self.command('import sys,time;sys.stdout.buffer.write(b"x"*1000000);sys.stdout.flush();time.sleep(5)'),b'',path,stdout_limit=16,timeout=5)
        self.assertEqual(receipt['status'],'stream_failure')
        self.assertIn('stdout_limit',receipt['failures'])
        self.assertEqual((path/'stdout.bin').stat().st_size,16)
        self.assertTrue(receipt['actual_exit_observed'])
    def test_timeout_observes_termination_and_retains_receipt(self):
        path=self.root/'timeout'
        receipt=run_bounded_child(self.command('import time;time.sleep(5)'),b'',path,stdout_limit=16,timeout=.05)
        self.assertEqual(receipt['status'],'timeout');self.assertIsNotNone(receipt['returncode'])
        self.assertTrue(receipt['actual_exit_observed']);self.assertTrue((path/'process.json').exists())
    def test_batch_admits_multiple_records_without_raising_single_request_cap(self):
        raw=(b'q'*599+b'\n')*4
        with self.assertRaisesRegex(ValueError,'bounded child request'):
            run_bounded_child(self.command('pass'),raw,self.root/'single',stdout_limit=64)
        self.assertFalse((self.root/'single').exists())
        path=self.root/'batch'
        observed=run_bounded_probe_batch(self.command('import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())'),raw,path)
        self.assertEqual(observed['status'],'exited');self.assertEqual(observed['returncode'],0)
        self.assertEqual((path/'stdout.bin').read_bytes(),raw)
        self.assertEqual(json.loads((path/'batch-contract.json').read_bytes())['records'],4)
    def test_batch_input_bounds_reject_before_process_or_directory(self):
        from unittest.mock import patch
        bad=[b'',b'q\n'*129,(b'q'*599+b'\n')*128,b'q'*1025+b'\n',b'bad\r\n',b'\0\n']
        with patch('tests.virtual_frozen_run_control.subprocess.Popen') as start:
            for index,raw in enumerate(bad):
                path=self.root/('invalid-'+str(index))
                with self.assertRaises(ValueError):run_bounded_probe_batch(self.command('pass'),raw,path)
                self.assertFalse(path.exists())
            start.assert_not_called()
    def test_batch_output_overflow_is_bounded_while_streaming(self):
        path=self.root/'batch-overflow'
        observed=run_bounded_probe_batch(self.command('import sys,time;sys.stdout.buffer.write(b"x"*3000000);sys.stdout.flush();time.sleep(5)'),b'q\n',path)
        self.assertEqual(observed['status'],'stream_failure')
        self.assertIn('stdout_limit',observed['failures'])
        self.assertEqual((path/'stdout.bin').stat().st_size,2100000)
        self.assertTrue(observed['actual_exit_observed'])

if __name__ == '__main__':unittest.main()
