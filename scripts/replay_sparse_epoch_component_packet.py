"""Replay saved sparse-epoch packets with authenticated current Python checks.

This verifier reads immutable archives and saved process output. It never
imports archived source, launches a native candidate, or builds native code.
"""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import subprocess
import stat
import sys
from tempfile import TemporaryDirectory
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PACKET=ROOT/'benchmarks/results/sparse-epoch-component-v1'
MANIFEST_PIN=('ce73046f44c76fd587e9a8928c094d4114188ff99c58de03340840c5f585aaee',81661)
PINS={
    'component':('component.zip','4333f62c353f251da41f68c48f97530e95a7b1f90ac3b22d475f0443f6e50df7',1454836,104),
    'reference':('reference.zip','05963144a58137bf43b7dc395fa730045de691b3c970d663fd37952103d4b0f5',285959,27),
    'development':('development.zip','be6e460dd0b6a8c3d3d1662b7b98861848635ad6b86491c1aa0531eba7156974',765233,66),
}
BOOTSTRAP=(
    'scripts/replay_sparse_epoch_component_packet.py',
    'scripts/replay_native_frozen_policy_state.py',
    'scripts/replay_native_policy_packet.py',
    'scripts/replay_native_grid_raw.py',
    'scripts/freeze_sparse_epoch_reference.py',
    'tests/test_native_sparse_epoch.py',
    'tests/virtual_sparse_epoch_reference.py',
    'tests/test_sparse_epoch_reference.py',
)
MAX_ARCHIVE=8<<20
MAX_MEMBER=8<<20
MAX_EXPANDED=80<<20
MAX_SOURCE_TOTAL=64<<20
MAX_SOURCE_FILE=32<<20
COMPONENT_SCOPE=('Synthetic sparse vanilla epoch component controls only; no whole-game '
                 'changing-policy run, sampled trainer, quality or wider admission.')


def bounded(path,limit):
    path=Path(path)
    require(path.is_file() and path.stat().st_size<=limit,'saved file byte ceiling: '+str(path))
    with path.open('rb') as source:body=source.read(limit+1)
    require(len(body)<=limit,'saved file grew past byte ceiling: '+str(path))
    return body


def require(value,message):
    if not value:raise ValueError(message)


def digest(body):return sha256(body).hexdigest()


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,stderr=subprocess.PIPE)


def git_file(head,name,limit=MAX_SOURCE_FILE):
    size_raw=git('cat-file','-s',head+':'+name).strip()
    require(size_raw.isdigit() and int(size_raw)<=limit,'committed source file byte ceiling: '+name)
    body=git('show',head+':'+name)
    require(len(body)==int(size_raw),'committed source file changed while reading: '+name)
    return body


def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'duplicate JSON key')
        result[key]=value
    return result


def safe_name(name):
    path=PurePosixPath(name)
    require(type(name) is str and bool(name) and str(path)==name and
            not path.is_absolute() and '..' not in path.parts and
            '\\' not in name and ':' not in name,'unsafe packet member path')
    return name


def authenticate_bootstrap():
    require(not git('status','--porcelain','--untracked-files=all','--',*BOOTSTRAP),
            'sparse epoch packet bootstrap must be committed and clean')
    head=git('rev-parse','HEAD').decode('ascii').strip();hashes={}
    for name in BOOTSTRAP:
        canonical=git_file(head,name)
        with (ROOT/name).open('rb') as source:raw=source.read((2<<20)+1)
        allowed=(canonical,canonical.replace(b'\n',b'\r\n')) if b'\r' not in canonical else (canonical,)
        require(len(raw)<=2<<20 and raw in allowed,'current sparse epoch replay bootstrap drift: '+name)
        hashes[name]=digest(raw)
    return {'head':head,'raw_sha256':hashes}


def load_manifest():
    raw=bounded(PACKET/'manifest.json',1<<20)
    require((digest(raw),len(raw))==MANIFEST_PIN,'immutable packet manifest drift')
    manifest=json.loads(raw,object_pairs_hook=unique)
    require(manifest.get('version')=='sparse-epoch-component-v1' and
            manifest.get('status')=='complete','packet manifest identity')
    return manifest,digest(raw),len(raw)


