"""Short tests for the fixed river-tail wrapper; solver calls are synthetic."""
from __future__ import annotations

import copy
from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import unittest
import uuid
from unittest.mock import patch

from scripts import benchmark_river_heldout_quality as base
from scripts import benchmark_river_heldout_tail as study
from scripts import turn_river_validation as rules
from pokerlab import river_tail_adapter as tail


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "benchmarks" / "results" / "river-heldout-quality-v1"


def _uniform_policy(case, iterations, discard):
    suffix = "materialized-cfrplus-10000.json"
    path = next((BASELINE / "policies").glob(f"{case['id']}-{suffix}"))
    result = json.loads(path.read_text(encoding="utf-8"))
    for row in result["strategy"]:
        probability = 1.0 / len(row["actions"])
        for action in row["actions"]:
            action["probability"] = probability
    result.update({
        "iterations": iterations, "requested_iterations": iterations,
        "discard": discard, "source_iteration_window": [discard + 1, iterations],
        "averaged_sweeps": iterations - discard,
        "average_weight_sum": (iterations * (iterations + 1) - discard * (discard + 1)) // 2,
        "average_schedule": "direct-original-linear-sweep-weight-own-reach-tail",
        "requested_regret_passes": 2 * iterations,
        "requested_average_passes": iterations - discard,
        "requested_total_traversal_passes": 3 * iterations - discard,
        "solver_version": (tail.SOLVER_VERSION if iterations <= tail.STANDARD_MAX_ITERATIONS
                           else tail.LONG_SOLVER_VERSION),
        "training_calls": 1,
    })
    preflight = study._case_preflight(case, iterations, discard)
    counts, limits = preflight["counts_and_work"], preflight["limits"]
    result.update({
        "deals": counts["compatible_pairs"],
        "compatible_pairs": counts["compatible_pairs"],
        "worlds": counts["worlds"], "worlds_materialized": counts["worlds"],
        "info_sets": counts["information_sets"],
        "public_nodes": counts["public_nodes"],
        "public_states": counts["public_states"],
        "terminal_nodes": counts["terminal_nodes"],
        "chance_nodes": counts["chance_nodes"],
        "world_traversal_nodes": counts["world_traversal_nodes"],
        "tree_actions": counts["tree_actions"],
        "public_state_limit": limits["public_states"],
        "public_node_limit": limits["public_nodes"],
        "public_batch_edge_limit": limits["prefix_hand_edges"],
        "resource_usage": {
            "full_requested_world_node_work": counts["world_node_work"],
            "full_requested_world_node_work_limit": limits["world_node_work"],
            "full_requested_dense_hand_state_pass_work": counts["dense_hand_state_pass_work"],
            "full_requested_dense_hand_state_pass_work_limit": limits["dense_hand_state_pass_work"],
            "info_action_slots": counts["info_action_slots"],
            "info_action_slots_limit": limits["info_action_slots"],
            "prefix_hand_edges": counts["prefix_hand_edges"],
            "prefix_hand_edge_limit": limits["prefix_hand_edges"],
        },
    })
    board = rules.cards(case["board"], 5)
    oracle = rules.replay_policy(result, case["oop"], case["ip"], board=board,
                                 config=base.RiverConfig.from_dict(case["config"]))
    for metric in base.METRICS:
        result[metric] = float(oracle[metric])
    return result


