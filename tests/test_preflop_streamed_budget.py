from unittest import TestCase
from unittest.mock import patch

from pokerlab.postflop_solver import _Chance
from pokerlab.river_tree import _Terminal
from pokerlab.preflop_vector_budget import (
    estimate_vector_budget,
    estimate_vector_budget_from_rows,
)
from tests.test_preflop_vector_budget import _instrumentation_game


def _seven_fields(rows):
    return tuple((*row[:4], row[4], "turn", "river") for row in rows)


class PreflopStreamedBudgetTests(TestCase):
    def compare(self, root, worlds, infos, iterations, algorithm, **kwargs):
        materialized = estimate_vector_budget(
            root, worlds, infos, iterations, algorithm, chance_type=_Chance,
            **kwargs)
        calls = 0

        def factory():
            nonlocal calls
            calls += 1
            return iter(worlds)

        streamed = estimate_vector_budget_from_rows(
            root, factory, len(worlds), infos, iterations, algorithm,
            chance_type=_Chance, **kwargs)
        self.assertEqual(streamed, materialized)
        self.assertEqual(calls, 2)

    def test_exact_budget_parity_with_holes_asymmetry_and_repeated_prefixes(self):
        root, short_rows, infos = _instrumentation_game()
        worlds = _seven_fields(short_rows)
        self.compare(root, worlds, infos, 8, "cfrplus", averaging_delay=3)
        self.compare(root, worlds, infos, 8, "cfrplus", averaging_delay=3,
                     checkpoint_interval=2)

    def test_weighted_repeated_prefixes_and_no_info_path(self):
        root, short_rows, infos = _instrumentation_game()
        base = _seven_fields(short_rows)
        worlds = (*base, (100, 0, 0.125, 1, "a", "turn", "river"),
                  (100, 0, 0.125, -1, "a", "turn", "river"))
        self.compare(root, worlds, infos, 3, "vanilla")
        self.compare(_Terminal("showdown", (0.5, 1.0)),
                     ((0, 1, 0.75, 1, "flop", "turn", "river"),),
                     {}, 5, "cfrplus", averaging_delay=2)

    def test_each_factory_pass_must_have_exact_declared_count(self):
        root, short_rows, infos = _instrumentation_game()
        worlds = _seven_fields(short_rows)
        calls = 0

        def short_second_pass():
            nonlocal calls
            calls += 1
            return worlds if calls == 1 else worlds[:-1]

        with self.assertRaisesRegex(ValueError, "fewer rows"):
            estimate_vector_budget_from_rows(
                root, short_second_pass, len(worlds), infos, 2, "vanilla",
                chance_type=_Chance)
        self.assertEqual(calls, 2)

        with self.assertRaisesRegex(ValueError, "more rows"):
            estimate_vector_budget_from_rows(
                root, lambda: (*worlds, worlds[0]), len(worlds), infos, 2,
                "vanilla", chance_type=_Chance)

    def test_invalid_count_and_malformed_rows_reject_before_census(self):
        root, short_rows, infos = _instrumentation_game()
        called = False

        def factory():
            nonlocal called
            called = True
            return ()

        for count in (0, -1, True, 300_001):
            with self.subTest(count=count), self.assertRaises(ValueError):
                estimate_vector_budget_from_rows(
                    root, factory, count, infos, 2, "vanilla",
                    chance_type=_Chance)
        self.assertFalse(called)
        with self.assertRaises(TypeError):
            estimate_vector_budget_from_rows(
                root, object(), 1, infos, 2, "vanilla", chance_type=_Chance)
        with self.assertRaisesRegex(ValueError, "seven-field"):
            estimate_vector_budget_from_rows(
                root, lambda: short_rows, len(short_rows), infos, 2,
                "vanilla", chance_type=_Chance)

    def test_prefix_and_dense_caps_are_shared_with_materialized_estimator(self):
        root, short_rows, infos = _instrumentation_game()
        worlds = _seven_fields(short_rows)
        with patch("pokerlab.preflop_vector_budget.MAX_PREFIX_EDGES", 1):
            with self.assertRaisesRegex(ValueError, "prefix edges"):
                estimate_vector_budget_from_rows(
                    root, lambda: iter(worlds), len(worlds), infos, 1,
                    "vanilla", chance_type=_Chance)
        with patch("pokerlab.preflop_vector_budget.MAX_DENSE_PREFIX_SLOTS", 1):
            with self.assertRaisesRegex(ValueError, "dense prefix slots"):
                estimate_vector_budget_from_rows(
                    root, lambda: iter(worlds), len(worlds), infos, 1,
                    "vanilla", chance_type=_Chance)
