"""Explicit source-built training for fixed public trees and hidden pair worlds.

Python retains poker rules, prepared-count provenance and exact diagnostics.
This helper supports only affine fold/showdown payoffs, with no public chance,
locks or arbitrary utility callbacks. It never compiles or falls back implicitly.
"""
from collections.abc import Mapping
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile

from .native_preflop_equity import _json_object, _reject_constant, _sha
from .river_tree import _Action, _Node, _Terminal

SOURCE = Path(__file__).resolve().parents[1] / 'native' / 'fixed_street_train.c'
PROTOCOL = 'OPENPOKER_FIXED_TRAIN_V1'
WORK_MODEL = 'native-fixed-street-work-v1'
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 24 * 1024 * 1024
MAX_NATIVE_HEAP_BYTES = 64 * 1024 * 1024
MAX_NATIVE_WORK = 500_000_000
NATIVE_TIMEOUT_SECONDS = 120
ALGORITHMS = {'vanilla': 0, 'dcfr': 1, 'cfrplus': 2}


def _source_hashes():
    raw = SOURCE.read_bytes()
    return (hashlib.sha256(raw).hexdigest(),
            hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest())


def _real(value, label, *, minimum=None, maximum=None):
    if type(value) not in (int, float):
        raise ValueError(label + ' must be a finite real number')
    try:
        value = float(value)
    except (ValueError, OverflowError):
        raise ValueError(label + ' must be a finite real number') from None
    if not math.isfinite(value):
        raise ValueError(label + ' must be a finite real number')
    if ((minimum is not None and value < minimum)
            or (maximum is not None and value > maximum)):
        raise ValueError(label + ' exceeds the native numeric envelope')
    return value


def admit_native_shape(states, worlds, slots, iterations, algorithm):
    """Reserve the entire wire/heap/loop envelope before flattening or launch.

    Validated arborescences have exactly states-1 action edges. Each scalar
    pass visits every state and has at most four loops over its action edges.
    Eight world-state units cover those loops; 24 slot units per sweep cover
    profiles, delta resets/updates and averaging normalization. Logical units
    and requested native allocations are separate from elapsed time and RSS.
    """
    for value, lower, upper, label in (
            (states, 1, 250_000, 'states'), (worlds, 1, 384, 'worlds'),
            (slots, 0, 1_000_000, 'action slots'),
            (iterations, 1, 10_000, 'iterations')):
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError('Native ' + label + ' exceeds its structural limit')
    if type(algorithm) is not str or algorithm not in ALGORITHMS:
        raise ValueError('Native algorithm must be vanilla, dcfr or cfrplus')
    passes = 3 if algorithm == 'cfrplus' else 1
    # Header/unsigned IDs/16-hex binary64 tokens fit these per-record bounds.
    wire = 256 + 128 * states + 64 * worlds
    # 130 bytes/state cover the C node plus indegree/DFS scratch, 64/world
    # covers its struct, and four double slot arrays are reserved separately.
    # Include the entire static input buffer and a 64 KiB stack/work margin.
    heap = MAX_INPUT_BYTES + 1 + 130 * states + 64 * worlds + 32 * slots + 65_536
    if wire > MAX_INPUT_BYTES or heap > MAX_NATIVE_HEAP_BYTES:
        raise ValueError('Native wire or heap reservation exceeds its byte limit')
    training = iterations * (8 * worlds * states * passes + 24 * slots)
    native_setup = 16 * (states + worlds + slots) + wire
    adapter_setup = 4096 + 256 * (states + worlds + slots)
    total = training + native_setup + adapter_setup
    if total > MAX_NATIVE_WORK:
        raise ValueError('Full requested native training exceeds 500,000,000 modeled loop entries')
    return {'budget_version': 'native-fixed-street-work-v1',
            'requested_iterations': iterations, 'algorithm': algorithm,
            'public_states': states, 'world_rows': worlds,
            'information_action_slots': slots, 'passes_per_iteration': passes,
            'wire_bytes_upper_bound': wire, 'wire_byte_limit': MAX_INPUT_BYTES,
            'native_heap_bytes_upper_bound': heap,
            'native_heap_byte_limit': MAX_NATIVE_HEAP_BYTES,
            'training_loop_entries_upper_bound': training,
            'native_setup_loop_entries_upper_bound': native_setup,
            'python_adapter_loop_entries_upper_bound': adapter_setup,
            'total_loop_entries_upper_bound': total,
            'total_loop_entry_limit': MAX_NATIVE_WORK,
            'scope': 'Full requested native training and Python adapter bookkeeping; '
                     'the calling solver separately retains its historical admission '
                     'and exact Python diagnostics. Logical loop/allocation reservations '
                     'are not runtime, actual allocated Python bytes or process RSS.'}


