"""Source-frozen PROOF9 T2 admission or one native run with saved-only replay."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import traceback
from zipfile import ZipFile

from scripts.build_native_exact_four_street import build
from scripts.run_native_exact_reach_conformance import bind_build, save, sha
from scripts.run_virtual_frozen_source_only import FIRST_STAGE, source_only_command, scan_project_caches
from scripts.verify_virtual_dyadic_training import EXPECTED_SHAPE, EXPECTED_TERMINAL_COMPLETIONS, FAMILIES, PARENT, SHAPE, TOTAL_BYTES, require
from tests.virtual_frozen_run_control import RunClaim, run_bounded_child, run_bounded_dyadic_probe
from tests.virtual_frozen_saved_review import unlinked_path
from tests.virtual_frozen_source_guard import _git, capture_source, verify_source, require_source_bootstrap

ROOT=Path(__file__).resolve().parents[1]
TARGET='virtual-dyadic-training'
PRODUCER='174b66645a05d5f050d4361ce81b06ea9a4e5ac3'
VERIFIER='6b49057bc62a6599bfc23086ecda52576d755908'
TWO_PASS_HEAD='aa3855903fbcb97020963235c9379e457e3a78c7'
NUMERIC_BYTES=TOTAL_BYTES-8-64*8
ARTIFACT_ALLOWANCE=2<<30


def exact_json(data):
    require(len(data)<=65536,'fixed cohort receipt byte cap')
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'duplicate cohort receipt key')
            result[key]=value
        return result
    return json.loads(data,object_pairs_hook=pairs)


def validate_admission(receipt,*,paired=False,packed=False):
    fixed={'protocol':'DYADIC_T2_V1','status':'ADMITTED','training_invocations':0,'target_passes':0,
           'completed_sweeps':0,'rank_calls':0,'literal_nodes':1105,'requested_sweeps':2,'H':12,'M':1,
           'D_bits':635,'value_bits':642,'normalizer':29,'d5':20,'output_bytes':TOTAL_BYTES,
           'expected_rank_calls':140,'first_uniform_exponent':420,'max_actor_depth':[6,7],
           'prefix_counts':[1,25,56,60],'prefix_supported_rows':[[2,2],[29,26],[60,56],[60,60]],
           'showdown_contractions_per_pass':EXPECTED_TERMINAL_COMPLETIONS[0],
           'hidden_completion_candidates_per_pass':EXPECTED_TERMINAL_COMPLETIONS[1],
           **dict(zip(SHAPE,EXPECTED_SHAPE))}
    if paired or packed:
        fixed['public_walks_per_sweep']=1
    if packed:
        fixed['packed_average_limbs']=258_694
        fixed['packed_average_work']=23_123_160
        fixed['entries']=1_351_755
    require(type(receipt) is dict and all(type(receipt.get(k)) is type(v) and receipt[k]==v for k,v in fixed.items()),
            'fixed admission census or zero-call receipt mismatch')
    for name,keys in [('component_work',FAMILIES),('parent_work',PARENT)]:
        plan=receipt.get(name)
        require(type(plan) is dict and set(plan)==set(keys) and all(type(v) is int and 0<=v<=500_000_000 for v in plan.values()),
                'fixed admission work categories differ')
    component=receipt['component_work']
    require(type(receipt.get('planned_total_work')) is int and 0<sum(component.values())==receipt['planned_total_work']<=500_000_000,
            'fixed admission whole work exceeds allowance')
    require(component['parent']==sum(receipt['parent_work'].values()),'fixed admission parent work sum')
    if packed:
        require(receipt['packed_average_work']<=receipt['parent_work']['average'], 'packed average codec work missing')
    else:
        require('packed_average_limbs' not in receipt and 'packed_average_work' not in receipt,
                'packed codec receipt for dense storage')
    quantizer=receipt.get('quantizer_terms')
    require(type(quantizer) is list and len(quantizer)==3 and all(type(x) is int and x>0 for x in quantizer)
            and sum(quantizer)==component['quantizer'],'fixed admission quantizer allocation')
    require(type(receipt.get('entries')) is int and 0<receipt['entries']<=2_000_000 and
            type(receipt.get('payload_bits')) is int and 0<receipt['payload_bits']<=1<<30,
            'fixed admission storage allowance')
    require(type(receipt.get('actual_admission_work')) is int and
            component['template']<=receipt['actual_admission_work']<=component['template']+receipt['parent_work']['geometry'],
            'fixed admission observed setup accounting')
    return receipt


def require_frozen_gate(source):
    name='benchmarks/results/virtual-frozen-complete-v1/manifest.json'
    path=ROOT/name
    raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==source['files'][name]['raw_sha256'],'fixed proof acceptance manifest source drift')
    gate=exact_json(raw)
    require(gate.get('status')=='accepted_fixed_profile_exact_update_identity' and
            (gate.get('producer_head'),gate.get('verifier_head'))==(PRODUCER,VERIFIER) and
            (gate.get('producer_evaluations'),gate.get('saved_replayed_evaluations'),gate.get('saved_review_producer_calls'))==(5040,5040,0)
            and gate['native_mutation_witnesses']['all_detected'] and gate['q_free_mutation_witness']['detected'],
            'complete fixed proof acceptance gate required')
    for key in ('producer_outer','review_outer'):
        outer=gate[key];require(outer['raw_source_stable'] and len(outer['runs'])==1 and
            outer['runs'][0]['actual_exit_observed'] and outer['runs'][0]['returncode']==0,'fixed proof outer completion gate')
    return {'manifest_sha256':source['files'][name]['raw_sha256'],'producer':PRODUCER,'verifier':VERIFIER}


def require_exit(observed,path):
    require(observed['status']=='exited' and observed['actual_exit_observed'] and observed['returncode']==0
            and not observed['failures'] and observed['automatic_retries']==0,'fixed cohort child failed; saved first attempt retained')
    require((path/'stderr.bin').stat().st_size==0,'fixed cohort child had stderr')


def paired_baseline(source):
    directory='benchmarks/results/native-dyadic-two-sweep-accepted-v1'
    name=f'{directory}/manifest.json'
    raw=(ROOT/name).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==source['files'][name]['raw_sha256'],
            'accepted two-pass manifest source drift')
    baseline=exact_json(raw)
    require(baseline['status']=='accepted_scoped_two_sweep_training_and_replay' and
            baseline['source_head']==TWO_PASS_HEAD and baseline['training_invocations']==1 and
            baseline['operator']['actual_exit_observed'] and baseline['operator']['returncode']==0 and
            baseline['operator']['raw_source_stable'], 'accepted two-pass baseline required')
    name=f'{directory}/evidence.zip'
    archive=ROOT/name
    identity=baseline['archive']
    require(identity['path']=='evidence.zip' and 0<archive.stat().st_size==identity['bytes']<=50<<20 and
            sha(archive)==identity['sha256']==source['files'][name]['raw_sha256'],
            'accepted two-pass archive identity differs')
    return archive,baseline


def compare_paired_output(path,archive,baseline):
    """Compare every data byte against the original saved two-pass output."""
    member='cohort/train/stdout.bin'
    with ZipFile(archive) as zipped, path.open('rb') as new:
        require(zipped.getinfo(member).file_size==TOTAL_BYTES,'two-pass artifact size')
        process_member='cohort/train/process.json'
        require(zipped.getinfo(process_member).file_size<=65536,'two-pass process receipt size')
        process=exact_json(zipped.read(process_member))
        require(process['actual_exit_observed'] and process['returncode']==0 and
                type(process['duration_seconds']) in (int,float) and 0<process['duration_seconds']<=300,
                'two-pass process receipt differs')
        original_hash=hashlib.sha256()
        numeric_hash=hashlib.sha256()
        with zipped.open(member) as original:
            remaining=NUMERIC_BYTES
            while remaining:
                count=min(remaining,1<<20)
                old_bytes=original.read(count)
                require(len(old_bytes)==count and new.read(count)==old_bytes,
                        f'paired numeric output differs at or after byte {NUMERIC_BYTES-remaining}')
                original_hash.update(old_bytes)
                numeric_hash.update(old_bytes)
                remaining-=count
            footer=original.read(TOTAL_BYTES-NUMERIC_BYTES)
            require(len(footer)==TOTAL_BYTES-NUMERIC_BYTES and footer.startswith(b'OPLDEND1') and
                    not original.read(1),'two-pass artifact footer')
            original_hash.update(footer)
    digest=original_hash.hexdigest()
    require(digest==baseline['saved_replay']['saved_output_sha256'],'two-pass artifact SHA-256 differs')
    return {'baseline_head':TWO_PASS_HEAD,'baseline_output_sha256':digest,
            'baseline_native_process_seconds':process['duration_seconds'],
            'equal_numeric_bytes':NUMERIC_BYTES,'numeric_sha256':numeric_hash.hexdigest()}


def check_verifier_bootstrap(path,source):
    receipt=exact_json(path.read_bytes())
    name='scripts/run_virtual_frozen_source_only.py'
    require(receipt['entry_module']=='scripts.verify_virtual_dyadic_training' and receipt['root']==str(ROOT) and
            receipt['interpreter']==require_source_bootstrap(ROOT,source)['interpreter'] and
            receipt['trusted_first_stage']=={'bootstrap_path':str(ROOT/name),'bootstrap_sha256':source['files'][name]['raw_sha256'],
                'command_sha256':hashlib.sha256(FIRST_STAGE.encode()).hexdigest()},'saved verifier final runtime/bootstrap identity')
    compiled=receipt['compiled']
    require({name,'scripts/verify_virtual_dyadic_training.py','tests/virtual_dyadic_training_reference.py'}<=set(compiled) and
            all(key in source['files'] and source['files'][key]['raw_sha256']==value for key,value in compiled.items()) and
            receipt['initial_cache_scan']['project_bytecode_files']==receipt['final_cache_scan']['project_bytecode_files']==0,
            'saved verifier executed source closure differs')
    return len(compiled)


def run(output,expected_head,*,train=False,paired=False,packed=False):
    require(require_source_bootstrap(ROOT)['interpreter']['optimize']==0,'fixed cohort requires normal source-only parent')
    require(all(type(flag) is bool for flag in (train,paired,packed)),'explicit fixed cohort mode')
    paired=paired or packed
    suffix='_PACKED' if packed else ('_PAIRED' if paired else '')
    require(_git(ROOT,['rev-parse','HEAD']).decode().strip()==expected_head,'fixed cohort source HEAD differs')
    output=Path(output).absolute()
    unlinked_path(output.parent)
    require(not output.is_relative_to(ROOT) and shutil.disk_usage(output.parent).free>=ARTIFACT_ALLOWANCE,
            'fixed cohort external evidence admission')
    claim=RunClaim(output,expected_head)
    started=time.perf_counter()
    entered=0
    try:
        source=capture_source(ROOT,snapshot_directory=output/'source')
        require(source['head']==expected_head,'fixed cohort committed capture differs')
        require_source_bootstrap(ROOT,source)
        save(output/'source.json',source)
        gate=require_frozen_gate(source)
        save(output/'fixed-proof-gate.json',gate)
        if paired:
            baseline_archive,baseline=paired_baseline(source)
        build_dir=output/'build'
        manifest=build(build_dir,target=TARGET)
        bind_build(manifest,source,TARGET,output/'source',build_dir)
        executable=Path(manifest['executable'])
        build_path=build_dir/'native-exact-build-manifest.json'
        build_hash=sha(build_path)
        def observed(mode):
            require(sha(build_path)==build_hash,'fixed build manifest changed before probe')
            bind_build(manifest,source,TARGET,output/'source',build_dir)
            directory=output/mode.lower()
            receipt=run_bounded_dyadic_probe([str(executable)],mode,directory)
            save(directory/'binary-identity.json',{'before_sha256':manifest['executable_sha256'],
                'after_sha256':sha(executable),'build_manifest_sha256':sha(build_path)})
            require_exit(receipt,directory)
            require(sha(build_path)==build_hash,'fixed build manifest changed after probe')
            bind_build(manifest,source,TARGET,output/'source',build_dir)
            return directory,receipt
        admitted,_=observed('ADMIT'+suffix)
        admission=validate_admission(exact_json((admitted/'stdout.bin').read_bytes()),paired=paired,packed=packed)
        save(output/'admission.json',admission)
        verify_source(ROOT,source)
        result={'head':expected_head,'mode':'train' if train else 'admit','admission':admission,
                'training_invocations':0,'fixed_proof_gate':gate,'scope':'fixed reduced PROOF9/T2 only',
                'outer_exit_and_final_bootstrap':'required separately'}
        if train:
            entered=1
            trained,process=observed('TRAIN'+suffix)
            raw=trained/'stdout.bin'
            digest=process['streams'][0]['sha256']
            require(raw.stat().st_size==TOTAL_BYTES and sha(raw)==digest,'saved binary byte identity after training')
            verify_source(ROOT,source)
            if paired:
                comparison=compare_paired_output(raw,baseline_archive,baseline)
                save(output/'paired-numeric-comparison.json',comparison)
            entry='scripts.verify_virtual_dyadic_training'
            bootstrap=ROOT/'scripts/run_virtual_frozen_source_only.py'
            receipt_path=output/'saved-review-bootstrap.json'
            command=source_only_command(bootstrap,source['files']['scripts/run_virtual_frozen_source_only.py']['raw_sha256'],
                entry,receipt_path,['--saved',str(raw),'--sha256',digest])
            if paired:
                command.append('--paired')
            save(output/'saved-review-command.json',command)
            replay_dir=output/'saved-review'
            observed_replay=run_bounded_child(command,b'',replay_dir,stdout_limit=65536)
            require_exit(observed_replay,replay_dir)
            compiled=check_verifier_bootstrap(receipt_path,source)
            numeric=exact_json((replay_dir/'stdout.bin').read_bytes())
            require(numeric['status']=='saved_two_sweep_exact_replay_pass' and numeric['saved_output_sha256']==digest
                    and numeric['work_plan']==admission['component_work'] and numeric['parent_work_plan']==admission['parent_work']
                    and numeric['planned_entries']==admission['entries'] and numeric['planned_payload_bits']==admission['payload_bits']
                    and numeric['showdown_contractions_per_pass']==admission['showdown_contractions_per_pass']
                    and numeric['hidden_completion_candidates_per_pass']==admission['hidden_completion_candidates_per_pass']
                    and numeric['native_producer_calls']==0,
                    'saved replay result differs from admitted producer')
            result.update(training_invocations=1,saved_only_replay=numeric,saved_review_compiled_sources=compiled,
                          training_stdout_sha256=digest,quality_gate=None)
            if paired:
                original=sum(baseline['saved_replay']['work_actual'].values())
                actual=sum(numeric['work_actual'].values())
                require(numeric['public_walks_per_sweep']==1 and actual<original,
                        'paired traversal must use fewer modeled work units')
                comparison.update(baseline_work=original,paired_work=actual,modeled_work_saved=original-actual)
                comparison['native_process_seconds']=process['duration_seconds']
                if os.name=='nt':
                    memory=process.get('memory',{})
                    require(memory.get('source')=='windows.K32GetProcessMemoryInfo' and
                            all(type(memory.get(key)) is int and memory[key]>0 for key in
                                ('peak_working_set_bytes','peak_commit_bytes')),
                            'paired Windows process memory measurement missing')
                    comparison['native_process_memory']=memory
                result['paired_comparison']=comparison
        result['source_final']=verify_source(ROOT,source)
        result['duration_seconds']=time.perf_counter()-started
        scan_project_caches(ROOT)
        require_source_bootstrap(ROOT,source)
        bind_build(manifest,source,TARGET,output/'source',build_dir)
        require(sum(x.stat().st_size for x in output.rglob('*') if x.is_file())<=ARTIFACT_ALLOWANCE-(1<<20),
                'fixed cohort actual artifact allowance')
        save(output/'result.json',result)
        claim.finish('complete',{'result':'result.json','training_invocations':entered,'outer_exit_and_final_bootstrap':'required separately'})
        return result
    except BaseException as error:
        claim.finish('failed',{'first_error':type(error).__name__+': '+str(error)[:2048],
                               'training_invocations_entered':entered,'traceback':traceback.format_exc()[-16384:]})
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--expected-head',required=True)
    parser.add_argument('--train',action='store_true')
    parser.add_argument('--paired',action='store_true')
    parser.add_argument('--packed-averages',action='store_true')
    args=parser.parse_args()
    print(json.dumps(run(args.output,args.expected_head,train=args.train,paired=args.paired,
        packed=args.packed_averages),sort_keys=True))


if __name__=='__main__':main()
