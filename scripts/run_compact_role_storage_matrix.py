"""Twelve frozen same-policy compact/canonical storage comparisons."""
import argparse
import json
from pathlib import Path
from scripts.run_frozen_role_walk_matrix import cases
from scripts.run_compact_role_storage_study import run

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('canonical','compact','controls','default','prefix'):p.add_argument(name,type=Path)
    a=p.parse_args();reports=[]
    for label,profile,selectors,rule in cases():
        output=a.prefix.parent/(a.prefix.name+'-'+label)
        result=run(a.canonical,a.compact,a.controls,a.default,output,profile,selectors,rule)
        reports.append({'label':label,'native_calls':result['native_calls'],'coordinates':result['numeric_coordinates_per_representation'],
            'canonical':result['output_sha256']['canonical'],'compact':result['output_sha256']['compact'],
            'storage':{mode:result['reports'][mode]['storage'] for mode in ('canonical','compact')}})
        print(json.dumps(reports[-1]),flush=True)
    print(json.dumps({'cases':len(reports),'native_calls':sum(x['native_calls'] for x in reports),
        'numeric_coordinates_per_representation':sum(x['coordinates'] for x in reports),'quality_gate':None}),flush=True)
