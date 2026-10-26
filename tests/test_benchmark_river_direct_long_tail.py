"""Focused math and synthetic publication-plumbing tests for the fixed long river run."""
from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

from pokerlab import river_tail_adapter as adapter
from pokerlab.river_config import RiverConfig
from scripts import benchmark_river_direct_long_tail as runner
from scripts import benchmark_river_direct_tail as base

SCRATCH = Path(__file__).resolve().parents[1]
TEST_TMP = SCRATCH / ".test_tmp"
REFERENCE_ROOT = runner.ROOT


def _temp_root():
    TEST_TMP.mkdir(exist_ok=True)
    root = TEST_TMP / f"long-river-{uuid.uuid4().hex}"
    results = root / "benchmarks" / "results"
    results.mkdir(parents=True, exist_ok=False)
    for key, source in runner._input_paths(REFERENCE_ROOT).items():
        (results / source.name).write_bytes(source.read_bytes())
    return root


def _remove_tree_files(root):
    results = root / "benchmarks" / "results"
    if results.exists():
        for path in results.iterdir():
            if path.is_file():
                path.unlink()
        results.rmdir()
    benchmarks = root / "benchmarks"
    if benchmarks.exists():
        benchmarks.rmdir()
    work = root / "work"
    if work.exists():
        rejected = work / "river_direct_long_tail_rejected"
        if rejected.exists():
            for path in rejected.iterdir():
                if path.is_file():
                    path.unlink()
            rejected.rmdir()
        work.rmdir()
    root.rmdir()


def _synthetic_long_payload(inputs):
    """Test-only schedule-shaped object; never a trained 100k policy."""
    fixture = runner.FIXTURE
    result = adapter.solve_river_tail(
        fixture["board"], fixture["oop"], fixture["ip"], fixture["config"],
        iterations=10, discard=5)
    result.update(runner._expected_profile(result, inputs["policy"], 100_000, 3_000))
    return result


def _synthetic_maps():
    producer = {name: "0" * 64 for name in runner.PRODUCER_REQUIRED}
    producer["pokerlab/cards.py"] = "1" * 64
    verification = {name: "2" * 64 for name in runner.VERIFY_PATHS}
    return producer, verification


def _audit_stub(inputs):
    exact = dict(inputs["accepted_exact_metrics"])
    return {
        "numeric_replay_deltas": {key: 0.0 for key in runner.METRICS},
        "exact_numeric_replay_deltas": {key: 0.0 for key in runner.METRICS},
        "exact_metrics_fractions": exact,
        "exact_threshold_fraction": "1/1000",
        "exact_threshold_met": False,
        "exact_nash_conv_zero": False,
        "known_value_fraction": "25",
        "known_value_in_response_interval": True,
        "lower_value_bound_fraction": "24",
        "upper_value_bound_fraction": "26",
        "exact_certificate": {"work": 1, "work_limit": 100_000,
                              "depth_limit": 64, "fraction_bit_limit": 65_536,
                              "normalization_ledger": []},
        "polarized_16x4_witness": {"scope": "synthetic plumbing only"},
    }


