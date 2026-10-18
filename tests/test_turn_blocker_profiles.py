"""Adversarial checks for saved blocker CFR+ profile proofs."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from fractions import Fraction as F
from unittest.mock import Mock, patch

from scripts import turn_blocker_profiles as profiles

ROOT = Path(__file__).resolve().parents[1]


class TurnBlockerProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A valid full saved proof is established before mutation tests.
        cls.report = profiles.verify_profiles()

    def run_report(self, report):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "mutated-report.json"
            path.write_bytes(profiles.canonical(report))
            return profiles.verify_profiles(path)

    def reject(self, edit):
        candidate = copy.deepcopy(self.report)
        edit(candidate)
        with self.assertRaises((ValueError, RuntimeError, KeyError, TypeError, IndexError)):
            self.run_report(candidate)

    def test_positive_saved_grid_metrics_bounds_and_normalization(self):
        self.assertEqual({(row["backend"], row["iterations_requested"])
                          for row in self.report["results"]}, set(profiles.GRID))
        self.assertEqual(len(self.report["results"]), 6)
        self.assertEqual(self.report["known_game_value_fraction"], "115/7")
        for row in self.report["results"]:
            self.assertEqual(row["worlds"], 6)
            self.assertEqual(row["information_sets"], 56)
            self.assertEqual(row["compatible_pairs"], 3)
            self.assertEqual(row["policy_rows"], 56)
            self.assertEqual(row["total_public_nodes"], 63)
            self.assertEqual(row["public_decision_nodes"], 28)
            self.assertEqual(row["known_game_value_fraction"], "115/7")
            self.assertEqual(len(row["exact"]["normalization_ledger"]), 56)
            self.assertLessEqual(F(row["exact"]["lower_value_bound"]), F(115, 7))
            self.assertGreaterEqual(F(row["exact"]["upper_value_bound"]), F(115, 7))
            self.assertEqual(row["target_met"],
                             F(row["exact"]["metrics"]["nash_conv"]) <= profiles.TARGET)

    def test_historical_extra_training_hash_is_well_formed_but_not_a_pin(self):
        candidate = copy.deepcopy(self.report)
        candidate["source_sha256"]["pokerlab/cfr.py"] = "0" * 64
        self.run_report(candidate)

    def test_saved_verifier_never_trains(self):
        with patch.object(profiles, "solve_materialized", side_effect=AssertionError("verification trained")), \
             patch.object(profiles, "solve_matrix_free_turn", side_effect=AssertionError("verification trained")):
            self.run_report(self.report)

    def test_wrong_grid_and_duplicate_profile(self):
        self.reject(lambda report: report["results"].pop())
        self.reject(lambda report: report["results"].__setitem__(
            1, copy.deepcopy(report["results"][0])))
        self.reject(lambda report: report["results"][0].update(iterations_requested=True))

    def test_missing_policy_file(self):
        target = profiles.ROOT / self.report["results"][0]["policy_file"]
        original = profiles.read_bounded
        def missing(path, cap):
            if Path(path) == target:
                raise FileNotFoundError(target)
            return original(path, cap)
        with patch.object(profiles, "read_bounded", side_effect=missing):
            with self.assertRaises(FileNotFoundError):
                profiles.verify_profiles()

    def test_source_pin_and_threshold_mutations(self):
        self.reject(lambda report: report["source_sha256"].pop(
            "scripts/turn_blocker_sequence_fixture.py"))
        self.reject(lambda report: report["source_sha256"].update(
            {"scripts/turn_rational_certificate.py": "0" * 64}))
        self.reject(lambda report: report.update(target_nash_conv_fraction="1/100"))
        def invert_threshold_flags(report):
            row = report["results"][0]
            row["target_met"] = not row["target_met"]
            row["threshold_miss"] = not row["threshold_miss"]
        self.reject(invert_threshold_flags)

    def test_normalization_ledger_and_policy_identity_mutations(self):
        self.reject(lambda report: report["results"][0]["exact"][
            "normalization_ledger"][0].update(input_row_sum_fraction="999"))
        self.reject(lambda report: report["results"][0].update(
            policy_identity_sha256="0" * 64))

    def test_false_zero_exact_metrics_are_rejected(self):
        def edit(report):
            row = report["results"][0]
            row["exact"]["metrics"] = {name: "0" for name in row["exact"]["metrics"]}
        self.reject(edit)

    def test_report_and_policy_file_admission(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            oversized = Path(directory) / "oversized.json"
            oversized.write_bytes(b"{" + b" " * profiles.MAX_REPORT_BYTES)
            with self.assertRaisesRegex(ValueError, "file admission"):
                profiles.read_bounded(oversized, profiles.MAX_REPORT_BYTES)
            oversized.write_bytes(b"{" + b" " * profiles.MAX_POLICY_BYTES)
            with self.assertRaisesRegex(ValueError, "file admission"):
                profiles.read_bounded(oversized, profiles.MAX_POLICY_BYTES)

    def test_head_and_source_drift_during_saved_replay(self):
        with patch.object(profiles, "head", side_effect=["a" * 40, "b" * 40]):
            with self.assertRaisesRegex(RuntimeError, "HEAD changed"):
                profiles.verify_profiles()
        original_inputs, calls = profiles.inputs, []
        def drifting_inputs():
            current = original_inputs()
            calls.append(None)
            if len(calls) > 1:
                current["scripts/turn_rational_certificate.py"] = "0" * 64
            return current
        with patch.object(profiles, "inputs", side_effect=drifting_inputs):
            with self.assertRaisesRegex(RuntimeError, "source or witness changed"):
                profiles.verify_profiles()

    def test_policy_input_drift_during_replay(self):
        target = profiles.ROOT / self.report["results"][0]["policy_file"]
        original, calls = profiles.read_bounded, []
        def changing(path, cap):
            raw = original(path, cap)
            if Path(path) == target:
                calls.append(None)
                if len(calls) > 1:
                    return raw + b" "
            return raw
        with patch.object(profiles, "read_bounded", side_effect=changing):
            with self.assertRaisesRegex(RuntimeError, "changed during verification"):
                profiles.verify_profiles()

    def test_generation_failure_restores_report_and_removes_only_new_policies(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            folder = Path(directory)
            report_path = folder / "accepted-report.json"
            prior = b"previously-accepted-report\n"
            report_path.write_bytes(prior)
            policy_dir = folder / "policies"
            policy_dir.mkdir()
            cached = {"cached_saved_policy": True}
            cached_bytes = profiles.canonical(cached)
            preexisting = policy_dir / "turn-blocker-materialized-1000.json"
            preexisting.write_bytes(cached_bytes)
            cached_solver_calls = Mock(return_value=cached)
            verification_mock = Mock(side_effect=[None, ValueError("post-publication rejection")])
            with patch.multiple(
                    profiles,
                    REPORT=report_path,
                    POLICY_DIR=policy_dir,
                    inputs=lambda: {"frozen": "a" * 64},
                    head=lambda: "b" * 40,
                    model=lambda: ((), object(), (), object()),
                    solve_materialized=cached_solver_calls,
                    solve_matrix_free_turn=cached_solver_calls,
                    recompute=lambda backend, iterations, *args: {
                        "backend": backend, "iterations_requested": iterations,
                        "policy_file": "unused",
                        "exact": {"metrics": {"nash_conv": "1/2"}},
                        "target_met": False, "threshold_miss": True,
                    },
                    verify_profiles=verification_mock,
                    ):
                with patch.object(profiles.witness_verifier, "verify_saved_artifact",
                                  return_value={"results": [{"exact": {"metrics": {"value_oop": "115/7"}}}]}):
                    with self.assertRaisesRegex(ValueError, "post-publication rejection"):
                        profiles.generate()
            self.assertEqual(cached_solver_calls.call_count, 6)
            self.assertEqual(report_path.read_bytes(), prior)
            self.assertEqual(preexisting.read_bytes(), cached_bytes)
            self.assertEqual(sorted(path.name for path in policy_dir.iterdir()),
                             [preexisting.name])
            self.assertEqual(verification_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
