"""Emit one bounded research moment frame and supported transcript witnesses."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]


def emit(index,witness_path,summary_path):
    from tests.virtual_opponent_action_worlds import WIRE_LIMIT,SIDE_LIMIT,SUMMARY_LIMIT,run_case,require
    witness_path=Path(witness_path).resolve();summary_path=Path(summary_path).resolve()
    directory=witness_path.parent
    require(directory==summary_path.parent and directory.is_dir() and not directory.is_symlink() and
            ROOT.parent in directory.parents and ROOT not in directory.parents and directory!=ROOT,
            'moment external evidence directory')
    require(not witness_path.exists() and not summary_path.exists(),'moment exclusive side outputs')
    wire,report,_visibility,side=run_case(index)
    report={**report,'wire_bytes':len(wire),'wire_sha256':sha256(wire).hexdigest(),
            'witness_bytes':len(side),'witness_sha256':sha256(side).hexdigest()}
    summary=(json.dumps(report,indent=2)+'\n').encode()
    require(len(wire)<=WIRE_LIMIT and len(side)<=SIDE_LIMIT and len(summary)<=SUMMARY_LIMIT,'moment complete I/O caps')
    with witness_path.open('xb') as output:output.write(side)
    with summary_path.open('xb') as output:output.write(summary)
    sys.stdout.buffer.write(wire);sys.stdout.buffer.flush()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',type=int,required=True)
    parser.add_argument('--witness-output',type=Path,required=True);parser.add_argument('--summary-output',type=Path,required=True)
    args=parser.parse_args();emit(args.case,args.witness_output,args.summary_output)
