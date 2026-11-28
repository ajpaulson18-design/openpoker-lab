"""Authenticate saved catalog controls and replay current independent rules."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from scripts.replay_native_frozen_policy_state import ORACLE_SOURCES,bounded,read_json,require
from scripts.replay_native_grid_raw import process,sources

MATH=(*ORACLE_SOURCES,'tests/virtual_strategy_catalog_reference.py')
CONTROLLERS=('tests/test_native_strategy_catalog.py',)
BOOTSTRAP=('scripts/replay_strategy_catalog.py','scripts/replay_native_grid_raw.py',
           'scripts/replay_native_frozen_policy_state.py')


def replay(directory):
    directory=Path(directory);native=read_json(directory/'native-build-manifest.json')
    require(native['target']=='virtual-strategy-catalog-controls' and native['scope']==
        'Sparse full-history strategy catalog identity/menu controls only; no policies, numerical state, training or wider physical support.',
        'catalog explicit native target/scope')
    require(read_json(directory/'native-identity.json')=={
        'manifest_sha256':sha256(bounded(directory/'native-build-manifest.json',1<<20)).hexdigest(),
        'executable_sha256':native['executable_sha256']},'catalog observed build identity')
    def identity():return sources(directory,native,math_sources=MATH,controllers=CONTROLLERS,
        version='native-strategy-catalog-sources-v1',bootstrap=BOOTSTRAP)
    saved,before=identity()
    command=read_json(directory/'command.json')
    require(command==[native['executable']],'catalog captured controller invocation')
    raw=process(directory/'process',0);require(len(raw)<=65536,'catalog output byte ceiling')
    # Archived source is never imported. Current numerical modules are loaded
    # only after their full committed-source closure has been authenticated.
    from tests.virtual_dyadic_training_reference import Fixture
    from tests.virtual_strategy_catalog_reference import parse_catalog_wire
    result=parse_catalog_wire(raw,Fixture())
    require(json.loads(json.dumps(result))==read_json(directory/'independent-replay.json'),
            'catalog independently recounted saved summary')
    require(identity()==(saved,before),'catalog source changed during replay')
    return {'status':'catalog-identities-and-guards-exact','result':result,
        'observed_source_head':saved['head'],'active_python_sha256':before,
        'candidate_calls':0,'archived_source_executed':False,
        'scope':'identity/menu/component-bound controls only; no policies, learning, physical-range support or wider admission',
        'invocation_receipts':'controller command and exit/stream observations; not independent syscall attestations'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path)
    print(json.dumps(replay(parser.parse_args().directory),indent=2))
