"""Independent scalar census for the bounded own-thread observation protocol.

No cycles-to-time conversion. Clock correction is an empirical proxy, not
an exact attribution or a mathematical bound on unobserved CPU cost.
"""
import json
import statistics

PHASES = (('begin', 0), ('range_input', 0), ('template', 0), ('chance', 0), ('owners', 0), ('header', 0),
          ('epoch_begin', 1), ('ticket', 1), ('walk', 1), ('stage', 1), ('release', 1), ('commit', 1), ('snapshot', 1),
          ('epoch_begin', 2), ('ticket', 2), ('walk', 2), ('stage', 2), ('release', 2), ('commit', 2), ('snapshot', 2),
          ('footer', 0), ('publish', 0))


def require(value, message):
    if not value:
        raise ValueError(message)


def decode(raw, offset, variant='eager', synthetic=False):
    require(type(raw) is bytes and len(raw) <= 8192 and raw.startswith(b'JOINT_THREAD_CYCLES ') and raw.endswith(b'\n'), 'cycle frame boundary')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate cycle key'); result[key] = value
        return result
    value = json.loads(raw[len(b'JOINT_THREAD_CYCLES '):], object_pairs_hook=pairs)
    expected = {'version', 'units', 'variant', 'offset', 'stride', 'cycle_queries', 'maximum_queries', 'thread_id',
                'extra_work', 'metadata_entries', 'metadata_payload_bits', 'empty_pair_cycles', 'epoch_read_calls',
                'epoch_sampled_calls', 'epoch_sampled_read_cycles', 'events', 'diagnostic_actual_work'}
    require(set(value) == expected, 'cycle exact schema')
    def integer(number):
        return type(number) is int and 0 <= number < 1 << 64
    for key in expected - {'units', 'variant', 'empty_pair_cycles', 'epoch_read_calls', 'epoch_sampled_calls', 'epoch_sampled_read_cycles', 'events'}:
        require(integer(value[key]), 'cycle scalar integer')
    require(type(offset) is int and 0 <= offset < 4 and variant in ('eager', 'lazy'), 'cycle requested domain')
    require((value['version'], value['units'], value['variant'], value['offset'], value['stride'],
             value['cycle_queries'], value['maximum_queries']) ==
            (1, 'synthetic_cycles' if synthetic else 'cpu_clock_cycles', variant, offset, 4, 489, 512), 'cycle contract')
    require(value['thread_id'] > 0 and
            (value['extra_work'], value['metadata_entries'], value['metadata_payload_bits'], value['diagnostic_actual_work']) ==
            (524288, 2048, 131072, 32768 + 256 * 489 + 256 * 868 + 256 * 22 + 16 * 8192), 'cycle resource census')
    for key, size in (('empty_pair_cycles', 16), ('epoch_read_calls', 2), ('epoch_sampled_calls', 2), ('epoch_sampled_read_cycles', 2)):
        require(type(value[key]) is list and len(value[key]) == size and all(map(integer, value[key])), 'cycle array shape')
    counts = [sum(index % 4 == offset for index in range(epoch * 434, (epoch + 1) * 434)) for epoch in range(2)]
    require(value['epoch_read_calls'] == [434, 434] and value['epoch_sampled_calls'] == counts and sum(counts) == 217, 'cycle read census')
    events = value['events']; require(type(events) is list and len(events) == len(PHASES), 'cycle phase count')
    previous = 0
    for event, phase in zip(events, PHASES):
        require(type(event) is list and len(event) == 3 and tuple(event[:2]) == phase and type(event[1]) is int and
                integer(event[2]) and event[2] >= previous, 'cycle phase schedule/monotonicity')
        previous = event[2]
    walks = [events[i][2] - events[i - 1][2] for i in (8, 15)]
    require(all(read <= walk for read, walk in zip(value['epoch_sampled_read_cycles'], walks)), 'cycle disjoint read bound')
    calibration = statistics.median(value['empty_pair_cycles'])
    sampled = sum(value['epoch_sampled_read_cycles']); walk = sum(walks)
    read_proxy = 4 * max(0, sampled - 217 * calibration)
    walk_proxy = max(0, walk - (2 * 217 + 2) * calibration)
    return {'raw': value, 'walk_cycles': walks, 'sampled_read_cycles': sampled,
            'median_empty_pair_cycles': calibration, 'empirical_full_read_cycles_proxy': read_proxy,
            'empirical_walk_cycles_proxy': walk_proxy,
            'empirical_read_share_proxy': read_proxy / walk_proxy if walk_proxy else None,
            'scope': 'Raw disjoint sampled read-family CPU cycles. Empirical correction/extrapolation is an estimate, not an exact uninstrumented share. No cycle conversion, owner-only attribution or quality claim.'}
