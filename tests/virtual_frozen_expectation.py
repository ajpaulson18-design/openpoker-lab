"""Exact, saved-only PROOF9 expectation accumulator; no producer execution.

Regrets share one proposal-corrected denominator per law. Each average row has
one denominator because its visible prefix, policy reach and q(P) are fixed.
Accumulate integers rather than repeatedly multiplying rational denominators.
"""
from dataclasses import dataclass
from fractions import Fraction
from scripts.matrix_free_certificate_budget import Budget
from tests.virtual_frozen_probe_protocol import DECK
from tests.virtual_frozen_study_admission import proposal_shape
from tests.virtual_frozen_update_comparison import compare_saved_update

ROWS, SLOTS, TOKENS, BOARDS = 24420, 58164, 249662, 2520
ROW_RECORDS = 107080
SLOT_RECORDS = 4 * ROW_RECORDS
VALUES = 2 * SLOTS + ROWS
VISIT_VALUES = 2 * SLOT_RECORDS + ROW_RECORDS
FORECAST = {
    'work': 64 * 15 * ROW_RECORDS + 32 * SLOT_RECORDS + 12 * VISIT_VALUES + 8 * VALUES + 100000,
    'entries': 32 * ROWS + 8 * SLOTS + 4 * TOKENS + 8 * BOARDS + 8192,
    'created_bits': (6000 * VISIT_VALUES + 32768 * VALUES +
                     2048 * ROW_RECORDS + 8192 * BOARDS + 1000000),
    'integer_bits': 8192,
}

@dataclass
class _Row:
    actions: tuple
    exponents: tuple
    regret: list
    average: list
    mass: int
    denominator: int

