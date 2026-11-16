"""Capture and saved-only validation of the bounded seeded PROOF9 experiment."""
import argparse
from bisect import bisect_right
from itertools import accumulate, combinations, islice
import hashlib
import gzip
import json
from math import comb, frexp
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
QUALITY_RUNS = ((SEED,32),(SEED,128),(SEED,512),
                (0x243F6A8885A308D3,128),(0x13198A2E03707344,128))
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
    maximum_rows = (DRAW_COUNT*868 if lines and
                    lines[0].startswith('SAMPLED_FULL52_WIDE_POLICY_REPLAY_V1 ') else 24_420)
    maximum_draws = 512 if lines and lines[0].startswith('SAMPLED_PROOF9_QUALITY_V1 ') else DRAW_COUNT
    require(len(lines) <= maximum_rows + maximum_draws + 3, 'seeded record count')
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


def _full_deck_lottery():
    # A separate verifier may scan the compatible pairs once. It stores
    # only per-first cumulative sums and independently decodes each ticket.
    hands = tuple(combinations(range(52),2))
    masks = tuple((1 << a) | (1 << b) for a,b in hands)
    weights = tuple(tuple(1 + (i*step+offset)%31 for i in range(len(hands)))
                    for step,offset in ((17,0),(29,3)))
    grouped = tuple(accumulate(first*sum(second for other,second in zip(masks,weights[1],strict=True)
                                  if not mask & other)
                               for mask,first in zip(masks,weights[0],strict=True)))

    def locate(raw_ticket):
        ticket = raw_ticket >> 104
        i = bisect_right(grouped,ticket)
        residual = ticket - (grouped[i-1] if i else 0)
        for j,(mask,weight) in enumerate(zip(masks,weights[1],strict=True)):
            if masks[i] & mask:
                continue
            interval = weights[0][i]*weight
            if residual < interval:
                return hands[i],hands[j]
            residual -= interval
        raise ValueError('full-deck compatible ticket escaped its intervals')

    # The smallest decoded input exponent on either side is -52 (weight one).
    return grouped[-1] << 104,locate


