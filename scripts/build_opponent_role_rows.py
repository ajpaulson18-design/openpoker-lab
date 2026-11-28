"""Explicit source-frozen row-arithmetic target using the unchanged build engine."""
import argparse
import json
from pathlib import Path
from scripts import build_native_exact_four_street as engine
from scripts.run_opponent_action_study import git

TARGET='opponent-role-row-controls'
SOURCES=('tests/native/opponent_role_row_controls.cpp','native/opponent_role_row.hpp',
         'scripts/build_opponent_role_rows.py','scripts/run_opponent_action_study.py',
         *engine.TARGETS['dyadic-policy-controls'][1][1:])
SCOPE='Compact role-row arithmetic and unchanged Q52 Quantizer controls only. No History/role-lease authority, poker draw, native whole walk, learning or quality.'


def register():
    record=('native-opponent-role-row-controls',SOURCES)
    engine._need(TARGET not in engine.TARGETS or engine.TARGETS[TARGET]==record,'role row target registration drift')
    engine.TARGETS[TARGET]=record


def build(output,*,sanitize=False):
    register()
    output=Path(output).resolve()
    engine._need(not output.exists() and output!=engine.ROOT and engine.ROOT not in output.parents,
                 'role row exclusive external build')
    names=(*SOURCES,'scripts/build_native_exact_four_street.py',
        'third_party/boost-multiprecision-1.92.0/manifest.json',
        'third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt','third_party/boost-multiprecision-1.92.0/headers.zip')
    engine._need(not git('status','--porcelain','--untracked-files=all','--',*names),'role row complete build source committed')
    head=git('rev-parse','HEAD').decode().strip()
    tree={line.split('\t',1)[1]:line.split('\t',1)[0].split()[2] for line in git('ls-tree','-r',head).decode().splitlines()}
    raw={name:engine._bounded_read(engine.ROOT/name,2<<20) for name in names}
    output.mkdir()
    for name,body in raw.items():
        path=output/'source'/name;path.parent.mkdir(exist_ok=True,parents=True);path.write_bytes(body)
    identity={'head':head,'raw_sha256':{n:engine._hash(b) for n,b in raw.items()},'committed_blobs':{n:tree[n] for n in raw}}
    (output/'source-identity.json').write_text(json.dumps(identity,indent=2)+'\n')
    result=engine.build(output,target=TARGET,sanitize=sanitize)
    engine._need(git('rev-parse','HEAD').decode().strip()==head and
                 all((engine.ROOT/n).read_bytes()==b for n,b in raw.items()),'role row source drift during build')
    # The unchanged engine captures this complete target, dependency and command.
    # Its generic fallback scope is replaced by this narrower component contract.
    result['scope']=SCOPE;path=Path(result.pop('manifest_path'))
    path.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return {**result,'manifest_path':str(path)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--sanitize',action='store_true');args=parser.parse_args()
    print(json.dumps(build(args.output_dir,sanitize=args.sanitize),indent=2))
