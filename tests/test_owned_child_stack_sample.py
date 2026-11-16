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
        sampling_begin_elapsed_ms=1,duration_ms=100,report_truncated=False,omitted_sample_records=0,omitted_module_records=0,
        modules=[dict(base='0x1000',size=4096,path=CHILD,mapped_local_image=True,exception_directory=True,
            image_usable=True,file_bytes=2048,denied_image_spans=0,identity_error='')],
        samples=[dict(elapsed_ms=5,pause_ns=100,seed_rip='0x1234',seed_rsp='0x2000',target_read_bytes=32,
            captured_stack_bytes=32,stack_capture_truncated=False,capture_error='',callback_calls=2,callback_bytes=16,
            stack_callback_bytes=8,module_callback_bytes=8,callback_failures=0,budget_denials=0,unmapped_reads=1,
            metadata_calls=2,seed_echo_skipped=True,status='partial_unwind',stop_reason='unmapped_current_frame',
            frames=[dict(pc='0x3000',sp='0x2010'),dict(pc='0x4000',sp='0x2020')])])
def verify(value,mode='periodic_stack_observation',exit_code=0):
    return validator.verify_report(value,CHILD,mode,exit_code)

class OwnedChildReportTests(unittest.TestCase):
    def test_valid_partial_and_empty_and_failure(self):
        r=fixture(); summary=verify(r)
        self.assertEqual((summary['sample_count'],summary['sample_depths'],summary['frame_count']),(1,[2],2))
        self.assertEqual(summary['partial_reasons'],{'unmapped_current_frame':1})
        self.assertEqual(summary['unmapped_reads'],1)
        r['samples']=[]; r['status']='completed_no_samples'
        self.assertEqual(verify(r)['sample_count'],0)
        r['child_exit_code']=r['cleanup_exit_code']=7; r['status']='child_failed'; r['error']='child_exit_code_nonzero'
        self.assertEqual(verify(r,exit_code=7)['child_status'],'child_failed')
        r=fixture();r['mode']='disabled';r['status']='completed_disabled';r['samples']=[];r['modules']=[];r['local_image_bytes']=0;r['module_enumeration_attempts']=0
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
        r=fixture();r['samples'][0]['callback_failures']=3
        with self.assertRaises(ValueError):verify(r)
        for key,value in [('base','0x0'),('size',0),('base','0xffffffffffffffff'),
                          ('file_bytes',0),('denied_image_spans',65538)]:
            r=fixture();r['modules'][0][key]=value
            with self.subTest(module_key=key),self.assertRaises(ValueError):verify(r)
        r=fixture();r['modules'][0].update(size=0xffffffff,mapped_local_image=False,image_usable=False,file_bytes=0)
        r['local_image_bytes']=0
        self.assertEqual(verify(r)['module_count'],1)
        r=fixture();r['modules'][0]['size']=64*1024*1024+1
        with self.assertRaises(ValueError):verify(r)
    def test_bounded_json_duplicate_and_nonfinite(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'report.json'
            for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b' '+b' '*validator.MAX_BYTES):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):validator.load_report(path)
            path.write_text(json.dumps(fixture()),encoding='utf-8')
            self.assertEqual(verify(validator.load_report(path))['sample_count'],1)

if __name__=='__main__': unittest.main()
