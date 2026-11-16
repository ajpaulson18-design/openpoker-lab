"""Capture and saved-only validation of the bounded seeded PROOF9 experiment."""
import argparse
import hashlib
import json
import os
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests.test_native_exact_reach import ROOT, authenticate
from tests.test_native_sampled_grid import FRONTIER_DECK, FRONTIER_RANGES, _grid, _literal_draw, _model, _uniform_boards
from tests.virtual_dyadic_training_reference import Fixture
from tests.virtual_frozen_run_control import run_bounded_child


SEED = 0x4F504C2026111601
DRAW_COUNT = 32
ATTEMPT_CAP = 64
DRAW_WORK_CAP = 500_000_000
CAPTURE_LIMIT = 2 << 20
EXECUTABLE = os.environ.get('OPENPOKER_NATIVE_SAMPLED_GRID_EXECUTABLE')


def require(condition, label):
    if not condition:
        raise ValueError(label)


def _splitmix(seed):
    modulus = 1 << 64
    while True:
        seed = (seed + 0x9E3779B97F4A7C15) % modulus
        first = ((seed ^ (seed >> 30)) * 0xBF58476D1CE4E5B9) % modulus
        second = ((first ^ (first >> 27)) * 0x94D049BB133111EB) % modulus
        yield second ^ (second >> 31)


def _records(raw):
    lines = raw.decode('ascii').splitlines()
    require(len(lines) <= 24_420 + DRAW_COUNT + 3, 'seeded record count')
    for line in lines:
        require(0 < len(line) <= 4096, 'seeded line length')
        yield line.split()


def _totals(existing, increment):
    return tuple(a+b for a,b in zip(existing,increment,strict=True))


def _fractions(item):
    if isinstance(item, tuple):
        return [_fractions(value) for value in item]
    return {'numerator': str(item.numerator), 'denominator': str(item.denominator)}


