"""Source-frozen dyadic T2 admission or one native run with saved-only replay."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from fractions import Fraction
import shutil
import struct
import time
import traceback
from zipfile import ZipFile

from scripts.build_native_exact_four_street import build
from scripts.run_native_exact_reach_conformance import bind_build, save, sha
from scripts.run_virtual_frozen_source_only import FIRST_STAGE, source_only_command, scan_project_caches
from scripts.verify_virtual_dyadic_training import EXPECTED_SHAPE, EXPECTED_TERMINAL_COMPLETIONS, FAMILIES, PARENT, SHAPE, TOTAL_BYTES, require
from scripts.verify_virtual_dyadic_training import SPLIT_BYTES, SPLIT_IMAGE_BYTES, SPLIT_IMAGE_NAMES
from scripts.verify_virtual_dyadic_training import TEN_CARD_IMAGE_BYTES, TEN_CARD_SHAPE, TEN_CARD_SPLIT_BYTES
from tests.virtual_frozen_run_control import RunClaim, run_bounded_child, run_bounded_dyadic_probe, run_bounded_quality32_replay, run_bounded_linear32_replay
from tests.virtual_frozen_saved_review import unlinked_path
from tests.virtual_frozen_source_guard import _git, capture_source, verify_source, require_source_bootstrap
from tests.virtual_dyadic_stage_schedule import stage_schedule
from tests.virtual_dyadic_directory_trace import directory_trace
from tests.virtual_dyadic_sweep_capture import sweep_stream_contract
from tests.virtual_dyadic_training_reference import Fixture
from scripts.verify_virtual_dyadic_training import compact_scales
from scripts.verify_virtual_dyadic_training import phase_payload_bits, rank_index_costs
from tests.virtual_dyadic_rank_trace import rank_trace

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


def validate_ten_admission(receipt, *, buffered=False, virtual_zero=False, ordered_state=False,row_coverage=False,
                           shared_policy=False, paged_directory=False):
    shared_policy=shared_policy or paged_directory
    row_coverage=row_coverage or shared_policy
    ordered_state=ordered_state or row_coverage
    virtual_zero=virtual_zero or ordered_state
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
    if ordered_state:
        path_work=3_814_272
        expected.update(ordered_registration=True,export_workspace_reused=True,registration_path_work=path_work,
                        directory_index_slots=0,entries=1_159_382)
        expected['component_work']['history']+=path_work
        expected['planned_total_work']+=path_work
        expected['parent_allowance']-=path_work
    if row_coverage:
        bitmap_reset=370_344
        expected.update(page_state_row_coverage=True,page_resident_bytes=591_008,entries=1_113_089)
        expected['paging_work']-=bitmap_reset
        expected['parent_work']['route']-=bitmap_reset
        expected['component_work']['parent']-=bitmap_reset
        expected['planned_total_work']-=bitmap_reset
    if shared_policy:
        spill_work=15_056_976
        expected.update(shared_policy=True,streamed_average=True,export_workspace_reused=False,entries=832_287,
                        policy_spill_work=spill_work,policy_spill_word_limit=161_870,
                        policy_spill_read_call_limit=357_588)
        expected['parent_work']['route']+=spill_work
        expected['component_work']['parent']+=spill_work
        expected['planned_total_work']+=spill_work
    if paged_directory:
        # Values independently pinned by the fixture-level forecast; preserve
        # every existing shared-policy field while changing only this profile.
        old_state=expected['component_work']['state']
        old_directory=expected['directory_work']
        expected.update(paged_row_directory=True,row_directory_entries=4608,
                        row_directory_page_limit=7656,row_directory_read_call_limit=1_191_960,
                        entries=360_303,directory_work=24_916_800)
        expected['component_work']['state']=261_025_384
        expected['parent_work']['route']+=24_916_800-old_directory
        expected['component_work']['parent']+=24_916_800-old_directory
        expected['planned_total_work']+=261_025_384-old_state+24_916_800-old_directory
        expected['parent_allowance']+=old_state-261_025_384
        require(expected['planned_total_work']==2_129_413_526,'paged directory work composition')
    require(type(receipt) is dict and receipt.keys()==expected.keys()|{'actual_admission_work'} and
            all(type(receipt[key]) is type(value) and receipt[key]==value for key,value in expected.items()),
            'ten-card admission differs from the independent fixed census')
    actual=receipt['actual_admission_work']
    require(type(actual) is int and 42_556_544<=actual<=45_556_544,'ten-card admission geometry work')
    return receipt


PROOF9_SPLIT_BASELINE='benchmarks/results/native-dyadic-split-checkpoint-accepted-v1'
PROOF9_T3_BASELINE='benchmarks/results/native-dyadic-proof9-three-sweep-accepted-v1'


def validate_bounded_proof9_admission(receipt,sweeps):
    baseline=exact_json((ROOT/PROOF9_SPLIT_BASELINE/'manifest.json').read_bytes())
    expected=dict(validate_admission(baseline['admission'],split=True))
    expected.pop('actual_admission_work')
    expected.update(protocol='DYADIC_T3_V1',proof9_t3=True,requested_sweeps=3,
        output_bytes=2_579_724,entries=269_651,payload_bits=255_270_096,
        packed_average_work=27_007_092,packed_regret_work=47_175_480,
        scaled_average_build_work=7_907_214,registration_path_work=781_440,
        directory_work=6_965_696,directory_index_slots=0,ordered_registration=True,
        export_workspace_reused=False,paged_row_directory=True,row_directory_entries=4608,
        row_directory_page_limit=2122,row_directory_read_call_limit=341_880,
        shared_policy=True,streamed_average=True,policy_spill_work=4_662_064,
        policy_spill_word_limit=33_744,policy_spill_read_call_limit=73_260,
        page_virtual_initial_zero=True,page_state_row_coverage=True,page_resident_bytes=591_008,
        page_stage_split_words=258_694,page_write_request_limit=5931,
        page_read_word_limit=2_223_164,page_request_limit=930_624,paging_work=46_986_096,
        general_quantizer_work=78_506_392,sweep_stream=sweep_stream_contract(proof9_sweeps=sweeps),
        component_work=dict(template=42_556_544,chance=124_856_139,history=31_014_848,
                            state=76_104_624,quantizer=182_766_664,parent=239_201_586),
        parent_work=dict(geometry=3_000_000,visit=2_688_356,support=8_265_728,reach=16_176_366,
                         value_add=15_378_930,terminal_scale=46_086_372,average=35_452_290,
                         route=107_584_872,output=4_568_672),
        parent_allowance=292_701_181,planned_total_work=696_500_405)
    work_limit=750_000_000
    if sweeps==4:
        work_limit=950_000_000
        expected.pop('proof9_t3')
        expected.update(protocol='DYADIC_T4_V1',proof9_t4=True,requested_sweeps=4,
            output_bytes=3_045_420,entries=269_667,payload_bits=255_271_120,
            packed_average_work=36_009_456,packed_regret_work=62_900_640,
            scaled_average_build_work=10_542_952,directory_work=8_825_536,
            row_directory_page_limit=2702,row_directory_read_call_limit=439_560,
            policy_spill_work=6_216_064,page_write_request_limit=7908,
            page_write_word_limit=2_426_920,page_read_word_limit=3_203_674,
            page_request_limit=1_221_444,paging_work=62_335_146,
            general_quantizer_work=157_012_784,
            component_work=dict(template=42_556_544,chance=170_253_946,history=37_487_840,
                                state=98_317_056,quantizer=261_273_056,parent=316_063_074),
            parent_work=dict(geometry=3_000_000,visit=3_421_544,support=10_686_848,reach=21_568_488,
                             value_add=20_505_240,terminal_scale=61_448_496,average=47_269_720,
                             route=142_463_642,output=5_699_096),
            parent_allowance=340_111_558,planned_total_work=925_951_516)
    require(type(receipt) is dict and receipt.keys()==expected.keys()|{'actual_admission_work'} and
            all(type(receipt[key]) is type(value) and receipt[key]==value for key,value in expected.items()),
            f'PROOF9 T{sweeps} admission differs from independent fixed census')
    actual=receipt['actual_admission_work']
    require(type(actual) is int and 42_556_544<=actual<=45_556_544,'bounded PROOF9 admission geometry work')
    contract=expected['sweep_stream']
    require(sum(expected['parent_work'].values())==expected['component_work']['parent'] and
            sum(expected['component_work'].values())==expected['planned_total_work'] and
            expected['planned_total_work']+contract['copy_work']<=work_limit and
            expected['entries']<=2_000_000 and
            expected['payload_bits']<=1<<30,'bounded PROOF9 composed transport admission')
    return receipt


def validate_quality32_admission(receipt,*,linear=False):
    """Pin the named Q32 census independently of the native receipt."""
    expected=exact_json((ROOT/'benchmarks/results/native-dyadic-proof9-four-sweep-accepted-v1/manifest.json').read_bytes())['admission']
    expected.pop('proof9_t4');expected.pop('actual_admission_work')
    components=dict(template=42_556_544,chance=395_628_627,history=218_731_616,
                    state=720_265_152,quantizer=1_867_537_648,parent=2_363_985_314)
    expected.update(protocol='DYADIC_T32_V1',proof9_quality32=True,requested_sweeps=32,
        sparse_chance=True,single_division=True,row_batched=True,value_bits=644,
        output_bytes=16_084_908,entries=270_172,payload_bits=255_885_592,
        packed_average_work=288_075_648,packed_regret_work=503_205_120,
        scaled_average_build_work=84_343_616,directory_work=60_901_056,
        row_directory_page_limit=18_942,row_directory_read_call_limit=3_174_600,
        policy_spill_work=49_728_064,page_write_request_limit=63_264,
        page_write_word_limit=19_415_360,page_read_word_limit=30_657_954,
        page_request_limit=3_931_620,paging_work=387_907_074,
        general_quantizer_work=30*59_307_688,quantizer_terms=[10_606_272,32_153_808,45_546_928],
        component_work=components,planned_total_work=sum(components.values()),
        parent_allowance=5_800_000_000-sum(v for k,v in components.items() if k!='parent'),
        parent_work=dict(geometry=3_000_000,visit=23_950_808,support=78_478_208,reach=172_547_904,
                         value_add=164_041_920,terminal_scale=491_587_968,average=378_157_760,
                         route=1_014_867_730,output=37_353_016),
        sweep_stream=sweep_stream_contract(proof9_sweeps=32))
    if linear:
        expected.pop('proof9_quality32')
        expected.update(protocol='DYADIC_L32_V1',proof9_linear32=True,
            average_weight_sum=528,maximum_average_weight=32,
            scaled_average_build_work=90_700_352,quantizer_terms=[10_606_272,32_153_808,45_600_688])
        components['quantizer']+=53_760
        components['parent']+=6_356_736
        expected['parent_work']['average']+=6_356_736
        expected['planned_total_work']=sum(components.values())
        expected['parent_allowance']-=53_760
    require(type(receipt) is dict and receipt.keys()==expected.keys()|{'actual_admission_work'} and
            all(type(receipt[k]) is type(v) and receipt[k]==v for k,v in expected.items()),
            'PROOF9 Q32 admission differs from independent fixed census')
    require(type(receipt['actual_admission_work']) is int and
            42_556_544<=receipt['actual_admission_work']<=45_556_544,
            'Q32 admission geometry work')
    require(sum(expected['parent_work'].values())==components['parent'] and
            expected['planned_total_work']+expected['sweep_stream']['copy_work']<=5_800_000_000,
            'Q32 composed transport admission')
    return receipt


# Each sweep stages two fields. Across both sweeps the trainer reads
# seven extents and stages four per row in the new profile.
ROW_BATCH_REQUEST_WORK=(16*11+8*4)*(281_066-119_196)
ROW_BATCH_CODEC_WORDS=3*((644+63)//64)
INDEXED_CACHE_WORK_DELTA=((rank_index_costs(17)['lookup']-2*17)*412_080+
                          17*rank_index_costs(17)['update']+rank_index_costs(17)['setup'])


def validate_admission(receipt,*,paired=False,packed=False,compact=False,scaled=False,sealed=False,paged=False,
                       directory=False,rank_sets=False,split=False,ten_card=False,ten_buffered=False,
                       ten_virtual_zero=False,ten_ordered_state=False,ten_row_coverage=False,ten_shared_policy=False,
                       ten_paged_directory=False,ten_sweep_stream=False,proof9_t3=False,proof9_t4=False,proof9_quality32=False,proof9_linear32=False,
                       ten_sparse_chance=False,ten_single_division=False,ten_phase_payload=False,
                       ten_row_batched=False,ten_indexed_cache=False,ten_complement=False):
    require(type(ten_complement) is bool and type(receipt) is dict and
            (receipt.get('complement_division') is True if ten_complement else 'complement_division' not in receipt),
            'complement division profile differs from requested admission')
    if ten_complement:
        earlier={key:value for key,value in receipt.items() if key!='complement_division'}
        validate_admission(earlier,ten_indexed_cache=True)
        return receipt
    if ten_indexed_cache:
        cost=rank_index_costs(17)
        require(type(receipt) is dict and receipt.get('sorted_rank_index') is True,
                'sorted rank index profile tag missing')
        expected={'rank_lookup_work_per_query':cost['lookup'],'rank_index_entries':cost['entries'],
                  'rank_index_update_work':cost['update'],'rank_index_setup_work':cost['setup'],
                  'planned_total_work':1_696_642_046+INDEXED_CACHE_WORK_DELTA,
                  'parent_allowance':1_185_397_984-INDEXED_CACHE_WORK_DELTA}
        require(all(type(receipt.get(key)) is int and receipt[key]==value for key,value in expected.items()) and
                type(receipt.get('component_work')) is dict and
                receipt['component_work'].get('chance')==127_793_144+INDEXED_CACHE_WORK_DELTA,
                'sorted rank index admission differs from independent fixed census')
        removed={'sorted_rank_index','rank_index_entries','rank_index_update_work','rank_index_setup_work'}
        earlier={key:value for key,value in receipt.items() if key not in removed}
        earlier.update(rank_lookup_work_per_query=34,planned_total_work=1_696_642_046,
                       parent_allowance=1_185_397_984)
        earlier['component_work']=dict(receipt['component_work'],chance=127_793_144)
        validate_admission(earlier,ten_row_batched=True)
        return receipt
    if ten_row_batched:
        state_bits,composed=phase_payload_bits(119_196,644,row_batched=True)
        require(type(receipt) is dict and receipt.get('row_batched') is True,
                'row-batched profile tag missing')
        expected={'page_request_limit':11*119_196,'paging_work':153_699_290-ROW_BATCH_REQUEST_WORK,
                  'planned_total_work':1_730_311_006-ROW_BATCH_REQUEST_WORK,
                  'entries':360_303+ROW_BATCH_CODEC_WORDS,'state_payload_bits':state_bits,'payload_bits':composed}
        require(all(type(receipt.get(key)) is int and receipt[key]==value for key,value in expected.items()),
                'row-batched admission differs from independent fixed census')
        earlier={key:value for key,value in receipt.items() if key!='row_batched'}
        earlier.update(page_request_limit=11*281_066,paging_work=153_699_290,
                       planned_total_work=1_730_311_006,entries=360_303)
        earlier['state_payload_bits'],earlier['payload_bits']=phase_payload_bits(119_196,644)
        for owner,key,old_work in (('parent_work','route',351_878_474),('component_work','parent',765_708_990)):
            group=receipt.get(owner)
            require(type(group) is dict and type(group.get(key)) is int and group[key]==old_work-ROW_BATCH_REQUEST_WORK,
                    'row-batched parent work differs from independent fixed census')
            earlier[owner]=dict(group,**{key:old_work})
        validate_admission(earlier,ten_phase_payload=True)
        contract=receipt['sweep_stream']
        require(composed+8*(contract['scratch_bytes']+contract['frame_header_bytes'])<=1_200_000_000,
                'row-batched payload exceeds composed transport cap')
        return receipt
    if ten_phase_payload:
        state_bits,composed=phase_payload_bits(119_196,644)
        require(type(receipt) is dict and receipt.get('phase_payload') is True and
                type(receipt.get('state_payload_bits')) is int and receipt['state_payload_bits']==state_bits and
                type(receipt.get('payload_bits')) is int and receipt['payload_bits']==composed,
                'phase payload differs from independent fixed census')
        earlier={key:value for key,value in receipt.items() if key not in ('phase_payload','state_payload_bits')}
        earlier['payload_bits']=1_182_148_028
        validate_admission(earlier,ten_single_division=True)
        contract=receipt['sweep_stream']
        require(composed+8*(contract['scratch_bytes']+contract['frame_header_bytes'])<=1_200_000_000,
                'phase payload exceeds composed transport cap')
        return receipt
    require(type(proof9_linear32) is bool,'linear32 admission mode must be boolean')
    if proof9_linear32:
        require(not any((paired,packed,compact,scaled,sealed,paged,directory,rank_sets,split,ten_card,
                         ten_buffered,ten_virtual_zero,ten_ordered_state,ten_row_coverage,ten_shared_policy,
                         ten_paged_directory,ten_sweep_stream,proof9_t3,proof9_t4,proof9_quality32,
                         ten_sparse_chance,ten_single_division,ten_phase_payload,ten_row_batched,ten_indexed_cache,ten_complement)),
                'select the linear32 admission mode alone')
        return validate_quality32_admission(receipt,linear=True)
    if proof9_quality32:
        return validate_quality32_admission(receipt)
    if proof9_t3 or proof9_t4:
        require(proof9_t3!=proof9_t4,'select one bounded PROOF9 admission')
        return validate_bounded_proof9_admission(receipt,4 if proof9_t4 else 3)
    if ten_sweep_stream or ten_sparse_chance or ten_single_division:
        contract=sweep_stream_contract()
        require(type(receipt) is dict and receipt.get('sweep_stream')==contract and
                all(type(value) is int for value in receipt['sweep_stream'].values()),
                'sweep stream admission differs from independent fixed census')
        numeric={key:value for key,value in receipt.items() if key!='sweep_stream'}
        if ten_sparse_chance or ten_single_division:
            require(numeric.get('sparse_chance') is True,'sparse chance profile tag missing')
            components=numeric.get('component_work')
            total=1_730_311_006 if ten_single_division else 1_810_140_094
            parent=1_185_397_984 if ten_single_division else 1_105_568_896
            require(type(components) is dict and type(components.get('chance')) is int and
                    components['chance']==127_793_144 and
                    type(numeric.get('planned_total_work')) is int and numeric['planned_total_work']==total and
                    type(numeric.get('parent_allowance')) is int and numeric['parent_allowance']==parent,
                    'sparse chance forecast differs from independent fixed census')
            baseline=dict(numeric)
            del baseline['sparse_chance']
            baseline['component_work']=dict(components,chance=447_066_576)
            if ten_single_division:
                terms=numeric.get('quantizer_terms')
                require(numeric.get('single_division') is True and type(components.get('quantizer')) is int and
                        components['quantizer']==433_472_328 and type(terms) is list and
                        all(type(term) is int for term in terms) and terms==[51_633_888,156_086_912,225_751_528],
                        'single-division forecast differs from independent fixed census')
                del baseline['single_division']
                baseline['component_work']['quantizer']=513_301_416
                baseline['quantizer_terms']=[51_633_888,178_125_664,283_541_864]
            baseline['planned_total_work']=2_129_413_526
            baseline['parent_allowance']=786_295_464
            validate_ten_admission(baseline,paged_directory=True)
        else:
            validate_ten_admission(numeric,paged_directory=True)
        scratch=contract['scratch_bytes']+contract['frame_header_bytes']
        require(numeric['output_bytes']==contract['retained_bytes'] and
                numeric['checkpoint_image_bytes']==contract['image_bytes'] and
                numeric['planned_total_work']+contract['copy_work']<=2_150_000_000 and
                numeric['entries']+(scratch+7)//8<=2_000_000 and
                numeric['payload_bits']+8*scratch<=1_200_000_000,
                'sweep stream exceeds composed fixture caps')
        return receipt
    if ten_card or ten_buffered or ten_virtual_zero or ten_ordered_state or ten_row_coverage or ten_shared_policy or ten_paged_directory:
        return validate_ten_admission(receipt,buffered=ten_buffered,virtual_zero=ten_virtual_zero,
                                      ordered_state=ten_ordered_state,row_coverage=ten_row_coverage,
                                      shared_policy=ten_shared_policy,paged_directory=ten_paged_directory)
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
                     write_words=stage['written_words'],physical_write_requests=stage['batched_write_calls'],
                     completed_sweeps=stage['sweeps'])
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
    names=set(files)|{'paging.json'}
    if admission.get('shared_policy',False):
        names|={'policy.bin','policy.json'}
    if admission.get('single_division',False):
        names.add('quantizer.json')
    if admission.get('sorted_rank_index',False):
        names.add('rank-index.json')
    require(set(item.name for item in directory.iterdir())==names,'unexpected paging artifact')
    return {'counts':receipt,'images':files}


def verify_rank_index(directory,admission,replay,trace):
    path=unlinked_path(directory/'rank-index.json')
    require(path.is_file() and 0<path.stat().st_size<=1024,'rank index receipt extent')
    record=exact_json(path.read_bytes())
    fields={'capacity','entries','size','searches','updates','lookup_work','update_work','setup_work'}
    require(type(record) is dict and record.keys()==fields and
            all(type(value) is int and value>=0 for value in record.values()),'rank index receipt schema')
    require(trace['native_calls']==trace['rank_calls']==0 and
            all(record[key]==trace[key] for key in fields),'rank index differs from independent structural trace')
    planes=admission['rank_cache_planes']
    cost=rank_index_costs(planes)
    chance=replay['chance_actual']
    queries=chance['cache_hits']+chance['cache_misses']
    require(queries==4*admission['showdown_contractions_per_pass'] and
            (record['capacity'],record['entries'],record['size'],record['updates'],record['setup_work'])==
            (planes,cost['entries'],planes,planes,cost['setup']) and
            planes==chance['cache_misses'] and queries==trace['queries'] and
            chance['cache_hits']==trace['cache_hits'] and chance['cache_evictions']==trace['cache_evictions'] and
            chance['cache_lookup_work']==trace['parent_cache_lookup_work'] and
            planes<=record['searches']<=queries and
            record['lookup_work']==(cost['lookup']-2)*record['searches'] and
            record['update_work']==cost['update']*planes and
            chance['cache_lookup_work']==2*(queries-1)+record['lookup_work']+
                record['update_work']+planes*(4*planes+64),
            'rank index allocation, search or mutation charge differs')
    return record


def verify_division_receipt(directory,admission):
    path=unlinked_path(directory/'quantizer.json')
    require(path.is_file() and 0<path.stat().st_size<=256,'combined division receipt extent')
    record=exact_json(path.read_bytes())
    require(type(record) is dict and record.keys()=={'combined_divisions'} and
            type(record['combined_divisions']) is int and
            0<record['combined_divisions']<=(32 if admission.get('proof9_quality32') or admission.get('proof9_linear32') else 2)*admission['slots'],'combined division receipt differs')
    return record


def verify_policy_spill(directory,stream,admission):
    sweeps=admission['requested_sweeps']
    if sweeps in (3,4,32):
        extent=sweep_stream_contract(proof9_sweeps=sweeps)['retained_bytes']
        magic=b'OPLDSL31' if admission.get('proof9_linear32') else b'OPLDSQ31' if sweeps==32 else f'OPLDST{sweeps}1'.encode('ascii')
    else:
        extent,magic=TEN_CARD_SPLIT_BYTES,b'OPLDTP01'
    require(sweeps in (2,3,4,32) and admission['output_bytes']==extent and
            stream.stat().st_size==extent,'policy spill scaffold byte bound')
    with stream.open('rb') as saved:
        raw=saved.read(extent+1)
    require(len(raw)==extent and raw[:8]==magic,'policy spill scaffold differs')
    rows,slots=admission['rows'],admission['slots']
    at=8+16*8+11*8+96*1105
    menus=[]
    slot=0
    for _ in range(rows):
        _,flags,offset=struct.unpack_from('<3Q',raw,at)
        menu=(flags>>16)&255
        require(2<=menu<=4 and offset==slot,'policy spill row extent differs')
        menus.append(menu)
        slot+=menu
        at+=24
    require(slot==slots,'policy spill slot count differs')
    policy=unlinked_path(directory/'policy.bin')
    receipt=unlinked_path(directory/'policy.json')
    size=policy.stat().st_size
    require(policy.is_file() and receipt.is_file() and receipt.stat().st_size<=65536
            and size<=8*admission['policy_spill_word_limit'],
            'policy spill artifact bound')
    expected=[]
    Q=1<<52
    with policy.open('rb') as spilled:
        for sweep in range(sweeps):
            counts=dict(uniform_rows=0,pure_rows=0,mixed_rows=0,extent_words=0,write_words=0,
                        read_calls=3*rows,mixed_read_calls=0,read_words=0)
            offset=0
            for menu in menus:
                units=struct.unpack_from(f'<{menu}Q',raw,at)
                require(sum(units)==Q,'policy spill grid total differs')
                base,remainder=divmod(Q,menu)
                if all(unit==base+(action<remainder) for action,unit in enumerate(units)):
                    counts['uniform_rows']+=1
                elif Q in units:
                    counts['pure_rows']+=1
                else:
                    counts['mixed_rows']+=1
                    counts['extent_words']=offset+menu-1
                    counts['write_words']+=menu-1
                    if sweep==sweeps-1:
                        spilled.seek(8*offset)
                        require(spilled.read(8*(menu-1))==raw[at:at+8*(menu-1)],'policy spill word bytes differ')
                offset+=menu-1
                at+=8*menu
            counts['mixed_read_calls']=3*counts['mixed_rows']
            counts['read_words']=3*counts['write_words']
            expected.append(counts)
            at+=4*(1+11)*8
    require(expected==exact_json(receipt.read_bytes()) and size==8*expected[-1]['extent_words']
            and 3*rows==admission['policy_spill_read_call_limit']
            and slots-rows==admission['policy_spill_word_limit'],'policy spill receipt differs from saved grids')
    return {'sweeps':expected,'retained_extent_bytes':size,'sha256':sha(policy)}


def verify_row_directory(directory, stream, admission):
    """Authenticate every immutable directory record against independent rows."""
    directory=unlinked_path(directory)
    require(directory.is_dir(),'row directory is missing')
    receipt_path=unlinked_path(directory/'rows.json')
    rows_path=unlinked_path(directory/'rows.bin')
    require(receipt_path.is_file() and receipt_path.stat().st_nlink==1 and
            0<receipt_path.stat().st_size<=65536,'row directory receipt must be private and bounded')
    receipt=exact_json(receipt_path.read_bytes())
    sweeps=admission.get('requested_sweeps',2)
    ten_card=sweeps==2
    trace=directory_trace() if ten_card else directory_trace(ten_card=False,sweeps=sweeps,quality32=sweeps==32)
    rows,slots=admission['rows'],admission['slots']
    require(trace['rows']==rows and trace['slots']==slots and trace['page_rows']==128
            and trace['cache_pages']==8 and trace['misses']==admission['row_directory_page_limit']
            and trace['logical_reads']==admission['row_directory_read_call_limit'],
            'independent row directory census differs from admission')
    expected=dict(appended_rows=rows,build_snapshots=rows,read_calls=trace['logical_reads'],
                  cache_hits=trace['hits'],page_reads=trace['misses'],
                  read_rows=trace['read_bytes']//32,write_calls=trace['write_calls'],written_rows=rows)
    require(type(receipt) is dict and receipt==expected and
            all(type(value) is int for value in receipt.values()),'row directory receipt differs from independent trace')
    require(rows_path.is_file() and rows_path.stat().st_nlink==1 and rows_path.stat().st_size==32*rows,
            'row directory must be a private fixed-size file')
    data=rows_path.read_bytes()
    require(len(data)==32*rows,'row directory length changed')
    digest=hashlib.sha256(data).hexdigest()
    fixture=Fixture(quality32=True) if sweeps==32 else Fixture(ten_card=ten_card)
    scales=compact_scales(fixture)
    value_bits=644 if ten_card or sweeps==32 else 642
    source_map={}
    reverse_map={}
    avg=reg=offset=0
    with unlinked_path(stream).open('rb') as saved:
        saved.seek(8+16*8+11*8+1105*96)
        for row,key in enumerate(fixture.ordered_rows()):
            require(row<rows,'independent directory row overflow')
            header=saved.read(24)
            require(len(header)==24,'truncated saved directory prelude')
            history,packed,at=struct.unpack('<3Q',header)
            actor,holding,menu=packed&255,(packed>>8)&255,(packed>>16)&255
            require(packed>>24==0 and at==offset and menu==len(fixture.menus[key])
                    and fixture.compact_key(history,actor,holding)==key,
                    'saved prelude differs from independent directory order')
            w0,w1,w2,w3=struct.unpack_from('<4Q',data,row*32)
            avg_shift,reg_shift=scales[history>>33]
            source=(w2>>32)&0xffff
            source_ref=fixture.paths[history>>33][0]
            require(source<388 and source_map.setdefault(source_ref,source)==source
                    and reverse_map.setdefault(source,source_ref)==source_ref,
                    'row source identity is out of range or inconsistent')
            require(w0==history and w1==(offset|(avg<<32))
                    and w2==(reg|(source<<32)|(avg_shift<<48))
                    and w3==(reg_shift|(actor<<16)|(holding<<24)),
                    'row directory record differs from independent packed geometry')
            offset+=menu
            avg+=menu*((value_bits-avg_shift+63)//64)
            reg+=menu*((value_bits-reg_shift+63)//64)
    require((row+1,offset,avg,reg)==(rows,slots,admission['packed_average_limbs'],admission['packed_regret_limbs']),
            'row directory complete extent differs')
    require(sha(rows_path)==digest and exact_json(receipt_path.read_bytes())==receipt,
            'row directory changed during verification')
    return {'receipt':receipt,'rows_bytes':len(data),'rows_sha256':digest,
            'receipt_sha256':sha(receipt_path),'independent_trace':trace}


def compare_buffered_ten(path,source,paging,images,*,virtual_zero=False,row_batched=False):
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
    if row_batched:
        invariant=('logical_read_words','completed_sweeps')
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


def verify_sweep_capture(process,admission,images,digest):
    contract=admission['sweep_stream']
    capture=process.get('sweep_capture',{})
    stdout=process['streams'][0]
    require(type(capture) is dict and len(images)==2,'captured checkpoint receipt or final roles differ')
    frames=capture.get('frames',[])
    require(type(frames) is list and len(frames)==contract['frames'], 'captured checkpoint count differs')
    for sweep,frame in enumerate(frames,1):
        require(type(frame) is dict and set(frame)=={'sweep','slot','bytes','sha256'} and
                all(type(frame[key]) is int for key in ('sweep','slot','bytes')) and
                (frame['sweep'],frame['slot'],frame['bytes'])==(sweep,sweep%2,contract['image_bytes']) and
                type(frame['sha256']) is str and len(frame['sha256'])==64 and
                all(c in '0123456789abcdef' for c in frame['sha256']), 'captured checkpoint frame differs')
    expected_final=[{'sweep':sweep,'slot':sweep%2,'bytes':image['bytes'],'sha256':image['sha256']}
                    for sweep,image in enumerate(images,contract['frames']-1)]
    wire_hash=stdout.get('wire_sha256')
    require(type(wire_hash) is str and len(wire_hash)==64 and all(c in '0123456789abcdef' for c in wire_hash)
            and stdout['observed_bytes']==contract['wire_bytes'] and
            stdout['saved_bytes']==contract['retained_bytes'] and stdout['sha256']==digest and
            frames[-2:]==expected_final and
            capture=={'contract':contract,'frames':frames,'wire_sha256':wire_hash,'retained_sha256':digest},
            'captured sweep checkpoint bytes or order differ')
    return capture


def compare_ten_card_work(source,replay,*,single_division=False):
    owner='quantizer' if single_division else 'chance'
    fixture,status,head=(
        ('sparse-chance','accepted_ten_card_sparse_chance_training_and_replay',
         '3c33c2f103d08594c10bb48b0f5e26f9e92105b0') if single_division else
        ('sweep-stream','accepted_streamed_sweep_checkpoint_digest_replay',
         '83d143d89a47528be36fe1f847e49d5568292a81'))
    path=f'benchmarks/results/native-dyadic-{fixture}-ten-card-accepted-v1/manifest.json'
    raw=(ROOT/path).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==source['files'][path]['raw_sha256'],
            'ten-card streamed chance baseline source drift')
    manifest=exact_json(raw)
    require(manifest['status']==status and manifest['source_head']==head and
            manifest['training_invocations']==1 and manifest['operator']['returncode']==0 and
            manifest['operator']['actual_exit_observed'] and manifest['operator']['raw_source_stable'],
            'accepted ten-card streamed chance baseline required')
    prior=manifest['saved_only_replay']
    require(all(replay[key]==prior[key] for key in ('sweeps','profile_and_br','checkpoint_images','shape')) and
            all(replay['work_actual'][key]==work for key,work in prior['work_actual'].items() if key!=owner) and
            all(replay['chance_actual'][field]==prior['chance_actual'][field]
                for field in (prior['chance_actual'] if single_division else
                    ('input_work','cache_lookup_work','rank_work','sort_work','rank_calls','cache_hits',
                     'cache_misses','cache_evictions','completed_contractions'))),
            'ten-card comparison changed a shared result or receipt category')
    reference=prior['work_actual'][owner]
    observed=replay['work_actual'][owner]
    return {f'baseline_actual_{owner}_work':reference,f'actual_{owner}_work':observed,
            f'actual_{owner}_work_delta':observed-reference,f'actual_{owner}_work_improved':observed<reference}


def compare_ten_card_payload(source,replay):
    path='benchmarks/results/native-dyadic-single-division-ten-card-accepted-v1/manifest.json'
    raw=(ROOT/path).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==source['files'][path]['raw_sha256'],
            'ten-card phase payload baseline source drift')
    manifest=exact_json(raw)
    require(manifest['status']=='accepted_ten_card_single_division_training_and_replay' and
            manifest['source_head']=='56dd7350f5feb7c4c18893414d03e590a1e23960' and
            manifest['training_invocations']==1 and manifest['operator']['returncode']==0 and
            manifest['operator']['actual_exit_observed'] and manifest['operator']['raw_source_stable'],
            'accepted ten-card single-division baseline required')
    prior=manifest['saved_only_replay']
    fields=('sweeps','profile_and_br','checkpoint_images','shape','work_plan','work_actual',
            'parent_work_plan','parent_work_actual','chance_actual','planned_entries','combined_divisions')
    require(all(replay[key]==prior[key] for key in fields),
            'phase payload changed a shared result or work receipt')
    return {'baseline_payload_bits':prior['planned_payload_bits'],
            'phase_payload_bits':replay['planned_payload_bits'],'state_payload_bits':replay['state_payload_bits']}


def compare_ten_card_row_batch(source,result,numeric,replay):
    directory='benchmarks/results/native-dyadic-phase-payload-ten-card-accepted-v1'
    manifest=f'{directory}/manifest.json'
    raw=(ROOT/manifest).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==source['files'][manifest]['raw_sha256'],
            'ten-card row-batched baseline source drift')
    prior=exact_json(raw)
    require(prior['status']=='accepted_ten_card_phase_payload_training_and_replay' and
            prior['source_head']=='bab69e2c5831ae5705bae3cc88707ee39bb812b3' and
            prior['training_invocations']==1 and prior['operator']['returncode']==0 and
            prior['operator']['actual_exit_observed'] and prior['operator']['raw_source_stable'],
            'accepted ten-card phase payload baseline required')
    before=prior['saved_only_replay']
    unchanged=('sweeps','profile_and_br','checkpoint_images','shape','chance_actual',
               'combined_divisions','changed_current_rows','quality_gate')
    require(all(before[key]==replay[key] for key in unchanged) and
            all(prior[key]==result[key] for key in ('policy_spill','row_directory','quantizer')) and
            prior['paging']['images']==result['paging']['images'],
            'row batching changed exact training or nonpager owner receipts')
    for group,owner in (('work_plan','parent'),('work_actual','parent'),
                        ('parent_work_plan','route'),('parent_work_actual','route')):
        expected=dict(before[group])
        expected[owner]-=ROW_BATCH_REQUEST_WORK
        require(replay[group]==expected,'row batching changed work outside the pager charge')
    old_counts=prior['paging']['counts']
    new_counts=result['paging']['counts']
    differing={'read_calls','stage_calls','synthetic_read_calls','cache_hits'}
    require({key for key in old_counts if old_counts[key]!=new_counts[key]}==differing,
            'row batching changed pager traffic outside the logical request model')
    archive_name=f'{directory}/verification.zip'
    archive=ROOT/archive_name
    identity=prior['archive']
    require(archive.stat().st_size==identity['bytes']<=50<<20 and
            sha(archive)==identity['sha256']==source['files'][archive_name]['raw_sha256'],
            'phase payload baseline archive identity differs')
    member='cohort/train_ten_phase_payload/stdout.bin'
    current=numeric.read_bytes()
    with ZipFile(archive) as zipped:
        require(zipped.getinfo(member).file_size==TEN_CARD_SPLIT_BYTES,'phase baseline stream extent differs')
        old=zipped.read(member)
    require(len(current)==len(old) and hashlib.sha256(old).hexdigest()==before['saved_output_sha256'] and
            current[:-520]==old[:-520] and current[-520:-512]==old[-520:-512]==b'OPLDTP02',
            'row batching changed retained bytes outside the receipt footer')
    return {'phase_baseline_head':prior['source_head'],'phase_baseline_paging':old_counts,
            'row_batched_paging':new_counts,'modeled_work_saved':ROW_BATCH_REQUEST_WORK,
            'numeric_sha256':hashlib.sha256(current[:-520]).hexdigest()}


def compare_ten_card_index(source,result,path,replay):
    directory='benchmarks/results/native-dyadic-row-batched-ten-card-accepted-v1'
    manifest=f'{directory}/manifest.json'
    raw=(ROOT/manifest).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==source['files'][manifest]['raw_sha256'],
            'indexed chance baseline source drift')
    prior=exact_json(raw)
    require(prior['status']=='accepted_ten_card_row_batched_training_and_replay' and
            prior['source_head']=='7a85266f488ad66849cdc67c98aefd4006f7902b' and
            prior['training_invocations']==1 and prior['operator']['returncode']==0 and
            prior['operator']['actual_exit_observed'] and prior['operator']['raw_source_stable'],
            'accepted row-batched baseline required')
    before=prior['saved_only_replay']
    fields=('sweeps','profile_and_br','checkpoint_images','shape','combined_divisions',
            'changed_current_rows','quality_gate','planned_entries','planned_payload_bits',
            'parent_work_plan','parent_work_actual','state_payload_bits')
    require(all(before[key]==replay[key] for key in fields) and
            all(prior[key]==result[key] for key in ('paging','row_directory','policy_spill','quantizer')),
            'indexed cache changed a shared numerical result or owner receipt')
    for group in ('work_plan','work_actual'):
        require(all(before[group][owner]==value for owner,value in replay[group].items() if owner!='chance'),
                'indexed cache changed work outside its owner')
    changing={'setup_work','cache_lookup_work','peak_live_entries'}
    require(all(before['chance_actual'][key]==value for key,value in replay['chance_actual'].items()
                if key not in changing) and
            replay['chance_actual']['setup_work']==before['chance_actual']['setup_work']+rank_index_costs(17)['setup'],
            'indexed cache changed nonindex chance work or ranks')
    archive_name=f'{directory}/verification.zip'
    archive=ROOT/archive_name
    require(archive.stat().st_size==prior['archive']['bytes']<=50<<20 and
            sha(archive)==prior['archive']['sha256']==source['files'][archive_name]['raw_sha256'],
            'row-batched baseline archive differs')
    with ZipFile(archive) as zipped:
        old=zipped.read('cohort/train_ten_row_batched/stdout.bin')
    current=path.read_bytes()
    require(len(current)==len(old)==TEN_CARD_SPLIT_BYTES and
            hashlib.sha256(old).hexdigest()==before['saved_output_sha256'] and
            current[:-520]==old[:-520] and current[-520:-512]==old[-520:-512]==b'OPLDTP02',
            'indexed cache changed exact retained bytes outside work receipt')
    return {'row_baseline_head':prior['source_head'],'baseline_chance_actual':before['chance_actual'],
            'indexed_chance_actual':replay['chance_actual'],'chance_work_forecast_delta':INDEXED_CACHE_WORK_DELTA,
            'numeric_sha256':hashlib.sha256(current[:-520]).hexdigest()}


def compare_ten_card_complement(source,result,path,replay,*,checked_history_work=None):
    directory='benchmarks/results/native-dyadic-indexed-cache-ten-card-accepted-v1'
    manifest=f'{directory}/manifest.json'
    raw=(ROOT/manifest).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==source['files'][manifest]['raw_sha256'],
            'complement baseline manifest source drift')
    prior=exact_json(raw)
    require(prior['status']=='accepted_ten_card_indexed_cache_training_and_replay' and
            prior['source_head']=='0122ce9de10bac680f3f8aad7d9d68173de7fab2' and
            prior['training_invocations']==1 and prior['operator']['returncode']==0 and
            prior['operator']['actual_exit_observed'] and prior['operator']['raw_source_stable'],
            'accepted indexed ten-card baseline required')
    before=prior['saved_only_replay']
    fields=('sweeps','profile_and_br','checkpoint_images','shape','changed_current_rows',
            'quality_gate','planned_entries','planned_payload_bits','parent_work_plan',
            'parent_work_actual','state_payload_bits','work_plan','work_actual','chance_actual')
    expected=before
    if checked_history_work is not None:
        require(type(checked_history_work) is int and 0<checked_history_work<before['work_actual']['history'],
                'checked History budget must reduce realized work')
        expected=dict(before,work_plan=dict(before['work_plan'],history=checked_history_work),
            work_actual=dict(before['work_actual'],history=checked_history_work))
    require(all(expected[key]==replay[key] for key in fields) and
            all(prior[key]==result[key] for key in ('paging','row_directory','policy_spill','sweep_capture')),
            'complement changed saved training evidence or work receipts')
    require(before['combined_divisions']==prior['quantizer']['combined_divisions']==325_666 and
            replay['combined_divisions']==result['quantizer']['combined_divisions']==186_152,
            'complement division counts differ from the frozen ten-card census')
    archive_name=f'{directory}/verification.zip'
    archive=ROOT/archive_name
    require(archive.stat().st_size==prior['archive']['bytes']<=50<<20 and
            sha(archive)==prior['archive']['sha256']==source['files'][archive_name]['raw_sha256'],
            'indexed ten-card baseline archive differs')
    with ZipFile(archive) as zipped:
        member=zipped.getinfo('cohort/train_ten_indexed_cache/stdout.bin')
        require(member.file_size==TEN_CARD_SPLIT_BYTES,'indexed baseline stream extent differs')
        old=zipped.read(member)
    require(hashlib.sha256(old).hexdigest()==before['saved_output_sha256'],
            'indexed retained numerical stream identity differs')
    candidate=path.read_bytes()
    if checked_history_work is not None:
        expected_bytes=bytearray(old)
        # Six plan words followed by six actual words at the start of the
        # 512-byte footer payload. History is index 2 in both families.
        for offset,key in ((496,'work_plan'),(448,'work_actual')):
            require(int.from_bytes(old[-offset:-offset+8],'little')==before[key]['history'],
                    'indexed History footer location differs')
            expected_bytes[-offset:-offset+8]=checked_history_work.to_bytes(8,'little')
        old=expected_bytes
    require(candidate==old and hashlib.sha256(candidate).hexdigest()==replay['saved_output_sha256'],
            'retained numerical stream differs beyond admitted History counters')
    return {'indexed_baseline_head':prior['source_head'],
            'combined_divisions_before':before['combined_divisions'],
            'combined_divisions_after':replay['combined_divisions'],
            'combined_divisions_removed':before['combined_divisions']-replay['combined_divisions'],
            'retained_sha256':replay['saved_output_sha256'],
            'wire_sha256':(result['compact_sweep_capture']['wire_sha256'] if checked_history_work is not None
                           else result['sweep_capture']['wire_sha256']),
            **({'expected_history_footer_changes':2} if checked_history_work is not None else {})}


def compare_proof9_t3_prefix(path,source,frames):
    manifest=f'{PROOF9_SPLIT_BASELINE}/manifest.json'
    raw=(ROOT/manifest).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==source['files'][manifest]['raw_sha256'],
            'PROOF9 T2 manifest source drift')
    baseline=exact_json(raw)
    require(baseline['status']=='accepted_split_checkpoint_training_and_replay' and
            baseline['source_head']=='df04bcb5f74470d03173df3a0747aa097a7b9940' and
            baseline['training_invocations']==1 and baseline['operator']['returncode']==0 and
            baseline['operator']['actual_exit_observed'] and baseline['operator']['raw_source_stable'],
            'accepted PROOF9 T2 split baseline required')
    archive_name=f'{PROOF9_SPLIT_BASELINE}/evidence.zip'
    archive=ROOT/archive_name
    binding=baseline['archive']
    require(binding['path']=='evidence.zip' and 0<archive.stat().st_size==binding['bytes']<=50<<20 and
            sha(archive)==binding['sha256']==source['files'][archive_name]['raw_sha256'],
            'PROOF9 T2 baseline archive identity differs')
    replay=baseline['saved_replay']
    first_two=replay['checkpoint_images']
    require([(f['bytes'],f['sha256']) for f in frames[:2]]==
            [(f['bytes'],f['sha256']) for f in first_two], 'first two checkpoint digests changed')
    header=8+16*8+11*8
    prefix=1105*96+24*24420+2*(8*58164+4*12*8)
    member='cohort/train_split/stdout.bin'
    with ZipFile(archive) as bundle, path.open('rb') as new:
        require(bundle.getinfo(member).file_size==SPLIT_BYTES,'PROOF9 T2 numerical extent differs')
        old=bundle.read(member)
        require(hashlib.sha256(old).hexdigest()==replay['saved_output_sha256'] and
                len(new.read(header))==header and new.read(prefix)==old[header:header+prefix],
                'PROOF9 T3 first two numerical sweeps differ')
    return {'baseline_source_head':baseline['source_head'],'baseline_stream_sha256':replay['saved_output_sha256'],
            'prefix_bytes':prefix,'prefix_sha256':hashlib.sha256(old[header:header+prefix]).hexdigest(),
            'first_two_checkpoint_images':first_two,'baseline_profile_and_br':replay['profile_and_br']}


def compare_proof9_t4_prefix(path,source,frames):
    manifest=f'{PROOF9_T3_BASELINE}/manifest.json'
    raw=(ROOT/manifest).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==source['files'][manifest]['raw_sha256'],
            'PROOF9 T3 manifest source drift')
    baseline=exact_json(raw)
    require(baseline['status']=='accepted_proof9_three_sweep_checkpoint_digest_replay' and
            baseline['source_head']=='66f4b3e66552c2a394ad3b25edf2329cbb364594' and
            baseline['training_invocations']==1 and baseline['operator']['returncode']==0 and
            baseline['operator']['actual_exit_observed'] and baseline['operator']['raw_source_stable'] and
            baseline['first_two_numerical_sweeps_match'] and baseline['independent_wire_reconstruction'],
            'accepted PROOF9 T3 baseline required')
    archive_name=f'{PROOF9_T3_BASELINE}/verification.zip'
    archive=ROOT/archive_name
    binding=baseline['archive']
    require(binding['name']=='verification.zip' and 0<archive.stat().st_size==binding['bytes']<=50<<20 and
            sha(archive)==binding['sha256']==source['files'][archive_name]['raw_sha256'],
            'PROOF9 T3 baseline archive identity differs')
    replay=baseline['saved_only_replay']
    first_three=replay['checkpoint_epochs']
    require(replay['status']=='saved_three_sweep_exact_replay_pass' and
            first_three==baseline['sweep_capture']['frames']==frames[:3],
            'first three checkpoint epochs changed')
    header=8+16*8+11*8
    prefix=1105*96+24*24420+3*(8*58164+4*12*8)
    member='cohort/train_proof9_t3/stdout.bin'
    with ZipFile(archive) as bundle, path.open('rb') as new:
        extent=sweep_stream_contract(proof9_sweeps=3)['retained_bytes']
        require(bundle.getinfo(member).file_size==extent,'PROOF9 T3 numerical extent differs')
        old=bundle.read(member)
        require(hashlib.sha256(old).hexdigest()==replay['saved_output_sha256'] and
                len(new.read(header))==header and new.read(prefix)==old[header:header+prefix],
                'PROOF9 T4 first three numerical sweeps differ')
    return {'baseline_source_head':baseline['source_head'],'baseline_stream_sha256':replay['saved_output_sha256'],
            'prefix_bytes':prefix,'prefix_sha256':hashlib.sha256(old[header:header+prefix]).hexdigest(),
            'first_three_checkpoint_epochs':first_three,'baseline_profile_and_br':replay['profile_and_br']}


def run(output,expected_head,*,train=False,paired=False,packed=False,compact=False,scaled=False,sealed=False,paged=False,
        directory=False,rank_sets=False,split=False,ten_card=False,ten_buffered=False,ten_virtual_zero=False,
        ten_ordered_state=False,ten_row_coverage=False,ten_shared_policy=False,ten_paged_directory=False,
        ten_sweep_stream=False,proof9_t3=False,proof9_t4=False,proof9_quality32=False,proof9_linear32=False,ten_sparse_chance=False,ten_single_division=False,
        ten_phase_payload=False,ten_row_batched=False,ten_indexed_cache=False,ten_complement=False):
    require(require_source_bootstrap(ROOT)['interpreter']['optimize']==0,'fixed cohort requires normal source-only parent')
    modes=(paired,packed,compact,scaled,sealed,paged,directory,rank_sets,split,ten_card,ten_buffered,ten_virtual_zero,
           ten_ordered_state,ten_row_coverage,ten_shared_policy,ten_paged_directory,ten_sweep_stream,proof9_t3,proof9_t4,proof9_quality32,proof9_linear32,
           ten_sparse_chance,ten_single_division,ten_phase_payload,ten_row_batched,ten_indexed_cache,ten_complement)
    require(type(train) is bool and all(type(flag) is bool for flag in modes) and sum(modes)<=1,
            'explicit fixed cohort mode')
    suffix=next((name for flag,name in zip(modes,('_PAIRED','_PACKED','_COMPACT','_SCALED','_SEALED','_PAGED',
                                                 '_DIRECTORY','_RANK_SETS','_SPLIT','_TEN','_TEN_BUFFERED',
                                                 '_TEN_VIRTUAL_ZERO','_TEN_ORDERED_STATE','_TEN_ROW_COVERAGE',
                                                 '_TEN_SHARED_POLICY','_TEN_PAGED_DIRECTORY','_TEN_SWEEP_STREAM',
                                                 '_PROOF9_T3','_PROOF9_T4','_PROOF9_Q32','_PROOF9_LINEAR32','_TEN_SPARSE_CHANCE','_TEN_SINGLE_DIVISION',
                                                 '_TEN_PHASE_PAYLOAD','_TEN_ROW_BATCHED','_TEN_INDEXED_CACHE','_TEN_COMPLEMENT'),strict=True) if flag),'')
    paired=any(modes)
    indexed_cache=ten_indexed_cache or ten_complement
    row_batched=ten_row_batched or indexed_cache
    phase_payload=ten_phase_payload or row_batched
    counted_divisions=ten_single_division or phase_payload
    ten_sweep_stream=ten_sweep_stream or ten_sparse_chance or counted_divisions
    ten_paged_directory=ten_paged_directory or ten_sweep_stream
    ten_shared_policy=ten_shared_policy or ten_paged_directory
    ten_row_coverage=ten_row_coverage or ten_shared_policy
    ten_ordered_state=ten_ordered_state or ten_row_coverage
    ten_virtual_zero=ten_virtual_zero or ten_ordered_state
    ten_card=ten_card or ten_buffered or ten_virtual_zero
    quality32=proof9_quality32 or proof9_linear32
    proof9_sweeps=32 if quality32 else 4 if proof9_t4 else 3 if proof9_t3 else 0
    row_batched=row_batched or quality32
    counted_divisions=counted_divisions or quality32
    split=split or ten_card or bool(proof9_sweeps)
    shared_policy=ten_shared_policy or bool(proof9_sweeps)
    paged_directory=ten_paged_directory or bool(proof9_sweeps)
    capture_checkpoints=ten_sweep_stream or bool(proof9_sweeps)
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
        receipt=exact_json((admitted/'stdout.bin').read_bytes())
        if proof9_linear32:
            admission=validate_admission(receipt,proof9_linear32=True)
        else:
            admission=validate_admission(receipt,paired=paired,
                packed=packed,compact=compact,scaled=scaled,sealed=sealed,paged=paged,directory=directory,
                rank_sets=rank_sets,split=split,ten_card=ten_card,ten_buffered=ten_buffered,ten_virtual_zero=ten_virtual_zero,
                ten_ordered_state=ten_ordered_state,ten_row_coverage=ten_row_coverage,ten_shared_policy=ten_shared_policy,
                ten_paged_directory=ten_paged_directory,ten_sweep_stream=ten_sweep_stream,
                proof9_t3=proof9_t3,proof9_t4=proof9_t4,proof9_quality32=proof9_quality32,ten_sparse_chance=ten_sparse_chance,
                ten_single_division=ten_single_division,ten_phase_payload=ten_phase_payload,
                ten_row_batched=ten_row_batched,ten_indexed_cache=ten_indexed_cache,ten_complement=ten_complement)
        save(output/'admission.json',admission)
        verify_source(ROOT,source)
        result={'head':expected_head,'mode':'train' if train else 'admit','admission':admission,
                'training_invocations':0,'fixed_proof_gate':gate,
                'scope':f'fixed reduced PROOF9/T{proof9_sweeps} only' if proof9_sweeps else
                    'fixed reduced PROOF10/T2 only' if ten_card else 'fixed reduced PROOF9/T2 only',
                'outer_exit_and_final_bootstrap':'required separately'}
        if train:
            schedule=stage_schedule(ten_card=True,virtual_zero=ten_virtual_zero,batch_rows=row_batched
                                    ) if ten_buffered or ten_virtual_zero else None
            if proof9_sweeps:
                schedule=stage_schedule(virtual_zero=True,sweeps=proof9_sweeps,batch_rows=quality32,quality32=quality32)
                require((schedule['written_words'],schedule['physical_read_words'],schedule['batched_write_calls'],
                         schedule['logical_read_calls']+proof9_sweeps*schedule['per_sweep_stage_calls'])==
                        (admission['page_write_word_limit'],admission['page_read_word_limit'],
                         admission['page_write_request_limit'],admission['page_request_limit']),
                        'independent bounded PROOF9 pager schedule differs before training')
            if indexed_cache:
                result['rank_index_trace']=rank_trace()
                require(result['rank_index_trace']['queries']==4*admission['showdown_contractions_per_pass'],
                        'independent rank cache trace differs before training')
                save(output/'rank-index-trace.json',result['rank_index_trace'])
            if row_batched and not quality32:
                require((schedule['written_words'],schedule['physical_read_words'],schedule['batched_write_calls'],
                         schedule['logical_read_calls']+2*schedule['per_sweep_stage_calls'])==
                        (admission['page_write_word_limit'],admission['page_read_word_limit'],
                         admission['page_write_request_limit'],admission['page_request_limit']),
                        'independent row-batched pager schedule differs before training')
            if paged_directory:
                trace=directory_trace(ten_card=not proof9_sweeps,sweeps=proof9_sweeps or 2,quality32=quality32)
                require(trace['misses']==admission['row_directory_page_limit'] and
                        trace['logical_reads']==admission['row_directory_read_call_limit'],
                        'independent row directory trace differs before training')
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
            if counted_divisions:
                command.append('--count-policy-divisions')
            if phase_payload:
                command.append('--phase-payload')
            if row_batched and not quality32:
                command.append('--row-batched')
            if indexed_cache:
                command.append('--indexed-cache')
            if ten_complement:
                command.append('--complement-divisions')
            if proof9_sweeps:
                command.append('--proof9-linear32' if proof9_linear32 else '--proof9-quality32' if quality32 else f'--proof9-t{proof9_sweeps}')
            if split:
                pages=output/'page-images'
                paging=verify_paging(pages,admission,schedule)
                if counted_divisions:
                    result['quantizer']=verify_division_receipt(pages,admission)
                if shared_policy:
                    result['policy_spill']=verify_policy_spill(pages,raw,admission)
                if paged_directory:
                    result['row_directory']=verify_row_directory(output/'page-images-rows',raw,admission)
                roles=('committed.bin','staged.bin') if proof9_t3 else SPLIT_IMAGE_NAMES
                images=[{'name':name,**paging['images'][name]} for name in roles]
                if capture_checkpoints:
                    result['sweep_capture']=verify_sweep_capture(process,admission,images,digest)
                    capture_process=(trained/'process.json').read_bytes()
                    require(exact_json(capture_process)==process,'saved sweep process receipt differs')
                    capture_process_hash=hashlib.sha256(capture_process).hexdigest()
                    result['sweep_capture_process_sha256']=capture_process_hash
                result['checkpoint_inputs']={'stream':{'bytes':admission['output_bytes'],'sha256':digest},
                                             'sweep_images':images}
                if proof9_sweeps:
                    frames=result['sweep_capture']['frames']
                    result['checkpoint_inputs']['sweep_epochs']=frames
                    compare=compare_proof9_t4_prefix if proof9_t4 else compare_proof9_t3_prefix
                    comparison=({'scope':'Separately named N9 T32 average schedule; independent exact replay required'} if quality32 else compare(raw,source,frames))
                    comparison['native_observation']={
                        'duration_seconds':process['duration_seconds'],'memory':process.get('memory')}
                    result[f'proof9_t{proof9_sweeps}_comparison']=comparison
                    result['independent_stage_schedule']=schedule
                save(output/'checkpoint-inputs.json',result['checkpoint_inputs'])
                if ten_buffered or ten_virtual_zero:
                    comparison=compare_buffered_ten(raw,source,paging,images,virtual_zero=ten_virtual_zero,
                                                    row_batched=row_batched)
                    label='complement' if ten_complement else 'indexed_cache' if ten_indexed_cache else 'row_batched' if ten_row_batched else 'phase_payload' if ten_phase_payload else 'single_division' if ten_single_division else 'sparse_chance' if ten_sparse_chance else 'sweep_stream' if ten_sweep_stream else 'paged_directory' if ten_paged_directory else 'shared_policy' if ten_shared_policy else 'row_coverage' if ten_row_coverage else (
                        'ordered_state' if ten_ordered_state else 'virtual_zero' if ten_virtual_zero else 'buffered')
                    comparison[label+'_native_observation']={'duration_seconds':process['duration_seconds'],
                                                             'memory':process.get('memory')}
                    result[label+'_comparison']=comparison
                    result['independent_stage_schedule']=schedule
                if capture_checkpoints:
                    command.extend(['--sweep-checkpoint-digest',*(frame['sha256'] for frame in result['sweep_capture']['frames'])])
                else:
                    command.extend(['--page-images',str(pages),'--sweep-image-sha256',*(image['sha256'] for image in images)])
            save(output/'saved-review-command.json',command)
            replay_dir=output/'saved-review'
            observed_replay=(run_bounded_linear32_replay(command,b'',replay_dir) if proof9_linear32 else
                             run_bounded_quality32_replay(command,b'',replay_dir) if proof9_quality32 else
                             run_bounded_child(command,b'',replay_dir,stdout_limit=65536))
            require_exit(observed_replay,replay_dir)
            compiled=check_verifier_bootstrap(receipt_path,source)
            numeric=exact_json((replay_dir/'stdout.bin').read_bytes())
            sweep_word={0:'two',3:'three',4:'four',32:'quality32'}[proof9_sweeps]
            replay_status='saved_linear32_exact_replay_pass' if proof9_linear32 else 'saved_quality32_exact_replay_pass' if proof9_quality32 else f'saved_{sweep_word}_sweep_exact_replay_pass'
            require(numeric['status']==replay_status and numeric['saved_output_sha256']==digest
                    and numeric['work_plan']==admission['component_work'] and numeric['parent_work_plan']==admission['parent_work']
                    and numeric['planned_entries']==admission['entries'] and numeric['planned_payload_bits']==admission['payload_bits']
                    and numeric['showdown_contractions_per_pass']==admission['showdown_contractions_per_pass']
                    and numeric['hidden_completion_candidates_per_pass']==admission['hidden_completion_candidates_per_pass']
                    and (not paired or numeric['public_walks_per_sweep']==1)
                    and numeric['native_producer_calls']==0,
                    'saved replay result differs from admitted producer')
            if ten_sparse_chance:
                result['sparse_chance_comparison'].update(compare_ten_card_work(source,numeric))
            if ten_single_division:
                result['single_division_comparison'].update(compare_ten_card_work(source,numeric,single_division=True))
            if ten_phase_payload:
                result['phase_payload_comparison'].update(compare_ten_card_payload(source,numeric))
            if counted_divisions:
                require(numeric['combined_divisions']==result['quantizer']['combined_divisions'] and
                        result['quantizer']==verify_division_receipt(output/'page-images',admission),
                        'independent combined division count differs')
            result.update(training_invocations=1,saved_only_replay=numeric,saved_review_compiled_sources=compiled,
                          training_stdout_sha256=digest,quality_gate=None)
            if quality32:
                require(numeric['wire_sha256']==process['sweep_capture']['wire_sha256'] and
                        numeric['wire_bytes']==admission['sweep_stream']['wire_bytes'],
                        'Q32 independent full wire reconstruction differs from captured transport')
                gate=numeric['quality_gate']
                value=numeric['profile_and_br']['exploitability']
                exact=Fraction(int(value['numerator']),int(value['denominator']))
                passed=exact<=Fraction(1,10)
                require(gate=={'metric':'exploitability_bb','threshold':{'numerator':'1','denominator':'10'},
                               'status':'pass' if passed else 'miss','passed':passed},
                        'Q32 exact quality target differs from replay')
                result.update(status=replay_status,quality_gate=gate,
                              exactness_accepted=True)
            if uses_paging:
                result['paging']=verify_paging(output/'page-images',admission,schedule)
            if indexed_cache:
                result['rank_index']=verify_rank_index(output/'page-images',admission,numeric,result['rank_index_trace'])
                if ten_complement:
                    result['complement_comparison'].update(compare_ten_card_complement(source,result,raw,numeric))
                else:
                    result['indexed_cache_comparison'].update(compare_ten_card_index(source,result,raw,numeric))
            if ten_row_batched:
                result['row_batched_comparison'].update(compare_ten_card_row_batch(source,result,raw,numeric))
            if shared_policy:
                require(result['policy_spill']==verify_policy_spill(output/'page-images',raw,admission),
                        'policy spill bytes changed after independent replay')
            if paged_directory:
                require(result['row_directory']==verify_row_directory(output/'page-images-rows',raw,admission),
                        'row directory changed after independent replay')
            if indexed_cache:
                require(result['rank_index']==verify_rank_index(output/'page-images',admission,numeric,result['rank_index_trace']),
                        'rank index receipt changed after independent replay')
            if split:
                require(numeric['checkpoint_images']==images and result['paging']==paging and sha(raw)==digest,
                        'split checkpoint bytes changed after saved replay')
            if capture_checkpoints:
                require(numeric.get('checkpoint_verification')=='independent_compact_digest' and
                        sha(trained/'process.json')==capture_process_hash,
                        'captured checkpoint evidence changed after digest replay')
            if proof9_sweeps:
                require(numeric['checkpoint_epochs']==result['sweep_capture']['frames'],
                        'independently replayed checkpoint epochs differ')
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
    modes.add_argument('--ten-ordered-state',action='store_true')
    modes.add_argument('--ten-row-coverage',action='store_true')
    modes.add_argument('--ten-shared-policy',action='store_true')
    modes.add_argument('--ten-paged-directory',action='store_true')
    modes.add_argument('--ten-sweep-stream',action='store_true')
    modes.add_argument('--ten-sparse-chance',action='store_true')
    modes.add_argument('--ten-single-division',action='store_true')
    modes.add_argument('--ten-phase-payload',action='store_true')
    modes.add_argument('--ten-row-batched',action='store_true')
    modes.add_argument('--ten-indexed-cache',action='store_true')
    modes.add_argument('--ten-complement',action='store_true')
    modes.add_argument('--ten-compact-wire',action='store_true')
    modes.add_argument('--ten-factored',action='store_true')
    modes.add_argument('--ten-checked-history',action='store_true')
    modes.add_argument('--proof9-t3',action='store_true')
    modes.add_argument('--proof9-t4',action='store_true')
    modes.add_argument('--proof9-quality32',action='store_true')
    modes.add_argument('--proof9-linear32',action='store_true')
    args=parser.parse_args()
    if args.ten_compact_wire or args.ten_factored or args.ten_checked_history:
        from scripts.run_virtual_dyadic_compact_cohort import run_compact
        print(json.dumps(run_compact(args.output,args.expected_head,train=args.train,factored=args.ten_factored or args.ten_checked_history,
            checked_history=args.ten_checked_history),sort_keys=True))
        return
    print(json.dumps(run(args.output,args.expected_head,train=args.train,paired=args.paired,
        packed=args.packed_averages,compact=args.compact_strategy,scaled=args.scaled_averages,
        sealed=args.sealed_menus,paged=args.paged_strategy,directory=args.compact_directory,
        rank_sets=args.rank_sets,split=args.split_checkpoint,ten_card=args.ten_card,
        ten_buffered=args.ten_buffered,ten_virtual_zero=args.ten_virtual_zero,
        ten_ordered_state=args.ten_ordered_state,ten_row_coverage=args.ten_row_coverage,
        ten_shared_policy=args.ten_shared_policy,ten_paged_directory=args.ten_paged_directory,
        ten_sweep_stream=args.ten_sweep_stream,proof9_t3=args.proof9_t3,proof9_t4=args.proof9_t4,proof9_quality32=args.proof9_quality32,proof9_linear32=args.proof9_linear32,
        ten_sparse_chance=args.ten_sparse_chance,ten_single_division=args.ten_single_division,
        ten_phase_payload=args.ten_phase_payload,ten_row_batched=args.ten_row_batched,
        ten_indexed_cache=args.ten_indexed_cache,ten_complement=args.ten_complement),sort_keys=True))


if __name__=='__main__':main()
