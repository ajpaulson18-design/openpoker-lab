"""Replay immutable normal/optimized raw matrices with current independent math."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PINS={
    'normal':('527f77a5bbce5faf365b16c89006a865ea792f2289534907b2a23aed1df3d9b2',4_606_322),
    'optimized':('6039823ffa32b1f1c930895d94f5d0eb5bb2fe8c69e6fa5519e8d576b012199b',4_606_418),
}


BOOTSTRAP=('scripts/replay_native_grid_raw_packet.py','scripts/replay_native_policy_packet.py',
           'scripts/replay_native_grid_raw.py','scripts/replay_native_frozen_policy_state.py')


def authenticate_bootstrap():
    """Authenticate current trusted entrypoints before any project import."""
    if subprocess.check_output(['git','status','--porcelain','--',*BOOTSTRAP],cwd=ROOT):
        raise ValueError('uncommitted raw packet bootstrap')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    hashes={}
    for name in BOOTSTRAP:
        canonical=subprocess.check_output(['git','show',head+':'+name],cwd=ROOT)
        with (ROOT/name).open('rb') as source:raw=source.read((2<<20)+1)
        allowed=(canonical,canonical.replace(b'\n',b'\r\n')) if b'\r' not in canonical else (canonical,)
        if len(raw)>2<<20 or raw not in allowed:raise ValueError('raw packet bootstrap byte drift')
        hashes[name]=sha256(raw).hexdigest()
    return {'head':head,'raw_sha256':hashes}


def replay_raw_packets():
    bootstrap=authenticate_bootstrap()
    from scripts.replay_native_frozen_policy_state import bounded,read_json,require
    from scripts.replay_native_grid_raw import replay
    from scripts.replay_native_policy_packet import replay_packet

    def replay_case(directory):
        native=read_json(directory/'native-build-manifest.json')
        executable=directory.parent/'build'/Path(native['executable'].replace('\\','/')).name
        require(sha256(bounded(executable,8<<20)).hexdigest()==native['executable_sha256'],
                'raw archived executable byte identity')
        result=replay(directory)
        commands=sorted(directory.glob('*.command.json'))
        require(len(commands)==26,'raw cross-mode invocation census')
        result['observed_stream_sha256']={path.name.removesuffix('.command.json'):
            [s['sha256'] for s in read_json(directory/path.name.removesuffix('.command.json')/'process.json')['streams']]
            for path in commands}
        return result

    results={}
    for mode,(digest,size) in PINS.items():
        results[mode]=replay_packet(
            packet=ROOT/('benchmarks/results/native-frozen-grid-raw-v1/'+mode+'.zip'),
            archive_sha=digest,archive_bytes=size,member_count=234,case_replay=replay_case,
            extract_prefixes=('matrix/','build/'),case_directories=('matrix',))
    normal=results['normal']['results'][0]['cases']
    optimized=results['optimized']['results'][0]['cases']
    require(normal==optimized,'raw normal/optimized independent replay parity')
    require(results['normal']['results'][0]['observed_stream_sha256']==
            results['optimized']['results'][0]['observed_stream_sha256'],'raw cross-mode observed byte parity')
    require(authenticate_bootstrap()==bootstrap,'raw packet bootstrap changed during replay')
    return {'status':'all-raw-rows-exact','modes':results,'candidate_calls':0,
            'active_bootstrap':bootstrap,
            'archived_source_executed':False,
            'scope':'fixed-policy raw arithmetic only; no State update, training, quality or wider admission'}


if __name__=='__main__':print(json.dumps(replay_raw_packets(),indent=2))
