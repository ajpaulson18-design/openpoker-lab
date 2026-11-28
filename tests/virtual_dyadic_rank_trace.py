"""Independent rank-free board-set cache query trace for named finite fixtures.

Builds no production game tree and performs no hand ranking or training. The
reference betting template and physical private-pair support determine query
order, including hidden all-in completions; the simulated cache is persistent
across two paired sweeps. Ordered turn/river remain distinct query events.
"""
from functools import lru_cache
from itertools import combinations

from tests.full_deck_public_chance_reference import PROOF9
from tests.virtual_betting_template_reference import build_reference_template
from tests.virtual_frozen_update_reference import _template_case, scaled_proof9_ranges


def rank_trace(*, eleven_card=False):
    """Return the exact N10/N11 paired-T2 sorted-board-set lookup ledger."""
    if type(eleven_card) is not bool:
        raise ValueError('fixture flag must be boolean')
    deck=tuple(sorted((*PROOF9,0,1))) if eleven_card else tuple(sorted((*PROOF9,0)))
    if len(set(deck))!=(11 if eleven_card else 10):
        raise ValueError('unexpected named deck')
    template=build_reference_template(_template_case())
    ranges=scaled_proof9_ranges()
    pairs=tuple(frozenset(a+b) for a,_ in ranges[0] for b,_ in ranges[1]
                if set(a).isdisjoint(b))
    if len(pairs)!=3:
        raise ValueError('unexpected private-pair support')

    @lru_cache(None)
    def supported(board):
        return any(not set(board)&private for private in pairs)

    @lru_cache(None)
    def reveal(board):
        candidates=(combinations(deck,3) if not board else
                    (board+(card,) for card in deck if card not in board))
        return tuple(b for b in candidates if supported(b))

    recent=None
    resident=set()
    queries=searches=misses=hits=ranked=0
    capacity=56 if eleven_card else 17
    def query(board):
        nonlocal recent,queries,searches,misses,hits,ranked
        if len(board)!=5 or not supported(board):
            raise ValueError('invalid full-board query')
        ranked+=1
        mask=sum(1<<card for card in board)
        # Paired SB/BB calls are adjacent, even if current reach is zero.
        for _ in range(2):
            queries+=1
            if recent==mask:
                hits+=1
                continue
            searches+=1
            if mask in resident:
                hits+=1
            else:
                if len(resident)>=capacity:
                    raise ValueError('fixed fixture unexpectedly evicts')
                resident.add(mask)
                misses+=1
            recent=mask

    def complete(board):
        if len(board)==5:
            query(board)
        else:
            for next_board in reveal(board):
                complete(next_board)

    def visit(node_id,board):
        node=template.nodes[node_id]
        if node.street!=len(board):
            raise ValueError('reference street differs')
        if node.phase=='reveal':
            if len(node.edges)!=1:
                raise ValueError('unexpected reveal edges')
            for next_board in reveal(board):
                visit(node.edges[0].child,next_board)
        elif node.phase=='decision':
            for edge in node.edges:
                visit(edge.child,board)
        elif node.phase=='showdown':
            complete(board)
        elif node.phase!='fold':
            raise ValueError('unknown reference phase')

    for _ in range(2):
        visit(template.root,())
    expected_queries=1_357_440 if eleven_card else 412_080
    if queries!=expected_queries or misses!=capacity or hits+misses!=queries:
        raise ValueError('rank-free showdown census differs')
    width=capacity.bit_length()
    lookup_bound=6+8*width
    update_bound=8*capacity+16*width+32
    setup=4*capacity+16
    # Recent hits cost two in parent receipt but are excluded from index
    # receipt's lookup_work; first query has no recent slot.
    index_lookup=searches*(lookup_bound-2)
    updates=misses
    update_work=updates*update_bound
    parent_lookup=2*(queries-1)+index_lookup+update_work+misses*(4*capacity+64)
    return {'fixture':'N11' if eleven_card else 'N10','queries':queries,
            'showdown_boards':ranked,'capacity':capacity,'entries':32+2*capacity,
            'size':len(resident),'searches':searches,'updates':updates,
            'lookup_work':index_lookup,'update_work':update_work,'setup_work':setup,
            'cache_hits':hits,'cache_misses':misses,'cache_evictions':0,
            'parent_cache_lookup_work':parent_lookup,'native_calls':0,'rank_calls':0}
