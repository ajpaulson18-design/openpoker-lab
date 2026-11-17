import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts import verify_owned_child_stack_sample as validator

CHILD = r'C:\fixture\child.exe'
def fixture():
    return dict(schema_version=1,sampler='owned-child-stack-sample-v1',architecture='windows-x64',
        mode='periodic_stack_observation',interval_ms=20,child=CHILD,scratch=r'C:\fixture\scratch',
        symbols_directory=r'C:\fixture\symbols',status='completed_partial_unwinds',error='',child_exit_code=0,
        watchdog_reason=0,sample_limit_reached=False,module_list_truncated=False,module_enumeration_attempts=1,
        module_enumeration_failures=0,dbghelp_error='',child_launched=True,child_process_id=8,child_thread_id=9,
        parent_process_id=10,child_creation_time=11,job_assigned=True,job_assignment_error=0,initial_thread_resumed=True,
        child_exit_observed=True,cleanup_exit_observed=True,cleanup_exit_code=0,cleanup_wait_result=0,
        termination_attempted=False,termination_succeeded=False,termination_error=0,local_image_bytes=4096,
        sampling_begin_elapsed_ms=1,duration_ms=100,report_truncated=False,omitted_sample_records=0,omitted_module_records=0,sampling_attempts=1,exit_race_events=[],
        modules=[dict(base='0x1000',size=4096,path=CHILD,mapped_local_image=True,exception_directory=True,
            image_usable=True,file_bytes=2048,denied_image_spans=0,identity_error='')],
        samples=[dict(elapsed_ms=5,pause_ns=100,seed_rip='0x1234',seed_rsp='0x2000',target_read_bytes=32,
            captured_stack_bytes=32,stack_capture_truncated=False,capture_error='',callback_calls=2,callback_bytes=16,
            stack_callback_bytes=8,module_callback_bytes=8,callback_failures=0,budget_denials=0,unmapped_reads=1,
            metadata_calls=2,seed_echo_skipped=True,status='partial_unwind',stop_reason='unmapped_current_frame',
            frames=[dict(pc='0x3000',sp='0x2010'),dict(pc='0x4000',sp='0x2020')],
            api_outcomes=dict(suspend_return=0,suspend_error=0,context_result=True,context_error=0,resume_return=1,resume_error=0))])
def verify(value,mode='periodic_stack_observation',exit_code=0):
    return validator.verify_report(value,CHILD,mode,exit_code)