def read_archive(name,pin,manifest):
    filename,expected_sha,expected_bytes,expected_count=pin
    raw=bounded(PACKET/filename,MAX_ARCHIVE)
    require(len(raw)<=MAX_ARCHIVE and len(raw)==expected_bytes and digest(raw)==expected_sha,
            'immutable sparse epoch archive pin drift: '+filename)
    record=manifest['archives'].get(filename)
    require(record is not None and record['sha256']==expected_sha and
            record['bytes']==expected_bytes and record['member_count']==expected_count,
            'manifest archive pin mismatch: '+filename)
    files={};inventory=[];expanded=0;casefold_names=set()
    with zipfile.ZipFile(BytesIO(raw),'r') as archive:
        infos=archive.infolist()
        require(len(infos)==expected_count,'archive member census: '+filename)
        for info in infos:
            member=safe_name(info.filename)
            file_type=stat.S_IFMT(info.external_attr>>16)
            require(member not in files and member.casefold() not in casefold_names and
                    not info.is_dir() and not info.flag_bits&1 and
                    file_type in (0,stat.S_IFREG) and info.file_size<=MAX_MEMBER,
                    'archive member boundary/type')
            casefold_names.add(member.casefold())
            expanded+=info.file_size
            require(expanded<=MAX_EXPANDED,'archive expanded byte ceiling')
            with archive.open(info,'r') as source:body=source.read(MAX_MEMBER+1)
            require(len(body)==info.file_size and len(body)<=MAX_MEMBER,'archive member size')
            files[member]=body
            inventory.append({'path':member,'bytes':len(body),'sha256':digest(body)})
    require(expanded<=MAX_EXPANDED and expanded==record['expanded_bytes'],
            'archive expanded byte inventory')
    require(inventory==record['members'],'archive member raw inventory differs from manifest')
    return files,{'archive':filename,'sha256':expected_sha,'bytes':len(raw),
                  'members':len(files),'expanded_bytes':expanded}


def verify_git_closure(files,prefix,closure):
    head=closure['head'];expected=closure['files']
    require(len(expected)==closure['file_count']<=128,'source closure count')
    git_tree={}
    for line in git('ls-tree','-r',head).decode('utf-8').splitlines():
        metadata,name=line.split('\t',1)
        if name in {row['path'] for row in expected}:git_tree[name]=metadata.split()[2]
    seen=set();total=0
    for row in expected:
        name=safe_name(row['path']);member=prefix+'/source/'+name
        require(name not in seen and member in files and row['bytes']<=MAX_SOURCE_FILE,
                'source closure member missing or duplicated')
        seen.add(name);body=files[member];total+=len(body)
        require(len(body)==row['bytes'] and digest(body)==row['sha256'] and
                git_tree.get(name)==row['blob'],'captured source raw/blob identity mismatch: '+name)
        canonical=git('show',head+':'+name)
        require(body==canonical or (b'\r' not in canonical and body==canonical.replace(b'\n',b'\r\n')),
                'captured source bytes differ from pinned committed source: '+name)
    require(total==closure['bytes'] and total<=MAX_SOURCE_TOTAL,'source closure byte total')
    return seen


def verify_native_manifest(files,member,source_prefix,closure):
    native=json.loads(files[member],object_pairs_hook=unique)
    require(native.get('target')=='virtual-sparse-epoch-controls' and
            native.get('scope')==COMPONENT_SCOPE,'native component build target/scope')
    source_hashes=native.get('source_sha256')
    require(type(source_hashes) is dict and bool(source_hashes),'native build source map missing')
    closure_map={row['path']:row['sha256'] for row in closure['files']}
    for name,value in source_hashes.items():
        safe_name(name)
        source_member=source_prefix+'/source/'+name
        require(source_member in files and digest(files[source_member])==value==closure_map.get(name),
                'native build source hash differs from captured source: '+name)
    return native


