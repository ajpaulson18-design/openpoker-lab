"""Compose the fixed complete experiment; no update producer is executed.

Independent resource models remain separate. This receipt is a resource plan,
not source authentication, native ADMIT evidence, or a license to skip gates.
"""
from tests.virtual_frozen_study_admission import BOARD_COUNT,CALL_COUNT,MAX_NATIVE_WORK,MAX_RAW_NATIVE_BYTES
from tests.virtual_frozen_update_comparison import FORECAST as COMPARE
from tests.virtual_frozen_expectation import FORECAST as AGGREGATE
from tests.virtual_frozen_reference_artifact import reference_study_allowance,artifact_allowance

LIMITS = {
    'native_work':3_000_000_000_000,'reference_work':3_000_000_000_000,
    'reference_created_bits':100_000_000_000_000,'comparison_work':200_000_000_000,
    'comparison_created_bits':1_000_000_000_000,'aggregation_work':300_000_000,
    'aggregation_created_bits':22_000_000_000,'codec_work':11_000_000_000,
    'peak_logical_entries':16_000_000,'peak_integer_payload_bits':32*(1<<30),
    'artifact_bytes':64*(1<<30),'authentication_read_bytes':16*(1<<40),
}
SOURCE = {'paths':4096,'single_file_bytes':64*(1<<20),'total_bytes':1<<30,
          'path_bytes':1024,'stream_chunk_bytes':1<<20}
NATIVE_CALLS = CALL_COUNT+2
FILE_FAMILIES = {
    'native_stdout':MAX_RAW_NATIVE_BYTES,'native_stderr':NATIVE_CALLS*65536,
    'requests':NATIVE_CALLS*1025,'call_receipts':NATIVE_CALLS*65536,
    'source_snapshot':SOURCE['total_bytes'],'headers_and_build':256*(1<<20),
    'controller_and_failure_logs':256*(1<<20),'saved_mutation_controls':128*(1<<20),
}


def compose_study_admission(census,expected,*,limits=None):
    ceilings=dict(LIMITS)
    if limits is not None:
        if type(limits) is not dict or set(limits)-set(LIMITS):raise ValueError('unknown whole-study limit')
        for name,value in limits.items():
            if type(value) is not int or not 0<value<=LIMITS[name]:raise ValueError('whole-study limits are positive and reduce-only')
            ceilings[name]=value
    version=census.get('version')
    if version not in ('virtual-frozen-study-admission-v1','virtual-frozen-prefix-fold-admission-v1'):
        raise ValueError('unknown census')
    prefix_folds=version=='virtual-frozen-prefix-fold-admission-v1'
    laws=('uniform',) if prefix_folds else ('uniform','river_weighted')
    if set(census['laws'])!=set(laws):raise ValueError('study law census differs')
    evals=BOARD_COUNT*len(laws)
    calls=evals+len(laws)
    for law in laws:
        part=census['laws'][law]
        if part['calls']!=2520 or part['row_records']!=107080 or part['action_slot_records']>428320:
            raise ValueError('complete two-law census required')
    if expected.worlds!=60 or expected.rank_calls!=120:raise ValueError('complete q-free oracle required')
    exports=reference_study_allowance()
    files={**FILE_FAMILIES,'reference_artifacts':exports['all_reference_artifact_bytes_upper']}
    if prefix_folds:
        files.update(native_stdout=files['native_stdout']//NATIVE_CALLS*calls,
                     native_stderr=calls*65536,requests=calls*1025,call_receipts=calls*65536,
                     reference_artifacts=exports['sampled_law_bytes_upper']+exports['q_free_bytes_upper'])
    raw_bytes=sum(files.values())
    # Keep originals and one archive, including bounded ZIP directory/header
    # overhead. Compression is never presumed to reduce the allowance.
    files['archive_with_headers_upper']=raw_bytes+128*(1<<20)
    expected_io=artifact_allowance('expected',24420,58164)
    sample_io=artifact_allowance('sampled',868,2078)
    sample_peak=max(p['max_reference_call']['entries'] for p in census['laws'].values())
    uses={
        'native_work':MAX_NATIVE_WORK//NATIVE_CALLS*calls,
        'reference_work':census['reference_work_upper']+expected.rule_setup_work+expected.work_upper+500_000_000,
        'reference_created_bits':census['reference_created_bits_upper']+expected.rule_setup_created_bits+expected.created_bits_upper+16_000_000_000,
        'comparison_work':evals*COMPARE['work'],
        'comparison_created_bits':evals*COMPARE['created_bits'],
        'aggregation_work':len(laws)*AGGREGATE['work'],
        'aggregation_created_bits':len(laws)*AGGREGATE['created_bits'],
        'codec_work':2*exports['one_export_or_read_named_work_upper'],
        # One law owner at a time; retain both possible oracle representations
        # conservatively, plus native, setup scratch, sampled and codec rows.
        'peak_logical_entries':(AGGREGATE['entries']+expected.entries_upper+expected_io['entries']+
                                sample_peak+sample_io['entries']+COMPARE['entries']+
                                200_000+2_000_000+2_000_000),
        'peak_integer_payload_bits':(2*expected_io['retained_integer_payload_bits']+
             2*sample_io['retained_integer_payload_bits']+(1<<30)+4_096_000_000+
             AGGREGATE['entries']*512+expected_io['row_scratch_integer_and_text_bits']),
        'artifact_bytes':sum(files.values()),
        # Full closure before/after every native request, plus outer guards.
        'authentication_read_bytes':(2*calls+4)*(SOURCE['total_bytes']+320*(1<<20)),
    }
    for name,value in uses.items():
        if type(value) is not int or value<0 or value>ceilings[name]:
            raise ValueError('complete study '+name+' admission exceeded')
    return {'version':('virtual-frozen-prefix-fold-whole-study-v1' if prefix_folds else
                       'virtual-frozen-whole-study-admission-v1'),'uses':uses,'limits':ceilings,
            'file_families':files,'source_limits':dict(SOURCE),'reference_setup_count':1,
            'q_free_oracle_count':1,'native_eval_requests':evals,'native_admit_requests':len(laws),
            'active_law_owners':1,'retained_law_results':'receipts only after finalization and owner release',
            'ready_for_producer':False,
            'remaining_gates':['clean committed executable/protocol freeze','source/build/dependency authentication',
                               'frozen worst-law native admission' if prefix_folds else 'two frozen worst-law native admissions','enforced output/log/source inventory bounds',
                               'exclusive controller claim and authoritative child process observation'],
            'scope':'complete fixed experiment resource composition; no capacity, equivalence or quality result'}
