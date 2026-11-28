"""Replay immutable Q52 evidence using current authenticated oracle source.

Unrelated later repository additions do not invalidate historical mathematics.
Archived source is authenticated as evidence and is never imported or executed.
"""
import argparse
from fractions import Fraction
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PACKET=ROOT/'benchmarks/results/frozen-q52-update-reference-v1'
FROZEN_HEAD='0c94835184878a8dada5b58847d87e93ef796dc0'
ARCHIVE_SHA='f34e7c7e76da800d0d9067f1c73c6cdbbadc7f053f8c6920d495ac8f041c6687'
ORACLE_SOURCES=(
    'pokerlab/__init__.py','pokerlab/cards.py',
    'scripts/matrix_free_certificate_budget.py','scripts/matrix_free_four_street_rules.py',
    'scripts/preflop_validation.py','tests/full_deck_public_chance_reference.py',
    'tests/test_native_dyadic_policy.py','tests/test_native_exact_reach.py',
    'tests/virtual_betting_template_reference.py','tests/virtual_dyadic_training_reference.py',
    'tests/virtual_frozen_run_control.py','tests/virtual_frozen_update_reference.py',
    'tests/virtual_frozen_value_reference.py',
)
MAX_JSON=1<<20
MAX_ROWS_BYTES=32<<20


def require(condition,message):
    if not condition:raise ValueError(message)


def unique(pairs):
    result={}
    for k,v in pairs:
        require(k not in result,'duplicate JSON key');result[k]=v
    return result


def decode_json(raw,limit=MAX_JSON):
    require(len(raw)<=limit,'JSON byte ceiling')
    return json.loads(raw,object_pairs_hook=unique)


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def source_checkout_hashes(archived_hash,canonical):
    """Accept exact pinned bytes, never normalize the candidate source."""
    result={archived_hash,sha256(canonical).hexdigest()}
    if b'\r' not in canonical:
        result.add(sha256(canonical.replace(b'\n',b'\r\n')).hexdigest())
    return result


def authenticate_oracle(source,root=ROOT):
    require(source['head']==FROZEN_HEAD,'unknown historical source')
    hashes={}
    for name in ORACLE_SOURCES:
        path=root/name
        require(path.is_file() and path.stat().st_size<=MAX_JSON,'oracle source bound/missing file')
        hashes[name]=sha256(path.read_bytes()).hexdigest()
        if hashes[name]!=source['files'].get(name):
            # Accept exact LF/CRLF checkout forms of the committed blob.
            # The archived raw form may itself contain historical mixed
            # endings. Never normalize the candidate to hide other drift.
            try:canonical=subprocess.check_output(['git','show',FROZEN_HEAD+':'+name],cwd=ROOT)
            except subprocess.CalledProcessError as error:
                raise ValueError('historical oracle blob unavailable: '+name) from error
            require(hashes[name] in source_checkout_hashes(source['files'].get(name),canonical),
                    'current oracle source drift: '+name)
    return hashes


def rational(raw,budget):
    require(type(raw) is list and len(raw)==2 and all(type(x) is str and 0<len(x)<=220 for x in raw),
            'saved rational grammar')
    n,d=map(int,raw)
    require(abs(n).bit_length()<=704 and 0<d and d.bit_length()<=704,'saved rational width')
    value=budget.div(budget.input(n,'saved numerator'),budget.input(d,'saved denominator'),'saved rational')
    require(raw==[str(value.numerator),str(value.denominator)],'noncanonical saved rational')
    return value


def expected_policy(fixture,name):
    if name=='uniform':return fixture.grid()
    require(name=='zero-skew','unknown saved profile')
    result={}
    for i,(key,menu) in enumerate(sorted(fixture.menus.items())):
        values=[0 if i%2 and len(menu)>1 else 1]*len(menu)
        values[i%len(menu)]=(1<<52)-sum(values)+values[i%len(menu)]
        result[key]=tuple(values)
    return result


