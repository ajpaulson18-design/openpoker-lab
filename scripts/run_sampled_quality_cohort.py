"""Run the frozen dealt PROOF9 quality cohort and retain every policy."""
import argparse
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from tests.test_native_exact_reach import ROOT, authenticate
from tests.test_native_sampled_seeded import CAPTURE_LIMIT, QUALITY_RUNS, replay_saved_policy
from tests.virtual_frozen_run_control import RunClaim, _json_exclusive, run_bounded_child


CASES = tuple(zip(('a32','a128','a512','b128','c128'), QUALITY_RUNS, strict=True))
MATCHED_BASELINE = ROOT / 'benchmarks/results/native-sampled-proof9-quality-cohort-v1'


def _source(expected):
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    clean = not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)
    if head != expected or not clean:
        raise ValueError('quality cohort requires the clean pinned source revision')


def _draws(path, expected_sha256=None):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path,'rb') as source:
        raw = source.read(CAPTURE_LIMIT+1)
    if len(raw) > CAPTURE_LIMIT:
        raise ValueError('quality cohort policy exceeds capture cap')
    if expected_sha256 is not None and hashlib.sha256(raw).hexdigest()!=expected_sha256:
        raise ValueError('matched archived policy digest differs')
    return tuple(line.split()[:15] for line in raw.splitlines() if line.startswith(b'DRAW '))


def _matched(label, directory, replay, expected):
    baseline = MATCHED_BASELINE / label
    before = json.loads((baseline/'quality.json').read_bytes())
    if (before['seed'],before['draws'],before['raw_sha256'])!=(replay['seed'],replay['draws'],expected):
        raise ValueError('matched archived case identity differs')
    first = _draws(baseline/'policy.bin.gz',expected)
    second = _draws(directory/'stdout.bin',replay['raw_sha256'])
    if len(first)!=replay['draws'] or first!=second:
        raise ValueError('linear averaging did not preserve the physical deal schedule')
    base = before['quality']['exploitability']
    candidate = replay['quality']['exploitability']
    difference = (Fraction(int(candidate['numerator']),int(candidate['denominator'])) -
                  Fraction(int(base['numerator']),int(base['denominator'])))
    return {'draw_schedule_equal':True,'baseline_sha256':expected,'baseline_exploitability':base,
            'linear_minus_equal':{'numerator':str(difference.numerator),'denominator':str(difference.denominator)}}


def run(exe, destination, expected, *, linear=False):
    _source(expected)
    exe, destination = Path(exe).resolve(), Path(destination).resolve()
    if destination.is_relative_to(ROOT):
        raise ValueError('quality cohort capture must be external to source')
    identity = authenticate(exe,ROOT,'virtual-frozen-update-controls')
    baseline_hashes = {}
    if linear:
        manifest = json.loads((MATCHED_BASELINE/'manifest.json').read_bytes())
        baseline_hashes = {case['case']:case['raw_policy_sha256'] for case in manifest['cases']}
        if baseline_hashes.keys() != {label for label,_ in CASES}:
            raise ValueError('matched archived case inventory differs')
    claim = RunClaim(destination,expected)
    outcomes = {}
    for label,(seed,draws) in CASES:
        _source(expected)
        directory = destination / label
        try:
            command = [str(exe),f'sampled-grid-quality-{label}']
            if linear:
                command.append('--linear')
            child = run_bounded_child(command,b'',directory,stdout_limit=CAPTURE_LIMIT,timeout=90)
            if (not child['actual_exit_observed'] or child['returncode'] or child['failures'] or
                    child['automatic_retries'] or child['streams'][1]['saved_bytes']):
                raise ValueError('quality cohort native child failed')
            if identity != authenticate(exe,ROOT,'virtual-frozen-update-controls'):
                raise ValueError('quality cohort native identity changed')
            print(json.dumps({'case':label,'phase':'native_exited','seed':seed,'draws':draws}),flush=True)
            replay = replay_saved_policy(directory/'stdout.bin', child['streams'][0]['sha256'])
            if (replay['seed'],replay['draws'],replay['native_producer_calls']) != (seed,draws,0):
                raise ValueError('quality cohort replay differs from planned case')
            if (replay.get('averaging')=='linear') != linear:
                raise ValueError('quality cohort averaging strategy differs')
            _json_exclusive(directory/'quality.json',replay)
            if linear:
                _json_exclusive(directory/'matched.json',_matched(label,directory,replay,baseline_hashes[label]))
            outcomes[label] = {'status':replay['status'],'quality_gate':replay['quality_gate'],
                               'exploitability':replay['quality']['exploitability'],
                               'saved_rows':replay['saved_rows'],'sha256':replay['raw_sha256']}
        except (ValueError, OSError, ArithmeticError, StopIteration) as error:
            outcomes[label] = {'status':'failed','error':str(error)[:4096]}
        print(json.dumps({'case':label,**outcomes[label]},sort_keys=True),flush=True)
    _source(expected)
    if identity != authenticate(exe,ROOT,'virtual-frozen-update-controls'):
        raise ValueError('final quality cohort native identity changed')
    previous = tuple(_draws(destination/label/'stdout.bin') for label in ('a32','a128','a512')
                     if outcomes[label]['status'] != 'failed')
    prefix_parity = (len(previous)==3 and previous[0]==previous[1][:32] and
                     previous[1]==previous[2][:128])
    complete = all(record['status']!='failed' for record in outcomes.values()) and prefix_parity
    summary = {'status':'complete' if complete else 'failed','source_head':expected,
               'prefix_parity':prefix_parity,'cases':outcomes}
    if linear:
        summary['averaging'] = 'linear'
    claim.finish(summary['status'],summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--head',required=True)
    parser.add_argument('--linear',action='store_true')
    args = parser.parse_args()
    return int(run(args.executable,args.output,args.head,linear=args.linear)['status']!='complete')


if __name__ == '__main__':
    raise SystemExit(main())
