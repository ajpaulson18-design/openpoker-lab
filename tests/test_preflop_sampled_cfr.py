import gc
import math
import weakref
import unittest
from unittest.mock import patch

from pokerlab import cfr
from pokerlab import preflop_sampled_cfr as sampled
from pokerlab.preflop_sampled_cfr import (
    _WeightedWorldSampler, train_chance_sampled, validate_sampling_options,
    world_contributions,
)
from pokerlab.postflop_solver import _Chance, _chance_child, _node_key
from pokerlab.river_tree import _Action, _Node, _Terminal, _terminal_value


def _tiny_game():
    root = _Node((), 0, (_Action("a"), _Action("b")),
                 (_Terminal("a", (1, 1)), _Terminal("b", (1, 1))))
    worlds = ((0, 0, 0.25, 1), (0, 1, 0.75, -1))
    infos = {(0, 0, ()): 2}
    payoff = lambda terminal, world: world[3] * (2.0 if terminal.kind == "a" else -1.0)
    node_key = lambda node, world: (node.player, world[node.player], node.history)
    return root, worlds, infos, payoff, node_key


class _SequenceRng:
    def __init__(self, values):
        self.values = iter(values)

    def randrange(self, stop):
        value = next(self.values)
        if not 0 <= value < stop:
            raise AssertionError("test draw is outside the sampler range")
        return value


