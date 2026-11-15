"""Independently validate coarse baseline phase diagnostics; no solver is called."""
import argparse
import json
from pathlib import Path


MAX_PROFILE_BYTES = 65_536
CAPACITY = 64
MAX_CLOCK_READS = 80
WORK_ALLOWANCE = 8192
METADATA_BYTES_RESERVED = 2048
METADATA_ENTRIES_RESERVED = 256
SCOPE = 'ten-card-bounded-division-T2'
SETUP_PHASES = ('chance_setup', 'owners_setup', 'row_registration', 'freeze', 'prelude')
SWEEP_PHASES = ('policy_build', 'policy_emit', 'walk', 'commit', 'checkpoint')
PHASES = (('plan_preflight', 0), *((phase, 0) for phase in SETUP_PHASES),
          *((phase, sweep) for sweep in (1, 2) for phase in SWEEP_PHASES),
          ('average_export', 0), ('footer', 0))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def schema(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), label+' schema differs')


def natural(value, label, *, positive=False):
    require(type(value) is int and (1 if positive else 0) <= value < 1 << 64,
            label+' must be an unsigned integer')
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate profile JSON key')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('nonfinite profile JSON constant: '+value)


def load_profile(path):
    """Read at most the small sidecar allowance before attempting JSON parsing."""
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_PROFILE_BYTES+1)
        require(0 < len(raw) <= MAX_PROFILE_BYTES, 'profile file byte allowance')
    return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)