def current_source_check(names,archived_files,archive_prefix,active_hashes):
    for name in names:
        member=archive_prefix+'/source/'+name
        require(member in archived_files,'active oracle missing from archive: '+name)
        raw=bounded(ROOT/name,MAX_SOURCE_FILE)
        canonical=git_file(git('rev-parse','HEAD').decode('ascii').strip(),name)
        allowed={digest(canonical)}
        if b'\r' not in canonical:allowed.add(digest(canonical.replace(b'\n',b'\r\n')))
        require(digest(raw) in allowed and digest(archived_files[member]) in allowed,
                'active Python oracle differs from saved packet source: '+name)
        active_hashes[name]=digest(raw)


def replay_component(files,active_hashes):
    from scripts.replay_native_frozen_policy_state import ORACLE_SOURCES
    closure=next(v for k,v in _MANIFEST['source_closures'].items() if k=='component-normal')
    normal=verify_git_closure(files,'runs/normal',closure)
    normal_native=verify_native_manifest(files,'runs/normal/native-build-manifest.json','runs/normal',closure)
    optimized_closure=_MANIFEST['source_closures']['component-optimized']
    optimized=verify_git_closure(files,'runs/optimized',optimized_closure)
    optimized_native=verify_native_manifest(files,'runs/optimized/native-build-manifest.json','runs/optimized',optimized_closure)
    build_native=json.loads(files['build/native-exact-build-manifest.json'],object_pairs_hook=unique)
    require(normal_native==optimized_native==build_native,
            'component build/run source manifests differ')
    require(normal==optimized,'normal/optimized source closure mismatch')
    current_names=tuple(ORACLE_SOURCES)+('tests/test_native_sparse_epoch.py',)
    current_source_check(current_names,files,'runs/normal',active_hashes)
    current_source_check(current_names,files,'runs/optimized',active_hashes)

    from tests.test_native_sparse_epoch import NativeSparseEpochTests
    from unittest.mock import patch
    checked=[];outputs=[]
    methods=sorted(name for name in dir(NativeSparseEpochTests) if name.startswith('test_'))
    require(len(methods)==4,'sparse epoch component checker census')
    for mode in ('normal','optimized'):
        base='runs/'+mode+'/process/'
        process=json.loads(files['runs/'+mode+'/process/process.json'],object_pairs_hook=unique)
        stdout=files[base+'stdout.bin'];stderr=files[base+'stderr.bin']
        request=files[base+'request.bin']
        require(process.get('status')=='exited' and process.get('returncode')==0 and
                process.get('actual_exit_observed') is True and process.get('automatic_retries')==0 and
                process.get('failures')==[] and process.get('request_sha256')==digest(request) and
                not request and not stderr and len(process.get('streams',[]))==2 and
                process['streams'][0]=={'observed_bytes':len(stdout),'saved_bytes':len(stdout),'sha256':digest(stdout)} and
                process['streams'][1]=={'observed_bytes':len(stderr),'saved_bytes':len(stderr),'sha256':digest(stderr)},
                'saved native process receipt is not successful')
        lines=stdout.decode('ascii').splitlines()
        with patch('tests.test_native_sparse_epoch.run_bounded_child',
                   side_effect=ValueError('saved sparse component replay forbids launching a candidate')):
            for method in methods:
                checker=NativeSparseEpochTests(method);checker.lines=lines
                checker.process=process;checker.stdout=stdout;checker.stderr=stderr
                getattr(checker,method)();checked.append(mode+':'+method)
        outputs.append({'mode':mode,'saved_stdout_bytes':len(stdout),
                        'saved_stdout_sha256':digest(stdout),'saved_stderr_bytes':len(stderr),
                        'current_numerical_methods':len(methods)})
    require(files['runs/normal/process/stdout.bin']==files['runs/optimized/process/stdout.bin'] and
            files['runs/normal/process/stderr.bin']==files['runs/optimized/process/stderr.bin'],
            'normal/optimized native saved process bytes differ')
    return {'status':'saved-component-controls-exact','outputs':outputs,
            'current_checks':checked,'candidate_calls':0}


