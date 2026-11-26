"""Authenticate source/build/process closure before current role-lease math."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
PACKET=ROOT/'benchmarks/results/opponent-role-epoch-v1'
PIN=(1472,'ec580e7783f44ee14a623bac2ada5c0efe8bf1f917f3fe4565ac29d42e9d87ab')
ORIGIN='7f6eb50e9bd062dd52468578a31cf9a1c7e6f247'
BUILD='629ee780793626b72ac830649eb7f5631287874d'
MATH=('tests/opponent_role_epoch_reference.py','tests/virtual_joint_two_epoch_forecast_reference.py')


def replay(packet=PACKET):
    from scripts import replay_joint_cycles_packet as base,joint_evidence_archive as archive
    from scripts import replay_joint_two_epoch_packet as helper,replay_single_pass_packet as known
    need=base.need;digest=lambda raw:sha256(raw).hexdigest()
    def bootstrap():
        prior=base.bootstrap();names=('scripts/replay_opponent_role_epoch.py','scripts/run_opponent_role_epoch_study.py',
                                    'scripts/build_opponent_role_epoch.py')
        need(not base.git('status','--porcelain','--untracked-files=all','--',*names),'role lease committed replay bootstrap')
        result={}
        for name in names:
            raw=archive.read(ROOT/name);need(digest(raw) in base.variants(base.git('show',prior[0]+':'+name)),
                'role lease current bootstrap raw identity');result[name]=digest(raw)
        return prior,result
    before=bootstrap();need(not any(n=='tests' or n.startswith(('tests.','pokerlab')) for n in sys.modules),'role lease fresh mathematical process')
    def load():return archive.load(packet,helper,pin=PIN,version='opponent-role-epoch',labels=('observations','builds','objects'),
        packager='package_opponent_role_epoch1.py.txt')
    manifest,loaded,pins=load()
    class Objects(helper.GitObjects):
        def __init__(self):super().__init__();self.blobs={}
        def body(self,head,name):
            blob=self.tree(head).get(name);need(blob is not None,'role lease missing original source blob')
            if blob not in self.blobs:self.blobs[blob]=super().body(head,name)
            return self.blobs[blob]
    objects=Objects();authentication={}
    def sources(files,prefix,head,count):
        saved=helper.decode(files[prefix+'/source-identity.json']);hashes=saved['raw_sha256']
        need(saved['head']==head and len(hashes)==count and set(hashes)==set(saved['committed_blobs']) and
             {n[len(prefix+'/source/'):] for n in files if n.startswith(prefix+'/source/')}==set(hashes),'role lease complete original source inventory')
        for name,expected in hashes.items():
            raw=files[prefix+'/source/'+helper.safe_name(name)];blob=objects.tree(head).get(name)
            need(digest(raw)==expected and saved['committed_blobs'][name]==blob and
                 (helper.source_bytes_match(raw,objects.body(head,name),name,blob) or
                  known.HISTORICAL_CHECKOUTS.get(name)==(expected,blob)),'role lease original raw/Git source identity')
        authentication[prefix]={'head':head,'files':len(hashes)};return hashes
    build_files=loaded['builds'];build_hashes=sources(build_files,'build',BUILD,31)
    build_raw=build_files['build/native-exact-build-manifest.json'];build=helper.decode(build_raw)
    need(build['target']=='opponent-role-epoch-controls' and build['contract']=='native-exact-build-v1' and
         build['source_sha256']==build_hashes and 'No complete native sampled traversal' in build['scope'] and
         build_files['logs/opponent-role-epoch-build1.exit'].strip()==b'0','role lease original successful introduced build')
    files=loaded['observations'];reports=[]
    processes,_=helper.process_receipts(files)
    need(set(processes)=={'normal/native','optimized/native'} and all(p['exit']==0 for p in processes.values()),
         'role lease both actual original process exits')
    for mode in ('normal','optimized'):
        hashes=sources(files,mode,ORIGIN,43);invocation=helper.decode(files[mode+'/invocation.json'])
        need(set(build_hashes)<=set(hashes) and all(build_hashes[n]==hashes[n] for n in build_hashes),
             'role lease original study/build source link')
        need(files[mode+'/native-build-manifest.json']==build_raw and invocation=={
            'command':[build['executable']],'executable_sha256':build['executable_sha256'],
            'build_manifest_sha256':digest(build_raw),'stdin_bytes':0,'automatic_retries':0,
            'python_optimized':int(mode=='optimized'),'source_head':ORIGIN} and
            files[mode+'/native/request.bin']==b'' and files[mode+'/native/stderr.bin']==b'',
            'role lease original invocation/executable/empty request identity')
        report=helper.decode(files[mode+'/result.json'])
        need(report['original_receipt']==helper.decode(files[mode+'/native/process.json']) and
             report['source_head']==ORIGIN and report['source_files']==43 and report['native_calls']==1 and
             report['build_manifest_sha256']==digest(build_raw) and report['executable_sha256']==build['executable_sha256'] and
             report['output_sha256']==digest(files[mode+'/native/stdout.bin']) and report['archived_source_executed'] is False,
             'role lease original complete controller outcome');reports.append(report)
    need(files['normal/native/stdout.bin']==files['optimized/native/stdout.bin'],'role lease original full paired-mode byte identity')
    def current_math():
        need(not (ROOT/'tests/__init__.py').exists() and not (ROOT/'scripts/__init__.py').exists() and
             not base.git('status','--porcelain','--untracked-files=all','--',*MATH),'role lease current reference namespace/source')
        result={}
        for name in (*MATH,'scripts/run_opponent_role_epoch_study.py'):
            raw=archive.read(ROOT/name);need(digest(raw) in base.variants(objects.body(ORIGIN,name)),'role lease current reference drift: '+name)
            result[name]=digest(raw)
        return result
    math_before=current_math();previous=sys.pycache_prefix,sys.dont_write_bytecode
    with TemporaryDirectory(prefix='role-epoch-empty-cache-',dir=ROOT.parent) as cache:
        sys.pycache_prefix=cache;sys.dont_write_bytecode=True
        try:
            from tests.opponent_role_epoch_reference import verify
            from scripts.run_opponent_role_epoch_study import mutations
            fresh=verify(files['normal/native/stdout.bin']);changed=mutations(files['normal/native/stdout.bin'],verify)
            for mode,report in zip(('normal','optimized'),reports):
                need(all(report[k]==helper.decode(json.dumps(v).encode()) for k,v in fresh.items()) and report['parser_mutations']==7 and
                     report['mutation_labels']==[label for label,_raw in changed] and
                     {n[len(mode+'/mutations/'):] for n in files if n.startswith(mode+'/mutations/')}=={label+'.bin' for label,_body in changed},
                     'role lease fresh complete arithmetic/guard/resource outcome')
                for label,body in changed:need(files[mode+'/mutations/'+label+'.bin']==body,'role lease original altered-frame input identity')
            for name in MATH:
                module=sys.modules.get(name[:-3].replace('/','.'))
                need(module is not None and Path(module.__file__).resolve()==(ROOT/name).resolve(),'role lease executed current reference identity')
            need(bootstrap()==before and current_math()==math_before and load()[2]==pins,'role lease final source/packet drift')
            return {'status':'shared-store-role-component-replayed','authentication':authentication,'original_native_processes':2,
                'fresh':fresh,'parser_mutations':7,'output_sha256':reports[0]['output_sha256'],'native_calls':0,
                'archived_source_executed':False,'rng_calls':0,'attempted_training':False,'quality_gate':None,
                'stored_expanded_bytes':manifest['stored_expanded_bytes'],
                'scope':'Original scoped role facade synthetic states and ledgers independently replayed after complete source/build/process admission. No archived code, recursive branch proof, sampled whole walk, longer lifetime, speed or quality.'}
        finally:sys.pycache_prefix,sys.dont_write_bytecode=previous


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('packet',nargs='?',type=Path,default=PACKET)
    print(json.dumps(replay(parser.parse_args().packet),indent=2))
