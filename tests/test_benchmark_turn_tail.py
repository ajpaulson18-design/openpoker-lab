"""Cheap safety tests for the draft fixed-grid turn-tail runner."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from fractions import Fraction
from unittest.mock import patch

from scripts.historical_turn_sources import TRANSITIONS
from scripts import benchmark_turn_tail as runner
from scripts.benchmark_turn_river_independent import solve

LOCAL_TEMP_ROOT = Path(__file__).resolve().parents[1] / ".test_tmp"
LOCAL_TEMP_ROOT.mkdir(exist_ok=True)


def local_temp():
    return tempfile.TemporaryDirectory(dir=LOCAL_TEMP_ROOT)


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


class TurnTailRunnerSafetyTests(unittest.TestCase):
    def test_default_generation_cannot_start_a_long_solve(self):
        with patch.object(runner, "_baseline_pins", side_effect=AssertionError("read")), \
                self.assertRaisesRegex(ValueError, "disabled"):
            runner.generate()

    def test_existing_report_is_verified_without_any_capture(self):
        with local_temp() as temp:
            report = Path(temp) / "accepted.json"
            report.write_bytes(b"immutable")
            with patch.object(runner, "_verify_saved", return_value={"training_calls": 0}) as verify, \
                    patch.object(runner, "capture", side_effect=AssertionError("trainer")):
                result = runner.generate(report, Path(temp) / "policies", allow_training=True)
            self.assertEqual(result, {"training_calls": 0})
            verify.assert_called_once()

    def test_capped_reader_checks_size_before_reading(self):
        with local_temp() as temp:
            path = Path(temp) / "large.json"
            path.write_bytes(b"0123456789")
            with patch.object(Path, "read_bytes", side_effect=AssertionError("read")):
                with self.assertRaisesRegex(ValueError, "byte cap"):
                    runner._read_capped(path, 9, "test file")

    def test_baseline_pin_requires_all_six_canonical_policy_bytes(self):
        with local_temp() as temp:
            root = Path(temp)
            policies = root / "policies"
            policies.mkdir()
            rows = []
            for backend in runner.BACKENDS:
                for iteration in (100, 1000, 1500):
                    filename = f"full-deck-raised-turn-v1-{backend}-{iteration}.json"
                    payload = canonical({"backend": backend, "iterations": iteration})
                    (policies / filename).write_bytes(payload)
                    rows.append({"backend": backend,
                                 "iterations_requested": iteration,
                                 "policy_file": filename,
                                 "policy_sha256": hashlib.sha256(payload).hexdigest()})
            report = root / "baseline.json"
            report.write_bytes(canonical({
                "benchmark_id": "full-deck-raised-turn-benchmark-v1", "results": rows
            }))
            with patch.object(runner, "BASELINE_REPORT", report), \
                    patch.object(runner, "BASELINE_REPORT_SHA256",
                                 hashlib.sha256(report.read_bytes()).hexdigest()), \
                    patch.object(runner, "BASELINE_POLICIES", policies):
                pins = runner._baseline_pins()
                self.assertEqual(len(pins["policies"]), 6)
                self.assertEqual(pins["report_sha256"],
                                 hashlib.sha256(report.read_bytes()).hexdigest())
                victim = policies / runner.REQUIRED_BASELINE_POLICIES[0]
                victim.write_bytes(b"tampered")
                with self.assertRaisesRegex(ValueError, "hash differs"):
                    runner._baseline_pins()

    def test_report_generation_head_is_historical_and_source_pins_are_strict(self):
        baseline = {"report_sha256": "b" * 64}
        current_pins = {name: TRANSITIONS[name][1] if name in TRANSITIONS else "d" * 64
                        for name in runner.REQUIRED_SOURCES}
        source_pins = dict(current_pins)
        source_pins["pokerlab/unrelated-historical.py"] = "a" * 64
        report = {
            "schema_version": runner.SCHEMA_VERSION,
            "benchmark_id": runner.BENCHMARK_ID,
            "generation_capture_calls": 2,
            "baseline_source_commit": runner.BASELINE_SOURCE_COMMIT,
            "generation_git_commit": "c" * 40,
            "current_head_at_generation": "c" * 40,
            "baseline_report_sha256": "b" * 64,
            "reference_sha256": runner.REFERENCE_SHA256,
            "source_sha256": source_pins,
        }
        runner._check_report_envelope(report, current_pins,
                                      "e" * 40, baseline)
        report["source_sha256"][runner.REQUIRED_SOURCES[0]] = "f" * 64
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            runner._check_report_envelope(report, current_pins,
                                          "e" * 40, baseline)

    def test_saved_metric_mutation_is_not_repaired_during_replay(self):
        policy = {name: 0.0 for name in runner.METRICS}
        oracle = {name: 0.0 for name in runner.METRICS}
        oracle.update(worlds=176, compatible_pair_count=4,
                      checked_information_sets=2404)
        with patch.object(runner, "_independent_oracle", return_value=oracle), \
                patch.object(runner, "compare_result", return_value={}):
            runner._replay(policy, "materialized", "prefix", {})
            policy["nash_conv"] = 0.25
            tampered_hash = runner._sha(canonical(policy))
            self.assertEqual(len(tampered_hash), 64)
            with self.assertRaisesRegex(ValueError, "Saved policy metrics"):
                runner._replay(policy, "materialized", "prefix", {})
            self.assertEqual(policy["nash_conv"], 0.25)

    def test_synthetic_harness_generation_and_all_saved_verification_stages(self):
        """SYNTHETIC HARNESS FIXTURE: accepted payloads, zero actual training."""
        with local_temp() as temp:
            temp = Path(temp)
            report_path, policies_path = temp / "report.json", temp / "policies"
            baseline = runner._baseline_pins()
            original_bytes = dict(baseline["policies"])
            source_map = {
                name: hashlib.sha256(("synthetic:" + name).encode()).hexdigest()
                for name in runner.REQUIRED_SOURCES
            }
            # Synthetic observations still need authenticated protected source endpoints.
            source_map.update({name: TRANSITIONS[name][1] for name in runner.REQUIRED_SOURCES
                               if name in TRANSITIONS})
            fake_head = "a" * 40
            calls = []

            def accepted_snapshots(case, backend, discard, total, interval=None):
                calls.append((backend, discard, total, interval))
                full = json.loads(baseline["policies"][(backend, total)])
                prefix = json.loads(baseline["policies"][(backend, discard)])
                evidence = {
                    "trainer_calls": 1,
                    "final_snapshot_exactly_matches_returned_profile": True,
                    "callback_iterations": [discard, total],
                    "complete_call_with_observations_seconds": 0.0,
                    "independent_replay_seconds": 0.0,
                }
                return full, prefix, evidence

            with patch.object(runner, "fingerprints", return_value=source_map), \
                    patch.object(runner, "_head", return_value=fake_head), \
                    patch.object(runner, "capture", side_effect=accepted_snapshots) as mocked_capture, \
                    patch("builtins.print"):
                first = runner.generate(report_path, policies_path, allow_training=True)
                self.assertEqual(first["status"], "VERIFIED_SAVED_TURN_TAIL")
                self.assertEqual(first["training_calls"], 0)
                self.assertEqual(first["profiles"], 6)
                # Existing accepted output takes the saved-verification path;
                # it must not request fresh captured profiles.
                second = runner.generate(report_path, policies_path, allow_training=True)
                self.assertEqual(second["status"], "VERIFIED_SAVED_TURN_TAIL")
                self.assertEqual(mocked_capture.call_count, 2)

            self.assertEqual(calls, [(backend, 1000, 1500, 1000)
                                     for backend in runner.BACKENDS])
            self.assertEqual(len(list(policies_path.glob("*.json"))), 6)
            for (backend, iteration), raw in original_bytes.items():
                filename = f"full-deck-raised-turn-v1-{backend}-{iteration}.json"
                self.assertEqual(runner._read_capped(
                    runner.BASELINE_POLICIES / filename, runner.MAX_POLICY_BYTES,
                    "Baseline policy"), raw)
            with report_path.open("rb") as stream:
                report = json.loads(stream.read())
            self.assertEqual(report["baseline_report_sha256"],
                             runner.BASELINE_REPORT_SHA256)
            self.assertEqual(report["baseline_source_commit"],
                             runner.BASELINE_SOURCE_COMMIT)
            self.assertTrue(all(row["independent_replay"] for row in report["results"]))

    def test_source_and_head_guard_reject_drift(self):
        with patch.object(runner, "fingerprints", return_value={"x.py": "new"}), \
                patch.object(runner, "_head", return_value="a" * 40):
            with self.assertRaisesRegex(ValueError, "source"):
                runner._guard({"x.py": "old"}, "a" * 40)
        with patch.object(runner, "fingerprints", return_value={"x.py": "same"}), \
                patch.object(runner, "_head", return_value="b" * 40):
            with self.assertRaisesRegex(ValueError, "HEAD"):
                runner._guard({"x.py": "same"}, "a" * 40)

    def test_atomic_policy_publication_never_overwrites_unrelated_bytes(self):
        with local_temp() as temp:
            target = Path(temp) / "kept.json"
            target.write_bytes(b"existing")
            created = []
            with self.assertRaisesRegex(ValueError, "immutable"):
                runner._atomic_exclusive(target, b"new", created)
            self.assertEqual(target.read_bytes(), b"existing")
            self.assertEqual(created, [])

    def test_derived_windows_preserve_full_request_cost_metadata(self):
        source = {"solver_version": "production-v1", "iterations": 1500,
                  "strategy": []}
        prefix = runner._derived_payload(source, "prefix", [])
        tail = runner._derived_payload(source, "tail", [])
        self.assertEqual(prefix["source_iteration_window"], [1, 1000])
        self.assertEqual(tail["source_iteration_window"], [1001, 1500])
        self.assertEqual((prefix["iterations"], tail["iterations"]), (1000, 1500))
        self.assertEqual(tail["averaged_sweeps"], 500)
        self.assertEqual(prefix["resource_metadata_scope"], tail["resource_metadata_scope"])
        self.assertIn("1500-sweep", prefix["resource_metadata_scope"])
        self.assertEqual(runner._json_fraction({"count": 0, "flag": False,
                                                "exact": Fraction(1, 3)}),
                         {"count": 0, "flag": False, "exact": "1/3"})

    def test_cheap_real_capture_conversion_and_replay_for_both_backends(self):
        for backend in runner.BACKENDS:
            with self.subTest(backend=backend):
                case = runner.frozen_case()
                profiles, evidence, oracle, ledger = runner.process_capture(
                    deepcopy(case), backend, 6, 10, interval=3)
                unwrapped = solve(case, backend, runner.ALGORITHM, 10)
                self.assertEqual(canonical(profiles["full"]), canonical(unwrapped))
                self.assertEqual(evidence["callback_iterations"], [3, 6, 9, 10])
                self.assertEqual(profiles["prefix"]["iterations"], 6)
                self.assertEqual(profiles["tail"]["iterations"], 10)
                self.assertEqual(profiles["tail"]["averaged_sweeps"], 4)
                self.assertEqual(profiles["tail"]["source_iteration_window"], [7, 10])
                self.assertEqual(set(oracle), {"prefix", "full", "tail"})
                for result in oracle.values():
                    self.assertEqual((result["worlds"], result["compatible_pairs"],
                                      result["information_rows"]), (176, 4, 2404))
                self.assertIn("changed_rows", ledger)


if __name__ == "__main__":
    unittest.main()
