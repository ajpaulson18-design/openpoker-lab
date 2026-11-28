"""Add full physical shared-board/private-holding promotion witnesses."""
from itertools import combinations
import struct

from tests.virtual_joint_witness_cases import cases as earlier_cases


def cases():
    yield from earlier_cases()
    for profile in (0, 1):
        yield (f'profile-{profile}-shared-board-distinct-holding', profile,
               ((0, 2140425), (4 if profile else 1, 2140425)))


def validate_shared_board_witnesses():
    from tests.virtual_weighted_joint_reference import build_law, require
    results = []
    for profile in (0, 1):
        side = tuple((hand, int.from_bytes(struct.pack('>d', float(index % 7 + 1 if profile else 1)), 'big'))
                     for index, hand in enumerate(combinations(range(52), 2)))
        law = build_law(tuple(range(52)), (side, side))
        pair = ((0, 2140425), (4 if profile else 1, 2140425))
        first, second = (law.decode(*selector) for selector in pair)
        require(first.board == second.board == (5, 6, 7, 8, 9) and
                first.holding_indices[0] == second.holding_indices[0] == 0 and
                (first.holding_indices[1], second.holding_indices[1]) == (101, 102),
                'independent same-board changed-opponent original holding witness')
        results.append({'profile': profile, 'selectors': pair, 'board': first.board,
            'holding_indices': (first.holding_indices, second.holding_indices),
            'showdown_signs': (first.showdown_sign, second.showdown_sign),
            'scope': 'Independent literal law/rank witness; no native execution or learning claim.'})
    return results
