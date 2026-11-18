"""Replay the immutable native policy packet with current independent code.

This maintained entrypoint reads archived source only as evidence. It never
imports extracted files, launches a candidate or changes the Python import path.
"""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from scripts.replay_native_frozen_policy_state import bounded,relative_name,replay,require,unique

ROOT=Path(__file__).resolve().parents[1]
PACKET=ROOT/'benchmarks/results/native-frozen-policy-state-v1/verification.zip'
ARCHIVE_SHA='ecb72cd2bcbcdb1fb7089da6401ae558a4d71855daefdda86828b7c3817fbdd5'


def replay_packet():
    raw=bounded(PACKET,8<<20)
    require(len(raw)==7_733_361 and sha256(raw).hexdigest()==ARCHIVE_SHA,'immutable native policy archive drift')
    # The file is immutable and has already been byte authenticated. Reopen and
    # recheck it afterwards as a separate source-drift guard.
    with TemporaryDirectory(dir=ROOT.parent) as temporary,zipfile.ZipFile(PACKET) as archive:
        names=archive.namelist()
        require(len(names)==len(set(names))==408,'native packet member census')
        for name in names:relative_name(name)
        require(sum(i.file_size for i in archive.infolist())<=80<<20,'native packet expanded byte ceiling')
        index=json.loads(archive.read('members.json'),object_pairs_hook=unique)
        require(set(index)==set(names)-{'members.json'},'native packet complete member identity')
        destination=Path(temporary)
        for name in names:
            with archive.open(name) as source:body=source.read((8<<20)+1)
            require(len(body)<=8<<20,'native packet member byte ceiling')
            if name in index:
                require(index[name]=={'bytes':len(body),'sha256':sha256(body).hexdigest()},'native packet member drift')
            if name.startswith('formal/'):
                target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('xb') as output:output.write(body)
        results=[replay(destination/'formal'/mode) for mode in ('normal','optimized')]
    require(sha256(bounded(PACKET,8<<20)).hexdigest()==ARCHIVE_SHA,'native packet changed during replay')
    return {'status':'exact','archive_sha256':ARCHIVE_SHA,'members_authenticated':408,
            'candidate_calls':0,'archived_source_executed':False,'results':results}


if __name__=='__main__':print(json.dumps(replay_packet(),indent=2))
