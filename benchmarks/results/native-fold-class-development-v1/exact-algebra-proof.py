"""Exact research proof for linear-storage fold operators; no solver/producer calls."""
from collections import defaultdict
from fractions import Fraction
import hashlib
from itertools import combinations
import json
from pathlib import Path
from random import Random

work = Path(__file__).resolve().parent
out = work / "fold-mask-class-proof-v1"
out.mkdir(exist_ok=False)
rng = Random(301031)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def handmask(hand): return sum(1 << c for c in hand)
def bucket(rows):
    total = Fraction(0); card = defaultdict(Fraction); exact = defaultdict(Fraction)
    for hand, value in rows:
        total += value
        for c in hand: card[c] += value
        exact[hand] += value
    return total, card, exact
def compatible(hand, b):
    total, card, exact = b
    return total - card[hand[0]] - card[hand[1]] + exact[hand]
def normalize_literal(ranges, boards):
    # Independent bounded oracle enumerates pairs/boards transiently, never used
    # by the proposed operator or a training backend.
    return sum((w0*w1 for h0,w0 in ranges[0] for h1,w1 in ranges[1]
        for board in boards if not (set(h0)&set(h1) or set(h0)&set(board) or set(h1)&set(board))), Fraction(0))
def prepare(ranges, boards):
    masks = [[sum(1 << k for k, board in enumerate(boards) if not set(hand)&set(board))
              for hand,_ in side] for side in ranges]
    classes = []
    for side, seat_masks in zip(ranges,masks):
        groups = defaultdict(list)
        for j, ((hand,weight), mask) in enumerate(zip(side,seat_masks)):
            groups[mask].append((j,hand,weight))
        classes.append(groups)
    return masks, classes
def apply_class(ranges, masks, classes, selected, player, payoff, reach, normalizer):
    query = sum(1 << k for k in selected)
    answer = [Fraction(0) for _ in ranges[player]]
    stats = {"buckets":0,"own_class_checks":0,"integer_board_counts":0}
    for opp_mask, rows in classes[1-player].items():
        if not opp_mask & query: continue
        b = bucket((hand, weight*reach[j]) for j,hand,weight in rows if reach[j])
        stats["buckets"] += 1
        for i, ((hand,weight), mask) in enumerate(zip(ranges[player],masks[player])):
            stats["own_class_checks"] += 1
            count = (query & mask & opp_mask).bit_count()
            if count:
                answer[i] += weight * compatible(hand,b) * count * payoff / normalizer
                stats["integer_board_counts"] += 1
    return answer, stats
def apply_literal(ranges, boards, selected, player, payoff, reach, normalizer):
    answer = []
    for own,weight in ranges[player]:
        value = sum((weight*oppweight*reach[j]*payoff for j,(opp,oppweight) in enumerate(ranges[1-player])
            for k in selected if not(set(own)&set(opp) or set(own)&set(boards[k]) or set(opp)&set(boards[k]))), Fraction(0))
        answer.append(value / normalizer)
    return answer
observations = []
deck = tuple(range(52))
for fixture in range(48):
    counts = ((2,2),(4,4),(2,16),(8,8))[(fixture//3)%4]
    board_count = (1,5,22,64)[fixture%4]
    boards = []
    while len(boards) < board_count:
        board = tuple(rng.sample(deck,5))
        board = tuple(sorted(board[:3])) + board[3:]
        if board not in boards: boards.append(board)
    pool = list(combinations(deck,2)); rng.shuffle(pool)
    ranges = []
    for seat,count in enumerate(counts):
        # Deliberately share an exact private holding between roles. That pair
        # is incompatible and requires the bucket's exact-hand correction.
        hands = pool[:count] if seat==0 else [pool[0],*pool[counts[0]:counts[0]+count-1]]
        ranges.append([(h, Fraction.from_float((1.,.5,.25,.1,2**-900)[(i+fixture)%5])) for i,h in enumerate(hands)])
    z = normalize_literal(ranges,boards)
    if not z:
        observations.append({"fixture":fixture,"status":"zero-support-rejected"});continue
    masks, classes = prepare(ranges,boards)
    for query_kind in range(3):
        selected = tuple(range(board_count)) if query_kind==0 else tuple(k for k in range(board_count) if (k+query_kind)%3==0)
        for player in (0,1):
            reach = [Fraction.from_float((0.,1.,.5,.1,2**-1000)[(j+fixture+query_kind)%5]) for j in range(counts[1-player])]
            payoff = Fraction.from_float((.5,-.5,.1,-.1,0.)[(fixture+query_kind)%5])
            actual,stats = apply_class(ranges,masks,classes,selected,player,payoff,reach,z)
            expected = apply_literal(ranges,boards,selected,player,payoff,reach,z)
            if actual != expected: raise ValueError("exact fold operator differs")
            if len(set(selected)) != len(selected): raise ValueError("duplicate subset")
            observations.append({"fixture":fixture,"player":player,"query":query_kind,"status":"exact-match",
                "boards":board_count,"selected":len(selected),"hands":counts,
                "classes":tuple(map(len,classes)),"stats":stats,
                "policy_storage":0,"private_pair_storage":0,"world_storage":0,
                "oracle_vector_sha256":sha(json.dumps([str(v) for v in expected]).encode())})
receipt={"status":"passed","checks":sum(x['status']=='exact-match' for x in observations),
    "fixtures":48,"seed":301031,"helper_sha256":sha(Path(__file__).read_bytes()),"observations":observations,
    "scope":"Exact Fraction algebra against a bounded independent pair/board oracle. Proposed class operator stores only per-hand masks and class membership, never pair coefficients. This is no native implementation, performance measurement, admission change or quality result."}
with (out / "receipt.json").open("x") as stream: json.dump(receipt,stream,indent=2)
print(json.dumps({k:receipt[k] for k in ('status','checks','fixtures','helper_sha256')}),flush=True)
