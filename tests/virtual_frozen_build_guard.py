"""Authenticate a fresh explicit probe build against frozen source and headers."""
from pathlib import Path
import hashlib,json
from scripts.build_native_exact_four_street import TARGETS


def file_hash(path,limit=64*(1<<20)):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>limit:
        raise ValueError('build input file bound/link')
    h=hashlib.sha256();total=0
    with path.open('rb') as source:
        while True:
            block=source.read(1<<20)
            if not block:break
            total+=len(block)
            if total>limit:raise ValueError('build input grew past bound')
            h.update(block)
    return h.hexdigest()


def authenticate_build(repo,directory,source_receipt):
    repo=Path(repo).resolve();directory=Path(directory).resolve()
    manifest_path=directory/'native-exact-build-manifest.json'
    if manifest_path.stat().st_size>65536:raise ValueError('build manifest byte bound')
    raw=manifest_path.read_bytes();manifest=json.loads(raw)
    if manifest.get('contract')!='native-exact-build-v1' or manifest.get('target')!='virtual-frozen-update':
        raise ValueError('wrong native proof build')
    names={*TARGETS['virtual-frozen-update'][1],'scripts/build_native_exact_four_street.py',
           'third_party/boost-multiprecision-1.92.0/manifest.json',
           'third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt',
           'third_party/boost-multiprecision-1.92.0/headers.zip'}
    if set(manifest['source_sha256'])!=names:raise ValueError('compiled source closure mismatch')
    for name in names:
        expected=source_receipt['files'].get(name)
        if expected is None or expected['raw_sha256']!=manifest['source_sha256'][name] or file_hash(repo/name)!=expected['raw_sha256']:
            raise ValueError('compiled source differs from frozen raw source: '+name)
    dependency=json.loads((repo/'third_party/boost-multiprecision-1.92.0/manifest.json').read_bytes())
    if manifest['dependency_headers']!=198 or len(dependency['headers_sha256'])!=198:
        raise ValueError('actual dependency closure mismatch')
    for name,expected in dependency['headers_sha256'].items():
        path=(directory/'boost-include'/name).resolve()
        if not path.is_relative_to(directory/'boost-include') or file_hash(path,2*(1<<20))!=expected:
            raise ValueError('actual extracted header drift')
    executable=Path(manifest['executable']).resolve()
    if executable.parent!=directory or not executable.name.startswith('native-virtual-frozen-update-probe'):
        raise ValueError('unexpected native executable path')
    if file_hash(executable)!=manifest['executable_sha256']:raise ValueError('native executable drift')
    compiler=Path(manifest['compiler']).resolve()
    if 'compiler_sha256' not in manifest or file_hash(compiler)!=manifest['compiler_sha256']:
        raise ValueError('actual compiler identity missing or changed')
    return {'manifest_sha256':hashlib.sha256(raw).hexdigest(),'sources':manifest['source_sha256'],
            'headers':198,'executable':str(executable),'executable_sha256':manifest['executable_sha256'],
            'compiler':str(compiler),'compiler_sha256':manifest['compiler_sha256'],
            'scope':'declared project sources, vendored headers, compiler and observed binary; system SDK/standard headers, linker/libraries/runtime are not exhaustively byte-attested; bit reproducibility unproven'}
