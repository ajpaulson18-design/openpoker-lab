"""Preflop-local chance-sampled vanilla CFR over joint physical worlds.

Sampling follows the chance-block sampling estimator described in section
3, equation 6 and the chance-block discussion of Lanctot et al. (2009):
https://papers.nips.cc/paper/2009/file/00411460f7c92d2124a67ea0f4cb5f85-Paper.pdf
Every betting action remains enumerated on a draw; only the joint private-hand
and public-runout chance outcome is sampled. Policies use caller-supplied
information keys, which for preflop solving contain own hand and public history.
This is vanilla simultaneous regret matching, not DCFR or CFR+.
"""

from bisect import bisect_right
from collections.abc import Mapping
from hashlib import sha256
from math import fsum, isfinite
import random

from .cfr import strategy


MAX_BATCH_SIZE = 256
MAX_SEED = (1 << 64) - 1


def validate_sampling_options(seed, batch_size):
    """Validate the public sampling controls before enumeration or allocation."""
    if type(seed) is not int or not 0 <= seed <= MAX_SEED:
        raise ValueError("Sampling seed must be an integer in [0, 2^64-1].")
    if type(batch_size) is not int or not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError("Sampling batch size must be an integer in [1, 256].")


class _WeightedWorldSampler:
    """Exact discrete CDF over the represented nonnegative float weights."""

    def __init__(self, worlds):
        if (isinstance(worlds, (str, bytes)) or not hasattr(worlds, "__len__") or
                not hasattr(worlds, "__getitem__")):
            raise TypeError("worlds must be a sized sequence of weighted deals")
        if not worlds:
            raise ValueError("at least one weighted world is required")

        ratios = []
        max_denominator_exponent = 0
        float_weights = []
        for world in worlds:
            if not isinstance(world, (tuple, list)) or len(world) < 3:
                raise ValueError("each world must include a weight at index 2")
            weight = world[2]
            if isinstance(weight, bool) or not isinstance(weight, (int, float)):
                raise ValueError("world weights must be finite nonnegative real numbers")
            if isinstance(weight, float):
                if not isfinite(weight) or weight < 0:
                    raise ValueError("world weights must be finite and nonnegative")
                numerator, denominator = weight.as_integer_ratio()
                denominator_exponent = denominator.bit_length() - 1
            else:
                if weight < 0:
                    raise ValueError("world weights must be finite and nonnegative")
                numerator, denominator_exponent = weight, 0
            ratios.append((numerator, denominator_exponent))
            max_denominator_exponent = max(max_denominator_exponent,
                                           denominator_exponent)
            try:
                float_weight = float(weight)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("world weights must be finite and nonnegative") from exc
            if not isfinite(float_weight):
                raise ValueError("world weights must be finite and nonnegative")
            float_weights.append(float_weight)

        try:
            total_mass = fsum(float_weights)
        except OverflowError as exc:
            raise ValueError("world weights must have finite positive total mass") from exc
        if not isfinite(total_mass) or total_mass <= 0:
            raise ValueError("world weights must have finite positive total mass")

        cumulative = []
        total_units = 0
        for numerator, denominator_exponent in ratios:
            total_units += numerator << (max_denominator_exponent - denominator_exponent)
            cumulative.append(total_units)
        if total_units <= 0:
            raise ValueError("world weights must have positive total mass")
        self.cumulative = tuple(cumulative)
        self.total_units = total_units
        self.total_mass = total_mass

    def draw_index(self, rng):
        draw = rng.randrange(self.total_units)
        return bisect_right(self.cumulative, draw)


def _checked_strategy(profile, key, action_count):
    probabilities = profile.get(key)
    if probabilities is None:
        probabilities = [1.0 / action_count] * action_count
    if len(probabilities) != action_count:
        raise ValueError("profile action count does not match the visited information set")
    try:
        values = tuple(float(value) for value in probabilities)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("profile probabilities must be finite and nonnegative") from exc
    if (any(not isfinite(value) or value < 0 for value in values) or
            abs(fsum(values) - 1.0) > 1e-12):
        raise ValueError("profile probabilities must be finite, nonnegative, and sum to one")
    return values


