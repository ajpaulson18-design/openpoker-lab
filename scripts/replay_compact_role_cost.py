"""Authenticate and independently reduce every same-policy storage timing pair."""
import argparse
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
PACKET=ROOT/'benchmarks/results/compact-role-storage-cost-v1'
PIN=(1492,'3f5f5dc489fc11b2800a725e1828731f07c56f03db70ca579c41529e559ff9a6')
ORIGIN='7f37234c1a38ff1309e4bcbda15477b8f9478a08'
BUILD='4915735b8850d64ad04411bc66ff71fdb211d612'
CANONICAL='role-storage-canonical'
COMPACT='role-storage-compact'
LABELS=('profile-1-same-world','profile-1-sb-loss','profile-1-sb-win','profile-1-shared-board-distinct-holding')


def replay(packet=PACKET):
    from scripts import replay_joint_cycles_packet as base,joint_evidence_archive as archive
    from scripts import replay_joint_two_epoch_packet as helper,replay_single_pass_packet as known,replay_compact_role_storage as storage
    need=base.need;digest=lambda b:sha256(b).hexdigest()
    def bootstrap():
        prior=base.bootstrap();names=('scripts/replay_compact_role_cost.py','scripts/replay_compact_role_storage.py')
        need(not base.git('status','--porcelain','--untracked-files=all','--',*names),'compact cost committed bootstrap')
        result={}
        for name in names:
            raw=archive.read(ROOT/name);need(digest(raw) in base.variants(base.git('show',prior[0]+':'+name)),
                'compact cost bootstrap raw source');result[name]=digest(raw)
        return prior,result
    before=bootstrap();need(not any(n=='tests' or n.startswith(('tests.','pokerlab')) for n in sys.modules),'compact cost fresh math process')
    def load():return archive.load(packet,helper,pin=PIN,version='compact-role-cost',labels=('observations','builds','objects'),
        packager='package_compact_role_cost1.py.txt')
    manifest,loaded,pins=load();files=loaded['observations'];buildfiles=loaded['builds']
    class Objects(helper.GitObjects):
        def __init__(self):super().__init__();self.blobs={}
        def body(self,head,name):
            blob=self.tree(head).get(name);need(blob is not None,'compact cost original Git blob')
            if blob not in self.blobs:self.blobs[blob]=super().body(head,name)
            return self.blobs[blob]
    objects=Objects();source_maps={}
    def sources(members,prefix,head,count):
        record=helper.decode(members[prefix+'/source-identity.json']);hashes=record['raw_sha256'];source={}
        need(record['head']==head and len(hashes)==count and set(hashes)==set(record['committed_blobs']) and
             {n[len(prefix+'/source/'):] for n in members if n.startswith(prefix+'/source/')}==set(hashes),
             'compact cost complete introduced source inventory')
        for name,expected in hashes.items():
            raw=members[prefix+'/source/'+helper.safe_name(name)];blob=objects.tree(head).get(name)
            need(digest(raw)==expected and record['committed_blobs'][name]==blob and
                 (helper.source_bytes_match(raw,objects.body(head,name),name,blob) or known.HISTORICAL_CHECKOUTS.get(name)==(expected,blob)),
                 'compact cost original raw/Git source closure');source[name]=raw
        source_maps[prefix]=source;return source
    source=sources(files,'study',ORIGIN,93);sources(files,'units',ORIGIN,60);builds={}
    for target in (CANONICAL,COMPACT):
        prefix=target+'-build2';buildsource=sources(buildfiles,prefix,BUILD,35)
        raw=buildfiles[prefix+'/native-exact-build-manifest.json'];build=helper.decode(raw)
        need(build['target']==target and build['contract']=='native-exact-build-v1' and
             build['source_sha256']=={n:digest(b) for n,b in buildsource.items()} and
             files['study/'+target+'-build.json']==raw and all(source.get(n)==b for n,b in buildsource.items()),
             'compact cost original build/introduced raw-source link');builds[target]=(raw,build)
    def flags(record):return ['<owned-boost-include>' if x.startswith(('/I','-I')) else x for x in record['flags']]
    a,b=builds[CANONICAL][1],builds[COMPACT][1]
    need(a['compiler_sha256']==b['compiler_sha256'] and a['dependency_archive_sha256']==b['dependency_archive_sha256'] and flags(a)==flags(b),
         'compact cost matching compiler/dependency/flags')
    need({n:v for n,v in a['source_sha256'].items() if n!='tests/native/virtual_opponent_role_storage_probe.cpp'}==
         {n:v for n,v in b['source_sha256'].items() if n!='tests/native/virtual_opponent_role_compact_probe.cpp'},
         'compact cost exact common source closure')
    protocol=helper.decode(files['study/protocol.json'])
    need(protocol['source_head']==ORIGIN and protocol['profile']==1 and protocol['case_labels']==list(LABELS) and protocol['blocks']==8 and
         protocol['calls_per_mode_per_block']==16 and protocol['warmups_per_mode']==2 and protocol['warmup_schedule']==[0,1] and
         protocol['timed_native_calls']==256 and protocol['total_native_calls']==260 and protocol['median_candidate_baseline_limit']==1.05 and
         protocol['maximum_pairs_above_1_10']==2 and protocol['automatic_retries']==0,'compact cost frozen nonregression contract')
    need(files['logs/compact-role-storage-cost1.exit'].strip()==b'0' and files['logs/compact-role-storage-units2.exit'].strip()==b'0',
         'compact cost original outer exits')
    processes,_=helper.process_receipts(files);expected={'units/normal','units/optimized'};wires={};requests={}
    # All four authoritative wires come from an exactly pinned state packet,
    # admitted before any mathematical import or timing interpretation.
    _sm,state_files,state_pins=archive.load(storage.PACKET,helper,pin=storage.PIN,version='compact-role-storage',
        labels=('observations','builds','objects'),packager='package_compact_role_storage1.py.txt')
    expected_image=helper.decode(files['study/independent-expected.json'])
    need(expected_image['packet_pin']==list(storage.PIN) and expected_image['labels']==list(LABELS),'compact cost exact independent state input')
    expected_observations=[]
    for index,label in enumerate(LABELS):
        prefix='matrix/normal/'+label;requests[index]=state_files['observations'][prefix+'/request.bin']
        need(files['study/'+label+'-request.bin']==requests[index],'compact cost exact original supplied input')
        for target,name in ((CANONICAL,'canonical'),(COMPACT,'compact')):
            wires[target,index]=state_files['observations'][prefix+'/'+name+'/stdout.bin']
            need(expected_image['wire_sha256'][target][index]==digest(wires[target,index]),'compact cost original expected full wire')
        need(len(wires[CANONICAL,index])==len(wires[COMPACT,index]),'compact cost identical per-case wire sizes')
        record=helper.decode(state_files['observations'][prefix+'/result.json'])
        expected_observations.append({'case':label,'canonical':record['reports']['canonical']['storage'],
            'compact':record['reports']['compact']['storage']})
    need(expected_image['original_storage_observations']==expected_observations,'compact cost complete original capacity observations')
    def observe(label,target,index):
        prefix='study/'+label;expected.add(prefix);receipt=helper.decode(files[prefix+'/process.json']);inv=helper.decode(files['study/'+label+'-invocation.json'])
        raw,build=builds[target];command=inv['command']
        need(inv['source_head']==ORIGIN and inv['target']==target and inv['case_index']==index and inv['stdin_bytes']==0 and inv['automatic_retries']==0 and
             inv['executable_sha256']==build['executable_sha256'] and inv['build_manifest_sha256']==digest(raw) and
             len(command)==2 and command[0]==build['executable'] and command[1].replace('\\','/').endswith('/'+LABELS[index]+'-request.bin'),
             'compact cost complete original executable/argv identity')
        need(prefix in processes and processes[prefix]['exit']==0 and files[prefix+'/request.bin']==b'' and files[prefix+'/stderr.bin']==b'' and
             files[prefix+'/stdout.bin']==wires[target,index] and type(receipt['duration_seconds']) in (int,float) and
             isfinite(receipt['duration_seconds']) and receipt['duration_seconds']>0,'compact cost actual original exit/full wire/duration')
        return {'label':label,'target':target,'case_index':index,'duration_seconds':receipt['duration_seconds'],
            'stdout_sha256':digest(wires[target,index]),'wire_bytes':len(wires[target,index])}
    warmups=[observe(f'warmup-{target}-{i}',target,i) for target in (CANONICAL,COMPACT) for i in range(2)]
    need(helper.decode(files['study/warmups.json'])==warmups,'compact cost original complete warmups')
    ratios=[]
    for block in range(8):
        order=[CANONICAL,COMPACT] if block%2==0 else [COMPACT,CANONICAL];record={'block':block,'order':order}
        for target in order:record[target]=[observe(f'block-{block}-{target}-{i}',target,(16*block+i)%4) for i in range(16)]
        ratio=sum(x['duration_seconds'] for x in record[COMPACT])/sum(x['duration_seconds'] for x in record[CANONICAL]);record['elapsed_ratio']=ratio;ratios.append(ratio)
        need(helper.decode(files[f'study/block-{block}.json'])==record,'compact cost all original per-process pair reductions')
    need(set(processes)==expected and len(processes)==262 and all(processes['units/'+mode]['exit']==0 for mode in ('normal','optimized')),
         'compact cost exact original process universe')
    units=helper.decode(files['units/result.json'])
    need(units['source_head']==ORIGIN and units['source_files']==60 and units['test_methods_per_mode']==5 and units['native_calls']==0 and
         units['children']==[helper.decode(files['units/'+mode+'/process.json']) for mode in ('normal','optimized')],
         'compact cost original domain/package unit outcomes')
    report=helper.decode(files['study/result.json']);median=statistics.median(ratios);slow=sum(x>1.10 for x in ratios)
    need(report['paired_elapsed_ratios']==ratios and report['median_compact_canonical_ratio']==median and report['pairs_above_1_10']==slow and
         report['whole_call_nonregression_gate_pass']==(median<=1.05 and slow<=2) and report['source_head']==ORIGIN and report['source_files']==93 and
         report['native_calls']==260 and report['same_exact_numeric_policies'] is True and report['same_wire_sizes'] is True and
         report['every_native_full_wire_matches_independent_evidence'] is True and report['archived_source_executed'] is False and
         report['supported_native_epochs']==2 and report['quality_gate'] is None and report['rng_calls']==0,
         'compact cost newly computed scoped nonregression result')
    math_names={n for n in source if n.endswith('.py')}
    def current_math():
        need(not base.git('status','--porcelain','--untracked-files=all','--',*math_names),'compact cost current complete source clean')
        result={}
        for name in math_names:
            raw=archive.read(ROOT/name);need(digest(raw) in base.variants(objects.body(ORIGIN,name)),
                'compact cost current reference closure drift');result[name]=digest(raw)
        return result
    math_before=current_math()
    fresh=storage.replay()
    need(helper.decode(json.dumps(fresh).encode())==helper.decode(files['study/independent-storage-replay.json']),
         'compact cost fresh complete independent state/policy replay')
    need(bootstrap()==before and current_math()==math_before and load()[2]==pins and
         archive.load(storage.PACKET,helper,pin=storage.PIN,version='compact-role-storage',labels=('observations','builds','objects'),
             packager='package_compact_role_storage1.py.txt')[2]==state_pins,'compact cost final source/state/cost packet drift')
    return {'status':'same-policy-compact-storage-whole-call-replayed','original_native_processes':260,'original_unit_children':2,
        'paired_elapsed_ratios':ratios,'median_compact_canonical_ratio':median,'pairs_above_1_10':slow,
        'whole_call_nonregression_gate_pass':median<=1.05 and slow<=2,'ratio_range':[min(ratios),max(ratios)],
        'same_exact_numeric_policies':True,'same_wire_sizes':True,'independent_state_cases':fresh['cases'],
        'native_calls':0,'archived_source_executed':False,'quality_gate':None,'supported_native_epochs':2,
        'stored_expanded_bytes':manifest['stored_expanded_bytes'],
        'scope':'All original same-policy storage pairs and exact current mathematical replay. One uncontrolled-load host; no allocator/RSS, stable/universal throughput, longer learning or quality admission.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('packet',nargs='?',type=Path,default=PACKET)
    print(json.dumps(replay(p.parse_args().packet),indent=2))