class ExactExpectation:
    """Single-use accumulator; any failed add/finish poisons all later access.

    Raw parsing/comparison is charged by its separate per-call allowance.
    This persistent meter covers aggregation and final expected-value comparison.
    No partial numeric result is exposed through the public API.
    """
    def __init__(self, law, *, limits=None):
        if law not in ('uniform', 'river_weighted'):
            raise ValueError('unsupported expectation law')
        self._budget = Budget(limits)
        for name, value in FORECAST.items():
            if value > self._budget.limits[name]:
                raise ValueError('whole expectation '+name+' admission exceeded')
        self._budget.entries(FORECAST['entries'] - 32, 'complete expectation state')
        self._law = law
        self._rows = {}
        self._boards = set()
        self._slots = self._tokens = self._row_visits = self._slot_visits = 0
        self._regret_denominator = None
        self._closed = False

    def _open(self):
        if self._closed:
            raise ValueError('expectation owner is consumed or failed')

    def _int(self, value):
        if type(value) is not int or value.bit_length() > 512:
            raise ValueError('expectation integer storage bound')
        return self._budget.input(value, 'aggregate integer input')

    def _product(self, a, b):
        if max(1,a.bit_length()) + max(1,b.bit_length()) > 512:
            raise ValueError('expectation product width admission')
        return self._budget.mul(self._int(a), self._int(b), 'aggregate integer product').numerator

    def _sum(self, a, b):
        if max(a.bit_length(),b.bit_length()) + 1 > 512:
            raise ValueError('expectation sum width admission')
        return self._budget.add(self._int(a), self._int(b), 'aggregate integer sum').numerator

    def _check_forecast(self):
        for field, actual in [('work',self._budget.work),('entries',self._budget.logical_entries),
                              ('created_bits',self._budget.created_bits),('integer_bits',self._budget.max_forecast_bits)]:
            if actual > FORECAST[field]:
                raise ArithmeticError('expectation exceeded whole-batch '+field+' forecast')

    def add(self, raw, reference):
        self._open()
        try:
            if reference.admission.proposal_law != self._law:
                raise ValueError('expectation proposal mismatch')
            board = reference.admission.board
            if board in self._boards or len(self._boards) >= BOARDS:
                raise ValueError('duplicate or excessive expectation board')
            candidate, comparison = compare_saved_update(raw, reference)
            qnum, qden = proposal_shape(board, self._law, DECK)[-1]
            quotient = self._budget.div(self._int(candidate['regret_denominator']),
                                        self._int(qnum), 'cancel board proposal numerator')
            if quotient.denominator != 1:
                raise ValueError('native regret denominator lacks proposal factor')
            denominator = self._product(quotient.numerator, qden)
            if self._regret_denominator is None:
                self._regret_denominator = denominator
            elif self._regret_denominator != denominator:
                raise ValueError('proposal-corrected regret denominator changed')
            for incoming in candidate['rows']:
                key = incoming['key']
                count = len(incoming['actions'])
                self._row_visits += 1
                self._slot_visits += count
                if self._row_visits > ROW_RECORDS or self._slot_visits > SLOT_RECORDS:
                    raise ValueError('expectation record census exceeded')
                self._budget.charge('aggregate_key_tokens', 64 * len(key[3]))
                self._budget.charge('aggregate_action_records', 32 * count)
                average_den = self._product(incoming['average_denominator'], qden)
                actions = tuple(a[1] for a in incoming['actions'])
                exponents = tuple(a[0] for a in incoming['actions'])
                row = self._rows.get(key)
                if row is None:
                    if len(self._rows) >= ROWS or self._slots + count > SLOTS or self._tokens + len(key[3]) > TOKENS:
                        raise ValueError('expectation retained geometry exceeded')
                    self._slots += count
                    self._tokens += len(key[3])
                    row = _Row(actions, exponents, [0]*count, [0]*count, 0, average_den)
                    self._rows[key] = row
                elif (row.actions != actions or row.exponents != exponents or row.denominator != average_den):
                    raise ValueError('same visible row changed policy or average denominator')
                row.mass = self._sum(row.mass, self._product(incoming['average_mass'], qnum))
                for index, (_exp, _token, regret, average) in enumerate(incoming['actions']):
                    row.regret[index] = self._sum(row.regret[index], regret)
                    row.average[index] = self._sum(row.average[index], self._product(average, qnum))
            self._boards.add(board)
            self._check_forecast()
            return comparison
        except BaseException:
            self._closed = True
            raise

    def finish(self, expected):
        self._open()
        self._closed = True
        if (len(self._boards) != BOARDS or len(self._rows) != ROWS or
                self._slots != SLOTS or self._row_visits != ROW_RECORDS):
            raise ValueError('expectation coverage incomplete')
        if len(expected.rows) != ROWS:
            raise ValueError('q-free expected row coverage mismatch')
        comparisons = 0
        def equal(num, den, target):
            nonlocal comparisons
            if (type(target) is not Fraction or target.numerator.bit_length() > 4096 or
                    target.denominator.bit_length() > 4096):
                raise ValueError('q-free expected integer input bound')
            actual = self._budget.div(self._int(num),self._int(den),'aggregate exact value')
            if self._budget.compare(actual,self._budget.input(target,'q-free scalar'),'expectation equality'):
                raise ValueError('exact q-free expectation mismatch')
            comparisons += 1
        for key,row in self._rows.items():
            other = expected.rows.get((key[0],(key[1],key[2]),key[3]))
            if other is None or row.actions != other.actions or row.exponents != other.action_exponents:
                raise ValueError('q-free expected row/menu/profile mismatch')
            equal(row.mass,row.denominator,other.average_reach_mass)
            for index in range(len(row.actions)):
                equal(row.regret[index],self._regret_denominator,other.regret_masses[index])
                equal(row.average[index],row.denominator,other.average_action_masses[index])
        receipt = self._budget.receipt()
        self._check_forecast()
        return {'law':self._law,'boards':len(self._boards),'rows':len(self._rows),
                'action_slots':self._slots,'exact_scalar_comparisons':comparisons,
                'forecast':dict(FORECAST),'actual':receipt,'native_producer_calls':0,
                'reference_producer_calls':0,'scope':'full saved contribution expectation equals supplied q-free snapshot'}
