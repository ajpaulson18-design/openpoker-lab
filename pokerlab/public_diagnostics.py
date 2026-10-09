"""Exact diagnostics for the public-tree/private-hand-vector solver."""

import math
from collections.abc import Mapping

from . import public_cfr
from .ranked_river import RankedRiverPayoffs
from .river_tree import _Terminal


def evaluate_profile(root, worlds, averages, *, pot, chance_type,
                     terminal_kernel: RankedRiverPayoffs | None = None):
    """Return OOP profile value and each player's exact information-set BR value.

    World tuples and strategy keys have the same shape as ``train_public_batched``.
    Chance is enumerated from the supplied public tree; hidden future cards are
    represented only by each world's prefix weight. An optional ranked river
    kernel accepts only its validated complete compatible river deal set and
    rejects future-card or arbitrary correlated weighted worlds.
    """
    if not isinstance(averages, Mapping):
        raise TypeError("averages must map information-set keys to policies.")
    policies = {}
    for key, row in averages.items():
        if not isinstance(row, (tuple, list)) or not row:
            raise ValueError("Each average policy must be a nonempty probability row.")
        try:
            probs = tuple(float(x) for x in row)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Average policies must contain finite probabilities.") from exc
        if (any(not math.isfinite(x) or x < 0 for x in probs) or
                abs(sum(probs) - 1.0) > 1e-8):
            raise ValueError("Average policy probabilities must sum to one.")
        policies[key] = probs
    infos = {key: len(row) for key, row in policies.items()}
    pot, hand_counts = public_cfr._validate_inputs(
        worlds, infos, 1, "vanilla", pot, chance_type,
    )
    if terminal_kernel is not None:
        if not isinstance(terminal_kernel, RankedRiverPayoffs):
            raise TypeError("terminal_kernel must be a RankedRiverPayoffs instance.")
        terminal_kernel.validate_worlds(worlds, pot=pot)
        context_counts = [len(terminal_kernel.hands[0]),
                          len(terminal_kernel.hands[1])]
        if any(key[1] >= context_counts[key[0]] for key in infos):
            raise ValueError("An information-set hand index is outside the ranked river kernel.")
        hand_counts = context_counts
    edges, marginals = public_cfr._aggregate_prefixes(worlds, hand_counts)

    half = pot / 2.0

    def terminal_vector(node, prefix, opponent_reach, responder):
        if terminal_kernel is not None:
            if prefix:
                raise ValueError("Ranked river payoffs require an empty public-card prefix.")
            return terminal_kernel.values(node, opponent_reach, responder)
        count = hand_counts[responder]
        out = [0.0] * count
        if node.kind == "fold":
            payoff = (1.0 if node.winner == 0 else -1.0) * (half + min(node.contributions))
            sign_mode = False
        else:
            payoff = half + min(node.contributions)
            sign_mode = True
        for i, j, mass, signed in edges.get(prefix, ()):
            own, opp = (i, j) if responder == 0 else (j, i)
            weight = mass * opponent_reach[opp]
            value = signed if sign_mode else mass
            out[own] += value * opponent_reach[opp] * payoff if sign_mode else payoff * weight
        if responder == 1:
            out = [-x for x in out]
        return out

    def policy(node, hand, prefix):
        row = policies.get((node.player, hand, node.history))
        if row is None:
            if marginals.get(prefix, ([0.0] * hand_counts[0],
                                     [0.0] * hand_counts[1]))[node.player][hand] > 0:
                raise ValueError("Average policy is missing a reachable information set.")
            return (1.0 / len(node.children),) * len(node.children)
        if len(row) != len(node.children):
            raise ValueError("Average policy action count does not match the public node.")
        return row

    def profile(node, prefix, r0, r1):
        if isinstance(node, chance_type):
            if terminal_kernel is not None:
                raise ValueError("Ranked river payoffs cannot traverse public chance nodes.")
            return sum(profile(child, prefix + (card,), r0, r1)
                       for card, child in node.branches.items())
        if isinstance(node, _Terminal):
            if terminal_kernel is not None:
                if prefix:
                    raise ValueError("Ranked river payoffs require an empty public-card prefix.")
                values = terminal_kernel.values(node, r1, 0)
                return sum(r0[index] * value for index, value in enumerate(values))
            if node.kind == "fold":
                unit = (1 if node.winner == 0 else -1) * (half + min(node.contributions))
                return sum(m * r0[i] * r1[j] * unit
                           for i, j, m, _ in edges.get(prefix, ()))
            scale = half + min(node.contributions)
            return sum(s * r0[i] * r1[j] * scale
                       for i, j, _, s in edges.get(prefix, ()))
        p = node.player
        value = 0.0
        for a, child in enumerate(node.children):
            reach = r0 if p == 0 else r1
            changed = [reach[h] * policy(node, h, prefix)[a] for h in range(len(reach))]
            value += profile(child, prefix,
                             changed if p == 0 else r0,
                             changed if p == 1 else r1)
        return value

    try:
        profile_value = profile(root, (), [1.0] * hand_counts[0], [1.0] * hand_counts[1])
    finally:
        profile = None

    def best(player):
        opponent = 1 - player
        def visit(node, prefix, opp_reach):
            if isinstance(node, chance_type):
                if terminal_kernel is not None:
                    raise ValueError("Ranked river payoffs cannot traverse public chance nodes.")
                result = [0.0] * hand_counts[player]
                for card, child in node.branches.items():
                    vals = visit(child, prefix + (card,), opp_reach)
                    result = [x + y for x, y in zip(result, vals)]
                return result
            if isinstance(node, _Terminal):
                return terminal_vector(node, prefix, opp_reach, player)
            if node.player == opponent:
                result = [0.0] * hand_counts[player]
                for action, child in enumerate(node.children):
                    changed = [opp_reach[h] * policy(node, h, prefix)[action]
                               for h in range(len(opp_reach))]
                    vals = visit(child, prefix, changed)
                    result = [x + y for x, y in zip(result, vals)]
                return result
            actions = [visit(child, prefix, opp_reach) for child in node.children]
            return [max(vals[h] for vals in actions) for h in range(hand_counts[player])]
        # Terminal vectors already contain the joint physical mass.
        try:
            vals = visit(root, (), [1.0] * hand_counts[opponent])
        finally:
            visit = None
        # Each world's mass was already included at terminals, so sum once
        # over hand indices; no additional marginal factor is appropriate.
        return sum(vals)

    return profile_value, best(0), best(1)