def validate_backend(training_backend, build_directory):
    if type(training_backend) is not str or training_backend not in ('python', 'native'):
        raise ValueError('Training backend must be python or native')
    if training_backend == 'native' and build_directory is None:
        raise ValueError('An explicit native training build directory is required')
    if training_backend == 'python' and build_directory is not None:
        raise ValueError('A build directory requires native training')


def complete_solve_admission(native, reference_total, reference_training):
    """Retain source/setup/Python diagnostics and replace only trainer work."""
    retained = reference_total - reference_training
    total = retained + native['total_loop_entries_upper_bound']
    if retained < 0 or total > MAX_NATIVE_WORK:
        raise ValueError('Complete native solve exceeds 500,000,000 modeled loop entries')
    return {'budget_version': 'native-fixed-street-complete-solve-v1',
            'native_training_admission': native,
            'retained_reference_nontraining_loop_entries_upper_bound': retained,
            'total_loop_entries_upper_bound': total,
            'total_loop_entry_limit': MAX_NATIVE_WORK,
            'scope': 'Retains all historical source/setup and Python exact diagnostic '
                     'charges, replacing only the Python trainer bound with the native '
                     'trainer and adapter envelope. Historical admission is also required.'}


def _backend(build_directory):
    if build_directory is None:
        raise ValueError('An explicit native training build directory is required')
    directory = Path(build_directory).resolve(strict=True)
    manifest_path = directory / 'native-train-manifest.json'
    if manifest_path.stat().st_size > 32_768:
        raise ValueError('Native training manifest exceeds its size limit')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'),
                          object_pairs_hook=_json_object, parse_constant=_reject_constant)
    keys = {'schema_version', 'protocol', 'work_model', 'source_sha256', 'source_lf_sha256',
            'executable', 'executable_sha256', 'compiler', 'compiler_version',
            'flags', 'platform'}
    if type(manifest) is not dict or set(manifest) != keys:
        raise ValueError('Unsupported native training manifest shape')
    if (type(manifest['schema_version']) is not int or manifest['schema_version'] != 1
            or manifest['protocol'] != PROTOCOL or manifest['work_model'] != WORK_MODEL
            or manifest['executable'] not in ('native-fixed-street-train', 'native-fixed-street-train.exe')):
        raise ValueError('Unsupported native training build identity')
    raw, lf = _source_hashes()
    if manifest['source_sha256'] != raw or manifest['source_lf_sha256'] != lf:
        raise ValueError('Native training source changed; explicitly rebuild')
    if (any(type(manifest[key]) is not str or not manifest[key]
            for key in ('compiler', 'compiler_version', 'platform', 'executable_sha256'))
            or type(manifest['flags']) is not list
            or any(type(flag) is not str for flag in manifest['flags'])):
        raise ValueError('Malformed native training compiler provenance')
    executable = directory / manifest['executable']
    if executable.is_symlink() or not executable.is_file():
        raise ValueError('Native trainer must be a local regular file')
    if _sha(executable) != manifest['executable_sha256']:
        raise ValueError('Native training executable changed since its recorded build')
    return executable, manifest


def _worlds(worlds):
    if type(worlds) not in (list, tuple) or not 1 <= len(worlds) <= 384:
        raise ValueError('Native training needs 1 to 384 fixed weighted worlds')
    active = [set(), set()]
    for world in worlds:
        if type(world) not in (list, tuple) or len(world) != 4:
            raise ValueError('Native worlds contain two hand IDs, mass and signed equity only')
        for player in (0, 1):
            if type(world[player]) is not int or not 0 <= world[player] < 1326:
                raise ValueError('Native private-hand index exceeds physical combo limits')
            active[player].add(world[player])
        if not 0 < _real(world[2], 'World mass', minimum=0, maximum=1):
            raise ValueError('Native world masses must be positive')
        _real(world[3], 'Signed equity', minimum=-1, maximum=1)
    if (any(not 1 <= len(hands) <= 128 for hands in active)
            or abs(math.fsum(world[2] for world in worlds) - 1) > 1e-9):
        raise ValueError('Native worlds exceed active-hand or normalized-mass limits')
    return tuple(tuple(sorted(hands)) for hands in active)