def verify_profile(record, admission):
    """Validate independently captured event order, budgets and time partition."""
    schema(record, ('version', 'clock', 'units', 'scope', 'profile_status',
                    'diagnostics', 'budgets', 'outer', 'events'), 'profile')
    require(type(record['version']) is int and record['version'] == 1,
            'profile version differs')
    for key, expected in (('clock', 'steady_clock'), ('units', 'nanoseconds'),
                          ('scope', SCOPE), ('profile_status', 'complete')):
        require(type(record[key]) is str and record[key] == expected, 'profile '+key+' differs')
    require(type(admission) is dict and admission.get('ten_card') is True
            and admission.get('bounded_division') is True
            and type(admission.get('requested_sweeps')) is int and admission['requested_sweeps'] == 2
            and type(admission.get('rows')) is int and admission['rows'] == 119_196
            and type(admission.get('slots')) is int and admission['slots'] == 281_066
            and admission.get('packed_policy', False) is False
            and admission.get('packed_policy_v2', False) is False,
            'profile requires the baseline ten-card bounded-division T2 admission')

    diagnostics = record['diagnostics']
    schema(diagnostics, ('capacity', 'event_count', 'clock_reads', 'max_clock_reads',
                         'metadata_bytes', 'metadata_bytes_reserved',
                         'metadata_entries_reserved', 'work_allowance', 'failed'), 'diagnostics')
    for key in diagnostics.keys()-{'failed'}:
        natural(diagnostics[key], 'diagnostics '+key, positive=True)
    require(diagnostics['failed'] is False, 'profile recorder failed')
    event_count = 2*len(PHASES)
    expected = dict(capacity=CAPACITY, event_count=event_count, clock_reads=1+6+event_count,
                    max_clock_reads=MAX_CLOCK_READS,
                    metadata_bytes_reserved=METADATA_BYTES_RESERVED,
                    metadata_entries_reserved=METADATA_ENTRIES_RESERVED,
                    work_allowance=WORK_ALLOWANCE)
    require(all(diagnostics[key] == value for key, value in expected.items()),
            'profile diagnostic reservation or event census differs')
    require(diagnostics['event_count'] <= diagnostics['capacity']
            and diagnostics['clock_reads'] <= diagnostics['max_clock_reads']
            and diagnostics['metadata_bytes'] <= diagnostics['metadata_bytes_reserved'],
            'profile diagnostic capacity exceeded')

    budgets = record['budgets']
    schema(budgets, ('solver_work', 'with_profile_work', 'solver_entries',
                     'with_profile_entries', 'solver_payload_bits', 'with_profile_payload_bits'), 'budgets')
    for key in budgets:
        natural(budgets[key], 'budget '+key, positive=True)
    for name, admission_key, extra, cap in (
        ('work', 'factored_composed_work', WORK_ALLOWANCE, 2_150_000_000),
        ('entries', 'factored_composed_entries', METADATA_ENTRIES_RESERVED, 2_000_000),
        ('payload_bits', 'factored_composed_payload_bits', 8*METADATA_BYTES_RESERVED, 1_200_000_000),
    ):
        solver = natural(admission.get(admission_key), 'admission '+admission_key, positive=True)
        require(budgets['solver_'+name] == solver
                and budgets['with_profile_'+name] == solver+extra <= cap,
                'profile composed '+name+' budget differs')

    outer = record['outer']
    outer_keys = ('driver_begin_ns', 'driver_end_ns', 'train_begin_ns',
                  'train_end_ns', 'receipts_begin_ns', 'receipts_end_ns')
    schema(outer, outer_keys, 'outer')
    timestamps = [natural(outer[key], key) for key in outer_keys]
    require(all(a <= b for a, b in zip(timestamps, timestamps[1:])),
            'profile outer timestamps are not monotonic')
    require(outer['receipts_end_ns'] > outer['driver_begin_ns'], 'profile total duration is zero')
    events = record['events']
    require(type(events) is list and len(events) == event_count, 'profile event count differs')
    leaves = []
    previous = 0
    for index, (phase, sweep) in enumerate(PHASES):
        pair = events[2*index:2*index+2]
        for event, edge in zip(pair, ('begin', 'end')):
            schema(event, ('phase', 'edge', 'sweep', 'ns'), 'event')
            require(type(event['phase']) is str and event['phase'] == phase
                    and type(event['edge']) is str and event['edge'] == edge
                    and type(event['sweep']) is int and event['sweep'] == sweep,
                    'profile phase, edge or sweep order differs')
            ns = natural(event['ns'], 'event ns')
            require(ns >= previous, 'profile event timestamps are not monotonic')
            previous = ns
        begin, end = (event['ns'] for event in pair)
        owner = 'driver' if index == 0 else 'train'
        require(outer[owner+'_begin_ns'] <= begin <= end <= outer[owner+'_end_ns'],
                'profile phase lies outside its owner interval')
        leaves.append(dict(phase=phase, sweep=sweep, ns=end-begin))

    driver_ns = outer['driver_end_ns']-outer['driver_begin_ns']
    train_ns = outer['train_end_ns']-outer['train_begin_ns']
    receipts_ns = outer['receipts_end_ns']-outer['receipts_begin_ns']
    measured_ns = outer['receipts_end_ns']-outer['driver_begin_ns']
    plan_ns = leaves[0]['ns']
    train_leaf_ns = sum(leaf['ns'] for leaf in leaves[1:])
    train_residual_ns = train_ns-train_leaf_ns
    outside_ns = measured_ns-driver_ns-train_ns-receipts_ns
    require(train_residual_ns >= 0 and outside_ns >= 0, 'profile negative residual')

    def share(ns):
        # Exact fractions avoid implying timer precision through rounded floats.
        return dict(numerator=ns, denominator=measured_ns)

    for leaf in leaves:
        leaf['fraction_of_measured'] = share(leaf['ns'])
    return dict(status='training_phase_profile_verified', scope=SCOPE,
                measured_begin_ns=outer['driver_begin_ns'], measured_end_ns=outer['receipts_end_ns'],
                measured_interval_ns=measured_ns, driver_inclusive_ns=driver_ns,
                plan_preflight_ns=plan_ns, driver_other_ns=driver_ns-plan_ns,
                train_inclusive_ns=train_ns, train_leaf_ns=train_leaf_ns,
                train_residual_ns=train_residual_ns, probe_outputs_ns=receipts_ns,
                unattributed_outside_ns=outside_ns, phases=leaves,
                fractions_of_measured={key: share(ns) for key, ns in (
                    ('driver', driver_ns), ('train_leaves', train_leaf_ns),
                    ('train_residual', train_residual_ns), ('probe_outputs', receipts_ns),
                    ('unattributed_outside', outside_ns))},
                exclusions=['recorder origin to driver_begin', 'process startup and request parsing',
                            'profile JSON sidecar writing', 'Driver destruction and process exit'],
                attribution='walk phases include Chance, State, History and parent work; no per-owner inference',
                native_producer_calls=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--admission', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_profile(load_profile(args.profile), load_profile(args.admission)), sort_keys=True))


if __name__ == '__main__':
    main()
