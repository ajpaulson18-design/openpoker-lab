"""Validate bounded owned-child stack reports; observations do not measure CPU time."""
import argparse
from collections import Counter
import json
import ntpath
from pathlib import Path
import re

MAX_BYTES = 4*1024*1024
MAX_MODULES, MAX_SAMPLES, MAX_FRAMES = 64, 1024, 64
MAX_CALLBACKS, MAX_READ = 4096, 64*1024
MAX_IMAGE, MAX_TOTAL_IMAGE = 64*1024*1024, 256*1024*1024
TOP = set('schema_version sampler architecture mode interval_ms child scratch symbols_directory status error child_exit_code watchdog_reason sample_limit_reached module_list_truncated module_enumeration_attempts module_enumeration_failures dbghelp_error child_launched child_process_id child_thread_id parent_process_id child_creation_time job_assigned job_assignment_error initial_thread_resumed child_exit_observed cleanup_exit_observed cleanup_exit_code cleanup_wait_result termination_attempted termination_succeeded termination_error local_image_bytes sampling_begin_elapsed_ms duration_ms report_truncated omitted_sample_records omitted_module_records modules samples'.split())
MODULE = set('base size path mapped_local_image exception_directory image_usable file_bytes denied_image_spans identity_error'.split())
SAMPLE = set('elapsed_ms pause_ns seed_rip seed_rsp target_read_bytes captured_stack_bytes stack_capture_truncated capture_error callback_calls callback_bytes stack_callback_bytes module_callback_bytes callback_failures budget_denials unmapped_reads metadata_calls seed_echo_skipped status stop_reason frames'.split())

def need(ok, reason):
    if not ok: raise ValueError(reason)
def schema(obj, keys, label):
    need(type(obj) is dict and set(obj)==keys,label+' schema')
def natural(value, label, maximum=(1<<64)-1, minimum=0):
    need(type(value) is int and minimum<=value<=maximum,label+' integer range')
    return value
def boolean(value,label): need(type(value) is bool,label+' boolean')
def string(value,label,allow_empty=True):
    need(type(value) is str and len(value)<=32768 and '\x00' not in value and (allow_empty or value),label+' string')
def address(value,label):
    need(type(value) is str and re.fullmatch(r'0x[0-9a-f]{1,16}',value) is not None,label+' address')
    return int(value,16)
def pairs(items):
    out={}
    for key,value in items:
        need(key not in out,'duplicate JSON key'); out[key]=value
    return out
def nonfinite(value): raise ValueError('nonfinite JSON constant: '+value)
def load_report(path):
    with Path(path).open('rb') as stream: raw=stream.read(MAX_BYTES+1)
    need(0<len(raw)<=MAX_BYTES,'report byte cap')
    try: return json.loads(raw,object_pairs_hook=pairs,parse_constant=nonfinite)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error: raise ValueError('invalid report JSON') from error

