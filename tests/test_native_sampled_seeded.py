"""Capture and saved-only validation of the bounded seeded PROOF9 experiment."""
import argparse
import hashlib
import gzip
import json
from math import frexp
import os
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests.test_native_exact_reach import ROOT, authenticate
from scripts.preflop_validation import independent_rank
from tests.full_deck_public_chance_reference import card_name
from tests.test_native_sampled_grid import (
    FRONTIER_DECK, FRONTIER_RANGES, _grid, _literal_draw, _model, _uniform_boards, _walk_deal,
)
from tests.virtual_dyadic_training_reference import Fixture
from tests.virtual_frozen_run_control import run_bounded_child


SEED = 0x4F504C2026111601
DRAW_COUNT = 32
ATTEMPT_CAP = 64
DEALT_ATTEMPT_CAP = 256
ELEVEN_DECK = tuple(sorted((*FRONTIER_DECK,0,1)))
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


def _dealt_lottery():
    # Align fixture prior weights by their decoded binary64 exponent. The
    # native ticket indexes exact integer masses, including this common scale.
    weights = [[(hand,Fraction(weight,8)) for hand,weight in side] for side in FRONTIER_RANGES]
    scale = 1 << sum(max(53-frexp(float(weight))[1] for _,weight in side) for side in weights)
    pairs = []
    for first,a in weights[0]:
        for second,b in weights[1]:
            if set(first).isdisjoint(second):
                size = a*b*scale
                require(size.denominator == 1, 'nonintegral private lottery weight')
                pairs.append(((first,second),size.numerator))
    return tuple(pairs)


def _dealt_ticket(limit, word):
    bits = (limit-1).bit_length()
    while True:
        candidate = sum((word() & ((1 << min(64,bits-i))-1)) << i for i in range(0,bits,64))
        if candidate < limit:
            return candidate


def _dealt_increments(root,nodes,board,committed,private):
    ranks = [independent_rank(tuple(card_name(card) for card in (*hand,*board))) for hand in private]
    sign = (ranks[0] > ranks[1]) - (ranks[0] < ranks[1])
    rows = {}
    _walk_deal(root,nodes,board,committed,private,dict.fromkeys((0,3,4,5),1),sign,rows)
    return rows


