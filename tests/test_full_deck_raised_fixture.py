"""Focused tests for the fixed full-deck raised-turn fixture census."""
import unittest
from unittest.mock import patch

from scripts import full_deck_raised_fixture as fixture


class FullDeckRaisedFixtureTests(unittest.TestCase):
    def test_embedded_fixture_and_exact_physical_worlds(self):
        self.assertEqual(fixture.FIXTURE, {
            "id": "full-deck-raised-turn-v1",
            "board": "Js8d4c2h",
            "oop": "AsAh:0.5,KsKh:1",
            "ip": "AcAd:1,KcKd:0.75",
            "config": {
                "pot": 100.0,
                "effective_stack": 220.0,
                "bet_sizes": [0.5],
                "raise_sizes": [0.5],
                "max_raises": 1,
                "include_all_in": False,
            },
        })
        worlds = fixture.build_physical_worlds()
        self.assertEqual(worlds.board, ("Js", "8d", "4c", "2h"))
        self.assertEqual(len(worlds.pairs), 4)
        self.assertEqual(tuple(len(pair.rivers) for pair in worlds.pairs),
                         (44, 44, 44, 44))
        self.assertEqual(len(worlds.worlds), 176)
        self.assertEqual(worlds.global_mass, fixture.Fraction(1, 1))
        self.assertEqual(tuple(
            (pair.oop_hand, pair.ip_hand,
             str(pair.normalized_mass), str(pair.per_river_weight))
            for pair in worlds.pairs
        ), (
            ("AhAs", "AcAd", "4/21", "1/231"),
            ("AhAs", "KcKd", "1/7", "1/308"),
            ("KhKs", "AcAd", "8/21", "2/231"),
            ("KhKs", "KcKd", "2/7", "1/154"),
        ))

    def test_rank_free_production_structure_census_and_raise_actions(self):
        forbidden = AssertionError("preflight cannot rank or train")
        with patch("pokerlab.cards.rank_hand", side_effect=forbidden), \
             patch("pokerlab.postflop_solver.rank_hand", side_effect=forbidden), \
             patch("pokerlab.postflop_solver.train", side_effect=forbidden), \
             patch("pokerlab.postflop_solver.train_plus", side_effect=forbidden), \
             patch("pokerlab.postflop_solver.train_planned", side_effect=forbidden), \
             patch("pokerlab.postflop_solver.train_public_batched", side_effect=forbidden):
            result = fixture.census()

        self.assertEqual((result.pairs, result.worlds), (4, 176))
        self.assertEqual(result.global_physical_mass, fixture.Fraction(1))
        self.assertEqual((result.public_candidates, result.reachable_rivers), (48, 48))
        self.assertEqual((result.public_nodes, result.decisions), (3039, 1254))
        self.assertEqual((result.information_rows, result.depth), (2404, 9))
        self.assertEqual(result.visited_decisions_per_world, 32)
        self.assertEqual(len(result.public_tree_sha256), 64)
        self.assertEqual(result.public_tree_sha256,
                         fixture.census().public_tree_sha256)
        self.assertFalse(fixture.FIXTURE["config"]["include_all_in"])
        self.assertIn("raise@150", result.action_tokens)
        self.assertIn("all_in@220", result.action_tokens)

    def test_fixed_forecast_grid_and_reference_cap_boundaries(self):
        self.assertEqual(fixture.FORECAST_ITERATIONS, (100, 1000, 1500))
        result = fixture.census()
        expected = {
            ("materialized", 100): 1_689_600,
            ("materialized", 1000): 16_896_000,
            ("materialized", 1500): 25_344_000,
            ("matrix-free", 100): 1_841_634,
            ("matrix-free", 1000): 18_252_234,
            ("matrix-free", 1500): 27_369_234,
        }
        forecasts = {(row.backend, row.iterations): row for row in result.forecasts}
        self.assertEqual(set(forecasts), set(expected))
        for key, work in expected.items():
            row = forecasts[key]
            self.assertEqual(row.work, work)
            self.assertEqual(row.reference_cap, 30_000_000)
            self.assertTrue(row.within_reference_cap)
            self.assertEqual(row.reference_cap_label, "WITHIN_REFERENCE_CAP")

        self.assertEqual(fixture.REFERENCE_BOUNDARIES, {
            "materialized": {
                "last_within_cap_iterations": 1775,
                "first_over_cap_iterations": 1776,
                "first_over_cap_work": 30_007_296,
            },
            "matrix-free": {
                "last_within_cap_iterations": 1644,
                "first_over_cap_iterations": 1645,
                "first_over_cap_work": 30_013_164,
            },
        })
        dimensions = (176, 32, 3039, 2)
        materialized_reject = fixture.forecast_for(
            "materialized", 1776, *dimensions[:2], *dimensions[2:])
        matrix_reject = fixture.forecast_for(
            "matrix-free", 1645, *dimensions[:2], *dimensions[2:])
        self.assertEqual(materialized_reject.work, 30_007_296)
        self.assertEqual(matrix_reject.work, 30_013_164)
        self.assertFalse(materialized_reject.within_reference_cap)
        self.assertFalse(matrix_reject.within_reference_cap)
        self.assertEqual(materialized_reject.reference_cap_label,
                         "EXCEEDS_REFERENCE_CAP")
        self.assertEqual(matrix_reject.reference_cap_label,
                         "EXCEEDS_REFERENCE_CAP")

    def test_forecast_rejects_unsupported_backend_and_invalid_iterations(self):
        args = (1, 1, 1, 1)
        with self.assertRaisesRegex(ValueError, "backend"):
            fixture.forecast_work("native", 1, *args)
        with self.assertRaisesRegex(ValueError, "positive integers"):
            fixture.forecast_work("materialized", True, *args)
        with self.assertRaisesRegex(ValueError, "positive integers"):
            fixture.forecast_work("matrix-free", -1, *args)


if __name__ == "__main__":
    unittest.main()
