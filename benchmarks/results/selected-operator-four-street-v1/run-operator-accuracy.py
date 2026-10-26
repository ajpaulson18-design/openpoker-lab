import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path.cwd()))
from scripts.benchmark_selected_operator import _identity, _write, verify_saved

out = Path('../accuracy-t1000-v1').resolve()
if out.exists():
    raise ValueError('Fresh directory required; no retry')
source = _identity()
if source['status']:
    raise ValueError('Clean source required')
out.mkdir()
_write(out / 'source.json', source)
_write(out / 'experiment.json', {
    'source_commit': source['commit'], 'iterations': 1000,
    'algorithm': 'cfrplus', 'calls': {'reference': 1, 'operator': 1},
    'traced': False, 'retries': 0, 'target_big_blinds': '1/1000',
    'case': 'benchmarks/four-street-integration-v1.json',
    'orchestrator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'scope': 'Additional fixed-budget accuracy comparison; single-call timing is descriptive.'})
for backend in ('reference', 'operator'):
    process = subprocess.run([sys.executable, '-B', '-m', 'scripts.benchmark_selected_operator',
                              '--child', backend, '--iterations', '1000'],
                             capture_output=True, text=True, check=True)
    raw = process.stdout.encode()
    (out / (backend + '-0.json')).write_bytes(raw)
    row = json.loads(raw)
    print(backend, row['seconds'], row['payload']['nash_conv'], flush=True)
if _identity() != source:
    raise ValueError('Source changed during calls')
manifest = {'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in out.iterdir() if p.is_file()}}
_write(out / 'manifest.json', manifest)
digest = hashlib.sha256((out / 'manifest.json').read_bytes()).hexdigest()
result = verify_saved(out, digest)
print(json.dumps({'manifest_sha256': digest, 'targets': [a['exact_target_met'] for a in result['audits']]}))
