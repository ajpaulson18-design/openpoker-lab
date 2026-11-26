"""Admit every original row attempt/build before current saved-only arithmetic."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
PACKET=ROOT/'benchmarks/results/opponent-role-rows-v2'
PIN=(0,'PENDING')
ORIGINS={1:'7025adf1fe6543f83fa5ae5d4b3b77c09bbc5003',2:'61305c2d66f799f88fdfd77966983f4cd10340bb',
         3:'37b94a602b0497a033362e4a46bc7ebd84cda791',4:'PENDING'}
MATH=('tests/opponent_role_row_reference.py','scripts/opponent_action_moment_frame.py')


def replay(packet=PACKET):
    from scripts import replay_joint_cycles_packet as base,joint_evidence_archive as archive
    from scripts import replay_joint_two_epoch_packet as helper,replay_single_pass_packet as known
    need=base.need;digest=lambda raw:sha256(raw).hexdigest()
    def bootstrap():
        prior=base.bootstrap();names=('scripts/replay_opponent_role_rows.py','scripts/replay_opponent_action_moments.py')
        need(not base.git('status','--porcelain','--untracked-files=all','--',*names),'role committed saved reader')
        result={}
        for name in names:
            raw=archive.read(ROOT/name);need(digest(raw) in base.variants(base.git('show',prior[0]+':'+name)),'role reader raw source drift')
            result[name]=digest(raw)
        return prior,result
    before=bootstrap();need(not any(n=='tests' or n.startswith(('tests.','pokerlab')) for n in sys.modules),'role fresh reference process')
    def load():return archive.load(packet,helper,pin=PIN,version='opponent-role-rows',
        labels=('first-refusal','observations','builds','objects'),packager='package_opponent_role_rows1.py.txt')
    manifest,loaded,pins=load();objects=helper.GitObjects();identities={}
    def sources(files,prefix,origin,count=None):
        identity=helper.decode(files[prefix+'/source-identity.json']);hashes=identity['raw_sha256']
        need(identity['head']==origin and (count is None or len(hashes)==count) and set(hashes)==set(identity['committed_blobs']) and
             {n[len(prefix+'/source/'):] for n in files if n.startswith(prefix+'/source/')}==set(hashes),
             'role complete original captured source closure')
        for name,expected in hashes.items():
            raw=files[prefix+'/source/'+helper.safe_name(name)];blob=objects.tree(origin).get(name)
            need(digest(raw)==expected and identity['committed_blobs'][name]==blob and
                 (helper.source_bytes_match(raw,objects.body(origin,name),name,blob) or
                  known.HISTORICAL_CHECKOUTS.get(name)==(expected,blob)),'role original raw/Git source identity')
        identities[prefix]={'head':origin,'files':len(hashes)};return hashes
    builds={}
    for version in (1,2):
        prefix=f'build-{version}';files=loaded['builds'];hashes=sources(files,prefix,ORIGINS[version])
        raw=files[prefix+'/native-exact-build-manifest.json'];build=helper.decode(raw)
        need(build['target']=='opponent-role-row-controls' and build['source_sha256']==hashes and
             build['contract']=='native-exact-build-v1' and 'No History/role-lease authority' in build['scope'] and
             len(build['executable_sha256'])==64,'role introduced build/source target identity')
        builds[version]=(build,digest(raw))
    original_processes=0;outcomes=[]
    for version in (1,2,3,4):
        files=loaded['first-refusal' if version==1 else 'observations'];build,build_digest=builds[1 if version==1 else 2]
        for mode in ('normal','optimized'):
            prefix=f'study-{version}/{mode}';sources(files,prefix,ORIGINS[version],68)
            processes,_=helper.process_receipts({n:b for n,b in files.items() if n.startswith(prefix+'/')})
            labels=('guards',) if version==1 else ('guards','matrix','bad-grid','bad-step-count','wide-regret','truncated','trailing','unknown-argument')
            need(set(processes)=={prefix+'/'+n for n in labels},'role every original native process')
            original_processes+=len(processes);records=[]
            protocol=helper.decode(files[prefix+'/protocol.json'])
            need(protocol['head']==ORIGINS[version] and protocol['native_calls']==8 and
                 protocol['python_optimized']==int(mode=='optimized') and protocol['automatic_retries']==0 and
                 protocol['request_cap']==116000 and protocol['output_cap']==131072,'role original protocol unchanged bounds')
            for label in labels:
                child=prefix+'/'+label;receipt=helper.decode(files[child+'/process.json'])
                expected=0 if label in ('guards','matrix') else 2
                need(processes[child]['exit']==expected and
                     files[child+'/request.bin']==b'','role actual original exit/executable/pipe input')
                payload=files.get(prefix+'/'+label+'-payload.bin',b'')
                if version==4:
                    invocation=helper.decode(files[prefix+'/'+label+'-invocation.json'])
                    command=invocation['command']
                    need(command[0]==build['executable'] and invocation['executable_sha256']==build['executable_sha256'] and
                         invocation['build_manifest_sha256']==build_digest and invocation['stdin_bytes']==0 and
                         (invocation['payload_bytes'],invocation['payload_sha256'])==(len(payload),digest(payload)) and
                         (command[1:]==['--guards'] if label=='guards' else
                          command[1:]==['--unsupported'] if label=='unknown-argument' else
                          len(command)==3 and command[1]=='--request-file' and
                          command[2].replace('\\','/').endswith('/'+label+'-payload.bin')),
                         'role original invocation/executable/payload link')
                record={'label':label,'payload_sha256':digest(payload),'payload_bytes':len(payload),'receipt':receipt}
                if version!=1:records.append(record)
                if label=='guards':
                    lines=files[child+'/stdout.bin'].decode('ascii').splitlines()
                    need(len(lines)==21 and all(n.startswith('GUARD ') and n.endswith(' PASS') for n in lines[:-1]) and
                         lines[-1]=='OPPONENT_ROLE_ROW_GUARDS_V1 PASS 20' and not files[child+'/stderr.bin'],'role twenty original guards')
                elif label=='matrix':need(not files[child+'/stderr.bin'],'role successful matrix stderr')
                else:need(not files[child+'/stdout.bin'] and files[child+'/stderr.bin'],'role negative private output')
            if version!=1:
                report=helper.decode(files[prefix+'/result.json'])
                need(report['original_processes']==records and report['source_head']==ORIGINS[version] and
                     report['source_files']==68 and report['build_manifest_sha256']==build_digest and
                     report['executable_sha256']==build['executable_sha256'] and report['native_calls']==8 and
                     report['native_guard_refusals']==20 and report['archived_source_executed'] is False,
                     'role complete original controller/build outcome')
                outcomes.append((version,mode,prefix,report))
    need(original_processes==50,'role all 50 original native process receipts')
    for mode in ('normal','optimized'):
        log=loaded['first-refusal'][f'logs/opponent-role-row-study1-{mode}.stderr']
        need(b"ValueError: bounded child request" in log,'role original pre-matrix pipe refusal preserved')
    def current_math():
        need(not (ROOT/'tests/__init__.py').exists() and not (ROOT/'scripts/__init__.py').exists() and
             not base.git('status','--porcelain','--untracked-files=all','--',*MATH),'role current mathematical source identity')
        result={}
        for name in MATH:
            raw=archive.read(ROOT/name)
            need(digest(raw) in base.variants(objects.body(ORIGINS[3],name)),'role current reference drift: '+name);result[name]=digest(raw)
        return result
    math_before=current_math();previous=sys.pycache_prefix,sys.dont_write_bytecode
    with TemporaryDirectory(prefix='role-row-empty-cache-',dir=ROOT.parent) as cache:
        sys.pycache_prefix=cache;sys.dont_write_bytecode=True
        try:
            from tests.opponent_role_row_reference import request_rows,encode,verify
            rows=request_rows();need(len(rows)==97,'role fresh complete witness/synthetic inventory')
            results=[];files=loaded['observations']
            for version,mode,prefix,report in outcomes:
                selected=rows[:96] if version==2 else rows
                need(encode(selected)==files[prefix+'/matrix-payload.bin'],'role fresh complete original input')
                fresh=verify(files[prefix+'/matrix/stdout.bin'],selected)
                need(all(report[k]==v for k,v in fresh.items()),'role fresh every R/A/policy and resource field')
                if mode=='optimized':need(files[prefix+'/matrix/stdout.bin']==files[prefix.replace('/optimized','/normal')+'/matrix/stdout.bin'],
                                          'role original numeric paired-mode byte identity')
                results.append({'version':version,'mode':mode,'fresh':fresh})
            for name in MATH:
                imported=sys.modules.get(name[:-3].replace('/','.'))
                need(imported is not None and Path(imported.__file__).resolve()==(ROOT/name).resolve(),'role executed current reference identity')
            need(bootstrap()==before and current_math()==math_before and load()[2]==pins,'role final source/packet drift')
            return {'status':'compact-role-row-evidence-replayed','original_source_closures':identities,
                'original_native_processes':50,'original_invocation_records':16,
                'older_invocation_limit':'34 earlier process receipts lack separate argv records; captured controller/build source reconstructs their command, not a raw original argv receipt.',
                'results':results,'native_calls':0,'archived_source_executed':False,
                'rng_calls':0,'attempted_training':False,'quality_gate':None,'stored_expanded_bytes':manifest['stored_expanded_bytes'],
                'scope':'Saved compact/canonical images and independent rational allocations, all original raw/Git/build/process admission. No native execution, role lease, whole walk, stochastic learning, timing or quality.'}
        finally:sys.pycache_prefix,sys.dont_write_bytecode=previous


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('packet',nargs='?',type=Path,default=PACKET)
    print(json.dumps(replay(parser.parse_args().packet),indent=2))
