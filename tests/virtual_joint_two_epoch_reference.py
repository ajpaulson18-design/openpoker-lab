"""Two changing-policy joint observations through the independent scalar oracle.

The full expected policy is reconstructed, including implicit defaults. Native
values, pokerlab trainers and production rankers are never numerical oracles.
"""
from hashlib import sha256
from fractions import Fraction

from tests.virtual_dyadic_training_reference import Q
from tests.virtual_grid_update_reference import freeze_grid
from tests.virtual_joint_sample_reference import (
    Request, REGRET_DENOMINATOR, AVERAGE_DENOMINATOR, one_sample, ticket,
)
from tests.virtual_sparse_epoch_reference import _largest_remainder, _uniform_row


def require(value, message):
    if not value:
        raise ValueError(message)


def policy_digest(fixture, policy):
    digest = sha256()
    for key in fixture.ordered_rows():
        for unit in policy[key]:
            digest.update(unit.to_bytes(8, 'little'))
    return digest.hexdigest()


def two_epochs(request, selectors):
    """One request owns both samples; apportion only after each whole raw update.

    The caller must use a fresh admitted Request. Its fixed-Q52 scalar bounds
    apply to every valid Q52 snapshot, including the independently matched E1.
    No literal sweep, independent expectation, RNG or quality run is performed.
    """
    require(type(request) is Request and request.sample_calls == 0 and
            not request.expectation_entered and request.profile == 'uniform',
            'joint two-epoch reference requires a fresh uniform admitted request')
    require(type(selectors) is tuple and len(selectors) == 2 and
            all(type(item) is tuple and len(item) == 2 for item in selectors),
            'joint two fixed selectors')
    # Validate both selectors before any rank or walk. Original holding IDs are
    # decoded by the independently checked exact ticket law.
    samples = tuple(ticket(request.law, *item) for item in selectors)
    fixture = request.fixture
    initial = {key: _uniform_row(len(menu)) for key, menu in fixture.menus.items()}
    require(dict(request.grid.units) == initial, 'joint initial uniform snapshot')
    policy = dict(initial)
    regrets = {}; averages = {}; observations = []
    quantized = staged_rows = staged_slots = 0
    for epoch, sample in enumerate(samples, 1):
        request.grid = freeze_grid(fixture, policy)
        old_policy_hash = policy_digest(fixture, policy)
        raw = one_sample(request, sample)
        require(len(raw.rows) == 434 and sum(len(row.units) for row in raw.rows.values()) == 1039,
                'joint selected-row observation geometry')
        for key, row in raw.rows.items():
            before_r = regrets.get(key, (0,) * len(row.units))
            before_a = averages.get(key, (0,) * len(row.units))
            after_r = tuple(a + b for a, b in zip(before_r, row.regrets))
            after_a = tuple(a + b for a, b in zip(before_a, row.averages))
            require(all(abs(value).bit_length() <= 631 for value in after_r) and
                    all(0 <= value and value.bit_length() <= 366 for value in after_a),
                    'joint exact T2 cumulative integer widths')
            if any(after_r) or any(after_a):
                regrets[key] = after_r; averages[key] = after_a
            else:
                regrets.pop(key, None); averages.pop(key, None)
            if any(row.regrets):
                quantized += 1
                policy[key] = _largest_remainder(tuple(max(value, 0) for value in after_r))
            require(sum(policy[key]) == Q, 'joint next policy exact Q52 partition')
        staged_rows += len(raw.rows); staged_slots += 1039
        require(regrets.keys() == averages.keys() and len(regrets) <= 434 * epoch and
                sum(len(values) for values in regrets.values()) <= 1039 * epoch,
                'joint retained numeric union')
        observations.append({
            'epoch': epoch, 'selector': selectors[epoch - 1], 'board': sample.board,
            'holdings': sample.holdings, 'root': Fraction(raw.root, REGRET_DENOMINATOR),
            'numeric': {key: (regrets[key], averages[key]) for key in regrets},
            'policy': dict(policy), 'input_policy_sha256': old_policy_hash,
            'policy_sha256': policy_digest(fixture, policy),
            'raw_rows': 434, 'raw_slots': 1039, 'quantized_rows': quantized,
            'staged_rows': staged_rows, 'staged_slots': staged_slots,
            'raw_zero_own_nonzero_regret_rows': raw.zero_own_nonzero_regret_rows,
            'raw_zero_policy_nonzero_regret_slots': raw.zero_policy_nonzero_regret_slots,
        })
        del raw
    require(request.sample_calls == 2 and REGRET_DENOMINATOR == 1 << 625 and
            AVERAGE_DENOMINATOR == 1 << 364, 'joint changing-policy sample boundary')
    return initial, tuple(observations)
