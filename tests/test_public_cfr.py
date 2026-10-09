"""Differential and lifetime checks for exact public-batched CFR traversal."""
import gc
import platform
import unittest
import weakref
from types import SimpleNamespace
from unittest.mock import patch

from pokerlab import public_cfr
from pokerlab.cfr import train as train_recursive
from pokerlab.postflop_solver import (
    _Chance, _build_postflop_tree, _chance_child, _enumerate_worlds,
    _node_key, _prefix_hand_index, _public_reveals,
)
from pokerlab.river_config import RiverConfig
from pokerlab.river_tree import _Node, _Terminal, _terminal_value


def _fixture():
    board = "Js8d4c"
    oop = "AsAh:0.5,KsKh:1"
    ip = "AcAd:1,KcKd:0.75"
    runouts = (("As", "3c"), ("3c", "As"), ("5h", "9s"))
    config = RiverConfig(pot=20, effective_stack=(35, 55),
                         bet_sizes=(0.25,), raise_sizes=(), max_raises=0,
                         include_all_in=True)
    turn_config = RiverConfig(pot=20, effective_stack=(35, 55),
                              bet_sizes=(0.5,), raise_sizes=(), max_raises=0,
                              include_all_in=True)
    river_config = RiverConfig(pot=20, effective_stack=(35, 55),
                               bet_sizes=(0.75,), raise_sizes=(), max_raises=0,
                               include_all_in=True)
    hands, worlds, _, _ = _enumerate_worlds(
        board, oop, ip, runouts, iterations=20,
    )
    root, nodes, _, _, _ = _build_postflop_tree(
        board, config, turn_config=turn_config, river_config=river_config,
        worlds=worlds,
    )
    legal = _prefix_hand_index(worlds)
    infos = {}
    for (player, history), node in nodes.items():
        prefix = _public_reveals(history)
        for hand_index in sorted(legal.get((player, prefix), ())):
            infos[(player, hand_index, history)] = len(node.actions)
    payoff = lambda node, world: _terminal_value(node, world[3], config.pot)
    return hands, worlds, root, infos, payoff, config, runouts


def _assert_profiles_equal(test, expected, actual):
    test.assertEqual(expected.keys(), actual.keys())
    for key in expected:
        test.assertEqual(len(expected[key]), len(actual[key]), repr(key))
        for left, right in zip(expected[key], actual[key]):
            test.assertAlmostEqual(left, right, places=12, msg=repr(key))


class PublicBatchedCFRTests(unittest.TestCase):
    def test_weighted_blocker_flop_profiles_match_recursive_reference(self):
        _, worlds, root, infos, payoff, config, _ = _fixture()
        zero_reach_key = (0, 0, ("unreachable-public-history",))
        infos[zero_reach_key] = 3
        self.assertAlmostEqual(sum(world[2] for world in worlds), 1.0, places=14)
        self.assertEqual(len(worlds), 8)
        for algorithm in ("vanilla", "dcfr"):
            for iterations in (20, 100):
                with self.subTest(algorithm=algorithm, iterations=iterations):
                    expected = train_recursive(
                        root, worlds, infos, iterations, algorithm, payoff,
                        _node_key, _chance_child,
                    )
                    actual = public_cfr.train_public_batched(
                        root, worlds, infos, iterations, algorithm,
                        pot=config.pot, chance_type=_Chance,
                    )
                    _assert_profiles_equal(self, expected, actual)
                    self.assertEqual(actual[zero_reach_key], [1 / 3] * 3)

    def test_unique_prefix_hand_edge_limit_rejects_before_large_aggregation(self):
        _, worlds, root, infos, _, config, _ = _fixture()
        with patch.object(public_cfr, "MAX_PREFIX_EDGES", 1):
            with self.assertRaisesRegex(ValueError, "prefix.*edge|edge.*limit"):
                public_cfr.train_public_batched(
                    root, worlds, infos, 20, "vanilla",
                    pot=config.pot, chance_type=_Chance,
                )

    def test_rejects_bad_algorithm_iteration_budget_and_empty_worlds(self):
        _, worlds, root, infos, _, config, _ = _fixture()
        for algorithm in ("other", None):
            with self.subTest(algorithm=algorithm), self.assertRaises(ValueError):
                public_cfr.train_public_batched(
                    root, worlds, infos, 20, algorithm,
                    pot=config.pot, chance_type=_Chance,
                )
        for iterations in (0, True, -1):
            with self.subTest(iterations=iterations), self.assertRaises(ValueError):
                public_cfr.train_public_batched(
                    root, worlds, infos, iterations, "vanilla",
                    pot=config.pot, chance_type=_Chance,
                )
        with self.assertRaises(ValueError):
            public_cfr.train_public_batched(
                root, (), infos, 20, "vanilla", pot=config.pot,
                chance_type=_Chance,
            )

    @unittest.skipUnless(platform.python_implementation() == "CPython",
                         "Immediate weakref release is CPython-specific.")
    def test_visitor_releases_history_keys_without_cyclic_gc_after_success(self):
        class Marker:
            pass

        marker = Marker()
        reference = weakref.ref(marker)
        history = (marker,)
        root = _Node(history, 0, ("a", "b"), (
            _Terminal("showdown", (0.0, 0.0)),
            _Terminal("showdown", (0.0, 4.0)),
        ))
        key = (0, 0, history)
        infos = {key: 2}
        worlds = [(0, 0, 1.0, 1)]
        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            profile = public_cfr.train_public_batched(
                root, worlds, infos, 10, "vanilla", pot=20.0,
                chance_type=_Chance,
            )
            self.assertIn(key, profile)
            del profile, root, infos, key, history, marker
            self.assertIsNone(reference())
        finally:
            if gc_was_enabled:
                gc.enable()
            gc.collect()

    @unittest.skipUnless(platform.python_implementation() == "CPython",
                         "Immediate weakref release is CPython-specific.")
    def test_visitor_releases_history_keys_without_cyclic_gc_after_failure(self):
        class Marker:
            pass

        marker = Marker()
        reference = weakref.ref(marker)
        key = (0, 0, (marker,))
        infos = {key: 2}
        worlds = [(0, 0, 1.0, 1, "5h")]
        root = _Chance((), {"6h": _Terminal("showdown", (0.0, 0.0))}, 4,
                       "turn")
        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            try:
                public_cfr.train_public_batched(
                    root, worlds, infos, 10, "vanilla", pot=20.0,
                    chance_type=_Chance,
                )
            except KeyError as error:
                error.__traceback__ = None
                del error
            else:
                self.fail("The fixture must fail inside the recursive visitor.")
            del root, infos, key, marker
            self.assertIsNone(reference())
        finally:
            if gc_was_enabled:
                gc.enable()
            gc.collect()


if __name__ == "__main__":
    unittest.main()