def _affine(node, pot):
    if (type(node) is not _Terminal or node.kind not in ('fold', 'showdown')
            or type(node.contributions) is not tuple or len(node.contributions) != 2):
        raise ValueError('Native training supports exact fixed fold/showdown terminals only')
    committed = [_real(value, 'Contribution', minimum=0, maximum=1e12)
                 for value in node.contributions]
    unit = pot / 2 + min(committed)
    if unit > 1e12:
        raise ValueError('Native terminal utility exceeds 1e12 chips')
    if node.kind == 'fold':
        if type(node.winner) is not int or node.winner not in (0, 1):
            raise ValueError('Native fold terminal must have an explicit player winner')
        return (unit if node.winner == 0 else -unit), 0.0
    if node.winner is not None:
        raise ValueError('Native showdown terminal cannot encode a fixed winner')
    return 0.0, unit


def _walk(root, pot):
    """Bounded validation pass; a second pass flattens only after admission."""
    pending = [(root, 0)]
    seen = set()
    histories = set()
    while pending:
        node, depth = pending.pop()
        if depth > 32 or len(seen) >= 250_000 or id(node) in seen:
            raise ValueError('Native public tree exceeds depth/state limits or is not an arborescence')
        seen.add(id(node))
        if type(node) is _Terminal:
            _affine(node, pot)
        elif type(node) is _Node:
            if (type(node.player) is not int or node.player not in (0, 1)
                    or type(node.actions) is not tuple or not 1 <= len(node.actions) <= 12
                    or type(node.children) is not tuple or len(node.children) != len(node.actions)
                    or type(node.history) is not tuple or len(node.history) > 32
                    or any(type(token) is not str or len(token) > 128 for token in node.history)):
                raise ValueError('Malformed native public decision node')
            identity = (node.player, node.history)
            if identity in histories:
                raise ValueError('Native public decision histories must be unique')
            histories.add(identity)
            for action, child in zip(node.actions, node.children):
                if type(action) is not _Action:
                    raise ValueError('Native decisions require ordinary action records')
                if type(child) is _Node and child.history != node.history + (action.token,):
                    raise ValueError('Native child history does not extend its public action')
            pending.extend((child, depth + 1) for child in reversed(node.children))
        else:
            raise ValueError('Native training rejects chance and callback nodes')
        yield node


def _hex(value):
    return struct.pack('>d', float(value)).hex()


def _decode(token):
    if len(token) != 16 or any(c not in b'0123456789abcdef' for c in token):
        raise ValueError('Malformed native binary64 policy token')
    value = struct.unpack('>d', bytes.fromhex(token.decode('ascii')))[0]
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('Native policy must contain finite probabilities in [0,1]')
    return value


