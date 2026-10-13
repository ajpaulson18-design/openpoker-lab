"""Additional public-output and convergence coverage after the measurement freeze."""
import unittest
from unittest.mock import patch
from pokerlab.preflop_streamed_worlds import estimate_streamed_construction, StreamedPhysicalWorlds
from pokerlab import preflop_solver as solver
from scripts.preflop_validation import compare_result, replay_policy
from tests.test_preflop_streamed_worlds import SOLVE_OPTIONS, SB, BB, _strip_streaming_only_fields


class StreamedOutputAndConvergenceTests(unittest.TestCase):
    def test_sparse_valid_worlds_charge_all_packed_blocker_scan_bytes(self):
        budget = estimate_streamed_construction(100, 300_000, 100)
        self.assertEqual(budget["blocker_scan_passes"], 4)
        self.assertEqual(budget["blocker_scan_byte_visits_upper_bound"], 15_000_000)
        self.assertEqual(budget["blocker_scan_loop_entries_upper_bound"], 60_000_000)
        self.assertEqual(budget["additional_loop_entries_upper_bound"], 62_405_728)
        # The independent 30M candidate-pair/runout preflight can admit this
        # sparse shape; a lower work ceiling must reject before index access.
        with patch("pokerlab.preflop_streamed_worlds.MAX_TOTAL_LOOP_ENTRIES", 50_000_000):
            with self.assertRaisesRegex(ValueError, "before scans"):
                StreamedPhysicalWorlds(None, None, [None] * 300_000, None,
                                       [None] * 100, 100, None)

    def test_entirely_blocked_selected_outcome_stays_unreachable(self):
        sb, bb = "AsAd:1,AsAh:0.5", "KsKd:1,KcKh:0.5"
        options = dict(SOLVE_OPTIONS)
        options.pop("world_admission")  # Also exercise unchanged default world*T admission.
        options["runouts"] = ("As2c3c4c5c", "2d3d4d5h6s", "2d3d4d6s5h")
        old = solver.solve_preflop(sb, bb, **options)
        new = solver.solve_preflop(sb, bb, **options, world_storage="streamed-flop-sign")
        self.assertEqual(_strip_streaming_only_fields(new), old)
        self.assertEqual(len(new["selected_runouts"]), 3)
        self.assertEqual(len(new["reachable_runouts"]), 2)
        self.assertTrue(any("As" in r for r in new["selected_runouts"]))
        self.assertFalse(any("As" in r for r in new["reachable_runouts"]))
        self.assertEqual(new["worlds"], 8)
        self.assertEqual(new["limits"]["world_iterations"], solver._MAX_WORLD_ITERATIONS)
        replay_options = {key: options[key] for key in ("config", "runouts", "flop_config", "postflop_scope")}
        compare_result(new, replay_policy(new, sb, bb, **replay_options))

    def test_convergence_preserves_full_requested_admission_and_exact_policy(self):
        options = {**SOLVE_OPTIONS, "iterations": 30, "averaging_delay": 5,
                   "target_nash_conv": 10.0, "convergence_check_interval": 7}
        old = solver.solve_preflop(SB, BB, **options)
        new = solver.solve_preflop(SB, BB, **options, world_storage="streamed-flop-sign")
        self.assertEqual(_strip_streaming_only_fields(new), old)
        self.assertEqual(new["iterations"], 30)
        self.assertEqual(new["completed_iterations"], 7)
        self.assertEqual(new["vector_work_budget"]["iterations"], 30)
        self.assertEqual(new["vector_work_budget"]["checkpoint_count_upper_bound"], 5)
        self.assertGreater(new["vector_work_budget"]["total_loop_entries_upper_bound"],
                           old["vector_work_budget"]["total_loop_entries_upper_bound"])
        replay_options = {key: options[key] for key in ("config", "runouts", "flop_config", "postflop_scope")}
        compare_result(new, replay_policy(new, SB, BB, **replay_options))


if __name__ == "__main__":
    unittest.main()
