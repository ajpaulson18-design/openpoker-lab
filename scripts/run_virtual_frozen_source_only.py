"""Trusted source-only front door. Launch by absolute path with -I -S -B."""
import argparse,hashlib,importlib.abc,importlib.machinery,json,os,runpy,stat,sys
from pathlib import Path

FIRST_STAGE = "import sys,hashlib\nfrom pathlib import Path\nif not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):raise RuntimeError('isolated first stage required')\np=Path(sys.argv[1]).resolve();expected=sys.argv[2]\nif p.stat().st_size>64*(1<<20):raise RuntimeError('bootstrap size bound')\nwith p.open('rb') as f:raw=f.read(64*(1<<20)+1)\nidentity=hashlib.sha256(raw).hexdigest()\nif len(raw)>64*(1<<20) or identity!=expected:raise RuntimeError('trusted bootstrap byte mismatch')\ncommand=sys.orig_argv[sys.orig_argv.index('-c')+1]\nsys._opl_trusted_first_stage={'bootstrap_path':str(p),'bootstrap_sha256':identity,'command_sha256':hashlib.sha256(command.encode()).hexdigest()}\nsys.argv=[str(p),*sys.argv[3:]]\nexec(compile(raw,str(p),'exec',dont_inherit=True),{'__name__':'__main__','__file__':str(p)})\n"

def source_only_command(script,identity,module,receipt,arguments):
    flags=['-O'] if sys.flags.optimize==1 else ['-OO'] if sys.flags.optimize==2 else []
    return [sys.executable,'-I','-S','-B',*flags,'-c',FIRST_STAGE,str(script),identity,
            '--module',module,'--receipt',str(receipt),'--',*arguments]

MAX_NODES=32768
MAX_FILE=64*(1<<20)

def digest(path):
    if path.stat().st_size>MAX_FILE:raise ValueError('bootstrap input size bound')
    h=hashlib.sha256();total=0
    with path.open('rb') as source:
        while True:
            value=source.read(1<<20)
            if not value:break
            total+=len(value)
            if total>MAX_FILE:raise ValueError('bootstrap input grew past bound')
            h.update(value)
    return h.hexdigest()


def scan_project_caches(root):
    root=Path(root).resolve();pending=[root];nodes=0
    while pending:
        directory=pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if directory==root and entry.name=='.git':continue
                nodes+=1
                if nodes>MAX_NODES:raise ValueError('bootstrap directory inventory bound')
                info=entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&1024:
                    raise ValueError('bootstrap linked/reparse project input')
                if entry.name.lower().endswith(('.pyc','.pyo')):
                    raise ValueError('project bytecode cache rejected before imports')
                if stat.S_ISDIR(info.st_mode):pending.append(Path(entry.path))
    return {'nodes':nodes,'project_bytecode_files':0}


def install_source_loader(root,state):
    root=Path(root).resolve();token=object();state['_token']=token
    class SourceLoader(importlib.machinery.SourceFileLoader):
        _opl_source_token=token
        def get_code(self,fullname):
            path=Path(self.get_filename(fullname))
            logical=Path(os.path.abspath(path))
            if not logical.is_relative_to(root):raise ValueError('project loader path escaped')
            current=root
            for part in logical.relative_to(root).parts:
                current=current/part;info=current.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&1024:
                    raise ValueError('linked project source')
            if path.suffix!='.py' or path.stat().st_size>MAX_FILE:raise ValueError('unsupported project module')
            with path.open('rb') as source:raw=source.read(MAX_FILE+1)
            if len(raw)>MAX_FILE:raise ValueError('project source grew past bound')
            name=logical.relative_to(root).as_posix()
            identity=hashlib.sha256(raw).hexdigest()
            if name in state['compiled'] and state['compiled'][name]!=identity:
                raise ValueError('project source changed across compilation')
            state['compiled'][name]=identity
            return compile(raw,str(path),'exec',dont_inherit=True,optimize=sys.flags.optimize)
    class SourceFinder(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            spec=importlib.machinery.PathFinder.find_spec(fullname,path)
            if spec is not None and spec.origin and Path(os.path.abspath(spec.origin)).is_relative_to(root):
                if Path(spec.origin).suffix!='.py':raise ValueError('project bytecode/extension import rejected')
                spec.loader=SourceLoader(fullname,spec.origin)
                return spec
            return None
    finder=SourceFinder();sys.meta_path.insert(0,finder)
    return finder


def public_receipt(state):
    return {key:value for key,value in state.items() if not key.startswith('_')}


def main():
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise ValueError('source-only bootstrap requires isolated no-site no-cache-write startup')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',choices=['scripts.run_virtual_frozen_update_study','scripts.verify_virtual_frozen_update_study','scripts.run_native_exact_reach_conformance','scripts.build_native_exact_four_street','unittest'],required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    parser.add_argument('arguments',nargs=argparse.REMAINDER)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    for name,module in tuple(sys.modules.items()):
        filename=getattr(module,'__file__',None)
        if name!='__main__' and filename and Path(filename).resolve().is_relative_to(root):
            raise ValueError('project module imported before bootstrap')
    first=getattr(sys,'_opl_trusted_first_stage',None)
    if (not isinstance(first,dict) or first.get('bootstrap_path')!=str(Path(__file__).resolve()) or
            first.get('command_sha256')!=hashlib.sha256(FIRST_STAGE.encode()).hexdigest()):
        raise ValueError('trusted one-buffer first-stage launch required')
    scan=scan_project_caches(root)
    state={'version':'project-source-only-bootstrap-v1','root':str(root),'entry_module':args.module,
           'compiled':{Path(__file__).relative_to(root).as_posix():first['bootstrap_sha256']},
           'trusted_first_stage':dict(first),
           'interpreter':{'path':str(Path(sys.executable).resolve()),'sha256':digest(Path(sys.executable)),
                          'version':sys.version,'isolated':sys.flags.isolated,'no_site':sys.flags.no_site,
                          'optimize':sys.flags.optimize,'dont_write_bytecode':sys.dont_write_bytecode},
           'initial_cache_scan':scan,'external_runtime_scope':'stdlib/extensions are environmental inputs, not exhaustively byte-attested'}
    sys._opl_source_bootstrap=state
    install_source_loader(root,state);sys.path.insert(0,str(root));os.chdir(root)
    arguments=args.arguments[1:] if args.arguments[:1]==['--'] else args.arguments
    sys.argv=[args.module,*arguments]
    try:runpy.run_module(args.module,run_name='__main__',alter_sys=True)
    finally:
        state['final_cache_scan']=scan_project_caches(root)
        raw=(json.dumps(public_receipt(state),sort_keys=True,indent=2)+'\n').encode()
        if len(raw)>1<<20:raise ValueError('bootstrap receipt size bound')
        with args.receipt.open('xb') as output:output.write(raw)

if __name__=='__main__':main()
