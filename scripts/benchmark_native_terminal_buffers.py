"""Reproduce the frozen ten-card comparison of prepared Chance output ownership."""
from argparse import ArgumentParser
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time

from tests.test_native_exact_reach import authenticate

HEAD = 'e47e6ca67a7fc620dedded481f13bd3cb388da94'
TARGETS = {
    "baseline": "virtual-dyadic-training-staged-pages",
    "buffer": "virtual-dyadic-training-terminal-buffer",
}


def verify_source(root):
    head = subprocess.check_output(['git','rev-parse','HEAD'],text=True,cwd=root).strip()
    clean = not subprocess.check_output(['git','status','--porcelain'],cwd=root)
    if not clean or head!=HEAD:
        raise RuntimeError('benchmark source differs from pinned revision')

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def write(path, data):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        stream.write(json.dumps(data,indent=2,sort_keys=True)+'\n')

def identities(root, executables):
    verify_source(root)
    return {mode:authenticate(exe,root,target) for mode,(exe,target) in executables.items()}

def run(root, reference, capture, baseline, candidate):
    executables = {"baseline": (baseline, TARGETS["baseline"]),
                   "buffer": (candidate, TARGETS["buffer"])}
    initial = identities(root, executables)
    archive = root / "benchmarks/results/native-dyadic-staged-pages-v1"
    saved = json.loads((archive/'timing.json').read_bytes())['warmup']['reuse']
    previous = json.loads((archive/'protocol.json').read_bytes())
    wanted_wire = saved['wire_sha256']
    if sha(reference/'stdout.bin')!=wanted_wire:
        raise RuntimeError('staged-page reference wire differs')
    stable = dict(previous['stable_sidecars'])
    paging = 'page-images/paging.json'
    if json.loads((reference/paging).read_bytes())!=saved['pager']:
        raise RuntimeError('staged-page reference pager differs')
    stable[paging] = sha(reference/paging)
    if any(sha(reference/name)!=digest for name,digest in stable.items()):
        raise RuntimeError('staged-page reference sidecars differ')
    capture.mkdir()
    protocol = {'source_head':HEAD,'warmup_pairs':1,'alternating_pairs':8,
        'median_ratio_max':0.96,'candidate_faster_pairs_min':6,'wire_bytes':saved['wire_bytes'],
        'expected_wire_sha256':wanted_wire,'expected_sidecar_sha256':stable,
        'baseline':'staged-page build of the exact same source','candidate':'staged pages with caller-owned Chance outputs',
        'workload':'ten-card T2 bounded division standard compact wire', 'one_host':True}
    write(capture/'protocol.json',protocol)
    def call(label, mode):
        out=capture/label
        out.mkdir()
        exe=executables[mode][0]
        wire=out/'stdout.bin'
        error=out/'stderr.bin'
        start=time.perf_counter()
        with wire.open('xb') as stdout,error.open('xb') as stderr:
            child=subprocess.Popen([str(exe),str(out/'page-images')],stdin=subprocess.PIPE,
                stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW,cwd=root)
            try:
                child.communicate(b'DYADIC_T2_V1 TRAIN_TEN_BOUNDED_DIVISION\n',timeout=45)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=10)
        elapsed=time.perf_counter()-start
        record={'mode':mode,'duration_seconds':elapsed,'actual_exit_observed':True,
                'returncode':child.returncode,'wire_sha256':sha(wire),
                'wire_bytes':wire.stat().st_size,'stderr_bytes':error.stat().st_size}
        write(out/'process.json',record)
        if child.returncode or record['stderr_bytes'] or (record['wire_sha256'],record['wire_bytes'])!=(wanted_wire,protocol['wire_bytes']):
            raise RuntimeError('native wire or process parity failed: '+label)
        if any(sha(out/name)!=digest for name,digest in stable.items()):
            raise RuntimeError('exact checkpoint, policy, pager or directory sidecar differs: '+label)
        return record
    warmup=[call('warm-baseline','baseline'),call('warm-buffer','buffer')]
    print('warmup complete, full wire and sidecar parity',flush=True)
    pairs=[]
    for index in range(1,9):
        order=('baseline','buffer') if index%2 else ('buffer','baseline')
        observations={mode:call(f'{index:02}-{mode}',mode) for mode in order}
        ratio=observations['buffer']['duration_seconds']/observations['baseline']['duration_seconds']
        pairs.append({'index':index,'order':order,'observations':observations,'ratio':ratio})
        print(json.dumps({'pair':index,'order':order,'ratio':ratio}),flush=True)
    if identities(root, executables)!=initial:
        raise RuntimeError('native input identity drift')
    ratios=[pair['ratio'] for pair in pairs]
    median=statistics.median(ratios)
    faster=sum(n<1 for n in ratios)
    result={'status':'complete','median_ratio':median,'faster_pairs':faster,'pairs':pairs,'warmup':warmup,
            'gate_passed':median<=protocol['median_ratio_max'] and faster>=protocol['candidate_faster_pairs_min'],
            'native_builds':{key:{field:identity[1][field] for field in
                                ('target','compiler_sha256','executable_sha256','source_sha256')}
                             for key,identity in initial.items()}}
    write(capture/'terminal.json',result)
    print(json.dumps({key:result[key] for key in ('status','median_ratio','faster_pairs','gate_passed')}),flush=True)


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    root, reference, output = args.source.resolve(), args.reference.resolve(), args.output.resolve()
    if output.is_relative_to(root):
        parser.error("capture must be external to the pinned source")
    run(root, reference, output, args.baseline.resolve(), args.candidate.resolve())
