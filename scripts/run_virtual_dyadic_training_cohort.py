"""Source-frozen dyadic T2 admission or one native run with saved-only replay."""
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
from scripts.verify_virtual_dyadic_training import SPLIT_BYTES, SPLIT_IMAGE_BYTES, SPLIT_IMAGE_NAMES
from scripts.verify_virtual_dyadic_training import TEN_CARD_IMAGE_BYTES, TEN_CARD_SHAPE, TEN_CARD_SPLIT_BYTES
from tests.virtual_frozen_run_control import RunClaim, run_bounded_child, run_bounded_dyadic_probe
from tests.virtual_frozen_saved_review import unlinked_path
from tests.virtual_frozen_source_guard import _git, capture_source, verify_source, require_source_bootstrap
from tests.virtual_dyadic_stage_schedule import stage_schedule

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


def validate_ten_admission(receipt, *, buffered=False, virtual_zero=False):
    expected={
        'protocol':'DYADIC_T2_V1','status':'ADMITTED','training_invocations':0,'target_passes':0,
        'completed_sweeps':0,'rank_calls':0,'literal_nodes':1105,'requested_sweeps':2,
        'H':12,'M':1,'D_bits':637,'value_bits':644,'normalizer':29,'d5':120,
        'output_bytes':TEN_CARD_SPLIT_BYTES,'checkpoint_image_bytes':TEN_CARD_IMAGE_BYTES,
        'split_checkpoint':True,'ten_card':True,'expected_rank_calls':42,
        'first_uniform_exponent':420,'max_actor_depth':[6,7],
        'prefix_counts':[1,46,156,340],'prefix_supported_rows':[[2,2],[56,50],[176,160],[360,340]],
        'showdown_contractions_per_pass':103_020,'hidden_completion_candidates_per_pass':70_912,
        'public_walks_per_sweep':1,**dict(zip(SHAPE,TEN_CARD_SHAPE)),
        'packed_average_limbs':1_295_812,'packed_average_work':88_688_480,
        'packed_regret_limbs':1_666_910,'packed_regret_work':151_359_736,
        'scaled_average_build_work':26_064_384,'sealed_menu_count':146,'sealed_token_count':371,
        'paging_work':130_214_136,'page_image_words':2_962_722,'page_words':4096,
        'page_cache_pages':16,'page_cache_banks':2,'page_read_word_limit':11_000_000,
        'page_write_word_limit':8_888_166,'page_request_limit':3_091_726,'page_resident_bytes':894_773,
        'directory_work':11_442_816,'directory_record_bytes':32,'directory_index_slots':524_288,
        'rank_cache_planes':17,'rank_lookup_work_per_query':34,
        'entries':1_551_317,'payload_bits':1_182_148_028,'parent_allowance':761_502_696,
        'planned_total_work':2_102_190_180,'quantizer_terms':[51_633_888,178_125_664,283_541_864],
        'component_work':dict(template=42_556_544,chance=447_066_576,history=95_940_344,
                              state=289_632_424,quantizer=513_301_416,parent=713_692_876),
        'parent_work':dict(geometry=3_000_000,visit=9_246_272,support=18_519_680,reach=50_851_556,
                           value_add=49_700_420,terminal_scale=150_196_888,average=116_524_928,
                           route=299_862_360,output=15_790_772),
    }
    if buffered or virtual_zero:
        extra_work=23_982_922-(127_424 if virtual_zero else 0)
        expected.update(page_stage_split_words=1_295_812,page_write_request_limit=18_836 if virtual_zero else 19_560,
                        page_resident_bytes=961_349,entries=1_559_639)
        expected['paging_work']+=extra_work
        expected['parent_work']['route']+=extra_work
        expected['component_work']['parent']+=extra_work
        expected['planned_total_work']+=extra_work
    if virtual_zero:
        expected.update(page_virtual_initial_zero=True,page_write_word_limit=5_925_444,
                        page_read_word_limit=6_130_244)
    require(type(receipt) is dict and receipt.keys()==expected.keys()|{'actual_admission_work'} and
            all(type(receipt[key]) is type(value) and receipt[key]==value for key,value in expected.items()),
            'ten-card admission differs from the independent fixed census')
    actual=receipt['actual_admission_work']
    require(type(actual) is int and 42_556_544<=actual<=45_556_544,'ten-card admission geometry work')
    return receipt


