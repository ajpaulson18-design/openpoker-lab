"""Authenticate saved sparse-epoch executions before independent exact replay.

The candidate and archived Python are evidence only and never executed here.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from scripts.replay_native_frozen_policy_state import bounded, read_json, require
from scripts.replay_native_grid_raw import MATH, CONTROLLERS, sources, process

NEW_MATH = ('tests/virtual_sparse_epoch_reference.py', 'tests/virtual_sparse_two_epoch_reference.py',
            'tests/virtual_sparse_two_epoch_forecast_reference.py',
            'tests/virtual_native_sparse_two_epoch_reference.py')
NEW_CONTROL = ('tests/test_native_sparse_two_epoch.py', 'scripts/replay_sparse_two_epoch.py',
               'scripts/replay_native_grid_raw.py')


def replay(directory):
    directory = Path(directory)
    native = read_json(directory / 'native-build-manifest.json')
    identity = read_json(directory / 'native-identity.json')
    require(native['target'] == 'virtual-sparse-two-epoch', 'sparse saved native target')
    require(identity == {'manifest_sha256': sha256(bounded(directory / 'native-build-manifest.json', 1 << 20)).hexdigest(),
                         'executable_sha256': native['executable_sha256']}, 'sparse saved build identity')

    def authenticate():
        return sources(directory, native, math_sources=(*MATH, *NEW_MATH),
                       controllers=(*CONTROLLERS, *NEW_CONTROL), version='native-sparse-two-epoch-sources-v1',
                       bootstrap=('scripts/replay_sparse_two_epoch.py', 'scripts/replay_native_grid_raw.py',
                                  'scripts/replay_native_frozen_policy_state.py'))

    saved, before = authenticate()
    from tests.test_native_sparse_two_epoch import selectors, SCOPE
    from tests.virtual_dyadic_training_reference import Fixture
    from tests.virtual_grid_update_reference import build_sampled_reference_context
    from tests.virtual_sparse_two_epoch_forecast_reference import forecast
    from tests.virtual_native_sparse_two_epoch_reference import verify_sparse_wire
    require(native['scope'] == SCOPE, 'sparse native scope')
    fixture = Fixture()
    context = build_sampled_reference_context()
    plan = selectors(fixture, context)
    saved_plan = read_json(directory / 'case-plan.json')
    expected_plan = json.loads(json.dumps(plan))
    budget = forecast()
    require(saved_plan == json.loads(json.dumps({'scope': SCOPE, 'cases': expected_plan, 'automatic_retries': 0,
                           'per_request_forecast': budget, 'native_requests': len(plan),
                           'sum_request_work_forecasts': len(plan) * budget['components']['total_work']})),
            'sparse complete independently bounded experiment plan')
    results = []
    digests = {}
    for label, pair in plan:
        args = read_json(directory / (label + '.command.json'))
        expected_args = [native['executable'], *[value for board in pair for value in ('uniform', *map(str, board))]]
        require(args == expected_args, 'sparse saved complete request')
        child = directory / label
        raw = process(child, 0)
        result = verify_sparse_wire(fixture, context, pair, raw)
        require(read_json(child / 'independent-rows.json') == json.loads(json.dumps(result)), 'sparse saved row report')
        results.append({'case': label, **result})
        digests[label] = sha256(raw).hexdigest()
    good = read_json(directory / (plan[0][0] + '.command.json'))
    invalid = {
        'reject-second-law': good[:7] + ['river_weighted', *good[8:]],
        'reject-second-duplicate': good[:-1] + [good[-2]],
        'reject-second-foreign': good[:8] + ['0', *good[9:]],
        'reject-second-unsorted': good[:8] + [good[9], good[8], *good[10:]],
        'reject-arity': good[:-1], 'reject-third-selector': good + good[1:7],
        'reject-negative-card': good[:2] + ['-1', *good[3:]],
    }
    for label, expected_args in invalid.items():
        require(read_json(directory / (label + '.command.json')) == expected_args, 'sparse saved rejection request')
        process(directory / label, 2)
    expected = {'status': 'all-two-epoch-rows-exact', 'cases': results,
                'successful_observed_requests': len(plan), 'rejected_observed_requests': len(invalid),
                'epochs_per_request': 2, 'rng_calls': 0, 'scope': SCOPE}
    require(read_json(directory / 'matrix-results.json') == json.loads(json.dumps(expected)), 'sparse saved matrix report')
    require(authenticate() == (saved, before), 'sparse replay source drift')
    return {**expected, 'candidate_calls': 0, 'archived_source_executed': False,
            'observed_source_head': saved['head'], 'active_source_sha256': before, 'stdout_sha256': digests,
            'invocation_receipts': 'saved controller commands and observed exits/streams; no independent syscall attestation'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    print(json.dumps(replay(parser.parse_args().directory), indent=2))
