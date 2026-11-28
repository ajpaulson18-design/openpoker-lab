"""Scalar full52 information universe for the existing fixed betting rules.

No native code, worlds, policies, sampling or learning are executed. This is
an architecture worksheet, not an admission or a lower bound on compressed
storage. Betting-path counts come from the independent numeric-rule template.
"""
from math import comb
import json

from tests.virtual_betting_template_reference import build_reference_template
from tests.virtual_frozen_update_reference import _template_case


def forecast():
    template = build_reference_template(_template_case())
    lengths = (0, 3, 4, 5)
    decisions, actions = [0] * 4, [0] * 4
    for index, node in enumerate(template.nodes):
        if node.phase == 'decision':
            street = lengths.index(node.street)
            paths = template.histories[index][0]
            decisions[street] += paths
            actions[street] += paths * len(node.edges)
    if decisions != [6, 32, 116, 280] or actions != [15, 84, 288, 652]:
        raise ValueError('fixed numeric betting template changed')
    prefixes = (1, comb(52, 3), comb(52, 3) * 49, comb(52, 3) * 49 * 48)
    holdings = tuple(comb(52 - length, 2) for length in lengths)
    streets = [dict(visible_cards=length, public_prefixes=prefix,
                    supported_own_holdings=hands, both_seat_decision_paths=rows,
                    both_seat_action_slots=slots, rows=prefix * hands * rows,
                    action_slots=prefix * hands * slots)
               for length, prefix, hands, rows, slots in
               zip(lengths, prefixes, holdings, decisions, actions)]
    total_rows = sum(street['rows'] for street in streets)
    total_slots = sum(street['action_slots'] for street in streets)
    return dict(schema='fixed-template-full52-information-universe-v1',
                source='Independent numeric betting rules and scalar combinatorics; complete positive 1326-hand ranges.',
                streets=streets, total_rows=total_rows, total_action_slots=total_slots,
                dense_eight_byte_action_units=8 * total_slots,
                optimistic_suit_orbit_row_lower_bound=(total_rows + 23) // 24,
                suit_scope='Only suit-symmetric inputs admit a 24-suit quotient; arbitrary weighted ranges do not.',
                scope='No native execution, allocation, admission, sampling, training or quality. Dense units are not an information-theoretic storage minimum.',
                numeric_rule_receipt=template.receipt)


if __name__ == '__main__':
    print(json.dumps(forecast(), indent=2))
