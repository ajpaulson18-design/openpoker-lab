import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.flop_class_compact_budget import (
    KERNEL_LF_SHA256,
    LOGICAL_WORK_CAP,
    MAX_ITERATIONS,
    VERSION,
    admit_compact_request,
    validate_observed_dimensions,
)


ROOT = Path(__file__).resolve().parents[1]


class FlopClassCompactBudgetTests(unittest.TestCase):
    def test_boundary_forecasts_are_exact_fresh_and_separate_from_legacy_proxy(self):
        low = admit_compact_request(1)
        high = admit_compact_request(MAX_ITERATIONS)
        self.assertEqual(low["version"], VERSION)
        self.assertEqual(low["total_training_work"], low["logical_work_per_sweep"])
        self.assertEqual(high["total_training_work"], high["logical_work_per_sweep"] * MAX_ITERATIONS)
        self.assertEqual(high["total_admitted_work"],
                         high["total_training_work"] + high["fixed_setup_and_output_work"])
        self.assertLessEqual(high["total_admitted_work"], LOGICAL_WORK_CAP)
        self.assertEqual(high["total_training_work"], 75_046_160)
        self.assertEqual(high["fixed_setup_and_output_work"], 61_670)
        self.assertEqual(high["total_admitted_work"], 75_107_830)
        self.assertEqual(low["dimensions"]["private_information_action_slots"], 932)
        self.assertEqual(low["dimensions"]["public_action_edges"], 632)
        self.assertEqual(low["dimensions"]["tree_edges_including_chance"], 1000)
        self.assertFalse(high["legacy_physical_proxy_reference"]["old_caps_enforced_by_this_mode"])
        self.assertEqual(
            high["legacy_physical_proxy_reference"]["physical_world_iterations_informational_only"],
            5940 * 3 * MAX_ITERATIONS,
        )
        low["per_sweep"]["outer_world_loop_entries"] = -1
        self.assertEqual(admit_compact_request(1)["per_sweep"]["outer_world_loop_entries"], 378)

    def test_named_traversal_and_initialization_charges_are_included(self):
        forecast = admit_compact_request(2)
        sweep = forecast["per_sweep"]
        self.assertEqual(sweep["chance_child_callback_calls"], 3 * 126 * 33)
        self.assertEqual(sweep["action_and_deterministic_chance_child_recursions_upper_bound"], 3 * 2 * 126 * 33)
        self.assertEqual(sweep["delta_dictionary_action_slots_zeroed"], 932)
        self.assertEqual(sweep["terminal_contribution_reads"], 4 * 126 * 33)
        self.assertEqual(sweep["profile_information_rows"], 3 * 466)
        self.assertEqual(sweep["regret_clipping_action_slots"], 932)
        self.assertEqual(forecast["fixed_setup"]["regret_and_average_action_slots_initialized"], 1864)
        self.assertEqual(forecast["fixed_output_and_diagnostics"]["physical_policy_action_slots_lifted_and_diagnosed"], 33824)
        self.assertEqual(forecast["fixed_physical_preparation_reference"]["physical_worlds"], 5940)
        self.assertEqual(forecast["fixed_physical_preparation_reference"]["physical_public_states"], 30812)
        self.assertIn("not a total memory", forecast["interpretation"])

    def test_invalid_requests_reject_before_kernel_source_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            for invalid in (True, False, 0, -1, MAX_ITERATIONS + 1, 1.0, "1", None):
                with self.subTest(invalid=invalid):
                    with self.assertRaises(ValueError):
                        admit_compact_request(invalid, source_root=directory)

    def test_kernel_source_change_rejects_before_forecast(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in KERNEL_LF_SHA256:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            good = admit_compact_request(1, source_root=root)
            self.assertEqual(good["kernel_lf_sha256"], KERNEL_LF_SHA256)
            changed = root / "pokerlab" / "cfr_plus.py"
            changed.write_bytes(changed.read_bytes() + b"\n# mutation\n")
            with self.assertRaisesRegex(ValueError, "source changed"):
                admit_compact_request(1, source_root=root)

    def test_oversized_kernel_rejects_from_stat_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "pokerlab" / "cfr_plus.py"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
            read_bytes = Path.read_bytes

            def tracked_read(path):
                if path == target:
                    self.fail("oversized source must be rejected before read_bytes")
                return read_bytes(path)

            with patch.object(Path, "read_bytes", tracked_read):
                with self.assertRaisesRegex(ValueError, "source bound"):
                    admit_compact_request(1, source_root=root)

    def test_observed_dimensions_are_strict(self):
        census = {
            "compact_public_states": 1001, "compact_decisions": 316,
            "compact_chance_nodes": 58, "compact_terminals": 627,
            "compact_worlds": 126, "compact_policy_rows": 466,
            "compact_action_slots": 932, "physical_policy_rows": 16912,
            "physical_action_slots": 33824,
        }
        infos = {(player, f"h{index}", ()): 2
                 for index, player in enumerate([0] * 232 + [1] * 234)}
        self.assertEqual(len(infos), 466)
        self.assertTrue(validate_observed_dimensions(census, 33, infos))
        for path_states in (0, 34, True, 33.0):
            with self.subTest(path_states=path_states), self.assertRaises(ValueError):
                validate_observed_dimensions(census, path_states, infos)
        wrong = dict(census, compact_action_slots=True)
        with self.assertRaises(ValueError):
            validate_observed_dimensions(wrong, 33, infos)
        with self.assertRaises(ValueError):
            validate_observed_dimensions(census, 33, {**infos, (0, "extra", ()): 2})
        all_one_player = {(0, f"h{index}", ()): 2 for index in range(466)}
        with self.assertRaisesRegex(ValueError, "per-player"):
            validate_observed_dimensions(census, 33, all_one_player)


if __name__ == "__main__":
    unittest.main()