def world_contributions(root, world, infos, profile, terminal_value,
                        node_key, chance_child):
    """Return unweighted one-world regret/own-reach average contributions.

    This independent entry point makes the estimator's exact chance-weighted
    expectation testable: sum each result times its world mass. Returned maps
    contain only information sets visited in this world's selected chance path.
    """
    if not isinstance(infos, Mapping):
        raise TypeError("infos must map information-set keys to action counts")
    if not callable(terminal_value) or not callable(node_key) or not callable(chance_child):
        raise TypeError("terminal_value, node_key, and chance_child must be callable")

    regrets = {}
    averages = {}
    visited = set()
    node_visits = 0

    def visit(node, reach0, reach1):
        nonlocal node_visits
        node_visits += 1
        child = chance_child(node, world)
        if child is not None:
            return visit(child, reach0, reach1)
        if hasattr(node, "branches") and not hasattr(node, "actions"):
            raise ValueError("sampled world does not select a child at a public chance node")
        if not hasattr(node, "actions"):
            value = terminal_value(node, world)
            try:
                value = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("terminal utility must be a finite real number") from exc
            if not isfinite(value):
                raise ValueError("terminal utility must be finite")
            return value

        if node.player not in (0, 1):
            raise ValueError("decision player must be 0 or 1")
        action_count = len(node.actions)
        if action_count < 1 or action_count != len(node.children):
            raise ValueError("decision actions and children must have matching positive lengths")
        key = node_key(node, world)
        if key not in infos:
            raise ValueError("visited node has no matching information-set entry")
        if type(infos[key]) is not int or infos[key] != action_count:
            raise ValueError("information-set action count does not match the visited node")
        probabilities = _checked_strategy(profile, key, action_count)
        visited.add(key)

        action_values = []
        for action_index, child_node in enumerate(node.children):
            action_values.append(visit(
                child_node,
                reach0 * (probabilities[action_index] if node.player == 0 else 1.0),
                reach1 * (probabilities[action_index] if node.player == 1 else 1.0),
            ))

        expected = fsum(probability * value for probability, value
                        in zip(probabilities, action_values))
        opponent_reach = reach1 if node.player == 0 else reach0
        own_reach = reach0 if node.player == 0 else reach1
        utility_sign = 1.0 if node.player == 0 else -1.0
        regret_row = regrets.setdefault(key, [0.0] * action_count)
        average_row = averages.setdefault(key, [0.0] * action_count)
        for action_index, value in enumerate(action_values):
            regret_row[action_index] += (opponent_reach * utility_sign *
                                         (value - expected))
            average_row[action_index] += (own_reach * probabilities[action_index])
        return expected

    try:
        visit(root, 1.0, 1.0)
    finally:
        visit = None
    return regrets, averages, {"node_visits": node_visits, "visited_information_sets": len(visited)}


def train_chance_sampled(root, worlds, infos, iterations, terminal_value,
                         node_key, chance_child, *, seed=0, batch_size=1):
    """Train vanilla CFR using weighted joint-world chance samples.

    Each iteration samples ``batch_size`` worlds with replacement from their
    exact represented float-mass law. The profile is frozen for the batch;
    regret and own-reach average contributions are scaled by total mass divided
    by batch size. All betting actions are traversed on each sampled world.
    Returns ``(average_policy, stats)``; unvisited information sets are uniform.
    """
    if type(iterations) is not int or iterations < 1:
        raise ValueError("iterations must be a positive integer")
    validate_sampling_options(seed, batch_size)
    if not isinstance(infos, Mapping):
        raise TypeError("infos must map information-set keys to action counts")
    if not callable(terminal_value) or not callable(node_key) or not callable(chance_child):
        raise TypeError("terminal_value, node_key, and chance_child must be callable")
    for key, action_count in infos.items():
        if type(action_count) is not int or action_count < 1:
            raise ValueError("information sets must have positive integer action counts")

    sampler = _WeightedWorldSampler(worlds)
    rng = random.Random(seed)
    regrets = {key: [0.0] * count for key, count in infos.items()}
    sums = {key: [0.0] * count for key, count in infos.items()}
    scale = sampler.total_mass / batch_size
    draw_digest = sha256()
    node_visits = 0
    visited_information_sets = set()

    for _iteration in range(iterations):
        profile = {}

        def policy_for(key):
            probabilities = profile.get(key)
            if probabilities is None:
                if key not in regrets:
                    raise ValueError("visited node has no matching information-set entry")
                probabilities = strategy(regrets[key])
                profile[key] = probabilities
            return probabilities

        batch_regrets = {}
        batch_sums = {}
        for _sample in range(batch_size):
            world_index = sampler.draw_index(rng)
            draw_digest.update(world_index.to_bytes(4, "little"))
            sampled_world = worlds[world_index]
            delta, average, stats = world_contributions(
                root, sampled_world, infos, _ProfileView(policy_for),
                terminal_value, node_key, chance_child,
            )
            node_visits += stats["node_visits"]
            visited_information_sets.update(delta)
            for key, row in delta.items():
                target = batch_regrets.setdefault(key, [0.0] * infos[key])
                for index, value in enumerate(row):
                    target[index] += scale * value
            for key, row in average.items():
                target = batch_sums.setdefault(key, [0.0] * infos[key])
                for index, value in enumerate(row):
                    target[index] += scale * value

        for key, row in batch_regrets.items():
            for index, value in enumerate(row):
                regrets[key][index] += value
        for key, row in batch_sums.items():
            for index, value in enumerate(row):
                sums[key][index] += value
        policy_for = None

    averages = {}
    for key, row in sums.items():
        total = fsum(row)
        averages[key] = ([value / total for value in row] if total else
                         [1.0 / len(row)] * len(row))
    return averages, {
        "algorithm": "vanilla-chance-sampled-cfr",
        "iterations": iterations,
        "batch_size": batch_size,
        "seed": seed,
        "rng_algorithm": "random.Random-MT19937",
        "world_sampling": "exact-integer-cdf-over-float-as-integer-ratio",
        "world_draws": iterations * batch_size,
        "sampled_world_index_sha256": draw_digest.hexdigest(),
        "actual_node_visits": node_visits,
        "visited_information_sets": len(visited_information_sets),
        "total_world_mass": sampler.total_mass,
    }


class _ProfileView(Mapping):
    """Read-only mapping that computes each visited policy at most once."""

    __slots__ = ("_policy_for",)

    def __init__(self, policy_for):
        self._policy_for = policy_for

    def __getitem__(self, key):
        return self._policy_for(key)

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def get(self, key, default=None):
        try:
            return self._policy_for(key)
        except KeyError:
            return default
