"""Compatible turn-to-river facade over the shared exact postflop engine."""
from .cards import cards
from .postflop_solver import (
    _Chance, _chance_child, _chance_partitions, _node_key, _build_public_tree,
    _enumerate_worlds as _postflop_worlds, solve_postflop,
)


def _enumerate_worlds(board, oop_range, ip_range, runouts=None, iterations=10):
    """Preserve the turn-only private world-enumeration interface."""
    return _postflop_worlds(cards(board, 4), oop_range, ip_range, runouts, iterations)


def _tree(config, river_config, runouts):
    """Preserve the turn test/benchmark tree interface without a second builder."""
    worlds = [(0, 0, 1., 0, river) for river in runouts]
    return _build_public_tree(4, config, river_config=river_config, worlds=worlds)[:4]


def solve_turn_river(board, oop_range, ip_range, config=None, *, river_config=None,
                     runouts=None, iterations=1000, algorithm="vanilla",
                     traversal="recursive", diagnostics="recursive",
                     target_exploitability=None, check_interval=100):
    """Solve the same finite turn game using the reusable postflop architecture.

    Pot and stacks describe the beginning of the turn. Subsequent sizing may
    change, while matched commitments and total stack caps carry to the river.
    Selected rivers condition the entire joint private-hand/runout distribution.
    The strategy schema and established turn result fields remain compatible.
    """
    result = solve_postflop(cards(board, 4), oop_range, ip_range, config,
                           river_config=river_config, runouts=runouts,
                           iterations=iterations, algorithm=algorithm,
                           traversal=traversal, diagnostics=diagnostics,
                           target_exploitability=target_exploitability,
                           check_interval=check_interval)
    result["solver_version"] = "configured-turn-river-v3"
    result["scope"] = ("Approximate equilibrium of the configured heads-up "
                       "turn-to-river action abstraction; no flop, preflop or rake.")
    return result
