"""Cheap safeguards for the fixed direct-tail report producer/verifier."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]

from fractions import Fraction
from pokerlab.river_config import RiverConfig
from pokerlab.turn_tail_adapter import solve_turn_tail
from scripts import full_deck_raised_reference as reference
from scripts import benchmark_turn_direct_tail as runner


class DirectTailRunnerTests(unittest.TestCase):
    def test_real_pinned_input_container_passes_source_and_input_guard(self):
        inputs, old_tail = runner._load_old_tail(ROOT)
        fingerprints = runner._fingerprints(ROOT, runner._verification_paths())
        self.assertEqual(len(inputs["accepted"]), 8)
        self.assertEqual(len(old_tail["strategy"]), 2404)
        runner._guard(ROOT, fingerprints, fingerprints, runner._head(ROOT), inputs)

    def test_actual_full_deck_ten_sweep_adapter_metadata_and_required_resource_keys(self):
        fixture = reference.FIXTURE
        policy = solve_turn_tail(
            fixture["board"], fixture["oop"], fixture["ip"],
            RiverConfig.from_dict(fixture["config"]), iterations=10, discard=8)
        self.assertEqual(policy["worlds"], 176)
        self.assertEqual(policy["resource_usage"]["full_requested_world_node_work"], 168960)
        runner._check_metadata(policy, reference.model(), total=10, discard=8)
        malformed = deepcopy(policy)
        del malformed["resource_usage"]["full_requested_dense_hand_state_pass_work"]
        with self.assertRaisesRegex(ValueError, "resource usage key set"):
            runner._check_metadata(malformed, reference.model(), total=10, discard=8)
        malformed = deepcopy(policy)
        malformed["compatible_pairs"] = True
        with self.assertRaisesRegex(ValueError, "metadata type differs: compatible_pairs"):
            runner._check_metadata(malformed, reference.model(), total=10, discard=8)
        malformed = deepcopy(policy)
        malformed["public_node_limit"] = True
        with self.assertRaisesRegex(ValueError, "metadata type differs: public_node_limit"):
            runner._check_metadata(malformed, reference.model(), total=10, discard=8)

    def test_quotient_certificate_json_and_exact_metric_agreement(self):
        names = runner.METRICS
        metrics = {name: Fraction(index, index + 2)
                   for index, name in enumerate(names, start=1)}
        certificate = {"metrics": dict(metrics), "proof_fraction": Fraction(7, 13)}
        converted = runner._check_exact_certificate(metrics, certificate)
        self.assertEqual(converted["proof_fraction"], "7/13")
        self.assertEqual(converted["metrics"][names[0]], str(metrics[names[0]]))
        self.assertIn(b'"proof_fraction": "7/13"', runner._canonical(converted))
        disagree = deepcopy(certificate)
        disagree["metrics"][names[0]] += Fraction(1, 1000)
        with self.assertRaisesRegex(ValueError, "certificates disagree"):
            runner._check_exact_certificate(metrics, disagree)

    def test_historical_source_context_is_shape_checked_without_git_object_lookup(self):
        required = {"pokerlab/turn_tail_adapter.py", "tests/test_turn_tail_adapter.py",
                    "tests/test_benchmark_turn_direct_tail.py",
                    "scripts/benchmark_turn_direct_tail.py"}
        saved = {"pokerlab/turn_tail_adapter.py": "a" * 64,
                 "pokerlab/public_cfr.py": "b" * 64,
                 "tests/test_turn_tail_adapter.py": "c" * 64,
                 "tests/test_benchmark_turn_direct_tail.py": "e" * 64,
                 "scripts/benchmark_turn_direct_tail.py": "d" * 64}
        with patch.object(runner.subprocess, "check_output",
                          side_effect=AssertionError("must not require historical Git object")):
            runner._historical_map(saved, required)
        bad = dict(saved)
        bad["../outside.py"] = "e" * 64
        with self.assertRaisesRegex(ValueError, "Unexpected historical producer path"):
            runner._historical_map(bad, required)
        bad = dict(saved)
        bad["pokerlab/nested/source.py"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "Unexpected historical producer path"):
            runner._historical_map(bad, required)

    def test_saved_call_timing_must_be_finite_nonnegative_and_not_bool(self):
        for value in (None, True, -1.0, float("inf"), float("nan")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "finite and nonnegative"):
                    runner._validate_elapsed(value)
        runner._validate_elapsed(0)
        runner._validate_elapsed(1.25)

    def _scratch_bundle(self):
        directory = ROOT / ".test_tmp" / ("direct-tail-publish-" + uuid.uuid4().hex)
        directory.parent.mkdir(exist_ok=True)
        directory.mkdir()
        results = directory / "results"
        results.mkdir()
        return directory, results

    def _cleanup_bundle(self, directory, results, report, policy, foreign):
        for path in (report, policy, foreign,
                     results / ("." + policy.name + ".unit.stage"),
                     results / ("." + report.name + ".unit.stage")):
            if path.exists():
                path.unlink()
        results.rmdir()
        directory.rmdir()

    def test_write_failure_cleans_registered_stage_and_preserves_foreign_file(self):
        directory, results = self._scratch_bundle()
        try:
            report = results / "accepted-report.json"
            policy = results / "accepted-policy.json"
            foreign = results / "foreign.txt"
            foreign.write_bytes(b"leave me")
            original_fsync = runner.os.fsync
            count = 0

            def fail_second_fsync(fd):
                nonlocal count
                count += 1
                if count == 2:
                    raise OSError("injected stage write failure")
                return original_fsync(fd)

            with (patch.object(runner, "RESULTS", results),
                  patch.object(runner, "REPORT", report),
                  patch.object(runner, "POLICY", policy),
                  patch.object(runner.uuid, "uuid4", return_value=SimpleNamespace(hex="unit")),
                  patch.object(runner, "_guard"),
                  patch.object(runner.os, "fsync", side_effect=fail_second_fsync)):
                with self.assertRaisesRegex(OSError, "injected stage write failure"):
                    runner._publish(b'{"policy":true}\n', b'{"report":true}\n',
                                    directory, {}, {}, "0" * 40, {"accepted": {}}, {})
            self.assertFalse(report.exists())
            self.assertFalse(policy.exists())
            self.assertEqual(foreign.read_bytes(), b"leave me")
            self.assertEqual(list(results.glob("*.stage")), [])
            self.assertEqual(list(results.glob(".*.stage")), [])
        finally:
            self._cleanup_bundle(directory, results, report, policy, foreign)

    def test_final_published_bundle_byte_guard_rolls_back_only_owned_files(self):
        directory, results = self._scratch_bundle()
        try:
            report = results / "accepted-report.json"
            policy = results / "accepted-policy.json"
            foreign = results / "foreign.txt"
            foreign.write_bytes(b"preserve")
            guard_calls = 0

            def mutate_after_final_source_guard(*_args, **_kwargs):
                nonlocal guard_calls
                guard_calls += 1
                if guard_calls == 2:
                    policy.write_bytes(b"tampered\n")

            def replay_guard(_report, _policy, *, bundle_guard, **_kwargs):
                bundle_guard()

            with (patch.object(runner, "RESULTS", results),
                  patch.object(runner, "REPORT", report),
                  patch.object(runner, "POLICY", policy),
                  patch.object(runner.uuid, "uuid4", return_value=SimpleNamespace(hex="unit")),
                  patch.object(runner, "_guard", side_effect=mutate_after_final_source_guard),
                  patch.object(runner, "_verify_payload", side_effect=replay_guard)):
                with self.assertRaisesRegex(ValueError, "Published bundle changed"):
                    runner._publish(b'{"policy":true}\n', b'{"report":true}\n',
                                    directory, {}, {}, "0" * 40, {"accepted": {}}, {})
            self.assertFalse(report.exists())
            self.assertFalse(policy.exists())
            self.assertEqual(foreign.read_bytes(), b"preserve")
            self.assertEqual(list(results.glob(".*.stage")), [])
        finally:
            self._cleanup_bundle(directory, results, report, policy, foreign)

    def test_late_foreign_inode_replacement_survives_owned_rollback(self):
        directory, results = self._scratch_bundle()
        report = results / "accepted-report.json"
        policy = results / "accepted-policy.json"
        foreign = results / "foreign.txt"
        foreign.write_bytes(b"preserve unrelated")
        guard_calls = 0

        def replace_owned_report_after_final_source_guard(*_args, **_kwargs):
            nonlocal guard_calls
            guard_calls += 1
            if guard_calls == 2:
                report.unlink()
                report.write_bytes(b"foreign replacement")

        def replay_guard(_report, _policy, *, bundle_guard, **_kwargs):
            bundle_guard()

        try:
            with (patch.object(runner, "RESULTS", results),
                  patch.object(runner, "REPORT", report),
                  patch.object(runner, "POLICY", policy),
                  patch.object(runner.uuid, "uuid4", return_value=SimpleNamespace(hex="unit")),
                  patch.object(runner, "_guard", side_effect=replace_owned_report_after_final_source_guard),
                  patch.object(runner, "_verify_payload", side_effect=replay_guard)):
                with self.assertRaisesRegex(ValueError, "Published bundle changed"):
                    runner._publish(b'{"policy":true}\n', b'{"report":true}\n',
                                    directory, {}, {}, "0" * 40, {"accepted": {}}, {})
            self.assertEqual(report.read_bytes(), b"foreign replacement")
            self.assertFalse(policy.exists())
            self.assertEqual(foreign.read_bytes(), b"preserve unrelated")
        finally:
            self._cleanup_bundle(directory, results, report, policy, foreign)

    def test_readonly_final_source_guard_cannot_hide_late_bundle_mutation(self):
        directory, results = self._scratch_bundle()
        report = results / "accepted-report.json"
        policy = results / "accepted-policy.json"
        foreign = results / "foreign.txt"
        report.write_bytes(b'{"report":true}\n')
        policy.write_bytes(b'{"policy":true}\n')

        def mutate_after_final_source_guard(*_args, **_kwargs):
            policy.write_bytes(b"late mutation\n")

        try:
            with (patch.object(runner, "ROOT", directory),
                  patch.object(runner, "REPORT", report),
                  patch.object(runner, "POLICY", policy),
                  patch.object(runner, "_head", return_value="0" * 40),
                  patch.object(runner, "_fingerprints", return_value={}),
                  patch.object(runner, "_require_committed"),
                  patch.object(runner, "_load_old_tail", return_value=({}, {})),
                  patch.object(runner, "_verify_payload", return_value={}),
                  patch.object(runner, "_guard", side_effect=mutate_after_final_source_guard)):
                with self.assertRaisesRegex(ValueError, "changed during replay"):
                    runner.verify_bundle()
            self.assertTrue(report.exists())
            self.assertEqual(policy.read_bytes(), b"late mutation\n")
        finally:
            self._cleanup_bundle(directory, results, report, policy, foreign)


if __name__ == "__main__":
    unittest.main()