def _replay_reference(files):
    closure=_MANIFEST['source_closures']['independent-reference']
    source_names=verify_git_closure(files,'artifact',closure)
    # Authenticate the full current reference dependency closure before import.
    global ACTIVE_HASHES
    current_source_check(sorted(source_names),files,'artifact',ACTIVE_HASHES)
    from scripts.freeze_sparse_epoch_reference import (
        _canonical_policy_digest,_json_bytes,_sparse_epoch,_template_case,
    )
    from tests.virtual_dyadic_training_reference import Fixture
    from tests.virtual_frozen_sample_reference import build_sampled_reference_context
    from tests.virtual_sparse_epoch_reference import run_two_positive_epochs,apply_epoch
    artifact=lambda name: files['artifact/'+name]
    proof_raw=artifact('input-proof.json')
    proof=json.loads(proof_raw,object_pairs_hook=unique)
    result_raw=artifact('result.json')
    result=json.loads(result_raw,object_pairs_hook=unique)
    process=json.loads(artifact('process-status.json'),object_pairs_hook=unique)
    selection=json.loads(artifact('board-selection.json'),object_pairs_hook=unique)
    require(proof['head']==closure['head']==result['head']==process['head'] and
            result['status']=='complete' and process['status']=='complete',
            'reference input/result/process identity')
    require(result['input_proof']=={'path':'input-proof.json','bytes':len(proof_raw),
            'sha256':digest(proof_raw)} and
            result['board_selection']=={'path':'board-selection.json',
                'bytes':len(artifact('board-selection.json')),
                'sha256':digest(artifact('board-selection.json'))},
            'reference input/board proof record hashes')
    require(process['result']=={'path':'result.json','bytes':len(result_raw),
            'sha256':digest(result_raw)} and process['scope']==proof['scope']==result['scope'],
            'reference final process/result/scope receipt')
    require(proof['boards']=={'first':[16,17,32,33,35],'second':[17,24,33,35,37]} and
            selection['selected_epoch_boards']==[proof['boards']['first'],proof['boards']['second']],
            'reference selected board pin')
    require(proof['fixture']['name']=='PROOF9' and proof['fixture']['private_pair_count']==3 and
            proof['fixture']['full_rows']==24420 and proof['proposal_law']=='uniform over 2520 ordered-combination boards',
            'reference fixture/input scope')
    limits=proof['limits']
    require(limits['source_files']<=128 and limits['source_file_bytes']==MAX_SOURCE_FILE and
            limits['source_total_bytes']==MAX_SOURCE_TOTAL and limits['numeric_rows_union']==1060 and
            limits['numeric_snapshot_rows_total']==1590 and limits['epoch_json_bytes']==4<<20 and
            limits['artifact_total_bytes']==32<<20,
            'reference proof resource ceilings')
    fixture=Fixture();context=build_sampled_reference_context()
    b1=tuple(proof['boards']['first']);b2=tuple(proof['boards']['second'])
    require(fixture.row_count==24420 and len(fixture.menus)==24420 and
            len(context.nodes)==388 and sum(len(node.edges) for node in context.nodes)==410,
            'current PROOF9 template/reference geometry')
    require(proof['betting_case']==_template_case() and
            proof['source_identity']['head']==closure['head'] and
            proof['source_identity']['source_file_count']==closure['file_count'] and
            proof['source_identity']['source_bytes']==closure['bytes'],
            'reference input proof source/betting receipt')
    expected_sources={row['path']:{'blob':row['blob'],'sha256':row['sha256'],'bytes':row['bytes']}
                      for row in closure['files']}
    require(proof['source_identity']['source_files']==expected_sources,
            'reference input proof source closure differs from packet inventory')
    by_pair={}
    for world in fixture.worlds:by_pair.setdefault(world.holdings,world.board)
    require(len(by_pair)==3 and tuple(by_pair.values())[:2]==((16,17,32,33,35),(17,24,33,35,37)),
            'reference fixture private-pair board selection')
    expected_pairs=[{'holdings':list(holdings),'board':list(board)} for holdings,board in by_pair.items()]
    expected_selection={
        'version':'sparse-epoch-board-selection-v1','source_head':closure['head'],
        'selection_rule':'first world board per ordered private holding pair in Fixture.worlds iteration order',
        'private_pair_count':3,'first_board_per_pair':expected_pairs,
        'selected_epoch_boards':[list(b1),list(b2)],'proposal_law':'uniform',
        'selected_boards_positive_worlds':{
            'first':sum(1 for world in fixture.worlds if world.board==b1),
            'second':sum(1 for world in fixture.worlds if world.board==b2)},
        'context_receipt':{'template_nodes':len(context.nodes),
            'template_edges':sum(len(node.edges) for node in context.nodes),
            'normalizer_z':[context.normalizer.numerator,context.normalizer.denominator],
            'physical_proposal_count':len(context.physical.proposals),
            'profile_version':context.profile_version}}
    require(selection==expected_selection,
            'reference full board-selection/context proof')
    initial,state1,state2=run_two_positive_epochs(fixture,context,b1,b2)
    frozen_b2=apply_epoch(fixture,context,initial,b2)
    h0,_,_=_canonical_policy_digest(fixture,initial)
    h1,_,changed10=_canonical_policy_digest(fixture,state1,initial)
    h2,_,changed21=_canonical_policy_digest(fixture,state2,state1)
    hf,_,_=_canonical_policy_digest(fixture,frozen_b2)
    h2f,_,changed2f=_canonical_policy_digest(fixture,state2,frozen_b2)
    saved_comp=result['policy_comparison']
    expected_comp={'E0_uniform_sha256':h0,'E1_sha256':h1,'E2_sha256':h2,
        'frozen_E0_plus_B2_sha256':hf,'E0_to_E1_changed_rows':changed10,
        'E1_to_E2_changed_rows':changed21,'E2_vs_frozen_E0_plus_B2_changed_rows':changed2f,
        'all_rows_compared':24420}
    require(saved_comp==expected_comp and h1!=h0 and h2!=h1 and h2!=hf and
            h2f==h2 and changed2f>0,
            'reference canonical full-policy result differs')
    states=(state1,state2);epoch_results=[];sparse_total=0
    require(len(result['epochs'])==2,'reference epoch record count')
    for state,saved_record in zip(states,result['epochs']):
        epoch_raw=artifact('epoch-%d.json'%state.epoch)
        require(len(epoch_raw)<=4<<20,'reference epoch JSON resource ceiling')
        document=json.loads(epoch_raw,object_pairs_hook=unique)
        independent=_sparse_epoch(fixture,state)
        canonical,rows,changed=_canonical_policy_digest(
            fixture,state,initial if state.epoch==1 else state1)
        independent['policy_sha256_canonical_full_rows']=canonical
        independent['changed_policy_rows_from_previous_epoch']=changed
        require(document==independent,'reference sparse rows/policy units differ at epoch %d'%state.epoch)
        encoded=_json_bytes(document)
        require(encoded==epoch_raw,'reference epoch canonical JSON bytes differ')
        require(saved_record['epoch']==state.epoch and saved_record['bytes']==len(encoded) and
                saved_record['sha256']==digest(encoded) and saved_record['sparse_numeric_row_count']==document['sparse_numeric_row_count'],
                'reference epoch manifest hash/count differs')
        sparse_total+=rows_count(document)
        epoch_results.append({'epoch':state.epoch,'sparse_rows':document['sparse_numeric_row_count'],
            'policy_overlays':document['policy_overlay_count'],'canonical_policy_sha256':canonical,
            'epoch_json_sha256':digest(encoded)})
    require(sparse_total==result['sparse_numeric_rows_total']==1308 and
            result['sparse_numeric_rows_union']<=1060 and
            sum(len(artifact(name)) for name in ('input-proof.json','board-selection.json',
                'epoch-1.json','epoch-2.json','result.json','process-status.json'))<=32<<20,
            'reference sparse totals/artifact resource bounds')
    return {'status':'independent-two-epoch-reference-exact','epochs':epoch_results,
            'policy_comparison':expected_comp,'candidate_calls':0}


