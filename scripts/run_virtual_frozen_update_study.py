"""Complete fixed two-law frozen-update controller. No subset, resume or retry."""
from pathlib import Path
from collections.abc import Mapping
from fractions import Fraction
import argparse,json,sys,shutil,traceback,time
from tests.virtual_frozen_source_guard import (capture_source,verify_source,capture_execution_closure,
    verify_execution_closure,require_source_bootstrap,_git)
from tests.virtual_frozen_build_guard import authenticate_build
from tests.virtual_frozen_run_control import RunClaim,run_bounded_child
from tests.virtual_frozen_study_admission import census_study_admission,WORST_BOARD
from tests.virtual_frozen_sample_reference import build_sampled_reference_context,admit_sampled_board,compute_sampled_update_reference
from tests.virtual_frozen_value_reference import prepare_expected_update_reference,compute_expected_update_reference
from tests.virtual_frozen_whole_study import compose_study_admission,FILE_FAMILIES,SOURCE
from tests.virtual_frozen_expectation import ExactExpectation,FORECAST as AGGREGATE
from tests.virtual_frozen_update_comparison import FORECAST as COMPARISON
from tests.virtual_frozen_reference_artifact import write_reference,read_reference,artifact_allowance
from tests.virtual_frozen_probe_protocol import request,parse,MAX_BYTES
from scripts.run_virtual_frozen_source_only import source_only_command

class AllowanceMeter:
    def __init__(self,limits):self.limits=dict(limits);self.used={name:0 for name in limits}
    def reserve(self,name,amount):
        if type(amount) is not int or amount<0 or name not in self.used or amount>self.limits[name]-self.used[name]:
            raise ValueError('controller allowance exceeded: '+str(name))
        self.used[name]+=amount


def _safe(value):
    if type(value) is Fraction:return [format(value.numerator,'x'),format(value.denominator,'x')]
    if isinstance(value,Mapping):return {key:_safe(v) for key,v in value.items()}
    if isinstance(value,(tuple,list)):return [_safe(v) for v in value]
    if value is None or type(value) in (str,int,float,bool):return value
    raise ValueError('unsupported controller metadata type')


def validate_build_bootstrap(child,source,parent):
    required={'scripts/run_virtual_frozen_source_only.py','scripts/build_native_exact_four_street.py'}
    if (child.get('version')!='project-source-only-bootstrap-v1' or
            child.get('entry_module')!='scripts.build_native_exact_four_street' or
            child.get('root')!=parent['root'] or child.get('interpreter')!=parent['interpreter'] or
            type(child.get('compiled')) is not dict or not required<=set(child['compiled']) or
            len(child['compiled'])>SOURCE['paths']):
        raise ValueError('build child source-only runtime differs')
    for name,identity in child['compiled'].items():
        if name not in source['files'] or identity!=source['files'][name]['raw_sha256']:
            raise ValueError('build child executed Python differs from committed source')


