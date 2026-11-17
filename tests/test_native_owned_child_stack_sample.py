"""Executed Windows owned-child controls with independent raw-report validation."""
import os
from pathlib import Path
import tempfile
import unittest
from tests.test_native_exact_reach import authenticate
from tests.virtual_frozen_run_control import run_bounded_child
from scripts.verify_owned_child_stack_sample import load_report, verify_report
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.name=="nt" and os.environ.get("OPENPOKER_NATIVE_OWNED_CHILD_SAMPLE_CONTROLS_EXE"),
                     "explicit Windows x64 owned-child controls required")
class NativeOwnedChildStackControls(unittest.TestCase):
    def test_actual_child_lifecycle_stack_caps_and_failure_evidence(self):
        exe=Path(os.environ["OPENPOKER_NATIVE_OWNED_CHILD_SAMPLE_CONTROLS_EXE"]).resolve()
        identity=authenticate(exe,ROOT,"owned-child-stack-sample-controls")
        configured=os.environ.get("OPENPOKER_NATIVE_OWNED_CHILD_SAMPLE_CONTROL_DIR")
        if configured:
            artifacts=Path(configured).resolve()
        else:
            base=Path(tempfile.mkdtemp(prefix="owned-child-controls-")).resolve()
            artifacts=base/"artifacts"
        self.assertFalse(artifacts.exists(),"native control artifacts must be fresh")
        process=artifacts.parent/(artifacts.name+"-process")
        self.assertFalse(process.exists(),"native control process output must be fresh")
        old=os.environ.get("OPENPOKER_NATIVE_OWNED_CHILD_SAMPLE_CONTROL_DIR")
        os.environ["OPENPOKER_NATIVE_OWNED_CHILD_SAMPLE_CONTROL_DIR"]=str(artifacts)
        try:
            observed=run_bounded_child([str(exe)],b"",process,stdout_limit=65536,timeout=90)
        finally:
            if old is None:
                os.environ.pop("OPENPOKER_NATIVE_OWNED_CHILD_SAMPLE_CONTROL_DIR",None)
            else:
                os.environ["OPENPOKER_NATIVE_OWNED_CHILD_SAMPLE_CONTROL_DIR"]=old
        self.assertTrue(observed["actual_exit_observed"])
        self.assertEqual(observed["automatic_retries"],0)
        self.assertEqual(observed["failures"],[])
        self.assertEqual(observed["returncode"],0,f"raw controls preserved at {artifacts} and {process}")
        self.assertEqual((process/"stdout.bin").read_bytes(),b"OWNED_CHILD_STACK_SAMPLE_CONTROLS PASS\r\n")
        self.assertEqual((process/"stderr.bin").read_bytes(),b"")
        summaries={}
        for name,mode,code in (("enabled","periodic_stack_observation",0),
                               ("disabled","disabled",0),("failed","periodic_stack_observation",7)):
            record=load_report(artifacts/(name+"-report.json"))
            summaries[name]=verify_report(record,str(exe),mode,code)
        self.assertGreaterEqual(summaries["enabled"]["sample_count"],2)
        self.assertGreaterEqual(max(summaries["enabled"]["sample_depths"]),2)
        self.assertEqual(summaries["disabled"]["sample_count"],0)
        failed=load_report(artifacts/"assignment-failure-report.json")
        self.assertEqual(failed["status"],"failed")
        self.assertTrue(failed["child_launched"])
        self.assertFalse(failed["job_assigned"])
        self.assertFalse(failed["initial_thread_resumed"])
        self.assertTrue(failed["termination_attempted"])
        self.assertTrue(failed["termination_succeeded"])
        self.assertTrue(failed["cleanup_exit_observed"])
        self.assertEqual(failed["cleanup_exit_code"],126)
        terminal=load_report(artifacts/"terminal-hot-report.json")
        terminal_summary=verify_report(terminal,str(exe),"periodic_stack_observation",0)
        self.assertEqual(terminal_summary["sampling_attempts"],1)
        self.assertEqual(terminal_summary["exit_race_event_count"],1)
        self.assertEqual(terminal_summary["sample_count"],0)
        rejected=load_report(artifacts/"terminal-fail-report.json")
        self.assertEqual(rejected["status"],"failed")
        self.assertEqual(rejected["child_exit_code"],7)
        self.assertEqual(rejected["cleanup_exit_code"],7)
        self.assertEqual(rejected["exit_race_events"],[])
        self.assertEqual(rejected["samples"][0]["api_outcomes"]["suspend_return"],(1<<32)-1)
        self.assertEqual(authenticate(exe,ROOT,"owned-child-stack-sample-controls"),identity)
if __name__=="__main__":
    unittest.main()