def replay_saved_policy(path, expected_sha256):
    """Authenticate and evaluate a saved policy without invoking native code."""
    with Path(path).open('rb') as source:
        raw = source.read(CAPTURE_LIMIT+1)
    require(0 < len(raw) <= CAPTURE_LIMIT, 'seeded artifact byte admission')
    observed = hashlib.sha256(raw).hexdigest()
    require(observed == expected_sha256, 'seeded artifact digest mismatch')
    records = _records(raw)
    tag, seed, draws, cap, work = next(records)
    require((tag, int(seed), int(draws), int(cap), int(work)) ==
            ('SAMPLED_PROOF9_V1', SEED, DRAW_COUNT, ATTEMPT_CAP, DRAW_WORK_CAP), 'seeded admission identity')
    boards = tuple(_uniform_boards(FRONTIER_DECK))
    words = _splitmix(SEED)
    rejection = (1 << 64) % len(boards)
    root, nodes = _model(True)
    committed, average, menus = {}, {}, {}
    attempts = staged = reserved = rank_calls = 0
    for draw in range(DRAW_COUNT):
        tag, *fields = next(records)
        ordinal_index, saved_attempt, word, ordinal, *tail = map(int, fields)
        board = tuple(tail[:5])
        rows, forecast, ranks = tail[5:]
        require(tag == 'DRAW' and ordinal_index == draw, 'seeded draw index')
        while True:
            require(attempts < ATTEMPT_CAP, 'seeded word attempt bound')
            attempts += 1
            expected_word = next(words)
            if expected_word >= rejection:
                break
        expected_ordinal = expected_word % len(boards)
        require((saved_attempt, word, ordinal, board) ==
                (attempts, expected_word, expected_ordinal, boards[expected_ordinal]), 'seeded proposal drift')
        require(0 < forecast <= DRAW_WORK_CAP and 0 <= rows <= 868, 'seeded draw resource bound')
        live = sum(set(hand).isdisjoint(board) for side in FRONTIER_RANGES for hand,_ in side)
        require(ranks == live, 'seeded rank-plane census')
        increments = _literal_draw(root,nodes,board,committed,FRONTIER_DECK,FRONTIER_RANGES)
        require(len(increments) == rows, 'seeded independent row census')
        for key, (menu, _policy, regret, _mass, masses) in increments.items():
            require(menus.setdefault(key,menu) == menu, 'seeded row legal menu drift')
            empty = (0,) * len(menu)
            committed[key] = _totals(committed.get(key,empty),regret)
            average[key] = _totals(average.get(key,empty),masses)
        staged += rows
        reserved += forecast
        rank_calls += ranks
    tag, *summary = next(records)
    row_count, slot_count = len(menus), sum(map(len,menus.values()))
    require(tag == 'POLICY' and tuple(map(int,summary)) ==
            (DRAW_COUNT,row_count,slot_count,staged,reserved,rank_calls,attempts), 'seeded policy census')

    sparse = {}
    last = None
    for _ in range(row_count):
        tag, actor, a, b, depth, *tokens = next(records)
        player, first, second, n = map(int,(actor,a,b,depth))
        history = tuple(tokens[:n])
        key = player,(first,second),history
        require(tag == 'ROW' and player in (0,1) and 0 <= first < second < 52 and 0 <= n <= 15 and
                (last is None or last < key) and key in menus, 'seeded policy row identity')
        last = key
        actions, *fields = tokens[n:]
        count = int(actions)
        menu = tuple(fields[::2])
        units = tuple(map(int,fields[1::2]))
        require(len(fields) == 2*count and menu == menus[key] and len(units) == len(menu),
                'seeded policy legal menu')
        require(units == _grid(average[key]), 'seeded policy differs from independent exact average')
        sparse[key] = units
    tag, rows, export_work = next(records)
    require(tag == 'END' and int(rows) == row_count and 0 < int(export_work) <= DRAW_WORK_CAP
            and next(records,None) is None, 'seeded complete export')
    fixture = Fixture()
    holding_rank = [{hand:i for i,(hand,_) in enumerate(side)} for side in FRONTIER_RANGES]
    supplied = {(p,holding_rank[p][hand],h): units for (p,hand,h),units in sparse.items()}
    require(set(supplied) <= fixture.menus.keys(), 'seeded quality has invalid visible history')
    require(all(menus[key] == fixture.menus[key[0],holding_rank[key[0]][key[1]],key[2]]
                for key in menus), 'seeded quality legal menu drift')
    uniform = fixture.grid(None,average=True)
    dense = {**uniform,**supplied}
    quality = fixture.quality(dense)
    baseline = fixture.quality(uniform)
    limit = Fraction(1,10)
    return {
        'status': 'seeded_proof9_saved_policy_exact_replay_pass',
        'raw_sha256': observed,
        'native_producer_calls': 0,
        'seed': SEED,
        'draws': DRAW_COUNT,
        'attempts': attempts,
        'staged_rows': staged,
        'saved_rows': row_count,
        'saved_slots': slot_count,
        'zero_average_mass_rows': sum(not any(values) for values in average.values()),
        'completed_uniform_rows': len(dense)-len(supplied),
        'rank_calls': rank_calls,
        'draw_work_reserved': reserved,
        'maximum_draw_work': DRAW_WORK_CAP,
        'export_work': int(export_work),
        'quality': {name: _fractions(value) for name,value in quality.items()},
        'uniform_baseline': {name: _fractions(value) for name,value in baseline.items()},
        'quality_gate': {'threshold_bb': _fractions(limit), 'passed': quality['exploitability'] <= limit},
    }


@unittest.skipUnless(EXECUTABLE, 'explicit source-built changing-policy controls required')
class NativeSampledSeededTests(unittest.TestCase):
    def test_saved_policy_and_independent_best_response(self):
        exe = Path(EXECUTABLE).resolve()
        identity = authenticate(exe,ROOT,'virtual-frozen-update-controls')
        location = os.environ.get('OPENPOKER_NATIVE_SAMPLED_SEEDED_DIR')
        if location is None:
            temporary = TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            location = str(Path(temporary.name) / 'seeded')
        output = Path(location).resolve()
        child = run_bounded_child([str(exe),'sampled-grid-seeded'],b'',output,stdout_limit=CAPTURE_LIMIT,timeout=90)
        self.assertTrue(child['actual_exit_observed'])
        self.assertFalse(child['failures'])
        self.assertEqual(child['automatic_retries'],0)
        self.assertEqual(child['returncode'],0,(output/'stderr.bin').read_bytes())
        self.assertEqual((output/'stderr.bin').read_bytes(),b'')
        self.assertEqual(authenticate(exe,ROOT,'virtual-frozen-update-controls'),identity)
        replay = replay_saved_policy(output/'stdout.bin',child['streams'][0]['sha256'])
        self.assertEqual(replay['draws'],DRAW_COUNT)
        self.assertEqual(replay['native_producer_calls'],0)
        with (output/'quality.json').open('x',encoding='utf-8') as receipt:
            json.dump(replay,receipt,sort_keys=True,indent=2)
            receipt.write('\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saved',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    args = parser.parse_args()
    print(json.dumps(replay_saved_policy(args.saved,args.sha256),sort_keys=True,indent=2))
