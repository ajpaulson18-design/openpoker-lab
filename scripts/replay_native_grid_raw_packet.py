"""Replay immutable normal/optimized raw matrices with current independent math."""
from hashlib import sha256
import json
from pathlib import Path

from scripts.replay_native_frozen_policy_state import bounded,read_json,require
from scripts.replay_native_grid_raw import replay
from scripts.replay_native_policy_packet import replay_packet

ROOT=Path(__file__).resolve().parents[1]
PINS={
    'normal':('527f77a5bbce5faf365b16c89006a865ea792f2289534907b2a23aed1df3d9b2',4_606_322),
    'optimized':('6039823ffa32b1f1c930895d94f5d0eb5bb2fe8c69e6fa5519e8d576b012199b',4_606_418),
}


def replay_case(directory):
    native=read_json(directory/'native-build-manifest.json')
    executable=directory.parent/'build'/Path(native['executable'].replace('\\','/')).name
    require(sha256(bounded(executable,8<<20)).hexdigest()==native['executable_sha256'],
            'raw archived executable byte identity')
    return replay(directory)


def replay_raw_packets():
    results={}
    for mode,(digest,size) in PINS.items():
        results[mode]=replay_packet(
            packet=ROOT/('benchmarks/results/native-frozen-grid-raw-v1/'+mode+'.zip'),
            archive_sha=digest,archive_bytes=size,member_count=234,case_replay=replay_case,
            extract_prefixes=('matrix/','build/'),case_directories=('matrix',))
    normal=results['normal']['results'][0]['cases']
    optimized=results['optimized']['results'][0]['cases']
    require(normal==optimized,'raw normal/optimized independent replay parity')
    return {'status':'all-raw-rows-exact','modes':results,'candidate_calls':0,
            'archived_source_executed':False,
            'scope':'fixed-policy raw arithmetic only; no State update, training, quality or wider admission'}


if __name__=='__main__':print(json.dumps(replay_raw_packets(),indent=2))