def verify_report(report, expected_child, expected_mode, expected_exit):
    schema(report,TOP,'report')
    need(type(report['schema_version']) is int and report['schema_version']==1 and
         report['sampler']=='owned-child-stack-sample-v1' and report['architecture']=='windows-x64','report identity')
    need(expected_mode in ('disabled','periodic_stack_observation') and report['mode']==expected_mode,'mode differs')
    natural(expected_exit,'expected exit',(1<<32)-1)
    for key in ('child','scratch','symbols_directory','status','error','dbghelp_error'):
        string(report[key],key,allow_empty=key in ('error','dbghelp_error'))
    string(expected_child,'expected child',False)
    need(ntpath.isabs(expected_child) and ntpath.isabs(report['child']) and
         ntpath.normcase(ntpath.normpath(report['child']))==ntpath.normcase(ntpath.normpath(expected_child)), 'child path differs')
    for key in ('sample_limit_reached','module_list_truncated','child_launched','job_assigned','initial_thread_resumed',
                'child_exit_observed','cleanup_exit_observed','termination_attempted','termination_succeeded'):
        boolean(report[key],key)
    for key in ('child_exit_code','watchdog_reason','child_process_id','child_thread_id','parent_process_id',
                'job_assignment_error','cleanup_exit_code','cleanup_wait_result','termination_error',
                'module_enumeration_attempts','module_enumeration_failures'):
        natural(report[key],key,(1<<32)-1)
    for key in ('child_creation_time','local_image_bytes','sampling_begin_elapsed_ms','duration_ms'):
        natural(report[key],key)
    natural(report['interval_ms'],'interval_ms',1000,1)
    need(all(report[k] for k in ('child_launched','job_assigned','initial_thread_resumed','child_exit_observed','cleanup_exit_observed')),
         'owned child lifecycle proof incomplete')
    need(all(report[k]>0 for k in ('child_process_id','child_thread_id','parent_process_id','child_creation_time')),
         'owned child identity incomplete')
    need(report['child_exit_code']==expected_exit==report['cleanup_exit_code'] and report['cleanup_wait_result']==0 and
         report['job_assignment_error']==0 and report['watchdog_reason']==0 and not report['termination_attempted'] and
         not report['termination_succeeded'] and report['termination_error']==0,'child exit proof differs')
    boolean(report['report_truncated'],'report_truncated')
    for key in ('omitted_sample_records','omitted_module_records'): natural(report[key],key)
    need(not report['report_truncated'] and report['omitted_sample_records']==0 and
         report['omitted_module_records']==0,'truncated report cannot prove completed child observation')
    modules=report['modules']; samples=report['samples']
    need(type(modules) is list and len(modules)<=MAX_MODULES and type(samples) is list and len(samples)<=MAX_SAMPLES,'record capacity')
    need(report['local_image_bytes']<=MAX_TOTAL_IMAGE,'total image limit')
    need(report['module_enumeration_attempts']<=4 and
         report['module_enumeration_failures']<=report['module_enumeration_attempts']+MAX_MODULES,
         'module enumeration bounds')
    need(report['sampling_begin_elapsed_ms']<=report['duration_ms'],'sampling time')
    if expected_exit:
        need(report['status']=='child_failed' and report['error']=='child_exit_code_nonzero','failed child status')
    else:
        expected_status=('completed_disabled' if expected_mode=='disabled' else
                         'completed_partial_unwinds' if samples else 'completed_no_samples')
        need(report['status']==expected_status and report['error']=='','completed status')
    if expected_mode=='disabled':
        need(not samples and not modules and not report['sample_limit_reached'] and
             report['module_enumeration_attempts']==0 and report['module_enumeration_failures']==0 and
             report['local_image_bytes']==0,'disabled has observations')
    if report['sample_limit_reached']: need(len(samples)==MAX_SAMPLES,'sample cap flag differs')
    mapped_total=0
    for module in modules:
        schema(module,MODULE,'module')
        base=address(module['base'],'module base'); size=natural(module['size'],'module size',(1<<32)-1,1)
        need(base>0 and base+size<=1<<64,'module address range')
        natural(module['file_bytes'],'module file bytes',MAX_IMAGE)
        natural(module['denied_image_spans'],'denied spans',65537)
        string(module['path'],'module path'); string(module['identity_error'],'identity error')
        for key in ('mapped_local_image','exception_directory','image_usable'): boolean(module[key],key)
        if module['mapped_local_image']:
            natural(module['size'],'mapped image size',MAX_IMAGE,1)
            need(module['file_bytes']>0,'mapped image file missing'); mapped_total+=module['size']
        need(not module['image_usable'] or module['mapped_local_image'],'usable image not mapped')
    need(mapped_total==report['local_image_bytes'],'mapped image total differs')
    reasons=Counter(); statuses=Counter(); depths=[]; frame_total=0
    last_elapsed=0
    for sample in samples:
        schema(sample,SAMPLE,'sample')
        for key in ('elapsed_ms','pause_ns','target_read_bytes','captured_stack_bytes','callback_calls','callback_bytes',
                    'stack_callback_bytes','module_callback_bytes','callback_failures','budget_denials','unmapped_reads','metadata_calls'):
            natural(sample[key],key)
        need(max(last_elapsed,report['sampling_begin_elapsed_ms'])<=sample['elapsed_ms']<=report['duration_ms'] and
             sample['pause_ns']<=250000000,'sample timing'); last_elapsed=sample['elapsed_ms']
        need(sample['target_read_bytes']<=MAX_READ and sample['captured_stack_bytes']<=MAX_READ and
             sample['captured_stack_bytes']==sample['target_read_bytes'] and sample['callback_calls']<=MAX_CALLBACKS and
             sample['metadata_calls']<=MAX_CALLBACKS and sample['callback_failures']<=sample['callback_calls'] and
             sample['callback_bytes']<=MAX_READ and sample['stack_callback_bytes']+sample['module_callback_bytes']==sample['callback_bytes'],
             'sample resource accounting')
        for key in ('stack_capture_truncated','seed_echo_skipped'): boolean(sample[key],key)
        for key in ('capture_error','status','stop_reason'): string(sample[key],key,allow_empty=key=='capture_error')
        seed=(address(sample['seed_rip'],'seed rip'),address(sample['seed_rsp'],'seed rsp'))
        need(seed[0]>0 and seed[1]>0,'sample seed missing')
        frames=sample['frames']; need(type(frames) is list and len(frames)<=MAX_FRAMES,'frame capacity')
        need(sample['status']==('partial_unwind' if frames else 'partial_rip_only'),'sample status')
        previous=seed[1]
        for frame in frames:
            schema(frame,{'pc','sp'},'frame'); pc=address(frame['pc'],'frame pc'); sp=address(frame['sp'],'frame sp')
            need(pc>0 and sp>previous and sp<=seed[1]+sample['captured_stack_bytes'] and (pc,sp)!=seed,
                 'frame progress or captured stack bounds'); previous=sp
        reasons[sample['stop_reason']]+=1; statuses[sample['status']]+=1
        depths.append(len(frames)); frame_total+=len(frames)
    return {'status':'validated_owned_child_report','child_status':report['status'],'mode':expected_mode,
            'sample_count':len(samples),'frame_count':frame_total,'seed_and_frame_count':len(samples)+frame_total,'sample_depths':depths,
            'partial_reasons':dict(reasons),'sample_statuses':dict(statuses),'module_count':len(modules),
            'unmapped_reads':sum(x['unmapped_reads'] for x in samples),
            'unknown_frame_attribution':'all frames retained; no mapping attempted',
            'sample_limit_reached':report['sample_limit_reached'],'module_list_truncated':report['module_list_truncated'],
            'limits':{'report_bytes':MAX_BYTES,'modules':MAX_MODULES,'samples':MAX_SAMPLES,'frames_per_sample':MAX_FRAMES,
                      'callback_calls_per_sample':MAX_CALLBACKS,'read_bytes_per_sample':MAX_READ,
                      'image_bytes':MAX_IMAGE,'total_image_bytes':MAX_TOTAL_IMAGE},
            'interpretation':'periodic observations only; no CPU-time claim'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path); parser.add_argument('--child',required=True)
    parser.add_argument('--mode',required=True,choices=('disabled','periodic_stack_observation'))
    parser.add_argument('--exit-code',required=True,type=int)
    args=parser.parse_args()
    print(json.dumps(verify_report(load_report(args.report),args.child,args.mode,args.exit_code),sort_keys=True))
if __name__=='__main__': main()
