"""Independent numeric-rule traversal and sampled-helper CPU census."""
from functools import lru_cache
import json
import statistics
from tests.virtual_joint_cycle_reference import PHASES, require

FAMILIES = ('reach', 'terminal', 'average', 'mix')
COUNTS = (1039, 606, 434, 434)


@lru_cache(maxsize=1)
def numeric_sequence():
    from tests.virtual_betting_template_reference import build_reference_template
    from tests.virtual_frozen_update_reference import _template_case
    template = build_reference_template(_template_case()); sequence = []; visits = reveals = 0
    def visit(source):
        nonlocal visits, reveals
        visits += 1; require(visits <= 1105, 'arithmetic sequence visit cap')
        node = template.nodes[source]
        if node.phase in ('fold', 'showdown'): sequence.append(1); return
        if node.phase == 'reveal':
            reveals += 1; require(len(node.edges) == 1, 'arithmetic sequence reveal arity'); visit(node.edges[0].child); return
        require(node.phase == 'decision' and 2 <= len(node.edges) <= 4, 'arithmetic sequence menu')
        sequence.append(2)
        for edge in node.edges:
            sequence.append(0); visit(edge.child)
        sequence.append(3)
    visit(template.root)
    require(visits == 1105 and reveals == 65 and len(sequence) == 2513 and
            tuple(sequence.count(i) for i in range(4)) == COUNTS, 'arithmetic numeric-rule census')
    return tuple(sequence)


def grouped_sequence(): return tuple(family for family, count in enumerate(COUNTS) for _ in range(count))


def decode(raw, offset, *, synthetic=False, sequence=None):
    prefix = b'JOINT_ARITHMETIC_CYCLES '
    require(type(raw) is bytes and len(raw) <= 8192 and raw.startswith(prefix) and raw.endswith(b'\n'), 'arithmetic cycle frame cap')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate arithmetic cycle key'); result[key] = value
        return result
    value = json.loads(raw[len(prefix):], object_pairs_hook=pairs)
    keys = {'version', 'units', 'variant', 'offset', 'stride', 'cycle_queries', 'maximum_queries', 'thread_id',
            'extra_work', 'metadata_entries', 'metadata_payload_bits', 'families', 'empty_pair_cycles',
            'epoch_helper_calls', 'epoch_sampled_calls', 'epoch_sampled_helper_cycles', 'events', 'diagnostic_actual_work'}
    require(type(value) is dict and set(value) == keys, 'arithmetic cycle exact schema')
    def integer(v): return type(v) is int and 0 <= v < 1 << 64
    require(type(offset) is int and 0 <= offset < 32, 'arithmetic cycle requested offset')
    for key in keys - {'units', 'variant', 'families', 'empty_pair_cycles', 'epoch_helper_calls', 'epoch_sampled_calls', 'epoch_sampled_helper_cycles', 'events'}:
        require(integer(value[key]), 'arithmetic cycle scalar integer')
    require((value['version'], value['units'], value['variant'], value['offset'], value['stride'], value['maximum_queries']) ==
            (1, 'synthetic_cycles' if synthetic else 'cpu_clock_cycles', 'eager', offset, 32, 512) and value['thread_id'] > 0 and
            value['families'] == list(FAMILIES), 'arithmetic cycle contract')
    sequence = numeric_sequence() if sequence is None else sequence
    require(type(sequence) is tuple and len(sequence) == 2513 and all(type(i) is int and 0 <= i < 4 for i in sequence) and
            tuple(sequence.count(i) for i in range(4)) == COUNTS, 'arithmetic independent sequence')
    sampled = [[0] * 4 for _ in range(2)]
    for index, family in enumerate(sequence * 2):
        if index % 32 == offset: sampled[index // 2513][family] += 1
    samples = sum(map(sum, sampled)); queries = 55 + 2 * samples
    require((value['extra_work'], value['metadata_entries'], value['metadata_payload_bits'], value['cycle_queries'], value['diagnostic_actual_work']) ==
            (655360, 2048, 131072, queries, 32768 + 256 * queries + 64 * 5026 + 256 * 22 + 16 * 8192), 'arithmetic cycle resource census')
    calibration = value['empty_pair_cycles']
    require(type(calibration) is list and len(calibration) == 16 and all(map(integer, calibration)), 'arithmetic calibration shape')
    for key in ('epoch_helper_calls', 'epoch_sampled_calls', 'epoch_sampled_helper_cycles'):
        matrix = value[key]
        require(type(matrix) is list and len(matrix) == 2 and all(type(row) is list and len(row) == 4 and all(map(integer, row)) for row in matrix), 'arithmetic matrix shape')
    require(value['epoch_helper_calls'] == [list(COUNTS)] * 2 and value['epoch_sampled_calls'] == sampled, 'arithmetic independent family/offset census')
    events = value['events']; require(type(events) is list and len(events) == 22, 'arithmetic phase count')
    previous = 0
    for event, phase in zip(events, PHASES):
        require(type(event) is list and len(event) == 3 and tuple(event[:2]) == phase and type(event[1]) is int and integer(event[2]) and event[2] >= previous, 'arithmetic phase identity/monotonicity')
        previous = event[2]
    walks = [events[i][2] - events[i - 1][2] for i in (8, 15)]
    cycles = value['epoch_sampled_helper_cycles']
    require(all(sum(row) <= walk for row, walk in zip(cycles, walks)), 'arithmetic sampled helpers disjoint inside walk')
    empty = statistics.median(calibration); proxies = {}
    for family, name in enumerate(FAMILIES):
        total = sum(row[family] for row in cycles); count = sum(row[family] for row in sampled)
        proxies[name] = 32 * max(0, total - count * empty)
    walk_proxy = max(0, sum(walks) - (2 * samples + 2) * empty)
    return {'raw': value, 'walk_cycles': walks, 'median_empty_pair_cycles': empty,
            'empirical_full_helper_cycles_proxies': proxies, 'empirical_walk_cycles_proxy': walk_proxy,
            'empirical_helper_share_proxies': {k: v / walk_proxy if walk_proxy else None for k, v in proxies.items()},
            'scope': 'Disjoint numeric helper bodies include guards/ledger/local allocation. Sampled correction/extrapolation is empirical, not exact pure arithmetic or unprofiled attribution. No cycle conversion or quality claim.'}