class SampledCFRTests(unittest.TestCase):
    def test_fixed_profile_world_contributions_have_exact_weighted_expectation(self):
        root, worlds, infos, payoff, node_key = _tiny_game()
        profile = {(0, 0, ()): [0.25, 0.75]}
        expected_regrets = [0.0, 0.0]
        expected_average = [0.0, 0.0]
        for world in worlds:
            delta, average, stats = world_contributions(
                root, world, infos, profile, payoff, node_key, _chance_child,
            )
            weight = world[2]
            for index in range(2):
                expected_regrets[index] += weight * delta[(0, 0, ())][index]
                expected_average[index] += weight * average[(0, 0, ())][index]
            self.assertEqual(stats["node_visits"], 3)
        self.assertAlmostEqual(expected_regrets[0], -1.125, delta=1e-15)
        self.assertAlmostEqual(expected_regrets[1], 0.375, delta=1e-15)
        self.assertEqual(expected_average, [0.25, 0.75])

    def test_two_player_counterfactual_reach_and_own_reach_average(self):
        left = _Node(("left",), 1, (_Action("a"), _Action("b")),
                     (_Terminal("2", (1,1)), _Terminal("-1", (1,1))))
        right = _Node(("right",), 1, (_Action("a"), _Action("b")),
                      (_Terminal("4", (1,1)), _Terminal("-2", (1,1))))
        root = _Node((), 0, (_Action("left"), _Action("right")), (left,right))
        profile = {(0,0,()):[0.25,0.75], (1,0,("left",)):[0.4,0.6],
                   (1,0,("right",)):[0.7,0.3]}
        infos = {key:2 for key in profile}
        deltas, averages, _ = world_contributions(
            root,(0,0,1,1),infos,profile,lambda t,w:float(t.kind),
            _node_key,_chance_child)
        expected = {(0,0,()):[-1.5,0.5], (1,0,("left",)):[-0.45,0.3],
                    (1,0,("right",)):[-1.35,3.15]}
        for key in expected:
            for actual, target in zip(deltas[key],expected[key]):
                self.assertAlmostEqual(actual,target,delta=1e-14)
            for actual, target in zip(averages[key],profile[key]):
                self.assertAlmostEqual(actual,target,delta=1e-14)

    def test_importance_scaled_batch_matches_exact_vanilla_update(self):
        root, worlds, infos, payoff, node_key = _tiny_game()
        total_units = _WeightedWorldSampler(worlds).total_units
        quarter = total_units // 4
        draws = iter((0, quarter, quarter * 2, quarter * 3,
                      0, quarter, quarter * 2, quarter * 3))

        class FixedRng:
            def randrange(self, stop):
                return next(draws)

        with patch.object(sampled.random, "Random", return_value=FixedRng()):
            actual, _stats = train_chance_sampled(
                root, worlds, infos, 2, payoff, node_key, _chance_child,
                batch_size=4,
            )
        expected = cfr.train(root, worlds, infos, 2, "vanilla", payoff,
                             node_key, _chance_child)
        for key in infos:
            for observed, target in zip(actual[key], expected[key]):
                self.assertAlmostEqual(observed, target, delta=2e-15)

    def test_exact_weight_sampler_preserves_tiny_positive_mass(self):
        tiny = math.ulp(0.0)
        worlds = ((0, 0, 1.0, 0), (0, 0, tiny, 0))
        sampler = _WeightedWorldSampler(worlds)
        self.assertEqual(sampler.draw_index(_SequenceRng([sampler.total_units - 1])), 1)
        self.assertEqual(sampler.draw_index(_SequenceRng([0])), 0)

    def test_zero_weights_are_never_selected_and_integer_boundary_is_exact(self):
        sampler = _WeightedWorldSampler(((0, 0, 0.0), (0, 0, 1.0),
                                          (0, 0, 0.0), (0, 0, 3.0), (0, 0, 0.0)))
        self.assertEqual(sampler.total_units, 4)
        self.assertEqual([sampler.draw_index(_SequenceRng([n])) for n in range(4)],
                         [1, 3, 3, 3])

    def test_normal_and_exceptional_training_release_tree_without_cyclic_gc(self):
        old = gc.isenabled()
        gc.disable()
        try:
            for fail in (False, True):
                root, worlds, infos, payoff, key = _tiny_game()
                ref = weakref.ref(root)
                def exercise():
                    try:
                        train_chance_sampled(root, worlds, {} if fail else infos,
                                             10, payoff, key, _chance_child)
                    except ValueError:
                        if not fail:
                            raise
                exercise()
                del root
                self.assertIsNone(ref())
        finally:
            if old:
                gc.enable()

    def test_batch_freezes_profile_until_all_draws_finish(self):
        root, worlds, infos, payoff, node_key = _tiny_game()
        observed = []
        original = sampled.world_contributions

        def record_profile(root, world, infos, profile, terminal_value,
                           node_key, chance_child):
            observed.append(tuple(profile.get((0, 0, ()))) )
            return original(root, world, infos, profile, terminal_value,
                            node_key, chance_child)

        with patch.object(sampled.random, "Random", return_value=type(
                "FakeRandom", (), {"randrange": lambda self, stop: 0})()):
            with patch.object(sampled, "world_contributions", side_effect=record_profile):
                result, stats = train_chance_sampled(
                    root, worlds, infos, 1, payoff, node_key, _chance_child,
                    seed=3, batch_size=2,
                )
        self.assertEqual(observed, [(0.5, 0.5), (0.5, 0.5)])
        self.assertEqual(result[(0, 0, ())], [0.5, 0.5])
        self.assertEqual(stats["world_draws"], 2)

    def test_fixed_seed_is_reproducible_and_seed_changes_draw_stream(self):
        root, worlds, infos, payoff, node_key = _tiny_game()
        first = train_chance_sampled(root, worlds, infos, 100, payoff, node_key,
                                     _chance_child, seed=29)
        replay = train_chance_sampled(root, worlds, infos, 100, payoff, node_key,
                                      _chance_child, seed=29)
        other = train_chance_sampled(root, worlds, infos, 100, payoff, node_key,
                                     _chance_child, seed=30)
        self.assertEqual(first, replay)
        self.assertNotEqual(first[1]["sampled_world_index_sha256"],
                            other[1]["sampled_world_index_sha256"])
        self.assertEqual(first[1]["rng_algorithm"], "random.Random-MT19937")
        self.assertEqual(first[1]["actual_node_visits"], 300)

    def test_sampled_public_chance_visits_only_revealed_branch_keys(self):
        left = _Node(("flop@A",), 0, (_Action("a"), _Action("b")),
                     (_Terminal("a", (1, 1)), _Terminal("b", (1, 1))))
        right = _Node(("flop@B",), 0, (_Action("a"), _Action("b")),
                      (_Terminal("a", (1, 1)), _Terminal("b", (1, 1))))
        root = _Chance((), {"A": left, "B": right}, 4, "flop")
        worlds = ((0, 0, 0.5, 1, "A"), (0, 0, 0.5, -1, "B"))
        infos = {(0, 0, ("flop@A",)): 2, (0, 0, ("flop@B",)): 2}
        payoff = lambda terminal, world: world[3]
        first, _, _ = world_contributions(
            root, worlds[0], infos, {}, payoff, _node_key, _chance_child,
        )
        second, _, _ = world_contributions(
            root, worlds[1], infos, {}, payoff, _node_key, _chance_child,
        )
        self.assertEqual(set(first), {(0, 0, ("flop@A",))})
        self.assertEqual(set(second), {(0, 0, ("flop@B",))})

    def test_invalid_sampling_controls_and_world_masses_reject(self):
        for seed, batch in ((True, 1), (-1, 1), (1 << 64, 1), (0, True), (0, 0), (0, 257)):
            with self.subTest(seed=seed, batch=batch):
                with self.assertRaises(ValueError):
                    validate_sampling_options(seed, batch)
        root, worlds, infos, payoff, node_key = _tiny_game()
        for weight in (True, -1, float("nan"), float("inf"), 0.0):
            bad = ((0, 0, weight, 1),)
            with self.subTest(weight=weight):
                with self.assertRaises((ValueError, OverflowError)):
                    train_chance_sampled(root, bad, infos, 1, payoff, node_key,
                                         _chance_child)

    def test_sampled_kuhn_policy_has_independent_legal_best_response(self):
        from scripts.cfr_quality import build_kuhn_adapter, check_metrics

        adapter = build_kuhn_adapter()
        payoff = lambda terminal, world: _terminal_value(
            terminal, world[3], adapter["config"].pot)
        for seed in (2, 17, 53):
            with self.subTest(seed=seed):
                profile, stats = train_chance_sampled(
                    adapter["root"], adapter["worlds"], adapter["infos"],
                    3000, payoff, _node_key, _chance_child, seed=seed,
                )
                metrics = check_metrics(profile, layout=adapter["layout"])
                self.assertLess(metrics["nash_conv"], 0.08)
                self.assertEqual(stats["world_draws"], 3000)
                self.assertEqual(stats["visited_information_sets"], 12)


if __name__ == "__main__":
    unittest.main()
