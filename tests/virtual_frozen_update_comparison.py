"""Saved-only exact full-row comparison for one frozen-update response.

No native process, ranker, betting builder, or update producer is called here.
The returned receipt proves equality to the supplied reference snapshot only;
source authentication and independence belong to the enclosing study.
"""
from fractions import Fraction
from scripts.matrix_free_certificate_budget import Budget
from tests.virtual_frozen_probe_protocol import parse, MAX_BYTES

MAX_ROWS = 868
MAX_SLOTS = 2078
MAX_TOKENS = 8570
MAX_FIELDS = 2 * MAX_SLOTS + MAX_ROWS
FORECAST = {
    'work': 16 * MAX_BYTES + 64 * MAX_TOKENS + 8 * MAX_FIELDS + 4096,
    'entries': 64 * MAX_ROWS + 16 * MAX_SLOTS + 4 * MAX_TOKENS + 8192,
    'created_bits': 32768 * MAX_FIELDS + 8192,
    'integer_bits': 8192,
}


def _bounded_fraction(value):
    if (type(value) is not Fraction or value.numerator.bit_length() > 4096 or
            value.denominator.bit_length() > 4096):
        raise ValueError('reference scalar outside comparison input bounds')


def compare_saved_update(raw, reference, *, limits=None):
    """Check all keys, ordered menus, policies and exact values, including zeros.

    `reference` is the separately produced SampledUpdateResult. This function
    accepts a structural snapshot for synthetic tests; no provenance follows
    from its type or from this comparison. Limits are reduce-only Budget caps.
    """
    budget = Budget(limits)
    for key, value in FORECAST.items():
        if value > budget.limits[key]:
            raise ValueError('whole comparison '+key+' admission exceeded')
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError('comparison raw input bound')
    if len(reference.rows) > MAX_ROWS:
        raise ValueError('comparison reference row bound')
    slots = tokens = 0
    for key, row in reference.rows.items():
        if (key != (row.actor, row.hand_ids, row.history) or type(row.history) is not tuple or
                len(row.history) > 15 or not 1 <= len(row.actions) <= 4):
            raise ValueError('invalid reference row shape')
        if any(type(t) is not str or not t.isascii() or not 0 < len(t) <= 64
               for t in (*row.history, *row.actions)):
            raise ValueError('invalid reference token')
        count = len(row.actions)
        if (len(row.action_exponents) != count or len(row.regret_masses) != count or
                len(row.average_action_masses) != count):
            raise ValueError('incomplete reference action vectors')
        slots += count
        tokens += len(row.history)
        if slots > MAX_SLOTS or tokens > MAX_TOKENS:
            raise ValueError('comparison reference payload bound')
        _bounded_fraction(row.average_mass)
        for value in (*row.regret_masses, *row.average_action_masses):
            _bounded_fraction(value)
    budget.entries(FORECAST['entries'] - 16, 'full comparison scratch')
    budget.charge('parse_and_frame', 16 * len(raw))
    budget.charge('reference_key_tokens', 64 * tokens)
    law = reference.admission.proposal_law
    if law not in ('uniform', 'river_weighted'):
        raise ValueError('unknown reference proposal law')
    candidate = parse(raw, mode='EVAL', proposal={
        'uniform': 'UNIFORM', 'river_weighted': 'RIVER_WEIGHTED'}[law],
        board=reference.admission.board)
    if 'error' in candidate:
        raise ValueError('native update returned an error frame')
    if len(candidate['rows']) != len(reference.rows):
        raise ValueError('complete row count mismatch')
    comparisons = 0

    def equal_ratio(num, den, expected, label):
        nonlocal comparisons
        actual = budget.div(budget.input(num, label), budget.input(den, label), label)
        if budget.compare(actual, budget.input(expected, label), label):
            raise ValueError('exact '+label+' mismatch')
        comparisons += 1

    for row in candidate['rows']:
        key = row['key']
        expected = reference.rows.get((key[0], (key[1], key[2]), key[3]))
        if expected is None:
            raise ValueError('full physical row key mismatch')
        actions = row['actions']
        if tuple(a[1] for a in actions) != tuple(expected.actions):
            raise ValueError('ordered action menu mismatch')
        if tuple(a[0] for a in actions) != tuple(expected.action_exponents):
            raise ValueError('frozen policy mismatch')
        equal_ratio(row['average_mass'], row['average_denominator'],
                    expected.average_mass, 'average mass')
        for index, (_exponent, _token, regret, average) in enumerate(actions):
            equal_ratio(regret, candidate['regret_denominator'],
                        expected.regret_masses[index], 'regret')
            equal_ratio(average, row['average_denominator'],
                        expected.average_action_masses[index], 'average action')
    receipt = budget.receipt()
    if (budget.work > FORECAST['work'] or budget.created_bits > FORECAST['created_bits'] or
            budget.logical_entries > FORECAST['entries'] or budget.max_forecast_bits > FORECAST['integer_bits']):
        raise ArithmeticError('comparison exceeded admitted named envelope')
    return candidate, {'scope': 'exact equality to supplied saved reference snapshot',
                       'rows': len(reference.rows), 'action_slots': slots,
                       'exact_scalar_comparisons': comparisons,
                       'forecast': dict(FORECAST), 'actual': receipt,
                       'native_producer_calls': 0, 'reference_producer_calls': 0}
