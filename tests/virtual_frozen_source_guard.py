"""Committed full-tree/raw-byte guard for the frozen-update study.

No archived code, filters, solver, compiler or native probe is executed. Git
blobs and working files are streamed; LF bridging is explicit and attribute-
aware. Later rechecks require identical raw bytes, including line endings.
"""
from pathlib import Path,PurePosixPath
import hashlib,os,stat,subprocess,tempfile,threading
from tests.virtual_frozen_whole_study import SOURCE


def _git(repo,args,*,data=None,cap=16*(1<<20),allow_missing=False):
    if data is not None and len(data)>8*(1<<20):raise ValueError('Git metadata input bound')
    with tempfile.TemporaryFile() as input_file:
        if data:input_file.write(data)
        input_file.seek(0)
        process=subprocess.Popen(['git','-c','core.fsmonitor=false',*args],cwd=repo,
                                 stdin=input_file,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        outputs=[bytearray(),bytearray()];overflow=[]
        def drain(pipe,index,limit):
            try:
                while True:
                    chunk=pipe.read(65536)
                    if not chunk:break
                    if len(outputs[index])+len(chunk)>limit:
                        overflow.append(index)
                        if process.poll() is None:process.kill()
                        break
                    outputs[index].extend(chunk)
            finally:pipe.close()
        readers=[threading.Thread(target=drain,args=(process.stdout,0,cap)),
                 threading.Thread(target=drain,args=(process.stderr,1,65536))]
        for thread in readers:thread.start()
        try:returncode=process.wait(timeout=60)
        finally:
            if process.poll() is None:process.kill();process.wait()
            for thread in readers:thread.join()
        if overflow:raise ValueError('Git metadata output bound')
        if returncode and not (allow_missing and returncode==1):
            raise ValueError('Git source metadata failed: '+args[0])
        return bytes(outputs[0])


def _clean(repo):
    if _git(repo,['status','--porcelain=v1','--untracked-files=all']):
        raise ValueError('source checkout must be clean')


def _path(repo,name):
    if (type(name) is not str or not 0<len(name.encode('utf-8'))<=SOURCE['path_bytes'] or
            any(c in name for c in ('\n','\r','\0','\\',':'))):
        raise ValueError('invalid source path')
    parts=PurePosixPath(name)
    if parts.is_absolute() or any(p in ('','..','.') for p in parts.parts):raise ValueError('source path escape')
    current=repo
    for part in parts.parts:
        current=current/part
        meta=current.lstat()
        if stat.S_ISLNK(meta.st_mode) or getattr(meta,'st_file_attributes',0)&1024:
            raise ValueError('linked/reparse source path')
    if not current.resolve().is_relative_to(repo):raise ValueError('resolved source escape')
    return current


def _inventory(repo):
    head=_git(repo,['rev-parse','HEAD']).decode('ascii').strip()
    if len(head) not in (40,64) or any(c not in '0123456789abcdef' for c in head):raise ValueError('invalid committed HEAD')
    tree=_git(repo,['ls-tree','-rz','--full-tree',head])
    entries=tree.split(b'\0')
    if entries[-1:]!=[b''] or len(entries)-1>SOURCE['paths']:raise ValueError('source path count bound')
    files={}
    for raw in entries[:-1]:
        metadata,name=raw.split(b'\t',1);mode,kind,oid=metadata.split()
        if mode not in (b'100644',b'100755') or kind!=b'blob':raise ValueError('unsupported source tree object')
        name=name.decode('utf-8');_path(repo,name)
        if name in files:raise ValueError('duplicate source path')
        files[name]=oid.decode('ascii')
    return head,files


def _attributes(repo,names):
    raw=_git(repo,['check-attr','-z','--stdin','text','eol','filter','working-tree-encoding','ident'],
             data=b''.join(name.encode()+b'\0' for name in names),cap=32*(1<<20))
    parts=raw.split(b'\0');result={name:{} for name in names}
    if parts[-1:]!=[b''] or (len(parts)-1)%3:raise ValueError('invalid Git attribute framing')
    for i in range(0,len(parts)-1,3):
        name,key,value=(p.decode('utf-8') for p in parts[i:i+3])
        if name not in result or key in result[name]:raise ValueError('unexpected Git attribute')
        result[name][key]=value
    for attrs in result.values():
        if set(attrs)!={'text','eol','filter','working-tree-encoding','ident'}:raise ValueError('incomplete Git attributes')
        if any(attrs[k]!='unspecified' for k in ('filter','working-tree-encoding','ident')):
            raise ValueError('unsupported executable/encoding/ident source transform')
    return result


def _raw_file(path,copy_to=None):
    size=path.stat().st_size
    if not 0<=size<=SOURCE['single_file_bytes']:raise ValueError('source file byte bound')
    rawhash=hashlib.sha256();lfhash=hashlib.sha256();total=0;tail=b'';prefix=b''
    output=None
    try:
        if copy_to is not None:
            copy_to.parent.mkdir(parents=True,exist_ok=True);output=copy_to.open('xb')
        with path.open('rb') as source:
            while True:
                chunk=source.read(SOURCE['stream_chunk_bytes'])
                if not chunk:break
                total+=len(chunk)
                if total>size:raise ValueError('source file grew during hashing')
                rawhash.update(chunk)
                if output:output.write(chunk)
                if len(prefix)<8000:prefix+=chunk[:8000-len(prefix)]
                value=tail+chunk;tail=b'\r' if value.endswith(b'\r') else b''
                if tail:value=value[:-1]
                lfhash.update(value.replace(b'\r\n',b'\n'))
        lfhash.update(tail)
        if total!=size or path.stat().st_size!=size:raise ValueError('source file size drift')
    finally:
        if output:output.close()
    return {'bytes':size,'raw_sha256':rawhash.hexdigest(),'lf_sha256':lfhash.hexdigest(),
            'binary_prefix':b'\0' in prefix}


def capture_source(repo,*,snapshot_directory=None):
    repo=Path(repo).resolve(strict=True)
    head,files=_inventory(repo);attrs=_attributes(repo,files);_clean(repo)
    autocrlf=_git(repo,['config','--get','core.autocrlf'],allow_missing=True).strip().lower()
    if autocrlf not in (b'',b'false',b'true',b'input'):raise ValueError('unsupported Git newline configuration')
    destination=None
    if snapshot_directory is not None:
        destination=Path(snapshot_directory).resolve()
        if destination.is_relative_to(repo):raise ValueError('source snapshot must be external')
        destination.mkdir(parents=True,exist_ok=False)
    total=0;records={}
    with tempfile.TemporaryFile() as errors:
        process=subprocess.Popen(['git','-c','core.fsmonitor=false','cat-file','--batch'],cwd=repo,stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,stderr=errors)
        def stop():
            if process.poll() is None:process.kill()
        watchdog=threading.Timer(180,stop);watchdog.start()
        try:
            for name,oid in files.items():
                path=_path(repo,name)
                if total+path.stat().st_size>SOURCE['total_bytes']:raise ValueError('complete source byte bound')
                record=_raw_file(path,None if destination is None else destination/name)
                total+=record['bytes']
                process.stdin.write((head+':'+name+'\n').encode());process.stdin.flush()
                header=process.stdout.readline(256)
                fields=header.rstrip(b'\n').split()
                if len(fields)!=3 or fields[0].decode()!=oid or fields[1]!=b'blob' or not fields[2].isdigit() or len(fields[2])>10:
                    raise ValueError('invalid committed source response')
                size=int(fields[2])
                if size>SOURCE['single_file_bytes']:raise ValueError('committed file byte bound')
                content=hashlib.sha256();object_hash=hashlib.new('sha1' if len(oid)==40 else 'sha256')
                object_hash.update(b'blob '+str(size).encode()+b'\0');remaining=size
                while remaining:
                    chunk=process.stdout.read(min(remaining,SOURCE['stream_chunk_bytes']))
                    if not chunk:raise ValueError('truncated committed source')
                    remaining-=len(chunk);content.update(chunk);object_hash.update(chunk)
                if process.stdout.read(1)!=b'\n' or object_hash.hexdigest()!=oid:
                    raise ValueError('committed source identity mismatch')
                digest=content.hexdigest();a=attrs[name]
                text=(a['text']=='set' or a['eol'] in ('lf','crlf') or
                      (a['text']!='unset' and (a['text']=='auto' or autocrlf in (b'true',b'input')) and not record['binary_prefix']))
                bridge='raw' if digest==record['raw_sha256'] else 'explicit_lf' if text and digest==record['lf_sha256'] else None
                if bridge is None:raise ValueError('working bytes differ from committed source: '+name)
                records[name]={**record,'git_oid':oid,'committed_sha256':digest,'bridge':bridge,'attributes':a}
            process.stdin.close()
            if process.stdout.read(1):raise ValueError('unexpected committed source tail')
            if process.wait(timeout=30):raise ValueError('Git source stream failed')
            if errors.tell():raise ValueError('Git source stream diagnostics')
        finally:
            watchdog.cancel()
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close()
            if not process.stdin.closed:process.stdin.close()
    after_head,after_files=_inventory(repo)
    if _attributes(repo,after_files)!=attrs:raise ValueError('Git source attributes changed')
    _clean(repo)
    if after_head!=head or after_files!=files:raise ValueError('source tree changed during authentication')
    return {'version':'virtual-frozen-source-guard-v1','head':head,'files':records,'bytes':total,
            'limits':dict(SOURCE),'git_autocrlf':autocrlf.decode(),'scope':'full committed tree plus exact raw checkout; no execution validation'}


def verify_source(repo,receipt):
    repo=Path(repo).resolve(strict=True);head,files=_inventory(repo)
    if receipt.get('version')!='virtual-frozen-source-guard-v1' or head!=receipt['head'] or set(files)!=set(receipt['files']):
        raise ValueError('frozen source cohort changed')
    attrs=_attributes(repo,files)
    if any(attrs[name]!=receipt['files'][name]['attributes'] for name in files):
        raise ValueError('source attributes changed')
    _clean(repo)
    if _git(repo,['config','--get','core.autocrlf'],allow_missing=True).strip().lower().decode()!=receipt['git_autocrlf']:
        raise ValueError('Git newline configuration changed')
    total=0
    for name,oid in files.items():
        expected=receipt['files'][name]
        if oid!=expected['git_oid']:raise ValueError('committed object drift')
        actual=_raw_file(_path(repo,name));total+=actual['bytes']
        if total>SOURCE['total_bytes'] or any(actual[k]!=expected[k] for k in actual):
            raise ValueError('raw frozen source drift: '+name)
    final_head,final_files=_inventory(repo)
    if _attributes(repo,final_files)!=attrs:raise ValueError('source attributes changed during recheck')
    _clean(repo)
    if head!=final_head or files!=final_files or total!=receipt['bytes']:raise ValueError('source recheck tree/size drift')
    return {'head':head,'files':len(files),'bytes':total,'raw_bytes_identical':True}
