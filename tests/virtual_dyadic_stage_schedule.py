"""Independent, rank-free packed-stage write schedule for the named fixtures.

This models write calls, not operating-system I/O. It imports no native producer
or its pager. One invocation covers initialization and both complete sweeps.
"""
from functools import lru_cache
from itertools import combinations

from tests.full_deck_public_chance_reference import PROOF9
from tests.virtual_betting_template_reference import build_reference_template
from tests.virtual_frozen_update_reference import _template_case, scaled_proof9_ranges

PAGE_WORDS = 4096


def stage_schedule(*, ten_card=False, virtual_zero=False, sweeps=2):
    """Return independently reconstructed direct and dirty-run write receipts.

    The dirty-run model owns one page buffer per field. A page change flushes
    only contiguous marked runs. Both fields share one global coverage bitmap,
    including when their extents occupy the same physical page. No hand ranking,
    strategy arithmetic, training, file writes, or production code is used.
    """
    if sweeps!=2 and (sweeps!=3 or ten_card or not virtual_zero):
        raise ValueError('unsupported staged sweep schedule')
    deck = tuple(sorted((*PROOF9, 0))) if ten_card else tuple(PROOF9)
    if len(set(deck)) != (10 if ten_card else 9):
        raise ValueError('unexpected named deck')
    template = build_reference_template(_template_case())
    ranges = scaled_proof9_ranges()
    pairs = tuple((i, j, frozenset(a + b))
                  for i, (a, _) in enumerate(ranges[0])
                  for j, (b, _) in enumerate(ranges[1])
                  if set(a).isdisjoint(b))

    @lru_cache(None)
    def support(board):
        live = tuple((i, j) for i, j, private in pairs if not set(board) & private)
        return tuple(tuple(sorted({p[a] for p in live})) for a in (0, 1))

    @lru_cache(None)
    def reveals(board):
        candidates = (combinations(deck, 3) if not board else
                      (board + (card,) for card in deck if card not in board))
        return tuple(b for b in candidates if support(b)[0])

    @lru_cache(None)
    def suffix(node_id):
        node = template.nodes[node_id]
        return int(node.phase == 'decision') + max(
            (suffix(edge.child) for edge in node.edges), default=0)

    if suffix(template.root) != 12:
        raise ValueError('unexpected decision horizon')
    value_bits = 644 if ten_card else 642
    average_words = regret_words = rows = slots = 0
    postorder = []
    preorder = []

    def visit(node_id, board, past):
        nonlocal average_words, regret_words, rows, slots
        node = template.nodes[node_id]
        if node.street != len(board):
            raise ValueError('street mismatch')
        if node.phase == 'reveal':
            if len(node.edges) != 1:
                raise ValueError('reveal edge count')
            for board_next in reveals(board):
                visit(node.edges[0].child, board_next, past)
            return
        if node.phase != 'decision':
            return
        actor = node.state.player
        menu = len(node.edges)
        if actor not in (0, 1) or not 2 <= menu <= 4:
            raise ValueError('decision shape')
        avg_shift = 1 + 52 * (11 - past[actor])
        regret_shift = 52 * (12 - past[1 - actor] - suffix(node_id))
        if not 0 <= min(avg_shift, regret_shift) <= max(avg_shift, regret_shift) < value_bits:
            raise ValueError('invalid compact shift')
        avg_stride = (value_bits - avg_shift + 63) // 64
        regret_stride = (value_bits - regret_shift + 63) // 64
        current = []
        for _ in support(board)[actor]:
            record = (average_words, regret_words, avg_stride, regret_stride, menu)
            current.append(record)
            preorder.append(record)
            average_words += menu * avg_stride
            regret_words += menu * regret_stride
            rows += 1
            slots += menu
        next_past = list(past)
        next_past[actor] += 1
        for edge in node.edges:
            visit(edge.child, board, next_past)
        postorder.extend(current)

    visit(template.root, (), (0, 0))
    expected = ((119196, 281066, 1295812, 1666910) if ten_card else
                (24420, 58164, 258694, 348036))
    if (rows, slots, average_words, regret_words) != expected or len(postorder) != rows:
        raise ValueError('independent row or extent census differs')
    image_words = average_words + regret_words
    seen = bytearray((image_words + 7) // 8)
    dirty = [None, None]
    runs = flushed_words = stage_calls = 0

    def flush(buffer):
        nonlocal runs, flushed_words
        if buffer is None:
            return
        _, mask = buffer
        # Start bits of each disjoint run, without writing clean words.
        runs += (mask & ~(mask << 1)).bit_count()
        flushed_words += mask.bit_count()

    def stage(field, offset, count):
        nonlocal stage_calls
        if not count or offset < 0 or offset + count > image_words:
            raise ValueError('invalid stage range')
        # Global coverage survives eviction and is shared across both fields.
        for word in range(offset, offset + count):
            byte, bit = divmod(word, 8)
            if seen[byte] & (1 << bit):
                raise ValueError('overlapping stage range')
            seen[byte] |= 1 << bit
        stage_calls += 1
        while count:
            page, at = divmod(offset, PAGE_WORDS)
            extent = min(count, PAGE_WORDS - at)
            old = dirty[field]
            if old is None or old[0] != page:
                flush(old)
                old = (page, 0)
            marks = ((1 << extent) - 1) << at
            if old[1] & marks:
                raise ValueError('dirty buffer overlap')
            dirty[field] = (page, old[1] | marks)
            offset += extent
            count -= extent

    for avg_offset, regret_offset, avg_stride, regret_stride, menu in postorder:
        for action in range(menu):
            stage(1, average_words + regret_offset + action * regret_stride, regret_stride)
            stage(0, avg_offset + action * avg_stride, avg_stride)
    for buffer in dirty:
        flush(buffer)
    if (stage_calls, flushed_words) != (2 * slots, image_words):
        raise ValueError('incomplete staged image')
    if any(byte != 255 for byte in seen[:-1]):
        raise ValueError('coverage gap')
    if seen[-1] != (1 << ((image_words - 1) % 8 + 1)) - 1:
        raise ValueError('coverage gap or padding mark')
    initial_calls = 0 if virtual_zero else (image_words + PAGE_WORDS - 1) // PAGE_WORDS
    result = {'rows': rows, 'slots': slots, 'average_words': average_words,
              'regret_words': regret_words, 'image_words': image_words,
              'initialization_calls': initial_calls, 'per_sweep_stage_calls': stage_calls,
              'per_sweep_dirty_runs': runs, 'direct_write_calls': initial_calls + sweeps*stage_calls,
              'batched_write_calls': initial_calls + sweeps*runs,
              'written_words': (sweeps+int(not virtual_zero))*image_words, 'sweeps': sweeps}
    expected_calls = ((1124264, 18836, 5925444) if ten_card else
                      (232656, 3954, 1213460)) if virtual_zero else (
                      (1124988, 19560, 8888166) if ten_card else (232805, 4103, 1820190))
    if sweeps==3:
        expected_calls = (348984, 5931, 1820190)
    if (result['direct_write_calls'], result['batched_write_calls'], result['written_words']) != expected_calls:
        raise ValueError('independent stage schedule differs from fixed fixture')
    if virtual_zero:
        # Two eight-page direct-mapped banks; zero-image accesses are logical
        # reads but do not populate or touch the physical cache. Both commits
        # invalidate all tags, including before the export phase.
        tags = [None] * 16
        logical_reads = logical_words = virtual_reads = virtual_words = 0
        misses = hits = physical_words = 0
        epochs = []

        def epoch(name, records, fields, zero=False):
            nonlocal logical_reads, logical_words, virtual_reads, virtual_words
            nonlocal misses, hits, physical_words
            before = (logical_reads, logical_words, virtual_reads, virtual_words,
                      hits, misses, physical_words)
            for avg_offset, regret_offset, avg_stride, regret_stride, menu in records:
                for action in range(menu):
                    for field in fields:
                        if field == 0:
                            offset, count = avg_offset + action * avg_stride, avg_stride
                        else:
                            offset = average_words + regret_offset + action * regret_stride
                            count = regret_stride
                        logical_reads += 1
                        logical_words += count
                        if zero:
                            virtual_reads += 1
                            virtual_words += count
                            continue
                        end = offset + count
                        while offset < end:
                            page, at = divmod(offset, PAGE_WORDS)
                            slot = field * 8 + page % 8
                            if tags[slot] == page:
                                hits += 1
                            else:
                                misses += 1
                                tags[slot] = page
                                physical_words += min(PAGE_WORDS, image_words - page * PAGE_WORDS)
                            offset += min(end - offset, PAGE_WORDS - at)
            after = (logical_reads, logical_words, virtual_reads, virtual_words,
                     hits, misses, physical_words)
            epochs.append(dict(zip(('name','logical_reads','logical_words','virtual_reads',
                                    'virtual_words','cache_hits','cache_misses','physical_words'),
                                   (name, *(a - b for a, b in zip(after, before))))))

        for sweep in range(1, sweeps+1):
            epoch(f'sweep_{sweep}_policy', preorder, (1,), zero=sweep == 1)
            epoch(f'sweep_{sweep}_stage', postorder, (1, 0), zero=sweep == 1)
            tags[:] = [None] * 16
        epoch('export_average', preorder, (0,))
        result.update({'read_epochs': epochs, 'logical_read_calls': logical_reads,
                       'logical_read_words': logical_words, 'virtual_read_calls': virtual_reads,
                       'virtual_read_words': virtual_words, 'cache_hits': hits,
                       'cache_misses': misses, 'physical_read_words': physical_words})
        expected_reads = ((1967462, 10555076, 843198, 4629632, 1498, 6130244)
                          if ten_card else (407148, 2168226, 174492, 954766, 306, 1242654))
        actual_reads = (logical_reads, logical_words, virtual_reads, virtual_words, misses, physical_words)
        if sweeps==3:
            expected_reads = (581640,3122992,174492,954766,548,2223164)
        if actual_reads != expected_reads:
            raise ValueError(f'independent virtual-zero read schedule differs: {actual_reads}')
    return result
