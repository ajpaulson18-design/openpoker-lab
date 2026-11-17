"""Source-frozen reference study and independent saved-grid replay; no native calls."""
import argparse
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from tests.virtual_grid_update_reference import (
    Fixture, Q, build_sampled_reference_context, freeze_grid, new_experiment_budget,
    raw_joint_update, complete_expectation, require,
)

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 32*1024*1024


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def source_identity():
    require(not git('status','--porcelain','--untracked-files=all','--','*.py','*.cpp','*.hpp','*.h'),
            'commit all source before the study')
    files = git('ls-files','--','*.py','*.cpp','*.hpp','*.h').splitlines()
    return {'head':git('rev-parse','HEAD'),
            'committed_blobs':source_blobs('HEAD'),
            'files':{name:sha256((ROOT/name).read_bytes()).hexdigest() for name in files}}


def source_blobs(revision):
    result = {}
    for line in git('ls-tree','-r',revision).splitlines():
        header,name = line.split('\t',1)
        if name.endswith(('.py','.cpp','.hpp','.h')):
            result[name] = header.split()[2]
    return result


def profile(fixture, name):
    if name == 'uniform':
        return fixture.grid()
    require(name == 'zero-skew', 'unknown fixed grid profile')
    result = {}
    for index,(key,menu) in enumerate(sorted(fixture.menus.items())):
        size = len(menu)
        if index%2 and size>1:
            values = [0]*size;values[index%size] = Q
        else:
            values = [1]*size;values[index%size] = Q-size+1
        result[key] = tuple(values)
    return result


def pair(value):
    return [str(value.numerator),str(value.denominator)]


def value(raw):
    require(type(raw) is list and len(raw)==2 and all(type(v) is str and len(v)<=500 for v in raw),
            'invalid saved rational')
    result = Fraction(int(raw[0]),int(raw[1]))
    require(pair(result)==raw, 'noncanonical saved rational')
    return result


