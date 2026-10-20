"""Focused non-benchmark checks for the fixed direct river-tail bundle."""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

from pokerlab.river_tail_adapter import solve_river_tail
from scripts import benchmark_river_direct_tail as runner

SCRATCH = Path(__file__).resolve().parents[1]
TEST_TMP = SCRATCH / ".test_tmp"
REFERENCE_ROOT = runner.ROOT


class RiverDirectTailEvidenceTests(unittest.TestCase):
    def _synthetic_plumbing_bundle(self):
        """T10 policies plus stubbed audit rows for report/ownership plumbing only."""
        inputs = runner._load_inputs(REFERENCE_ROOT)
        policies = {}
        rows = {}
        for fixture_id, fixture in runner.FIXTURES.items():
            result = solve_river_tail(
                fixture["board"], fixture["oop"], fixture["ip"],
                fixture["config"], iterations=10, discard=5)
            policies[fixture_id] = runner._canonical(result)
            rows[fixture_id] = {
                "exact_threshold_met": False,
                "exact_nash_conv_zero": False,
                "plumbing_probe": "synthetic-test-only; no 10k training",
                **runner._metadata_only_report_row(result, 0.25),
            }
        head = "a" * 40  # Deliberately historical and not required to exist locally.
        producer = {key: "0" * 64 for key in runner.PRODUCER_EXTRA}
        producer["pokerlab/cards.py"] = "1" * 64
        verification = {key: "2" * 64 for key in runner.VERIFY_PATHS}
        report = runner._build_report(head, producer, verification, inputs, rows, policies)
        return inputs, policies, rows, head, producer, verification, report

    def test_real_accepted_prior_input_loader_checks_fixed_bytes_and_metadata(self):
        inputs = runner._load_inputs(REFERENCE_ROOT)
        runner._guard_inputs(REFERENCE_ROOT, inputs)
        self.assertEqual(
            inputs["report_sha256"], runner.OLD_TAIL_REPORT_SHA256)
        self.assertEqual(set(inputs["policies"]), set(runner.FIXTURES))
        self.assertEqual(
            inputs["policies"]["river-polarised-bluffcatcher"]["sha256"],
            runner.OLD_POLICIES["river-polarised-bluffcatcher"][1])
        self.assertEqual(
            inputs["policies"]["river-weighted-raises"]["sha256"],
            runner.OLD_POLICIES["river-weighted-raises"][1])
        for fixture_id, loaded in inputs["policies"].items():
            row = loaded["report_row"]
            self.assertEqual(row["scenario"], fixture_id)
            self.assertEqual(row["backend"], "materialized")
            self.assertEqual(row["profile_kind"], "tail")
            self.assertEqual(row["source_requested_iterations"], 10_000)
            self.assertEqual(row["source_iteration_window"], [3001, 10_000])
            self.assertEqual(loaded["payload"]["solver_version"],
                             "research-river-cfrplus-tail-v1")

    def test_genuine_ten_sweep_profiles_pass_full_independent_exact_audit(self):
        inputs = runner._load_inputs(REFERENCE_ROOT)
        for fixture_id, fixture in runner.FIXTURES.items():
            with self.subTest(fixture=fixture_id):
                result = solve_river_tail(
                    fixture["board"], fixture["oop"], fixture["ip"],
                    fixture["config"], iterations=10, discard=5)
                runner._validate_profile_metadata(
                    result, fixture_id, iterations=10, discard=5)
                audit = runner._audit_new_policy(
                    result, fixture_id, iterations=10, discard=5)
                self.assertEqual(audit["fixture"], fixture_id)
                self.assertEqual(audit["exact_certificate"]["work_limit"], 100_000)
                self.assertEqual(audit["exact_certificate"]["depth_limit"], 64)
                self.assertEqual(audit["exact_certificate"]["fraction_bit_limit"], 65_536)
                self.assertEqual(set(audit["exact_metrics_fractions"]), {
                    "value_oop", "value_ip", "oop_best_response_value",
                    "ip_best_response_value", "oop_best_response_gain",
                    "ip_best_response_gain", "nash_conv", "exploitability",
                })
                self.assertTrue(audit["known_game_reference_in_response_interval"])
                expected_reference = ("25" if fixture_id == "river-polarised-bluffcatcher"
                                      else "-43339/2163")
                self.assertEqual(audit["known_game_reference_fraction"], expected_reference)
                import json
                json.dumps(audit, sort_keys=True, allow_nan=False)
                self.assertTrue(all(abs(delta) <= 1e-9
                                    for delta in audit["numeric_replay_deltas"].values()))
                # These are cheap API plumbing probes, not fixed-budget results.
                self.assertEqual(result["iterations"], 10)
                self.assertEqual(result["discard"], 5)
                self.assertEqual(result["training_calls"], 1)

    def test_polarized_exact_history_oracle_matches_generic_certificate(self):
        fixture = runner.FIXTURES["river-polarised-bluffcatcher"]
        result = solve_river_tail(
            fixture["board"], fixture["oop"], fixture["ip"],
            fixture["config"], iterations=10, discard=5)
        audited = runner._audit_new_policy(
            result, "river-polarised-bluffcatcher", iterations=10, discard=5)
        witness = audited["polarized_16x4_witness"]
        self.assertEqual(witness["known_game_value_fraction"], "25")
        self.assertTrue(witness["known_value_in_interval"])
        self.assertTrue(audited["known_game_reference_in_response_interval"])

    def test_genuine_cheap_metadata_rejects_bool_counts_and_missing_resource_keys(self):
        fixture_id = "river-polarised-bluffcatcher"
        fixture = runner.FIXTURES[fixture_id]
        result = solve_river_tail(
            fixture["board"], fixture["oop"], fixture["ip"],
            fixture["config"], iterations=10, discard=5)
        runner._validate_profile_metadata(result, fixture_id, iterations=10, discard=5)

        bool_count = deepcopy(result)
        bool_count["chance_nodes"] = False  # False compares equal to the integer 0.
        with self.assertRaisesRegex(ValueError, "chance_nodes"):
            runner._validate_profile_metadata(bool_count, fixture_id,
                                              iterations=10, discard=5)

        missing_resource = deepcopy(result)
        del missing_resource["resource_usage"]["full_requested_world_node_work"]
        with self.assertRaisesRegex(ValueError, "Resource metadata key set"):
            runner._validate_profile_metadata(missing_resource, fixture_id,
                                              iterations=10, discard=5)

    def test_disagreeing_exact_history_oracle_is_rejected(self):
        from fractions import Fraction
        from scripts import replay_river_accuracy_extension as history
        fixture_id = "river-polarised-bluffcatcher"
        fixture = runner.FIXTURES[fixture_id]
        result = solve_river_tail(
            fixture["board"], fixture["oop"], fixture["ip"],
            fixture["config"], iterations=10, discard=5)
        witness = history.rational_polarised(result, fixture)
        witness["oop_br_fraction"] = str(Fraction(witness["oop_br_fraction"]) + 1)
        with patch.object(history, "rational_polarised", return_value=witness):
            with self.assertRaisesRegex(ValueError, "exact-history result differs"):
                runner._audit_new_policy(result, fixture_id, iterations=10, discard=5)

    def test_public_verify_checks_bundle_after_final_input_guard(self):
        TEST_TMP.mkdir(exist_ok=True)
        root = TEST_TMP / f"direct-tail-public-verify-{uuid.uuid4().hex}"
        results = root / "benchmarks" / "results"
        results.mkdir(parents=True, exist_ok=False)
        targets = runner._fixed_targets(root)
        try:
            for key, path in targets.items():
                path.write_bytes(key.encode())
            # Isolate final guard ordering, without claiming a mathematical audit.
            def mutate_during_final_input_check(*args):
                targets["river-weighted-raises"].write_bytes(b"late input-check drift")

            with patch.object(runner, "_head", return_value="a" * 40), \
                 patch.object(runner, "_verification_hashes", return_value={}), \
                 patch.object(runner, "_require_committed"), \
                 patch.object(runner, "_load_inputs", return_value={}), \
                 patch.object(runner, "_verify_bundle", return_value={}), \
                 patch.object(runner, "_guard_inputs", side_effect=mutate_during_final_input_check):
                with self.assertRaisesRegex(RuntimeError, "bytes changed"):
                    runner.verify(root)
            self.assertEqual(targets["report"].read_bytes(), b"report")
            self.assertEqual(targets["river-weighted-raises"].read_bytes(), b"late input-check drift")
        finally:
            for path in targets.values():
                if path.exists():
                    path.unlink()
            results.rmdir()
            (root / "benchmarks").rmdir()
            root.rmdir()

    def test_complete_report_rebuild_and_historical_context_without_git_lookup(self):
        inputs, policies, rows, historical_head, producer, verification, report = (
            self._synthetic_plumbing_bundle())
        raw_report = runner._canonical(report)

        def stub_audit(payload, fixture_id, loaded, *, guard=None):
            self.assertIs(loaded, inputs)
            return {key: value for key, value in rows[fixture_id].items()
                    if key not in {
                        "actual_complete_call_seconds", "requested_iterations", "discard",
                        "averaged_sweeps", "average_weight_sum", "requested_regret_passes",
                        "requested_average_passes", "requested_total_traversal_passes",
                        "training_calls", "worlds", "compatible_pairs", "public_states",
                        "public_nodes", "visited_nodes", "info_sets", "tree_actions",
                        "info_action_slots", "prefix_hand_edges", "world_node_work",
                        "dense_hand_state_pass_work",
                    }}

        with patch.object(runner, "_audit_policy", side_effect=stub_audit), \
             patch.object(runner, "_guard_replay") as replay_guard:
            checked = runner._verify_bundle(
                raw_report, policies, root=runner.ROOT,
                expected_math=verification, expected_inputs=inputs,
                current_head="b" * 40)
        self.assertEqual(checked["historical_producer_head"], historical_head)
        self.assertNotEqual(checked["historical_producer_head"], "b" * 40)
        replay_guard.assert_called()

    def test_report_tampering_of_fixture_counts_or_elapsed_time_is_rejected(self):
        inputs, policies, rows, _head, _producer, verification, report = (
            self._synthetic_plumbing_bundle())
        audit_rows = {
            fixture_id: {key: value for key, value in row.items()
                         if key not in {
                             "actual_complete_call_seconds", "requested_iterations", "discard",
                             "averaged_sweeps", "average_weight_sum", "requested_regret_passes",
                             "requested_average_passes", "requested_total_traversal_passes",
                             "training_calls", "worlds", "compatible_pairs", "public_states",
                             "public_nodes", "visited_nodes", "info_sets", "tree_actions",
                             "info_action_slots", "prefix_hand_edges", "world_node_work",
                             "dense_hand_state_pass_work",
                         }} for fixture_id, row in rows.items()
        }

        def accept_stub(_payload, fixture_id, _inputs, *, guard=None):
            return audit_rows[fixture_id]

        changed = deepcopy(report)
        changed["fixtures"]["river-polarised-bluffcatcher"]["purpose"] = "forged"
        with patch.object(runner, "_audit_policy", side_effect=accept_stub), \
             patch.object(runner, "_guard_replay"):
            with self.assertRaisesRegex(ValueError, "reconstruction"):
                runner._verify_bundle(runner._canonical(changed), policies,
                                      expected_math=verification, expected_inputs=inputs,
                                      current_head="b" * 40)

        changed = deepcopy(report)
        changed["results"]["river-weighted-raises"]["actual_complete_call_seconds"] = True
        with patch.object(runner, "_audit_policy", side_effect=accept_stub), \
             patch.object(runner, "_guard_replay"):
            with self.assertRaisesRegex(ValueError, "time"):
                runner._verify_bundle(runner._canonical(changed), policies,
                                      expected_math=verification, expected_inputs=inputs,
                                      current_head="b" * 40)

    def test_historical_source_map_rejects_bad_paths_but_never_resolves_old_head(self):
        inputs, policies, rows, _head, producer, verification, report = (
            self._synthetic_plumbing_bundle())
        self.assertFalse(any(key in producer for key in ("", "../outside.py")))
        self.assertEqual(report["historical_producer_head"], "a" * 40)
        runner._expected_map_shape(producer)
        malformed = dict(producer)
        malformed["../outside.py"] = "3" * 64
        with self.assertRaisesRegex(ValueError, "Unexpected historical producer path"):
            runner._expected_map_shape(malformed)

    def test_prior_flow_self_comparison_and_perturbed_ip_call_fold_row(self):
        inputs = runner._load_inputs(REFERENCE_ROOT)
        fixture_id = "river-polarised-bluffcatcher"
        original = inputs["policies"][fixture_id]["payload"]
        same = runner._compare_prior_tail(original, fixture_id, inputs)
        self.assertEqual(same["own_action_flow_max_error_fraction"], "0")

        changed = deepcopy(original)
        row = next(row for row in changed["strategy"]
                   if row["player"] == "ip" and len(row["actions"]) == 2)
        first, second = row["actions"]
        epsilon = 0.01 if first["probability"] <= 0.98 else -0.01
        first["probability"] += epsilon
        second["probability"] -= epsilon
        from scripts import turn_river_validation as validator
        fixture = runner.FIXTURES[fixture_id]
        replay = validator.replay_policy(changed, fixture["oop"], fixture["ip"],
                                         board=fixture["board"], config=fixture["config"])
        for metric in ("value_oop", "value_ip", "oop_best_response_value",
                       "ip_best_response_value", "oop_best_response_gain",
                       "ip_best_response_gain", "nash_conv", "exploitability"):
            changed[metric] = replay[metric]
        with self.assertRaisesRegex(ValueError, "own-action flow"):
            runner._compare_prior_tail(changed, fixture_id, inputs)

    def test_existing_fixed_target_refuses_before_source_or_training_work(self):
        TEST_TMP.mkdir(exist_ok=True)
        root = TEST_TMP / f"direct-tail-target-refusal-{uuid.uuid4().hex}"
        targets = runner._fixed_targets(root)
        targets["report"].parent.mkdir(parents=True, exist_ok=False)
        sentinel = b"foreign accepted target\n"
        targets["report"].write_bytes(sentinel)
        try:
            with patch.object(runner, "_source_context",
                              side_effect=AssertionError("source checks should not run")) as source:
                with self.assertRaises(FileExistsError):
                    runner.generate(root=root)
                source.assert_not_called()
            self.assertEqual(targets["report"].read_bytes(), sentinel)
            self.assertFalse(targets["river-polarised-bluffcatcher"].exists())
            self.assertFalse(targets["river-weighted-raises"].exists())
        finally:
            if targets["report"].exists():
                targets["report"].unlink()
            targets["report"].parent.rmdir()
            (root / "benchmarks").rmdir()
            root.rmdir()

    def test_descriptor_identity_is_registered_before_writing(self):
        TEST_TMP.mkdir(exist_ok=True)
        directory = TEST_TMP / f"direct-tail-owned-write-{uuid.uuid4().hex}"
        directory.mkdir(parents=True, exist_ok=False)
        path = directory / "stage.json"
        owned = {}
        try:
            # A path-stat lookup during registration could adopt a foreign replacement.
            with patch.object(runner, "_bundle_identity",
                              side_effect=AssertionError("must use fstat on opened descriptor")):
                runner._owned_write(path, b"stage bytes", owned)
            expected = (os.stat(path).st_dev, os.stat(path).st_ino)
            self.assertEqual(owned[path], expected)
            self.assertEqual(path.read_bytes(), b"stage bytes")
        finally:
            if path.exists():
                path.unlink()
            directory.rmdir()

    def test_foreign_replacement_is_not_removed_by_owned_rollback(self):
        TEST_TMP.mkdir(exist_ok=True)
        directory = TEST_TMP / f"direct-tail-foreign-{uuid.uuid4().hex}"
        directory.mkdir(parents=True, exist_ok=False)
        stage, target = directory / "stage", directory / "published"
        owned = {}
        try:
            runner._owned_write(stage, b"staged", owned)
            runner._publish_staged({"only": stage}, {"only": target}, owned)
            target.unlink()
            foreign = b"foreign replacement"
            target.write_bytes(foreign)
            runner._rollback_owned(owned)
            self.assertEqual(target.read_bytes(), foreign)
            self.assertFalse(stage.exists())
        finally:
            for path in (stage, target):
                if path.exists():
                    path.unlink()
            directory.rmdir()

    def test_second_and_third_stage_write_faults_rollback_only_owned_files(self):
        original_write = runner._owned_write
        for fail_at in (2, 3):
            with self.subTest(fail_at=fail_at):
                TEST_TMP.mkdir(exist_ok=True)
                root = TEST_TMP / f"direct-tail-stage-fault-{fail_at}-{uuid.uuid4().hex}"
                results = root / "benchmarks" / "results"
                results.mkdir(parents=True, exist_ok=False)
                unrelated = results / "unrelated.keep"
                unrelated.write_bytes(b"unrelated sentinel")
                calls = 0

                def injected(path, raw, owned):
                    nonlocal calls
                    calls += 1
                    original_write(path, raw, owned)
                    if calls == fail_at:
                        raise OSError("injected stage write failure")

                try:
                    with patch.object(runner, "_owned_write", side_effect=injected), \
                         patch.object(runner, "_guard_generation"):
                        with self.assertRaisesRegex(OSError, "injected stage"):
                            runner._publish_bundle(
                                b"report", {
                                    "river-polarised-bluffcatcher": b"policy-a",
                                    "river-weighted-raises": b"policy-b",
                                }, root=root, head="a" * 40, producer={},
                                verification={}, inputs={})
                    targets = runner._fixed_targets(root)
                    self.assertTrue(all(not path.exists() for path in targets.values()))
                    self.assertEqual(unrelated.read_bytes(), b"unrelated sentinel")
                    self.assertEqual(list(results.glob(".*.stage")), [])
                finally:
                    unrelated.unlink()
                    results.rmdir()
                    (root / "benchmarks").rmdir()
                    root.rmdir()

    def test_staged_byte_drift_is_detected_and_rolls_back(self):
        TEST_TMP.mkdir(exist_ok=True)
        root = TEST_TMP / f"direct-tail-stage-drift-{uuid.uuid4().hex}"
        results = root / "benchmarks" / "results"
        results.mkdir(parents=True, exist_ok=False)
        unrelated = results / "keep.me"
        unrelated.write_bytes(b"unrelated")
        stages = {}

        original_read = runner._read_bundle

        def remember_read(paths):
            stages.update(paths)
            return original_read(paths)

        def mutate_then_guard(*_args, bundle_guard=None, **_kwargs):
            stages["river-polarised-bluffcatcher"].write_bytes(b"tampered stage")
            bundle_guard()

        try:
            with patch.object(runner, "_guard_generation"), \
                 patch.object(runner, "_read_bundle", side_effect=remember_read), \
                 patch.object(runner, "_verify_bundle", side_effect=mutate_then_guard):
                with self.assertRaisesRegex(RuntimeError, "bytes changed"):
                    runner._publish_bundle(
                        b"report", {
                            "river-polarised-bluffcatcher": b"policy-a",
                            "river-weighted-raises": b"policy-b",
                        }, root=root, head="a" * 40, producer={},
                        verification={}, inputs={})
            targets = runner._fixed_targets(root)
            self.assertTrue(all(not path.exists() for path in targets.values()))
            self.assertEqual(unrelated.read_bytes(), b"unrelated")
            self.assertEqual(list(results.glob(".*.stage")), [])
        finally:
            unrelated.unlink()
            results.rmdir()
            (root / "benchmarks").rmdir()
            root.rmdir()

    def test_post_link_foreign_replacement_survives_bundle_rollback(self):
        TEST_TMP.mkdir(exist_ok=True)
        root = TEST_TMP / f"direct-tail-post-link-foreign-{uuid.uuid4().hex}"
        results = root / "benchmarks" / "results"
        results.mkdir(parents=True, exist_ok=False)
        unrelated = results / "keep.me"
        unrelated.write_bytes(b"unrelated")
        targets = runner._fixed_targets(root)
        foreign = b"foreign report replacement"
        real_publish = runner._publish_staged

        def replace_after_links(staged, target_map, owned):
            real_publish(staged, target_map, owned)
            target_map["report"].unlink()
            target_map["report"].write_bytes(foreign)

        try:
            with patch.object(runner, "_guard_generation"), \
                 patch.object(runner, "_verify_bundle"), \
                 patch.object(runner, "_publish_staged", side_effect=replace_after_links):
                with self.assertRaisesRegex(RuntimeError, "inode changed"):
                    runner._publish_bundle(
                        b"report", {
                            "river-polarised-bluffcatcher": b"policy-a",
                            "river-weighted-raises": b"policy-b",
                        }, root=root, head="a" * 40, producer={},
                        verification={}, inputs={})
            self.assertEqual(targets["report"].read_bytes(), foreign)
            self.assertFalse(targets["river-polarised-bluffcatcher"].exists())
            self.assertFalse(targets["river-weighted-raises"].exists())
            self.assertEqual(unrelated.read_bytes(), b"unrelated")
        finally:
            for path in (targets["report"], unrelated):
                if path.exists():
                    path.unlink()
            results.rmdir()
            (root / "benchmarks").rmdir()
            root.rmdir()

    def test_final_readonly_bundle_guard_detects_late_byte_drift(self):
        TEST_TMP.mkdir(exist_ok=True)
        directory = TEST_TMP / f"direct-tail-final-guard-{uuid.uuid4().hex}"
        directory.mkdir(parents=True, exist_ok=False)
        targets = {
            "report": directory / "report.json",
            "river-polarised-bluffcatcher": directory / "polar.json",
            "river-weighted-raises": directory / "weighted.json",
        }
        expected_report = b"report original"
        expected_policies = {
            "river-polarised-bluffcatcher": b"polar original",
            "river-weighted-raises": b"weighted original",
        }
        owned = {}
        try:
            for key, path in targets.items():
                path.write_bytes(expected_report if key == "report" else expected_policies[key])
                owned[path] = runner._bundle_identity(path)
            runner._final_bundle_guard(targets, owned, expected_report, expected_policies)
            targets["river-weighted-raises"].write_bytes(b"late changed bytes")
            with self.assertRaisesRegex(RuntimeError, "bytes changed"):
                runner._final_bundle_guard(targets, owned, expected_report, expected_policies)
        finally:
            for path in targets.values():
                if path.exists():
                    path.unlink()
            directory.rmdir()


if __name__ == "__main__":
    unittest.main()
