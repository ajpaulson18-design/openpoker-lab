import unittest
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from scripts.preflop_validation import compare_result, physical_worlds, replay_policy

SB = "AsAd"
BB = "KsKd"
RUNOUTS = ("2c3c4d7h8h", "2c3c4dKc8s")
CONFIG = {"starting_stack": [3, 3], "raise_sizes": [0.5],
          "max_raises": 1, "include_all_in": False}
FLOP = {"bet_sizes": [0.5], "raise_sizes": [0.5],
        "max_raises": 1, "include_all_in": False}
CHECKDOWN = {
    "config": CONFIG, "runouts": RUNOUTS, "flop_config": FLOP,
    "postflop_scope": "flop-checkdown", "iterations": 10,
    "algorithm": "cfrplus", "averaging_delay": 5,
    "traversal": "public-batched", "diagnostics": "public-batched",
    "resource_model": "public-vector",
}


class PreflopFlopCheckdownTests(unittest.TestCase):
    def test_hidden_future_checkdown_replays_and_exposes_only_preflop_flop_rows(self):
        result = solver.solve_preflop(SB, BB, **CHECKDOWN)
        oracle = replay_policy(result, SB, BB, config=CONFIG, runouts=RUNOUTS,
                               flop_config=FLOP, postflop_scope="flop-checkdown")
        compare_result(result, oracle)
        physical = physical_worlds(SB, BB, RUNOUTS)
        self.assertEqual({world[3] for world in physical}, {-1, 1})
        self.assertEqual(result["solver_version"], "preflop-flop-checkdown-v1")
        self.assertEqual(result["postflop_scope"], "flop-checkdown")
        self.assertEqual(set(result["postflop_action_configs"]), {"flop"})
        self.assertIn("forced checkdown", result["scope"])
        self.assertTrue(any(row["street"] == "preflop" for row in result["strategy"]))
        self.assertTrue(any(row["street"] == "flop" for row in result["strategy"]))
        self.assertFalse(any(row["street"] in ("turn", "river")
                             for row in result["strategy"]))
        flop_rows = [row for row in result["strategy"] if row["street"] == "flop"]
        self.assertTrue(flop_rows)
        public_keys = set()
        for row in flop_rows:
            key = (row["player"], row["hand"], tuple(row["history"]))
            self.assertNotIn(key, public_keys)
            public_keys.add(key)
            self.assertEqual(row["revealed_board"], ["2c", "3c", "4d"])
            self.assertFalse(any(token.startswith(("turn@", "river@"))
                                 for token in row["history"]))
            self.assertEqual(sum(token.startswith("flop@") for token in row["history"]), 1)
        preflop_rows = [row for row in result["strategy"] if row["street"] == "preflop"]
        root = next(row for row in preflop_rows
                    if row["player"] == "sb" and not row["history"])
        self.assertIn("fold", {a["name"] for a in root["actions"]})
        self.assertIn("call", {a["name"] for a in root["actions"]})
        self.assertIn("raise", {a["name"] for a in root["actions"]})
        bb_after_limp = [row for row in preflop_rows if row["player"] == "bb"
                         and "call" in row["history"]]
        self.assertTrue(bb_after_limp)
        self.assertIn("check", {a["name"] for a in bb_after_limp[0]["actions"]})
        self.assertIn("raise", {a["name"] for a in bb_after_limp[0]["actions"]})
        bb_facing_open = [row for row in preflop_rows if row["player"] == "bb"
                          and "raise@2" in row["history"]]
        self.assertTrue(bb_facing_open)
        self.assertEqual({a["name"] for a in bb_facing_open[0]["actions"]},
                         {"fold", "call"})


    def test_weighted_asymmetric_short_call_refund_replays(self):
        config = {"starting_stack": [2.25, 1.5], "raise_sizes": [0.5],
                  "max_raises": 1, "include_all_in": False}
        sb_range = "AsAd:1,AhAc:0.25"
        bb_range = "KsKd:1,KcKh:0.5"
        runouts = ("2c3c4d7h8h", "2c3c4dKc8s", "Ac2c3d7h8h")
        options = dict(CHECKDOWN)
        options.update(config=config, runouts=runouts)
        result = solver.solve_preflop(sb_range, bb_range, **options)
        oracle = replay_policy(result, sb_range, bb_range, config=config,
                               runouts=runouts, flop_config=FLOP,
                               postflop_scope="flop-checkdown")
        compare_result(result, oracle)
        self.assertGreater(len(result["private_pair_probabilities"]), 1)
        self.assertAlmostEqual(sum(row["probability"] for row in
                                   result["private_pair_probabilities"]), 1.0, places=12)
        root = next(row for row in result["strategy"]
                    if row["street"] == "preflop" and row["player"] == "sb"
                    and not row["history"])
        self.assertTrue(any(action["name"] == "raise" for action in root["actions"]))
        bb_short_call = next(row for row in result["strategy"]
                             if row["street"] == "preflop" and row["player"] == "bb"
                             and "raise@2" in row["history"])
        self.assertEqual({a["name"] for a in bb_short_call["actions"]}, {"fold", "call"})
        self.assertEqual(next(a["raise_to"] for a in bb_short_call["actions"]
                              if a["name"] == "call"), 1.5)

    def test_hidden_checkdown_value_matches_forced_check_future_policy(self):
        collapsed = solver.solve_preflop(SB, BB, **CHECKDOWN)
        options = dict(CHECKDOWN, postflop_scope="all-streets")
        expanded = solver.solve_preflop(SB, BB, **options)
        rows = {(r["player"], r["hand"], tuple(r["history"])): r
                for r in collapsed["strategy"]}
        future_rows = []
        for row in expanded["strategy"]:
            if row["street"] in ("preflop", "flop"):
                key = row["player"], row["hand"], tuple(row["history"])
                expected = rows[key]
                self.assertEqual([a["history_key"] for a in row["actions"]],
                                 [a["history_key"] for a in expected["actions"]])
                for actual, source in zip(row["actions"], expected["actions"]):
                    actual["probability"] = source["probability"]
            else:
                future_rows.append(row)
                names = {a["name"] for a in row["actions"]}
                chosen = "check" if "check" in names else "call"
                for action in row["actions"]:
                    action["probability"] = float(action["name"] == chosen)
        self.assertTrue(future_rows)
        # Only profile value is equivalent: the all-streets model still permits
        # future deviations, so its BR values are not the checkdown BR values.
        oracle = replay_policy(expanded, SB, BB, config=CONFIG, runouts=RUNOUTS,
                               flop_config=FLOP)
        self.assertAlmostEqual(collapsed["value_sb"], oracle["value_sb"], delta=1e-12)
        self.assertGreaterEqual(oracle["sb_best_response_value"] + 1e-12,
                                collapsed["sb_best_response_value"])
        self.assertGreaterEqual(oracle["bb_best_response_value"] + 1e-12,
                                collapsed["bb_best_response_value"])

    def test_replay_requires_explicit_matching_scope(self):
        result = solver.solve_preflop(SB, BB, **CHECKDOWN)
        args = {"config": CONFIG, "runouts": RUNOUTS, "flop_config": FLOP}
        with self.assertRaisesRegex(ValueError, "scope"):
            replay_policy(result, SB, BB, **args)
        with self.assertRaisesRegex(ValueError, "scope"):
            replay_policy(result, SB, BB, **args, postflop_scope="invalid")
        with self.assertRaisesRegex(ValueError, "does not accept"):
            replay_policy(result, SB, BB, **args,
                          postflop_scope="flop-checkdown", turn_config={})

    def test_compact_checkpoint_policy_has_same_hidden_game_values(self):
        options = dict(CHECKDOWN, iterations=20, averaging_delay=5,
                       target_nash_conv=10, convergence_check_interval=10)
        original = solver.solve_preflop(SB, BB, **options)
        compact = solver.solve_preflop(SB, BB, **options, private_indexing="compact")
        self.assertEqual(original["strategy"], compact["strategy"])
        self.assertEqual(original["convergence_checkpoints"], compact["convergence_checkpoints"])
        self.assertTrue(compact["stopped_early"])
        self.assertEqual(compact["completed_iterations"], 10)
        self.assertEqual(compact["vector_work_budget"]["iterations"], 20)
        compare_result(compact, replay_policy(
            compact, SB, BB, config=CONFIG, runouts=RUNOUTS,
            flop_config=FLOP, postflop_scope="flop-checkdown"))

    def test_default_scope_payload_matches_explicit_all_streets(self):
        kwargs = {"config": {"starting_stack": [1.5, 1.5], "max_raises": 0},
                  "runouts": ("2c3c4d7h8h",), "iterations": 10,
                  "algorithm": "vanilla"}
        implicit = solver.solve_preflop(SB, BB, **kwargs)
        explicit = solver.solve_preflop(SB, BB, **kwargs,
                                        postflop_scope="all-streets")
        self.assertEqual(implicit, explicit)
        self.assertNotIn("postflop_scope", explicit)

    def test_invalid_scope_and_combinations_reject_before_enumeration(self):
        cases = [
            ({"postflop_scope": "future"}, "postflop_scope"),
            ({"postflop_scope": "flop-checkdown", "turn_config": {}}, "does not accept"),
            ({"postflop_scope": "flop-checkdown", "river_config": {}}, "does not accept"),
            ({"postflop_scope": "flop-checkdown", "algorithm": "vanilla",
              "averaging_delay": 0}, "requires positive-delay CFR"),
            ({"postflop_scope": "flop-checkdown", "resource_model": "world"},
             "requires positive-delay CFR"),
            ({"postflop_scope": "flop-checkdown", "traversal": "recursive"},
             "(?i)public-vector resource model|requires positive-delay CFR"),
            ({"postflop_scope": "flop-checkdown", "diagnostics": "recursive"},
             "(?i)public-vector resource model|requires positive-delay CFR"),
        ]
        for extra, message in cases:
            options = dict(CHECKDOWN)
            options.update(extra)
            with self.subTest(extra=extra), patch.object(
                    solver, "_enumerate_physical_worlds") as enumerate_worlds:
                with self.assertRaisesRegex(ValueError, message):
                    solver.solve_preflop(SB, BB, **options)
                enumerate_worlds.assert_not_called()

    def test_vector_and_template_guards_precede_training_view_and_trainer(self):
        with patch.object(solver, "estimate_vector_budget",
                          side_effect=ValueError("vector cap")):
            with patch.object(solver, "_positive_pot_training_view") as view:
                with patch.object(solver, "train_delayed_public_cfrplus") as trainer:
                    with self.assertRaisesRegex(ValueError, "vector cap"):
                        solver.solve_preflop(SB, BB, **CHECKDOWN)
                    view.assert_not_called()
                    trainer.assert_not_called()
        with patch.object(solver, "_MAX_PUBLIC_NODES", 1):
            with patch.object(solver, "_positive_pot_training_view") as view:
                with patch.object(solver, "train_delayed_public_cfrplus") as trainer:
                    with self.assertRaisesRegex(ValueError, "decisions"):
                        solver.solve_preflop(SB, BB, **CHECKDOWN)
                    view.assert_not_called()
                    trainer.assert_not_called()
        # The underlying existing postflop template cap is still enforced.
        with patch.object(solver._postflop, "_MAX_PUBLIC_NODES", 1):
            with patch.object(solver, "_positive_pot_training_view") as view:
                with patch.object(solver, "train_delayed_public_cfrplus") as trainer:
                    with self.assertRaisesRegex(ValueError, "decision nodes"):
                        solver.solve_preflop(SB, BB, **CHECKDOWN)
                    view.assert_not_called()
                    trainer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
