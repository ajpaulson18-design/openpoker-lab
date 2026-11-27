"""Source-frozen same-policy storage comparison and untouched-default parity."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import struct
import sys
from scripts.run_opponent_action_study import ROOT,closure,git,need
from scripts.build_compact_role_storage import register,SOURCES,CANONICAL,COMPACT,CONTROLS
from scripts.build_frozen_role_walk import TARGET as DEFAULT,SOURCES as PRIOR_SOURCES


def run(canonical,compact,controls,default,output,profile,selectors,rule):
    register();paths={CANONICAL:Path(canonical).resolve(),COMPACT:Path(compact).resolve(),
        CONTROLS:Path(controls).resolve(),DEFAULT:Path(default).resolve()};output=Path(output).resolve()
    need(output.parent==ROOT.parent.resolve() and not output.exists(),'compact role fresh external study')
    names=closure(('scripts/run_compact_role_storage_study.py','scripts/run_compact_role_storage_matrix.py',
        'tests/compact_role_storage_reference.py','tests/test_native_exact_reach.py','tests/virtual_frozen_run_control.py',
        'scripts/replay_opponent_role_walk.py'))
    for name in (*[n for values in SOURCES.values() for n in values],*PRIOR_SOURCES[DEFAULT],
        'third_party/boost-multiprecision-1.92.0/manifest.json','third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt',
        'third_party/boost-multiprecision-1.92.0/headers.zip'):names[name]=(ROOT/name).read_bytes()
    need(not git('status','--porcelain','--untracked-files=all','--',*names),'compact role complete study source committed')
    head=git('rev-parse','HEAD').decode().strip()
    tree={line.split('\t',1)[1]:line.split('\t',1)[0].split()[2] for line in git('ls-tree','-r',head).decode().splitlines()}
    output.mkdir()
    def write(name,value):(output/name).write_text(json.dumps(value,indent=2)+'\n')
    for name,body in names.items():
        path=output/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
    write('source-identity.json',{'head':head,'python_optimized':sys.flags.optimize,'python_version':sys.version,
        'raw_sha256':{n:sha256(b).hexdigest() for n,b in names.items()},'committed_blobs':{n:tree[n] for n in names}})
    # No mathematical module is imported until complete committed bytes are durable.
    from tests.test_native_exact_reach import authenticate,sha
    from tests.virtual_frozen_run_control import run_bounded_child
    from tests.virtual_role_walk_reference import Context,INPUT,OUTPUT
    from tests.virtual_role_walk_wire_reference import parse,receipts,compare,request_tapes
    from tests.compact_role_storage_reference import unwrap,verify_controls
    from scripts.run_frozen_role_walk_matrix import cases
    from scripts import replay_opponent_role_walk as saved,joint_evidence_archive as archive,replay_joint_two_epoch_packet as helper
    identities={target:authenticate(path,ROOT,target) for target,path in paths.items()}
    for target,identity in identities.items():(output/(target+'-build.json')).write_bytes(identity[0])
    manifest,packet,pins=archive.load(saved.PACKET,helper,pin=saved.PIN,version='opponent-role-walk',
        labels=('observations','builds','objects'),packager='package_opponent_role_walk1.py.txt')
    label=next((name for name,pair_profile,pair,pair_rule in cases() if (pair_profile,pair,pair_rule)==(profile,selectors,rule)),None)
    need(label is not None,'compact role named original trajectory required')
    ctx=Context(profile,selectors,rule);ctx.run();request=ctx.request();request_path=output/'request.bin';request_path.write_bytes(request)
    write('protocol.json',{'profile':profile,'selectors':selectors,'rule':rule,'case_label':label,'original_packet_pin':saved.PIN,
        'request_sha256':sha256(request).hexdigest(),'automatic_retries':0,'same_policy_comparison':True,'native_supported_epochs':2})
    need(request==packet['observations']['matrix/normal/'+label+'/request.bin'],'compact role independent original request identity')
    processes=[]
    def invoke(name,target,args=(),success=True,cap=OUTPUT):
        path=paths[target];inv={'command':[str(path),*map(str,args)],'executable_sha256':sha(path),
            'build_manifest_sha256':sha256(identities[target][0]).hexdigest(),'stdin_bytes':0,'automatic_retries':0,
            'python_optimized':sys.flags.optimize,'source_head':head}
        write(name+'-invocation.json',inv)
        receipt=run_bounded_child(inv['command'],b'',output/name,stdout_limit=cap,stderr_limit=65536,timeout=180)
        processes.append({'label':name,'target':target,'receipt':receipt})
        need((receipt['status'],receipt['actual_exit_observed'],receipt['returncode'],receipt['failures'])==
            ('exited',True,0 if success else 2,[]) and authenticate(path,ROOT,target)==identities[target],
            'compact role actual original process exit/build identity: '+name)
        raw=(output/name/'stdout.bin').read_bytes();error=(output/name/'stderr.bin').read_bytes()
        need(not error if success else not raw and bool(error),'compact role original private streams: '+name)
        return raw
    control=verify_controls(invoke('controls',CONTROLS,cap=65536))
    original=invoke('default',DEFAULT,(request_path,))
    need(original==packet['observations']['matrix/normal/'+label+'/native/stdout.bin'],
         'compact role unchanged default complete historical byte identity')
    original_records=parse(original,profile,selectors,request_tapes(request,profile,selectors));receipts(original_records)
    original_report=compare(original_records,request,ctx,ctx.admission,len(original))
    reports={};raws={};records_by_mode={}
    for mode,target in ((0,CANONICAL),(1,COMPACT)):
        name='canonical' if mode==0 else 'compact';raw=invoke(name,target,(request_path,));raws[mode]=raw
        records,normalized,storage,admission=unwrap(raw,request,profile,selectors,rule,mode)
        if mode==0:need(normalized==original,'canonical storage observer unchanged complete default wire after declared wrapper removal')
        report=compare(records,request,ctx,admission,len(normalized));reports[name]={**report,**storage}
        records_by_mode[mode]=records
    for a,b in zip(records_by_mode[0],records_by_mode[1]):
        need(all(a[k]==b[k] for k in ('world','roots','counts','work','peak_bits','raw','choices','snapshot')),
            'compact role exact cross-representation roots/raw/state/policy identity')
    (output/'mutations').mkdir();mutations=[];raw=raws[1];offsets=reports['compact']['transport_offsets']
    changed=[('truncated',raw[:-1]),('trailing',raw+b'\0')]
    for name,at in (('resource',8+13*8),('persistent-mode',288),('backend-used',offsets['storage'][0]+8+5*8),
        ('root',offsets['roots'][0]),('canonical-regret',offsets['snapshot_regrets'][0])):
        body=bytearray(raw);body[at]^=1;changed.append((name,bytes(body)))
    for name,body in changed:
        (output/'mutations'/(name+'.bin')).write_bytes(body)
        try:
            records,normalized,_storage,admission=unwrap(body,request,profile,selectors,rule,1)
            compare(records,request,ctx,admission,len(normalized))
        except ValueError:mutations.append(name)
        else:raise ValueError('compact role altered frame accepted: '+name)
    bad=[]
    for name,index,value in (('version',0,2),('profile',1,2),('lifetime',2,3),
        ('private-selector',3,(1624350,25908876)[profile]),('board-selector',4,34246080),('ticket-extent',7,205),('ticket-Q',11,1<<52)):
        body=bytearray(request);struct.pack_into('<Q',body,8+8*index,value);bad.append((name,bytes(body)))
    bad.extend((('trailing',request+b'\0'),('oversize',b'\0'*(INPUT+1))))
    count=struct.unpack_from('<Q',request,64)[0];need(count>0,'compact role short/excess tape witness')
    body=bytearray(request);struct.pack_into('<Q',body,64,count-1);del body[96+8*(count-1):96+8*count];bad.append(('short-tape',bytes(body)))
    body=bytearray(request);struct.pack_into('<Q',body,64,count+1);body[96+8*count:96+8*count]=b'\0'*8;bad.append(('excess-tape',bytes(body)))
    for name,body in bad:
        path=output/(name+'-request.bin');path.write_bytes(body);invoke('reject-'+name,COMPACT,(path,),success=False)
    need(git('rev-parse','HEAD').decode().strip()==head and all((ROOT/n).read_bytes()==b for n,b in names.items()),
        'compact role final complete raw source/head drift')
    report={'status':'same-owner-role-storage-original-complete','source_head':head,'source_files':len(names),'case_label':label,
        'default_full_wire_historical_identity':True,'canonical_observer_normalized_identity':True,'same_numeric_policy_all_coordinates':True,
        'numeric_coordinates_per_representation':original_report['all_numeric_coordinates'],'reports':reports,'controls':control,
        'output_sha256':{name:sha256(raws[mode]).hexdigest() for mode,name in ((0,'canonical'),(1,'compact'))},
        'parser_mutations':mutations,'native_rejections':len(bad),'native_calls':len(processes),'processes':processes,
        'archived_source_executed':False,'rng_calls':0,'supported_native_epochs':2,'quality_gate':None,
        'scope':'Same sparse Store with explicit persistent carrier, both native roots/raw/evolving states identical after exact canonical expansion. Backend limb use/capacity is observed, not allocator/RSS or complete-call speed.'}
    write('result.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('canonical','compact','controls','default','output'):p.add_argument(name,type=Path)
    p.add_argument('--profile',type=int,choices=(0,1),default=0);p.add_argument('--selectors',nargs=4,type=int,default=(0,0,0,0))
    p.add_argument('--rule',choices=('first','last','middle','alternating'),default='first');a=p.parse_args()
    selectors=tuple(tuple(a.selectors[i:i+2]) for i in (0,2))
    result=run(a.canonical,a.compact,a.controls,a.default,a.output,a.profile,selectors,a.rule)
    print(json.dumps({k:v for k,v in result.items() if k!='processes'},indent=2))
