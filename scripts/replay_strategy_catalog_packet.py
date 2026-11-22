"""Recount immutable catalog/legacy/provider evidence using current source."""
from hashlib import sha256
import json
from pathlib import Path,PureWindowsPath
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
PINS={
    'catalog':('8bc5891ea688a7622f24e89d419e4b2d05ef924344e3f720e04e4ce8743b060a',2_463_508,305),
    'legacy-regression':('32f4e332320d0e1c622d5bfc81b0562d4cdf2eb6140967547756503346acfc7e',7_494_245,687),
    'provider-parity':('3c1181eadfdec6569e575777956a32e02fa26ed7a0895222d190eed1f4cefac9',4_638_454,386),
}
BOOTSTRAP=('scripts/replay_strategy_catalog_packet.py','scripts/replay_strategy_catalog.py',
    'scripts/replay_native_grid_raw.py','scripts/replay_native_frozen_policy_state.py',
    'scripts/replay_native_policy_packet.py','scripts/replay_shared_grid_owners_packet.py',
    'scripts/replay_frozen_grid_envelope.py','scripts/replay_native_policy_session.py',
    'scripts/build_native_exact_four_street.py')


def authenticate_bootstrap():
    if subprocess.check_output(['git','status','--porcelain','--',*BOOTSTRAP],cwd=ROOT):
        raise ValueError('uncommitted catalog packet bootstrap')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();hashes={}
    for name in BOOTSTRAP:
        canonical=subprocess.check_output(['git','show',head+':'+name],cwd=ROOT)
        with (ROOT/name).open('rb') as source:raw=source.read((2<<20)+1)
        allowed=(canonical,canonical.replace(b'\n',b'\r\n')) if b'\r' not in canonical else (canonical,)
        if len(raw)>2<<20 or raw not in allowed:raise ValueError('catalog packet bootstrap byte drift')
        hashes[name]=sha256(raw).hexdigest()
    return {'head':head,'raw_sha256':hashes}


def replay_packets():
    before=authenticate_bootstrap()
    loaded=[name for name,module in tuple(sys.modules.items()) if name!='__main__' and
        getattr(module,'__file__',None) and ROOT in Path(module.__file__).resolve().parents]
    if loaded:raise ValueError('catalog packet replay requires a fresh Python process')
    previous=(sys.pycache_prefix,sys.dont_write_bytecode)
    with TemporaryDirectory(prefix='catalog-current-python-',dir=ROOT.parent) as cache:
        sys.pycache_prefix=cache;sys.dont_write_bytecode=True
        try:
            from scripts.replay_native_frozen_policy_state import bounded,read_json,require,source_checkout_hashes
            from scripts.replay_native_grid_raw import process
            from scripts.replay_native_policy_packet import replay_packet
            from scripts.replay_strategy_catalog import replay as catalog_replay
            from scripts.replay_shared_grid_owners_packet import default_replay
            from scripts.replay_native_policy_session import replay as provider_replay
            def binary(directory,name):
                native=read_json(directory/'native-build-manifest.json')
                executable=directory.parent/name/PureWindowsPath(native['executable']).name
                require(sha256(bounded(executable,8<<20)).hexdigest()==native['executable_sha256'],
                        'catalog packet executable identity')
            def catalog_case(directory):
                native=read_json(directory/'native-build-manifest.json')
                executable=directory.parents[1]/'build/catalog'/PureWindowsPath(native['executable']).name
                require(sha256(bounded(executable,8<<20)).hexdigest()==native['executable_sha256'],
                        'catalog archived executable identity')
                return catalog_replay(directory)
            def regression_case(directory):
                result=default_replay(directory)
                head=read_json(directory/'source-identity.json')['head']
                names=('tests/test_native_virtual_dyadic_state.py','tests/test_native_dyadic_policy.py',
                    'tests/virtual_betting_template_reference.py','tests/virtual_frozen_update_reference.py')
                for name in names:
                    canonical=subprocess.check_output(['git','show',head+':'+name],cwd=ROOT)
                    raw=bounded(ROOT/name,2<<20)
                    require(sha256(raw).hexdigest() in source_checkout_hashes(sha256(canonical).hexdigest(),canonical),
                            'current saved State oracle differs from captured regression commit')
                from tests.test_native_virtual_dyadic_state import NativeVirtualDyadicStateTests
                from unittest.mock import patch
                methods=sorted(n for n in dir(NativeVirtualDyadicStateTests) if n.startswith('test_'))
                require(len(methods)==11,'legacy State saved checker census')
                state_results=[]
                native=read_json(directory.parent/'build/state/native-exact-build-manifest.json')
                exe=directory.parent/'build/state'/PureWindowsPath(native['executable']).name
                require(native['target']=='virtual-dyadic-state-controls' and
                    sha256(bounded(exe,8<<20)).hexdigest()==native['executable_sha256'],'State archived binary identity')
                for mode in ('normal','optimized'):
                    case=directory.parent/'state'/mode
                    raw=process(case,0);lines=raw.decode('ascii').splitlines()
                    with patch('tests.test_native_virtual_dyadic_state.run_bounded_child',
                               side_effect=ValueError('saved State replay must not launch a child')):
                        for method in methods:
                            checker=NativeVirtualDyadicStateTests(method);checker.lines=lines
                            getattr(checker,method)()
                    state_results.append({'mode':mode,'current_independent_checks':11,'stdout_sha256':sha256(raw).hexdigest()})
                return {'default':result,'saved_State_controls':state_results,'candidate_calls':0,
                    'scope':'complete legacy/provider parity, not sparse learning or timing acceptance'}
            results={}
            for name,(digest,size,count) in PINS.items():
                if name=='catalog':
                    prefixes=('formal/','build/catalog/');directories=('formal/normal','formal/optimized');checker=catalog_case
                elif name=='legacy-regression':
                    prefixes=('default/','state/','build/');directories=('default',);checker=regression_case
                else:
                    prefixes=('provider/','build/');directories=('provider',)
                    def checker(directory):
                        binary(directory,'build/provider')
                        return provider_replay(directory)
                results[name]=replay_packet(packet=ROOT/('benchmarks/results/sparse-strategy-catalog-v1/'+name+'.zip'),
                    archive_sha=digest,archive_bytes=size,member_count=count,case_replay=checker,
                    extract_prefixes=prefixes,case_directories=directories)
            normal,optimized=(result['result'] for result in results['catalog']['results'])
            require(normal==optimized,'catalog cross-mode independent replay parity')
            require(authenticate_bootstrap()==before,'catalog packet bootstrap changed during replay')
            return {'status':'catalog-and-preserved-regressions-exact','results':results,
                'active_bootstrap':before,'candidate_calls':0,'archived_source_executed':False,
                'current_project_imports':'fresh process, empty bytecode cache prefix, no bytecode writes',
                'scope':'catalog identity, legacy numerical and provider parity only; no native sparse epoch, quality, RSS or wider admission'}
        finally:sys.pycache_prefix,sys.dont_write_bytecode=previous


if __name__=='__main__':print(json.dumps(replay_packets(),indent=2))
