"""Replay pinned session matrices and timing evidence; execute no archived code."""
from hashlib import sha256
import json
from pathlib import Path,PureWindowsPath
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
PINS={
    'normal':('31488c428c628b90d0055050774551a1cb92b98fbd7a004319229b803ab65d14',4_646_296,389),
    'optimized':('fddf7fd23cbaaf16ce52cf140ef6543712356d85d2785b3d09f7a0d5b1d5dda4',4_646_321,389),
    'benchmark':('5e3bc0642a44ade1899ff1cf2daed9cc62195160d4de5f964a6a5f5e8469c935',8_339_732,616),
}
BOOTSTRAP=('scripts/replay_native_policy_session_packet.py','scripts/replay_native_policy_session.py',
    'scripts/replay_policy_session_benchmark.py','scripts/replay_native_grid_raw.py',
    'scripts/replay_native_policy_packet.py','scripts/replay_native_frozen_policy_state.py')


def authenticate_bootstrap():
    if subprocess.check_output(['git','status','--porcelain','--',*BOOTSTRAP],cwd=ROOT):
        raise ValueError('uncommitted session packet bootstrap')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();hashes={}
    for name in BOOTSTRAP:
        canonical=subprocess.check_output(['git','show',head+':'+name],cwd=ROOT)
        with (ROOT/name).open('rb') as source:raw=source.read((2<<20)+1)
        allowed=(canonical,canonical.replace(b'\n',b'\r\n')) if b'\r' not in canonical else (canonical,)
        if len(raw)>2<<20 or raw not in allowed:raise ValueError('session packet bootstrap byte drift')
        hashes[name]=sha256(raw).hexdigest()
    return {'head':head,'raw_sha256':hashes}


def replay_packets():
    before=authenticate_bootstrap()
    # A fresh dedicated entrypoint plus an empty cache prefix makes current
    # project imports compile source instead of reading an ignored old .pyc.
    project_modules=[name for name,module in tuple(sys.modules.items())
        if name!='__main__' and getattr(module,'__file__',None) and
        ROOT in Path(module.__file__).resolve().parents]
    if project_modules:raise ValueError('session packet replay requires a fresh Python process')
    previous=(sys.pycache_prefix,sys.dont_write_bytecode)
    with TemporaryDirectory(prefix='session-current-python-',dir=ROOT.parent) as cache:
        sys.pycache_prefix=cache;sys.dont_write_bytecode=True
        try:
            from scripts.replay_native_frozen_policy_state import bounded,read_json,require
            from scripts.replay_native_policy_packet import replay_packet
            from scripts.replay_native_policy_session import replay as session_replay
            from scripts.replay_policy_session_benchmark import replay as benchmark_replay
            def replay_case(directory):
                if directory.name=='benchmark':
                    for kind in ('baseline','session'):
                        native=read_json(directory/(kind+'-native-build-manifest.json'))
                        executable=directory.parent/'build'/kind/PureWindowsPath(native['executable']).name
                        require(sha256(bounded(executable,8<<20)).hexdigest()==native['executable_sha256'],
                                'benchmark archived executable bytes')
                    return benchmark_replay(directory)
                native=read_json(directory/'native-build-manifest.json')
                executable=directory.parent/'build'/PureWindowsPath(native['executable']).name
                require(sha256(bounded(executable,8<<20)).hexdigest()==native['executable_sha256'],
                        'session archived executable bytes')
                return session_replay(directory)
            results={}
            for name,(digest,size,count) in PINS.items():
                prefix='benchmark' if name=='benchmark' else 'matrix'
                results[name]=replay_packet(packet=ROOT/('benchmarks/results/native-frozen-policy-session-v1/'+name+'.zip'),
                    archive_sha=digest,archive_bytes=size,member_count=count,case_replay=replay_case,
                    extract_prefixes=(prefix+'/','build/'),case_directories=(prefix,))
            normal=results['normal']['results'][0];optimized=results['optimized']['results'][0]
            require(normal['cases']==optimized['cases'] and normal['observed_stream_sha256']==optimized['observed_stream_sha256'],
                    'session cross-mode independent results/observed byte parity')
            require(authenticate_bootstrap()==before,'session packet bootstrap changed during replay')
            return {'status':'session-matrices-and-timing-replayed','results':results,
                'active_bootstrap':before,'current_project_imports':'fresh process, empty cache prefix, bytecode writes disabled',
                'candidate_calls':0,'archived_source_executed':False,
                'scope':'named immutable-session raw math/setup amortization only; no training, quality or wider admission'}
        finally:sys.pycache_prefix,sys.dont_write_bytecode=previous


if __name__=='__main__':print(json.dumps(replay_packets(),indent=2))
