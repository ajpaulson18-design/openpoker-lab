"""Named literal witnesses; verify selectors independently before candidates."""
from itertools import combinations
import struct


def cases():
    for profile, normalizer in enumerate((1624350, 25908876)):
        loss = 4 if profile else 1
        win = 1966603 if profile else 124950
        for label, pair in (
            ('same-world', ((0, 0), (0, 0))),
            ('boundaries', ((normalizer - 1, 34246079), (0, 0))),
            ('shared-flop-future', ((0, 0), (0, 1))),
            ('sb-loss', ((loss, 0), (loss, 0))),
            ('sb-win', ((win, 0), (win, 0)))):
            yield f'profile-{profile}-{label}', profile, pair


def validate_sign_witnesses():
    from tests.virtual_weighted_joint_reference import build_law, require
    results = []
    for profile in (0, 1):
        side = tuple((hand, int.from_bytes(struct.pack('>d', float(index % 7 + 1 if profile else 1)), 'big'))
                     for index, hand in enumerate(combinations(range(52), 2)))
        law = build_law(tuple(range(52)), (side, side))
        selectors = (0, 4 if profile else 1, 1966603 if profile else 124950)
        worlds = tuple(law.decode(ticket, 0) for ticket in selectors)
        require(tuple(world.showdown_sign for world in worlds) == (0, -1, 1), 'independent tie/loss/win witness signs')
        require(worlds[1].holding_indices == (0, 102) and worlds[2].holding_indices == (102, 0) and
                worlds[1].board == worlds[2].board == (3, 5, 6, 7, 8), 'independent original holding/board sign witnesses')
        results.append({'profile': profile, 'private_tickets': selectors, 'showdown_signs': (0, -1, 1),
                        'normalizer': law.normalizer, 'scope': 'Independent exact-law/rank input witnesses, no native calls.'})
    return results
