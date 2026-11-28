from argparse import ArgumentParser
from hashlib import file_digest
from pathlib import Path
import json
import statistics
import struct
import subprocess
import time

from tests.test_native_exact_reach import authenticate

FROZEN = {
    '78309bcb271e58a4b3acf4855a5e6f30e3c27502': (18140, 95200),
    '8cde31fe7450b6bd5b8b95ab4ad84e7acf5497d2': (1292, 21760),
}
REFERENCE_WIRE = 'bc0496571953a80fd6b1a0f321ed903e11691c5ae5328ed532853ded264ffa49'
TRAIN = b'DYADIC_T2_V1 TRAIN_TEN_BOUNDED_DIVISION\n'
ADMIT = b'DYADIC_T2_V1 ADMIT_TEN_BOUNDED_DIVISION\n'
FIELDS = {
    'chance_forecast': 1, 'chance_actual': 7, 'input_work': 43, 'contraction_work': 47,
    'peak_live_entries': 53, 'peak_integer_payload_bits': 54, 'peak_integer_bits': 55,
}
FOOTER = struct.Struct('<8s64Q')


def sha(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def sealed_write(path, data):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(data, indent=2, sort_keys=True)+'\n')


def compare_wires(reference, candidate, label):
    if reference.stat().st_size != candidate.stat().st_size:
        raise ValueError('complete wire extent differs: '+label)
    remaining = reference.stat().st_size - FOOTER.size
    with reference.open('rb') as first, candidate.open('rb') as second:
        while remaining:
            size = min(remaining, 65536)
            if first.read(size) != second.read(size):
                raise ValueError('exact numerical stream differs: '+label)
            remaining -= size
        old_magic, *old = FOOTER.unpack(first.read(FOOTER.size))
        new_magic, *new = FOOTER.unpack(second.read(FOOTER.size))
    if old_magic != b'OPLDTP02' or new_magic != old_magic:
        raise ValueError('training footer identity differs')
    differences = {index: new[index]-old[index] for index in range(64) if new[index]!=old[index]}
    if set(differences)-set(FIELDS.values()):
        raise ValueError(f'unexpected footer differences in {label}: {differences}')
    if differences.get(7,0) != differences.get(43,0)+differences.get(47,0):
        raise ValueError('Chance delta is not the measured input and contraction delta')
    return ({name: old[index] for name,index in FIELDS.items()},
            {name: new[index] for name,index in FIELDS.items()})