class RiverTailWrapperTests(unittest.TestCase):
    def test_fixed_schedule_and_exact_original_weight_windows(self):
        self.assertEqual(study.GRID, (
            (base.CASES[0]["id"], 10_000, 5_000),
            (base.CASES[0]["id"], 50_000, 25_000),
            (base.CASES[1]["id"], 10_000, 5_000),
            (base.CASES[1]["id"], 50_000, 25_000),
        ))
        self.assertEqual(study.TARGET, base.TARGET_NASH_CONV)
        self.assertEqual(
            (37_502_500, 937_512_500),
            tuple((t * (t + 1) - d * (d + 1)) // 2
                  for t, d in ((10_000, 5_000), (50_000, 25_000))),
        )

    def test_fresh_no_training_preflight_admits_all_four_with_full_budget_caps(self):
        receipt = study._preflight_all()
        calls = receipt["tail_calls"]
        self.assertEqual(len(calls), 4)
        by_identity = {
            (row["identity"]["scenario"], row["identity"]["iterations"]): row
            for row in calls
        }
        self.assertEqual(set(by_identity), {
            (case["id"], t) for case in base.CASES for t in (10_000, 50_000)
        })
        for case in base.CASES:
            entry = by_identity[(case["id"], 50_000)]
            row, limits = entry["counts_and_work"], entry["limits"]
            self.assertEqual(row["candidate_hand_pair_iterations"], 800_000)
            self.assertEqual(row["world_iterations"],
                             700_000 if case is base.CASES[0] else 750_000)
            self.assertEqual(row["world_node_work"],
                             21_000_000 if case is base.CASES[0] else 22_500_000)
            self.assertEqual(row["dense_hand_state_pass_work"], 16_200_324)
            for resource in (
                "candidate_hand_pair_iterations", "world_iterations", "world_node_work",
                "dense_hand_state_pass_work", "info_action_slots", "prefix_hand_edges",
                "public_states", "public_nodes",
            ):
                self.assertLessEqual(row[resource], limits[resource], resource)
            self.assertEqual(row["total_traversal_passes"], 125_000)

    def test_baseline_source_compatibility_accepts_line_endings_but_rejects_math_drift(self):
        historical = {
            "scripts/turn_river_validation.py": {
                "bytes": 10, "raw_sha256": "old-raw",
                "normalized_lf_sha256": "same-lf", "git_blob": "same-blob",
            },
        }
        current = {
            "scripts/turn_river_validation.py": {
                "bytes": 12, "raw_sha256": "new-crlf-raw",
                "normalized_lf_sha256": "same-lf", "git_blob": "same-blob",
            },
            "scripts/new_unrelated.py": {"normalized_lf_sha256": "new", "git_blob": "new"},
        }
        study._assert_baseline_sources_compatible(historical, current)
        changed = dict(current)
        changed["scripts/turn_river_validation.py"] = {
            **current["scripts/turn_river_validation.py"],
            "normalized_lf_sha256": "changed-lf",
        }
        with self.assertRaisesRegex(RuntimeError, "source changed"):
            study._assert_baseline_sources_compatible(historical, changed)

    def test_frozen_v1_inputs_are_pinned_as_a_complete_replay_set(self):
        pins = study._baseline_inputs_pin()
        self.assertEqual(pins["report_sha256"], study.BASELINE_REPORT_SHA256)
        self.assertEqual(pins["claim_sha256"], study.BASELINE_CLAIM_SHA256)
        self.assertEqual(pins["status_sha256"], study.BASELINE_STATUS_SHA256)
        self.assertEqual(pins["policy_sha256"], study.BASELINE_POLICIES)

    def test_tail_auditor_accepts_synthetic_uniform_rows_and_rejects_wrong_window(self):
        case = base.CASES[0]
        policy = _uniform_policy(case, 50_000, 25_000)
        preflight = study._case_preflight(case, 50_000, 25_000)
        audit = study._tail_audit_policy(policy, case, 50_000, 25_000,
                                         preflight=preflight)
        self.assertEqual(set(audit["metrics"]), set(base.METRICS))
        self.assertIn(audit["exact_audit"]["status"], ("admitted",))
        self.assertEqual(audit["exact_target_met"], audit["exact_audit"]["target_met"])
        bad = dict(policy)
        bad["source_iteration_window"] = [25_000, 50_000]
        with patch.object(rules, "replay_policy",
                          side_effect=AssertionError("metadata must fail before replay")):
            with self.assertRaisesRegex(ValueError, "source_iteration_window"):
                study._tail_audit_policy(bad, case, 50_000, 25_000,
                                         preflight=preflight)

    def test_exact_capacity_miss_is_retained_as_unknown_not_discarded(self):
        case = base.CASES[0]
        policy = _uniform_policy(case, 50_000, 25_000)
        preflight = study._case_preflight(case, 50_000, 25_000)
        rejected = {
            "status": "admission-rejected", "chance_groupings": {
                "scan": {"status": "admission-rejected", "reason": "work cap"},
                "partition": {"status": "admission-rejected", "reason": "work cap"},
            },
            "metrics_fraction": None, "target_met": None,
        }
        with patch.object(base, "_exact_result", return_value=(rejected, {})):
            audit = study._tail_audit_policy(policy, case, 50_000, 25_000,
                                             preflight=preflight)
        self.assertEqual(audit["exact_audit"], rejected)
        self.assertIsNone(audit["exact_target_met"])
        self.assertIsNone(audit["exact_vs_numeric_differences"])
        self.assertIsInstance(audit["numeric_target_met"], bool)

    def test_bad_four_call_preflight_fails_before_claim_or_solver(self):
        state = {"head": "0" * 40, "base": {}, "extension": {}}
        calls = []
        receipt = {"tail_calls": [
            {"identity": study._identity(*row), "admitted": True,
             "counts_and_work": {}, "limits": {}}
            for row in study.GRID
        ]}
        receipt["tail_calls"][2]["admitted"] = False
        out = ROOT.parent / ("tail-wrapper-preflight-failure-" + uuid.uuid4().hex)
        with self.assertRaisesRegex(RuntimeError, "All four"):
            study.run_batch(
                out, "0" * 40, _source_guard=lambda _commit: state,
                _baseline_check_fn=lambda _state: {"profiles_replayed": 4},
                _preflight_fn=lambda: receipt,
                _solver=lambda *args: calls.append(args),
            )
        self.assertEqual(calls, [])
        self.assertFalse(out.exists())

    def test_malformed_resource_receipts_fail_before_claim_or_training(self):
        admitted = study._preflight_all()
        state = {"head": "0" * 40, "base": {}, "extension": {}}
        for resource, limit in admitted["tail_calls"][0]["limits"].items():
            for invalid in (None, -1, True, limit + 1):
                with self.subTest(resource=resource, invalid=invalid):
                    receipt = copy.deepcopy(admitted)
                    counts = receipt["tail_calls"][0]["counts_and_work"]
                    if invalid is None:
                        del counts[resource]
                    else:
                        counts[resource] = invalid
                    out = ROOT.parent / ("tail-wrapper-resource-reject-" + uuid.uuid4().hex)
                    with self.assertRaisesRegex(RuntimeError, "Preflight resource"):
                        study.run_batch(
                            out, "0" * 40, _source_guard=lambda _commit: state,
                            _baseline_check_fn=lambda _state: {"profiles_replayed": 4},
                            _preflight_fn=lambda: receipt,
                            _solver=lambda *args: self.fail("Rejected resources reached training"),
                        )
                    self.assertFalse(out.exists())

    def test_saved_tail_audit_needs_no_production_helpers_and_binds_identity(self):
        case = base.CASES[0]
        policy = _uniform_policy(case, 50_000, 25_000)
        preflight = study._case_preflight(case, 50_000, 25_000)
        with ExitStack() as stack:
            for owner, name in (
                (study.postflop, "_enumerate_worlds"),
                (study.postflop, "_build_postflop_tree"),
                (study.tail, "solve_river_tail"),
                (study.public_cfr, "_validate_inputs"),
                (study.public_cfr, "_aggregate_prefixes"),
                (study, "_case_preflight"),
            ):
                stack.enter_context(patch.object(
                    owner, name, side_effect=AssertionError("Production helper reached saved replay")))
            audit = study._tail_audit_policy(policy, case, 50_000, 25_000,
                                             preflight=preflight)
            self.assertEqual(set(audit["exact_vs_result_differences"]), set(base.METRICS))
            wrong = copy.deepcopy(preflight)
            wrong["identity"]["discard"] = 5_000
            with patch.object(rules, "replay_policy", side_effect=AssertionError("Wrong identity reached replay")):
                with self.assertRaisesRegex(ValueError, "Preflight identity"):
                    study._tail_audit_policy(policy, case, 50_000, 25_000,
                                             preflight=wrong)

    def test_mock_batch_saves_before_audit_and_keeps_all_four_profiles(self):
        calls = []
        state = {"head": "0" * 40, "base": {}, "extension": {}}
        preflight = study._preflight_all()

        def solver(case, iterations, discard):
            calls.append((case["id"], iterations, discard))
            return _uniform_policy(case, iterations, discard)

        out = ROOT.parent / ("tail-wrapper-success-" + uuid.uuid4().hex)
        try:
            report = study.run_batch(
                out, "0" * 40, _source_guard=lambda _commit: state,
                _baseline_check_fn=lambda _state: {"profiles_replayed": 4},
                _preflight_fn=lambda: preflight, _solver=solver,
            )
            self.assertEqual(calls, list(study.GRID))
            self.assertEqual(len(report["results"]), 4)
            self.assertTrue(all(row["saved_reload_replay"] == "passed"
                                for row in report["results"]))
            self.assertTrue((out / "run-claim.json").is_file())
            self.assertEqual(json.loads((out / "run-status.json").read_text())[
                "status"], "completed")
        finally:
            resolved = out.resolve()
            if resolved.parent == ROOT.parent.resolve() and resolved.name.startswith("tail-wrapper-success-") and resolved.exists():
                shutil.rmtree(resolved)

    def test_partial_failure_is_retained_and_same_attempt_cannot_retry(self):
        calls = []
        state = {"head": "0" * 40, "base": {}, "extension": {}}
        preflight = study._preflight_all()

        def solver(case, iterations, discard):
            calls.append((case["id"], iterations, discard))
            if len(calls) == 2:
                raise RuntimeError("synthetic stop after first saved profile")
            return _uniform_policy(case, iterations, discard)

        out = ROOT.parent / ("tail-wrapper-failure-" + uuid.uuid4().hex)
        try:
            kwargs = dict(
                _source_guard=lambda _commit: state,
                _baseline_check_fn=lambda _state: {"profiles_replayed": 4},
                _preflight_fn=lambda: preflight, _solver=solver,
            )
            with self.assertRaisesRegex(RuntimeError, "synthetic stop"):
                study.run_batch(out, "0" * 40, **kwargs)
            status = json.loads((out / "run-status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "failed")
            self.assertFalse(status["retry_permitted"])
            self.assertEqual(len(status["completed_profiles"]), 1)
            failure = json.loads((out / "failure.json").read_text(encoding="utf-8"))
            self.assertEqual(failure["saved_policy_files"], [
                "river-unpaired-blocker-tie-raise-T10000-D5000.json"
            ])
            first_policy = out / status["completed_profiles"][0]
            self.assertTrue(first_policy.is_file())
            saved = json.loads(first_policy.read_text(encoding="utf-8"))
            self.assertEqual(saved["discard"], 5_000)
            with self.assertRaises(FileExistsError):
                study.run_batch(out, "0" * 40, **kwargs)
            self.assertEqual(len(calls), 2)
        finally:
            resolved = out.resolve()
            if resolved.parent == ROOT.parent.resolve() and resolved.name.startswith("tail-wrapper-failure-") and resolved.exists():
                shutil.rmtree(resolved)


if __name__ == "__main__":
    unittest.main()
