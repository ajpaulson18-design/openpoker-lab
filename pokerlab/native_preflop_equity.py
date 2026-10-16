"""Explicit source-built native preparation for bounded full-board equities.

The Python builder remains the default/reference. This module never compiles
implicitly, changes solver admission, or falls back after a native failure.
Build manifests identify local tools and bytes; they are not authentication of
an untrusted binary or caller-supplied table.
"""
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from .cards import DECK, cards
from .preflop_full_board_equity import (
    BOARDS_PER_PAIR, FullBoardEquities, _as_positive_float,
    plan_preflop_equities,
)

SOURCE = Path(__file__).resolve().parents[1] / 'native' / 'preflop_equity.c'
PROTOCOL = 'OPENPOKER_NATIVE_V1'
MAX_OUTPUT_BYTES = 262_144
NATIVE_TIMEOUT_SECONDS = 120


def _json_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('Duplicate native JSON field.')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('Non-finite native JSON value: ' + value)


def _sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _source_hashes():
    raw = SOURCE.read_bytes()
    return (hashlib.sha256(raw).hexdigest(),
            hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest())


def _backend(build_directory):
    directory = Path(build_directory).resolve(strict=True)
    manifest_path = directory / 'native-preflop-manifest.json'
    if manifest_path.stat().st_size > 32_768:
        raise ValueError('Native build manifest exceeds its size limit.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'),
                          object_pairs_hook=_json_object, parse_constant=_reject_constant)
    keys = {'schema_version', 'protocol', 'source_sha256', 'source_lf_sha256',
            'executable', 'executable_sha256', 'compiler', 'compiler_version',
            'flags', 'platform'}
    if type(manifest) is not dict or set(manifest) != keys:
        raise ValueError('Native build manifest has an unsupported shape.')
    if (type(manifest['schema_version']) is not int
            or manifest['schema_version'] != 1 or manifest['protocol'] != PROTOCOL
            or manifest['executable'] not in ('native-preflop-equity', 'native-preflop-equity.exe')):
        raise ValueError('Unsupported native build identity.')
    raw_hash, lf_hash = _source_hashes()
    if (manifest['source_sha256'] != raw_hash
            or manifest['source_lf_sha256'] != lf_hash):
        raise ValueError('Native source changed; explicitly rebuild the helper.')
    if (any(type(manifest[key]) is not str or not manifest[key]
            for key in ('compiler', 'compiler_version', 'platform', 'executable_sha256'))
            or type(manifest['flags']) is not list
            or any(type(flag) is not str for flag in manifest['flags'])):
        raise ValueError('Native compiler provenance is malformed.')
    executable = directory / manifest['executable']
    if executable.is_symlink() or not executable.is_file():
        raise ValueError('Native executable must be a local regular file.')
    if _sha(executable) != manifest['executable_sha256']:
        raise ValueError('Native executable changed since its recorded build.')
    return executable, manifest


def _invoke(mode, rows, build_directory):
    executable, manifest = _backend(build_directory)
    request = (f'{PROTOCOL} {mode} {len(rows)}\n'
               + ''.join(' '.join(map(str, row)) + '\n' for row in rows)).encode('ascii')
    if len(request) > MAX_OUTPUT_BYTES:
        raise ValueError('Native request exceeds its byte limit.')
    # Files bound Python reads even if a broken helper emits unexpected output.
    # The project-owned helper itself admits a fixed input/output envelope.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        completed = subprocess.run([str(executable)], input=request, stdout=output,
                                   stderr=errors, timeout=NATIVE_TIMEOUT_SECONDS,
                                   check=False)
        output.seek(0); payload = output.read(MAX_OUTPUT_BYTES + 1)
        errors.seek(0); error = errors.read(4096)
    if completed.returncode != 0:
        raise RuntimeError(f'Native preparation failed ({completed.returncode}): '
                           + error.decode('utf-8', errors='replace').strip())
    if len(payload) > MAX_OUTPUT_BYTES:
        raise ValueError('Native response exceeds its byte limit.')
    if _sha(executable) != manifest['executable_sha256'] or _source_hashes()[0] != manifest['source_sha256']:
        raise RuntimeError('Native source or executable changed during execution.')
    try:
        result = json.loads(payload, object_pairs_hook=_json_object,
                            parse_constant=_reject_constant)
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Native response is not valid JSON.') from exc
    if (type(result) is not dict or type(result.get('schema_version')) is not int
            or result['schema_version'] != 1 or result.get('mode') != mode.lower()):
        raise ValueError('Native response protocol identity mismatch.')
    return result, manifest