def run_complete_study(directory,expected_head):
    repo=Path(__file__).resolve().parents[1]
    if Path.cwd().resolve()!=repo:raise ValueError('controller must run in its source checkout')
    directory=Path(directory).resolve()
    if directory.is_relative_to(repo):raise ValueError('study output must be external')
    head=_git(repo,['rev-parse','HEAD']).decode().strip()
    if head!=expected_head:raise ValueError('requested committed source does not match HEAD')
    require_source_bootstrap(repo)
    claim=RunClaim(directory,head);started=time.perf_counter();evals=0;eval_attempts=0
    # Preparation outputs are bounded before the rank-free full resource plan.
    files=AllowanceMeter({**FILE_FAMILIES,'reference_artifacts':5_000_000_000})
    files.reserve('controller_and_failure_logs',131072+65536)
    call_metadata={}
    files.reserve('controller_and_failure_logs',(2*(5040+2)+32)*1024)
    progress=(directory/'progress.jsonl').open('xb');events=0
    def emit(phase,**values):
        nonlocal events
        raw=(json.dumps({'phase':phase,'elapsed_seconds':time.perf_counter()-started,**values},sort_keys=True)+'\n').encode()
        if len(raw)>1024 or events>=2*(5040+2)+32:raise ValueError('controller progress log bound')
        progress.write(raw);progress.flush();events+=1
    def save(path,value,*,family='call_receipts',cap=65536):
        raw=(json.dumps(_safe(value),sort_keys=True,indent=2)+'\n').encode()
        if len(raw)>cap:raise ValueError('controller metadata frame exceeded')
        if family=='call_receipts' and path.parent in call_metadata:
            if len(raw)>call_metadata[path.parent]:raise ValueError('combined per-call metadata exceeded')
            call_metadata[path.parent]-=len(raw)
        else:files.reserve(family,len(raw))
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as output:output.write(raw)
    try:
        emit('source_capture_start')
        files.reserve('source_snapshot',SOURCE['total_bytes'])
        source=capture_source(repo,snapshot_directory=directory/'source')
        if source['head']!=head:raise ValueError('source changed before full capture')
        boot=require_source_bootstrap(repo,source)
        save(directory/'python-bootstrap.json',boot,family='controller_and_failure_logs',cap=1<<20)
        save(directory/'source.json',source,family='controller_and_failure_logs',cap=16*(1<<20))
        emit('source_capture_complete',files=len(source['files']),bytes=source['bytes'])
        # Build under the authenticated current source, outside its checkout.
        files.reserve('controller_and_failure_logs',MAX_BYTES+2*65536+(2<<20))
        build_dir=directory/'build'
        built=run_bounded_child(source_only_command(repo/'scripts/run_virtual_frozen_source_only.py',
             source['files']['scripts/run_virtual_frozen_source_only.py']['raw_sha256'],
             'scripts.build_native_exact_four_street',directory/'build-bootstrap.json',
             ['--target','virtual-frozen-update','--output-dir',str(build_dir)]),b'',directory/'build-process',
             stdout_limit=MAX_BYTES,timeout=300)
        if built['status']!='exited' or built['returncode']!=0:raise ValueError('native proof build failed')
        child_boot_path=directory/'build-bootstrap.json'
        if child_boot_path.stat().st_size>1<<20:raise ValueError('build bootstrap receipt bound')
        child_boot=json.loads(child_boot_path.read_bytes())
        validate_build_bootstrap(child_boot,source,boot)
        build_size=sum(p.stat().st_size for p in build_dir.rglob('*') if p.is_file())
        files.reserve('headers_and_build',build_size)
        build=authenticate_build(repo,build_dir,source)
        save(directory/'build-identity.json',build,family='controller_and_failure_logs')
        emit('build_authenticated')
        context=build_sampled_reference_context()
        census=census_study_admission(context)
        expected_admission=prepare_expected_update_reference()
        plan=compose_study_admission(census,expected_admission)
        # Keep file-family limits identical to the admitted complete plan.
        for name,amount in files.used.items():
            if amount>plan['file_families'][name]:raise ValueError('preparation exceeded final file family')
        files.limits=dict(plan['file_families'])
        files.used.update({name:0 for name in files.limits if name not in files.used})
        numeric=AllowanceMeter(plan['uses'])
        numeric.reserve('reference_work',150_000_000+expected_admission.rule_setup_work+expected_admission.work_upper+500_000_000)
        numeric.reserve('reference_created_bits',1_000_000_000+expected_admission.rule_setup_created_bits+expected_admission.created_bits_upper+16_000_000_000)
        numeric.reserve('authentication_read_bytes',2*SOURCE['total_bytes'])
        save(directory/'resource-plan.json',plan,family='controller_and_failure_logs')
        if shutil.disk_usage(directory).free<plan['uses']['artifact_bytes']:
            raise ValueError('insufficient free space for the complete admitted evidence allowance')
        closure=capture_execution_closure(repo,source,build['sources'])
        save(directory/'execution-closure.json',closure,family='controller_and_failure_logs')
        def guard():
            numeric.reserve('authentication_read_bytes',SOURCE['total_bytes']+320*(1<<20))
            observed=verify_execution_closure(repo,source,closure)
            if authenticate_build(repo,build_dir,source)!=build:raise ValueError('build identity changed')
            return observed
        def native(mode,law,board,path):
            nonlocal evals,eval_attempts
            before=guard()
            payload=request(mode,law,board)
            files.reserve('requests',len(payload));files.reserve('native_stdout',MAX_BYTES)
            files.reserve('native_stderr',65536);files.reserve('call_receipts',65536)
            numeric.reserve('native_work',500_000_000)
            if mode=='EVAL':eval_attempts+=1
            emit('native_start',mode=mode,law=law,board=list(board),eval_attempts=eval_attempts)
            observed=run_bounded_child([build['executable']],payload,path,stdout_limit=MAX_BYTES)
            call_metadata[path]=65536-(path/'process.json').stat().st_size
            if call_metadata[path]<0:raise ValueError('process metadata exceeded call allowance')
            after=guard()
            if observed['status']!='exited' or observed['returncode']!=0 or observed['streams'][1]['saved_bytes']:
                raise ValueError('native proof child failed')
            raw=(path/'stdout.bin').read_bytes()
            if mode=='EVAL':
                response=parse(raw,mode=mode,proposal=law,board=board)
                if response.get('status')!='COMPLETE':raise ValueError('native update did not complete')
                evals+=1
            emit('native_exit',mode=mode,law=law,eval_completions=evals)
            return raw,before,after
        admissions={}
        for law in ('UNIFORM','RIVER_WEIGHTED'):
            raw,_,_=native('ADMIT',law,WORST_BOARD,directory/('admit-'+law))
            result=parse(raw,mode='ADMIT',proposal=law,board=WORST_BOARD)
            if result.get('status')!='ADMITTED' or any(result['calls']):raise ValueError('frozen worst-law native admission failed')
            if result['forecast'][1]+result['probe'][2]>500_000_000:raise ValueError('combined native/transport admission failed')
            admissions[law]=result
        save(directory/'native-admissions.json',admissions,family='controller_and_failure_logs')
        def export_reference(path,result,kind):
            count=len(result.rows);slots=sum(len(row.actions) for row in result.rows.values())
            allowance=artifact_allowance(kind,count,slots)
            files.reserve('reference_artifacts',allowance['bytes'])
            numeric.reserve('codec_work',2*allowance['work'])
            saved=write_reference(path,result,kind)
            loaded=read_reference(path,byte_limit=allowance['bytes'])
            return loaded,saved
        # Compute exactly once; preserve full exact output before comparison.
        emit('q_free_reference_start')
        expected=compute_expected_update_reference(expected_admission)
        saved_expected,expected_export=export_reference(directory/'expected.jsonl',expected,'expected')
        save(directory/'expected-receipt.json',expected.receipt,family='controller_and_failure_logs')
        del expected
        emit('q_free_reference_saved')
        law_results={}
        for law,wire in [('uniform','UNIFORM'),('river_weighted','RIVER_WEIGHTED')]:
            numeric.reserve('aggregation_work',AGGREGATE['work'])
            numeric.reserve('aggregation_created_bits',AGGREGATE['created_bits'])
            owner=ExactExpectation(law)
            law_dir=directory/law;law_dir.mkdir()
            for index,board in enumerate(context.physical.proposals):
                call=law_dir/('%04d'%index)
                raw,before,after=native('EVAL',wire,board,call)
                admission=admit_sampled_board(context,board,law)
                numeric.reserve('reference_work',admission.work_upper)
                numeric.reserve('reference_created_bits',admission.created_bits_upper)
                sample=compute_sampled_update_reference(admission)
                loaded,export=export_reference(call/'reference.jsonl',sample,'sampled')
                save(call/'reference-receipt.json',sample.receipt)
                del sample
                numeric.reserve('comparison_work',COMPARISON['work'])
                numeric.reserve('comparison_created_bits',COMPARISON['created_bits'])
                comparison=owner.add(raw,loaded)
                save(call/'comparison.json',{'comparison':comparison,'source_before':before,
                     'source_after':after,'reference_export':export})
                del loaded,raw
            law_results[law]=owner.finish(saved_expected)
            save(directory/(law+'-expectation.json'),law_results[law],family='controller_and_failure_logs')
            del owner
        numeric.reserve('authentication_read_bytes',SOURCE['total_bytes'])
        from scripts.run_virtual_frozen_source_only import scan_project_caches
        scan_project_caches(repo)
        final_source=verify_source(repo,source)
        if authenticate_build(repo,build_dir,source)!=build:raise ValueError('final build identity changed')
        receipt={'status':'exact_update_identity_pass','native_eval_completions':evals,'native_eval_attempts':eval_attempts,
                 'laws':law_results,'source_final':final_source,'source_head':head,
                 'numeric_reserved':numeric.used,'files_reserved':files.used,
                 'expected_export':expected_export,'duration_seconds':time.perf_counter()-started,
                 'scope':'fixed procedural profile update identity only; no sampler/training/quality result',
                 'mutation_witnesses':'pending saved-only review; not experiment acceptance'}
        save(directory/'result.json',receipt,family='controller_and_failure_logs')
        claim.finish('complete',{'native_eval_completions':evals,'native_eval_attempts':eval_attempts,'result':'result.json',
                     'acceptance':'pending independent saved-only review and mutation witnesses'})
        emit('complete_pending_saved_review',eval_completions=evals)
        return receipt
    except BaseException as error:
        failure={'status':'failed','native_eval_completions':evals,'native_eval_attempts':eval_attempts,'first_error':type(error).__name__+': '+str(error)[:2048],
                 'traceback':traceback.format_exc()[-16384:],'duration_seconds':time.perf_counter()-started}
        claim.finish('failed',failure)
        raise
    finally:
        progress.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--expected-head',required=True)
    args=parser.parse_args()
    print(json.dumps(_safe(run_complete_study(args.output,args.expected_head)),sort_keys=True))

if __name__=='__main__':main()