def rows_count(document):
    return len(document['all_sparse_rows'])


def replay_development(files):
    closuremap=_MANIFEST['source_closures']
    verify_git_closure(files,'component2-development/normal',closuremap['component2-development'])
    introduced=closuremap['component1-introduced-source']
    require(introduced['head']=='f82fac8b31476a64af0d3d74612a8bae9ad611ea' and
            introduced['file_count']==4,'historical compile-failure source pin')
    historical_tree={}
    for line in git('ls-tree','-r',introduced['head']).decode('utf-8').splitlines():
        metadata,name=line.split('\t',1);historical_tree[name]=metadata.split()[2]
    for item in introduced['files']:
        body=files['component1-compile-failure/introduced-source/'+item['path']]
        require(len(body)==item['bytes'] and digest(body)==item['sha256'] and
                historical_tree.get(item['path'])==item['blob'] and
                git('cat-file','blob',item['blob'])==body,'historical introduced source mismatch')
    failure=json.loads(files['component1-compile-failure/build/build-failure.json'],object_pairs_hook=unique)
    c2=json.loads(files['component2-development/normal/process/process.json'],object_pairs_hook=unique)
    interim=json.loads(files['interim-full-scan/status.json'],object_pairs_hook=unique)
    require(failure['returncode']!=0 and c2['status']=='exited' and c2['returncode']==0 and
            interim['executed'] is False,'development evidence classification')
    header=files['component2-development/normal/source/native/virtual_sparse_strategy_epoch.hpp']
    controls=files['component2-development/normal/source/tests/native/virtual_sparse_epoch_controls.cpp']
    require(b'raw regret does not center on the leased policy' not in header and
            b'uncentered-regret' not in controls,'component2 pre-centering classification')
    return {'status':'development-evidence-authenticated','compile_failure_returncode':failure['returncode'],
            'component2_saved_exit':c2['returncode'],'component2_centering_guard':'absent',
            'interim_full_scan_executed':False,'numerical_pass_claimed':False}


