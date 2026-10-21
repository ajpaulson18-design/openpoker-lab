"""Fault tests for the fixed T6000 publication boundary; no trainer calls."""
from __future__ import annotations

import subprocess
import shutil
import unittest
import uuid
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import benchmark_turn_class_tail as experiment
from scripts import turn_three_hand_reference as reference


@contextmanager
def scratch_directory():
    base = Path(reference.__file__).resolve().parents[1] / "work"
    base.mkdir(parents=True, exist_ok=True)
    root = base / ("turn-class-producer-test-" + uuid.uuid4().hex)
    root.mkdir(exist_ok=False)
    try:
        yield str(root)
    finally:
        resolved = root.resolve()
        if resolved.parent != base.resolve() or not resolved.name.startswith("turn-class-producer-test-"):
            raise ValueError("Unsafe scratch cleanup target")
        shutil.rmtree(resolved)


class CanonicalAndAdmissionTests(unittest.TestCase):
    def test_jsonable_preserves_tuple_dictionary_keys_as_entries(self):
        value = {("oop", "AsAh", ("check",)): Fraction(3, 7)}
        result = experiment.jsonable(value)
        self.assertEqual(list(result), ["key_value_entries"])
        self.assertEqual(
            result["key_value_entries"][0]["key"],
            ["oop", "AsAh", ["check"]],
        )
        self.assertEqual(result["key_value_entries"][0]["value"], "3/7")
        self.assertTrue(experiment.canonical(value).endswith(b"\n"))

    def test_nonfinite_json_value_is_rejected(self):
        with self.assertRaises(ValueError):
            experiment.canonical({"bad": float("nan")})

    def test_schedule_and_resource_model_are_fixed_before_audit(self):
        payload = {
            "resource_model": experiment.RESOURCE_MODEL,
            "algorithm": "cfrplus",
            "iterations": experiment.ITERATIONS,
            "requested_iterations": experiment.ITERATIONS,
            "discard": experiment.DISCARD,
            "averaged_sweeps": experiment.AVERAGED_SWEEPS,
            "average_weight_sum": experiment.AVERAGE_WEIGHT_SUM,
            "requested_regret_passes": experiment.REGRET_PASSES,
            "requested_average_passes": experiment.AVERAGE_PASSES,
            "requested_total_traversal_passes": experiment.TOTAL_PASSES,
            "strategy": [{} for _ in range(3606)],
            "resource_usage": {
                "physical_world_iterations": 2376000,
                "candidate_pair_iterations": 54000,
                "compact_world_proxy": 25920000,
                "compact_dense_proxy": 3 * 456 * (3 * experiment.ITERATIONS + 3),
                "trainer_vector_work": 450960288,
                "complete_vector_work": 452960288,
            },
        }
        for name in experiment.METRICS:
            payload[name] = 0.0
        experiment._validate_payload(payload)
        payload["resource_usage"]["trainer_vector_work"] -= 1
        with self.assertRaisesRegex(ValueError, "Resource admission"):
            experiment._validate_payload(payload)

    def test_exclusive_write_never_replaces_existing_bytes(self):
        with scratch_directory() as directory:
            path = Path(directory) / "already-owned.json"
            path.write_bytes(b"prior")
            with self.assertRaises(FileExistsError):
                experiment._exclusive_write(path, b"replacement")
            self.assertEqual(path.read_bytes(), b"prior")

    def test_run_claim_survives_and_blocks_any_second_attempt(self):
        with scratch_directory() as directory:
            root = Path(directory)
            attempt = experiment._claim_run(root, "a" * 40, {"source.py": "b" * 64})
            self.assertTrue((root / experiment.ATTEMPT_ROOT / experiment.CLAIM_NAME).is_file())
            self.assertTrue(attempt.is_dir())
            with self.assertRaisesRegex(FileExistsError, "prior T6000 claim"):
                experiment._refuse_prior_run(root)

    def test_git_warning_stderr_does_not_pollute_status_stdout(self):
        result = SimpleNamespace(returncode=0, stdout=b"", stderr=b"warning: inaccessible ignored temp\n")
        with patch.object(experiment.subprocess, "run", return_value=result):
            self.assertEqual(experiment._git(Path("."), "status", "--porcelain"), "")

    def test_git_status_failure_remains_an_error(self):
        result = SimpleNamespace(returncode=128, stdout=b"", stderr=b"fatal: not a repository")
        with patch.object(experiment.subprocess, "run", return_value=result):
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                experiment._git(Path("."), "status", "--porcelain")
        self.assertEqual(caught.exception.stderr, b"fatal: not a repository")

    def test_failure_retains_raw_return_when_first_retention_did_not_finish(self):
        with scratch_directory() as directory:
            attempt = Path(directory)
            raw = b'{"untouched": true}\n'
            experiment._save_failure(attempt, "a" * 40, {}, "retention",
                                     {"untouched": True}, raw, 1.0,
                                     OSError("initial retention failed"))
            self.assertEqual((attempt / "returned-policy.json").read_bytes(), raw)
            self.assertTrue((attempt / "failure-receipt.json").is_file())


