import itertools
import unittest
from unittest.mock import patch

from pokerlab.cards import DECK, cards
from pokerlab.preflop_solver import solve_preflop
from pokerlab.preflop_tree import PreflopConfig


_LOWER_POSTFLOP = {
    "bet_sizes": (0.5,), "raise_sizes": (),
    "max_raises": 0, "include_all_in": False,
}
_RUNOUTS = (
    "2c 3d 4h 5s 6c",
    "4h 2c 3d 6c 5s",  # same canonical flop; turn and river are swapped
)


class PreflopSolverTests(unittest.TestCase):
    def solve(self, *, traversal="recursive", algorithm="vanilla", **kwargs):
        arguments = {"runouts": _RUNOUTS, "flop_config": _LOWER_POSTFLOP,
                     "iterations": 10, "traversal": traversal,
                     "algorithm": algorithm}
        arguments.update(kwargs)
        return solve_preflop("AsAh", "KsKh", PreflopConfig(max_raises=0),
                             **arguments)

    def test_canonical_flop_and_ordered_turn_river_worlds_are_distinct(self):
        result = self.solve()
        self.assertEqual(result["worlds"], 2)
        self.assertEqual(result["compatible_private_pairs"], 1)
        self.assertEqual(result["selected_runouts"], [
            ["2c", "3d", "4h", "5s", "6c"],
            ["2c", "3d", "4h", "6c", "5s"],
        ])
        self.assertEqual(result["runout_mode"], "conditioned-ordered-selected-runouts")
        self.assertEqual(result["private_pair_probabilities"][0]["probability"], 1.0)

        with self.assertRaisesRegex(ValueError, "Duplicate canonical"):
            solve_preflop("AsAh", "KsKh", PreflopConfig(max_raises=0),
                          runouts=("2c3d4h5s6c", "4h2c3d5s6c"),
                          flop_config=_LOWER_POSTFLOP, iterations=10)
        for bad in ((), ("2c 3d 4h 5s",), ("2c 3d 4h 5s 5s",),
                    ("2c 3d 4h 5s 7x",)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                solve_preflop("AsAh", "KsKh", PreflopConfig(max_raises=0),
                              runouts=bad, iterations=10)

    def test_global_conditioning_changes_private_pair_probabilities_by_blockers(self):
        result = solve_preflop(
            "AsAh,QsQh", "KsKh", PreflopConfig(max_raises=0),
            runouts=("As 2c 3c 4c 5c", "2s 3d 4h 5s 6c"),
            flop_config=_LOWER_POSTFLOP, iterations=10,
        )
        self.assertEqual(result["worlds"], 3)
        probabilities = {row["sb_hand"]: row["probability"]
                         for row in result["private_pair_probabilities"]}
        self.assertAlmostEqual(probabilities["AhAs"], 1 / 3)
        self.assertAlmostEqual(probabilities["QhQs"], 2 / 3)
        self.assertAlmostEqual(sum(probabilities.values()), 1.0)

    def test_serialized_strategy_keeps_global_positions_and_reveals_no_future_cards(self):
        result = self.solve()
        rows = result["strategy"]
        self.assertTrue(any(row["player"] == "sb" and row["street"] == "preflop"
                            for row in rows))
        flop_rows = [row for row in rows if row["street"] == "flop"]
        self.assertTrue(flop_rows)
        flop_openers = [row for row in flop_rows
                        if row["history"][-1].startswith("flop@")]
        self.assertTrue(flop_openers)
        self.assertTrue(all(row["player"] == "bb" for row in flop_openers))
        for row in rows:
            board = row["revealed_board"]
            expected = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}[row["street"]]
            self.assertEqual(len(board), expected)
            history = row["history"]
            revealed = [token for token in history
                        if token.startswith(("flop@", "turn@", "river@"))]
            self.assertEqual(len(board), sum(
                3 if token.startswith("flop@") else 1 for token in revealed
            ))
            self.assertNotIn("opponent_hand", row)
            for action in row["actions"]:
                self.assertEqual(action["history_key"], action["name"] if action["name"]
                                 not in {"bet", "raise", "all_in"} else
                                 f"{action['name']}@{action['raise_to']:.9f}".rstrip("0").rstrip("."))
        self.assertEqual(result["strategy_schema"], "preflop-strategy-v1")

    def test_postflop_raise_to_uses_whole_hand_contribution_and_stage_inheritance(self):
        result = self.solve(turn_config={"bet_sizes": (0.25,)})
        flop = result["postflop_action_configs"]["flop"]
        turn = result["postflop_action_configs"]["turn"]
        river = result["postflop_action_configs"]["river"]
        self.assertEqual(flop["bet_sizes"], [0.5])
        self.assertEqual(turn["bet_sizes"], [0.25])
        self.assertEqual(river["bet_sizes"], [0.5])
        flop_bets = [action for row in result["strategy"] if row["street"] == "flop"
                     for action in row["actions"] if action["name"] == "bet"]
        self.assertTrue(flop_bets)
        # The settled blind pot is 2 chips; a half-pot bet is 1 more chip,
        # and its serialized whole-hand contribution is matched preflop 1 + 1.
        self.assertTrue(all(abs(action["raise_to"] - 2.0) < 1e-9
                            for action in flop_bets))

    def test_recursive_and_planned_trainers_agree_for_vanilla_and_dcfr(self):
        for algorithm in ("vanilla", "dcfr"):
            with self.subTest(algorithm=algorithm):
                recursive = self.solve(algorithm=algorithm)
                planned = self.solve(algorithm=algorithm, traversal="planned")
                for field in ("value_sb", "sb_best_response_value",
                              "bb_best_response_value", "nash_conv"):
                    self.assertAlmostEqual(recursive[field], planned[field], places=11)
                self.assertEqual(recursive["strategy"], planned["strategy"])

    def test_all_in_preflop_refund_is_not_double_counted_and_has_no_future_actions(self):
        result = solve_preflop(
            "AsAh", "KsKh", PreflopConfig(starting_stack=(0.5, 1), max_raises=0),
            runouts=("2c3d4h5s6c",), iterations=10,
        )
        self.assertEqual(result["decisions"], 0)
        self.assertEqual(result["strategy"], [])
        self.assertEqual(result["worlds"], 1)
        self.assertAlmostEqual(result["value_bb"], -result["value_sb"])

    def test_rejects_full_deck_before_rank_or_world_allocation(self):
        with patch("pokerlab.preflop_solver.rank_hand") as rank:
            with self.assertRaisesRegex(ValueError, "Full-deck.*34,246,080"):
                solve_preflop("AsAh", "KsKh", PreflopConfig(max_raises=0),
                              iterations=10)
            rank.assert_not_called()

    def test_input_and_aggregate_resource_limits_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "candidate-pair iterations"):
            solve_preflop("random", "random", PreflopConfig(max_raises=0),
                          runouts=(_RUNOUTS[0],), iterations=10)
        selected = []
        available = [card for card in DECK if card not in {"As", "Ah", "Ks", "Kh"}]
        for five in itertools.combinations(available, 5):
            selected.append(five)
            if len(selected) == 301:
                break
        with self.assertRaisesRegex(ValueError, "3 million world iterations"):
            solve_preflop("AsAh", "KsKh", PreflopConfig(max_raises=0),
                          runouts=selected, flop_config=_LOWER_POSTFLOP,
                          iterations=10_000)

        with patch("pokerlab.preflop_solver._MAX_PUBLIC_STATES", 2):
            with self.assertRaisesRegex(ValueError, "Combined preflop/postflop tree"):
                self.solve()

    def test_stage_configs_are_action_only_and_traversal_is_supported(self):
        with self.assertRaisesRegex(ValueError, "Unknown postflop stage config fields"):
            self.solve(flop_config={**_LOWER_POSTFLOP, "pot": 100})
        with self.assertRaisesRegex(ValueError, "Unknown postflop stage config fields"):
            self.solve(flop_config={**_LOWER_POSTFLOP, "effective_stack": (500, 500)})
        with self.assertRaisesRegex(TypeError, "action mappings"):
            self.solve(flop_config=object())
        with self.assertRaisesRegex(ValueError, "recursive or planned"):
            self.solve(traversal="public-batched")

    def test_shared_flop_turn_prefix_preserves_river_dependent_hidden_outcomes(self):
        from scripts.preflop_validation import compare_result, physical_worlds, replay_policy

        runouts = (
            "2c3c4d7h8h",  # SB wins with a pair of aces.
            "2c3c4d7hKc",  # Same public prefix; BB wins with three kings.
            "2c3c4dKc8h",  # Same flop, but the ordered turn is different.
        )
        worlds = physical_worlds("AsAd", "KsKd", runouts)
        self.assertEqual({world[3] for world in worlds}, {-1, 1})
        self.assertTrue(all(world[4][:4] == tuple(cards("2c3c4d7h", 4))
                            for world in worlds[:2]))

        kwargs = {
            "config": {"starting_stack": 4, "max_raises": 0,
                       "raise_sizes": [], "include_all_in": False},
            "runouts": runouts,
            "flop_config": {"bet_sizes": [.5], "raise_sizes": [],
                            "max_raises": 0, "include_all_in": False},
        }
        for traversal in ("recursive", "planned"):
            with self.subTest(traversal=traversal):
                result = solve_preflop(
                    "AsAd", "KsKd", iterations=20, traversal=traversal, **kwargs)
                oracle = replay_policy(result, "AsAd", "KsKd", **kwargs)
                compare_result(result, oracle)
                flop_rows = [row for row in result["strategy"]
                             if row["player"] == "bb" and row["street"] == "flop"
                             and row["history"][-1] == "flop@2c3c4d"]
                self.assertEqual(len(flop_rows), 1)
                self.assertEqual(flop_rows[0]["revealed_board"], ["2c", "3c", "4d"])
                self.assertEqual(oracle["checked_information_sets"],
                                 len(result["strategy"]))

    def test_runout_iterables_are_bounded_before_materialization(self):
        from pokerlab import preflop_solver

        with patch.object(preflop_solver, "_MAX_SELECTED_RUNOUTS", 1):
            with self.assertRaisesRegex(ValueError, "300,000-outcome"):
                preflop_solver._requested_runouts(iter(_RUNOUTS))

        consumed = []
        def long_outcome():
            for card in (*cards(_RUNOUTS[0], 5), "7c", "8c", "9c"):
                consumed.append(card)
                yield card

        with self.assertRaisesRegex(ValueError, "exactly five"):
            preflop_solver._requested_runouts([long_outcome()])
        self.assertEqual(len(consumed), 6)


if __name__ == "__main__":
    unittest.main()
