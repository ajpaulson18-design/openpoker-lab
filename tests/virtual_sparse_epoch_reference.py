"""Independent sparse overlay for two fixed-policy uniform CFR epochs.

This reference reuses the literal Fixture and sampled-board raw arithmetic.
It keeps unclipped cumulative integer regrets and exact average numerators;
it does not implement native quantization, stochastic sampling, training
quality, convergence, CFR+, or a wider-deck admission contract.
"""
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType

from tests.virtual_dyadic_training_reference import D, Fixture, Q
from tests.virtual_frozen_sample_reference import admit_sampled_board, build_sampled_reference_context
from tests.virtual_grid_update_reference import freeze_grid, sampled_grid_update
from scripts.matrix_free_certificate_budget import Budget
from tests.full_deck_public_chance_reference import PROOF9

REGRET_DENOMINATOR = 580 << 625
AVERAGE_DENOMINATOR = 580 << 364
MAX_EPOCHS = 2
MAX_REGRET_BITS = 649
MAX_AVERAGE_BITS = 382
MAX_POSITIVE_SUM_BITS = 651
MAX_SCALED_WEIGHT_BITS = 701


def require(value, message):
    if not value:
        raise ValueError(message)


def _uniform_row(size):
    base, extra = divmod(Q, size)
    return tuple(base + (index < extra) for index in range(size))


def _largest_remainder(weights):
    """Apportion Q52 by positive integer weight, ties in stable menu order."""
    require(type(weights) is tuple and weights and
            all(type(weight) is int and weight >= 0 for weight in weights),
            'invalid positive-regret apportionment weights')
    total = sum(weights)
    if total == 0:
        return _uniform_row(len(weights))
    quotients, remainders = [], []
    for weight in weights:
        numerator = weight * Q
        quotient, remainder = divmod(numerator, total)
        quotients.append(quotient)
        remainders.append(remainder)
    left = Q - sum(quotients)
    order = sorted(range(len(weights)), key=lambda index: (-remainders[index], index))
    for index in order[:left]:
        quotients[index] += 1
    require(sum(quotients) == Q and all(0 <= unit <= Q for unit in quotients),
            'Q52 largest-remainder partition')
    return tuple(quotients)


def _integer_at(value, denominator, label):
    require(type(value) is Fraction, label + ' must be an exact Fraction')
    numerator, remainder = divmod(value.numerator * denominator, value.denominator)
    require(remainder == 0, label + ' is not exactly representable')
    return numerator


@dataclass(frozen=True)
class SparseEpochState:
    epoch: int
    regrets: object
    averages: object
    policy: object

    @property
    def default_policy(self):
        return MappingProxyType({'kind': 'uniform-q52', 'units': Q})

    @property
    def numeric_rows(self):
        """Only changed numeric rows; each value is (raw R, cumulative A)."""
        return MappingProxyType({key: (self.regrets[key], self.averages[key])
            for key in self.regrets
            if any(self.regrets[key]) or any(self.averages[key])})

    @property
    def policy_overlays(self):
        """Only policy rows that differ from their implicit uniform default."""
        return MappingProxyType({key: units for key, units in self.policy.items()
            if units != _uniform_row(len(units))})


def implicit_uniform(fixture):
    require(type(fixture) is Fixture and fixture.deck == PROOF9 and
            fixture.denominator == D and fixture.row_count == 24_420 and
            fixture.slot_count == 58_164 and fixture.runouts == 20,
            'sparse epoch contract is fixed proof9 only')
    regrets = {key: (0,) * len(menu) for key, menu in fixture.menus.items()}
    averages = {key: (0,) * len(menu) for key, menu in fixture.menus.items()}
    policy = {key: _uniform_row(len(menu)) for key, menu in fixture.menus.items()}
    return SparseEpochState(0, MappingProxyType(regrets), MappingProxyType(averages),
                            MappingProxyType(policy))


def _check_bounds(fixture, regrets, averages):
    require(regrets.keys() == fixture.menus.keys() and averages.keys() == fixture.menus.keys(),
            'complete numeric row inventory')
    for key, menu in fixture.menus.items():
        r, a = regrets[key], averages[key]
        require(len(r) == len(a) == len(menu), 'numeric row/menu width')
        require(all(type(x) is int and abs(x).bit_length() <= MAX_REGRET_BITS for x in r),
                'cumulative unclipped regret bound')
        require(all(type(x) is int and x >= 0 and x.bit_length() <= MAX_AVERAGE_BITS for x in a),
                'cumulative average bound')
        positive_sum = sum(max(value, 0) for value in r)
        require(positive_sum.bit_length() <= MAX_POSITIVE_SUM_BITS,
                'positive regret sum bound')
        require(all((max(value, 0) * Q).bit_length() <= MAX_SCALED_WEIGHT_BITS for value in r),
                'Q52 scaled regret weight bound')


