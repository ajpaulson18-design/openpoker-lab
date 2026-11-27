"""Explicit same-owner canonical/compact storage probes; frozen before compile."""
import argparse
import json
from pathlib import Path
from scripts import build_frozen_role_walk as prior
from scripts.run_opponent_action_study import git

engine=prior.engine
CANONICAL='role-storage-canonical'
COMPACT='role-storage-compact'
CONTROLS='role-storage-controls'
COMMON=(*prior.SOURCES[prior.TARGET],'scripts/build_compact_role_storage.py')
SOURCES={CANONICAL:('tests/native/virtual_opponent_role_storage_probe.cpp',*COMMON),
    COMPACT:('tests/native/virtual_opponent_role_compact_probe.cpp',*COMMON),
    CONTROLS:('tests/native/virtual_compact_role_store_controls.cpp',*COMMON)}


def register():
    prior.register()
    for target,sources in SOURCES.items():
        record=('native-'+target,sources)
        engine._need(target not in engine.TARGETS or engine.TARGETS[target]==record,'compact storage target registration drift')
        engine.TARGETS[target]=record


def build(output,*,target,sanitize=False):
    engine._need(target in SOURCES,'explicit compact storage target required');register();output=Path(output).resolve()
    engine._need(not output.exists() and output!=engine.ROOT and engine.ROOT not in output.parents,'compact storage fresh external build')
    names=(*SOURCES[target],'scripts/build_native_exact_four_street.py','third_party/boost-multiprecision-1.92.0/manifest.json',
        'third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt','third_party/boost-multiprecision-1.92.0/headers.zip')
    engine._need(not git('status','--porcelain','--untracked-files=all','--',*names),'compact storage complete build source committed')
    head=git('rev-parse','HEAD').decode().strip()
    tree={line.split('\t',1)[1]:line.split('\t',1)[0].split()[2] for line in git('ls-tree','-r',head).decode().splitlines()}
    raw={name:engine._bounded_read(engine.ROOT/name,2<<20) for name in names};output.mkdir()
    for name,body in raw.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
    (output/'source-identity.json').write_text(json.dumps({'head':head,'raw_sha256':{n:engine._hash(b) for n,b in raw.items()},
        'committed_blobs':{n:tree[n] for n in raw}},indent=2)+'\n')
    result=engine.build(output,target=target,sanitize=sanitize)
    engine._need(git('rev-parse','HEAD').decode().strip()==head and all((engine.ROOT/n).read_bytes()==b for n,b in raw.items()),
        'compact storage source drift during build')
    result['scope']=(('Explicit compact arithmetic/scale/phase controls in the same sparse Store only.' if target==CONTROLS else
        'Explicit fixed-template full52 deterministic T2 role walk with '+('canonical' if target==CANONICAL else 'compact')+
        ' persistent integers in the same sparse Store, canonical numeric output and bounded numeric-backend storage observation.')+
        ' No new lifetime, RNG, native allocator/RSS, stable/equal-quality speed or unrestricted NLHE admission.')
    path=Path(result.pop('manifest_path'));path.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return {**result,'manifest_path':str(path)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--target',choices=tuple(SOURCES),required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--sanitize',action='store_true')
    a=p.parse_args();print(json.dumps(build(a.output_dir,target=a.target,sanitize=a.sanitize),indent=2))
