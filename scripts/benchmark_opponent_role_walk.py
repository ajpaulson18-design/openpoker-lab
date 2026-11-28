"""Frozen complete-call cost study; distinct estimators, no equal-quality claim."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import statistics
from scripts.run_opponent_action_study import ROOT,closure,git,need
from scripts.build_frozen_role_walk import register,TARGET,SOURCES

BLOCKS=8
CALLS=8
CASES=(('same-world',((0,0),(0,0)),'first'),('sb-loss',((4,0),(4,0)),'alternating'),
    ('sb-win',((1966603,0),(1966603,0)),'middle'),
    ('shared-board-distinct-holding',((0,2140425),(4,2140425)),'alternating'))


def benchmark(baseline,candidate,output):
    register();baseline=Path(baseline).resolve();candidate=Path(candidate).resolve();output=Path(output).resolve()
    need(output.parent==ROOT.parent.resolve() and not output.exists(),'role cost fresh external evidence')
    from scripts.build_native_exact_four_street import TARGETS
    names=closure(('scripts/benchmark_opponent_role_walk.py','scripts/replay_opponent_role_walk.py',
        'tests/virtual_native_single_pass_reference.py','tests/virtual_role_walk_wire_reference.py',
        'tests/test_native_exact_reach.py','tests/virtual_frozen_run_control.py'))
    for name in (*SOURCES[TARGET],*TARGETS['virtual-weighted-joint-single-pass'][1],
        'third_party/boost-multiprecision-1.92.0/manifest.json','third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt',
        'third_party/boost-multiprecision-1.92.0/headers.zip'):names[name]=(ROOT/name).read_bytes()
    need(not git('status','--porcelain','--untracked-files=all','--',*names),'role cost complete source committed')
    head=git('rev-parse','HEAD').decode().strip()
    tree={line.split('\t',1)[1]:line.split('\t',1)[0].split()[2] for line in git('ls-tree','-r',head).decode().splitlines()}
    output.mkdir()
    def write(name,value):
        with (output/name).open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    for name,body in names.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
    write('source-identity.json',{'head':head,'raw_sha256':{n:sha256(b).hexdigest() for n,b in names.items()},
        'committed_blobs':{n:tree[n] for n in names}})
    write('protocol.json',{'source_head':head,'profile':1,'cases':CASES,'blocks':BLOCKS,'calls_per_mode_per_block':CALLS,
        'case_schedule':'(8*block+call)%4, identical cases in both modes; each case warmed once per mode',
        'order':'baseline then candidate on even blocks; candidate then baseline on odd blocks',
        'warmup_native_calls':8,'timed_native_calls':128,'automatic_retries':0,'median_ratio_limit':0.95,'minimum_faster_pairs':6,
        'scope':'One host; complete process including startup, preparation, two research updates, private output and transport. Same physical selector schedule, different deterministic/full estimators and retained states. No numerical parity between estimators, equal-quality, convergence, RNG, longer lifetime or universal speed claim.'})
    # Full source and fixed performance contract are durable before numerical imports.
    from tests.test_native_exact_reach import authenticate,sha
    from tests.virtual_frozen_run_control import run_bounded_child
    from tests.virtual_native_single_pass_reference import verify as verify_baseline
    from tests.virtual_role_walk_wire_reference import verify as verify_candidate
    from scripts import replay_opponent_role_walk as saved,joint_evidence_archive as archive,replay_joint_two_epoch_packet as helper
    packet,loaded,pins=archive.load(saved.PACKET,helper,pin=saved.PIN,version='opponent-role-walk',
        labels=('observations','builds','objects'),packager='package_opponent_role_walk1.py.txt')
    paths={'baseline':baseline,'candidate':candidate};targets={'baseline':'virtual-weighted-joint-single-pass','candidate':TARGET}
    identities={mode:authenticate(path,ROOT,targets[mode]) for mode,path in paths.items()}
    need(identities['baseline'][1]['compiler_sha256']==identities['candidate'][1]['compiler_sha256'] and
         identities['baseline'][1]['dependency_archive_sha256']==identities['candidate'][1]['dependency_archive_sha256'],
         'role cost same compiler and integer dependency')
    def flags(record):return ['<owned-boost-include>' if x.startswith(('/I','-I')) else x for x in record['flags']]
    baseflags=flags(identities['baseline'][1]);trialflags=flags(identities['candidate'][1])
    need(baseflags in ([*trialflags,'/DOPENPOKER_WEIGHTED_JOINT_TWO_EPOCH','/DOPENPOKER_JOINT_SINGLE_PASS'],
                       [*trialflags,'-DOPENPOKER_WEIGHTED_JOINT_TWO_EPOCH','-DOPENPOKER_JOINT_SINGLE_PASS']),
         'role cost unchanged optimization/warning flags and exact weighted/single-pass baseline target macros')
    for mode,identity in identities.items():(output/(mode+'-build.json')).write_bytes(identity[0])
    expected={'baseline':[],'candidate':[]};requests=[]
    for label,selectors,rule in CASES:
        prefix='matrix/normal/profile-1-'+label
        request=loaded['observations'][prefix+'/request.bin'];path=output/('request-'+label+'.bin');path.write_bytes(request);requests.append(path)
        raw=loaded['observations'][prefix+'/native/stdout.bin'];expected['candidate'].append(raw)
        report=verify_candidate(raw,request,1,selectors,rule);write('candidate-reference-'+label+'.json',report)
    def invoke(mode,label,index):
        command=[str(paths[mode])]
        if mode=='candidate':command.append(str(requests[index]))
        else:command.extend(map(str,(1,*[x for pair in CASES[index][1] for x in pair])))
        invocation={'command':command,'executable_sha256':sha(paths[mode]),'build_manifest_sha256':sha256(identities[mode][0]).hexdigest(),
            'stdin_bytes':0,'source_head':head,'automatic_retries':0,'case_index':index,'mode':mode}
        write(label+'-invocation.json',invocation)
        receipt=run_bounded_child(command,b'',output/label,stdout_limit=549280,stderr_limit=4096,timeout=180)
        raw=(output/label/'stdout.bin').read_bytes()
        need((receipt['status'],receipt['actual_exit_observed'],receipt['returncode'],receipt['failures'])==('exited',True,0,[]) and
             not (output/label/'stderr.bin').read_bytes() and authenticate(paths[mode],ROOT,targets[mode])==identities[mode],
             'role cost original exit/source/build identity')
        if mode=='baseline' and len(expected[mode])<=index:
            report=verify_baseline(1,CASES[index][1],raw);write('baseline-reference-'+CASES[index][0]+'.json',report)
            expected[mode].append(raw)
        need(raw==expected[mode][index],'role cost exact per-estimator full wire')
        return {'label':label,'mode':mode,'case_index':index,'duration_seconds':receipt['duration_seconds'],
            'stdout_sha256':sha256(raw).hexdigest(),'wire_bytes':len(raw)}
    warmups=[invoke(mode,'warmup-'+mode+'-'+str(i),i) for mode in ('baseline','candidate') for i in range(4)]
    write('warmups.json',warmups);blocks=[]
    for block in range(BLOCKS):
        order=('baseline','candidate') if block%2==0 else ('candidate','baseline');record={'block':block,'order':order}
        for mode in order:record[mode]=[invoke(mode,f'block-{block}-{mode}-{i}',(CALLS*block+i)%4) for i in range(CALLS)]
        record['elapsed_ratio']=sum(x['duration_seconds'] for x in record['candidate'])/sum(x['duration_seconds'] for x in record['baseline'])
        blocks.append(record);write('block-'+str(block)+'.json',record)
        print(json.dumps({'block':block,'elapsed_ratio':record['elapsed_ratio']}),flush=True)
    need(git('rev-parse','HEAD').decode().strip()==head and all((ROOT/n).read_bytes()==b for n,b in names.items()) and
         all(authenticate(paths[mode],ROOT,targets[mode])==identity for mode,identity in identities.items()), 'role cost original final source drift')
    ratios=[b['elapsed_ratio'] for b in blocks];median=statistics.median(ratios);faster=sum(x<1 for x in ratios)
    result={'status':'role-walk-complete-call-cost-observed','native_calls':136,'paired_elapsed_ratios':ratios,
        'median_candidate_baseline_ratio':median,'candidate_faster_pairs':faster,'cost_gate_pass':median<=0.95 and faster>=6,
        'same_physical_schedule':True,'per_estimator_full_wire_identity':True,'equal_quality_speedup_admitted':False,
        'quality_gate':None,'rng_calls':0,'source_head':head,'source_files':len(names),'original_packet_pin':saved.PIN,
        'scope':'Defined deterministic T2 role/full requests only, including distinct raw/state output sizes. Host load uncontrolled. No shared numerical output, equal-quality or realistic NLHE speed claim.'}
    write('result.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('baseline',type=Path);p.add_argument('candidate',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();print(json.dumps(benchmark(a.baseline,a.candidate,a.output),indent=2))