def train_native_fixed_street(root, worlds, infos, iterations, algorithm='cfrplus',
                              *, pot, build_directory):
    """Return average policies and deterministic build/admission provenance.

    Caller-owned table/rule admission must precede this specialized trainer.
    Counts and executable manifests need trusted provenance; identities are not
    authentication. Input, heap and full training caps are checked independently.
    """
    if not isinstance(infos, Mapping):
        raise TypeError('Native information sets must be a mapping')
    if len(infos) > 1_000_000:
        raise ValueError('Native information-set limit exceeded')
    for key, count in infos.items():
        if (type(key) is not tuple or len(key) != 3
                or type(key[0]) is not int or key[0] not in (0, 1)
                or type(key[1]) is not int or not 0 <= key[1] < 1326
                or type(key[2]) is not tuple
                or any(type(token) is not str for token in key[2])
                or type(count) is not int or not 1 <= count <= 12):
            raise ValueError('Malformed native information-set key or action count')
    pot = _real(pot, 'Pot', minimum=0, maximum=1e12)
    active = _worlds(worlds)
    expected_infos = slots = states = 0
    for node in _walk(root, pot):
        states += 1
        if type(node) is _Node:
            expected_infos += len(active[node.player])
            slots += len(active[node.player]) * len(node.actions)
            if slots > 1_000_000:
                raise ValueError('Native information-action slot limit exceeded')
            for hand in active[node.player]:
                key = node.player, hand, node.history
                if (key not in infos or type(infos[key]) is not int
                        or infos[key] != len(node.actions)):
                    raise ValueError('Native policy keys must use only actor, own hand and public history')
    if len(infos) != expected_infos:
        raise ValueError('Native policy keys have missing or extra information sets')
    admission = admit_native_shape(states, len(worlds), slots, iterations, algorithm)
    if not infos:
        return {}, {'backend': 'native-fixed-street-v1', 'execution_skipped': 'no-information-sets',
                    'admission': admission, 'native_world_rows': len(worlds),
                    'scope': 'No training or native process was required; Python evaluates the terminal game.'}
    # No tree/world/wire/policy arrays are flattened until the complete shape
    # envelope above has passed. Original keys remain exclusively in Python.
    nodes = list(_walk(root, pot))
    indices = {id(node): index for index, node in enumerate(nodes)}
    dense = [{hand: index for index, hand in enumerate(hands)} for hands in active]
    lines = [f'{PROTOCOL} {ALGORITHMS[algorithm]} {iterations} {len(active[0])} {len(active[1])} '
             f'{states} {len(worlds)} {slots}']
    policy_rows = []
    for node in nodes:
        if type(node) is _Terminal:
            constant, coefficient = _affine(node, pot)
            lines.append('T ' + _hex(constant) + ' ' + _hex(coefficient))
        else:
            children = ' '.join(str(indices[id(child)]) for child in node.children)
            lines.append(f'D {node.player} {len(node.actions)} ' + children)
            policy_rows.extend(((node.player, hand, node.history), len(node.actions))
                               for hand in active[node.player])
    for h0, h1, mass, sign in worlds:
        lines.append(f'{dense[0][h0]} {dense[1][h1]} {_hex(mass)} {_hex(sign)}')
    request = ('\n'.join(lines) + '\n').encode('ascii')
    if len(request) > admission['wire_bytes_upper_bound']:
        raise AssertionError('Native wire exceeded its admitted envelope')
    executable, manifest = _backend(build_directory)
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        completed = subprocess.run([str(executable)], input=request, stdout=output,
                                   stderr=errors, timeout=NATIVE_TIMEOUT_SECONDS, check=False)
        output.seek(0); payload = output.read(MAX_OUTPUT_BYTES + 1)
        errors.seek(0); error = errors.read(4096)
    if completed.returncode:
        raise RuntimeError(f'Native training failed ({completed.returncode}): '
                           + error.decode('utf-8', errors='replace').strip())
    if len(payload) > MAX_OUTPUT_BYTES:
        raise ValueError('Native training response exceeds its byte limit')
    if _backend(build_directory) != (executable, manifest):
        raise RuntimeError('Native training build identity changed during execution')
    tokens = payload.split()
    if (len(tokens) != slots + 3 or tokens[:2] != [PROTOCOL.encode('ascii'), b'POLICY']
            or tokens[2] != str(slots).encode('ascii')):
        raise ValueError('Native training response has an invalid protocol or slot census')
    probabilities = [_decode(token) for token in tokens[3:]]
    averages = {}
    offset = 0
    for key, count in policy_rows:
        row = probabilities[offset:offset + count]
        if abs(math.fsum(row) - 1) > 1e-9:
            raise ValueError('Native average policy row is not normalized')
        averages[key] = row
        offset += count
    if offset != slots:
        raise AssertionError('Native policy restoration exceeded its slot envelope')
    return averages, {'backend': 'native-fixed-street-v1', 'build': manifest,
                      'admission': admission, 'native_world_rows': len(worlds),
                      'input_sha256': hashlib.sha256(request).hexdigest(),
                      'output_sha256': hashlib.sha256(payload).hexdigest(),
                      'scope': 'Source-built scalar full traversal with hidden pair worlds; '
                               'Python retains poker rules and exact visible-information diagnostics. '
                               'Build identities and structural checks are not authentication; '
                               'native heap reservations do not measure RSS.'}
