"""Read-only shared-owner parity replay; no archived code or candidate calls."""
from hashlib import file_digest,sha256
import json
from pathlib import Path,PureWindowsPath
import subprocess
import zipfile

from scripts.replay_native_frozen_policy_state import bounded,read_json,replay as policy_replay,require,source_checkout_hashes
from scripts.replay_frozen_grid_envelope import replay as envelope_replay
from scripts.replay_native_policy_packet import replay_packet

ROOT=Path(__file__).resolve().parents[1]


def default_replay(directory):
    identity=read_json(directory/'source-identity.json');head=identity['head']
    require(type(head) is str and len(head)==40 and all(c in '0123456789abcdef' for c in head),'shared-owner source commit grammar')
    # The archive has already been pinned and every member authenticated. Now
    # authenticate the current complete-observation checker before importing it.
    names=('scripts/check_native_training_studies.py','tests/test_native_exact_reach.py',
           'tests/virtual_frozen_run_control.py','tests/virtual_dyadic_sweep_capture.py')
    for name in names:
        raw=bounded(ROOT/name,2<<20);canonical=subprocess.check_output(['git','show',head+':'+name],cwd=ROOT)
        require(sha256(raw).hexdigest() in source_checkout_hashes(identity['raw_sha256'][name],canonical),'current training receipt checker drift')
    # build_native_exact_four_street is an imported, trusted current metadata
    # bootstrap; it is never used to rebuild or run an archived candidate here.
    name='scripts/build_native_exact_four_street.py'
    require(not subprocess.check_output(['git','status','--porcelain','--',name],cwd=ROOT),'active build metadata drift')
    from scripts.check_native_training_studies import verify_observation
    process=read_json(directory/'observed/process.json')
    result=verify_observation(process,'virtual-dyadic-training')
    raw=bounded(directory/'observed/stdout.bin',4<<20)
    require(sha256(raw).hexdigest()==process['streams'][0]['sha256'],'retained complete-training numeric stream drift')
    require(not bounded(directory/'observed/stderr.bin',65536),'complete-training stderr')
    request=bounded(directory/'observed/request.bin',1025)
    require(request==b'DYADIC_T2_V1 TRAIN_TEN_BOUNDED_DIVISION\n' and sha256(request).hexdigest()==process['request_sha256'],'complete-training request identity')
    native=read_json(directory/'native-build-manifest.json');command=read_json(directory/'command.json')
    require(native['target']=='virtual-dyadic-training' and len(command)==2 and command[0]==native['executable'] and
            PureWindowsPath(command[1]).name=='page-images','complete-training invocation identity')
    executable=directory.parent/'build/default'/PureWindowsPath(native['executable']).name
    require(sha256(bounded(executable,8<<20)).hexdigest()==native['executable_sha256'],'archived default executable identity')
    expected=read_json(directory/'protocol.json')['stable_sidecars']
    missing={}
    for name,digest in expected.items():
        path=directory/'observed'/name
        if path.is_file():require(sha256(bounded(path,4<<20)).hexdigest()==digest,'retained owner sidecar drift')
        else:missing[name]=digest
    require(set(missing)=={'page-images/committed.bin','page-images/staged.bin'},'canonical checkpoint reference inventory')
    canonical_archive=ROOT/'benchmarks/results/native-dyadic-buffered-ten-card-accepted-v1/evidence.zip'
    require(canonical_archive.stat().st_size==10_270_677,'canonical checkpoint archive byte identity')
    with canonical_archive.open('rb') as source:
        require(file_digest(source,'sha256').hexdigest()=='e82d5f8b40340893213ad9f73ac8ee71483119598551ce4db90ee8ff95a4674b','canonical checkpoint archive drift')
    with zipfile.ZipFile(canonical_archive) as archive:
        for name,digest in missing.items():
            with archive.open('cohort/'+name) as source:raw=source.read(23_701_776+1)
            require(len(raw)==23_701_776 and sha256(raw).hexdigest()==digest,'canonical checkpoint bytes drift')
    return {**result,'canonical_checkpoint_references_authenticated':2,'candidate_calls':0,
            'scope':'existing ten-card complete-wire/owner parity only; no speed, raw-update or wider-capacity acceptance'}


def replay_case(directory):
    if directory.name=='snapshot':return policy_replay(directory)
    if directory.name=='envelope':return envelope_replay(directory)
    return default_replay(directory)


def replay_shared_packet():
    result=replay_packet(packet=ROOT/'benchmarks/results/native-frozen-grid-shared-owners-v1/verification.zip',
        archive_sha='e34d62021b526e0e52d3c291310b579f48c54b6cdc018e8c3564c8087803a2f9',
        archive_bytes=5_938_835,member_count=215,case_replay=replay_case,
        extract_prefixes=('snapshot/','envelope/','default/','build/'),case_directories=('snapshot','envelope','default'))
    return {**result,'scope':'shared contract/reach parity only; raw-update producer remains unimplemented'}


if __name__=='__main__':print(json.dumps(replay_shared_packet(),indent=2))
