"""Measure a bounded 12-river repeat with both full 1,326-holding ranges."""
from argparse import ArgumentParser
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

from tests.test_native_exact_reach import authenticate
from tests.virtual_frozen_run_control import run_bounded_child

HEAD='8987e610b1ea6c90addb73f51ad53fd645fd55d8'
KEYS=('modeled_work','input_work','contraction_work','peak_live_entries','peak_integer_payload_bits',
      'rank_calls','contractions','prepared_families','prepared_showdowns')


def separate_wire(raw):
    numeric, separator, ledger = raw.rpartition(b'\nWORK ')
    if not separator or len(ledger.split())!=len(KEYS) or numeric.count(b'\n')!=24:
        raise ValueError('wide study wire framing differs')
    return numeric+b'\n',dict(zip(KEYS,map(int,ledger.split()),strict=True))


def run(root, exe, out):
    def verify():
        if (subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()!=HEAD or
                subprocess.check_output(['git','status','--porcelain'],cwd=root)):
            raise ValueError('wide study requires the frozen source')
        return authenticate(exe,root,'prepared-public-chance-controls')

    def save(path, value):
        with path.open('x',encoding='utf8',newline='\n') as stream:
            stream.write(json.dumps(value,indent=2,sort_keys=True)+'\n')

    identity=verify()
    out.mkdir()
    protocol={'source_head':HEAD,'timed_pairs':8,'warmup_pairs':1,'median_ratio_max':0.96,
              'candidate_faster_pairs_min':6,'holdings_per_seat':1326,'rivers':list(range(12)),
              'fixed_turn':[17,24,33,35],'groups':16,'reach_exponent':212,'contractions':384,
              'scope':'exact component calls on one host, with one full 24-vector capture per child'}
    save(out/'protocol.json',protocol)
    same_output=None

    def invoke(label,mode):
        nonlocal same_output
        case=out/label
        record=run_bounded_child([str(exe),f'wide-reach-{mode}'],b'',case,stdout_limit=2_100_000,timeout=60)
        if not record['actual_exit_observed'] or record['returncode'] or record['failures'] or record['streams'][1]['saved_bytes']:
            raise ValueError(f'wide study process failed: {label} {(case/"stderr.bin").read_bytes()!r}')
        values,ledger=separate_wire((case/'stdout.bin').read_bytes())
        if same_output is None:
            same_output=values
        if values!=same_output:
            raise ValueError('wide per-row exact output differs: '+label)
        if (ledger['rank_calls']!=25944 or ledger['contractions']!=384 or
                (ledger['prepared_families'],ledger['prepared_showdowns'])!=((16,384) if mode=='reuse' else (0,0)) or
                ledger['modeled_work']>500_000_000):
            raise ValueError('wide scope or work cap differs: '+label)
        return {'duration_seconds':record['duration_seconds'],'work':ledger,
                'raw_sha256':record['streams'][0]['sha256'],'actual_exit_observed':True}

    warmup={mode:invoke(f'warm-{mode}',mode) for mode in ('baseline','reuse')}
    with (out/'numerical.bin').open('xb') as stream:
        stream.write(same_output)
    print(json.dumps({'warmup':warmup}),flush=True)
    pairs=[]
    for index in range(1,9):
        order=('baseline','reuse') if index%2 else ('reuse','baseline')
        observed={mode:invoke(f'{index:02}-{mode}',mode) for mode in order}
        if any(observed[mode]['work']!=warmup[mode]['work'] or
               observed[mode]['raw_sha256']!=warmup[mode]['raw_sha256'] for mode in order):
            raise ValueError('wide repeated receipt or output differs')
        ratio=observed['reuse']['duration_seconds']/observed['baseline']['duration_seconds']
        pairs.append({'pair':index,'order':order,'observations':observed,'elapsed_ratio':ratio})
        print(json.dumps({'pair':index,'ratio':ratio}),flush=True)
    ratios=[pair['elapsed_ratio'] for pair in pairs]
    median=statistics.median(ratios)
    faster=sum(ratio<1 for ratio in ratios)
    if verify()!=identity:
        raise ValueError('component source identity changed')
    terminal={'status':'complete','warmup':warmup,'pairs':pairs,'median_elapsed_ratio':median,
              'faster_pairs':faster,'gate_passed':median<=0.96 and faster>=6,
              'numerical_sha256':hashlib.sha256(same_output).hexdigest(),
              'native_build':{key:identity[1][key] for key in
                              ('target','compiler_sha256','executable_sha256','source_sha256')}}
    save(out/'terminal.json',terminal)
    print(json.dumps({key:terminal[key] for key in ('status','median_elapsed_ratio','faster_pairs','gate_passed')}),flush=True)


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__)
    for arg in ('source','executable','output'):
        parser.add_argument('--'+arg,type=Path,required=True)
    options=parser.parse_args()
    if options.output.resolve().is_relative_to(options.source.resolve()):
        parser.error('capture must remain external to source')
    run(options.source.resolve(),options.executable.resolve(),options.output.resolve())
