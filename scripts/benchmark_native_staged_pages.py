"""Reproduce the frozen ten-card staged-page benchmark on Windows."""
from argparse import ArgumentParser
from pathlib import Path
import hashlib
import json
import statistics
import struct
import subprocess
import time

from tests.test_native_exact_reach import authenticate

CANDIDATE_HEAD = '35c216bee267406a854fc87b350ec5821fe949fd'
BASELINE_HEAD = '53a4072c3bd055e1fca9b787556da170af3c3c6d'


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-source", type=Path, required=True)
    parser.add_argument("--candidate-source", type=Path, required=True)
    parser.add_argument("--baseline-executable", type=Path, required=True)
    parser.add_argument("--candidate-executable", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    baseline_source = args.baseline_source.resolve()
    candidate_source = args.candidate_source.resolve()
    base_exe = args.baseline_executable.resolve()
    new_exe = args.candidate_executable.resolve()
    reference = args.reference_dir.resolve()
    out = args.output_dir.resolve()
    if out.is_relative_to(baseline_source) or out.is_relative_to(candidate_source):
        parser.error("capture must be external to both source trees")
    out.mkdir()
    request = (reference/'request.bin').read_bytes()
    reference_wire = reference/'stdout.bin'
    expected_wire_sha = '7fde396c4c2e645087d9fd8abdc373a97a485265bf157e537e3cfd181c538945'
    size = reference_wire.stat().st_size
    footer_bytes = 8+64*8
    workspace_delta = 4*(2*2*119196)+128
    changes = {5:workspace_delta,11:workspace_delta,19:workspace_delta,28:workspace_delta,
               38:128,39:8176,62:128,63:8176}

    def sha(path):
        with path.open('rb') as stream:
            return hashlib.file_digest(stream,'sha256').hexdigest()

    def require_identity(path, expected_head, exe, target):
        if subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip()!=expected_head or subprocess.check_output(['git','status','--porcelain'],cwd=path):
            raise RuntimeError('matched trainer source drift')
        return authenticate(exe,path,target)

    def save(path, record):
        with path.open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(json.dumps(record,indent=2,sort_keys=True)+'\n')

    identities = {
        'baseline':require_identity(baseline_source,BASELINE_HEAD,base_exe,'virtual-dyadic-training'),
        'reuse':require_identity(candidate_source,CANDIDATE_HEAD,new_exe,'virtual-dyadic-training-staged-pages'),
    }
    if sha(reference_wire)!=expected_wire_sha:
        raise ValueError('independently replayed baseline wire has changed')
    stable_sidecars = {
        str(path.relative_to(reference).as_posix()):sha(path)
        for root in ('page-images','page-images-rows')
        for path in (reference/root).iterdir() if path.is_file() and path.name!='paging.json'
    }
    for name in ('compact-wire.json','equal-quantizer.json','factored-execution.json'):
        stable_sidecars[name] = sha(reference/name)
    baseline_pager=json.loads((reference/'page-images/paging.json').read_bytes())
    new_pager={**baseline_pager,'read_words':6115174,'physical_read_requests':1495,
               'physical_write_requests':2390,'cache_hits':baseline_pager['cache_hits']+3,'cache_misses':1495}
    save(out/'protocol.json',{'baseline':BASELINE_HEAD,'candidate':CANDIDATE_HEAD,
         'baseline_wire_sha256':expected_wire_sha,'stable_sidecars':stable_sidecars,'footer_word_delta':changes,
         'median_elapsed_ratio_max':0.96,'candidate_faster_pairs_min':6,'alternating_pairs':8,
         'warmup_pairs':1,'expected_candidate_pager':new_pager,
         'duration_scope':'one complete native child with stdout streamed to file on one host'})

    def invoke(label,mode):
        directory=out/label
        directory.mkdir()
        lhs=directory/'stdout.bin'
        stderr=directory/'stderr.bin'
        exe=base_exe if mode=='baseline' else new_exe
        source=baseline_source if mode=='baseline' else candidate_source
        stamp=time.perf_counter()
        with lhs.open('xb') as stdout,stderr.open('xb') as err:
            child=subprocess.Popen([str(exe),str(directory/'page-images')],stdin=subprocess.PIPE,
                                   stdout=stdout,stderr=err,cwd=source,creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                child.communicate(request,timeout=45)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=10)
        elapsed=time.perf_counter()-stamp
        record={'mode':mode,'duration_seconds':elapsed,'native_returncode':child.returncode,
                'actual_exit_observed':True,'wire_bytes':lhs.stat().st_size,'wire_sha256':sha(lhs)}
        save(directory/'process.json',record)
        if child.returncode or stderr.stat().st_size or lhs.stat().st_size!=size:
            raise ValueError('native training/process artifact failed: '+label)
        if mode=='baseline':
            if record['wire_sha256']!=expected_wire_sha:
                raise ValueError('baseline training stream changed: '+label)
        else:
            with lhs.open('rb') as actual, reference_wire.open('rb') as expected:
                remaining=size-footer_bytes
                while remaining:
                    count=min(remaining,65536)
                    if actual.read(count)!=expected.read(count):
                        raise ValueError('candidate differs before bounded resource footer: '+label)
                    remaining-=count
                candidate_words=struct.unpack('<8s64Q',actual.read(footer_bytes))
                baseline_words=struct.unpack('<8s64Q',expected.read(footer_bytes))
                if candidate_words[0]!=baseline_words[0] or any((x-y)!=changes.get(i,0)
                            for i,(x,y) in enumerate(zip(candidate_words[1:],baseline_words[1:],strict=True))):
                    print('observed footer delta',[(i,x-y) for i,(x,y) in enumerate(
                          zip(candidate_words[1:],baseline_words[1:],strict=True)) if x!=y],flush=True)
                    raise ValueError('candidate differs outside accounted footer deltas: '+label)
        if {name:sha(directory/name) for name in stable_sidecars}!=stable_sidecars:
            raise ValueError('checkpoint, policy or row directory bytes differ: '+label)
        pager=json.loads((directory/'page-images/paging.json').read_bytes())
        if pager!=(baseline_pager if mode=='baseline' else new_pager):
            print('observed pager',json.dumps(pager),flush=True)
            raise ValueError('pager differs from independently projected schedule: '+label)
        record.update({'checkpoint_policy_directory_parity':True,'numeric_stream_parity':True,'pager':pager})
        save(directory/'verified.json',record)
        return record

    warmup={'baseline':invoke('warm-baseline','baseline'),'reuse':invoke('warm-reuse','reuse')}
    print('warmup parity',json.dumps({k:v['duration_seconds'] for k,v in warmup.items()}),flush=True)
    pairs=[]
    for index in range(1,9):
        order=('baseline','reuse') if index%2 else ('reuse','baseline')
        compared={mode:invoke(f'{index:02}-{mode}',mode) for mode in order}
        pair={'pair':index,'order':order,'elapsed_ratio':compared['reuse']['duration_seconds']/compared['baseline']['duration_seconds'],
              'observations':compared}
        pairs.append(pair)
        print(json.dumps({key:pair[key] for key in ('pair','order','elapsed_ratio')}),flush=True)
    if (identities['baseline']!=require_identity(baseline_source,BASELINE_HEAD,base_exe,'virtual-dyadic-training') or
        identities['reuse']!=require_identity(candidate_source,CANDIDATE_HEAD,new_exe,'virtual-dyadic-training-staged-pages')):
        raise ValueError('trainers changed across matched run')
    ratios=[pair['elapsed_ratio'] for pair in pairs]
    median=statistics.median(ratios)
    faster=sum(ratio<1 for ratio in ratios)
    result={'status':'complete','median_elapsed_ratio':median,'faster_pairs':faster,
            'elapsed_gate_passed':median<=0.96 and faster>=6,'pairs':pairs,'warmup':warmup,
            'builds':{label:{k:identity[1][k] for k in ('target','compiler_sha256','executable_sha256','source_sha256')}
                      for label,identity in identities.items()}}
    save(out/'terminal.json',result)
    print(json.dumps({k:result[k] for k in ('status','median_elapsed_ratio','faster_pairs','elapsed_gate_passed')}),flush=True)


if __name__ == "__main__":
    main()
