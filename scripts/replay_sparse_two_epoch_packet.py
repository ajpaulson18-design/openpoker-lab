"""Replay immutable changing-policy observations using authenticated current math."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'benchmarks/results/sparse-two-epoch-v1'
PINS = {
    'normal': ('0f8fb2ebc6a707346996ee7bf9ba73799ba5873c2961e4821bc4969c3fd4d269', 1017982, 146),
    'optimized': ('7250a203c4946f969f70df2e039808044fcdd3171737db988227d9ee211dc1d5', 1017991, 146),
    'development': ('025cb20f121e009db2bf049987147d28f7c3651b09e7029dbcb91c1a1a8a1c0d', 671057, 35),
}
MANIFEST_SHA = '000cd25bded51cf9bccb66a13fed6405b5bd69d3084baaeb551d110b2a7e0b02'
BOOTSTRAP = ('scripts/replay_sparse_two_epoch_packet.py', 'scripts/replay_sparse_two_epoch.py',
             'scripts/replay_native_policy_packet.py', 'scripts/replay_native_grid_raw.py',
             'scripts/replay_native_frozen_policy_state.py')


def authenticate_bootstrap():
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all', '--', *BOOTSTRAP], cwd=ROOT):
        raise ValueError('uncommitted sparse epoch packet bootstrap')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    hashes = {}
    for name in BOOTSTRAP:
        canonical = subprocess.check_output(['git', 'show', head + ':' + name], cwd=ROOT)
        with (ROOT / name).open('rb') as source:
            body = source.read((2 << 20) + 1)
        allowed = (canonical, canonical.replace(b'\n', b'\r\n')) if b'\r' not in canonical else (canonical,)
        if len(body) > 2 << 20 or body not in allowed:
            raise ValueError('sparse packet bootstrap byte drift')
        hashes[name] = sha256(body).hexdigest()
    return {'head': head, 'raw_sha256': hashes}


def replay_packets():
    before = authenticate_bootstrap()
    loaded = [name for name, module in tuple(sys.modules.items()) if name != '__main__' and
              getattr(module, '__file__', None) and ROOT in Path(module.__file__).resolve().parents]
    if loaded:
        raise ValueError('sparse packet replay needs a fresh Python process')
    previous = (sys.pycache_prefix, sys.dont_write_bytecode)
    with TemporaryDirectory(prefix='sparse-whole-current-python-', dir=ROOT.parent) as cache:
        sys.pycache_prefix = cache
        sys.dont_write_bytecode = True
        try:
            from scripts.replay_native_frozen_policy_state import bounded, read_json, require
            from scripts.replay_native_policy_packet import replay_packet
            from scripts.replay_sparse_two_epoch import replay
            manifest_raw = bounded(PACKET / 'manifest.json', 1 << 20)
            require(len(manifest_raw) == 53086 and sha256(manifest_raw).hexdigest() == MANIFEST_SHA,
                    'sparse whole packet manifest pin')
            manifest = read_json(PACKET / 'manifest.json')
            require(manifest['matrix_source_capture_head'] == '41ae6727523abec3044bd32ae93b321d8d2b5bed' and
                    manifest['candidate_build_commit'] == 'b4240aa3f0797426e28f18342e47fb3f864a8f98',
                    'sparse whole captured source pins')

            def whole_case(directory):
                native = bounded(directory / 'native-build-manifest.json', 1 << 20)
                require(native == bounded(directory.parent / 'build/native-exact-build-manifest.json', 1 << 20),
                        'sparse packet run/build metadata agreement')
                return replay(directory)

            def development_case(directory):
                record = read_json(directory / 'source-reconstruction.json')
                require(record == manifest['development_source_reconstruction'] and
                        record['source_commit'] == 'ef1601a8078cd901ea52cc4f7be74de99ec5fb28' and
                        record['original_raw_checkout_attestation'] is False and
                        record['source_file_count'] == len(record['source_files']) == 29,
                        'sparse compile failure provenance')
                tree = {}
                for line in subprocess.check_output(['git', 'ls-tree', '-r', record['source_commit']], cwd=ROOT, text=True).splitlines():
                    metadata, name = line.split('\t', 1)
                    tree[name] = metadata.split()[2]
                for name, identity in record['source_files'].items():
                    body = bounded(directory / 'source' / name, 2 << 20)
                    canonical = subprocess.check_output(['git', 'show', record['source_commit'] + ':' + name], cwd=ROOT)
                    require(body == canonical and len(body) == identity['bytes'] and
                            sha256(body).hexdigest() == identity['sha256'] and tree[name] == identity['git_blob'],
                            'sparse reconstructed committed compile source')
                failure = read_json(directory / 'build-failure.json')
                require(failure['target'] == 'virtual-sparse-two-epoch' and failure['returncode'] == 2,
                        'sparse preserved compile refusal')
                return {'status': 'compile-failure-source-authenticated', 'compiler_returncode': 2,
                        'original_raw_checkout_attestation': False, 'numerical_pass_claimed': False}

            results = {}
            for name, (digest, size, count) in PINS.items():
                record = manifest['archives'][name + '.zip']
                require((record['sha256'], record['bytes'], record['member_count']) == (digest, size, count),
                        'sparse whole manifest/archive pin agreement')
                development = name == 'development'
                results[name] = replay_packet(packet=PACKET / (name + '.zip'), archive_sha=digest,
                                             archive_bytes=size, member_count=count,
                                             extract_prefixes=('development/',) if development else ('matrix/', 'build/'),
                                             case_directories=('development',) if development else ('matrix',),
                                             case_replay=development_case if development else whole_case)
            normal = results['normal']['results'][0]
            optimized = results['optimized']['results'][0]
            require(normal['cases'] == optimized['cases'] and normal['stdout_sha256'] == optimized['stdout_sha256'],
                    'sparse whole cross-mode exact row and stream parity')
            require(authenticate_bootstrap() == before, 'sparse whole bootstrap changed during replay')
            return {'status': 'sparse-two-epoch-packets-exact', 'results': results, 'active_bootstrap': before,
                    'candidate_calls': 0, 'archived_source_executed': False,
                    'binary_claim': manifest['binary_claim'],
                    'scope': manifest['scope'], 'python_imports': 'fresh process and empty bytecode-cache prefix'}
        finally:
            sys.pycache_prefix, sys.dont_write_bytecode = previous


if __name__ == '__main__':
    print(json.dumps(replay_packets(), indent=2))
