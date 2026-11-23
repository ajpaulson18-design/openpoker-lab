"""Authenticate saved joint observations before importing independent math.

The native executable and archived Python remain evidence; neither is executed.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from scripts.replay_native_frozen_policy_state import bounded, read_json, require
from scripts.replay_native_grid_raw import MATH, CONTROLLERS, sources, process

TARGET = 'virtual-joint-two-epoch'
SCOPE = 'Deterministic PROOF9 two-joint-observation sparse signed-regret epochs only; no RNG, convergence, solved quality or full-range admission.'
SOURCE_VERSION = 'native-joint-two-epoch-sources-v1'
NEW_MATH = ('tests/virtual_joint_sample_reference.py', 'tests/virtual_joint_two_epoch_reference.py',
            'tests/virtual_joint_two_epoch_forecast_reference.py', 'tests/virtual_sparse_epoch_reference.py',
            'tests/virtual_target_board_reference.py', 'tests/virtual_native_joint_two_epoch_reference.py')
NEW_CONTROL = ('tests/test_joint_sample_reference.py', 'tests/test_joint_two_epoch_reference.py',
               'tests/test_native_joint_two_epoch.py', 'scripts/replay_joint_two_epoch.py',
               'scripts/replay_native_grid_raw.py')
MATH_SOURCES = tuple(dict.fromkeys((*MATH, *NEW_MATH)))
CONTROL_SOURCES = tuple(dict.fromkeys((*CONTROLLERS, *NEW_CONTROL)))


def selectors():
    return (('different-pairs', ((0, 0), (11, 0))), ('reversed', ((11, 0), (0, 0))),
            ('same-world', ((0, 0), (0, 0))), ('equivalent-tickets', ((0, 0), (2, 0))),
            ('shared-flop-future', ((0, 0), (0, 1))), ('boundaries', ((28, 19), (0, 19))))


def command(executable, pair):
    return [str(executable), *[str(value) for observation in pair for value in observation]]


def invalid_commands(good):
    # Empty argv is not launched: the unchanged bounded observer rejects it
    # before the candidate. '+0' is a real unsigned-parser rejection instead.
    return {'reject-arity': good[:-1], 'reject-ticket-29': [*good[:3], '29', good[4]],
            'reject-rank-20': [*good[:4], '20'], 'reject-negative': [good[0], '-1', *good[2:]],
            'reject-plus-sign': [*good[:4], '+0'], 'reject-too-long': [*good[:4], '000'],
            'reject-letters': [*good[:3], 'xx', good[4]]}


def plan_record(resource):
    return {'scope': SCOPE, 'cases': selectors(), 'automatic_retries': 0,
            'per_request_forecast': resource, 'native_requests': 6, 'rejection_requests': 7,
            'sum_request_work_forecasts': 6 * resource['components']['total_work'],
            'empty_argument_candidate_tested': False,
            'empty_argument_limit': 'Existing bounded observer refuses empty argv before candidate execution.'}


def matrix_record(results):
    return {'status': 'all-joint-two-epoch-rows-exact', 'cases': results,
            'successful_observed_requests': 6, 'rejected_observed_requests': 7,
            'observed_native_invocations': 13, 'epochs_per_request': 2,
            'rng_calls': 0, 'quality_gate': None, 'scope': SCOPE,
            'empty_argument_candidate_tested': False}


def replay(directory):
    directory = Path(directory)
    native = read_json(directory / 'native-build-manifest.json')
    require(native['target'] == TARGET and native['scope'] == SCOPE, 'joint saved target/scope')
    require(read_json(directory / 'native-identity.json') == {
        'manifest_sha256': sha256(bounded(directory / 'native-build-manifest.json', 1 << 20)).hexdigest(),
        'executable_sha256': native['executable_sha256']}, 'joint saved native build identity')

    def authenticate_sources():
        return sources(directory, native, math_sources=MATH_SOURCES, controllers=CONTROL_SOURCES,
                       version=SOURCE_VERSION,
                       bootstrap=('scripts/replay_joint_two_epoch.py', 'scripts/replay_native_grid_raw.py',
                                  'scripts/replay_native_frozen_policy_state.py'))

    saved, before = authenticate_sources()
    # Source authentication above precedes all current oracle/codec imports.
    # Archived source is never placed on sys.path, imported, or executed.
    from tests.virtual_joint_two_epoch_forecast_reference import forecast
    from tests.virtual_native_joint_two_epoch_reference import verify_joint_wire
    resource = forecast()
    require(resource['forecast_passes_caps'], 'joint replay independent whole-domain preflight')
    require(read_json(directory / 'case-plan.json') == json.loads(json.dumps(plan_record(resource))),
            'joint complete fixed matrix plan')
    results = []; digests = {}; first = None
    for label, pair in selectors():
        expected_command = command(native['executable'], pair)
        require(read_json(directory / (label + '.command.json')) == expected_command,
                'joint saved exact candidate argv')
        child = directory / label
        raw = process(child, 0)
        require(len(raw) <= resource['components']['output_bytes'], 'joint saved output byte cap')
        result = verify_joint_wire(pair, raw)
        require(read_json(child / 'independent-rows.json') == json.loads(json.dumps(result)),
                'joint saved independent complete policy report')
        results.append({'case': label, **result}); digests[label] = sha256(raw).hexdigest()
        if first is None:
            first = pair, raw
    for label, expected_command in invalid_commands(command(native['executable'], selectors()[0][1])).items():
        require(read_json(directory / (label + '.command.json')) == expected_command,
                'joint saved real parser rejection argv')
        process(directory / label, 2)
    pair, original = first
    corrupt = bytearray(original); corrupt[336 + 168] ^= 1
    controls = {'corrupt-root': bytes(corrupt), 'corrupt-truncation': original[:-1]}
    expected_controls = []
    for label, changed in controls.items():
        require(bounded(directory / (label + '.bin'), resource['components']['output_bytes']) == changed,
                'joint saved corruption bytes')
        try:
            verify_joint_wire(pair, changed)
        except ValueError:
            expected_controls.append({'case': label, 'status': 'rejected', 'sha256': sha256(changed).hexdigest()})
        else:
            raise ValueError('joint corrupted policy/root accepted')
    require(read_json(directory / 'corruption-controls.json') == expected_controls, 'joint saved corruption control report')
    expected = matrix_record(results)
    require(read_json(directory / 'matrix-results.json') == json.loads(json.dumps(expected)), 'joint saved matrix report')
    require(authenticate_sources() == (saved, before), 'joint saved replay source drift')
    return {**expected, 'candidate_calls': 0, 'archived_source_executed': False,
            'observed_source_head': saved['head'], 'active_source_sha256': before, 'stdout_sha256': digests,
            'invocation_receipts': 'Saved direct controller commands and observed exits/streams; no independent syscall attestation.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    print(json.dumps(replay(parser.parse_args().directory), indent=2))
