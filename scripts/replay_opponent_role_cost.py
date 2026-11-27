"""Authenticate original cost observations and recompute their scoped gate."""
import argparse
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import statistics
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
PACKET=ROOT/'benchmarks/results/opponent-role-cost-v1'
PIN=(1457,'b4499d504aa13a609849b857b9f5a3b4b8673dceb7d69e2625040b5123f4e1bb')
FIRST='1bf063f33d1cffc0ee20f98685f71c83b8ff7634'
ORIGIN='5606fdd0f3ed7eb3aab986df1fcc9286b907ad92'


def replay(packet=PACKET):
    from scripts import replay_joint_cycles_packet as base,joint_evidence_archive as archive
    from scripts import replay_joint_two_epoch_packet as helper,replay_single_pass_packet as known,replay_opponent_role_walk as role
    need=base.need;digest=lambda b:sha256(b).hexdigest()
    def bootstrap():
        prior=base.bootstrap();names=('scripts/replay_opponent_role_cost.py','scripts/replay_opponent_role_walk.py')
        need(not base.git('status','--porcelain','--untracked-files=all','--',*names),'role cost committed bootstrap')
        result={}
        for name in names:
            raw=archive.read(ROOT/name);need(digest(raw) in base.variants(base.git('show',prior[0]+':'+name)),
                'role cost bootstrap raw identity');result[name]=digest(raw)
        return prior,result
    before=bootstrap();need(not any(n=='tests' or n.startswith(('tests.','pokerlab')) for n in sys.modules),'role cost fresh math process')
    def load():return archive.load(packet,helper,pin=PIN,version='opponent-role-cost',
        labels=('observations','builds','objects'),packager='package_opponent_role_cost1.py.txt')
    manifest,loaded,pins=load();files=loaded['observations'];buildfiles=loaded['builds']
    objects=helper.GitObjects();source_maps={}
    for version in (1,2,3):
        prefix='cost-'+str(version);record=helper.decode(files[prefix+'/source-identity.json']);head=ORIGIN if version==3 else FIRST
        hashes=record['raw_sha256'];blobs=record['committed_blobs'];source={}
        need(record['head']==head and len(hashes)==91 and set(hashes)==set(blobs) and
             {n[len(prefix+'/source/'):] for n in files if n.startswith(prefix+'/source/')}==set(hashes),'role cost complete source inventory')
        for name,expected in hashes.items():
            raw=files[prefix+'/source/'+helper.safe_name(name)];blob=objects.tree(head).get(name)
            need(digest(raw)==expected and blobs[name]==blob and
                 (helper.source_bytes_match(raw,objects.body(head,name),name,blob) or
                  known.HISTORICAL_CHECKOUTS.get(name)==(expected,blob)), 'role cost original raw/Git source closure')
            source[name]=raw
        source_maps[prefix]=source
        need(files[f'logs/opponent-role-walk-cost{version}.exit'].strip()==(b'0' if version==3 else b'1'),
             'role cost original outer process outcome')
    need(b'exact-reach source/build drift: native/virtual_joint_sample_raw.hpp' in files['logs/opponent-role-walk-cost1.stderr'] and
         b'role cost unchanged optimization/warning flags and declared baseline macro' in files['logs/opponent-role-walk-cost2.stderr'],
         'role cost both original pre-observation refusals')
    builds={}
    for mode,target in (('baseline','virtual-weighted-joint-single-pass'),('candidate','opponent-role-four-street')):
        raw=files['cost-3/'+mode+'-build.json'];build=helper.decode(raw)
        need(raw==buildfiles[mode+'/native-exact-build-manifest.json'] and build['target']==target and
             build['contract']=='native-exact-build-v1','role cost original build identity')
        helper.build_source_links(build,source_maps['cost-3']);builds[mode]=(raw,build)
    need(builds['baseline'][1]['compiler_sha256']==builds['candidate'][1]['compiler_sha256'] and
         builds['baseline'][1]['dependency_archive_sha256']==builds['candidate'][1]['dependency_archive_sha256'],
         'role cost matching compiler and integer dependency')
    def flags(record):return ['<owned-boost-include>' if x.startswith(('/I','-I')) else x for x in record['flags']]
    trial=flags(builds['candidate'][1]);need(flags(builds['baseline'][1]) in (
        [*trial,'/DOPENPOKER_WEIGHTED_JOINT_TWO_EPOCH','/DOPENPOKER_JOINT_SINGLE_PASS'],
        [*trial,'-DOPENPOKER_WEIGHTED_JOINT_TWO_EPOCH','-DOPENPOKER_JOINT_SINGLE_PASS']), 'role cost exact target macro/flags contract')
    protocol=helper.decode(files['cost-3/protocol.json']);cases=(('same-world',((0,0),(0,0)),'first'),
        ('sb-loss',((4,0),(4,0)),'alternating'),('sb-win',((1966603,0),(1966603,0)),'middle'),
        ('shared-board-distinct-holding',((0,2140425),(4,2140425)),'alternating'))
    need(protocol['source_head']==ORIGIN and protocol['profile']==1 and protocol['cases']==helper.decode(json.dumps(cases).encode()) and
         protocol['blocks']==8 and protocol['calls_per_mode_per_block']==8 and protocol['warmup_native_calls']==8 and
         protocol['timed_native_calls']==128 and protocol['automatic_retries']==0 and protocol['median_ratio_limit']==0.95 and
         protocol['minimum_faster_pairs']==6,'role cost frozen physical/ticket/performance contract')
    processes,_=helper.process_receipts(files);expected=set();wires={};observations={}
    for mode in ('baseline','candidate'):
        for index in range(4):wires[mode,index]=files[f'cost-3/warmup-{mode}-{index}/stdout.bin']
    def observation(label,mode,index):
        prefix='cost-3/'+label;expected.add(prefix);receipt=helper.decode(files[prefix+'/process.json'])
        inv=helper.decode(files['cost-3/'+label+'-invocation.json']);raw,build=builds[mode];command=inv['command']
        need(inv['source_head']==ORIGIN and inv['mode']==mode and inv['case_index']==index and inv['stdin_bytes']==0 and
             inv['automatic_retries']==0 and inv['executable_sha256']==build['executable_sha256'] and
             inv['build_manifest_sha256']==digest(raw) and command[0]==build['executable'], 'role cost exact invocation/executable link')
        if mode=='candidate':need(len(command)==2 and command[1].replace('\\','/').endswith('/request-'+cases[index][0]+'.bin'),
            'role cost exact supplied request file')
        else:need(command[1:]==list(map(str,(1,*[v for pair in cases[index][1] for v in pair]))),'role cost exact baseline selectors')
        need(prefix in processes and processes[prefix]['exit']==0 and files[prefix+'/request.bin']==b'' and
             files[prefix+'/stderr.bin']==b'' and files[prefix+'/stdout.bin']==wires[mode,index] and
             type(receipt['duration_seconds']) in (int,float) and isfinite(receipt['duration_seconds']) and receipt['duration_seconds']>0,
             'role cost original successful bounded process/full wire/duration')
        result={'label':label,'mode':mode,'case_index':index,'duration_seconds':receipt['duration_seconds'],
            'stdout_sha256':digest(wires[mode,index]),'wire_bytes':len(wires[mode,index])};observations[label]=result;return result
    warmups=[observation(f'warmup-{mode}-{i}',mode,i) for mode in ('baseline','candidate') for i in range(4)]
    need(helper.decode(files['cost-3/warmups.json'])==warmups,'role cost all original warmups retained')
    ratios=[]
    for block in range(8):
        order=['baseline','candidate'] if block%2==0 else ['candidate','baseline'];record={'block':block,'order':order}
        for mode in order:record[mode]=[observation(f'block-{block}-{mode}-{i}',mode,(8*block+i)%4) for i in range(8)]
        ratio=sum(x['duration_seconds'] for x in record['candidate'])/sum(x['duration_seconds'] for x in record['baseline'])
        record['elapsed_ratio']=ratio;ratios.append(ratio)
        need(helper.decode(files[f'cost-3/block-{block}.json'])==record,'role cost original block/process reduction')
    need(set(processes)==expected and len(processes)==136,'role cost exact original process inventory')
    report=helper.decode(files['cost-3/result.json']);median=statistics.median(ratios);faster=sum(x<1 for x in ratios)
    need(report['paired_elapsed_ratios']==ratios and report['median_candidate_baseline_ratio']==median and report['candidate_faster_pairs']==faster and
         report['cost_gate_pass']==(median<=0.95 and faster>=6) and report['native_calls']==136 and report['source_head']==ORIGIN and
         report['equal_quality_speedup_admitted'] is False and report['quality_gate'] is None and report['rng_calls']==0,
         'role cost freshly reduced scoped result')
    def current_math():
        names=[n for n in source_maps['cost-3'] if n.endswith('.py')]
        need(not (ROOT/'tests/__init__.py').exists() and not (ROOT/'scripts/__init__.py').exists() and
             not base.git('status','--porcelain','--untracked-files=all','--',*names),'role cost current reference source clean')
        result={}
        for name in names:
            raw=archive.read(ROOT/name);need(digest(raw) in base.variants(objects.body(ORIGIN,name)),
                'role cost current complete reference closure drift');result[name]=digest(raw)
        return result
    math_before=current_math();previous=sys.pycache_prefix,sys.dont_write_bytecode
    with TemporaryDirectory(prefix='role-cost-replay-cache-',dir=ROOT.parent) as cache:
        sys.pycache_prefix=cache;sys.dont_write_bytecode=True
        try:
            from tests.virtual_native_single_pass_reference import verify as full
            from tests.virtual_role_walk_wire_reference import verify as sampled
            fresh=[]
            for index,(label,selectors,rule) in enumerate(cases):
                a=full(1,selectors,wires['baseline',index]);b=sampled(wires['candidate',index],files['cost-3/request-'+label+'.bin'],1,selectors,rule)
                need(helper.decode(json.dumps(a).encode())==helper.decode(files['cost-3/baseline-reference-'+label+'.json']) and
                     helper.decode(json.dumps(b).encode())==helper.decode(files['cost-3/candidate-reference-'+label+'.json']),
                     'role cost independent per-estimator full numeric replay')
                fresh.append({'case':label,'baseline_wire_sha256':digest(wires['baseline',index]),
                    'candidate_wire_sha256':digest(wires['candidate',index]),'candidate_numeric_coordinates':b['all_numeric_coordinates']})
            need(bootstrap()==before and current_math()==math_before and load()[2]==pins,'role cost final source/packet drift')
            return {'status':'role-walk-complete-call-cost-replayed','original_native_processes':136,'pre_observation_refusals':2,
                'paired_elapsed_ratios':ratios,'median_candidate_baseline_ratio':median,'candidate_faster_pairs':faster,
                'cost_gate_pass':median<=0.95 and faster>=6,'ratio_range':[min(ratios),max(ratios)],'fresh':fresh,
                'native_calls':0,'archived_source_executed':False,'equal_quality_speedup_admitted':False,'quality_gate':None,
                'stored_expanded_bytes':manifest['stored_expanded_bytes'],
                'scope':'Different deterministic T2 estimators and transport sizes; one uncontrolled-load host. Gate passes its frozen rule; high dispersion does not establish stable throughput or equal-quality solving speed.'}
        finally:sys.pycache_prefix,sys.dont_write_bytecode=previous


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('packet',nargs='?',type=Path,default=PACKET)
    print(json.dumps(replay(p.parse_args().packet),indent=2))
