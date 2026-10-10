"""Preflop-local vector CFR+ with delayed completed-sweep averaging.

The averaging weight follows Tammelin's CFR+ schedule
``w_t = max(t - d, 0)`` (https://arxiv.org/pdf/1407.5042, section 2).
This adapter preserves the repository's established end-of-completed-sweep,
own-reach averaging convention; it does not claim to reproduce every detail
of the paper's pseudocode. Shared public CFR kernels remain unchanged.
"""

from . import public_cfr
from .cfr import strategy
from .river_tree import _Terminal


def train_delayed_public_cfrplus(root, worlds, infos, iterations, *,
                                 averaging_delay=0, pot, chance_type,
                                 checkpoint_interval=None,
                                 checkpoint_callback=None):
    """Train alternating public-vector CFR+ with a delayed average policy.

    Regret updates are the repository's public-vector CFR+ updates. After each
    complete player-0/player-1 sweep, the profile is accumulated with linear
    weight ``max(iteration - averaging_delay, 0)`` and acting-player reach.
    """
    if type(iterations) is not int or iterations < 1:
        raise ValueError("Iterations must be a positive integer.")
    if type(averaging_delay) is not int or not 0 <= averaging_delay < iterations:
        raise ValueError("CFR+ averaging delay must be an integer in [0, iterations).")
    if checkpoint_callback is not None and not callable(checkpoint_callback):
        raise TypeError("checkpoint_callback must be callable.")
    if (checkpoint_interval is not None and
            (type(checkpoint_interval) is not int or checkpoint_interval < 1)):
        raise ValueError("checkpoint_interval must be a positive integer.")
    if (checkpoint_callback is not None) != (checkpoint_interval is not None):
        raise ValueError(
            "checkpoint_interval and checkpoint_callback must be supplied together."
        )

    pot, hand_counts = public_cfr._validate_inputs(
        worlds, infos, iterations, "cfrplus", pot, chance_type,
    )
    if not infos:
        if checkpoint_callback is not None:
            last_checkpoint = 0
            for iteration in range(checkpoint_interval, iterations + 1,
                                   checkpoint_interval):
                if checkpoint_callback(iteration, {}):
                    return {}
                last_checkpoint = iteration
            if last_checkpoint != iterations:
                checkpoint_callback(iterations, {})
        return {}
    edges, marginals = public_cfr._aggregate_prefixes(worlds, hand_counts)
    # Preserve the caller's original row order in returned mappings, while
    # keeping per-player update lists for selective rematching.
    keys = list(infos)
    keys_by_player = {player: [key for key in keys if key[0] == player]
                      for player in (0, 1)}
    regrets = {key: [0.0] * infos[key] for key in keys}
    sums = {key: [0.0] * infos[key] for key in keys}
    half_pot = pot / 2.0

    def accumulate_average(current, iteration_weight):
        def visit(node, prefix, reach0, reach1):
            if isinstance(node, chance_type):
                for card, child in node.branches.items():
                    visit(child, prefix + (card,), reach0, reach1)
                return
            if isinstance(node, _Terminal):
                return

            player = node.player
            action_count = len(node.actions)
            uniform = [1.0 / action_count] * action_count
            for hand_index in range(hand_counts[player]):
                key = (player, hand_index, node.history)
                if key in sums:
                    sigma = current.get(key, uniform)
                    own_mass = marginals[prefix][player][hand_index]
                    own_reach = reach0[hand_index] if player == 0 else reach1[hand_index]
                    for action in range(action_count):
                        sums[key][action] += (own_mass * own_reach * sigma[action] *
                                              iteration_weight)
            for action_index, child in enumerate(node.children):
                if player == 0:
                    child_reach0 = [reach0[index] * current.get(
                        (player, index, node.history), uniform)[action_index]
                        for index in range(hand_counts[0])]
                    visit(child, prefix, child_reach0, reach1)
                else:
                    child_reach1 = [reach1[index] * current.get(
                        (player, index, node.history), uniform)[action_index]
                        for index in range(hand_counts[1])]
                    visit(child, prefix, reach0, child_reach1)

        try:
            visit(root, (), [1.0] * hand_counts[0], [1.0] * hand_counts[1])
        finally:
            # Break the recursive closure cycle on normal and exceptional exits.
            visit = None

    # The profile begins at the uniform strategy and then only the active
    # player's rows change after each alternating regret sweep. Keep the other
    # player's cached rows intact instead of rematching every information set.
    current = {key: strategy(regrets[key]) for key in keys}
    for iteration in range(1, iterations + 1):
        for player in (0, 1):
            deltas = public_cfr._cfrplus_target_deltas(
                root, edges, infos, current, player, hand_counts,
                half_pot, chance_type,
            )
            for key in keys_by_player[player]:
                regrets[key] = [max(0.0, old + delta)
                                for old, delta in zip(regrets[key], deltas[key])]
                current[key] = strategy(regrets[key])

        weight = float(max(iteration - averaging_delay, 0))
        if weight > 0.0:
            accumulate_average(current, weight)

        if checkpoint_callback is not None and (
                iteration % checkpoint_interval == 0 or iteration == iterations):
            snapshot = {}
            for key in keys:
                total = sum(sums[key])
                snapshot[key] = ([value / total for value in sums[key]] if total else
                                 [1.0 / infos[key]] * infos[key])
            try:
                should_stop = bool(checkpoint_callback(iteration, snapshot))
            finally:
                # Do not retain the last normalized policy alongside the
                # regret and average tables after the callback returns.
                snapshot = None
            if should_stop:
                break

    averages = {}
    for key in keys:
        total = sum(sums[key])
        averages[key] = ([value / total for value in sums[key]] if total else
                         [1.0 / infos[key]] * infos[key])
    return averages