class RiverDirectLongTailTests(unittest.TestCase):
    def test_real_accepted_two_file_inputs_hash_and_exact_metrics(self):
        inputs = runner._read_inputs(REFERENCE_ROOT)
        runner._guard_inputs(REFERENCE_ROOT, inputs)
        audited = runner._audit_math(inputs["policy"], inputs,
                                     iterations=10_000, discard=3_000)
        self.assertEqual(inputs["report_sha256"], runner.INPUT_REPORT_SHA256)
        self.assertEqual(inputs["policy_sha256"], runner.INPUT_POLICY_SHA256)
        self.assertEqual(audited["exact_metrics_fractions"], inputs["accepted_exact_metrics"])
        self.assertEqual(audited["exact_certificate"]["work_limit"], 100_000)
        self.assertTrue(audited["known_value_in_response_interval"])

    def test_genuine_ten_five_profile_metadata_numeric_exact_and_16x4(self):
        inputs = runner._read_inputs(REFERENCE_ROOT)
        fixture = runner.FIXTURE
        result = adapter.solve_river_tail(
            fixture["board"], fixture["oop"], fixture["ip"], fixture["config"],
            iterations=10, discard=5)
        audit = runner._audit_math(result, inputs, iterations=10, discard=5)
        self.assertEqual(result["solver_version"], runner.V1_VERSION)
        self.assertEqual(result["iterations"], 10)
        self.assertEqual(result["discard"], 5)
        self.assertEqual(set(audit["exact_metrics_fractions"]), set(runner.METRICS))
        self.assertTrue(audit["known_value_in_response_interval"])
        self.assertEqual(audit["polarized_16x4_witness"]["known_game_value_fraction"], "25")
        self.assertEqual(audit["exact_certificate"]["work_limit"], 100_000)
        self.assertEqual(audit["exact_certificate"]["depth_limit"], 64)
        self.assertEqual(audit["exact_certificate"]["fraction_bit_limit"], 65_536)

    def test_independent_math_rejects_a_metric_disagreement(self):
        inputs = runner._read_inputs(REFERENCE_ROOT)
        fixture = runner.FIXTURE
        result = adapter.solve_river_tail(
            fixture["board"], fixture["oop"], fixture["ip"], fixture["config"],
            iterations=10, discard=5)
        result["oop_best_response_gain"] += 0.01
        with self.assertRaisesRegex(ValueError, "independent replay"):
            runner._audit_math(result, inputs, iterations=10, discard=5)

    def test_disagreeing_exact_history_oracle_is_rejected(self):
        from fractions import Fraction
        from scripts import replay_river_accuracy_extension as history
        inputs = runner._read_inputs(REFERENCE_ROOT)
        fixture = runner.FIXTURE
        result = adapter.solve_river_tail(
            fixture["board"], fixture["oop"], fixture["ip"], fixture["config"],
            iterations=10, discard=5)
        witness = history.rational_polarised(result, fixture)
        witness["oop_br_fraction"] = str(Fraction(witness["oop_br_fraction"]) + 1)
        with patch.object(history, "rational_polarised", return_value=witness):
            with self.assertRaisesRegex(ValueError, "exact-history oracle differs"):
                runner._audit_math(result, inputs, iterations=10, discard=5)

    def test_full_report_reconstruction_is_explicitly_synthetic_plumbing_only(self):
        inputs = runner._read_inputs(REFERENCE_ROOT)
        payload = _synthetic_long_payload(inputs)
        producer, verification = _synthetic_maps()
        policy_raw = base._canonical(payload)
        audit = _audit_stub(inputs)
        report = runner._build_report("a" * 40, producer, verification, inputs,
                                      payload, audit, 0.25, policy_raw)
        report_raw = base._canonical(report)
        with patch.object(runner, "compatible_exact_source_maps", side_effect=lambda saved, current, root: saved == current), \
             patch.object(runner, "_audit_math", return_value=audit):
            rebuilt = runner._verify_bundle(
                report_raw, policy_raw, root=REFERENCE_ROOT,
                expected_math=verification, inputs=inputs, current_head=None)
        self.assertEqual(base._canonical(rebuilt), report_raw)
        self.assertEqual(rebuilt["generation_head"], "a" * 40)
        self.assertNotIn("a" * 40, (REFERENCE_ROOT / ".git" / "objects").as_posix())
        # This only tests serialization/reconstruction plumbing. The payload above
        # is a T10 policy with test-only metadata and is not a 100k training result.
        with self.assertRaisesRegex(ValueError, "timing"):
            runner._build_report("a" * 40, producer, verification, inputs,
                                 payload, audit, True, policy_raw)
        with self.assertRaisesRegex(ValueError, "byte cap"):
            runner._build_report("a" * 40, producer, verification, inputs,
                                 payload, audit, 0.25, b"x" * (runner.POLICY_CAP + 1))

    def test_two_file_stage_and_publish_round_trip_is_synthetic_plumbing_only(self):
        root = _temp_root()
        try:
            inputs = runner._read_inputs(root)
            payload = _synthetic_long_payload(inputs)
            producer, verification = _synthetic_maps()
            head = "e" * 40
            policy_raw = base._canonical(payload)
            audit = _audit_stub(inputs)
            report = runner._build_report(head, producer, verification, inputs,
                                          payload, audit, 0.125, policy_raw)
            report_raw = base._canonical(report)
            with patch.object(runner, "compatible_exact_source_maps", side_effect=lambda saved, current, root: saved == current), \
                 patch.object(runner, "_guard_generation"), \
                 patch.object(runner, "_audit_math", return_value=audit), \
                 patch.object(base, "_head", return_value=head):
                runner._publish_bundle(report_raw, policy_raw, root=root, head=head,
                                       producer=producer, verification=verification,
                                       inputs=inputs)
                actual_report, actual_policy = runner._read_bundle(runner._targets(root))
                self.assertEqual(actual_report, report_raw)
                self.assertEqual(actual_policy, policy_raw)
                rebuilt = runner._verify_bundle(
                    actual_report, actual_policy, root=root,
                    expected_math=verification, inputs=inputs, current_head=head)
            self.assertEqual(base._canonical(rebuilt), report_raw)
            # Test-only schedule-shaped data exercises file ownership and replay plumbing,
            # not a real 100k policy or quality observation.
        finally:
            _remove_tree_files(root)

    def test_bundle_rejects_nonbyte_arguments_before_parsing(self):
        inputs = runner._read_inputs(REFERENCE_ROOT)
        with self.assertRaisesRegex(ValueError, "must be bytes"):
            runner._verify_bundle("{}", b"{}", root=REFERENCE_ROOT,
                                  expected_math={}, inputs=inputs, current_head=None)

    def test_report_timing_schema_and_historical_source_context_are_strict(self):
        inputs = runner._read_inputs(REFERENCE_ROOT)
        payload = _synthetic_long_payload(inputs)
        producer, verification = _synthetic_maps()
        audit = _audit_stub(inputs)
        policy_raw = base._canonical(payload)
        report = runner._build_report("b" * 40, producer, verification,
                                      inputs, payload, audit, 0.5, policy_raw)
        for mutation, pattern in (
            (lambda row: row.update(actual_complete_call_seconds=True), "timing"),
            (lambda row: row.update(schema_version=True), "schema"),
            (lambda row: row.update(fixture_id="forged"), "fixture"),
            (lambda row: row.update(iterations=True), "schedule"),
        ):
            changed = copy.deepcopy(report)
            mutation(changed)
            with patch.object(runner, "compatible_exact_source_maps", side_effect=lambda saved, current, root: saved == current), \
                 self.subTest(pattern=pattern), patch.object(runner, "_audit_math", return_value=audit):
                with self.assertRaisesRegex(ValueError, pattern):
                    runner._verify_bundle(base._canonical(changed), policy_raw,
                                          root=REFERENCE_ROOT, expected_math=verification,
                                          inputs=inputs, current_head=None)
        malformed = dict(producer)
        malformed["../outside.py"] = "3" * 64
        with self.assertRaisesRegex(ValueError, "source map"):
            runner._validate_historical_map(malformed, runner.PRODUCER_REQUIRED, producer=True)
        malformed = dict(producer)
        malformed["pokerlab/cards.py"] = int("1" * 64)
        with self.assertRaisesRegex(ValueError, "source map"):
            runner._validate_historical_map(malformed, runner.PRODUCER_REQUIRED, producer=True)
        malformed = dict(producer)
        malformed["pokerlab\\nested.py"] = "4" * 64
        with self.assertRaisesRegex(ValueError, "source map"):
            runner._validate_historical_map(malformed, runner.PRODUCER_REQUIRED, producer=True)
        malformed = dict(producer)
        malformed["pokerlab/nested/module.py"] = "5" * 64
        with self.assertRaisesRegex(ValueError, "source map"):
            runner._validate_historical_map(malformed, runner.PRODUCER_REQUIRED, producer=True)
        self.assertIn("tests/reference_river_tail_v1.py", runner.PRODUCER_REQUIRED)

    def test_generation_rejects_new_producer_module_drift(self):
        inputs = runner._read_inputs(REFERENCE_ROOT)
        head = "f" * 40
        actual_paths = runner._producer_paths(REFERENCE_ROOT)
        changed_paths = (*actual_paths, "pokerlab/late_added.py")
        with patch.object(base, "_head", return_value=head), \
             patch.object(runner, "_producer_paths", return_value=changed_paths):
            with self.assertRaisesRegex(RuntimeError, "Producer source bytes changed"):
                runner._guard_generation(REFERENCE_ROOT, head, {}, {}, inputs)

    def test_real_input_byte_drift_is_rejected_without_touching_accepted_repo(self):
        root = _temp_root()
        try:
            inputs = runner._read_inputs(root)
            path = root / "benchmarks" / "results" / "river-direct-tail-v1-polarised.json"
            raw = path.read_bytes()
            path.write_bytes(raw + b" ")
            with self.assertRaisesRegex(ValueError, "bytes changed"):
                runner._guard_inputs(root, inputs)
        finally:
            _remove_tree_files(root)

    def test_existing_output_refuses_before_inputs_or_source_checks(self):
        TEST_TMP.mkdir(exist_ok=True)
        root = TEST_TMP / f"long-river-target-{uuid.uuid4().hex}"
        targets = runner._targets(root)
        targets["report"].parent.mkdir(parents=True, exist_ok=False)
        sentinel = b"foreign target"
        targets["report"].write_bytes(sentinel)
        try:
            with patch.object(runner, "_read_inputs", side_effect=AssertionError("inputs read")), \
                 patch.object(runner, "_source_context", side_effect=AssertionError("source checked")):
                with self.assertRaises(FileExistsError):
                    runner.generate(root)
            self.assertEqual(targets["report"].read_bytes(), sentinel)
        finally:
            targets["report"].unlink()
            targets["report"].parent.rmdir()
            (root / "benchmarks").rmdir()
            root.rmdir()

    def test_descriptor_owned_stage_failure_rolls_back_only_owned_files(self):
        TEST_TMP.mkdir(exist_ok=True)
        root = TEST_TMP / f"long-river-stage-fault-{uuid.uuid4().hex}"
        results = root / "benchmarks" / "results"
        results.mkdir(parents=True, exist_ok=False)
        unrelated = results / "unrelated.keep"
        unrelated.write_bytes(b"keep")
        original_write = base._owned_write
        calls = 0

        def fail_second(path, raw, owned):
            nonlocal calls
            calls += 1
            original_write(path, raw, owned)
            if calls == 2:
                raise OSError("injected second stage failure")

        producer, verification = _synthetic_maps()
        inputs = runner._read_inputs(REFERENCE_ROOT)
        try:
            with patch.object(base, "_owned_write", side_effect=fail_second), \
                 patch.object(runner, "_guard_generation"):
                with self.assertRaisesRegex(OSError, "second stage"):
                    runner._publish_bundle(b"report", b"policy", root=root,
                                           head="a" * 40, producer=producer,
                                           verification=verification, inputs=inputs)
            self.assertEqual(unrelated.read_bytes(), b"keep")
            self.assertEqual(list(results.glob(".*.stage")), [])
            self.assertTrue(all(not path.exists() for path in runner._targets(root).values()))
        finally:
            unrelated.unlink()
            results.rmdir()
            (root / "benchmarks").rmdir()
            root.rmdir()

    def test_stage_bytes_and_published_foreign_replacement_are_guarded(self):
        TEST_TMP.mkdir(exist_ok=True)
        root = TEST_TMP / f"long-river-stage-drift-{uuid.uuid4().hex}"
        results = root / "benchmarks" / "results"
        results.mkdir(parents=True, exist_ok=False)
        unrelated = results / "keep.me"
        unrelated.write_bytes(b"keep")
        producer, verification = _synthetic_maps()
        inputs = runner._read_inputs(REFERENCE_ROOT)
        stages = {}
        real_publish = base._publish_staged

        def accept_but_mutate(_report, _policy, *, bundle_guard=None, **_kwargs):
            stages["policy"].write_bytes(b"changed staged bytes")
            bundle_guard()

        orig_write = base._owned_write
        def remember(path, raw, owned):
            orig_write(path, raw, owned)
            if path.name.endswith(".stage") and "polarised" in path.name:
                stages["policy"] = path

        try:
            with patch.object(base, "_owned_write", side_effect=remember), \
                 patch.object(runner, "_guard_generation"), \
                 patch.object(runner, "_verify_bundle", side_effect=accept_but_mutate):
                with self.assertRaisesRegex(RuntimeError, "bytes changed"):
                    runner._publish_bundle(b"report", b"policy", root=root,
                                           head="a" * 40, producer=producer,
                                           verification=verification, inputs=inputs)
            self.assertEqual(unrelated.read_bytes(), b"keep")
            self.assertEqual(list(results.glob(".*.stage")), [])
            self.assertTrue(all(not path.exists() for path in runner._targets(root).values()))
        finally:
            unrelated.unlink()
            results.rmdir()
            (root / "benchmarks").rmdir()
            root.rmdir()

        # Separate ownership test: a foreign file replacing a linked target survives rollback.
        root = TEST_TMP / f"long-river-foreign-{uuid.uuid4().hex}"
        results = root / "benchmarks" / "results"
        results.mkdir(parents=True, exist_ok=False)
        unrelated = results / "keep.me"
        unrelated.write_bytes(b"keep")
        targets = runner._targets(root)
        foreign = b"foreign replacement"

        def replace_after_link(staged, target_map, owned):
            real_publish(staged, target_map, owned)
            target_map["report"].unlink()
            target_map["report"].write_bytes(foreign)

        try:
            with patch.object(runner, "_guard_generation"), \
                 patch.object(runner, "_verify_bundle"), \
                 patch.object(base, "_publish_staged", side_effect=replace_after_link):
                with self.assertRaisesRegex(RuntimeError, "inode changed"):
                    runner._publish_bundle(b"report", b"policy", root=root,
                                           head="a" * 40, producer=producer,
                                           verification=verification, inputs=inputs)
            self.assertEqual(targets["report"].read_bytes(), foreign)
            self.assertFalse(targets["policy"].exists())
            self.assertEqual(unrelated.read_bytes(), b"keep")
        finally:
            for path in (targets["report"], unrelated):
                if path.exists():
                    path.unlink()
            results.rmdir()
            (root / "benchmarks").rmdir()
            root.rmdir()

    def test_final_readonly_bundle_guard_runs_after_final_source_input_check(self):
        root = _temp_root()
        targets = runner._targets(root)
        targets["report"].write_bytes(b"synthetic report")
        targets["policy"].write_bytes(b"synthetic policy")
        try:
            inputs = runner._read_inputs(root)
            producer, verification = _synthetic_maps()
            head = "c" * 40
            bundle_checked = False

            def mark_bundle_checked(*args, **kwargs):
                nonlocal bundle_checked
                bundle_checked = True

            def late_change(_root, _head, _verification, _inputs):
                # Drift during the final source/input check, after the bundle
                # has been read and its complete verification has returned.
                if bundle_checked:
                    targets["policy"].write_bytes(b"late modified policy")

            with patch.object(runner, "_verification_context", return_value=(head, verification)), \
                 patch.object(runner, "_verify_bundle", side_effect=mark_bundle_checked), \
                 patch.object(runner, "_guard_replay", side_effect=late_change):
                with self.assertRaisesRegex(RuntimeError, "bytes changed"):
                    runner.verify(root)
        finally:
            _remove_tree_files(root)

    def test_post_return_late_failure_preserves_exact_policy_bytes(self):
        root = _temp_root()
        try:
            inputs = runner._read_inputs(root)
            fixture = runner.FIXTURE
            synthetic_return = adapter.solve_river_tail(
                fixture["board"], fixture["oop"], fixture["ip"], fixture["config"],
                iterations=10, discard=5)
            producer, verification = _synthetic_maps()
            head = "d" * 40
            real_audit = runner._audit_math

            def reject_new_payload(payload, loaded, **kwargs):
                if payload is synthetic_return:
                    raise RuntimeError("late synthetic audit rejection")
                return real_audit(payload, loaded, **kwargs)

            with patch.object(runner, "_source_context", return_value=(head, producer, verification)), \
                 patch.object(runner, "_guard_generation"), \
                 patch.object(runner, "_audit_math", side_effect=reject_new_payload), \
                 patch.object(adapter, "solve_river_tail", return_value=synthetic_return):
                with self.assertRaisesRegex(RuntimeError, "late synthetic"):
                    runner.generate(root)
            folder = root / "work" / "river_direct_long_tail_rejected"
            records = list(folder.glob("rejected-*.json"))
            self.assertEqual(len(records), 1)
            record = json.loads(records[0].read_bytes())
            self.assertEqual(base64.b64decode(record["raw_policy_base64"]),
                             base._canonical(synthetic_return))
            records[0].unlink()
            folder.rmdir()
            (root / "work").rmdir()
        finally:
            _remove_tree_files(root)

    def test_unserializable_returned_policy_is_preserved_without_masking_failure(self):
        root = _temp_root()
        try:
            inputs = runner._read_inputs(root)
            returned = adapter.solve_river_tail(
                runner.FIXTURE["board"], runner.FIXTURE["oop"], runner.FIXTURE["ip"],
                runner.FIXTURE["config"], iterations=10, discard=5)
            producer, verification = _synthetic_maps()
            head = "9" * 40
            with patch.object(runner, "_source_context", return_value=(head, producer, verification)), \
                 patch.object(runner, "_guard_generation"), \
                 patch.object(runner, "_audit_math", return_value=_audit_stub(inputs)), \
                 patch.object(adapter, "solve_river_tail", return_value=returned), \
                 patch.object(runner, "_serialize_policy", side_effect=TypeError("injected serialization failure")):
                with self.assertRaisesRegex(TypeError, "injected serialization"):
                    runner.generate(root)
            folder = root / "work" / "river_direct_long_tail_rejected"
            records = list(folder.glob("rejected-*.json"))
            self.assertEqual(len(records), 1)
            record = json.loads(records[0].read_bytes())
            self.assertIsNone(record["raw_policy_base64"])
            self.assertIsNone(record["raw_policy_sha256"])
            self.assertIn("strategy", record["unserialized_returned_policy_repr"])
            self.assertIn("injected serialization", record["rejection"])
            records[0].unlink()
            folder.rmdir()
            (root / "work").rmdir()
        finally:
            _remove_tree_files(root)

    def test_nonfinite_elapsed_rejection_still_preserves_returned_policy(self):
        root = _temp_root()
        try:
            inputs = runner._read_inputs(root)
            returned = adapter.solve_river_tail(
                runner.FIXTURE["board"], runner.FIXTURE["oop"], runner.FIXTURE["ip"],
                runner.FIXTURE["config"], iterations=10, discard=5)
            producer, verification = _synthetic_maps()
            with patch.object(runner, "_source_context", return_value=("9" * 40, producer, verification)), \
                 patch.object(runner, "_guard_generation"), \
                 patch.object(runner, "_audit_math", return_value=_audit_stub(inputs)), \
                 patch.object(adapter, "solve_river_tail", return_value=returned), \
                 patch.object(runner.time, "perf_counter", side_effect=(1.0, float("nan"))):
                with self.assertRaisesRegex(ValueError, "timing"):
                    runner.generate(root)
            records = list((root / "work" / "river_direct_long_tail_rejected").glob("*.json"))
            self.assertEqual(len(records), 1)
            record = json.loads(records[0].read_bytes())
            self.assertIsNone(record["actual_complete_call_seconds"])
            self.assertEqual(record["invalid_elapsed_repr"], "nan")
            self.assertEqual(base64.b64decode(record["raw_policy_base64"]), base._canonical(returned))
        finally:
            _remove_tree_files(root)

    def test_invalid_none_return_preserves_completed_call_context(self):
        root = _temp_root()
        try:
            producer, verification = _synthetic_maps()
            with patch.object(runner, "_source_context", return_value=("6" * 40, producer, verification)), \
                 patch.object(runner, "_guard_generation"), \
                 patch.object(adapter, "solve_river_tail", return_value=None):
                with self.assertRaisesRegex(ValueError, "Policy payload must be a dictionary"):
                    runner.generate(root)
            records = list((root / "work" / "river_direct_long_tail_rejected").glob("*.json"))
            self.assertEqual(len(records), 1)
            record = json.loads(records[0].read_bytes())
            self.assertEqual(base64.b64decode(record["raw_policy_base64"]), b"null\n")
            self.assertEqual((record["fixture_id"], record["iterations"], record["discard"]),
                             (runner.FIXTURE_ID, 100000, 3000))
        finally:
            _remove_tree_files(root)

    def test_committed_context_guards_old_audit_before_training_boundary(self):
        root = _temp_root()
        try:
            inputs = runner._read_inputs(root)
            producer, verification = _synthetic_maps()
            events = []

            def context(_root):
                events.append("context")
                return "7" * 40, producer, verification

            def guard(*args):
                self.assertEqual(events[0], "context")
                events.append("guard")

            real_audit = runner._audit_math

            def audit_old(payload, loaded, **kwargs):
                self.assertIsNotNone(kwargs.get("guard"))
                self.assertIn("guard", events)
                events.append("old audit")
                return real_audit(payload, loaded, **kwargs)

            def boundary(*args, **kwargs):
                self.assertIn("old audit", events)
                self.assertEqual(events[-1], "guard")
                raise RuntimeError("training boundary sentinel; no solve executed")

            with patch.object(runner, "_source_context", side_effect=context), \
                 patch.object(runner, "_guard_generation", side_effect=guard), \
                 patch.object(runner, "_audit_math", side_effect=audit_old), \
                 patch.object(adapter, "solve_river_tail", side_effect=boundary):
                with self.assertRaisesRegex(RuntimeError, "training boundary sentinel"):
                    runner.generate(root)
        finally:
            _remove_tree_files(root)


if __name__ == "__main__":
    unittest.main()
