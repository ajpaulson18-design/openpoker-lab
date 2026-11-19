"""Replay immutable V2 evidence; V1 remains superseded and is never executed."""
import json
from pathlib import Path

from scripts.replay_frozen_grid_envelope import replay
from scripts.replay_native_policy_packet import replay_packet

ROOT=Path(__file__).resolve().parents[1]


def replay_envelope_packet():
    result=replay_packet(packet=ROOT/'benchmarks/results/frozen-grid-update-envelope-v2/verification.zip',
        archive_sha='dce1e6d5f59773d3e540c1f365664af88e1bf43edd7e44ebb6db4cc42392f4ac',
        archive_bytes=4_081_505,member_count=262,case_replay=replay)
    return {**result,'status':'provisional-envelope-packet-replayed','update_admitted':False,
            'scope':'V2 architecture equations only; no raw-update producer, training or quality acceptance'}


if __name__=='__main__':print(json.dumps(replay_envelope_packet(),indent=2))
