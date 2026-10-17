"""Conservative admission before constructing the full-board preflop tree.

These are modeled loop/element envelopes, not bytecode, time or memory bounds.
No legal-action generator is duplicated: the forecast deliberately overbounds
the existing preflop builder, then the adapter checks its actual census.
"""
from .preflop_full_board_equity import BOARDS_PER_PAIR, FullBoardEquities
from .preflop_tree import PreflopConfig

MAX_DECISION_NODES = 10_000
MAX_PUBLIC_STATES = 250_000
MAX_ACTION_SLOTS = 1_000_000
MAX_MODELED_LOOP_ENTRIES = 500_000_000

_DEFAULT_CONFIG = {'small_blind': .5, 'big_blind': 1, 'starting_stack': 3,
                   'raise_sizes': (.5,), 'max_raises': 1, 'include_all_in': True}


def options(config, iterations, algorithm, resource_model):
    if type(iterations) is not int or not 10 <= iterations <= 10_000:
        raise ValueError('Iterations must be an integer from 10 to 10,000')
    if type(algorithm) is not str or algorithm not in ('vanilla', 'dcfr', 'cfrplus'):
        raise ValueError('Algorithm must be vanilla, dcfr or cfrplus')
    if type(resource_model) is not str or resource_model not in ('source-inclusive', 'prepared-counts'):
        raise ValueError('Resource model must be source-inclusive or prepared-counts')
    if config is None:
        return PreflopConfig(**_DEFAULT_CONFIG)
    if type(config) is PreflopConfig:
        return config
    if type(config) is dict:
        return PreflopConfig.from_dict({**_DEFAULT_CONFIG, **config})
    raise TypeError('Config must be a mapping or a PreflopConfig')


def admit_prepared(equities, config, iterations, algorithm, resource_model,
                   *, world_indexing='categorical'):
    config = options(config, iterations, algorithm, resource_model)
    if type(world_indexing) is not str or world_indexing not in ('categorical', 'pair-mean'):
        raise ValueError('World indexing must be categorical or pair-mean')
    if type(equities) is not FullBoardEquities:
        raise TypeError('Equities must be an exact FullBoardEquities table with trusted counts')
    equities.validate()
    pairs = len(equities.pairs)
    candidates = len(equities.hands[0]) * len(equities.hands[1])
    categorical_worlds = 3 * pairs
    worlds = pairs if world_indexing == 'pair-mean' else categorical_worlds
    branches = len(config.raise_sizes) + int(config.include_all_in)
    # Every raise, including an incomplete all-in, increments raises_made.
    # Only the initial SB call can create a same-depth BB option node; all
    # other non-raise actions fold or settle. Deduplication, stack clipping,
    # and closed raise rights only reduce this two-root geometric envelope.
    decisions = 2 * sum(branches ** depth for depth in range(config.max_raises + 1))
    states = 1 + decisions * (branches + 2)
    infos = pairs * decisions
    slots = infos * (branches + 2)
    if decisions > MAX_DECISION_NODES or states > MAX_PUBLIC_STATES:
        raise ValueError('Conservative preflop tree forecast exceeds its state or decision cap')
    if slots > MAX_ACTION_SLOTS:
        raise ValueError('Conservative preflop action-slot forecast exceeds 1,000,000')

    passes = 3 if algorithm == 'cfrplus' else 1
    # A full traversal visits at most S states per world. At decisions its
    # child/value/regret/average loops are bounded by the tree's edge count.
    # BR additionally partitions/scales four-element worlds at opponent
    # branches. 32 element/loop units per world-state covers these paths.
    # Separate 32*A units per sweep cover all row/profile work: CFR+ has
    # three regret-matching profiles (<=12*A units), two filtered delta
    # constructions and regret updates (<=5*A); vanilla/DCFR use fewer.
    training = iterations * (32 * worlds * states * passes + 32 * slots)
    # One evaluation and both exact own-hand best responses are fully charged.
    diagnostics = 32 * worlds * states * 3
    # Table/candidate validation, world/row setup, final normalization and
    # serialization are reserved separately from iterative world traversal.
    setup = (4096 + 128 * candidates + 256 * pairs
             + 128 * sum(map(len, equities.hands)) + 128 * slots
             + 64 * categorical_worlds + 64 * states)
    pair_mean_setup = 256 * pairs if world_indexing == 'pair-mean' else 0
    setup += pair_mean_setup
    source = (128 + 8 * candidates + 128 * pairs + 64 * BOARDS_PER_PAIR * pairs
              if resource_model == 'source-inclusive' else 0)
    total = source + setup + training + diagnostics
    if total > MAX_MODELED_LOOP_ENTRIES:
        raise ValueError('Full-requested preflop work exceeds 500,000,000 modeled loop entries')
    result = {
        'budget_version': 'preflop-full-checkdown-work-v1',
        'resource_model': resource_model, 'requested_iterations': iterations,
        'algorithm': algorithm, 'compatible_pairs': pairs,
        'categorical_rows_upper_bound': categorical_worlds,
        'tree_upper_bound': {'raise_branches': branches, 'decision_nodes': decisions,
                            'public_states': states, 'information_sets': infos,
                            'information_action_slots': slots},
        'limits': {'decision_nodes': MAX_DECISION_NODES,
                   'public_states': MAX_PUBLIC_STATES,
                   'information_action_slots': MAX_ACTION_SLOTS},
        'training_passes_per_iteration': passes,
        'training_loop_entries_upper_bound': training,
        'diagnostic_loop_entries_upper_bound': diagnostics,
        'prepared_setup_loop_entries_upper_bound': setup,
        'source_bookkeeping_loop_entries_upper_bound': source,
        'source_enumeration_charged': resource_model == 'source-inclusive',
        'current_rank_calls': 0, 'current_board_combinations': 0,
        'historical_equity_preparation': equities.budget,
        'total_loop_entries_upper_bound': total,
        'total_loop_entry_limit': MAX_MODELED_LOOP_ENTRIES,
        'scope': 'Conservative configuration-derived tree/row forecasts, full requested '
                 'scalar CFR traversal and exact evaluation/own-hand best responses, '
                 'plus table/setup/output bookkeeping. Forecasts may reject a configuration '
                 'whose realized tree would be smaller. Source-inclusive mode also charges '
                 'historical full-board preparation/bookkeeping (rank instructions are '
                 'separately capped, excluded from these loop units); prepared-counts charges current table '
                 'work only. No current ranking. Not bytecode, elapsed time, allocation '
                 'bytes or RSS bounds; trusted counts require independent provenance.',
    }
    if world_indexing == 'pair-mean':
        result.update({
            'budget_version': 'preflop-full-checkdown-pair-mean-work-v1',
            'world_indexing': 'pair-mean',
            'training_world_rows_upper_bound': pairs,
            'pair_mean_setup_loop_entries_upper_bound': pair_mean_setup,
            'scope': result['scope'] + ' Pair-mean indexing aggregates each private pair\'s '
                     'hidden W/T/L categories to a conditional signed mean computed as a '
                     'Fraction before binary64 conversion; its setup charge is included above. '
                     'Floating-point summation order may differ.',
        })
    return result
