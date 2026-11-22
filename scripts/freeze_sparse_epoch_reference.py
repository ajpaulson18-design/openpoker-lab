"""Freeze deterministic independent E1/E2 sparse tables for native Store tests.

Reference-artifact generation only. This is not native execution, stochastic
training, equilibrium evidence, or a solver quality claim.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import subprocess
import sys

from scripts.replay_native_frozen_policy_state import ORACLE_SOURCES
from tests.virtual_dyadic_training_reference import Fixture, Q
from tests.virtual_frozen_sample_reference import build_sampled_reference_context
from tests.virtual_sparse_epoch_reference import (
    AVERAGE_DENOMINATOR, REGRET_DENOMINATOR, apply_epoch, implicit_uniform,
    run_two_positive_epochs,
)
from tests.virtual_frozen_update_reference import _template_case

ROOT=Path(__file__).resolve().parents[1]
SCRIPT='scripts/freeze_sparse_epoch_reference.py'
SPARSE_SOURCES=('tests/virtual_sparse_epoch_reference.py','tests/test_sparse_epoch_reference.py',
    'tests/virtual_frozen_sample_reference.py','tests/virtual_grid_update_reference.py',
    'scripts/replay_native_frozen_policy_state.py')
SOURCES=tuple(ORACLE_SOURCES)+SPARSE_SOURCES+(SCRIPT,)
BOARD_1=(16,17,32,33,35)
BOARD_2=(17,24,33,35,37)
MAX_SOURCES=128
MAX_SOURCE_BYTES=32<<20
MAX_SOURCE_TOTAL=64<<20
MAX_OUTPUT_BYTES=32<<20
MAX_EPOCH_BYTES=4<<20
MAX_ROWS=1060
MAX_SNAPSHOT_ROWS=1590 # E1 <=530 plus E2 <=1060; not extra live numerical rows
ROW_COUNT=24420
REGRET_BITS=649
AVERAGE_BITS=382
POSITIVE_SUM_BITS=651
SCALED_WEIGHT_BITS=701
SCOPE=('Deterministic independent two-positive-board PROOF9 sparse epoch reference; '
       'unclipped integer regrets, exact integer averages, complete policy overlays; '
       'no native Store execution, sampled trainer, quality or convergence claim.')
HISTORICAL_WITNESS_NOTE=(
    'Keep the earlier swapped-board witness separate: it changed raw R/A while its '
    'policy stayed unchanged, so it did not demonstrate a second policy transition. '
    'The historical c2ad165 source and raw logs remain separate frozen evidence.'
)


def require(value,message):
    if not value:raise ValueError(message)


def _git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,stderr=subprocess.PIPE).decode('utf-8').strip()


def _source_capture():
    require(len(SOURCES)==19 and len(set(SOURCES))==len(SOURCES),'introduced source inventory')
    require(len(SOURCES)<=MAX_SOURCES,'introduced source count cap')
    head=_git('rev-parse','HEAD')
    require(len(head)==40 and all(c in '0123456789abcdef' for c in head),'full committed HEAD required')
    dirty=_git('status','--porcelain','--untracked-files=all','--',*SOURCES)
    require(not dirty,'introduced source closure must be clean and committed')
    tree={}
    for line in _git('ls-tree','-r',head).splitlines():
        metadata,name=line.split('\t',1)
        if name in SOURCES:tree[name]=metadata.split()[2]
    require(set(tree)==set(SOURCES),'introduced source closure is absent from committed HEAD')
    files={};total=0
    for name in SOURCES:
        body=(ROOT/name).read_bytes();total+=len(body)
        require(len(body)<=MAX_SOURCE_BYTES and total<=MAX_SOURCE_TOTAL,'source byte ceiling')
        canonical=subprocess.check_output(['git','show',head+':'+name],cwd=ROOT)
        require(body==canonical or (b'\r' not in canonical and body==canonical.replace(b'\n',b'\r\n')),
                'current reference source differs from committed bytes')
        files[name]={'blob':tree[name],'sha256':sha256(body).hexdigest(),'bytes':len(body)}
    return {
        'head':head,'source_files':files,'source_file_count':len(files),
        'source_bytes':total,
        'python':{'version':sys.version,'implementation':platform.python_implementation(),
                  'platform':platform.platform(),'executable':str(Path(sys.executable).resolve()),
                  'pycache_prefix':sys.pycache_prefix,'dont_write_bytecode':sys.dont_write_bytecode,
                  'executable_sha256':_file_sha256(Path(sys.executable))},
    }


def _file_sha256(path):
    digest=sha256()
    with path.open('rb') as source:
        while True:
            block=source.read(1<<20)
            if not block:break
            digest.update(block)
    return digest.hexdigest()


def _canonical_policy_digest(fixture,state,previous=None):
    digest=sha256();changed=0;count=0
    for actor,holding,history in fixture.ordered_rows():
        key=(actor,holding,history)
        require(key in fixture.menus and key in state.policy,'canonical policy row missing')
        units=state.policy[key]
        require(len(units)==len(fixture.menus[key]) and sum(units)==Q,'policy row partition')
        encoded=json.dumps([actor,holding,list(history),list(units)],ensure_ascii=True,
                           separators=(',',':')).encode('ascii')+b'\n'
        digest.update(encoded);count+=1
        if previous is not None and units!=previous.policy[key]:changed+=1
    require(count==ROW_COUNT,'canonical full policy row count')
    return digest.hexdigest(),count,changed


def _sparse_epoch(fixture,state):
    canonical=list(fixture.ordered_rows())
    require(len(canonical)==ROW_COUNT and len(set(canonical))==ROW_COUNT,
            'canonical full-history row ordering')
    require(set(state.regrets)==set(fixture.menus) and set(state.averages)==set(fixture.menus) and
            set(state.policy)==set(fixture.menus),'complete reference epoch inventory')
    rows=[];overlays=[];untouched=0;max_r=max_a=max_positive=max_scaled=0
    for actor,holding,history in canonical:
        key=(actor,holding,history);r=state.regrets[key];a=state.averages[key]
        units=state.policy[key];menu=fixture.menus[key]
        require(len(r)==len(a)==len(units)==len(menu),'sparse numeric/menu width')
        require(all(type(v) is int and abs(v).bit_length()<=REGRET_BITS for v in r),
                'sparse raw regret magnitude width')
        require(all(type(v) is int and v>=0 and v.bit_length()<=AVERAGE_BITS for v in a),
                'sparse average magnitude width')
        positive=sum(max(v,0) for v in r)
        scaled=max(((max(v,0)*Q).bit_length() for v in r),default=0)
        require(positive.bit_length()<=POSITIVE_SUM_BITS and scaled<=SCALED_WEIGHT_BITS,
                'positive or scaled regret width')
        max_r=max(max_r,max((abs(v).bit_length() for v in r),default=0))
        max_a=max(max_a,max((v.bit_length() for v in a),default=0))
        max_positive=max(max_positive,positive.bit_length());max_scaled=max(max_scaled,scaled)
        nonzero=any(r) or any(a)
        uniform=tuple((Q//len(menu)+(i<Q%len(menu))) for i in range(len(menu)))
        if nonzero:
            rows.append({'key':{'actor':actor,'holding_index':holding,'history_tokens':list(history)},
                         'Rliststr':[str(v) for v in r],'Aliststr':[str(v) for v in a],
                         'unitslist':list(units)})
        else:
            untouched+=1
            require(tuple(units)==uniform,'untouched row lost its implicit uniform default')
        if tuple(units)!=uniform:
            overlays.append({'key':{'actor':actor,'holding_index':holding,'history_tokens':list(history)},
                             'units':list(units)})
    require(0<len(rows)<=MAX_ROWS,'sparse epoch row count cap')
    return {
        'epoch':state.epoch,'R_denominator':str(REGRET_DENOMINATOR),
        'A_denominator':str(AVERAGE_DENOMINATOR),'all_sparse_rows':rows,
        'policy_overlays':overlays,'policy_overlay_count':len(overlays),
        'untouched_uniform_default_rows':untouched,
        'sparse_numeric_row_count':len(rows),
        'policy_sha256_canonical_full_rows':None,
        'canonical_policy_row_count':ROW_COUNT,
        'max_magnitude_bits':{'R':max_r,'A':max_a,'positive_R_sum':max_positive,
                              'Q52_scaled_positive_R':max_scaled},
    }


def _json_bytes(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,
                       allow_nan=False)+'\n').encode('ascii')


def freeze(output_directory):
    output=Path(output_directory).expanduser().resolve()
    require(output!=ROOT and ROOT not in output.parents,'output must be outside checkout')
    output.mkdir(parents=True,exist_ok=False)
    status={'version':'sparse-epoch-reference-freeze-v1','status':'started','scope':SCOPE}
    written=0
    def write(name,body,cap=MAX_OUTPUT_BYTES):
        nonlocal written
        require(type(body) is bytes and len(body)<=cap,'artifact file byte cap')
        written+=len(body);require(written<=MAX_OUTPUT_BYTES,'artifact total byte cap')
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as target:target.write(body)
        return {'path':name,'bytes':len(body),'sha256':sha256(body).hexdigest()}
    try:
        source_identity=_source_capture()
        for name,record in source_identity['source_files'].items():
            body=(ROOT/name).read_bytes()
            require(sha256(body).hexdigest()==record['sha256'],'source changed before evidence copy')
            write('source/'+name,body,MAX_SOURCE_BYTES)
        boards={'first':list(BOARD_1),'second':list(BOARD_2)}
        input_proof={
            'version':'sparse-epoch-reference-input-v1','scope':SCOPE,
            'head':source_identity['head'],'source_identity':source_identity,
            'fixture':{'name':'PROOF9','private_pair_count':3,'full_rows':ROW_COUNT,
                       'R_denominator':str(REGRET_DENOMINATOR),
                       'A_denominator':str(AVERAGE_DENOMINATOR),
                       'literal_rows':1105,'template_nodes':388,'template_edges':410},
            'betting_case':_template_case(),
            'proposal_law':'uniform over 2520 ordered-combination boards',
            'epoch_semantics':'each epoch computes both seats from one frozen policy then updates cumulative unclipped integer R/A and quantizes the next complete policy',
            'boards':boards,'policy_default':{'kind':'uniform-q52','units':Q},
            'historical_weak_witness_note':HISTORICAL_WITNESS_NOTE,
            'limits':{'source_files':MAX_SOURCES,'source_file_bytes':MAX_SOURCE_BYTES,
                      'source_total_bytes':MAX_SOURCE_TOTAL,'numeric_rows_union':MAX_ROWS,
                      'numeric_snapshot_rows_total':MAX_SNAPSHOT_ROWS,
                      'epoch_json_bytes':MAX_EPOCH_BYTES,'artifact_total_bytes':MAX_OUTPUT_BYTES},
        }
        inputs_file=write('input-proof.json',_json_bytes(input_proof))

        fixture=Fixture();context=build_sampled_reference_context()
        require(fixture.row_count==ROW_COUNT and len(fixture.menus)==ROW_COUNT,
                'PROOF9 complete information-row inventory')
        by_private_pair={}
        for world in fixture.worlds:by_private_pair.setdefault(world.holdings,world.board)
        require(len(by_private_pair)==3,'expected three positive private pairs')
        # The source task fixes exactly two observations. It checks the separate
        # three-pair positive-support census without adding a third epoch.
        pairs=tuple(by_private_pair.items())
        require(tuple(by_private_pair.values())[:2]==(BOARD_1,BOARD_2),
                'fixed boards differ from the first private-pair representatives')
        selection_proof={
            'version':'sparse-epoch-board-selection-v1','source_head':source_identity['head'],
            'selection_rule':'first world board per ordered private holding pair in Fixture.worlds iteration order',
            'private_pair_count':len(pairs),
            'first_board_per_pair':[{'holdings':list(holdings),'board':list(board)} for holdings,board in pairs],
            'selected_epoch_boards':[list(BOARD_1),list(BOARD_2)],
            'selected_boards_positive_worlds':{
                'first':sum(1 for world in fixture.worlds if world.board==BOARD_1),
                'second':sum(1 for world in fixture.worlds if world.board==BOARD_2)},
            'proposal_law':'uniform',
            'context_receipt':{
                'template_nodes':len(context.nodes),
                'template_edges':sum(len(node.edges) for node in context.nodes),
                'normalizer_z':[context.normalizer.numerator,context.normalizer.denominator],
                'physical_proposal_count':len(context.physical.proposals),
                'profile_version':context.profile_version},
        }
        selection_file=write('board-selection.json',_json_bytes(selection_proof))
        initial,state1,state2=run_two_positive_epochs(fixture,context,BOARD_1,BOARD_2)
        frozen_b2=apply_epoch(fixture,context,initial,BOARD_2)
        h0,n0,_=_canonical_policy_digest(fixture,initial)
        h1,n1,changed10=_canonical_policy_digest(fixture,state1,initial)
        h2,n2,changed21=_canonical_policy_digest(fixture,state2,state1)
        hf,nf,changed2f=_canonical_policy_digest(fixture,frozen_b2)
        h2f,n2f,changed2f=_canonical_policy_digest(fixture,state2,frozen_b2)
        require((n0,n1,n2,nf,n2f)==(ROW_COUNT,)*5,'full policy digest row count')
        require(h1!=h0 and changed10>0,'E1 did not change policy from E0')
        require(h2!=h1 and changed21>0,'E2 did not change policy from E1')
        require(h2!=hf and h2f==h2 and changed2f>0,
                'E2 did not differ from the frozen-E0/B2 control')

        epoch_records=[];sparse_total=0;sparse_union=set()
        for state,previous,digest in ((state1,initial,h1),(state2,state1,h2)):
            document=_sparse_epoch(fixture,state)
            require(document['sparse_numeric_row_count']<=530*state.epoch,'per-transition union row cap')
            for row in document['all_sparse_rows']:
                key=row['key'];sparse_union.add((key['actor'],key['holding_index'],tuple(key['history_tokens'])))
            document['policy_sha256_canonical_full_rows']=digest
            document['changed_policy_rows_from_previous_epoch']=(
                sum(state.policy[key]!=previous.policy[key] for key in fixture.menus))
            require(document['changed_policy_rows_from_previous_epoch']>0,
                    'epoch must change at least one policy row')
            data=_json_bytes(document)
            require(len(data)<=MAX_EPOCH_BYTES,'per-epoch sparse JSON byte cap')
            artifact=write(f"epoch-{state.epoch}.json",data,MAX_EPOCH_BYTES)
            artifact['epoch']=state.epoch;artifact['sparse_numeric_row_count']=document['sparse_numeric_row_count']
            epoch_records.append(artifact);sparse_total+=document['sparse_numeric_row_count']
        require(sparse_total<=MAX_SNAPSHOT_ROWS and len(sparse_union)<=MAX_ROWS,
                'sparse snapshots or live union exceed independent two-transition bounds')
        final_capture=_source_capture()
        require(final_capture==source_identity,'source/HEAD drift during reference generation')
        result={
            'version':'sparse-epoch-reference-result-v1','status':'complete',
            'scope':SCOPE,'head':source_identity['head'],'input_proof':inputs_file,
            'board_selection':selection_file,
            'epochs':epoch_records,'sparse_numeric_rows_total':sparse_total,
            'sparse_numeric_rows_union':len(sparse_union),
            'policy_comparison':{
                'E0_uniform_sha256':h0,'E1_sha256':h1,'E2_sha256':h2,
                'frozen_E0_plus_B2_sha256':hf,'E0_to_E1_changed_rows':changed10,
                'E1_to_E2_changed_rows':changed21,'E2_vs_frozen_E0_plus_B2_changed_rows':changed2f,
                'all_rows_compared':ROW_COUNT,
            },
            'historical_weak_witness_note':HISTORICAL_WITNESS_NOTE,
            'complete_policy_table_retained':False,
            'policy_hash_serialization':'streamed canonical JSON rows [actor,holding_index,full_history_tokens,Q52_units] in Fixture.ordered_rows order; LF terminated',
            'total_artifact_bytes_before_result':written,
        }
        result_file=write('result.json',_json_bytes(result))
        status.update({'status':'complete','head':source_identity['head'],
                       'result':result_file,'artifact_bytes':written})
        write('process-status.json',_json_bytes(status))
        return result
    except Exception as exc:
        status.update({'status':'failed','error_type':type(exc).__name__,'error':str(exc),
                       'artifact_bytes':written})
        try:write('process-status.json',_json_bytes(status))
        except Exception:pass
        raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory',required=True,
                        help='fresh directory outside the checkout; existing paths are rejected')
    args=parser.parse_args(argv)
    result=freeze(args.output_directory)
    print(json.dumps({'status':result['status'],'head':result['head'],
                      'sparse_numeric_rows_total':result['sparse_numeric_rows_total'],
                      'artifact_bytes':result['total_artifact_bytes_before_result']},sort_keys=True))


if __name__=='__main__':main()
