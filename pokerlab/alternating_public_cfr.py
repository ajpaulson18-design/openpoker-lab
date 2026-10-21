"""Isolated LCFR and alternating-DCFR drafts for public-batched CFR.

These explicitly selected trainers use ordinary, unfloored regret matching
and pre-sweep own-reach averaging. LCFR weights regret deltas and averages by t;
alternating DCFR discounts cumulative regrets and weights averages by t squared.
The shared vanilla/DCFR/CFR+ kernels remain unchanged.
"""

from collections.abc import Mapping

from .cfr import strategy
from .public_cfr import (
    _aggregate_prefixes,
    _cfrplus_target_deltas,
    _validate_inputs,
)
from .river_tree import _Terminal


def _weighted_average_sweep(root, current, sums, infos, hand_counts, marginals,
                            average_weight, chance_type):
    """Accumulate the current profile with a supplied nonnegative weight.

    The sweep uses only each acting player's own reach. For a fixed player and
    private hand, that reach is unchanged by the other player's simultaneous
    strategy. Thus one pre-sweep traversal records the profile used for both
    alternating regret updates in this iteration.
    """
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
        if player == 0:
            own_reach = reach0
        else:
            own_reach = reach1

        for hand_index in range(hand_counts[player]):
            key = (player, hand_index, node.history)
            if key not in sums:
                continue
            probabilities = current.get(key, uniform)
            own_mass = marginals[prefix][player][hand_index]
            weight = own_mass * own_reach[hand_index] * average_weight
            for action_index, probability in enumerate(probabilities):
                sums[key][action_index] += weight * probability

        for action_index, child in enumerate(node.children):
            if player == 0:
                child_reach0 = [
                    reach0[index] * current.get(
                        (player, index, node.history), uniform
                    )[action_index]
                    for index in range(hand_counts[0])
                ]
                visit(child, prefix, child_reach0, reach1)
            else:
                child_reach1 = [
                    reach1[index] * current.get(
                        (player, index, node.history), uniform
                    )[action_index]
                    for index in range(hand_counts[1])
                ]
                visit(child, prefix, reach0, child_reach1)

    try:
        visit(root, (), [1.0] * hand_counts[0], [1.0] * hand_counts[1])
    finally:
        # Break the self-recursive closure cycle on success and failure.
        visit = None


def _train_alternating(root, worlds, infos, iterations, *, pot, chance_type,
                       algorithm):
    if algorithm not in ("lcfr", "dcfr-alternating"):
        raise ValueError("algorithm must be lcfr or dcfr-alternating.")
    if not isinstance(infos, Mapping):
        raise TypeError("infos must map information-set keys to action counts.")
    pot, hand_counts = _validate_inputs(
        worlds, infos, iterations, "vanilla", pot, chance_type,
    )
    edges, marginals = _aggregate_prefixes(worlds, hand_counts)
    keys = list(infos)
    regrets = {key: [0.0] * infos[key] for key in keys}
    sums = {key: [0.0] * infos[key] for key in keys}
    half_pot = pot / 2.0

    for iteration in range(1, iterations + 1):
        current = {key: strategy(row) for key, row in regrets.items()}
        average_weight = (float(iteration) if algorithm == "lcfr" else
                          float(iteration * iteration))
        _weighted_average_sweep(
            root, current, sums, infos, hand_counts, marginals,
            average_weight, chance_type,
        )

        for player in (0, 1):
            deltas = _cfrplus_target_deltas(
                root, edges, infos, current, player, hand_counts,
                half_pot, chance_type,
            )
            for key in keys:
                if key[0] != player:
                    continue
                if algorithm == "lcfr":
                    updated = [old + float(iteration) * delta
                               for old, delta in zip(regrets[key], deltas[key])]
                else:
                    # Alternating DCFR(3/2,0,2): add this player's unweighted
                    # current delta, discount once, then rematch before the
                    # other player's update. Nonpositive regret is discounted
                    # by 1/2; regret is never clipped at zero.
                    positive_discount = (iteration ** 1.5 /
                                         (iteration ** 1.5 + 1.0))
                    raw = [old + delta for old, delta in
                           zip(regrets[key], deltas[key])]
                    updated = [value * (positive_discount if value > 0 else 0.5)
                               for value in raw]
                regrets[key] = updated
                current[key] = strategy(updated)

    averages = {}
    for key, values in sums.items():
        total = sum(values)
        averages[key] = (
            [value / total for value in values] if total else
            [1.0 / infos[key]] * infos[key]
        )
    return averages


def train_public_lcfr(root, worlds, infos, iterations, *, pot, chance_type):
    """Train exact public-batched LCFR on a bounded fold/showdown tree.

    ``worlds`` contains ``(oop_index, ip_index, mass, sign, *future_cards)``
    rows. The game tree, worlds, information sets, and chance class have the
    same restricted contract as ``public_cfr.train_public_batched``. Each
    iteration performs one pre-sweep average traversal and two alternating
    regret traversals, so callers must charge three world/tree passes per
    requested iteration. Regrets are accumulated as ``R += t * delta`` with
    no positive-regret floor; average contributions are weighted by ``t``.

    Returns only the average profile, like the existing public trainer. This
    draft does not perform diagnostics, stopping, or checkpoint callbacks.
    """
    return _train_alternating(
        root, worlds, infos, iterations, pot=pot, chance_type=chance_type,
        algorithm="lcfr",
    )


def train_public_alternating_dcfr(root, worlds, infos, iterations, *,
                                  pot, chance_type):
    """Train public-batched alternating DCFR(3/2,0,2), as a distinct draft.

    Existing project DCFR remains simultaneous and unchanged. This variant
    averages the pre-sweep profile with weight t^2, adds unweighted regret
    deltas one player at a time, discounts that player's positive regrets by
    t^(3/2)/(t^(3/2)+1) and nonpositive regrets by 1/2, then rematches.
    """
    return _train_alternating(
        root, worlds, infos, iterations, pot=pot, chance_type=chance_type,
        algorithm="dcfr-alternating",
    )
