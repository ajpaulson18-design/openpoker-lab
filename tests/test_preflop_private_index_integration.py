import gc
import unittest
import weakref
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from pokerlab import preflop_vector_budget as budget
from scripts.preflop_validation import compare_result, replay_policy


SB = ",".join([f"As{rank}s" for rank in "23456789TJQK"] + ["QsQd", "JcJd"])
BB = "AsAd,As2d"
GAME = {"config": {"starting_stack": 2, "max_raises": 0, "include_all_in": False},
        "runouts": ("2c3c4d7h8h", "Jc2h3h7s8c")}
OPTIONS = {"iterations": 12, "averaging_delay": 5, "algorithm": "cfrplus",
           "traversal": "public-batched", "diagnostics": "public-batched",
           "resource_model": "public-vector"}


class PreflopPrivateIndexIntegrationTests(unittest.TestCase):
    def assert_equivalent(self, original, compact):
        for field in ("strategy", "value_sb", "sb_best_response_value",
                      "bb_best_response_value", "nash_conv", "info_sets", "worlds",
                      "private_pair_probabilities", "reachable_runouts"):
            self.assertEqual(compact[field], original[field], field)
        self.assertEqual(compact["private_indexing_metadata"]["original_hand_dimensions"], [14, 2])
        self.assertEqual(compact["private_indexing_metadata"]["compact_hand_dimensions"], [2, 2])
        self.assertEqual(compact["private_indexing_metadata"]["original_active_indices"], [[12, 13], [0, 1]])
        compare_result(compact, replay_policy(compact, SB, BB, **GAME))

    def test_blocked_range_holes_and_selected_future_conditioning_preserve_policy(self):
        original = solver.solve_preflop(SB, BB, **GAME, **OPTIONS)
        compact = solver.solve_preflop(SB, BB, **GAME, **OPTIONS, private_indexing="compact")
        self.assert_equivalent(original, compact)
        priors = sorted(row["probability"] for row in compact["private_pair_probabilities"])
        self.assertEqual(priors, [1 / 6, 1 / 6, 1 / 3, 1 / 3])
        self.assertEqual(compact["vector_work_budget"]["hand_counts"], [2, 2])
        self.assertEqual(original["vector_work_budget"]["hand_counts"], [14, 2])

    def test_target_miss_retains_full_ceiling_and_exact_checkpoint_parity(self):
        options = dict(OPTIONS, iterations=15, target_nash_conv=1e-30,
                       convergence_check_interval=4)
        original = solver.solve_preflop(SB, BB, **GAME, **options)
        compact = solver.solve_preflop(SB, BB, **GAME, **options, private_indexing="compact")
        self.assert_equivalent(original, compact)
        self.assertEqual(compact["completed_iterations"], 15)
        self.assertFalse(compact["convergence_target_reached"])
        self.assertEqual(compact["convergence_checkpoints"], original["convergence_checkpoints"])
        self.assertEqual([row["completed_iterations"] for row in compact["convergence_checkpoints"]], [8, 12, 15])

    def test_reference_and_work_caps_reject_before_compact_copy_or_vector_view(self):
        for cap in ("MAX_COMPACTION_REFERENCE_SLOTS", "MAX_TOTAL_LOOP_ENTRIES"):
            with self.subTest(cap=cap), patch.object(budget, cap, 1), \
                    patch.object(solver, "compact_private_indices", side_effect=AssertionError("copy allocated")), \
                    patch.object(solver, "_positive_pot_training_view", side_effect=AssertionError("view allocated")):
                with self.assertRaises(ValueError):
                    solver.solve_preflop(SB, BB, **GAME, **OPTIONS, private_indexing="compact")

    def test_compact_owner_released_on_success_and_diagnostic_failure_without_gc(self):
        factory = solver.compact_private_indices
        for fail in (False, True):
            references = []
            def track(worlds, infos):
                result = factory(worlds, infos)
                references.append(weakref.ref(result))
                return result
            with self.subTest(fail=fail), patch.object(solver, "compact_private_indices", new=track), \
                    patch.object(gc, "collect", side_effect=AssertionError("forced collection")):
                if fail:
                    with patch.object(solver, "evaluate_public_profile", side_effect=RuntimeError("diagnostic failure")):
                        with self.assertRaisesRegex(RuntimeError, "diagnostic failure"):
                            solver.solve_preflop(SB, BB, **GAME, **OPTIONS, private_indexing="compact")
                else:
                    solver.solve_preflop(SB, BB, **GAME, **OPTIONS, private_indexing="compact")
            self.assertEqual(len(references), 1)
            self.assertIsNone(references[0]())


if __name__ == "__main__":
    unittest.main()
