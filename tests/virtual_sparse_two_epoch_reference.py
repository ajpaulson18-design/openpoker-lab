"""Whole mathematical observations for two sequential sparse epochs.

Epoch one freezes the uniform E0 grid; epoch two freezes the signed-regret
quantized E1 grid produced by the first board. This remains a finite PROOF9
reference and makes no native admission, training-quality, or convergence claim.
"""
from dataclasses import replace
from fractions import Fraction

from tests.virtual_dyadic_training_reference import Fixture
from tests.virtual_frozen_sample_reference import admit_sampled_board
from tests.virtual_grid_update_reference import freeze_grid, sampled_grid_update
from scripts.matrix_free_certificate_budget import Budget
from tests.full_deck_public_chance_reference import PROOF9
from tests.virtual_sparse_epoch_reference import (
    SparseEpochState,
    apply_epoch,
    implicit_uniform,
    observe_zero_target_prefix_averages,
)


def _measure_observation(fixture, context, state, board):
    admission = admit_sampled_board(context, tuple(board), "uniform")
    if admission.proposal_law != "uniform" or admission.board_probability != Fraction(1, 2520):
        raise ValueError("two-epoch reference accepts only uniform public-board proposals")
    policy = freeze_grid(fixture, dict(state.policy))
    sampled, root = sampled_grid_update(context, admission, policy, Budget())
    return {
        "root": root,
        "raw_rows": len(sampled),
        "raw_slots": sum(len(raw) for raw, _averages in sampled.values()),
        "quantized_rows": sum(any(raw) for raw, _averages in sampled.values()),
        "zero_target": not admission.compatible_pairs,
    }


def _next_state(fixture, context, state, board, zero_target):
    if zero_target:
        # The sampled zero-target board still carries earlier-prefix average
        # contributions. Keep the established exact oracle and advance the
        # accepted observation count without changing its E0/E1 grid semantics.
        observed = observe_zero_target_prefix_averages(fixture, context, state, board)
        return replace(observed, epoch=state.epoch + 1)
    return apply_epoch(fixture, context, state, board, law="uniform")


def two_epochs(fixture: Fixture, context, first, second):
    """Return ``(E0, observations)`` for two sequential uniform observations.

    Each observation dictionary has ``state`` (the post-observation complete
    state), exact ``root`` value, and counts ``raw_rows``, ``raw_slots``, and
    ``quantized_rows``. A zero-full-target board advances the observation epoch,
    leaves regret and policy unchanged, and may still add prefix averages.
    """
    if type(fixture) is not Fixture or fixture.deck != PROOF9:
        raise ValueError("two-epoch reference requires the fixed PROOF9 Fixture")
    state0 = implicit_uniform(fixture)
    observations = []
    state = state0
    for board in (tuple(first), tuple(second)):
        measured = _measure_observation(fixture, context, state, board)
        state = _next_state(fixture, context, state, board, measured["zero_target"])
        observations.append({
            "state": state,
            "root": measured["root"],
            "raw_rows": measured["raw_rows"],
            "raw_slots": measured["raw_slots"],
            "quantized_rows": measured["quantized_rows"],
        })
    return state0, tuple(observations)
