"""Independent N10 immutable row-directory access and traffic projection.

The trace uses only the physical range/template reference, not native code,
training, or a saved producer policy. Counts describe the specified serial
cache schedule and append-per-row builder, not OS-level I/O.
"""
from functools import lru_cache
from itertools import combinations

from tests.full_deck_public_chance_reference import PROOF9
from tests.virtual_betting_template_reference import build_reference_template
from tests.virtual_frozen_update_reference import _template_case, scaled_proof9_ranges


def directory_trace():
    """Return the N10 directory append and exact direct-mapped read schedule."""
    deck = tuple(sorted((*PROOF9, 0)))
    if len(set(deck)) != 10:
        raise ValueError('unexpected ten-card fixture')
    template = build_reference_template(_template_case())
    ranges = scaled_proof9_ranges()
    pairs = tuple((i, j, frozenset(a + b))
                  for i, (a, _) in enumerate(ranges[0])
                  for j, (b, _) in enumerate(ranges[1])
                  if set(a).isdisjoint(b))
    if len(pairs) != 3:
        raise ValueError('unexpected private-pair support')

    @lru_cache(None)
    def support(board):
        live = tuple((i, j) for i, j, private in pairs if not set(board) & private)
        return tuple(tuple(sorted({pair[seat] for pair in live})) for seat in (0, 1))

    @lru_cache(None)
    def reveals(board):
        candidates = (combinations(deck, 3) if not board else
                      (board + (card,) for card in deck if card not in board))
        return tuple(next_board for next_board in candidates if support(next_board)[0])

    events = []
    rows = slots = 0

    def visit(node_id, board):
        nonlocal rows, slots
        node = template.nodes[node_id]
        if node.street != len(board):
            raise ValueError('street differs from visible board')
        if node.phase == 'reveal':
            if len(node.edges) != 1:
                raise ValueError('unexpected reveal geometry')
            for next_board in reveals(board):
                visit(node.edges[0].child, next_board)
            return
        if node.phase != 'decision':
            return
        if node.state.player not in (0, 1) or not 2 <= len(node.edges) <= 4:
            raise ValueError('unexpected decision geometry')
        own_rows = []
        for _holding in support(board)[node.state.player]:
            own_rows.append(rows)
            events.append(rows)  # policy access in preorder
            rows += 1
            slots += len(node.edges)
        for edge in node.edges:
            visit(edge.child, board)
        events.extend(own_rows)  # staging in postorder

    visit(template.root, ())
    if (rows, slots, len(events)) != (119196, 281066, 2 * 119196):
        raise ValueError('independent N10 row/slot/trace census differs')
    page_rows, cache_pages, row_bytes = 128, 8, 32
    pages = (rows + page_rows - 1) // page_rows
    cache = [None] * cache_pages  # invalidated after freeze
    phases = []

    def phase(name, trace):
        calls = hits = misses = read_bytes = 0
        for row in trace:
            if not 0 <= row < rows:
                raise ValueError('directory row out of bounds')
            calls += 1
            page = row // page_rows
            slot = page % cache_pages
            if cache[slot] == page:
                hits += 1
            else:
                misses += 1
                cache[slot] = page
                read_bytes += min(page_rows, rows - page * page_rows) * row_bytes
        phases.append({'phase': name, 'logical_reads': calls, 'hits': hits,
                       'misses': misses, 'read_bytes': read_bytes})

    phase('prelude', range(rows))
    for sweep in (1, 2):
        phase(f'sweep_{sweep}_begin', range(rows))
        phase(f'sweep_{sweep}_profile', range(rows))
        phase(f'sweep_{sweep}_walk', events)
    phase('export', range(rows))
    result = {'rows': rows, 'slots': slots, 'record_bytes': row_bytes,
              'page_rows': page_rows, 'cache_pages': cache_pages, 'page_count': pages,
              'append_calls': rows, 'append_bytes': rows * row_bytes,
              'write_calls': pages, 'written_rows': rows,
              'phases': phases, 'logical_reads': sum(p['logical_reads'] for p in phases),
              'hits': sum(p['hits'] for p in phases),
              'misses': sum(p['misses'] for p in phases),
              'read_bytes': sum(p['read_bytes'] for p in phases)}
    if result['logical_reads'] != 10 * rows or result['hits'] + result['misses'] != 10 * rows:
        raise ValueError('directory trace count differs')
    return result
