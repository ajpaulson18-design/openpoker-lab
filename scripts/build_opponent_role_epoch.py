"""Freeze explicit role-facade component sources using the existing compiler engine."""
import argparse
import json
from pathlib import Path
from scripts import build_native_exact_four_street as engine
from scripts.run_opponent_action_study import git

TARGET='opponent-role-epoch-controls'
SOURCES=('tests/native/virtual_opponent_role_epoch_controls.cpp','native/virtual_opponent_role_epoch.hpp',
    'scripts/build_opponent_role_epoch.py','scripts/run_opponent_action_study.py',
    *engine.TARGETS['virtual-single-pass-epoch-controls'][1][1:])
SCOPE='Synthetic callback-scoped joint-chance/History/Catalog/shared-Store role facade controls. No complete native sampled traversal, random training, longer lifetime, speed or quality admission.'


def register():
    record=('native-opponent-role-epoch-controls',SOURCES)
    engine._need(TARGET not in engine.TARGETS or engine.TARGETS[TARGET]==record,'role epoch target registration drift')
    engine.TARGETS[TARGET]=record


def build(output,*,sanitize=False):
    register();output=Path(output).resolve()
    engine._need(not output.exists() and output!=engine.ROOT and engine.ROOT not in output.parents,'role epoch fresh external build')
    names=(*SOURCES,'scripts/build_native_exact_four_street.py','third_party/boost-multiprecision-1.92.0/manifest.json',
           'third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt','third_party/boost-multiprecision-1.92.0/headers.zip')
    engine._need(not git('status','--porcelain','--untracked-files=all','--',*names),'role epoch complete build source committed')
    head=git('rev-parse','HEAD').decode().strip()
    tree={line.split('\t',1)[1]:line.split('\t',1)[0].split()[2] for line in git('ls-tree','-r',head).decode().splitlines()}
    raw={name:engine._bounded_read(engine.ROOT/name,2<<20) for name in names};output.mkdir()
    for name,body in raw.items():
        path=output/'source'/name;path.parent.mkdir(exist_ok=True,parents=True);path.write_bytes(body)
    (output/'source-identity.json').write_text(json.dumps({'head':head,'raw_sha256':{n:engine._hash(b) for n,b in raw.items()},
        'committed_blobs':{n:tree[n] for n in raw}},indent=2)+'\n')
    result=engine.build(output,target=TARGET,sanitize=sanitize)
    engine._need(git('rev-parse','HEAD').decode().strip()==head and all((engine.ROOT/n).read_bytes()==b for n,b in raw.items()),'role epoch build source drift')
    result['scope']=SCOPE;path=Path(result.pop('manifest_path'))
    path.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8');return {**result,'manifest_path':str(path)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--sanitize',action='store_true');args=parser.parse_args()
    print(json.dumps(build(args.output_dir,sanitize=args.sanitize),indent=2))
