"""Read-only archive byte/provenance audit; executes no archived project code."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

work = Path(__file__).resolve().parent
archive_path = work / 'matrix-free-certificate-evidence-v1.zip'
package = json.loads((work / 'matrix-free-certificate-package-v1.json').read_bytes())
def sha(raw): return hashlib.sha256(raw).hexdigest()
def require(condition,message):
    if not condition: raise ValueError(message)
raw = archive_path.read_bytes()
require(sha(raw) == package['sha256'] and len(raw) == package['bytes'], 'outer archive hash/size')
with zipfile.ZipFile(archive_path) as archive:
    names = archive.namelist()
    require(len(names) == len(set(names)) == package['entries'], 'archive duplicate/count')
    require(all(not n.startswith(('/', '\\')) and '..' not in Path(n).parts and '\\' not in n for n in names), 'unsafe archive member')
    members = {n:archive.read(n) for n in names}
require(sha(members['manifest.json']) == package['manifest_sha256'], 'inner manifest hash')
manifest = json.loads(members['manifest.json'])
require(set(members) == set(manifest['files']) | {'manifest.json'} and
    all(sha(members[n]) == h for n,h in manifest['files'].items()), 'inner complete byte manifest')
def evidence(directory,name): return members['evidence/'+directory+'/'+name]
def parse(directory,name): return json.loads(evidence(directory,name))
study = 'matrix-free-certificate-study-v1'
review = 'matrix-free-certificate-independent-review-v1'
source = parse(study,'source-before.json')
require(source == parse(study,'source-after.json') and source['commit'] == package['source_commit'] and
    source['commit'] == manifest['source_commit'] and not source['status'], 'source closure/freeze')
require(set(source['tree_blob_oid']) == set(source['git_normalized_blob_oid']) == set(source['sha256']), 'source identity keyset')
repo = work / 'matrix-free-certificate-repo'
def git(*args, data=None):
    return subprocess.check_output(['git','-C',str(repo),*args],input=data)
require(git('rev-parse','HEAD').decode().strip() == source['commit'] and
    not git('status','--porcelain','--untracked-files=all').strip(), 'live frozen source commit/status')
tree = {}
for item in git('ls-tree','-rz','--full-tree',source['commit']).split(b'\0')[:-1]:
    metadata,name = item.split(b'\t',1)
    mode,kind,oid = metadata.split()
    require(mode in (b'100644',b'100755') and kind == b'blob', 'nonordinary committed source')
    tree[name.decode()] = oid.decode('ascii')
require(tree == source['tree_blob_oid'], 'pinned committed tree map')
names = list(source['sha256'])
normalized = git('hash-object','--stdin-paths',data=('\n'.join(names)+'\n').encode()).decode('ascii').splitlines()
require(len(normalized) == len(names) and dict(zip(names,normalized)) == source['git_normalized_blob_oid'],
    'recomputed normalized source object map')
raw_identity_fallbacks = []
for name, expected in source['sha256'].items():
    path = work / 'matrix-free-certificate-repo' / name
    source_raw = path.read_bytes()
    require(sha(source_raw) == expected, 'frozen raw source drift: '+name)
    tree_oid = source['tree_blob_oid'][name]
    raw_oid = hashlib.sha1(b'blob '+str(len(source_raw)).encode('ascii')+b'\0'+source_raw).hexdigest()
    require(raw_oid == tree_oid or source['git_normalized_blob_oid'][name] == tree_oid,
        'raw/normalized committed source identity: '+name)
    if source['git_normalized_blob_oid'][name] != tree_oid:
        raw_identity_fallbacks.append(name)
source_names = [n.removeprefix('source/') for n in members if n.startswith('source/')]
require(source_names and all(n in source['sha256'] and sha(members['source/'+n]) == source['sha256'][n]
    for n in source_names), 'archived source raw byte closure')
for name in source['sha256']:
    if name.startswith(('scripts/','pokerlab/','tests/','native/')) and Path(name).suffix in ('.py','.hpp','.cpp'):
        require('source/'+name in members, 'omitted executable math/test source: '+name)
saved_manifest = parse(study,'manifest.json')
actual_saved = {n.removeprefix('evidence/'+study+'/'):r for n,r in members.items() if n.startswith('evidence/'+study+'/')}
require(set(actual_saved) == set(saved_manifest['files']) | {'manifest.json'} and
    all(sha(actual_saved[n]) == h for n,h in saved_manifest['files'].items()), 'study manifest inventory')
captured = parse(study,'capture-time-sha256.json')
# The runner stores the direct filename-to-digest map.
require(type(captured) is dict and captured and all(n in actual_saved and sha(actual_saved[n]) == h
    for n,h in captured.items()), 'capture-time byte pins')
report = parse(study,'report.json')
require(report['failure'] is None and all(report[k] == 28 for k in
    ('records_planned','records_attempted','records_captured')) and not any(report['forbidden_calls'].values()), 'study terminal inventory/calls')
process = 'matrix-free-certificate-study-process-v1'
status = parse(process,'status.json'); request = parse(process,'request.json')
observation = parse(process,'process-observation.json')
require(status['returncode'] == observation['terminal_exit_code'] == 0 and status['retries'] == 0 and
    status['command'] == request['command'] and observation['confirmed_terminal_handle'] and
    request['wrapper_sha256'] == sha(members['helpers/run-matrix-free-saved-study-v1.py']) and
    observation['stdout_sha256'] == sha(evidence(process,'stdout.log')) and
    observation['stderr_sha256'] == sha(evidence(process,'stderr.log')), 'study process binding')
receipts = [json.loads(r) for n,r in members.items() if n.startswith('evidence/'+review+'/') and
            n.endswith('/receipt.json') and json.loads(r).get('status') == 'passed']
require(len(receipts) == 1, 'independent acceptance count')
receipt = receipts[0]
require(receipt['source_commit'] == source['commit'] and receipt['producer_or_candidate_calls'] == 0 and
    receipt['candidate_manifest_sha256'] == sha(actual_saved['manifest.json']) and
    receipt['helper_sha256'] == sha(evidence(review,'review.py')) and
    receipt['terminal_exit_code'] == 0, 'independent review binding')
require(set(receipt['independent_six']) == set(parse(study,'protocol.json')['old_exact_unknown_labels']), 'scalar six-policy inventory')
for label, result in receipt['independent_six'].items():
    require(type(result.get('scalar_sha256')) is str and len(result['scalar_sha256']) == 64, 'missing independent scalar hash')
    matches = [r for n,r in members.items() if n.startswith('evidence/'+review+'/') and n.endswith('/'+label+'-scalar.json')]
    require(len(matches) == 1 and sha(matches[0]) == result['scalar_sha256'], 'independent scalar raw bytes: '+label)
review_request = parse(review,'saved-process-v1/request.json')
review_status = parse(review,'saved-process-v1/status.json')
review_observation = parse(review,'saved-process-v1/process-observation.json')
require(review_observation['terminal_exit_code'] == 0 and review_observation['confirmed_terminal_handle'], 'reviewer outer terminal confirmation')
require(review_status['returncode'] == 0 and review_status['retries'] == review_request['retries'] == 0 and
    review_status['command'] == review_request['command'] and
    review_status['helper_sha256'] == review_request['helper_sha256'] == receipt['helper_sha256'] and
    review_status['helper_sha256_after'] == review_status['expected_helper_sha256'] == receipt['helper_sha256'] and
    review_request['expected_helper_sha256'] == receipt['helper_sha256'] and review_status['error'] is None and
    review_status['request_sha256'] == sha(evidence(review,'saved-process-v1/request.json')) and
    review_status['wrapper_sha256'] == review_request['wrapper_sha256'] == sha(evidence(review,'run-review-v1.py')) and
    review_status['receipt_sha256'] == sha(next(r for n,r in members.items() if n.startswith('evidence/'+review+'/') and
        n.endswith('/receipt.json') and json.loads(r).get('status') == 'passed')) and
    review_status['stdout_sha256'] == sha(evidence(review,'saved-process-v1/stdout.log')) and
    review_status['stderr_sha256'] == sha(evidence(review,'saved-process-v1/stderr.log')),
    'actual independent reviewer process binding')
require(sha(members['original-evidence/native-fold-classes-evidence-v1.zip']) ==
    'f0a840055b9a9ebabb0909a8dd92a1c855531ab568b64e7fe57b725329c70f88', 'accepted original archive')
result = {'status':'passed','archive_sha256':package['sha256'],'manifest_sha256':package['manifest_sha256'],
    'source_commit':source['commit'],'members':len(members),'archived_source_files':len(source_names),
    'study_records':len(report['records']),'candidate_complete':report['candidate_complete'],
    'candidate_resource_unverified':report['candidate_resource_unverified'],
    'independent_receipt_sha256':sha(next(r for n,r in members.items() if n.startswith('evidence/'+review+'/') and
        n.endswith('/receipt.json') and json.loads(r).get('status') == 'passed')),
    'auditor_sha256':sha(Path(__file__).read_bytes()),'archived_source_executed':False}
result['raw_committed_identity_fallbacks'] = raw_identity_fallbacks
result['initial_auditor_failure_preserved'] = 'matrix-free-certificate-archive-audit-first-failure-v1.json'
result['pinned_tree_and_normalized_maps_recomputed'] = True
with (work / 'matrix-free-certificate-archive-audit-v2.json').open('x') as stream:
    json.dump(result,stream,indent=2);stream.write('\n')
print(json.dumps(result),flush=True)