class OwnedChildReportTests(unittest.TestCase):
    def test_valid_partial_and_empty_and_failure(self):
        r=fixture(); summary=verify(r)
        self.assertEqual((summary['sample_count'],summary['sample_depths'],summary['frame_count']),(1,[2],2))
        self.assertEqual(summary['partial_reasons'],{'unmapped_current_frame':1})
        self.assertEqual(summary['unmapped_reads'],1)
        r['samples']=[]; r['sampling_attempts']=0; r['status']='completed_no_samples'
        self.assertEqual(verify(r)['sample_count'],0)
        r['child_exit_code']=r['cleanup_exit_code']=7; r['status']='child_failed'; r['error']='child_exit_code_nonzero'
        self.assertEqual(verify(r,exit_code=7)['child_status'],'child_failed')
        r=fixture();r['mode']='disabled';r['status']='completed_disabled';r['samples']=[];r['sampling_attempts']=0;r['modules']=[];r['local_image_bytes']=0;r['module_enumeration_attempts']=0
        self.assertEqual(verify(r,'disabled')['sample_count'],0)
    def test_schema_and_identity_rejected(self):
        for key,value in [('child',r'C:\other.exe'),('mode','disabled'),('child_process_id',True),
                          ('child_thread_id',0),('parent_process_id',0),('child_creation_time',0),
                          ('job_assigned',False),('child_exit_observed',False),('cleanup_exit_observed',False),
                          ('cleanup_exit_code',7),('cleanup_wait_result',258),('status','child_failed'),('sample_limit_reached',True),
                          ('report_truncated',True),('omitted_sample_records',1),('omitted_module_records',1),
                          ('module_enumeration_attempts',5),('module_enumeration_failures',66)]:
            with self.subTest(key=key):
                r=fixture();r[key]=value
                with self.assertRaises(ValueError):verify(r)
        r=fixture();r['extra']=1
        with self.assertRaises(ValueError):verify(r)
        with self.assertRaises(ValueError):validator.verify_report(fixture(),CHILD,'periodic_stack_observation',7)
    def test_resource_limits_and_progress(self):
        for key,value in [('callback_calls',4097),('callback_bytes',65537),('target_read_bytes',65537),
                          ('captured_stack_bytes',True),('metadata_calls',4097),('seed_rip','0x0'),('seed_rsp','0x0'),
                          ('pause_ns',250000001),('elapsed_ms',0),('frames',[{'pc':'0x2','sp':hex(0x2001+i)} for i in range(65)])]:
            with self.subTest(key=key):
                r=fixture();r['samples'][0][key]=value
                with self.assertRaises(ValueError):verify(r)
        for frames in ([{'pc':'0x1234','sp':'0x2000'}], [{'pc':'0x2','sp':'0x2010'},{'pc':'0x3','sp':'0x2010'}],
                       [{'pc':'0x0','sp':'0x2010'}], [{'pc':'0x3','sp':'0x2021'}]):
            r=fixture();r['samples'][0]['frames']=frames
            with self.assertRaises(ValueError):verify(r)
        for key,value in [('modules',[fixture()['modules'][0]]*65),('samples',[fixture()['samples'][0]]*1025),
                          ('local_image_bytes',256*1024*1024+1)]:
            r=fixture();r[key]=value
            with self.assertRaises(ValueError):verify(r)
        r=fixture();r['samples'][0]['frames']=[{'pc':'0x3000','sp':'0x2010'},{'pc':'0x3000','sp':'0x2020'}]
        r['samples'][0]['budget_denials']=1
        self.assertEqual(verify(r)['frame_count'],2)
        for key,value in [('suspend_return',1),('suspend_error',1),('context_result',False),
                          ('context_error',1),('resume_return',0),('resume_error',1)]:
            r=fixture();r['samples'][0]['api_outcomes'][key]=value
            with self.assertRaises(ValueError):verify(r)
        r=fixture();r['samples'][0]['callback_failures']=3
        with self.assertRaises(ValueError):verify(r)
        for key,value in [('base','0x0'),('size',0),('base','0xffffffffffffffff'),
                          ('file_bytes',0),('denied_image_spans',65537)]:
            r=fixture();r['modules'][0][key]=value
            with self.subTest(module_key=key),self.assertRaises(ValueError):verify(r)
        r=fixture();r['modules'][0].update(size=0xffffffff,mapped_local_image=False,image_usable=False,file_bytes=0)
        r['local_image_bytes']=0
        self.assertEqual(verify(r)['module_count'],1)
        r=fixture();r['modules'][0]['size']=64*1024*1024+1
        with self.assertRaises(ValueError):verify(r)
    def test_terminal_race_proof_and_denominator(self):
        r=fixture(); event_sample=copy.deepcopy(r['samples'][0])
        event_sample.update(seed_rip='0x0',seed_rsp='0x0',frames=[],status='terminal_race_capture',
            stop_reason='not_attempted',seed_echo_skipped=False,callback_calls=0,callback_bytes=0,
            stack_callback_bytes=0,module_callback_bytes=0,callback_failures=0,budget_denials=0,unmapped_reads=0,metadata_calls=0)
        event=dict(capture_failure='SuspendThread_failed',thread_exit_observed=True,thread_exit_code=0,
            process_exit_observed=True,child_exit_code=0,api_outcomes=dict(suspend_return=0xffffffff,suspend_error=5,
            context_result=None,context_error=0,resume_return=None,resume_error=0),sample=event_sample)
        event_sample['api_outcomes']=copy.deepcopy(event['api_outcomes'])
        r['exit_race_events']=[event];r['sampling_attempts']=2
        summary=verify(r)
        self.assertEqual((summary['sample_count'],summary['sampling_attempts'],summary['exit_race_event_count']), (1,2,1))
        for failure,changes in [('GetThreadContext_failed',dict(suspend_return=0,context_result=False,resume_return=1)),
            ('ResumeThread_failed',dict(suspend_return=0,context_result=True,resume_return=0xffffffff)),
            ('owned_suspend_increment_changed',dict(suspend_return=0,context_result=True,resume_return=0))]:
            candidate=copy.deepcopy(r);ev=candidate['exit_race_events'][0];ev['capture_failure']=failure
            ev['api_outcomes'].update(changes);ev['api_outcomes']['suspend_error']=0
            ev['sample']['api_outcomes']=copy.deepcopy(ev['api_outcomes'])
            self.assertEqual(verify(candidate)['exit_race_event_count'],1)
        for mutate in (lambda x:x.update(sampling_attempts=1),
                       lambda x:x.update(exit_race_events=x['exit_race_events']*2,sampling_attempts=3),
                       lambda x:x['exit_race_events'][0].update(thread_exit_observed=False),
                       lambda x:x['exit_race_events'][0].update(process_exit_observed=False),
                       lambda x:x['exit_race_events'][0].update(thread_exit_code=7),
                       lambda x:x['exit_race_events'][0].update(child_exit_code=7),
                       lambda x:x['exit_race_events'][0].update(capture_failure='unexpected_prior_suspend_count'),
                       lambda x:x['exit_race_events'][0]['api_outcomes'].update(resume_return=2),
                       lambda x:x['exit_race_events'][0]['sample'].update(frames=[dict(pc='0x1',sp='0x2')]),
                       lambda x:x['exit_race_events'][0]['sample'].update(status='partial_rip_only'),
                       lambda x:x['exit_race_events'][0]['sample']['api_outcomes'].update(suspend_error=0),
                       lambda x:x['exit_race_events'][0]['sample']['api_outcomes'].update(context_error=False),
                       lambda x:(x['samples'].append(copy.deepcopy(x['exit_race_events'][0]['sample'])),x.update(sampling_attempts=3))):
            candidate=copy.deepcopy(r);mutate(candidate)
            with self.assertRaises(ValueError):verify(candidate)
        candidate=copy.deepcopy(r);candidate['exit_race_events'][0].update(capture_failure='owned_suspend_increment_changed')
        candidate['exit_race_events'][0]['api_outcomes'].update(suspend_return=0,suspend_error=0,context_result=True,resume_return=2)
        candidate['exit_race_events'][0]['sample']['api_outcomes']=copy.deepcopy(candidate['exit_race_events'][0]['api_outcomes'])
        with self.assertRaises(ValueError):verify(candidate)
        for key,value in [('suspend_error',5),('context_error',5),('resume_error',5)]:
            candidate=copy.deepcopy(r);ev=candidate['exit_race_events'][0]
            ev.update(capture_failure='owned_suspend_increment_changed')
            ev['api_outcomes'].update(suspend_return=0,suspend_error=0,context_result=True,context_error=0,resume_return=0,resume_error=0)
            ev['api_outcomes'][key]=value;ev['sample']['api_outcomes']=copy.deepcopy(ev['api_outcomes'])
            with self.assertRaises(ValueError):verify(candidate)
        candidate=copy.deepcopy(r);candidate['exit_race_events'][0]['sample']['pause_ns']=250000001
        with self.assertRaises(ValueError):verify(candidate)
        candidate=copy.deepcopy(r);candidate['samples']=[];candidate['sampling_attempts']=1;candidate['status']='completed_no_samples'
        self.assertEqual(verify(candidate)['sample_count'],0)
        candidate=copy.deepcopy(r);candidate.update(child_exit_code=7,cleanup_exit_code=7,status='child_failed',error='child_exit_code_nonzero')
        with self.assertRaises(ValueError):verify(candidate,exit_code=7)
        candidate=copy.deepcopy(r);candidate['watchdog_reason']=1
        with self.assertRaises(ValueError):verify(candidate)

    def test_bounded_json_duplicate_and_nonfinite(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'report.json'
            for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b' '+b' '*validator.MAX_BYTES):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):validator.load_report(path)
            path.write_text(json.dumps(fixture()),encoding='utf-8')
            self.assertEqual(verify(validator.load_report(path))['sample_count'],1)

if __name__=='__main__': unittest.main()