def validate_admission(receipt,*,paired=False,packed=False,compact=False,scaled=False,sealed=False,paged=False,
                       directory=False,rank_sets=False,split=False,ten_card=False,ten_buffered=False,ten_virtual_zero=False):
    if ten_card or ten_buffered or ten_virtual_zero:
        return validate_ten_admission(receipt,buffered=ten_buffered,virtual_zero=ten_virtual_zero)
    require(type(receipt) is dict and 'ten_card' not in receipt,'ten-card receipt for earlier profile')
    rank_sets=rank_sets or split
    directory=directory or rank_sets
    paged=paged or directory
    sealed=sealed or paged
    scaled=scaled or sealed
    compact=compact or scaled
    fixed={'protocol':'DYADIC_T2_V1','status':'ADMITTED','training_invocations':0,'target_passes':0,
           'completed_sweeps':0,'rank_calls':0,'literal_nodes':1105,'requested_sweeps':2,'H':12,'M':1,
           'D_bits':635,'value_bits':642,'normalizer':29,'d5':20,'output_bytes':TOTAL_BYTES,
           'expected_rank_calls':140,'first_uniform_exponent':420,'max_actor_depth':[6,7],
           'prefix_counts':[1,25,56,60],'prefix_supported_rows':[[2,2],[29,26],[60,56],[60,60]],
           'showdown_contractions_per_pass':EXPECTED_TERMINAL_COMPLETIONS[0],
           'hidden_completion_candidates_per_pass':EXPECTED_TERMINAL_COMPLETIONS[1],
           **dict(zip(SHAPE,EXPECTED_SHAPE))}
    if paired or packed or compact:
        fixed['public_walks_per_sweep']=1
    if packed or compact:
        fixed['packed_average_limbs']=258_694
        fixed['packed_average_work']=18_004_728 if scaled else 23_123_160
        fixed['entries']=841_925 if paged else (1_980_339 if compact else 1_351_755)
    if compact:
        fixed['packed_regret_limbs']=348_036
        fixed['packed_regret_work']=31_450_320
    if scaled:
        fixed['scaled_average_build_work']=5_271_476
    if sealed:
        fixed['sealed_menu_count']=146
        fixed['sealed_token_count']=371
    if paged:
        fixed.update(paging_work=30_508_644,page_image_words=606_730,page_words=4096,page_cache_pages=16,
            page_cache_banks=2,page_read_word_limit=3_500_000,page_write_word_limit=1_820_190,
            page_request_limit=872_460,page_resident_bytes=600_274)
    if directory:
        fixed.update(entries=500_045,directory_work=2_344_320,directory_record_bytes=32,
                     directory_index_slots=131_072)
    if rank_sets:
        fixed.update(expected_rank_calls=7,rank_cache_planes=3,rank_lookup_work_per_query=6)
    if split:
        fixed.update(output_bytes=SPLIT_BYTES,split_checkpoint=True,checkpoint_image_bytes=SPLIT_IMAGE_BYTES,
                     paging_work=26_786_148,page_read_word_limit=2_250_000,page_request_limit=639_804)
    require(type(receipt) is dict and all(type(receipt.get(k)) is type(v) and receipt[k]==v for k,v in fixed.items()),
            'fixed admission census or zero-call receipt mismatch')
    for name,keys in [('component_work',FAMILIES),('parent_work',PARENT)]:
        plan=receipt.get(name)
        require(type(plan) is dict and set(plan)==set(keys) and all(type(v) is int and 0<=v<=500_000_000 for v in plan.values()),
                'fixed admission work categories differ')
    component=receipt['component_work']
    if rank_sets:
        require(component['chance']==79_458_332,'rank-set chance allowance differs')
    else:
        require(not {'rank_cache_planes','rank_lookup_work_per_query'} & receipt.keys(),
                'rank-set receipt for earlier profile')
    if split:
        require(receipt['planned_total_work']==460_626_716,'split checkpoint work allowance differs')
    else:
        require(not {'split_checkpoint','checkpoint_image_bytes'} & receipt.keys(),
                'split checkpoint receipt for earlier profile')
    require(type(receipt.get('planned_total_work')) is int and 0<sum(component.values())==receipt['planned_total_work']<=500_000_000,
            'fixed admission whole work exceeds allowance')
    require(component['parent']==sum(receipt['parent_work'].values()),'fixed admission parent work sum')
    if packed or compact:
        require(receipt['packed_average_work']<=receipt['parent_work']['average'], 'packed average codec work missing')
    else:
        require('packed_average_limbs' not in receipt and 'packed_average_work' not in receipt,
                'packed codec receipt for dense storage')
    if scaled:
        require(receipt['packed_average_work']+receipt['scaled_average_build_work']<=receipt['parent_work']['average'],
                'scaled average work missing')
    else:
        require('scaled_average_build_work' not in receipt,'scaled average receipt for earlier storage profile')
    if not sealed:
        require(not {'sealed_menu_count','sealed_token_count'} & receipt.keys(),
                'sealed menu receipt for earlier storage profile')
    if paged:
        require(receipt['paging_work']+(receipt['directory_work'] if directory else 0)<=receipt['parent_work']['route'],
                'paged bookkeeping work missing')
    else:
        require(not any(key=='paging_work' or key.startswith('page_') for key in receipt),
                'paged receipt for earlier storage profile')
    if not directory:
        require(not any(key.startswith('directory_') for key in receipt),'compact directory receipt for earlier profile')
    if compact:
        allowance=receipt.get('parent_allowance')
        non_parent=sum(value for name,value in component.items() if name!='parent')
        require(type(allowance) is int and component['parent']<=allowance==500_000_000-non_parent
                and receipt['packed_regret_work']<=receipt['parent_work']['route'],
                'compact strategy allowance does not compose')
    else:
        require(not {'packed_regret_limbs','packed_regret_work','parent_allowance'} & receipt.keys(),
                'compact regret receipt for earlier storage profile')
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


