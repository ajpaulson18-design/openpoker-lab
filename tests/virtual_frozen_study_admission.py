"""Rank-free whole-batch census for the fixed two-law update proof.

This helper admits reference calls and bounds transport, not a native producer,
training loop, Python RSS, or the still separate aggregation/exporter.
"""
from fractions import Fraction
from tests.virtual_frozen_sample_reference import (
    build_sampled_reference_context, admit_sampled_board,
)
from tests.virtual_frozen_probe_protocol import MAX_BYTES, DECK, request

BOARD_COUNT = 2520
CALL_COUNT = 5040
WORST_BOARD = (16, 17, 24, 32, 48)
MAX_STUDY_REFERENCE_WORK = 5040 * 500_000_000 + 150_000_000
MAX_STUDY_REFERENCE_CREATED_BITS = 5040 * 16_000_000_000 + 1_000_000_000
MAX_NATIVE_WORK = (5040 + 2) * 500_000_000
MAX_RAW_NATIVE_BYTES = (5040 + 2) * MAX_BYTES


def proposal_shape(board, law, deck):
    """Unreduced native-law widths, derived here without native helpers.

    Python Fraction canonicalizes q; the native forecast uses unreduced q.
    Reconstruct that representation explicitly instead of treating reduced
    numerator widths as an upper bound for the native expression.
    """
    if law not in ('uniform', 'river_weighted') or tuple(deck) != DECK:
        raise ValueError('only the two fixed PROOF9 proposal laws are supported')
    request('ADMIT', 'UNIFORM' if law == 'uniform' else 'RIVER_WEIGHTED', board)
    if law == 'uniform':
        return ((1, 1), (1, 84), (1, 504), (1, 2520))
    weights = {card: index + 1 for index, card in enumerate(sorted(deck))}
    after_flop = sum(w for card, w in weights.items() if card not in board[:3])
    after_turn = sum(w for card, w in weights.items() if card not in board[:4])
    return ((1, 1), (5 * after_flop, 12600),
            (after_turn, 12600), (weights[board[-1]], 12600))


def census_study_admission(context=None):
    """Enumerate every admission once, retaining totals and maxima only.

    No update/reference result, rank, native subprocess or expanded row key is
    created here. The original context setup is counted once in totals.
    """
    context = build_sampled_reference_context() if context is None else context
    deck = tuple(sorted({c for b in context.physical.proposals for c in b}))
    if len(context.physical.proposals) != BOARD_COUNT or len(deck) != 9:
        raise ValueError('fixed proposal universe changed')
    reference_work = context.setup_receipt['work']
    reference_bits = context.setup_receipt['created_bits']
    laws = {}
    for law, wire_law in [('uniform', 'UNIFORM'), ('river_weighted', 'RIVER_WEIGHTED')]:
        worst = proposal_shape(WORST_BOARD, law, deck)
        maxima = {'work': 0, 'entries': 0, 'created_bits': 0, 'integer_bits': 0}
        rows = slots = tokens = calls = rank_calls = 0
        total_q = Fraction(0)
        suffix_q = {}
        for board in context.physical.proposals:
            shape = proposal_shape(board, law, deck)
            # All board dependence in the native forecast is in these positive
            # q numerators/denominators and their widths. Unfiltered geometry,
            # range weights, money bounds and visibility depth are fixed.
            if any(n > wn or d != wd for (n, d), (wn, wd) in zip(shape, worst)):
                raise ArithmeticError('worst-law dominance failed')
            q = Fraction(*shape[-1])
            total_q += q
            for length, pair in zip((0, 3, 4, 5), shape):
                prefix = board[:length]
                record = suffix_q.setdefault(prefix, [Fraction(0), Fraction(*pair)])
                if record[1] != Fraction(*pair):
                    raise ArithmeticError('prefix law depends on hidden future')
                record[0] += q
            admission = admit_sampled_board(context, board, law)
            if admission.board_probability != q:
                raise ArithmeticError('independent board-law mismatch')
            reference_work += admission.work_upper
            reference_bits += admission.created_bits_upper
            rows += admission.row_count_upper
            slots += admission.action_slots_upper
            tokens += admission.history_tokens_upper
            rank_calls += admission.rank_calls_upper
            for field, value in [('work', admission.work_upper), ('entries', admission.entries_upper),
                                 ('created_bits', admission.created_bits_upper),
                                 ('integer_bits', admission.max_integer_bits_upper)]:
                maxima[field] = max(maxima[field], value)
            if len(request('EVAL', wire_law, board)) > 1025:
                raise ArithmeticError('request framing cap exceeded')
            calls += 1
        if total_q != 1 or any(total != declared for total, declared in suffix_q.values()):
            raise ArithmeticError('all-outcome prefix probability identity failed')
        if rows != 107080:
            raise ArithmeticError('row-record census changed')
        laws[law] = {'calls': calls, 'row_records': rows, 'action_slot_records': slots,
                     'history_token_records': tokens, 'rank_calls_upper': rank_calls,
                     'max_reference_call': maxima, 'proposal_prefixes': len(suffix_q),
                     'worst_board': WORST_BOARD, 'worst_unreduced_ratios': worst}
    if reference_work > MAX_STUDY_REFERENCE_WORK or reference_bits > MAX_STUDY_REFERENCE_CREATED_BITS:
        raise ValueError('whole-reference study cap exceeded')
    return {'version': 'virtual-frozen-study-admission-v1', 'laws': laws,
            'reference_work_upper': reference_work, 'reference_created_bits_upper': reference_bits,
            'native_requested_work_upper': MAX_NATIVE_WORK,
            'native_raw_output_bytes_upper': MAX_RAW_NATIVE_BYTES,
            'context_setup_count': 1, 'native_eval_calls': 0, 'reference_update_calls': 0,
            'scope': 'rank-free admission census and proposal-width dominance only; aggregation, q-free oracle and export admission remain separate'}
