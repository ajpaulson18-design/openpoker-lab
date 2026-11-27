"""Admit same-owner storage provenance before current exact mathematical replay."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
PACKET=ROOT/'benchmarks/results/compact-role-storage-v1'
PIN=(1540,'0108e8753ec3d2932c7b7be7740634fb0cfb85ba03120a180ab106cc084383b3')
FIRST_BUILD='8524f827a32ebeeeaf90ed09dcb970f1bc1890aa'
BUILD='4915735b8850d64ad04411bc66ff71fdb211d612'
STUDY='e05aa85ad1d203c21fc8d28e8d742327b6ad961b'
ORIGIN='93aae969b436ae73a667f8bc18b54d4d568d7bbd'


def replay(packet=PACKET):
    from scripts import replay_joint_cycles_packet as base,joint_evidence_archive as archive
    from scripts import replay_joint_two_epoch_packet as helper,replay_single_pass_packet as known,replay_opponent_role_walk as parent
    need=base.need;digest=lambda b:sha256(b).hexdigest()
    def bootstrap():
        prior=base.bootstrap();name='scripts/replay_compact_role_storage.py';raw=archive.read(ROOT/name)
        need(not base.git('status','--porcelain','--untracked-files=all','--',name) and
             digest(raw) in base.variants(base.git('show',prior[0]+':'+name)),'compact storage committed replay bootstrap')
        return prior,digest(raw)
    before=bootstrap();need(not any(n=='tests' or n.startswith(('tests.','pokerlab')) for n in sys.modules),'compact storage fresh mathematical process')
    def load():return archive.load(packet,helper,pin=PIN,version='compact-role-storage',labels=('observations','builds','objects'),
        packager='package_compact_role_storage1.py.txt')
    manifest,loaded,pins=load();files=loaded['observations'];buildfiles=loaded['builds']
    class Objects(helper.GitObjects):
        def __init__(self):super().__init__();self.blobs={}
        def body(self,head,name):
            blob=self.tree(head).get(name);need(blob is not None,'compact storage introduced Git source')
            if blob not in self.blobs:self.blobs[blob]=super().body(head,name)
            return self.blobs[blob]
    objects=Objects();authentication={};source_maps={}
    def sources(members,prefix,head,count):
        record=helper.decode(members[prefix+'/source-identity.json']);hashes=record['raw_sha256'];source={}
        need(record['head']==head and len(hashes)==count and set(hashes)==set(record['committed_blobs']) and
             {n[len(prefix+'/source/'):] for n in members if n.startswith(prefix+'/source/')}==set(hashes),
             'compact storage complete original source inventory')
        for name,expected in hashes.items():
            body=members[prefix+'/source/'+helper.safe_name(name)];blob=objects.tree(head).get(name)
            need(digest(body)==expected and record['committed_blobs'][name]==blob and
                 (helper.source_bytes_match(body,objects.body(head,name),name,blob) or
                  known.HISTORICAL_CHECKOUTS.get(name)==(expected,blob)), 'compact storage original raw/Git source closure')
            source[name]=body
        authentication[prefix]={'head':head,'files':count};source_maps[prefix]=source;return source
    builds={};names=[f'role-storage-{kind}-build{version}' for kind in ('canonical','compact','controls') for version in (1,2)]
    names.extend(('role-storage-controls-build3','opponent-role-default-regression-build1'))
    for name in names:
        default=name=='opponent-role-default-regression-build1';version=int(name[-1])
        head=BUILD if default or version==2 else STUDY if version==3 else FIRST_BUILD
        source=sources(buildfiles,name,head,33 if default else 35);exit_code=buildfiles['logs/'+name+'.exit'].strip()
        if version==1 and not default:
            need(exit_code!=b'0' and b'C2131' in buildfiles[name+'/build.log'] and
                 name+'/native-exact-build-manifest.json' not in buildfiles,'compact storage first constant-expression build failures')
        else:
            raw=buildfiles[name+'/native-exact-build-manifest.json'];build=helper.decode(raw)
            need(exit_code==b'0' and build['contract']=='native-exact-build-v1' and build['source_sha256']=={n:digest(b) for n,b in source.items()},
                 'compact storage original successful build closure')
            if name!='role-storage-controls-build2':builds[build['target']]=(raw,build,source)
    need(set(builds)=={'role-storage-canonical','role-storage-compact','role-storage-controls','opponent-role-four-street'},
         'compact storage exact executed build inventory')
    processes,_=helper.process_receipts(files);expected={'units/normal','units/optimized'};prefixes=[];matrix=[]
    labels=('same-world','boundaries','shared-flop-future','sb-loss','sb-win','shared-board-distinct-holding')
    for mode in ('normal','optimized'):
        sources(files,'study/'+mode,STUDY,96);prefixes.append(('study/'+mode,STUDY))
        need(files['logs/compact-role-storage-study1-'+mode+'.exit'].strip()==b'0' and
             files['logs/compact-role-storage-matrix1-'+mode+'.exit'].strip()==b'0','compact storage original outer study/matrix exits')
        for profile in (0,1):
            for label in labels:
                prefix=f'matrix/{mode}/profile-{profile}-{label}';sources(files,prefix,ORIGIN,96);prefixes.append((prefix,ORIGIN))
                if mode=='normal':matrix.append(prefix)
    sources(files,'units',ORIGIN,17)
    rejection_labels={'reject-'+x for x in ('version','profile','lifetime','private-selector','board-selector','ticket-extent',
        'ticket-Q','trailing','oversize','short-tape','excess-tape')}
    targets={'canonical':'role-storage-canonical','compact':'role-storage-compact','controls':'role-storage-controls',
        'default':'opponent-role-four-street',**{n:'role-storage-compact' for n in rejection_labels}}
    for prefix,head in prefixes:
        report=helper.decode(files[prefix+'/result.json']);protocol=helper.decode(files[prefix+'/protocol.json'])
        need(report['source_head']==head and report['source_files']==96 and report['native_calls']==15 and report['native_rejections']==11 and
             report['default_full_wire_historical_identity'] is True and report['canonical_observer_normalized_identity'] is True and
             report['same_numeric_policy_all_coordinates'] is True and report['supported_native_epochs']==2 and
             report['archived_source_executed'] is False and report['quality_gate'] is None and report['rng_calls']==0 and
             protocol['original_packet_pin']==list(parent.PIN) and protocol['request_sha256']==digest(files[prefix+'/request.bin']),
             'compact storage original complete controller/protocol outcome')
        inventory={n[len(prefix+'/'):-len('-invocation.json')] for n in files if n.startswith(prefix+'/') and
            '/' not in n[len(prefix+'/'):] and n.endswith('-invocation.json')}
        need(inventory==set(targets),'compact storage complete original invocation inventory')
        for label,target in targets.items():
            process=prefix+'/'+label;expected.add(process);inv=helper.decode(files[prefix+'/'+label+'-invocation.json']);raw,build,source=builds[target]
            need(files[prefix+'/'+target+'-build.json']==raw and set(source)<=set(source_maps[prefix]) and
                 all(source[n]==source_maps[prefix][n] for n in source),'compact storage original study/build raw link')
            command=inv['command'];need(inv['source_head']==head and inv['stdin_bytes']==0 and inv['automatic_retries']==0 and
                 inv['python_optimized']==int('/optimized' in prefix) and inv['executable_sha256']==build['executable_sha256'] and
                 inv['build_manifest_sha256']==digest(raw) and command[0]==build['executable'], 'compact storage original executable/argv identity')
            if label=='controls':need(len(command)==1,'compact storage explicit controls arity')
            else:
                filename='request.bin' if label in ('canonical','compact','default') else label[len('reject-'):]+'-request.bin'
                need(len(command)==2 and command[1].replace('\\','/').endswith('/'+filename) and prefix+'/'+filename in files,
                     'compact storage original complete supplied-file identity')
            rejected=label in rejection_labels
            need(process in processes and processes[process]['exit']==(2 if rejected else 0) and files[process+'/request.bin']==b'' and
                 (not files[process+'/stdout.bin'] and bool(files[process+'/stderr.bin']) if rejected else not files[process+'/stderr.bin']),
                 'compact storage original actual exit/private streams')
        need({prefix+'/'+p['label']:p['receipt'] for p in report['processes']}==
             {prefix+'/'+label:helper.decode(files[prefix+'/'+label+'/process.json']) for label in targets},
             'compact storage controller/actual process link')
    need(set(processes)==expected and len(processes)==392 and all(processes['units/'+m]['exit']==0 for m in ('normal','optimized')),
         'compact storage exact original process universe')
    math_names={n for n in source_maps[matrix[0]] if n.endswith('.py')}
    def current_math():
        need(not (ROOT/'tests/__init__.py').exists() and not (ROOT/'scripts/__init__.py').exists() and
             not base.git('status','--porcelain','--untracked-files=all','--',*math_names),'compact storage current reference namespace/source')
        result={}
        for name in math_names:
            body=archive.read(ROOT/name);need(digest(body) in base.variants(objects.body(ORIGIN,name)),
                'compact storage current complete reference drift: '+name);result[name]=digest(body)
        return result
    math_before=current_math();previous=sys.pycache_prefix,sys.dont_write_bytecode
    with TemporaryDirectory(prefix='compact-role-replay-cache-',dir=ROOT.parent) as cache:
        sys.pycache_prefix=cache;sys.dont_write_bytecode=True
        try:
            # This authenticates the original canonical parent and freshly
            # verifies every coordinate with its unchanged literal oracle.
            # Exact full-record equality below transports that independent
            # mathematical result; no second oracle or archived code is used.
            canonical_parent=parent.replay()
            _pm,parent_files,parent_pins=archive.load(parent.PACKET,helper,pin=parent.PIN,version='opponent-role-walk',
                labels=('observations','builds','objects'),packager='package_opponent_role_walk1.py.txt')
            from tests.compact_role_storage_reference import unwrap,verify_controls
            from tests.virtual_role_walk_wire_reference import parse,receipts,request_tapes
            summaries=[];totals={'canonical_used':0,'compact_used':0,'canonical_capacity':0,'compact_capacity':0}
            numerical_fields=('world','roots','counts','work','peak_bits','raw','choices','snapshot')
            for prefix in matrix:
                other=prefix.replace('/normal/','/optimized/');protocol=helper.decode(files[prefix+'/protocol.json'])
                profile=protocol['profile'];selectors=tuple(tuple(x) for x in protocol['selectors']);rule=protocol['rule'];label=protocol['case_label']
                request=files[prefix+'/request.bin'];original=parent_files['observations']['matrix/normal/'+label+'/native/stdout.bin']
                need(request==files[other+'/request.bin']==parent_files['observations']['matrix/normal/'+label+'/request.bin'] and
                     files[prefix+'/default/stdout.bin']==files[other+'/default/stdout.bin']==original,
                     'compact storage both fresh default wires match independently replayed original history')
                expected_records=parse(original,profile,selectors,request_tapes(request,profile,selectors));receipts(expected_records)
                control=verify_controls(files[prefix+'/controls/stdout.bin'])
                need(files[prefix+'/controls/stdout.bin']==files[other+'/controls/stdout.bin'],'compact storage paired original control identity')
                case={}
                for mode,name in ((0,'canonical'),(1,'compact')):
                    raw=files[prefix+'/'+name+'/stdout.bin'];need(raw==files[other+'/'+name+'/stdout.bin'],'compact storage full paired-mode native identity')
                    records,normalized,storage,_admission=unwrap(raw,request,profile,selectors,rule,mode)
                    need(all(all(a[k]==b[k] for k in numerical_fields) for a,b in zip(records,expected_records)),
                         'compact storage complete independently replayed mathematical-record equality')
                    if mode==0:need(normalized==original,'compact storage canonical observer exact normalized original wire')
                    for mode_prefix in (prefix,other):
                        report=helper.decode(files[mode_prefix+'/result.json']);saved_report=report['reports'][name]
                        need(all(saved_report[k]==helper.decode(json.dumps(v).encode()) for k,v in storage.items()) and
                             report['controls']==helper.decode(json.dumps(control).encode()) and
                             report['output_sha256'][name]==digest(raw),'compact storage current actual ledger/capacity/control outcome')
                    totals[name+'_used']+=sum(x['native_used_limbs'] for x in storage['storage'])
                    totals[name+'_capacity']+=sum(x['native_capacity_limbs'] for x in storage['storage'])
                    case[name]={'wire_sha256':digest(raw),'storage':storage['storage']}
                for mode_prefix in (prefix,other):
                    report=helper.decode(files[mode_prefix+'/result.json']);mutants={n.rsplit('/',1)[-1][:-4]:n for n in files if n.startswith(mode_prefix+'/mutations/')}
                    need(set(mutants)==set(report['parser_mutations'])=={'truncated','trailing','resource','persistent-mode','backend-used','root','canonical-regret'},
                         'compact storage complete original mutation inventory')
                    for name,path in mutants.items():
                        try:
                            changed,_wire,_storage,_admission=unwrap(files[path],request,profile,selectors,rule,1)
                            need(all(all(a[k]==b[k] for k in numerical_fields) for a,b in zip(changed,expected_records)),
                                 'compact storage altered numeric coordinate')
                        except ValueError:pass
                        else:raise ValueError('compact storage saved mutation accepted: '+name)
                summaries.append({'case':label,**case})
            for mode in ('normal','optimized'):
                for name in ('controls','default','canonical','compact'):
                    need(files['study/'+mode+'/'+name+'/stdout.bin']==files[matrix[0]+'/'+name+'/stdout.bin'],
                         'compact storage first original study identity with full matrix')
            need(bootstrap()==before and current_math()==math_before and load()[2]==pins and
                 archive.load(parent.PACKET,helper,pin=parent.PIN,version='opponent-role-walk',labels=('observations','builds','objects'),
                     packager='package_opponent_role_walk1.py.txt')[2]==parent_pins,'compact storage final source/packet drift')
            return {'status':'same-owner-compact-role-storage-replayed','cases':12,'numeric_coordinates_per_representation':canonical_parent['numeric_coordinates'],
                'original_native_processes':390,'original_unit_children':2,'first_compile_failures':3,'compiled_unexecuted_control_builds':1,
                'native_calls':0,'archived_source_executed':False,'rng_calls':0,'quality_gate':None,'supported_native_epochs':2,
                'authentication':authentication,'totals_across_separate_snapshots':totals,'fresh':summaries,
                'stored_expanded_bytes':manifest['stored_expanded_bytes'],
                'scope':'Exact same-Store carriers and current literal parent mathematics. Used limbs independently exact; capacity is authenticated original native observation with plausibility bounds. No allocator/RSS, runtime, longer-lifetime or solved-quality admission.'}
        finally:sys.pycache_prefix,sys.dont_write_bytecode=previous


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('packet',nargs='?',type=Path,default=PACKET)
    print(json.dumps(replay(p.parse_args().packet),indent=2))
