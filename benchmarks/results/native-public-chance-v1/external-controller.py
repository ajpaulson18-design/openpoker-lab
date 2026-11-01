"""Authenticate the complete committed closure before component mathematics."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

work=Path(__file__).resolve().parent
repo=work/'full-deck-sampling-contract-repo'
out=work/'native-public-chance-frozen-controls-v1'
exe=work/'full-deck-public-chance-luna-v4/probe/native-full-deck-public-chance-probe.exe'
expected='32ddc17409d7e56e012a9d749863af438a79a3d9'
expected_exe='3ca382a6c2b709115513aab01288e614733d77c658f1da5416dc13962a9b69ef'
out.mkdir(exist_ok=False)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def write(name,value):
    with (out/name).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n')
def need(condition,message):
    if not condition:raise ValueError(message)
def git(*args,data=None):
    return subprocess.check_output(['git','-C',str(repo),*args],input=data)
def identity():
    commit=git('rev-parse','HEAD').decode().strip()
    status=git('status','--porcelain','--untracked-files=all').decode().strip()
    need(commit==expected and not status,'require clean exact frozen commit')
    names=git('ls-files','-z').decode().split('\0')[:-1]
    raw={name:sha((repo/name).read_bytes()) for name in names}
    tree={}
    for item in git('ls-tree','-rz','--full-tree',commit).split(b'\0')[:-1]:
        metadata,name=item.split(b'\t',1); mode,kind,oid=metadata.split()
        need(mode in (b'100644',b'100755') and kind==b'blob','nonordinary source')
        tree[name.decode()]=oid.decode()
    need(set(tree)==set(names),'tracked/committed closure differs')
    normalized=git('hash-object','--stdin-paths',data=('\n'.join(names)+'\n').encode()).decode().splitlines()
    need(len(normalized)==len(names),'normalization closure incomplete')
    normalized=dict(zip(names,normalized))
    for name in names:
        value=(repo/name).read_bytes()
        oid=hashlib.sha1(b'blob '+str(len(value)).encode()+b'\0'+value).hexdigest()
        need(sha(value)==raw[name] and (oid==tree[name] or normalized[name]==tree[name]),'source drift: '+name)
    need(git('rev-parse','HEAD').decode().strip()==commit and not git('status','--porcelain').strip(),'source changed during authentication')
    return {'commit':commit,'root':str(repo),'status':status,'closure_count':len(names),
            'sha256':raw,'tree_blob_oid':tree,'git_normalized_blob_oid':normalized}
def build_identity(source):
    manifest_path=exe.with_name('native-exact-build-manifest.json')
    raw=manifest_path.read_bytes(); manifest=json.loads(raw)
    need(manifest['target']=='full-deck-chance' and sha(exe.read_bytes())==manifest['executable_sha256']==expected_exe,'wrong native probe identity')
    for name,digest in manifest['source_sha256'].items():
        need(source['sha256'].get(name)==digest and sha((repo/name).read_bytes())==digest,'compiled source drift: '+name)
    dependency=json.loads((repo/'third_party/boost-multiprecision-1.92.0/manifest.json').read_bytes())
    include=exe.parent/'boost-include'
    actual={p.relative_to(include).as_posix():sha(p.read_bytes()) for p in include.rglob('*') if p.is_file()}
    need(actual==dependency['headers_sha256'] and len(actual)==198,'actual native header closure drift')
    return {'manifest_sha256':sha(raw),'executable_sha256':expected_exe,
        'source_sha256':manifest['source_sha256'],'headers_sha256':actual,'compiler':manifest['compiler'],
        'flags':manifest['flags']}

before=build_before=None; results=[]; failure=None
try:
    before=identity();write('source-before.json',before)
    build_before=build_identity(before);write('build-before.json',build_before)
    write('protocol.json',{'source_commit':expected,'modes':['normal','optimized'],
        'expected_tests_each':18,'expected_skips_each':0,'training_calls':0,
        'scope':'Component law/arithmetic/admission controls only. No sampler/training/full-game quality, speed or RSS result.',
        'source_and_actual_build_authentication_before_project_mathematics':True})
    environment=os.environ.copy();environment['OPENPOKER_NATIVE_FULL_DECK_CHANCE_EXE']=str(exe)
    for name,flags in (('normal',[]),('optimized',['-O'])):
        environment['OPENPOKER_NATIVE_FULL_DECK_CONTROL_DIR']=str(out/('n' if name=='normal' else 'o'))
        command=[sys.executable,'-B',*flags,'-m','unittest','tests.test_build_native_full_deck_public_chance',
                 'tests.test_native_full_deck_public_chance','-v']
        with (out/(name+'.stdout.log')).open('xb') as stdout,(out/(name+'.stderr.log')).open('xb') as stderr:
            child=subprocess.run(command,cwd=repo,env=environment,stdout=stdout,stderr=stderr)
        log=(out/(name+'.stderr.log')).read_text()
        count=re.search(r'Ran (\d+) tests in ([0-9.]+)s',log)
        skips=re.search(r'\(skipped=(\d+)\)',log)
        result={'mode':name,'command':command,'returncode':child.returncode,
            'tests':int(count[1]) if count else None,'seconds':float(count[2]) if count else None,
            'skipped':int(skips[1]) if skips else 0}
        results.append(result);write(name+'-status.json',result)
        need(child.returncode==0 and result['tests']==18 and result['skipped']==0,'component controls failed or skipped')
        need(identity()==before and build_identity(before)==build_before,'source/build drift after mode')
except BaseException as error:
    failure={'type':type(error).__name__,'message':str(error)};write('first-failure.json',failure)
finally:
    try:
        after=identity();write('source-after.json',after)
        if before is not None:need(after==before,'source before/after differs')
        if build_before is not None:
            build_after=build_identity(after);write('build-after.json',build_after)
            need(build_after==build_before,'original probe build drift')
    except BaseException as error:
        write('after-failure.json',{'type':type(error).__name__,'message':str(error)})
        if failure is None:failure={'type':type(error).__name__,'message':str(error)}
    receipt={'source_commit':expected,'results':results,'failure':failure,
        'status':'passed' if failure is None and len(results)==2 else 'failed',
        'scope':'Complete committed raw/Git source and actual build authenticated before component mathematics; not full-deck training/quality.'}
    write('receipt.json',receipt)
    files={p.relative_to(out).as_posix():sha(p.read_bytes()) for p in sorted(out.rglob('*')) if p.is_file()}
    write('manifest.json',{'contract':'native-public-chance-frozen-controls-v1','files':files})
    print(json.dumps(receipt),flush=True)
raise SystemExit(0 if receipt['status']=='passed' else 1)
