"""Explicit source-frozen four-street role walk and its scalar controls."""
import argparse
import json
from pathlib import Path
from scripts import build_native_exact_four_street as engine
from scripts.run_opponent_action_study import git

TARGET='opponent-role-four-street'
CONTROLS='opponent-role-walk-controls'
COMMON=('native/virtual_opponent_role_walk.hpp','native/virtual_opponent_role_walk_forecast.hpp',
    'native/virtual_opponent_role_epoch.hpp','scripts/build_frozen_role_walk.py','scripts/run_opponent_action_study.py',
    *engine.TARGETS['virtual-single-pass-epoch-controls'][1][1:])
SOURCES={TARGET:('tests/native/virtual_opponent_role_walk_probe.cpp',*COMMON),
         CONTROLS:('tests/native/virtual_opponent_role_walk_controls.cpp',*COMMON)}
SCOPES={TARGET:'Explicit full52 fixed-template two-epoch signed-regret research updates from supplied deterministic Q52 ticket tapes. No RNG, longer learning, equal-quality speedup or unrestricted NLHE admission.',
        CONTROLS:'Bounded ticket-CDF intervals, signed raw words and foreign active-world binding controls only. No whole-game training or quality.'}


def register():
    for target,sources in SOURCES.items():
        record=('native-'+target,sources)
        engine._need(target not in engine.TARGETS or engine.TARGETS[target]==record,'role walk target registration drift')
        engine.TARGETS[target]=record


def build(output,*,target=TARGET,sanitize=False):
    engine._need(type(target) is str and target in SOURCES,'explicit role walk target required');register();output=Path(output).resolve()
    engine._need(not output.exists() and output!=engine.ROOT and engine.ROOT not in output.parents,'role walk fresh external build')
    names=(*SOURCES[target],'scripts/build_native_exact_four_street.py','third_party/boost-multiprecision-1.92.0/manifest.json',
        'third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt','third_party/boost-multiprecision-1.92.0/headers.zip')
    engine._need(not git('status','--porcelain','--untracked-files=all','--',*names),'role walk complete build source committed')
    head=git('rev-parse','HEAD').decode().strip()
    tree={line.split('\t',1)[1]:line.split('\t',1)[0].split()[2] for line in git('ls-tree','-r',head).decode().splitlines()}
    raw={name:engine._bounded_read(engine.ROOT/name,2<<20) for name in names};output.mkdir()
    for name,body in raw.items():
        path=output/'source'/name;path.parent.mkdir(exist_ok=True,parents=True);path.write_bytes(body)
    (output/'source-identity.json').write_text(json.dumps({'head':head,'raw_sha256':{n:engine._hash(b) for n,b in raw.items()},
        'committed_blobs':{n:tree[n] for n in raw}},indent=2)+'\n')
    result=engine.build(output,target=target,sanitize=sanitize)
    engine._need(git('rev-parse','HEAD').decode().strip()==head and all((engine.ROOT/n).read_bytes()==b for n,b in raw.items()),'role walk source drift during build')
    result['scope']=SCOPES[target];path=Path(result.pop('manifest_path'))
    path.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8');return {**result,'manifest_path':str(path)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--target',choices=tuple(SOURCES),default=TARGET);parser.add_argument('--sanitize',action='store_true')
    args=parser.parse_args();print(json.dumps(build(args.output_dir,target=args.target,sanitize=args.sanitize),indent=2))
