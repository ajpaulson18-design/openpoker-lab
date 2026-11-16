"""Run the frozen dealt PROOF9 quality cohort and retain every policy."""
import argparse
import json
from pathlib import Path
import subprocess

from tests.test_native_exact_reach import ROOT, authenticate
from tests.test_native_sampled_seeded import CAPTURE_LIMIT, QUALITY_RUNS, replay_saved_policy
from tests.virtual_frozen_run_control import RunClaim, _json_exclusive, run_bounded_child


CASES = tuple(zip(('a32','a128','a512','b128','c128'), QUALITY_RUNS, strict=True))


def _source(expected):
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    clean = not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)
    if head != expected or not clean:
        raise ValueError('quality cohort requires the clean pinned source revision')


def _draws(path):
    with path.open('rb') as source:
        raw = source.read(CAPTURE_LIMIT+1)
    if len(raw) > CAPTURE_LIMIT:
        raise ValueError('quality cohort policy exceeds capture cap')
    return tuple(line.split()[:15] for line in raw.splitlines() if line.startswith(b'DRAW '))


def run(exe, destination, expected):
    _source(expected)
    exe, destination = Path(exe).resolve(), Path(destination).resolve()
    if destination.is_relative_to(ROOT):
        raise ValueError('quality cohort capture must be external to source')
    identity = authenticate(exe,ROOT,'virtual-frozen-update-controls')
    claim = RunClaim(destination,expected)
    outcomes = {}
    for label,(seed,draws) in CASES:
        _source(expected)
        directory = destination / label
        try:
            child = run_bounded_child([str(exe),f'sampled-grid-quality-{label}'],b'',directory,
                                      stdout_limit=CAPTURE_LIMIT,timeout=90)
            if (not child['actual_exit_observed'] or child['returncode'] or child['failures'] or
                    child['automatic_retries'] or child['streams'][1]['saved_bytes']):
                raise ValueError('quality cohort native child failed')
            if identity != authenticate(exe,ROOT,'virtual-frozen-update-controls'):
                raise ValueError('quality cohort native identity changed')
            print(json.dumps({'case':label,'phase':'native_exited','seed':seed,'draws':draws}),flush=True)
            replay = replay_saved_policy(directory/'stdout.bin', child['streams'][0]['sha256'])
            if (replay['seed'],replay['draws'],replay['native_producer_calls']) != (seed,draws,0):
                raise ValueError('quality cohort replay differs from planned case')
            _json_exclusive(directory/'quality.json',replay)
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
    claim.finish(summary['status'],summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--head',required=True)
    args = parser.parse_args()
    return int(run(args.executable,args.output,args.head)['status']!='complete')


if __name__ == '__main__':
    raise SystemExit(main())