def run(root, baseline, candidate, reference, output):
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    if head not in FROZEN:
        raise ValueError('unknown frozen source')
    executables = {'baseline':(baseline,'virtual-dyadic-training-staged-pages'),
                   'reuse':(candidate,'virtual-dyadic-training-allin-reach')}

    def identity():
        if (subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()!=head or
                subprocess.check_output(['git','status','--porcelain'],cwd=root)):
            raise ValueError('matched run requires the frozen clean source')
        return {name:authenticate(exe,root,target) for name,(exe,target) in executables.items()}

    initial = identity()
    if initial['baseline'][1]['source_sha256'] != initial['reuse'][1]['source_sha256']:
        raise ValueError('matched targets compiled different source bytes')
    reference_wire = reference/'stdout.bin'
    if sha(reference_wire) != REFERENCE_WIRE:
        raise ValueError('archived staged-page reference drift')
    trace = json.loads((root/'benchmarks/results/native-dyadic-staged-pages-v1/protocol.json').read_bytes())
    sidecars = trace['stable_sidecars']
    pager = json.loads((root/'benchmarks/results/native-dyadic-staged-pages-v1/timing.json').read_bytes())
    if json.loads((reference/'page-images/paging.json').read_bytes())!=pager['warmup']['reuse']['pager']:
        raise ValueError('reference pager differs')
    sidecars['page-images/paging.json'] = sha(reference/'page-images/paging.json')
    if any(sha(reference/key)!=expected for key,expected in sidecars.items()):
        raise ValueError('archived sidecar reference drift')
    output.mkdir()

    protocol = {'source_head':head,'reference_wire_sha256':REFERENCE_WIRE,
                'expected_sidecar_sha256':sidecars,'alternating_pairs':8,'warmup_pairs':1,
                'median_elapsed_ratio_max':0.96,'candidate_faster_pairs_min':6,
                'allowed_footer_fields':FIELDS,'scope':'same staged-page source, one Windows host, ten-card T2',
                'expected_early_groups':FROZEN[head][0],'expected_family_showdowns':FROZEN[head][1]}
    sealed_write(output/'protocol.json', protocol)

    admissions = {}
    for label,(exe,_) in executables.items():
        planned = subprocess.run([str(exe)], input=ADMIT, capture_output=True, check=True, timeout=30)
        if planned.stderr:
            raise ValueError('native admission produced stderr')
        admissions[label] = json.loads(planned.stdout)
    sealed_write(output/'admissions.json',admissions)

    def call(label, mode):
        case = output/label
        case.mkdir()
        wire = case/'stdout.bin'
        stderr = case/'stderr.bin'
        exe = executables[mode][0]
        start = time.perf_counter()
        with wire.open('xb') as stdout, stderr.open('xb') as errors:
            child = subprocess.Popen([str(exe),str(case/'page-images')],stdin=subprocess.PIPE,
                                     stdout=stdout,stderr=errors,creationflags=subprocess.CREATE_NO_WINDOW,cwd=root)
            try:
                child.communicate(TRAIN,timeout=45)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=10)
        elapsed = time.perf_counter()-start
        capture = {'native_exit_observed':True,'returncode':child.returncode,'mode':mode,
                   'duration_seconds':elapsed,'wire_bytes':wire.stat().st_size,'wire_sha256':sha(wire)}
        sealed_write(case/'process.json', capture)
        if child.returncode or stderr.stat().st_size:
            raise ValueError(f'{label} did not exit successfully')
        if mode=='baseline' and capture['wire_sha256']!=REFERENCE_WIRE:
            raise ValueError('same-source baseline did not reproduce the archive')
        old,new = compare_wires(reference_wire,wire,label)
        if any(sha(case/name)!=expected for name,expected in sidecars.items()):
            raise ValueError('checkpoint, policy or pager sidecar differs: '+label)
        capture['chance'] = new
        return capture

    warmup={mode:call(f'warm-{mode}',mode) for mode in executables}
    print(json.dumps({'warmup_chance_baseline':warmup['baseline']['chance'],
                      'warmup_chance_reuse':warmup['reuse']['chance']}),flush=True)
    pairs = []
    for i in range(1,9):
        order = ('baseline','reuse') if i%2 else ('reuse','baseline')
        records = {mode:call(f'{i:02}-{mode}',mode) for mode in order}
        if any(record['chance']!=warmup[mode]['chance'] or
               record['wire_sha256']!=warmup[mode]['wire_sha256'] for mode,record in records.items()):
            raise ValueError('complete training outputs drifted between repeats')
        ratio = records['reuse']['duration_seconds']/records['baseline']['duration_seconds']
        pairs.append({'pair':i,'order':order,'observations':records,'ratio':ratio})
        print(json.dumps({'pair':i,'ratio':ratio}),flush=True)
    if identity()!=initial:
        raise ValueError('source or executable identity changed')
    ratios = [pair['ratio'] for pair in pairs]
    median = statistics.median(ratios)
    faster = sum(ratio<1 for ratio in ratios)
    terminal = {'status':'complete','median_elapsed_ratio':median,'faster_pairs':faster,
                'gate_passed':median<=protocol['median_elapsed_ratio_max'] and faster>=protocol['candidate_faster_pairs_min'],
                'warmup':warmup,'pairs':pairs,
                'native_builds':{mode:{name:entry[1][name] for name in
                                 ('target','compiler_sha256','executable_sha256','source_sha256')}
                                 for mode,entry in initial.items()}}
    sealed_write(output/'terminal.json',terminal)
    print(json.dumps({k:terminal[k] for k in ('status','median_elapsed_ratio','faster_pairs','gate_passed')}),flush=True)


if __name__ == '__main__':
    parser = ArgumentParser(description='Match frozen early-all-in reach reuse against the staged-page baseline.')
    for name in ('source','baseline','candidate','reference','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    options = parser.parse_args()
    if options.output.resolve().is_relative_to(options.source.resolve()):
        parser.error('capture must remain external to source')
    run(*(getattr(options,key).resolve() for key in ('source','baseline','candidate','reference','output')))
