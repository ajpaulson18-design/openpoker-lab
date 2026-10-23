"""Lifecycle, fixed-manifest, and exact-threshold regressions; no solver training."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid

from scripts import benchmark_river_heldout_quality as runner

EXPECTED_HEAD = "a" * 40


def _source_state(head=EXPECTED_HEAD, status="clean"):
    names = {
        "scripts/turn_river_validation.py", "scripts/preflop_validation.py",
        "scripts/turn_rational_certificate.py", runner.PREFLIGHT_RELATIVE,
        runner.PROTOCOL_RELATIVE, "scripts/benchmark_river_heldout_quality.py",
        "pokerlab/cards.py",
    }
    return {"head": head, "status": status, "files": {
        name: {"git_blob": "blob"} for name in names
    }}


def _plan():
    return ([{
        "scenario": case["id"], "backend": backend,
        "algorithm": runner.ALGORITHM, "iterations": runner.ITERATIONS,
        "preflight": {},
    } for case in runner.CASES for backend in runner.BACKENDS],
        {"schema": "river-heldout-quality-preflight-v1", "cases": [], "limits": {}})


def _audit(numeric_nc=0.0001, exact_target=False):
    metrics = {name: 0.0 for name in runner.METRICS}
    metrics["nash_conv"] = numeric_nc
    return {
        "metrics": metrics,
        "float_replay_differences": {name: 0.0 for name in runner.METRICS},
        "worlds": 10, "compatible_pairs": 10, "information_sets": 4,
        "public_decision_nodes": 8,
        "exact": {"status": "admitted", "target_met": exact_target,
                  "chance_groupings": {"scan": {}, "partition": {}}},
        "exact_vs_float_replay_differences": {name: 0.0 for name in runner.METRICS},
        "exact_vs_result_differences": {name: 0.0 for name in runner.METRICS},
    }


class HeldoutQualityRunnerTests(unittest.TestCase):
    def setUp(self):
        self.attempts = Path(tempfile.gettempdir()) / f".heldout-test-{uuid.uuid4().hex}"
        self.addCleanup(lambda: shutil.rmtree(self.attempts, ignore_errors=True))
        self.source_guard = lambda expected: _source_state(expected)
        self.preflight = lambda expected: _plan()

    def test_fixed_grid_and_limits_are_immutable(self):
        self.assertEqual([case["id"] for case in runner.CASES], [
            "river-unpaired-blocker-tie-raise",
            "river-paired-short-spr-rank-extremes",
        ])
        self.assertEqual(runner.ITERATIONS, 10_000)
        self.assertEqual(runner.TARGET_NASH_CONV.as_integer_ratio(), (1, 1000))
        self.assertEqual((runner.LIMITS["exact_work"], runner.LIMITS["exact_depth"],
                          runner.LIMITS["exact_fraction_bits"]), (100_000, 64, 65_536))

    def test_changed_range_or_config_with_same_case_id_rejects_before_solver(self):
        changed = copy.deepcopy(runner.CASES)
        changed[0]["oop"] = "AsTc:0.5,3c4c:0.25,9c9d:0.75,5c6c:0.5"
        called = []
        with patch.object(runner.preflight, "CASES", changed):
            with self.assertRaisesRegex(RuntimeError, "manifest"):
                runner._preflight_all()
        self.assertEqual(called, [])

    def test_preflight_all_four_precedes_first_solver_and_claim_is_exclusive(self):
        calls = []
        def solve(case, backend, iterations):
            calls.append((case["id"], backend, iterations))
            return {"scenario": case["id"], "backend": backend}
        with patch.object(runner, "_audit_policy", side_effect=lambda result, case: _audit()):
            report = runner.run_batch(
                self.attempts, EXPECTED_HEAD, solver=solve,
                source_guard=self.source_guard, preflight=self.preflight)
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(report["results"]), 4)
        self.assertTrue(all(row["numeric_target_met"] for row in report["results"]))
        self.assertTrue(all(row["target_met"] is False for row in report["results"]))
        for row in report["results"]:
            raw = (self.attempts / row["policy_file"]).read_bytes()
            self.assertTrue(raw.endswith(b"\n"))
            self.assertNotIn(b"\r", raw)
            self.assertEqual(runner._sha256(raw), row["policy_sha256"])
            self.assertEqual(row["saved_reload_replay"], "passed")
        with patch.object(runner, "_audit_policy", side_effect=lambda result, case: _audit()):
            with self.assertRaises(FileExistsError):
                runner.run_batch(self.attempts, EXPECTED_HEAD, solver=solve,
                                 source_guard=self.source_guard, preflight=self.preflight)
        self.assertEqual(len(calls), 4)

    def test_raw_policy_and_failure_receipt_survive_replay_rejection(self):
        calls = []
        with patch.object(runner, "_audit_policy", side_effect=ValueError("bad policy")):
            with self.assertRaisesRegex(ValueError, "bad policy"):
                runner.run_batch(
                    self.attempts, EXPECTED_HEAD,
                    solver=lambda *args: calls.append(args) or {"complete": True},
                    source_guard=self.source_guard, preflight=self.preflight)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(list((self.attempts / "policies").glob("*.json"))), 1)
        self.assertTrue((self.attempts / "failure.json").is_file())
        status = json.loads((self.attempts / "run-status.json").read_text())
        self.assertEqual(status["status"], "failed")
        self.assertFalse(status["retry_permitted"])

    def test_source_drift_after_call_preserves_policy_and_stops(self):
        drift = {"seen": False}
        calls = []
        def guard(expected):
            return _source_state(expected, "dirty" if drift["seen"] else "clean")
        def solve(case, backend, iterations):
            calls.append((case["id"], backend))
            drift["seen"] = True
            return {"complete": True}
        with self.assertRaisesRegex(RuntimeError, "Source, HEAD, or worktree state changed"):
            runner.run_batch(self.attempts, EXPECTED_HEAD, solver=solve,
                             source_guard=guard, preflight=self.preflight)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(list((self.attempts / "policies").glob("*.json"))), 1)
        self.assertFalse(json.loads((self.attempts / "failure.json").read_text())["retry_permitted"])

    def test_exact_capacity_is_the_only_admission_miss(self):
        self.assertTrue(runner._is_exact_capacity_error(
            "Exact rational certificate exceeds its work limit"))
        self.assertTrue(runner._is_exact_capacity_error(
            "Exact rational certificate exceeds the 65536-bit limit"))
        self.assertFalse(runner._is_exact_capacity_error("malformed policy"))

    def test_fresh_all_four_preflight_and_full_uniform_replay_without_training(self):
        with patch.object(runner, "solve_postflop", side_effect=AssertionError("training")), \
             patch.object(runner, "solve_matrix_free_river", side_effect=AssertionError("training")):
            plans, receipt = runner._preflight_all()
            self.assertEqual(len(plans), 4)
            self.assertEqual([row["compatible_physical_pairs"] for row in receipt["cases"]], [14, 15])
            for case in runner.CASES:
                board = runner.rules.cards(case["board"], 5)
                config = runner.RiverConfig.from_dict(case["config"])
                ranges = tuple(runner.rules.expand_range(case[side], board) for side in ("oop", "ip"))
                worlds, _ = runner.rules._worlds(board, ranges, None)
                root, _ = runner.preflight._build_tree(config)
                result, _, _ = runner.preflight._uniform_production_artifact(
                    case, board, root, worlds, config)
                result.update(runner.rules.replay_policy(
                    result, case["oop"], case["ip"], board=board, config=config))
                result.update(algorithm=runner.ALGORITHM, iterations=runner.ITERATIONS,
                              strategy_schema="postflop-strategy-v1")
                audit = runner._audit_policy(result, case)
                self.assertEqual(audit["exact"]["status"], "admitted")
                self.assertFalse(audit["exact"]["target_met"])
                self.assertEqual(set(audit["metrics"]), set(runner.METRICS))
                json.dumps(audit, allow_nan=False)
                for field in ("config", "river_config", "street_configs"):
                    altered = copy.deepcopy(result)
                    altered[field] = {}
                    with self.assertRaisesRegex(ValueError, "configuration differs"):
                        runner._audit_policy(altered, case)
                result["iterations"] = 10
                with self.assertRaisesRegex(ValueError, "fixed 10,000"):
                    runner._audit_policy(result, case)

    def test_source_authentication_catches_hidden_edits_and_inventory_changes(self):
        source = self.attempts / "source"
        source.mkdir(parents=True)
        names = _source_state()["files"]
        for name in names:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture\n")
        (source / ".gitignore").write_bytes(b"pokerlab/extra.py\n")

        def git(*args):
            return subprocess.check_output(["git", "-C", str(source), *args],
                                           stderr=subprocess.STDOUT, text=True).strip()

        git("init", "--quiet")
        git("add", ".")
        git("-c", "user.name=Solver Test", "-c", "user.email=solver-test@example.invalid",
            "commit", "--quiet", "-m", "Frozen fixture")
        expected = git("rev-parse", "HEAD")
        with patch.object(runner, "REPO_ROOT", source):
            state = runner._capture_source_state(expected)
            self.assertEqual(state["head"], expected)
            self.assertEqual(set(state["files"]), set(names))
            git("update-index", "--assume-unchanged", "pokerlab/cards.py")
            (source / "pokerlab/cards.py").write_bytes(b"hidden edit\n")
            with self.assertRaisesRegex(RuntimeError, "Working source differs"):
                runner._capture_source_state(expected)
            (source / "pokerlab/cards.py").write_bytes(b"fixture\n")
            (source / "pokerlab/extra.py").write_bytes(b"ignored module\n")
            with self.assertRaisesRegex(RuntimeError, "inventory differs"):
                runner._capture_source_state(expected)


if __name__ == "__main__":
    unittest.main()
