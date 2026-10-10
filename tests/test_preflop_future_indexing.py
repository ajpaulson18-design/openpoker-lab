import gc
import unittest
import weakref
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from scripts.preflop_validation import compare_result, replay_policy
from tests.test_preflop_flop_checkdown import CHECKDOWN, FLOP

SB = "AsAd:1,AhAc:0.25"
BB = "KsKd:1,KcKh:0.5"
RUNOUTS = ("2c3c4d7h8h", "2c3c4d7h9h", "2c3c4dKc8s",
           "2c3d4h5s6c", "Ac2c3d7h8h")
OPTIONS = dict(CHECKDOWN, runouts=RUNOUTS,
               config={"starting_stack": [2.25, 1.5], "raise_sizes": [0.5],
                       "max_raises": 1, "include_all_in": False})


def replay(result):
    oracle = replay_policy(result, SB, BB, config=OPTIONS["config"],
                           runouts=RUNOUTS, flop_config=FLOP,
                           postflop_scope="flop-checkdown")
    compare_result(result, oracle)
    return oracle


class FutureIndexingTests(unittest.TestCase):
    def test_grouped_weighted_blocked_game_replays_full_worlds(self):
        original = solver.solve_preflop(SB, BB, **OPTIONS)
        explicit = solver.solve_preflop(SB, BB, **OPTIONS, future_indexing="original")
        self.assertEqual(original, explicit)
        grouped = solver.solve_preflop(SB, BB, **OPTIONS, future_indexing="flop-sign")
        a, b = replay(original), replay(grouped)
        for key in ("value_sb", "sb_best_response_value", "bb_best_response_value", "nash_conv"):
            self.assertAlmostEqual(a[key], b[key], places=11)
        for key in ("worlds", "selected_runouts", "reachable_runouts", "private_pair_probabilities",
                    "public_states", "decisions", "info_sets", "postflop_action_configs"):
            self.assertEqual(original[key], grouped[key])
        self.assertEqual([(r["player"], r["hand"], r["history"]) for r in original["strategy"]],
                         [(r["player"], r["hand"], r["history"]) for r in grouped["strategy"]])
        for a, b in zip(original["strategy"], grouped["strategy"]):
            self.assertIn(b["street"], ("preflop", "flop"))
            for x, y in zip(a["actions"], b["actions"]):
                self.assertAlmostEqual(x["probability"], y["probability"], places=11)
        meta = grouped["future_indexing_metadata"]
        self.assertEqual(meta["physical_world_count"], original["worlds"])
        self.assertLess(meta["training_world_rows"], original["worlds"])
        old, new = original["vector_work_budget"], grouped["vector_work_budget"]
        self.assertEqual(new["world_count"], old["world_count"])
        self.assertEqual(new["public_prefixes"], old["public_prefixes"])
        self.assertEqual(new["total_loop_entries_upper_bound"], old["total_loop_entries_upper_bound"] +
                         new["future_grouping"]["grouping_loop_entries_upper_bound"])

    def test_compact_grouped_checkpoints_replay_and_keep_requested_admission(self):
        options = dict(OPTIONS, iterations=20, target_nash_conv=10,
                       convergence_check_interval=10, future_indexing="flop-sign")
        original_ids = solver.solve_preflop(SB, BB, **options)
        compact = solver.solve_preflop(SB, BB, **options, private_indexing="compact")
        replay(compact)
        self.assertEqual(compact["strategy"], original_ids["strategy"])
        self.assertEqual(compact["convergence_checkpoints"], original_ids["convergence_checkpoints"])
        self.assertEqual(compact["completed_iterations"], 10)
        self.assertEqual(compact["vector_work_budget"]["iterations"], 20)
        self.assertEqual(compact["worlds"], original_ids["worlds"])
        self.assertEqual(compact["vector_work_budget"]["private_index_world_fields"], 7 * compact["worlds"])

    def test_invalid_modes_reject_before_enumeration(self):
        for changes in ({"future_indexing": "other"},
                        {"future_indexing": "flop-sign", "postflop_scope": "all-streets"},
                        {"future_indexing": "flop-sign", "averaging_delay": 0}):
            with self.subTest(changes=changes), patch.object(solver, "_enumerate_physical_worlds") as enumerate_worlds:
                with self.assertRaises(ValueError):
                    solver.solve_preflop(SB, BB, **dict(OPTIONS, **changes))
                enumerate_worlds.assert_not_called()

    def test_grouping_and_total_caps_precede_any_group_or_compact_copy(self):
        original = solver.solve_preflop(SB, BB, **OPTIONS)
        with patch("pokerlab.preflop_future_groups.MAX_GROUP_REFERENCE_SLOTS", 1), \
                patch.object(solver, "group_hidden_futures") as group, \
                patch.object(solver, "compact_private_indices") as compact:
            with self.assertRaises(ValueError):
                solver.solve_preflop(SB, BB, **OPTIONS, future_indexing="flop-sign", private_indexing="compact")
            group.assert_not_called()
            compact.assert_not_called()
        with patch.object(solver, "MAX_TOTAL_LOOP_ENTRIES", original["vector_work_budget"]["total_loop_entries_upper_bound"]), \
                patch.object(solver, "group_hidden_futures") as group:
            with self.assertRaisesRegex(ValueError, "Future grouping"):
                solver.solve_preflop(SB, BB, **OPTIONS, future_indexing="flop-sign")
            group.assert_not_called()
        with patch("pokerlab.preflop_vector_budget.MAX_PREFIX_EDGES", 1), \
                patch.object(solver, "group_hidden_futures") as group:
            with self.assertRaisesRegex(ValueError, "prefix edges"):
                solver.solve_preflop(SB, BB, **OPTIONS, future_indexing="flop-sign")
            group.assert_not_called()

    def test_grouped_view_released_after_success_and_trainer_failure(self):
        class View(list):
            pass
        refs = []
        real_group = solver.group_hidden_futures
        def tracked(worlds):
            view = View(real_group(worlds))
            refs.append(weakref.ref(view))
            return view
        with patch.object(solver, "group_hidden_futures", tracked):
            solver.solve_preflop(SB, BB, **OPTIONS, future_indexing="flop-sign", private_indexing="compact")
        gc.collect()
        self.assertIsNone(refs[-1]())
        with patch.object(solver, "group_hidden_futures", tracked), \
                patch.object(solver, "train_delayed_public_cfrplus", side_effect=RuntimeError("injected")):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                solver.solve_preflop(SB, BB, **OPTIONS, future_indexing="flop-sign", private_indexing="compact")
        gc.collect()
        self.assertIsNone(refs[-1]())


if __name__ == "__main__":
    unittest.main()
