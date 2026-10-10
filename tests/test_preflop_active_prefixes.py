import unittest
from unittest.mock import patch

from pokerlab import preflop_solver as solver


def _original_legal_private_hands(worlds):
    """Frozen copy of the former inline solver loop for exact comparisons."""
    legal = {(player, ()): set() for player in (0, 1)}
    for world in worlds:
        future = solver.cards(world[4], 3) + (world[5], world[6])
        for player in (0, 1):
            legal[(player, ())].add(world[player])
            for length in (3, 4, 5):
                legal.setdefault((player, future[:length]), set()).add(world[player])
    return legal


class PreflopActivePrefixTests(unittest.TestCase):
    def setUp(self):
        self.sb = "AsAd:1,AhAc:0.25"
        self.bb = "KsKd:1,KcKh:0.5"
        self.runouts = (
            "2c3c4d7h8h", "2c3c4dKc8s",
            "5h6sJc7d8d", "5h6sJc9dTd",
        )
        self.config = {"starting_stack": [2.25, 1.5], "raise_sizes": [0.5],
                       "max_raises": 1, "include_all_in": False}

    def test_checkdown_legal_sets_equal_old_root_and_flop_sets(self):
        worlds = solver._enumerate_physical_worlds(
            self.sb, self.bb, self.runouts, 1)[1]
        expected = _original_legal_private_hands(worlds)
        actual = solver._legal_private_hands(worlds, "flop-checkdown")
        expected_active = {key: hands for key, hands in expected.items()
                           if len(key[1]) in (0, 3)}
        self.assertEqual(actual, expected_active)
        self.assertTrue(any(len(key[1]) == 4 for key in expected))
        self.assertTrue(any(len(key[1]) == 5 for key in expected))

    def test_checkdown_decodes_each_distinct_flop_once(self):
        worlds = solver._enumerate_physical_worlds(
            self.sb, self.bb, self.runouts, 1)[1]
        with patch.object(solver, "cards", wraps=solver.cards) as decoder:
            legal = solver._legal_private_hands(worlds, "flop-checkdown")
        self.assertEqual(decoder.call_count, 2)
        self.assertEqual({call.args[0] for call in decoder.call_args_list},
                         {world[4] for world in worlds})
        self.assertEqual(len(legal), 6)

    def test_existing_world_iteration_cap_still_precedes_legal_set_build(self):
        kwargs = {
            "config": self.config, "runouts": self.runouts,
            "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                            "max_raises": 0, "include_all_in": False},
            "postflop_scope": "flop-checkdown", "iterations": 10,
            "algorithm": "cfrplus", "averaging_delay": 5,
            "traversal": "public-batched", "diagnostics": "public-batched",
            "resource_model": "public-vector",
        }
        with patch.object(solver, "_MAX_WORLD_ITERATIONS", 1):
            with patch.object(solver, "_legal_private_hands") as legal:
                with self.assertRaisesRegex(ValueError, "world iterations"):
                    solver.solve_preflop(self.sb, self.bb, **kwargs)
                legal.assert_not_called()

    def test_all_streets_legal_sets_keep_the_literal_old_loop(self):
        worlds = solver._enumerate_physical_worlds(
            self.sb, self.bb, self.runouts, 1)[1]
        self.assertEqual(solver._legal_private_hands(worlds),
                         _original_legal_private_hands(worlds))
        self.assertEqual(solver._legal_private_hands(worlds, "all-streets"),
                         _original_legal_private_hands(worlds))

    def test_complete_solver_payload_is_exact_against_old_loop_for_both_scopes(self):
        common = {"config": self.config, "runouts": self.runouts,
                  "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                                  "max_raises": 0, "include_all_in": False}}
        scopes = (
            ("all-streets", {"iterations": 10, "algorithm": "vanilla"}),
            ("flop-checkdown", {"iterations": 10, "algorithm": "cfrplus",
                                "averaging_delay": 5, "traversal": "public-batched",
                                "diagnostics": "public-batched",
                                "resource_model": "public-vector"}),
        )
        for scope, extra in scopes:
            with self.subTest(scope=scope):
                kwargs = dict(common, postflop_scope=scope, **extra)
                expected = _original_legal_private_hands
                with patch.object(solver, "_legal_private_hands",
                                  side_effect=lambda worlds, _scope="all-streets": expected(worlds)):
                    baseline = solver.solve_preflop(self.sb, self.bb, **kwargs)
                optimized = solver.solve_preflop(self.sb, self.bb, **kwargs)
                self.assertEqual(optimized, baseline)


if __name__ == "__main__":
    unittest.main()