class PublicationBoundaryTests(unittest.TestCase):
    def test_generation_refuses_existing_output_before_freeze_or_solver(self):
        with scratch_directory() as directory:
            root = Path(directory)
            policy = experiment.targets(root)["policy"]
            policy.parent.mkdir(parents=True)
            policy.write_bytes(b"immutable policy")
            with patch.object(experiment, "_freeze", side_effect=AssertionError("freeze must not run")):
                with self.assertRaises(FileExistsError):
                    experiment.generate(root)
            self.assertEqual(policy.read_bytes(), b"immutable policy")

    def test_final_verifier_failure_removes_only_new_bundle_files(self):
        with scratch_directory() as directory:
            root = Path(directory)
            fixed = experiment.targets(root)
            fixed["report"].parent.mkdir(parents=True)
            unrelated = root / "unrelated.txt"
            unrelated.write_bytes(b"keep")
            calls = []

            def verify_saved_artifact(*, path, root=None):
                calls.append(Path(path))
                if len(calls) == 2:
                    raise ValueError("independent final check rejected staged bundle")

            checker = type(
                "Checker",
                (),
                {"verify_saved_artifact": staticmethod(verify_saved_artifact)},
            )
            with patch.dict("sys.modules", {"scripts.verify_turn_class_tail_experiment": checker()}), \
                 patch.object(experiment, "_guard", return_value=None):
                with self.assertRaisesRegex(ValueError, "final check rejected"):
                    experiment._publish(root, b"{}\n", b"{}\n", "a" * 40, (), {})
            self.assertEqual(len(calls), 2)
            self.assertFalse(fixed["report"].exists())
            self.assertFalse(fixed["policy"].exists())
            self.assertEqual(unrelated.read_bytes(), b"keep")

    def test_atomic_promotion_refuses_a_report_created_at_the_race_boundary(self):
        with scratch_directory() as directory:
            root = Path(directory)
            fixed = experiment.targets(root)
            fixed["report"].parent.mkdir(parents=True)
            checker = type(
                "Checker",
                (),
                {"verify_saved_artifact": staticmethod(lambda *, path, root=None: None)},
            )

            def race_create_report(stage, destination):
                Path(destination).write_bytes(b"concurrent report")
                raise FileExistsError(destination)

            with patch.dict("sys.modules", {"scripts.verify_turn_class_tail_experiment": checker()}), \
                 patch.object(experiment, "_guard", return_value=None), \
                 patch.object(experiment.os, "link", side_effect=race_create_report):
                with self.assertRaises(FileExistsError):
                    experiment._publish(root, b"report", b"policy", "c" * 40, (), {})
            self.assertEqual(fixed["report"].read_bytes(), b"concurrent report")
            self.assertFalse(fixed["policy"].exists())

    def test_existing_immutable_policy_blocks_publication(self):
        with scratch_directory() as directory:
            root = Path(directory)
            fixed = experiment.targets(root)
            fixed["policy"].parent.mkdir(parents=True)
            fixed["policy"].write_bytes(b"frozen policy")
            with self.assertRaises(FileExistsError):
                experiment._publish(root, b"report", b"new policy", "b" * 40, (), {})
            self.assertEqual(fixed["policy"].read_bytes(), b"frozen policy")
            self.assertFalse(fixed["report"].exists())

    def test_t750_pins_are_literal(self):
        self.assertEqual(
            experiment.OLD_REPORT_SHA256,
            "1827e2163b897c5a1c5274e4a300ee365d8234fdf38235647772d63300953a7a",
        )
        self.assertEqual(
            experiment.OLD_POLICY_SHA256,
            "c02e37dedf886f586e8b0ce9a98e86d079a32322d6e2ba4eb5beaab127dd6789",
        )
        self.assertNotEqual(experiment.OLD_REPORT_SHA256, experiment.OLD_POLICY_SHA256)

    def test_source_guard_detects_working_byte_drift(self):
        names = ("fixture.py",)
        with patch.object(experiment, "_git", side_effect=["a" * 40, ""]), \
             patch.object(experiment, "_source_names", return_value=names), \
             patch.object(experiment, "_source_bytes", return_value=b"new"), \
             patch.object(experiment, "_committed", return_value=None):
            with self.assertRaisesRegex(ValueError, "Frozen source bytes changed"):
                experiment._guard(Path("."), "a" * 40, names, {"fixture.py": "0" * 64})

    def test_oversized_artifact_is_rejected_from_stat_before_open(self):
        with scratch_directory() as directory:
            path = Path(directory) / "oversized.json"
            path.write_bytes(b"x" * (experiment.BYTE_CAP + 1))
            with patch.object(Path, "open", side_effect=AssertionError("must not read")):
                with self.assertRaisesRegex(ValueError, "byte cap"):
                    experiment._read_bounded(path)

    def test_exact_positive_gap_is_recorded_as_a_threshold_miss(self):
        exact = {
            "value_oop": Fraction(10),
            "value_ip": Fraction(-10),
            "oop_best_response_value": Fraction(11),
            "ip_best_response_value": Fraction(-9),
            "oop_best_response_gain": Fraction(1),
            "ip_best_response_gain": Fraction(1),
            "nash_conv": Fraction(2),
            "exploitability": Fraction(1),
        }
        audit = {"full_physical_exact_metrics": exact}
        old_baseline = {
            "exact_metrics_fractions": {name: str(value) for name, value in exact.items()}
        }
        report = experiment._build_report(
            "a" * 40,
            {"source.py": "0" * 64},
            {},
            audit,
            {name: float(value) for name, value in exact.items()},
            {name: 0.0 for name in experiment.METRICS},
            old_baseline,
            b"{}\n",
            1.25,
            3.5,
        )
        self.assertFalse(report["target_met"])
        self.assertTrue(report["threshold_miss"])
        self.assertEqual(report["exact_metrics_fractions"]["nash_conv"], "2")
        self.assertEqual(report["verification_scope"], experiment.VERIFICATION_SCOPE)


if __name__ == "__main__":
    unittest.main()
