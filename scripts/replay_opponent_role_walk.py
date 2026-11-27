"""Authenticate original whole-walk evidence before fresh current literal math."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
PACKET=ROOT/'benchmarks/results/opponent-role-walk-v1'
PIN=(1492,'39d31e542ca909fa1cb0a16c03c155caaf7d4a5096da625a8ec6f2edec312578')
INITIAL='c327043151de8f50e9479c3180f8751a6551d2a0'
BUILD='c0f3f8245cf8a2e2ea57f81556dce6c2fcc8a2a5'
FIRST='7ea1224300176a5bd337d5dc044e9fe9a71ccc41'
SECOND='7433f3351f5dd129c89eb53432cd15a001b1e1c8'
ORIGIN='56f40ab73833204c0d4926d04fa43cba5c2800eb'
UNITS='9dbeedb9e9acba0c7104ca1f0ecd5fade70fa805'


def replay(packet=PACKET):
    from scripts import replay_joint_cycles_packet as base,joint_evidence_archive as archive
    from scripts import replay_joint_two_epoch_packet as helper,replay_single_pass_packet as known
    need=base.need;digest=lambda b:sha256(b).hexdigest()
    def bootstrap():
        prior=base.bootstrap();name='scripts/replay_opponent_role_walk.py';raw=archive.read(ROOT/name)
        need(not base.git('status','--porcelain','--untracked-files=all','--',name) and
             digest(raw) in base.variants(base.git('show',prior[0]+':'+name)), 'role walk committed replay bootstrap')
        return prior,digest(raw)
    before=bootstrap()
    need(not any(n=='tests' or n.startswith(('tests.','pokerlab')) for n in sys.modules),'role walk fresh reference process')
    def load():return archive.load(packet,helper,pin=PIN,version='opponent-role-walk',
        labels=('observations','builds','objects'),packager='package_opponent_role_walk1.py.txt')
    manifest,loaded,pins=load();files=loaded['observations'];build_files=loaded['builds']
    class Objects(helper.GitObjects):
        def __init__(self):super().__init__();self.blobs={}
        def body(self,head,name):
            blob=self.tree(head).get(name);need(blob is not None,'role walk introduced source blob')
            if blob not in self.blobs:self.blobs[blob]=super().body(head,name)
            return self.blobs[blob]
    objects=Objects();authentication={}
    def sources(members,prefix,head,count):
        record=helper.decode(members[prefix+'/source-identity.json']);hashes=record['raw_sha256']
        need(record['head']==head and len(hashes)==count and set(hashes)==set(record['committed_blobs']) and
             {n[len(prefix+'/source/'):] for n in members if n.startswith(prefix+'/source/')}==set(hashes),
             'role walk complete original source inventory')
        for name,expected in hashes.items():
            raw=members[prefix+'/source/'+helper.safe_name(name)];blob=objects.tree(head).get(name)
            need(digest(raw)==expected and record['committed_blobs'][name]==blob and
                 (helper.source_bytes_match(raw,objects.body(head,name),name,blob) or
                  known.HISTORICAL_CHECKOUTS.get(name)==(expected,blob)), 'role walk original raw/Git source closure')
        authentication[prefix]={'head':head,'files':count};return hashes
    builds={}
    for target in ('four-street','walk-controls'):
        for version in (1,2):
            prefix=f'{target}-build-{version}';hashes=sources(build_files,prefix,INITIAL if version==1 else BUILD,33)
            outer=f'logs/opponent-role-{target}-build{version}.exit'
            if version==1:
                need(build_files[outer].strip()!=b'0' and b'C4334' in build_files[prefix+'/build.log'] and
                     prefix+'/native-exact-build-manifest.json' not in build_files,'role walk original warning-policy build failure')
            else:
                raw=build_files[prefix+'/native-exact-build-manifest.json'];record=helper.decode(raw)
                need(record['target']=='opponent-role-'+target and record['contract']=='native-exact-build-v1' and
                     record['source_sha256']==hashes and build_files[outer].strip()==b'0', 'role walk introduced successful build')
                builds[record['target']]=(raw,record,hashes)
    sources(files,'reference-check',INITIAL,12);sources(files,'units',UNITS,16)
    processes,_=helper.process_receipts(files);expected_processes={f'units/{mode}' for mode in ('normal','optimized')}
    reports={};matrix=[]
    labels=('same-world','boundaries','shared-flop-future','sb-loss','sb-win','shared-board-distinct-holding')
    for mode in ('normal','optimized'):
        need(files[f'logs/opponent-role-walk-study1-{mode}.exit'].strip()==b'1' and
             b"NameError: name 'raw' is not defined" in files[f'logs/opponent-role-walk-study1-{mode}.stderr'],
             'role walk original post-math report failure retained')
        need(files[f'logs/opponent-role-walk-study2-{mode}.exit'].strip()==b'0' and
             files[f'logs/opponent-role-walk-matrix1-{mode}.exit'].strip()==b'0','role walk complete original outer exits')
        for version,head in ((1,FIRST),(2,SECOND)):
            prefix=f'study-{version}/{mode}';sources(files,prefix,head,53)
            reports[prefix]=head
        for profile in (0,1):
            for label in labels:
                prefix=f'matrix/{mode}/profile-{profile}-{label}'
                sources(files,prefix,ORIGIN,54);reports[prefix]=ORIGIN
                if mode=='normal':matrix.append(prefix)
    for prefix,head in reports.items():
        success=not prefix.startswith('study-1/');hashes=helper.decode(files[prefix+'/source-identity.json'])['raw_sha256']
        invocations={n[len(prefix+'/'):-len('-invocation.json')]:n for n in files
            if n.startswith(prefix+'/') and '/' not in n[len(prefix+'/'):] and n.endswith('-invocation.json')}
        expected_labels={'controls','native'}
        if success:expected_labels|={'reject-'+x for x in ('version','profile','lifetime','private-selector','board-selector',
            'ticket-extent','ticket-Q','trailing','oversize','short-tape','excess-tape')}
        need(set(invocations)==expected_labels,'role walk original complete invocation inventory')
        for label,name in invocations.items():
            native=label!='controls';target='opponent-role-four-street' if native else 'opponent-role-walk-controls'
            build_raw,build,bhash=builds[target]
            need(set(bhash)<=set(hashes) and all(hashes[n]==bhash[n] for n in bhash) and
                 files[prefix+'/'+target+'-build.json']==build_raw,'role walk original study/build source link')
            inv=helper.decode(files[name]);command=inv['command'];process=prefix+'/'+label;expected_processes.add(process)
            need(inv['source_head']==head and inv['automatic_retries']==0 and inv['stdin_bytes']==0 and
                 inv['python_optimized']==int('/optimized' in prefix) and inv['executable_sha256']==build['executable_sha256'] and
                 inv['build_manifest_sha256']==digest(build_raw) and command[0]==build['executable'] and
                 len(command)==(2 if native else 1) and files[process+'/request.bin']==b'',
                 'role walk original supplied-file invocation identity')
            if native:
                filename='request.bin' if label=='native' else label[len('reject-'):]+'-request.bin'
                need(command[1].replace('\\','/').endswith('/'+filename) and prefix+'/'+filename in files,
                     'role walk complete original input file identity')
            rejected=label.startswith('reject-')
            need(process in processes and processes[process]['exit']==(2 if rejected else 0) and
                 (not files[process+'/stdout.bin'] and bool(files[process+'/stderr.bin']) if rejected else
                  not files[process+'/stderr.bin']), 'role walk actual original child exit/private streams')
        if success:
            report=helper.decode(files[prefix+'/result.json']);protocol=helper.decode(files[prefix+'/protocol.json'])
            need(report['source_head']==head and report['source_files']==len(hashes) and report['native_calls']==13 and
                 report['native_rejections']==11 and report['parser_mutations']==5 and report['executed_signed_regret_epochs']==2 and
                 report['quality_gate'] is None and report['rng_calls']==0 and report['archived_source_executed'] is False and
                 report['output_sha256']==digest(files[prefix+'/native/stdout.bin']) and
                 protocol['request_sha256']==digest(files[prefix+'/request.bin']), 'role walk original complete controller result')
            need({prefix+'/'+p['label']:p['receipt'] for p in report['processes']}==
                 {prefix+'/'+label:helper.decode(files[prefix+'/'+label+'/process.json']) for label in expected_labels},
                 'role walk original report/process receipt link')
    need(set(processes)==expected_processes and len(processes)==344 and
         all(processes['units/'+mode]['exit']==0 for mode in ('normal','optimized')), 'role walk exact original process universe')
    unit_report=helper.decode(files['units/result.json'])
    need(unit_report['source_head']==UNITS and unit_report['unit_methods_per_mode']==4 and unit_report['finite_retention_vectors']==772,
         'role walk original retention/admission controls')
    current_names={n for n in helper.decode(files[matrix[0]+'/source-identity.json'])['raw_sha256'] if n.endswith('.py')}
    def current_math():
        need(not (ROOT/'tests/__init__.py').exists() and not (ROOT/'scripts/__init__.py').exists() and
             not base.git('status','--porcelain','--untracked-files=all','--',*current_names), 'role walk current namespace/source')
        result={}
        for name in current_names:
            raw=archive.read(ROOT/name);need(digest(raw) in base.variants(objects.body(ORIGIN,name)),
                'role walk current complete reference closure drift: '+name);result[name]=digest(raw)
        return result
    math_before=current_math();previous=sys.pycache_prefix,sys.dont_write_bytecode
    with TemporaryDirectory(prefix='role-walk-replay-cache-',dir=ROOT.parent) as cache:
        sys.pycache_prefix=cache;sys.dont_write_bytecode=True
        try:
            from tests.virtual_role_walk_wire_reference import verify,verify_controls,parse,receipts,request_tapes
            fresh=[];scalar=verify_controls(files[matrix[0]+'/controls/stdout.bin'])
            for prefix in matrix:
                other=prefix.replace('/normal/','/optimized/');protocol=helper.decode(files[prefix+'/protocol.json'])
                need(files[prefix+'/native/stdout.bin']==files[other+'/native/stdout.bin'] and
                     files[prefix+'/request.bin']==files[other+'/request.bin'] and
                     files[prefix+'/controls/stdout.bin']==files[matrix[0]+'/controls/stdout.bin']==files[other+'/controls/stdout.bin'],
                     'role walk complete paired-mode original byte identity')
                selectors=tuple(tuple(x) for x in protocol['selectors']);profile=protocol['profile'];rule=protocol['rule']
                report=verify(files[prefix+'/native/stdout.bin'],files[prefix+'/request.bin'],profile,selectors,rule)
                for mode_prefix in (prefix,other):
                    original=helper.decode(files[mode_prefix+'/result.json'])
                    need(all(original[k]==helper.decode(json.dumps(v).encode()) for k,v in report.items()),
                         'role walk fresh complete numerical/ledger outcome')
                    altered=[n for n in files if n.startswith(mode_prefix+'/mutations/')]
                    need(len(altered)==5,'role walk complete original altered-frame inventory')
                    # Original controls already compared the valid-width numeric
                    # corruption to the literal state. Recheck framing/ledger
                    # corruptions here; the saved numeric coordinate is required
                    # to differ at exactly the first retained regret byte.
                    for name in altered:
                        body=files[name]
                        if name.endswith('/committed-regret.bin'):
                            valid=files[mode_prefix+'/native/stdout.bin'];at=valid.index(b'OPLRSN01')+72
                            expected=bytearray(valid);expected[at]^=1
                            need(body==bytes(expected),'role walk preserved committed-regret mutation')
                        else:
                            try:
                                parsed=parse(body,profile,selectors,request_tapes(files[mode_prefix+'/request.bin'],profile,selectors));receipts(parsed)
                            except ValueError:pass
                            else:raise ValueError('role walk saved altered framing/ledger accepted')
                fresh.append(report)
            first=matrix[0]
            for version in (1,2):
                for mode in ('normal','optimized'):
                    prefix=f'study-{version}/{mode}'
                    need(files[prefix+'/request.bin']==files[first+'/request.bin'] and
                         files[prefix+'/native/stdout.bin']==files[first+'/native/stdout.bin'] and
                         files[prefix+'/controls/stdout.bin']==files[first+'/controls/stdout.bin'],
                         'role walk historical report failures/success share admitted exact wire')
            need(bootstrap()==before and current_math()==math_before and load()[2]==pins,'role walk final packet/source drift')
            return {'status':'full-four-street-role-walk-replayed','cases':12,'numeric_coordinates':sum(x['all_numeric_coordinates'] for x in fresh),
                'original_native_processes':342,'original_unit_children':2,'original_compile_failures':2,'original_report_failures':2,
                'authentication':authentication,'scalar_controls':scalar,'fresh':fresh,'native_calls':0,'archived_source_executed':False,
                'rng_calls':0,'quality_gate':None,'stored_expanded_bytes':manifest['stored_expanded_bytes'],
                'scope':'Current exact full1326 law and literal direct-reach reference replay all deterministic T2 native updates. No RNG/convergence, longer lifetime, timing, eleven-card or unrestricted NLHE admission.'}
        finally:sys.pycache_prefix,sys.dont_write_bytecode=previous


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('packet',nargs='?',type=Path,default=PACKET)
    print(json.dumps(replay(p.parse_args().packet),indent=2))
