"""Bound uniform joint-world encounters and integer growth without training.

Encountered Catalog identities and nonzero numerical Store rows are distinct.
This worksheet neither changes nor admits the current two-epoch lifetime.
"""
import argparse
from fractions import Fraction
import json
from math import comb

DEFAULT_OBSERVATIONS = (2, 3, 10, 100, 1000, 10000, 100000, 1000000)
MAX_OBSERVATIONS = 1000000000


def require(value, message):
    if not value:
        raise ValueError(message)


def uniform_cells(deck_size):
    require(type(deck_size) is int and 9 <= deck_size <= 52, 'uniform cell deck domain')
    public = (1, comb(deck_size, 3), comb(deck_size, 3) * (deck_size - 3),
              comb(deck_size, 3) * (deck_size - 3) * (deck_size - 4))
    own = comb(deck_size, 2)
    information = (own, own * comb(deck_size - 2, 3), own * comb(deck_size - 2, 3) * (deck_size - 5),
                   own * comb(deck_size - 2, 3) * (deck_size - 5) * (deck_size - 6))
    require(information == tuple(p * comb(deck_size - visible, 2) for p, visible in zip(public, (0, 3, 4, 5))),
            'uniform own-prefix marginal double count')
    return public, information


def occupancy_bounds(cells, observations):
    """Exact rational bounds for cells*(1-(1-1/cells)**observations).

    Four-term Bonferroni lower, three-term upper, and the Cauchy lower
    require only fixed-degree arithmetic, even for a billion observations.
    """
    require(type(cells) is int and 1 <= cells < (1 << 56) and type(observations) is int and
            0 <= observations <= MAX_OBSERVATIONS, 'bounded occupancy inputs')
    if not observations:
        return Fraction(0), Fraction(0)
    terms = tuple(Fraction(comb(observations, degree), cells ** (degree - 1))
                  for degree in range(1, 5))
    first, second, third, fourth = terms
    lower = max(Fraction(0), first - second, first - second + third - fourth,
                Fraction(cells * observations, cells + observations - 1))
    upper = min(Fraction(cells), Fraction(observations), first - second + third)
    require(0 <= lower <= upper <= min(cells, observations) and
            all(abs(x.numerator).bit_length() <= 256 and x.denominator.bit_length() <= 256
                for x in (*terms, lower, upper)), 'bounded exact occupancy interval')
    return lower, upper


