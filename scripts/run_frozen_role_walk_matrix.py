"""Twelve established full1326 worlds with deterministic role-ticket transcripts."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from scripts.run_frozen_role_walk_study import run


def cases():
    for profile,normalizer in enumerate((1624350,25908876)):
        loss=4 if profile else 1;win=1966603 if profile else 124950
        for label,selectors,rule in (
            ('same-world',((0,0),(0,0)),'first'),
            ('boundaries',((normalizer-1,34246079),(0,0)),'last'),
            ('shared-flop-future',((0,0),(0,1)),'middle'),
            ('sb-loss',((loss,0),(loss,0)),'alternating'),
            ('sb-win',((win,0),(win,0)),'middle'),
            ('shared-board-distinct-holding',((0,2140425),(loss,2140425)),'alternating')):
            yield f'profile-{profile}-{label}',profile,selectors,rule


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('executable',type=Path);p.add_argument('controls',type=Path)
    p.add_argument('prefix',type=Path);a=p.parse_args();reports=[]
    # Each request independently admits and captures its complete sources,
    # retains every child exit, and rejects directory reuse. Stop on first miss.
    for label,profile,selectors,rule in cases():
        output=a.prefix.parent/(a.prefix.name+'-'+label)
        result=run(a.executable,a.controls,output,profile,selectors,rule)
        reports.append({'label':label,'output_sha256':result['output_sha256'],'coordinates':result['all_numeric_coordinates'],
            'rows':result['raw_rows'],'retained':result['retained_rows'],'native_calls':result['native_calls'],
            'result_sha256':sha256((output/'result.json').read_bytes()).hexdigest()})
        print(json.dumps(reports[-1]),flush=True)
    print(json.dumps({'cases':12,'native_calls':sum(x['native_calls'] for x in reports),
        'numeric_coordinates':sum(x['coordinates'] for x in reports),'quality_gate':None}),flush=True)