@dataclass(frozen=True, slots=True)
class NativePreflopPreparation:
    """Immutable ordinary equity table plus separately serialized provenance."""
    equities: FullBoardEquities
    _metadata_json: str

    @property
    def metadata(self):
        return json.loads(self._metadata_json)


def prepare_native_preflop_equities(sb_range, bb_range, *, build_directory):
    """Prepare all boards with an explicitly built helper after normal admission.

    This separate entry point has no progress callback. Existing Python callback
    semantics, default preparation and solver payloads remain unchanged.
    """
    plan = plan_preflop_equities(sb_range, bb_range)
    plan.validate()
    ids = {card: index for index, card in enumerate(DECK)}
    rows = [tuple(ids[card] for card in plan.hands[0][i] + plan.hands[1][j])
            for i, j, _ in plan.pairs]
    result, manifest = _invoke('COUNT', rows, build_directory)
    if set(result) != {'schema_version', 'mode', 'counts', 'boards_per_pair', 'rank_calls'}:
        raise ValueError('Native count response has unexpected fields.')
    if (type(result['boards_per_pair']) is not int or result['boards_per_pair'] != BOARDS_PER_PAIR
            or type(result['rank_calls']) is not int
            or result['rank_calls'] != 2 * len(plan.pairs) * BOARDS_PER_PAIR):
        raise ValueError('Native work census disagrees with admitted full-board work.')
    counts = result['counts']
    if (type(counts) is not list or len(counts) != len(plan.pairs)
            or any(type(row) is not list or len(row) != 3
                   or any(type(value) is not int or value < 0 for value in row)
                   or sum(row) != BOARDS_PER_PAIR for row in counts)):
        raise ValueError('Native counts do not cover every admitted board.')
    worlds = []
    for (i, j, prior), (wins, ties, losses) in zip(plan.pairs, counts):
        for sign, count in zip((-1, 0, 1), (losses, ties, wins)):
            if count:
                mass = prior * Fraction(count, BOARDS_PER_PAIR)
                worlds.append((i, j, _as_positive_float(mass, 'categorical mass'), sign))
    equities = FullBoardEquities(plan.hands, plan.pairs,
                                tuple(tuple(row) for row in counts), tuple(worlds),
                                plan._budget_items)
    equities.validate()
    metadata = {'backend': 'native-full-board-v1', 'build': manifest,
                'compatible_pairs': len(plan.pairs),
                'board_evaluations': len(plan.pairs) * BOARDS_PER_PAIR,
                'rank_calls': result['rank_calls'], 'source_inclusive_admission': True,
                'scope': 'Exact unordered boards; same finite preparation limits. '
                         'Build identity and structural validation are not authentication.'}
    return NativePreflopPreparation(equities, json.dumps(metadata, sort_keys=True, allow_nan=False))


def rank_native_hands(hands, *, build_directory):
    """Bounded evaluator conformance utility; each returned rank has six integers."""
    if type(hands) not in (list, tuple) or not 1 <= len(hands) <= 4096:
        raise ValueError('Native rank batch must contain 1 to 4,096 hands.')
    ids = {card: index for index, card in enumerate(DECK)}
    rows = []
    for hand in hands:
        validated = cards(hand)
        if not 5 <= len(validated) <= 7:
            raise ValueError('Native hand ranking needs 5 to 7 distinct cards.')
        rows.append((len(validated), *(ids[card] for card in validated)))
    result, _ = _invoke('RANK', rows, build_directory)
    if set(result) != {'schema_version', 'mode', 'ranks'}:
        raise ValueError('Native rank response has unexpected fields.')
    ranks = result['ranks']
    if (type(ranks) is not list or len(ranks) != len(rows)
            or any(type(row) is not list or len(row) != 6
                   or any(type(value) is not int or not 0 <= value <= 14 for value in row)
                   or row[0] > 8 for row in ranks)):
        raise ValueError('Native rank response has invalid ranks.')
    return tuple(tuple(row) for row in ranks)
