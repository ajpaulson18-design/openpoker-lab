import unittest
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from pokerlab import preflop_vector_budget as vector_budget
from scripts.preflop_validation import compare_result, replay_policy
from tests.test_preflop_flop_checkdown import FLOP

SB, BB = "AsAd", "KsKd"
RUNOUTS = ("2c3c4d7h8h", "2c3c4dKc8s")
CONFIG = {"starting_stack": [3, 3], "raise_sizes": [0.5],
          "max_raises": 1, "include_all_in": False}
BASE = {"config": CONFIG, "runouts": RUNOUTS, "flop_config": FLOP,
        "postflop_scope": "flop-checkdown", "iterations": 20,
        "algorithm": "cfrplus", "averaging_delay": 10,
        "traversal": "public-batched", "diagnostics": "public-batched",
        "resource_model": "public-vector"}
GROUPED = dict(BASE, future_indexing="flop-sign", world_admission="grouped-vector")

class GroupedWorldAdmissionTests(unittest.TestCase):
    def test_default_and_explicit_legacy_mode_are_exactly_unchanged(self):
        default = solver.solve_preflop(SB, BB, **BASE)
        explicit = solver.solve_preflop(SB, BB, **BASE, world_admission="world-iterations")
        self.assertEqual(default, explicit)
        self.assertNotIn("world_admission", default)
        self.assertEqual(default["limits"]["world_iterations"], solver._MAX_WORLD_ITERATIONS)

    def test_invalid_mode_or_missing_dependencies_reject_before_enumeration(self):
        invalid = [
            {"world_admission": "other"},
            {"world_admission": "grouped-vector"},
            {"world_admission": "grouped-vector", "postflop_scope": "all-streets",
             "future_indexing": "flop-sign"},
            {"world_admission": "grouped-vector", "averaging_delay": 0,
             "future_indexing": "flop-sign"},
            {"world_admission": "grouped-vector", "future_indexing": "original"},
        ]
        for changes in invalid:
            args = dict(BASE, **changes)
            with self.subTest(changes=changes), patch.object(solver, "_enumerate_physical_worlds") as enumerate_worlds:
                with self.assertRaises(ValueError):
                    solver.solve_preflop(SB, BB, **args)
                enumerate_worlds.assert_not_called()

    def test_construction_row_guard_boundary_and_one_over_precede_ranking(self):
        # One compatible private pair and one physical outcome. The admission
        # multiplier is patched small so the exact boundary is cheap to prove.
        with patch.object(solver, "_MAX_WORLD_ITERATIONS", 2), \
             patch.object(solver, "_MAX_CANDIDATE_HAND_ITERATIONS", 100):
            result = solver._enumerate_physical_worlds(SB, BB, (RUNOUTS[0],), 10,
                                                       world_work_iterations=2)
            self.assertEqual(len(result[1]), 1)
        with patch.object(solver, "_MAX_WORLD_ITERATIONS", 1), \
             patch.object(solver, "_MAX_CANDIDATE_HAND_ITERATIONS", 100), \
             patch.object(solver, "_rank_world") as rank:
            with self.assertRaisesRegex(ValueError, "3 million world iterations"):
                solver._enumerate_physical_worlds(SB, BB, (RUNOUTS[0],), 10,
                                                  world_work_iterations=2)
            rank.assert_not_called()

    def test_candidate_pair_guard_still_uses_requested_iterations(self):
        with patch.object(solver, "_MAX_CANDIDATE_HAND_ITERATIONS", 9), \
             patch.object(solver, "RunoutBlockerIndex") as index:
            with self.assertRaisesRegex(ValueError, "candidate-pair iterations"):
                solver._enumerate_physical_worlds(SB, BB, (RUNOUTS[0],), 10,
                                                  world_work_iterations=1)
            index.assert_not_called()

    def test_full_requested_vector_ceiling_rejects_before_any_view_copy_or_training(self):
        options = dict(GROUPED, private_indexing="compact", target_nash_conv=100.0,
                       convergence_check_interval=5)
        real_estimate = solver.estimate_vector_budget
        seen = []
        def capture(*args, **kwargs):
            seen.append(args[3])
            return real_estimate(*args, **kwargs)
        with patch.object(vector_budget, "MAX_TOTAL_LOOP_ENTRIES", 1), \
             patch.object(solver, "estimate_vector_budget", capture), \
             patch.object(solver, "compact_private_indices") as compact, \
             patch.object(solver, "group_hidden_futures") as grouping, \
             patch.object(solver, "_positive_pot_training_view") as view, \
             patch.object(solver, "train_delayed_public_cfrplus") as trainer:
            with self.assertRaisesRegex(ValueError, "estimated loop entries"):
                solver.solve_preflop(SB, BB, **options)
        self.assertEqual(seen, [20])
        compact.assert_not_called(); grouping.assert_not_called()
        view.assert_not_called(); trainer.assert_not_called()

    def test_grouped_higher_ceiling_compact_stop_replays_full_physical_worlds(self):
        # With a patched legacy world-work cap of 20, two physical rows at the
        # requested 20 iterations would fail the old 40-unit product. The
        # opt-in construction charge is 2*10, while vector admission still sees
        # the full requested ceiling and an early stop cannot lower it.
        options = dict(GROUPED, private_indexing="compact", target_nash_conv=100.0,
                       convergence_check_interval=5)
        with patch.object(solver, "_MAX_WORLD_ITERATIONS", 20):
            with patch.object(solver, "_rank_world") as rank:
                with self.assertRaisesRegex(ValueError, "world iterations"):
                    solver.solve_preflop(SB, BB, **dict(options, world_admission="world-iterations"))
                rank.assert_not_called()
            result = solver.solve_preflop(SB, BB, **options)
        oracle = replay_policy(result, SB, BB, config=CONFIG, runouts=RUNOUTS,
                               flop_config=FLOP, postflop_scope="flop-checkdown")
        compare_result(result, oracle)
        self.assertEqual(result["worlds"], len(RUNOUTS))
        self.assertEqual(result["world_admission"], "grouped-vector")
        self.assertEqual(result["world_construction_admission_iterations"], 10)
        self.assertEqual(result["limits"]["reference_world_iterations"], 20)
        self.assertIsNone(result["limits"]["world_iterations"])
        self.assertEqual(result["limits"]["constructed_worlds"], 2)
        self.assertEqual(result["limits"]["candidate_pair_iterations"], solver._MAX_CANDIDATE_HAND_ITERATIONS)
        self.assertEqual(result["vector_work_budget"]["iterations"], 20)
        self.assertEqual(result["vector_work_budget"]["budget_version"],
                         "preflop-public-vector-grouped-world-budget-v6")
        self.assertEqual(result["vector_work_budget"]["base_budget_version"],
                         "preflop-public-vector-future-group-budget-v5")
        self.assertEqual(result["completed_iterations"], 15)
        self.assertTrue(result["stopped_early"])

    def test_public_one_over_construction_cap_rejects_before_ranking_and_copies(self):
        # Public opt-in is fixed at ten, not the requested twenty or a freely
        # selected multiplier: two worlds are one over floor(19/10).
        with patch.object(solver, "_MAX_WORLD_ITERATIONS", 19), \
                patch.object(solver, "_rank_world") as rank, \
                patch.object(solver, "compact_private_indices") as compact, \
                patch.object(solver, "group_hidden_futures") as group:
            with self.assertRaisesRegex(ValueError, "world iterations"):
                solver.solve_preflop(SB, BB, **dict(GROUPED, private_indexing="compact"))
            rank.assert_not_called()
            compact.assert_not_called()
            group.assert_not_called()

    def test_actual_compact_renumbering_and_full_ceiling_checkpoint_replay(self):
        sb, bb = "AsAd,QsQd", "KsKd,JhJc"
        runouts = ("As2c3c7h8h", "As2c3c7h9h")
        options = dict(GROUPED, runouts=runouts, target_nash_conv=100,
                       convergence_check_interval=5)
        # Every selected outcome blocks SB's original index zero; compaction
        # really maps the remaining index one to zero before grouping.
        with patch.object(solver, "_MAX_WORLD_ITERATIONS", 40):
            original = solver.solve_preflop(sb, bb, **options)
            compact = solver.solve_preflop(sb, bb, **options, private_indexing="compact")
        metadata = compact["private_indexing_metadata"]
        self.assertEqual(metadata["original_hand_dimensions"], [2, 2])
        self.assertEqual(metadata["compact_hand_dimensions"], [1, 2])
        self.assertEqual(metadata["original_active_indices"][0], [1])
        self.assertEqual(compact["strategy"], original["strategy"])
        self.assertEqual(compact["convergence_checkpoints"], original["convergence_checkpoints"])
        self.assertEqual(compact["worlds"], 4)
        self.assertEqual(compact["vector_work_budget"]["iterations"], 20)
        self.assertEqual(compact["vector_work_budget"]["private_index_world_fields"], 28)
        oracle = replay_policy(compact, sb, bb, config=CONFIG, runouts=runouts,
                               flop_config=FLOP, postflop_scope="flop-checkdown")
        compare_result(compact, oracle)

if __name__ == "__main__":
    unittest.main()