def replay_packets():
    global _MANIFEST,ACTIVE_HASHES
    bootstrap=authenticate_bootstrap()
    loaded=[name for name,module in tuple(sys.modules.items()) if name!='__main__' and
        getattr(module,'__file__',None) and ROOT in Path(module.__file__).resolve().parents]
    require(not loaded,'sparse epoch packet replay requires a fresh Python process')
    manifest,manifest_sha,manifest_bytes=load_manifest();_MANIFEST=manifest;ACTIVE_HASHES={}
    previous=(sys.pycache_prefix,sys.dont_write_bytecode)
    with TemporaryDirectory(prefix='sparse-epoch-current-python-',dir=ROOT.parent) as cache:
        sys.pycache_prefix=cache;sys.dont_write_bytecode=True
        try:
            archives={};results={}
            for name,pin in PINS.items():archives[name]=read_archive(name,pin,manifest)
            results['component']=replay_component(archives['component'][0],ACTIVE_HASHES)
            results['reference']=_replay_reference(archives['reference'][0])
            results['development']=replay_development(archives['development'][0])
            require(authenticate_bootstrap()==bootstrap,'replay bootstrap changed during packet replay')
            for name,(filename,expected_sha,expected_bytes,_) in PINS.items():
                raw=(PACKET/filename).read_bytes()
                require(len(raw)==expected_bytes and digest(raw)==expected_sha,'packet changed during replay')
            return {'status':'sparse-epoch-component-reference-packets-exact',
                'manifest':{'sha256':manifest_sha,'bytes':manifest_bytes},
                'archives':{name:entry[1] for name,entry in archives.items()},
                'results':results,'active_bootstrap':bootstrap,'active_source_sha256':ACTIVE_HASHES,
                'candidate_calls':0,'archived_source_executed':False,
                'python_imports':'fresh process and isolated bytecode-cache prefix',
                'scope':'saved synthetic component and independent two-epoch reference only; no whole-game learning, quality, convergence, or scale claim'}
        finally:sys.pycache_prefix,sys.dont_write_bytecode=previous


if __name__=='__main__':print(json.dumps(replay_packets(),indent=2,sort_keys=True))