def replay_saved_policy(path, expected_sha256):
    """Authenticate and evaluate a saved policy without invoking native code."""
    path = Path(path)
    require(path.stat().st_size <= CAPTURE_LIMIT, 'seeded encoded artifact byte admission')
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path,'rb') as source:
        raw = source.read(CAPTURE_LIMIT+1)
    require(0 < len(raw) <= CAPTURE_LIMIT, 'seeded artifact byte admission')
    observed = hashlib.sha256(raw).hexdigest()
    require(observed == expected_sha256, 'seeded artifact digest mismatch')
    records = _records(raw)
    tag, seed, draws, cap, work = next(records)
    eleven = tag == 'SAMPLED_PROOF11_DEALT_V1'
    dealt = eleven or tag == 'SAMPLED_PROOF9_DEALT_V1'
    deck = ELEVEN_DECK if eleven else FRONTIER_DECK
    attempt_cap = DEALT_ATTEMPT_CAP if dealt else ATTEMPT_CAP
    require(tag in ('SAMPLED_PROOF11_DEALT_V1','SAMPLED_PROOF9_DEALT_V1','SAMPLED_PROOF9_V1') and
            (int(seed), int(draws), int(cap), int(work)) ==
            (SEED, DRAW_COUNT, attempt_cap, DRAW_WORK_CAP), 'seeded admission identity')
    boards = () if dealt else tuple(_uniform_boards(deck))
    work_sums = dict.fromkeys(('chance','history','common_regret','average','quantization'),0)
    words = _splitmix(SEED)
    lottery = _dealt_lottery() if dealt else ()
    private_limit = sum(size for _,size in lottery)
    root, nodes = _model(True)
    committed, average, menus = {}, {}, {}
    attempts = staged = reserved = rank_calls = 0
    def word_attempt():
        nonlocal attempts
        require(attempts < attempt_cap, 'seeded word attempt bound')
        attempts += 1
        return next(words)

    for draw in range(DRAW_COUNT):
        tag, *fields = next(records)
        ordinal_index, saved_attempt, word, ordinal, *tail = map(int, fields)
        private = None
        proposal = boards
        if dealt:
            saved_ticket, a, b, c, d, *tail = tail
            ticket = _dealt_ticket(private_limit,word_attempt)
            require(saved_ticket == ticket, 'seeded private ticket drift')
            residual = ticket
            for pair,size in lottery:
                if residual < size:
                    private = pair
                    break
                residual -= size
            require(private == ((a,b),(c,d)), 'seeded compatible private deal drift')
            remaining = tuple(card for card in deck if card not in (a,b,c,d))
            proposal = tuple(_uniform_boards(remaining))
        board = tuple(tail[:5])
        rows, forecast, ranks, *ledgers = tail[5:]
        require(len(ledgers) == (len(work_sums) if eleven else 0), 'seeded draw ledger shape')
        if eleven:
            require(min(ledgers) >= 0 and sum(ledgers) <= forecast, 'seeded draw ledger exceeds admission')
            for key, value in zip(work_sums,ledgers,strict=True):
                work_sums[key] += value
        require(tag == 'DRAW' and ordinal_index == draw, 'seeded draw index')
        rejection = (1 << 64) % len(proposal)
        expected_word = word_attempt()
        while expected_word < rejection:
            expected_word = word_attempt()
        expected_ordinal = expected_word % len(proposal)
        require((saved_attempt, word, ordinal, board) ==
                (attempts, expected_word, expected_ordinal, proposal[expected_ordinal]), 'seeded proposal drift')
        require(0 < forecast <= DRAW_WORK_CAP and 0 <= rows <= 868, 'seeded draw resource bound')
        live = 2 if dealt else sum(set(hand).isdisjoint(board) for side in FRONTIER_RANGES for hand,_ in side)
        require(ranks == live, 'seeded rank-plane census')
        increments = (_dealt_increments(root,nodes,board,committed,private) if dealt else
                      _literal_draw(root,nodes,board,committed,FRONTIER_DECK,FRONTIER_RANGES))
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
    fixture = Fixture(eleven_card=eleven)
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
    status = ('seeded_proof11_dealt_saved_policy_exact_replay_pass' if eleven else
              'seeded_proof9_dealt_saved_policy_exact_replay_pass' if dealt else
              'seeded_proof9_saved_policy_exact_replay_pass')
    result = {
        'status': status,
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
    if eleven:
        result.update(physical_worlds=len(fixture.worlds), physical_policy_rows=fixture.row_count,
                      physical_policy_slots=fixture.slot_count, measured_draw_ledgers=work_sums)
    return result


class DealtEstimatorTests(unittest.TestCase):
    def test_expected_signed_updates_equal_exhaustive_proof9(self):
        fixture = Fixture()
        root, nodes = _model(True)
        pair_ranges = tuple(tuple(hand for hand,_ in side) for side in FRONTIER_RANGES)
        holding_rank = [{hand:i for i,hand in enumerate(side)} for side in pair_ranges]
        signed, average = {}, {}
        for world in fixture.worlds:
            private = tuple(pair_ranges[p][index] for p,index in enumerate(world.holdings))
            for (player,hand,history),(menu,_,regret,_,masses) in _dealt_increments(
                    root,nodes,world.board,{},private).items():
                key = (player,holding_rank[player][hand],history)
                self.assertEqual(menu,fixture.menus[key])
                zero = (0,) * len(menu)
                signed[key] = _totals(signed.get(key,zero),tuple(world.mass*x for x in regret))
                average[key] = _totals(average.get(key,zero),tuple(world.mass*x for x in masses))
        self.assertEqual(signed.keys(),fixture.menus.keys())
        # Give the exhaustive CFR+ reference a positive offset to leave its
        # clipping inactive, then subtract it to compare signed increments.
        offset = 32*fixture.denominator
        base = {key:(offset,)*len(menu) for key,menu in fixture.menus.items()}
        empty = {key:(0,)*len(menu) for key,menu in fixture.menus.items()}
        full_regret,full_average,_ = fixture.sweep(fixture.grid(),base,empty)
        self.assertTrue(any(value<0 for row in signed.values() for value in row))
        self.assertEqual(signed,{key:tuple(Fraction(x-offset,fixture.denominator) for x in values)
                                 for key,values in full_regret.items()})
        self.assertEqual(average,{key:tuple(Fraction(x,fixture.denominator) for x in values)
                                  for key,values in full_average.items()})


@unittest.skipUnless(EXECUTABLE, 'explicit source-built changing-policy controls required')
class NativeSampledSeededTests(unittest.TestCase):
    def test_saved_policy_and_independent_best_response(self):
        self._capture('sampled-grid-seeded','uniform')

    def test_dealt_saved_policy_and_independent_best_response(self):
        self._capture('sampled-grid-dealt-seeded','dealt')

    def _capture(self, mode, label):
        exe = Path(EXECUTABLE).resolve()
        identity = authenticate(exe,ROOT,'virtual-frozen-update-controls')
        location = os.environ.get('OPENPOKER_NATIVE_SAMPLED_SEEDED_DIR')
        if location is None:
            temporary = TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            location = temporary.name
        output = Path(location).resolve() / label
        output.parent.mkdir(parents=True,exist_ok=True)
        child = run_bounded_child([str(exe),mode],b'',output,stdout_limit=CAPTURE_LIMIT,timeout=90)
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