def produce(destination, name, law):
    require(not destination.exists(), 'study destination must be fresh')
    before = source_identity()
    context = build_sampled_reference_context()
    budget = new_experiment_budget(context)
    fixture = Fixture()
    grid = freeze_grid(fixture,profile(fixture,name))
    expected_r,expected_a,expected_v = raw_joint_update(fixture,grid)
    actual_r,actual_a,actual_v = complete_expectation(context,grid,law,budget)
    exact = (expected_r,expected_a,expected_v)==(actual_r,actual_a,actual_v)
    require(source_identity()==before, 'source drift during study')
    destination.mkdir(parents=True)
    rows_path = destination/'rows.jsonl.gz'
    total = 0
    with rows_path.open('wb') as output:
        with gzip.GzipFile(filename='',mode='wb',fileobj=output,mtime=0) as compressed:
            for key in sorted(grid.units):
                row = {'key':key,'actions':grid.menus[key],'units':grid.units[key],
                       'expected_regret':list(map(pair,expected_r[key])),
                       'expected_average':list(map(pair,expected_a[key])),
                       'actual_regret':list(map(pair,actual_r[key])),
                       'actual_average':list(map(pair,actual_a[key]))}
                encoded = json.dumps(row,separators=(',',':')).encode()+b'\n'
                total += len(encoded)
                require(total<=MAX_BYTES, 'saved row byte ceiling')
                compressed.write(encoded)
    result = {'version':'frozen-q52-grid-expectation-v1','profile':name,'law':law,
              'source':before,'grid_sha256':grid.digest,'rows':len(grid.units),
              'action_slots':sum(map(len,grid.units.values())),'proposals':2520,
              'positive_board_evaluations':60,'zero_full_target_boards':2460,
              'zero_target_average_handling':'all 2520 q(B) included in each visible q(P) marginal',
              'expected_root':pair(expected_v),'actual_root':pair(actual_v),
              'rows_sha256':sha256(rows_path.read_bytes()).hexdigest(),'uncompressed_bytes':total,
              'resource_accounting':budget.receipt(), 'all_rows_exact':exact,
              'native_calls':0,'training_iterations':0,'quality_gate':None,
              'scope':'bounded fixed-policy raw update only; no sampled CFR+ convergence or native-grid ingestion'}
    (destination/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    require(exact,'complete frozen-grid expectation mismatch; candidate and expected rows preserved')
    return {k:v for k,v in result.items() if k!='source'}


def unique(pairs):
    result = {}
    for key,item in pairs:
        require(key not in result, 'duplicate saved JSON key')
        result[key] = item
    return result


def verify(destination):
    result = json.loads((destination/'result.json').read_text(encoding='utf-8'),object_pairs_hook=unique)
    require(result['version']=='frozen-q52-grid-expectation-v1', 'unknown saved study')
    require(result['law'] in ('uniform','river_weighted') and result['proposals']==2520 and
            result['positive_board_evaluations']==60 and result['zero_full_target_boards']==2460,
            'saved proposal scope changed')
    # Later documentation/evidence commits may differ; every executed source
    # byte must still match the captured committed tree and current checkout.
    before = source_identity()
    require(before['files']==result['source']['files'] and
            before['committed_blobs']==result['source']['committed_blobs'], 'saved study source closure drift')
    require(source_blobs(result['source']['head'])==result['source']['committed_blobs'],
            'saved source was not committed')
    rows_path = destination/'rows.jsonl.gz'
    require(rows_path.stat().st_size<=MAX_BYTES and sha256(rows_path.read_bytes()).hexdigest()==result['rows_sha256'],
            'saved row artifact drift')
    # Read-only replay uses the separate q-free literal-world reference. It
    # does not execute the sampled estimator or any native producer.
    context = build_sampled_reference_context()
    budget = new_experiment_budget(context)
    fixture = Fixture();grid=freeze_grid(fixture,profile(fixture,result['profile']))
    require(grid.digest==result['grid_sha256'], 'saved grid changed')
    regrets,averages,root = raw_joint_update(fixture,grid)
    count=slots=total=0
    ordered = iter(sorted(grid.units))
    with gzip.open(rows_path,'rb') as source:
        while True:
            line = source.readline(32769)
            if not line:break
            require(len(line)<=32768 and line.endswith(b'\n'), 'saved row line ceiling')
            total += len(line);require(total<=MAX_BYTES,'saved row byte ceiling')
            row=json.loads(line,object_pairs_hook=unique)
            k=row['key']
            require(type(k) is list and len(k)==3 and type(k[0]) is int and type(k[1]) is int and
                    type(k[2]) is list and all(type(t) is str for t in k[2]),'saved key scalar types')
            require(type(row['units']) is list and all(type(u) is int for u in row['units']),
                    'saved grid unit types')
            key=(k[0],k[1],tuple(k[2]))
            require(key==next(ordered,None), 'saved row inventory/order')
            require(row['actions']==list(grid.menus[key]) and row['units']==list(grid.units[key]), 'saved policy/menu drift')
            for name,expected in (('regret',regrets[key]),('average',averages[key])):
                require(tuple(map(value,row['actual_'+name]))==expected and
                        tuple(map(value,row['expected_'+name]))==expected,'saved raw update mismatch')
            count+=1;slots+=len(grid.units[key])
    require(next(ordered,None) is None and count==result['rows']==24420 and slots==result['action_slots']==58164,
            'saved census mismatch')
    require(total==result['uncompressed_bytes'] and value(result['actual_root'])==value(result['expected_root'])==root,
            'saved root/byte count mismatch')
    require(source_identity()==before,'source drift during saved replay')
    return {'rows':count,'slots':slots,'grid_sha256':grid.digest,'independent_saved_replay':True,
            'sampled_estimator_calls':0,'native_calls':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--profile',choices=('uniform','zero-skew'),default='uniform')
    parser.add_argument('--law',choices=('uniform','river_weighted'),default='uniform')
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    was_fresh = not args.output_dir.exists()
    try:
        result=verify(args.output_dir) if args.verify else produce(args.output_dir,args.profile,args.law)
    except Exception as error:
        if not args.verify and was_fresh:
            args.output_dir.mkdir(parents=True,exist_ok=True)
            failure=args.output_dir/'failure.json'
            if not failure.exists():
                failure.write_text(json.dumps({'error':str(error),'head':git('rev-parse','HEAD'),
                                              'profile':args.profile,'law':args.law})+'\n',encoding='utf-8')
        raise
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
