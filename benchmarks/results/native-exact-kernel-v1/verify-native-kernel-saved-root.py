"""Re-authenticate the frozen native kernel and recheck saved vectors only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

WORK = Path(__file__).resolve().parent
ROOT = WORK / 'native-exact-kernel-repo'
STUDY = WORK / 'native-exact-kernel-study-v1'

def need(condition, message):
    if not condition:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def module(name, path, expected):
    need(sha(path.read_bytes()) == expected, 'review helper byte drift')
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

review = module('kernel_frozen_review', WORK / 'native-exact-kernel-study.py',
    '2d885c0ce48eaa953e2d127caaeb31e35651d3fc11e1c20b86bd6301726a02b8')
auth = module('kernel_full_auth', WORK / 'exact-selected-independent-review.py', review.AUTH_SHA)
auth.FROZEN = review.FROZEN
before = review.source_snapshot(ROOT)
need(before == json.loads((STUDY / 'source-before.json').read_bytes()), 'source differs from frozen capture')
authenticated = auth.source_identity(ROOT, before)
archive = WORK / 'native-exact-kernel-study-v1.zip'
need(sha(archive.read_bytes()) == '2a8ce2f33e718490e36342af961deea31fd61f64da40e9fd68fcfe764952ae7b', 'archive drift')
manifest_raw = (STUDY / 'manifest.json').read_bytes()
need(sha(manifest_raw) == 'e55f61cad93ee17cd91561ff873839f19ccb5d761d73ca064d9e6881c42c1d1f', 'manifest drift')
manifest = json.loads(manifest_raw)
with zipfile.ZipFile(archive) as packed:
    need(packed.read('manifest.json') == manifest_raw and len(packed.namelist()) == len(manifest['sha256']) + 1, 'archive inventory mismatch')
    for name, expected in manifest['sha256'].items():
        need(sha(packed.read(name)) == expected and sha((STUDY / name).read_bytes()) == expected, 'saved bytes changed: ' + name)

# Project mathematics is imported only after the complete committed source and
# every saved artifact have been authenticated. Archived source is never run.
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from tests import test_native_exact_selected_vectors as oracle
cases = review.schedule()
records = 0
with review.oracle_guard():
    for case in cases:
        directory = STUDY / 'cases' / case['id']
        parsed = review.parse_saved_wire((directory / 'input.txt').read_bytes())
        need(json.loads(json.dumps(parsed)) == json.loads(json.dumps({
            key: case[key] for key in ('hands', 'boards', 'queries', 'cache')})), 'wire/spec mismatch')
        expected = review.expectation(parsed, oracle)
        need(expected == json.loads((directory / 'expected.json').read_bytes()), 'exact targets changed')
        review.check_stdout((directory / 'stdout.txt').read_bytes(), expected)
        need((directory / 'stderr.txt').read_bytes() == b'' and
            json.loads((directory / 'status.json').read_bytes()) == {'returncode': 0, 'candidate_invocations': 1}, 'saved process failed')
        records += len(expected['vectors'])
need(review.source_snapshot(ROOT) == before and auth.source_identity(ROOT, before) == authenticated, 'source drift after replay')
receipt = {'source_commit': review.FROZEN, 'authenticated_files': authenticated['files'],
    'archive_entries': len(manifest['sha256']) + 1, 'cases': len(cases), 'vector_records': records,
    'candidate_invocations': 0, 'production_kernel_rank_training_calls': 0,
    'all_saved_bits_support_Z_scales_match': True, 'source_unchanged': True,
    'scope': 'Root independently rechecks the saved formal vector archive using the unchanged physical Fraction/best-five oracle; no second mathematical implementation, native execution or full-game claim.'}
(WORK / 'native-exact-kernel-root-saved-receipt.json').write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps(receipt, sort_keys=True))