def verify_paging(directory,admission,stage=None):
    path=unlinked_path(directory/'paging.json')
    require(path.is_file() and path.stat().st_size<=65536,'paged training receipt path or size')
    receipt=exact_json(path.read_bytes())
    fixed={'read_calls':639_804,'stage_calls':232_656,'logical_read_words':3_381_686,
           'write_words':1_820_190,'physical_write_requests':232_805,'completed_sweeps':2}
    split=admission.get('split_checkpoint',False)
    if split:
        fixed.update(read_calls=407_148,logical_read_words=2_168_226)
    page_references=407_565 if split else 640_455
    if admission.get('ten_card',False):
        fixed.update(read_calls=1_967_462,stage_calls=1_124_264,logical_read_words=10_555_076,
                     write_words=8_888_166,physical_write_requests=1_124_988)
        page_references=1_969_550
    if stage is not None:
        require(stage['average_words']==admission['page_stage_split_words'] and
                stage['image_words']==admission['page_image_words'] and
                stage['batched_write_calls']==admission['page_write_request_limit'],
                'independent buffered write schedule differs from admission')
        fixed.update(stage_calls=stage['per_sweep_stage_calls']*stage['sweeps'],
                     write_words=stage['written_words'],physical_write_requests=stage['batched_write_calls'])
    if admission.get('page_virtual_initial_zero',False):
        require(stage is not None and not stage['initialization_calls']
                and stage['physical_read_words']==admission['page_read_word_limit']
                and stage['written_words']==admission['page_write_word_limit']
                and stage['logical_read_calls']+fixed['stage_calls']==admission['page_request_limit'],
                'independent virtual-zero pager schedule differs from admission')
        fixed.update(read_calls=stage['logical_read_calls'],logical_read_words=stage['logical_read_words'],
                     synthetic_read_calls=stage['virtual_read_calls'],synthetic_read_words=stage['virtual_read_words'],
                     read_words=stage['physical_read_words'],physical_read_requests=stage['cache_misses'],
                     cache_hits=stage['cache_hits'],cache_misses=stage['cache_misses'])
        page_references=stage['cache_hits']+stage['cache_misses']
    counts=('read_words','physical_read_requests','cache_hits','cache_misses')
    require(type(receipt) is dict and set(receipt)==set(fixed)|set(counts)
            and all(type(receipt[key]) is int and receipt[key]==value for key,value in fixed.items())
            and all(type(receipt[key]) is int and receipt[key]>=0 for key in counts), 'paged lifecycle receipt differs')
    require(0<receipt['read_words']<=admission['page_read_word_limit']
            and receipt['physical_read_requests']==receipt['cache_misses']
            and receipt['cache_hits']+receipt['cache_misses']==page_references,
            'paged physical reads or cache counts differ')
    files={}
    for name in ('committed.bin','staged.bin'):
        image=unlinked_path(directory/name)
        require(image.is_file() and image.stat().st_size==8*admission['page_image_words'], 'paged file extent differs')
        files[name]={'bytes':image.stat().st_size,'sha256':sha(image)}
    require(set(item.name for item in directory.iterdir())==set(files)|{'paging.json'},'unexpected paging artifact')
    return {'counts':receipt,'images':files}