def apply_epoch(fixture, context, state, board, law='uniform'):
    """Apply one deterministic positive-board observation to a frozen epoch.

    Both seats' raw gradients and averages are computed from the same frozen
    policy. The next policy is derived only after the full joint update.
    """
    require(type(fixture) is Fixture and fixture.deck == PROOF9 and
            fixture.denominator == D and fixture.runouts == 20,
            'sparse epoch supports only fixed proof9 Fixture')
    require(type(state) is SparseEpochState and state.epoch < MAX_EPOCHS,
            'sparse epoch limit is two transitions')
    require(law == 'uniform', 'sparse epoch contract admits uniform proposal only')
    require(context is not None, 'sampled reference context required')
    admission = admit_sampled_board(context, tuple(board), law)
    require(admission.proposal_law == 'uniform' and admission.board_probability == Fraction(1, 2520),
            'implicit uniform board proposal')
    require(admission.compatible_pairs, 'epoch board must have positive full-target support')
    current_grid = freeze_grid(fixture, dict(state.policy))
    sampled, _root = sampled_grid_update(context, admission, current_grid, Budget())

    regrets = {key: list(values) for key, values in state.regrets.items()}
    averages = {key: list(values) for key, values in state.averages.items()}
    for key, (raw, avg) in sampled.items():
        for index, value in enumerate(raw):
            regrets[key][index] += _integer_at(value, REGRET_DENOMINATOR, 'raw regret')
        for index, value in enumerate(avg):
            averages[key][index] += _integer_at(value, AVERAGE_DENOMINATOR, 'prefix average')
    regrets = {key: tuple(values) for key, values in regrets.items()}
    averages = {key: tuple(values) for key, values in averages.items()}
    _check_bounds(fixture, regrets, averages)

    policy = {key: _largest_remainder(tuple(max(value, 0) for value in regrets[key]))
              for key in fixture.menus}
    require(all(len(policy[key]) == len(menu) and sum(policy[key]) == Q
                for key, menu in fixture.menus.items()), 'complete next policy grid')
    return SparseEpochState(state.epoch + 1, MappingProxyType(regrets),
        MappingProxyType(averages), MappingProxyType(policy))


def observe_zero_target_prefix_averages(fixture, context, state, board, law='uniform'):
    """Witness a zero-full-target board's prefix average without a regret step."""
    require(type(state) is SparseEpochState and law == 'uniform',
            'zero-target witness requires the uniform sparse state')
    admission = admit_sampled_board(context, tuple(board), law)
    require(admission.proposal_law == 'uniform' and admission.board_probability == Fraction(1, 2520) and
            not admission.compatible_pairs, 'zero-full-target board required')
    grid = freeze_grid(fixture, dict(state.policy))
    sampled, _root = sampled_grid_update(context, admission, grid, Budget())
    regrets = {key: list(values) for key, values in state.regrets.items()}
    averages = {key: list(values) for key, values in state.averages.items()}
    for key, (raw, avg) in sampled.items():
        require(not any(raw), 'zero full-target produced a regret update')
        for index, value in enumerate(avg):
            averages[key][index] += _integer_at(value, AVERAGE_DENOMINATOR, 'zero-target prefix average')
    regrets = {key: tuple(values) for key, values in regrets.items()}
    averages = {key: tuple(values) for key, values in averages.items()}
    _check_bounds(fixture, regrets, averages)
    require(regrets == dict(state.regrets), 'zero-target changed cumulative regret')
    return SparseEpochState(state.epoch, MappingProxyType(regrets), MappingProxyType(averages), state.policy)


def run_two_positive_epochs(fixture, context, first_board, second_board):
    """Convenience path: E0 uniform, then B1, then B2 on the new frozen grid."""
    state0 = implicit_uniform(fixture)
    state1 = apply_epoch(fixture, context, state0, first_board)
    state2 = apply_epoch(fixture, context, state1, second_board)
    return state0, state1, state2


def overlay_descriptor(state):
    require(type(state) is SparseEpochState, 'sparse epoch state required')
    return {'epoch': state.epoch, 'default': dict(state.default_policy),
            'numeric_rows': dict(state.numeric_rows), 'policy_overlays': dict(state.policy_overlays)}