def interval(lower, upper):
    return {'lower': [lower.numerator, lower.denominator], 'upper': [upper.numerator, upper.denominator],
            'integer_floor_lower': lower.numerator // lower.denominator,
            'integer_ceil_upper': -(-upper.numerator // upper.denominator)}


def forecast(observations=DEFAULT_OBSERVATIONS):
    require(type(observations) is tuple and 1 <= len(observations) <= 16 and
            all(type(n) is int and 1 <= n <= MAX_OBSERVATIONS for n in observations) and
            len(set(observations)) == len(observations), 'bounded distinct lifetime requests')
    from scripts.matrix_free_certificate_budget import Budget
    from tests.virtual_betting_template_reference import build_reference_template
    from tests.virtual_frozen_update_reference import _template_case
    source_budget = Budget({'work': 43000000, 'entries': 131072, 'created_bits': 1000000000, 'integer_bits': 4096})
    template = build_reference_template(_template_case(), rule_budget=source_budget)
    decisions, actions = [0] * 4, [0] * 4
    stakes = []
    for index, node in enumerate(template.nodes):
        if node.phase == 'decision':
            street = (0, 3, 4, 5).index(node.street); paths = template.histories[index][0]
            decisions[street] += paths; actions[street] += paths * len(node.edges)
        elif node.phase in ('fold', 'showdown'):
            stakes.append(min(Fraction.from_float(float(x)) for x in node.state.state.committed))
    require(decisions == [6, 32, 116, 280] and actions == [15, 84, 288, 652] and
            max(stakes) == 8 and min(stakes) >= 0, 'fixed independent full-history and utility geometry')
    public, information = uniform_cells(52)
    reports = []
    for count in observations:
        block_low = block_high = row_low = row_high = slot_low = slot_high = Fraction(0)
        streets = []
        for visible, p, k, d, a in zip((0, 3, 4, 5), public, information, decisions, actions):
            bl, bu = occupancy_bounds(p, count); rl, ru = occupancy_bounds(k, count)
            block_low += d * bl; block_high += d * bu
            row_low += d * rl; row_high += d * ru; slot_low += a * rl; slot_high += a * ru
            streets.append({'visible_cards': visible, 'public_cells_per_path': p, 'own_prefix_cells_per_path': k,
                'decision_paths': d, 'action_slots_per_world': a,
                'expected_encountered_public_blocks': interval(d * bl, d * bu),
                'expected_encountered_information_rows': interval(d * rl, d * ru)})
        max_blocks = sum(d * min(count, p) for d, p in zip(decisions, public))
        max_rows = sum(d * min(count, k) for d, k in zip(decisions, information))
        max_slots = sum(a * min(count, k) for a, k in zip(actions, information))
        # Same current logical Catalog ledger; 21 bitmap words even for one
        # holding seen in a new public block. This is not physical memory/RSS.
        catalog_fixed = 1024 + 320 * 434
        catalog_lower, catalog_upper = catalog_fixed + 53 * block_low, catalog_fixed + 53 * block_high
        regret_bits = (count * 16 * (1 << 625)).bit_length()
        average_bits = (count * (1 << 364)).bit_length()
        positive_sum_bits = (4 * count * 16 * (1 << 625)).bit_length()
        scaled_sum_bits = (4 * count * 16 * (1 << (625 + 52))).bit_length()
        reports.append({'observations': count, 'streets': streets,
            'expected_encountered_public_blocks': interval(block_low, block_high),
            'expected_encountered_information_rows': interval(row_low, row_high),
            'expected_encountered_action_slots': interval(slot_low, slot_high),
            'deterministic_encounter_upper': {'public_blocks': max_blocks, 'information_rows': max_rows, 'action_slots': max_slots},
            'catalog_expected_logical_words': interval(catalog_lower, catalog_upper),
            'catalog_deterministic_logical_word_upper': catalog_fixed + 53 * max_blocks,
            'catalog_expected_words_lower_exceeds_current_two_million_cap': catalog_lower > 2000000,
            'hypothetical_eight_byte_units_for_every_encountered_slot': interval(8 * slot_low, 8 * slot_high),
            'conservative_numerator_bits': {'regret': regret_bits, 'average': average_bits,
                'four_action_positive_regret_sum': positive_sum_bits, 'positive_sum_times_q52': scaled_sum_bits},
            'current_numeric_widths_cover_conservative_bounds': regret_bits <= 649 and average_bits <= 382 and
                positive_sum_bits <= 651 and scaled_sum_bits <= 704,
            'current_epoch_limit_allows_lifetime': count <= 2, 'whole_request_admitted': False,
            'attempted_training': False, 'quality_gate': None})
    return {'schema': 'uniform-joint-learning-lifetime-worksheet-v1', 'deck_size': 52,
        'law': 'iid uniform complete legal private-pair/board worlds; all fixed-tree action paths walked',
        'independent_template_receipt': template.receipt, 'reports': reports,
        'numeric_retained_rows': 'Unknown and policy dependent; at most encountered rows. Encounter lower bounds are not numerical Store lower bounds.',
        'integer_argument': 'Fixed Q52, depth and q=P keep denominators fixed at 2^625/2^364; per-coordinate increments are bounded by16 and1 before scaling. Cumulative numerator bounds grow logarithmically in observation count.',
        'scope': 'Scalar architecture worksheet only, not native execution, an RNG implementation, whole-lifetime work admission, allocated memory, convergence or quality. Weighted nonuniform-law expectations are not covered. No caps are changed.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observations', type=int, nargs='*')
    args = parser.parse_args()
    print(json.dumps(forecast(tuple(args.observations) if args.observations else DEFAULT_OBSERVATIONS), indent=2))