def compare_buffered_ten(path,source,paging,images,*,virtual_zero=False):
    variant='buffered-ten-card' if virtual_zero else 'ten-card'
    directory=f'benchmarks/results/native-dyadic-{variant}-accepted-v1'
    manifest=f'{directory}/manifest.json'
    raw=(ROOT/manifest).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==source['files'][manifest]['raw_sha256'],
            'ten-card baseline manifest source drift')
    baseline=exact_json(raw)
    operator=baseline['operator']
    status='accepted_buffered_ten_card_training_and_replay' if virtual_zero else 'accepted_ten_card_training_and_replay'
    head='753b6583fd282393fb7272126d4c391399123710' if virtual_zero else 'bb46feb27a6a92f3a1cefbc8ad152ffaedead86d'
    require(baseline['status']==status and baseline['source_head']==head and
            baseline['training_invocations']==1 and operator['actual_exit_observed'] and
            operator['returncode']==0 and operator['raw_source_stable'],'accepted ten-card baseline required')
    replay=baseline['saved_only_replay'] if virtual_zero else baseline['saved_replay']
    old_counts=baseline['paging']['counts'] if virtual_zero else baseline['comparison']['paging']
    new_counts=paging['counts']
    invariant=('read_calls','logical_read_words','stage_calls','completed_sweeps') if virtual_zero else (
        key for key in new_counts if key!='physical_write_requests')
    require(images==replay['checkpoint_images'] and
            all(old_counts[key]==new_counts[key] for key in invariant),
            'buffered checkpoint or paging parity differs')
    archive_name=f'{directory}/evidence.zip'
    archive=ROOT/archive_name
    identity=baseline['archive']
    require(identity['path']=='evidence.zip' and 0<archive.stat().st_size==identity['bytes']<=50<<20 and
            sha(archive)==identity['sha256']==source['files'][archive_name]['raw_sha256'],
            'ten-card baseline archive identity differs')
    member='cohort/train_ten_buffered/stdout.bin' if virtual_zero else 'cohort/train_ten/stdout.bin'
    footer_bytes=8+64*8
    numeric_bytes=TEN_CARD_SPLIT_BYTES-footer_bytes
    numeric_hash=hashlib.sha256()
    original_hash=hashlib.sha256()
    with ZipFile(archive) as zipped, path.open('rb') as buffered:
        require(zipped.getinfo(member).file_size==TEN_CARD_SPLIT_BYTES,'ten-card baseline stream size differs')
        with zipped.open(member) as direct:
            for at in range(0,numeric_bytes,1<<20):
                count=min(numeric_bytes-at,1<<20)
                data=direct.read(count)
                require(len(data)==count and buffered.read(count)==data,
                        f'buffered numeric output differs at or after byte {at}')
                numeric_hash.update(data)
                original_hash.update(data)
            footer=direct.read(footer_bytes)
            require(len(footer)==footer_bytes and footer.startswith(b'OPLDTP02') and not direct.read(1),
                    'ten-card baseline stream footer differs')
            original_hash.update(footer)
    digest=original_hash.hexdigest()
    require(digest==replay['saved_output_sha256'],'ten-card baseline stream SHA-256 differs')
    if virtual_zero:
        return {'baseline_source_head':head,'baseline_stream_sha256':digest,
                'numeric_bytes':numeric_bytes,'numeric_sha256':numeric_hash.hexdigest(),
                'exact_checkpoint_images':images,'baseline_paging':old_counts,'virtual_zero_paging':new_counts,
                'baseline_native_observation':baseline['buffered_comparison']['buffered_native_observation']}
    return {'direct_source_head':baseline['source_head'],'direct_stream_sha256':digest,
            'numeric_bytes':numeric_bytes,'numeric_sha256':numeric_hash.hexdigest(),
            'exact_checkpoint_images':images,'direct_write_calls':old_counts['physical_write_requests'],
            'buffered_write_calls':new_counts['physical_write_requests'],
            'direct_native_observation':baseline['comparison']['native_observation']}


