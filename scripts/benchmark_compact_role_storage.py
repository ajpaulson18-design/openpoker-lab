"""Predeclared whole-call non-regression test for same-policy compact storage."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import statistics
from scripts.run_opponent_action_study import ROOT,closure,git,need
from scripts.build_compact_role_storage import register,SOURCES,CANONICAL,COMPACT

LABELS=('profile-1-same-world','profile-1-sb-loss','profile-1-sb-win','profile-1-shared-board-distinct-holding')
BLOCKS=8
CALLS=16


def benchmark(canonical,compact,output):
    register();paths={CANONICAL:Path(canonical).resolve(),COMPACT:Path(compact).resolve()};output=Path(output).resolve()
    need(output.parent==ROOT.parent.resolve() and not output.exists(),'compact cost fresh external output')
    names=closure(('scripts/benchmark_compact_role_storage.py','scripts/replay_compact_role_storage.py',
        'tests/test_native_exact_reach.py','tests/virtual_frozen_run_control.py'))
    for name in (*SOURCES[CANONICAL],*SOURCES[COMPACT],'third_party/boost-multiprecision-1.92.0/manifest.json',
        'third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt','third_party/boost-multiprecision-1.92.0/headers.zip'):
        names[name]=(ROOT/name).read_bytes()
    need(not git('status','--porcelain','--untracked-files=all','--',*names),'compact cost complete source committed')
    head=git('rev-parse','HEAD').decode().strip();tree={line.split('\t',1)[1]:line.split('\t',1)[0].split()[2] for line in git('ls-tree','-r',head).decode().splitlines()}
    output.mkdir()
    def write(name,value):
        with (output/name).open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    for name,body in names.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
    write('source-identity.json',{'head':head,'raw_sha256':{n:sha256(b).hexdigest() for n,b in names.items()},'committed_blobs':{n:tree[n] for n in names}})
    write('protocol.json',{'source_head':head,'profile':1,'case_labels':LABELS,'blocks':BLOCKS,'calls_per_mode_per_block':CALLS,
        'warmups_per_mode':2,'warmup_schedule':[0,1],'timed_native_calls':256,'total_native_calls':260,
        'case_schedule':'(16*block+call)%4, identical in both modes; alternating canonical/compact order by block parity',
        'median_candidate_baseline_limit':1.05,'maximum_pairs_above_1_10':2,'automatic_retries':0,
        'scope':'Same exact T2 policies and canonical payload sizes with both storage observers enabled. Complete startup/preparation/updates/export/transport included; compact canonical expansion remains billed. One uncontrolled-load host; no allocator/RSS, stable throughput, longer learning or quality claim.'})
    # The contract and complete source are durable before independent replay,
    # warmups or any timing observation. No timing gate is selected afterward.
    from scripts import replay_compact_role_storage as saved,joint_evidence_archive as archive,replay_joint_two_epoch_packet as helper
    independent=saved.replay();write('independent-storage-replay.json',independent)
    _manifest,loaded,pins=archive.load(saved.PACKET,helper,pin=saved.PIN,version='compact-role-storage',
        labels=('observations','builds','objects'),packager='package_compact_role_storage1.py.txt')
    from tests.test_native_exact_reach import authenticate,sha
    from tests.virtual_frozen_run_control import run_bounded_child
    identities={target:authenticate(path,ROOT,target) for target,path in paths.items()}
    a,b=identities[CANONICAL][1],identities[COMPACT][1]
    def flags(record):return ['<owned-boost-include>' if x.startswith(('/I','-I')) else x for x in record['flags']]
    need(a['compiler_sha256']==b['compiler_sha256'] and a['dependency_archive_sha256']==b['dependency_archive_sha256'] and flags(a)==flags(b),
         'compact cost same compiler/dependency/optimization/warning flags')
    common_a={n:v for n,v in a['source_sha256'].items() if n!='tests/native/virtual_opponent_role_storage_probe.cpp'}
    common_b={n:v for n,v in b['source_sha256'].items() if n!='tests/native/virtual_opponent_role_compact_probe.cpp'}
    need(common_a==common_b,'compact cost identical common native source closure')
    for target,identity in identities.items():(output/(target+'-build.json')).write_bytes(identity[0])
    requests=[];expected={CANONICAL:[],COMPACT:[]};observed_storage=[]
    for label in LABELS:
        prefix='matrix/normal/'+label;request=loaded['observations'][prefix+'/request.bin'];path=output/(label+'-request.bin');path.write_bytes(request);requests.append(path)
        record=helper.decode(loaded['observations'][prefix+'/result.json'])
        for target,name in ((CANONICAL,'canonical'),(COMPACT,'compact')):expected[target].append(loaded['observations'][prefix+'/'+name+'/stdout.bin'])
        need(len(expected[CANONICAL][-1])==len(expected[COMPACT][-1]),'compact cost identical per-case canonical wire sizes')
        observed_storage.append({'case':label,'canonical':record['reports']['canonical']['storage'],'compact':record['reports']['compact']['storage']})
    write('independent-expected.json',{'packet_pin':saved.PIN,'labels':LABELS,
        'wire_sha256':{target:[sha256(raw).hexdigest() for raw in images] for target,images in expected.items()},'original_storage_observations':observed_storage})
    def invoke(target,label,index):
        invocation={'command':[str(paths[target]),str(requests[index])],'executable_sha256':sha(paths[target]),
            'build_manifest_sha256':sha256(identities[target][0]).hexdigest(),'stdin_bytes':0,'automatic_retries':0,
            'source_head':head,'case_index':index,'target':target};write(label+'-invocation.json',invocation)
        receipt=run_bounded_child(invocation['command'],b'',output/label,stdout_limit=549280,stderr_limit=4096,timeout=180)
        raw=(output/label/'stdout.bin').read_bytes()
        need((receipt['status'],receipt['actual_exit_observed'],receipt['returncode'],receipt['failures'])==('exited',True,0,[]) and
             not (output/label/'stderr.bin').read_bytes() and raw==expected[target][index] and authenticate(paths[target],ROOT,target)==identities[target],
             'compact cost actual original exit and exact full per-mode wire identity')
        return {'label':label,'target':target,'case_index':index,'duration_seconds':receipt['duration_seconds'],
            'stdout_sha256':sha256(raw).hexdigest(),'wire_bytes':len(raw)}
    warmups=[invoke(target,f'warmup-{target}-{i}',i) for target in (CANONICAL,COMPACT) for i in range(2)]
    write('warmups.json',warmups);blocks=[]
    for block in range(BLOCKS):
        order=(CANONICAL,COMPACT) if block%2==0 else (COMPACT,CANONICAL);record={'block':block,'order':order}
        for target in order:record[target]=[invoke(target,f'block-{block}-{target}-{i}',(CALLS*block+i)%4) for i in range(CALLS)]
        record['elapsed_ratio']=sum(x['duration_seconds'] for x in record[COMPACT])/sum(x['duration_seconds'] for x in record[CANONICAL])
        blocks.append(record);write('block-'+str(block)+'.json',record);print(json.dumps({'block':block,'elapsed_ratio':record['elapsed_ratio']}),flush=True)
    need(git('rev-parse','HEAD').decode().strip()==head and all((ROOT/n).read_bytes()==body for n,body in names.items()) and
         all(authenticate(paths[target],ROOT,target)==identity for target,identity in identities.items()),'compact cost original final source/executable drift')
    ratios=[x['elapsed_ratio'] for x in blocks];median=statistics.median(ratios);slow=sum(x>1.10 for x in ratios)
    result={'status':'same-policy-compact-storage-whole-call-observed','source_head':head,'source_files':len(names),'native_calls':260,
        'paired_elapsed_ratios':ratios,'median_compact_canonical_ratio':median,'pairs_above_1_10':slow,
        'whole_call_nonregression_gate_pass':median<=1.05 and slow<=2,'same_exact_numeric_policies':True,'same_wire_sizes':True,
        'every_native_full_wire_matches_independent_evidence':True,'archived_source_executed':False,'rng_calls':0,
        'quality_gate':None,'supported_native_epochs':2,
        'scope':'Same policies, startup/preparation/T2 updates, both storage observers and canonical export/transport. Every pair retained on one uncontrolled-load host; no allocator/RSS, stable throughput, longer lifetime or quality claim.'}
    write('result.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('canonical',type=Path);p.add_argument('compact',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();print(json.dumps(benchmark(a.canonical,a.compact,a.output),indent=2))