def replay_case(archive,name,source):
    # Authenticate the full archived producer closure before any oracle import.
    authenticate_oracle(source)
    from scripts.matrix_free_certificate_budget import Budget
    from tests.virtual_dyadic_training_reference import Fixture,D
    result=decode_json(archive.read('formal/'+name+'/result.json'))
    require(result['source']==source and result['all_rows_exact'] is True,'saved experiment/source mismatch')
    require(name==result['profile']+'-'+result['law'] and result['law'] in ('uniform','river_weighted'),
            'saved case identity')
    require(result['rows']==24420 and result['action_slots']==58164 and result['proposals']==2520 and
            result['positive_board_evaluations']==60 and result['zero_full_target_boards']==2460 and
            result['native_calls']==0 and result['training_iterations']==0 and result['quality_gate'] is None,
            'saved experiment scope')
    budget=Budget()
    operations=9*62340+4*66300+5*58164+3*60
    budget.charge('literal_reference_reserved',200_000_000+operations)
    budget.entries(3_700_000,'literal reference and policy reservation')
    budget.created_bits=2_000_000_000+10_000*operations
    require(budget.created_bits<=budget.limits['created_bits'],'literal reference bit reservation')
    budget.max_forecast_bits=4096
    fixture=Fixture();policy=expected_policy(fixture,result['profile'])
    encoded=archive.read('formal/'+name+'/rows.jsonl.gz')
    require(sha256(encoded).hexdigest()==result['rows_sha256'],'saved row transport drift')
    rows={};count=slots=total=0;ordered=iter(sorted(fixture.menus))
    digest=sha256(b'opl-frozen-q52-grid-v1\n')
    with gzip.GzipFile(fileobj=io.BytesIO(encoded)) as stream:
        while True:
            line=stream.readline(32769)
            if not line:break
            require(len(line)<=32768 and line.endswith(b'\n'),'saved row line bound')
            total+=len(line);require(total<=MAX_ROWS_BYTES,'saved row total bound')
            row=decode_json(line,32768);k=row['key']
            require(type(k) is list and len(k)==3 and type(k[0]) is int and type(k[1]) is int and
                    type(k[2]) is list and all(type(t) is str for t in k[2]),'saved row key grammar')
            key=k[0],k[1],tuple(k[2]);require(key==next(ordered,None),'saved row inventory/order')
            menu=fixture.menus[key];units=row['units']
            require(type(units) is list and all(type(u) is int for u in units) and
                    units==list(policy[key]) and row['actions']==list(menu),'saved policy/menu mismatch')
            budget.entries(32+12*len(menu)+len(key[2]),'saved decoded row')
            vectors=[]
            for field in ('actual_regret','expected_regret','actual_average','expected_average'):
                require(type(row[field]) is list and len(row[field])==len(menu),'saved vector width')
                vectors.append(tuple(rational(v,budget) for v in row[field]))
            rows[key]=vectors
            payload=[key[0],key[1],key[2],menu,tuple(units)]
            digest.update(json.dumps(payload,separators=(',',':'),ensure_ascii=True).encode()+b'\n')
            count+=1;slots+=len(menu)
    require(next(ordered,None) is None and count==24420 and slots==58164 and total==result['uncompressed_bytes'],
            'saved final census')
    require(digest.hexdigest()==result['grid_sha256'],'saved snapshot hash mismatch')
    # Positive translation avoids clipping without executing candidate code.
    require(len(fixture.worlds)==60 and sum(w.mass for w in fixture.worlds)==1 and
            all(w.mass>0 for w in fixture.worlds) and all(0<=v<=8 for v in fixture.stakes.values()),
            'literal translation preconditions')
    bias=16*D
    prior={k:(bias,)*len(v) for k,v in fixture.menus.items()}
    empty={k:(0,)*len(v) for k,v in fixture.menus.items()}
    regrets,averages,root=fixture.sweep(policy,prior,empty)
    for key,vectors in rows.items():
        for fields,target in ((vectors[:2],tuple(Fraction(v-bias,D) for v in regrets[key])),
                              (vectors[2:],tuple(Fraction(v,D) for v in averages[key]))):
            for values in fields:
                for actual,expected in zip(values,target):
                    require(budget.compare(actual,expected,'saved independent update')==0,'saved raw update mismatch')
    require(rational(result['expected_root'],budget)==rational(result['actual_root'],budget)==root,'saved root mismatch')
    return {'case':name,'rows':count,'action_slots':slots,'grid_sha256':digest.hexdigest(),
            'resource_accounting':budget.receipt(),'candidate_calls':0,'native_calls':0,'exact':True}


def replay(packet=PACKET):
    require(packet.resolve()==PACKET.resolve(),'only the pinned repository evidence packet is supported')
    paths=[*ORACLE_SOURCES,Path(__file__).relative_to(ROOT).as_posix(),
           (PACKET/'manifest.json').relative_to(ROOT).as_posix(),(PACKET/'verification.zip').relative_to(ROOT).as_posix()]
    require(not git('status','--porcelain','--untracked-files=all','--',*paths),'commit replay inputs before verification')
    own_hash=sha256(Path(__file__).read_bytes()).hexdigest()
    manifest_path=packet/'manifest.json';archive_path=packet/'verification.zip'
    require(manifest_path.stat().st_size<=MAX_JSON and archive_path.stat().st_size<=16<<20,'packet byte ceiling')
    manifest=decode_json(manifest_path.read_bytes())
    require(sha256(archive_path.read_bytes()).hexdigest()==ARCHIVE_SHA==manifest['archive']['sha256'],'pinned archive drift')
    with zipfile.ZipFile(archive_path) as archive:
        names=archive.namelist()
        require(len(names)==len(set(names))==manifest['archive']['members']<=1100 and
                sum(i.file_size for i in archive.infolist())<=64<<20,'archive expansion/member bound')
        require(set(names)==set(manifest['archive']['member_sha256']),'archive inventory drift')
        for name in names:
            require(sha256(archive.read(name)).hexdigest()==manifest['archive']['member_sha256'][name],
                    'archive member drift')
        first=decode_json(archive.read('formal/uniform-uniform/result.json'));source=first['source']
        require(source['head']==FROZEN_HEAD and len(source['files'])==998,'historical source identity')
        blobs={}
        for line in git('ls-tree','-r',FROZEN_HEAD).splitlines():
            header,name=line.split('\t',1)
            if name.endswith(('.py','.cpp','.hpp','.h')):blobs[name]=header.split()[2]
        require(blobs==source['committed_blobs'],'historical committed closure drift')
        for name,digest in source['files'].items():
            require(sha256(archive.read('source/'+name)).hexdigest()==digest,'archived producer source drift')
        before=authenticate_oracle(source)
        results=[replay_case(archive,name,source) for name in ('uniform-uniform','uniform-river_weighted',
                                                              'zero-skew-uniform','zero-skew-river_weighted')]
        require(authenticate_oracle(source)==before and sha256(Path(__file__).read_bytes()).hexdigest()==own_hash and
                sha256(archive_path.read_bytes()).hexdigest()==ARCHIVE_SHA,
                'replay source changed during verification')
    return {'source_head':FROZEN_HEAD,'current_head':git('rev-parse','HEAD'),'replayer_sha256':own_hash,
            'python_version':sys.version,'python_executable_sha256':sha256(Path(sys.executable).read_bytes()).hexdigest(),
            'archived_sources_authenticated':998,'current_oracle_sources_authenticated':len(before),
            'archived_code_executed':False,'results':results}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.parse_args()
    print(json.dumps(replay(),indent=2))