def run(output,expected_head,*,train=False,paired=False,packed=False,compact=False,scaled=False,sealed=False,paged=False,
        directory=False,rank_sets=False,split=False,ten_card=False,ten_buffered=False,ten_virtual_zero=False):
    require(require_source_bootstrap(ROOT)['interpreter']['optimize']==0,'fixed cohort requires normal source-only parent')
    modes=(paired,packed,compact,scaled,sealed,paged,directory,rank_sets,split,ten_card,ten_buffered,ten_virtual_zero)
    require(type(train) is bool and all(type(flag) is bool for flag in modes) and sum(modes)<=1,
            'explicit fixed cohort mode')
    suffix=next((name for flag,name in zip(modes,('_PAIRED','_PACKED','_COMPACT','_SCALED','_SEALED','_PAGED',
                                                 '_DIRECTORY','_RANK_SETS','_SPLIT','_TEN','_TEN_BUFFERED',
                                                 '_TEN_VIRTUAL_ZERO')) if flag),'')
    paired=any(modes)
    ten_card=ten_card or ten_buffered or ten_virtual_zero
    split=split or ten_card
    uses_paging=paged or directory or rank_sets or split
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
        if paired and not split:
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
            command=[str(executable)]
            if mode.startswith('TRAIN') and uses_paging:
                scratch=output/'page-images'
                require(str(scratch).isascii() and not scratch.exists(),'fresh ASCII paged image directory required')
                command.append(str(scratch))
            receipt=run_bounded_dyadic_probe(command,mode,directory)
            save(directory/'binary-identity.json',{'before_sha256':manifest['executable_sha256'],
                'after_sha256':sha(executable),'build_manifest_sha256':sha(build_path)})
            require_exit(receipt,directory)
            require(sha(build_path)==build_hash,'fixed build manifest changed after probe')
            bind_build(manifest,source,TARGET,output/'source',build_dir)
            return directory,receipt
        admitted,_=observed('ADMIT'+suffix)
        admission=validate_admission(exact_json((admitted/'stdout.bin').read_bytes()),paired=paired,
            packed=packed,compact=compact,scaled=scaled,sealed=sealed,paged=paged,directory=directory,
            rank_sets=rank_sets,split=split,ten_card=ten_card,ten_buffered=ten_buffered,ten_virtual_zero=ten_virtual_zero)
        save(output/'admission.json',admission)
        verify_source(ROOT,source)
        result={'head':expected_head,'mode':'train' if train else 'admit','admission':admission,
                'training_invocations':0,'fixed_proof_gate':gate,
                'scope':'fixed reduced PROOF10/T2 only' if ten_card else 'fixed reduced PROOF9/T2 only',
                'outer_exit_and_final_bootstrap':'required separately'}
        if train:
            schedule=stage_schedule(ten_card=True,virtual_zero=ten_virtual_zero) if ten_buffered or ten_virtual_zero else None
            entered=1
            trained,process=observed('TRAIN'+suffix)
            raw=trained/'stdout.bin'
            digest=process['streams'][0]['sha256']
            require(raw.stat().st_size==admission['output_bytes'] and sha(raw)==digest,
                    'saved binary byte identity after training')
            verify_source(ROOT,source)
            if paired and not split:
                comparison=compare_paired_output(raw,baseline_archive,baseline)
                save(output/'paired-numeric-comparison.json',comparison)
            entry='scripts.verify_virtual_dyadic_training'
            bootstrap=ROOT/'scripts/run_virtual_frozen_source_only.py'
            receipt_path=output/'saved-review-bootstrap.json'
            command=source_only_command(bootstrap,source['files']['scripts/run_virtual_frozen_source_only.py']['raw_sha256'],
                entry,receipt_path,['--saved',str(raw),'--sha256',digest])
            if paired:
                command.append('--paired')
            if rank_sets or split:
                command.append('--rank-sets')
            if ten_card:
                command.append('--ten-card')
            if split:
                pages=output/'page-images'
                paging=verify_paging(pages,admission,schedule)
                images=[{'name':name,**paging['images'][name]} for name in SPLIT_IMAGE_NAMES]
                result['checkpoint_inputs']={'stream':{'bytes':admission['output_bytes'],'sha256':digest},
                                             'sweep_images':images}
                save(output/'checkpoint-inputs.json',result['checkpoint_inputs'])
                if ten_buffered or ten_virtual_zero:
                    comparison=compare_buffered_ten(raw,source,paging,images,virtual_zero=ten_virtual_zero)
                    label='virtual_zero' if ten_virtual_zero else 'buffered'
                    comparison[label+'_native_observation']={'duration_seconds':process['duration_seconds'],
                                                             'memory':process.get('memory')}
                    result[label+'_comparison']=comparison
                    result['independent_stage_schedule']=schedule
                command.extend(['--page-images',str(pages),'--sweep-image-sha256',*(image['sha256'] for image in images)])
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
                    and (not paired or numeric['public_walks_per_sweep']==1)
                    and numeric['native_producer_calls']==0,
                    'saved replay result differs from admitted producer')
            result.update(training_invocations=1,saved_only_replay=numeric,saved_review_compiled_sources=compiled,
                          training_stdout_sha256=digest,quality_gate=None)
            if uses_paging:
                result['paging']=verify_paging(output/'page-images',admission,schedule)
            if split:
                require(numeric['checkpoint_images']==images and result['paging']==paging and sha(raw)==digest,
                        'split checkpoint bytes changed after saved replay')
            if paired and not split:
                original=sum(baseline['saved_replay']['work_actual'].values())
                actual=sum(numeric['work_actual'].values())
                require(numeric['public_walks_per_sweep']==1
                        and (compact or scaled or sealed or uses_paging or actual<original),
                        'paired traversal or mode-specific work comparison differs')
                comparison.update(baseline_work=original,paired_work=actual)
                if compact or scaled or sealed or uses_paging:
                    comparison['modeled_work_delta_from_two_pass']=actual-original
                else:
                    comparison['modeled_work_saved']=original-actual
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
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--paired',action='store_true')
    modes.add_argument('--packed-averages',action='store_true')
    modes.add_argument('--compact-strategy',action='store_true')
    modes.add_argument('--scaled-averages',action='store_true')
    modes.add_argument('--sealed-menus',action='store_true')
    modes.add_argument('--paged-strategy',action='store_true')
    modes.add_argument('--compact-directory',action='store_true')
    modes.add_argument('--rank-sets',action='store_true')
    modes.add_argument('--split-checkpoint',action='store_true')
    modes.add_argument('--ten-card',action='store_true')
    modes.add_argument('--ten-buffered',action='store_true')
    modes.add_argument('--ten-virtual-zero',action='store_true')
    args=parser.parse_args()
    print(json.dumps(run(args.output,args.expected_head,train=args.train,paired=args.paired,
        packed=args.packed_averages,compact=args.compact_strategy,scaled=args.scaled_averages,
        sealed=args.sealed_menus,paged=args.paged_strategy,directory=args.compact_directory,
        rank_sets=args.rank_sets,split=args.split_checkpoint,ten_card=args.ten_card,
        ten_buffered=args.ten_buffered,ten_virtual_zero=args.ten_virtual_zero),sort_keys=True))


if __name__=='__main__':main()