def _full_deck_board(remaining, ordinal):
    # Only the flop is enumerated for indexing. Turn and river are
    # independent ordered selections among the remaining cards.
    after_flop = len(remaining)-3
    flop_index,suffix = divmod(ordinal,after_flop*(after_flop-1))
    flop = next(islice(combinations(remaining,3),flop_index,None))
    legal = [card for card in remaining if card not in flop]
    turn,river = divmod(suffix,after_flop-1)
    return (*flop,legal.pop(turn),legal[river])


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
    curve = tag == 'SAMPLED_PROOF9_QUALITY_V1'
    wide = tag == 'SAMPLED_FULL52_WIDE_POLICY_REPLAY_V1'
    packed = wide or curve
    policy_replay = wide or tag == 'SAMPLED_FULL52_POLICY_REPLAY_V1'
    full_deck = policy_replay or tag == 'SAMPLED_FULL52_DEALT_REPLAY_V1'
    history_replay = tag == 'SAMPLED_PROOF11_DEALT_HISTORY_REPLAY_V1'
    eleven = history_replay or tag == 'SAMPLED_PROOF11_DEALT_V1'
    dealt = curve or full_deck or eleven or tag == 'SAMPLED_PROOF9_DEALT_V1'
    deck = tuple(range(52)) if full_deck else ELEVEN_DECK if eleven else FRONTIER_DECK
    seed,draw_count = int(seed),int(draws)
    attempt_cap = 8*draw_count if curve else DEALT_ATTEMPT_CAP if dealt else ATTEMPT_CAP
    accepted = QUALITY_RUNS if curve else ((SEED,DRAW_COUNT),)
    require((dealt or tag == 'SAMPLED_PROOF9_V1') and (seed,draw_count) in accepted and
            (int(cap),int(work))==(attempt_cap,DRAW_WORK_CAP), 'seeded admission identity')
    boards = () if dealt else tuple(_uniform_boards(deck))
    work_sums = dict.fromkeys(('chance','history','common_regret','average','quantization'),0)
    words = _splitmix(seed)
    lottery = _dealt_lottery() if dealt and not full_deck else ()
    private_limit = sum(size for _,size in lottery)
    if full_deck:
        private_limit,locate = _full_deck_lottery()
    has_ledgers = curve or eleven or full_deck
    root, nodes = _model(True,wide=wide)
    if wide:
        require(len(nodes)==661, 'wide reference betting geometry')
    committed, average, menus = {}, {}, {}
    attempts = staged = reserved = rank_calls = 0
    def word_attempt():
        nonlocal attempts
        require(attempts < attempt_cap, 'seeded word attempt bound')
        attempts += 1
        return next(words)

    for draw in range(draw_count):
        tag, *fields = next(records)
        ordinal_index, saved_attempt, word, ordinal, *tail = map(int, fields)
        private = None
        proposal = boards
        remaining = ()
        if dealt:
            saved_ticket, a, b, c, d, *tail = tail
            ticket = _dealt_ticket(private_limit,word_attempt)
            require(saved_ticket == ticket, 'seeded private ticket drift')
            if full_deck:
                private = locate(ticket)
            else:
                residual = ticket
                for pair,size in lottery:
                    if residual < size:
                        private = pair
                        break
                    residual -= size
            require(private == ((a,b),(c,d)), 'seeded compatible private deal drift')
            remaining = tuple(card for card in deck if card not in (a,b,c,d))
            if not full_deck:
                proposal = tuple(_uniform_boards(remaining))
        board = tuple(tail[:5])
        rows, forecast, ranks, *ledgers = tail[5:]
        require(len(ledgers) == (len(work_sums) if has_ledgers else 0), 'seeded draw ledger shape')
        if has_ledgers:
            require(min(ledgers) >= 0 and sum(ledgers) <= forecast, 'seeded draw ledger exceeds admission')
            for key, value in zip(work_sums,ledgers,strict=True):
                work_sums[key] += value
        require(tag == 'DRAW' and ordinal_index == draw, 'seeded draw index')
        if full_deck:
            size = comb(len(remaining),3)*(len(remaining)-3)*(len(remaining)-4)
        else:
            size = len(proposal)
        rejection = (1 << 64) % size
        expected_word = word_attempt()
        while expected_word < rejection:
            expected_word = word_attempt()
        expected_ordinal = expected_word % size
        expected_board = (_full_deck_board(remaining,expected_ordinal) if full_deck else
                          proposal[expected_ordinal])
        require((saved_attempt, word, ordinal, board) ==
                (attempts, expected_word, expected_ordinal, expected_board), 'seeded proposal drift')
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
            (draw_count,row_count,slot_count,staged,reserved,rank_calls,attempts), 'seeded policy census')

    sparse = {}
    last = None
    last_history = ()
    for _ in range(row_count):
        tag, actor, a, b, depth, *tokens = next(records)
        player, first, second, n = map(int,(actor,a,b,depth))
        if packed:
            suffix_length,*tokens = tokens
            suffix = int(suffix_length)
            require(tag=='PACK' and 0 <= n <= len(last_history) and 0 <= suffix <= 64-n,
                    'packed row visible history')
            history = last_history[:n] + tuple(tokens[:suffix])
            actions,*fields = tokens[suffix:]
            count = int(actions)
            require(len(fields)==count, 'packed row policy units')
            units = tuple(int(value,16) for value in fields)
        else:
            require(tag=='ROW' and 0 <= n <= 15, 'seeded row visible history')
            history = tuple(tokens[:n])
            actions,*fields = tokens[n:]
            count = int(actions)
            units = tuple(map(int,fields[1::2]))
        key = player,(first,second),history
        require(player in (0,1) and 0 <= first < second < 52 and
                (last is None or last < key) and key in menus, 'seeded policy row identity')
        last = key
        last_history = history
        menu = menus[key]
        require(len(units)==count==len(menu), 'seeded policy action count')
        if not packed:
            require(len(fields)==2*count and tuple(fields[::2])==menu, 'seeded policy legal menu')
        require(units == _grid(average[key]), 'seeded policy differs from independent exact average')
        sparse[key] = units
    tag, rows, export_work, *dealer = next(records)
    require(tag == 'END' and int(rows) == row_count and 0 < int(export_work) <= DRAW_WORK_CAP
            and next(records,None) is None, 'seeded complete export')
    if full_deck:
        work, retained, scratch, payload, queries, terminals, ranking = map(int,dealer)
        require(0 < work <= DRAW_WORK_CAP and retained+scratch <= 2_000_000 and
                0 < payload <= 1 << 30 and queries == DRAW_COUNT and terminals == ranking == 0,
                'full-deck private dealer resource receipt')
        result = {'status':'seeded_full52_sparse_policy_exact_replay_pass',
                'raw_sha256':observed,'native_producer_calls':0,'seed':SEED,
                'draws':DRAW_COUNT,'attempts':attempts,'staged_rows':staged,
                'saved_rows':row_count,'saved_slots':slot_count,
                'zero_average_mass_rows':sum(not any(values) for values in average.values()),
                'rank_calls':rank_calls,'measured_draw_ledgers':work_sums,
                'draw_work_reserved':reserved,'maximum_draw_work':DRAW_WORK_CAP,
                'export_work':int(export_work),
                'holdings_per_seat':comb(52,2),'compatible_private_deals':comb(52,2)*comb(50,2),
                'possible_boards_per_deal':comb(48,3)*45*44,
                'dealer':{'modeled_work':work,'retained_entries':retained,
                          'peak_scratch_entries':scratch,'peak_integer_payload_bits':payload,
                          'root_queries':queries,'terminal_queries':terminals,'rank_calls':ranking},
                'quality_gate':None}
        if policy_replay:
            result['policy_replay'] = True
        if wide:
            result['betting_nodes'] = len(nodes)
            result['postflop_bet_sizes'] = [0.5,0.75,1.0]
        return result
    require(not dealer, 'unexpected private dealer receipt')
    fixture = Fixture(eleven_card=eleven)
    holding_rank = [{hand:i for i,(hand,_) in enumerate(side)} for side in FRONTIER_RANGES]
    supplied = {(p,holding_rank[p][hand],h): units for (p,hand,h),units in sparse.items()}
    require(set(supplied) <= fixture.menus.keys(), 'seeded quality has invalid visible history')
    require(all(menus[key] == fixture.menus[key[0],holding_rank[key[0]][key[1]],key[2]]
                for key in menus), 'seeded quality legal menu drift')
    quality = fixture.quality(supplied,uniform_unseen=True)
    baseline = fixture.quality({},uniform_unseen=True)
    limit = Fraction(1,10)
    status = ('seeded_proof9_quality_saved_policy_exact_replay_pass' if curve else
              'seeded_proof11_dealt_saved_policy_exact_replay_pass' if eleven else
              'seeded_proof9_dealt_saved_policy_exact_replay_pass' if dealt else
              'seeded_proof9_saved_policy_exact_replay_pass')
    result = {
        'status': status,
        'raw_sha256': observed,
        'native_producer_calls': 0,
        'seed': seed,
        'draws': draw_count,
        'attempts': attempts,
        'staged_rows': staged,
        'saved_rows': row_count,
        'saved_slots': slot_count,
        'zero_average_mass_rows': sum(not any(values) for values in average.values()),
        'completed_uniform_rows': fixture.row_count-len(supplied),
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
    if curve:
        result['measured_draw_ledgers'] = work_sums
    if history_replay:
        result['history_replay'] = True
    return result


def compare_sampled_transcripts(baseline, candidate, *, policy_replay=False):
    # The decoded strategy and draw schedule must be identical. Only history
    # and the composed forecast may differ in the native resource transcript.
    first,second = _records(baseline),_records(candidate)
    header_a,header_b = next(first),next(second)
    tags = (('SAMPLED_FULL52_DEALT_REPLAY_V1','SAMPLED_FULL52_POLICY_REPLAY_V1') if policy_replay else
            ('SAMPLED_PROOF11_DEALT_V1','SAMPLED_PROOF11_DEALT_HISTORY_REPLAY_V1'))
    require((header_a[0],header_b[0])==tags and header_a[1:]==header_b[1:],
            'history comparison seed admission')
    original = current = 0
    original_policy = current_policy = 0
    for _ in range(DRAW_COUNT):
        a,b = next(first),next(second)
        require(a[0]==b[0]=='DRAW' and a[:-7]==b[:-7] and a[-6:-4]==b[-6:-4] and
                a[-3:-1]==b[-3:-1] and (policy_replay or a[-1]==b[-1]),
                'history comparison changed a draw or its other work')
        require(int(b[-7])<int(a[-7]) and int(b[-4])<int(a[-4]), 'history replay work did not decline')
        original += int(a[-4])
        current += int(b[-4])
        original_policy += int(a[-1])
        current_policy += int(b[-1])
    a,b = next(first),next(second)
    require(a[0]==b[0]=='POLICY' and a[:5]==b[:5] and a[6:]==b[6:],
            'history comparison policy summary differs')
    for a,b in zip(first,second,strict=True):
        require(a==b, 'history replay changed the saved policy or export')
    result = {'baseline_history_work':original,'candidate_history_work':current}
    if policy_replay:
        require(current_policy<original_policy, 'policy replay work did not decline')
        result.update(baseline_policy_work=original_policy,candidate_policy_work=current_policy)
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
    def test_eleven_history_replay_preserves_policy_and_lowers_work(self):
        self._compare_replay('eleven-history',('sampled-grid-dealt-eleven-seeded',
                                              'sampled-grid-eleven-history-replay'))

    def test_full52_policy_replay_preserves_policy_and_lowers_work(self):
        self._compare_replay('full52-policy',('sampled-grid-full52-dealt-seeded',
                                             'sampled-grid-full52-policy-replay'),policy_replay=True)

    def _compare_replay(self, label, modes, *, policy_replay=False):
        exe = Path(EXECUTABLE).resolve()
        identity = authenticate(exe,ROOT,'virtual-frozen-update-controls')
        base = os.environ.get('OPENPOKER_NATIVE_SAMPLED_SEEDED_DIR')
        if base is None:
            temporary = TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            base = temporary.name
        directory = Path(base) / label
        directory.mkdir(parents=True,exist_ok=False)
        outputs = []
        for label,mode in zip(('baseline','candidate'),modes,strict=True):
            out = directory / label
            observation = run_bounded_child([str(exe),mode],b'',out,stdout_limit=CAPTURE_LIMIT,timeout=90)
            self.assertTrue(observation['actual_exit_observed'])
            self.assertFalse(observation['failures'])
            self.assertEqual(observation['returncode'],0,(out/'stderr.bin').read_bytes())
            self.assertEqual((out/'stderr.bin').read_bytes(),b'')
            outputs.append((out/'stdout.bin').read_bytes())
        self.assertEqual(authenticate(exe,ROOT,'virtual-frozen-update-controls'),identity)
        comparison = compare_sampled_transcripts(*outputs,policy_replay=policy_replay)
        with (directory/'comparison.json').open('x',encoding='utf-8') as receipt:
            json.dump(comparison,receipt,sort_keys=True,indent=2)
            receipt.write('\n')

    def test_full52_wide_saved_policy_replay(self):
        self._capture('sampled-grid-full52-wide','full52-wide')

    def test_full52_broad_range_saved_policy_replay(self):
        self._capture('sampled-grid-full52-dealt-seeded','full52')

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
