"""Explicit source-only build of the independent fixed best-five count reference."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'native/preflop_five_card_reference.c'
PROTOCOL='PREFLOP_FIVE_REFERENCE_V2'

def source_hashes():
    raw=SOURCE.read_bytes()
    return hashlib.sha256(raw).hexdigest(),hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()

def build(output_directory):
    directory=Path(output_directory).resolve()
    if directory==ROOT or ROOT in directory.parents:
        raise ValueError('Reference build must be outside the source checkout')
    compiler=shutil.which('cl' if os.name=='nt' else 'cc')
    if compiler is None:raise RuntimeError('Use an installed compiler environment; no automatic installation')
    compiler=str(Path(compiler).resolve())
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('Use an empty reference build directory; earlier build data is retained')
    directory.mkdir(parents=True,exist_ok=True)
    exe=directory/('preflop-five-reference.exe' if os.name=='nt' else 'preflop-five-reference')
    if exe.exists() or exe.is_symlink() or (directory/'five-reference-manifest.json').exists():
        raise ValueError('Use a fresh reference build directory; existing observations are retained')
    env=os.environ.copy()
    for name in ('CL','_CL_','LINK','_LINK_'):env.pop(name,None)
    if os.name=='nt':
        flags=['/nologo','/std:c11','/O2','/W4','/WX','/MT']
        command=[compiler,*flags,str(SOURCE),'/Fo'+str(directory/'five_reference.obj'),'/Fe'+str(exe)]
        version_command=[compiler]
    else:
        flags=['-std=c11','-O3','-Wall','-Wextra','-Werror','-pedantic']
        command=[compiler,*flags,str(SOURCE),'-o',str(exe)];version_command=[compiler,'--version']
    before=source_hashes()
    version=subprocess.run(version_command,capture_output=True,timeout=30,check=False,env=env)
    completed=subprocess.run(command,capture_output=True,timeout=120,check=False,cwd=directory,env=env)
    if completed.returncode:
        raise RuntimeError('Reference compilation failed: '+(completed.stdout+completed.stderr).decode(errors='replace')[:8192])
    if source_hashes()!=before:raise RuntimeError('Reference source changed during build')
    manifest={'schema_version':1,'protocol':PROTOCOL,'source_sha256':before[0],
              'source_lf_sha256':before[1],'executable':exe.name,
              'executable_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
              'compiler':compiler,'compiler_version':(version.stdout+version.stderr).decode(errors='replace')[:4096],
              'flags':flags,'platform':platform.platform()}
    path=directory/'five-reference-manifest.json'
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(manifest,stream,indent=2,sort_keys=True);stream.write('\n')
    return path

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',required=True)
    args=parser.parse_args();print(build(args.output_dir))
