"""Regression checks for the immutable four-policy held-out river artifact.

It only replays the published saved policies; it never calls a trainer or
production tree/evaluator helper.
"""
from __future__ import annotations

from contextlib import ExitStack
from fractions import Fraction
from scripts.historical_foundation_sources import historical_preflop_rank_source_matches

import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import benchmark_river_heldout_quality as runner


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "benchmarks" / "results" / "river-heldout-quality-v1"
EXPECTED_HEAD = "df02381625ce72d7922461b97d7c7d238258523e"
EXPECTED_REPORT_SHA256 = "5b26d6e9275b4962df4c67be1822594caa3d46291d196f863fe3b65f4353b578"
EXPECTED_CLAIM_SHA256 = "f9a6bdd53d71bb4a995e3c5be5be15faa6f25f7d145dcb75e04e76900256279c"
EXPECTED_POLICIES = {
    "policies/river-unpaired-blocker-tie-raise-materialized-cfrplus-10000.json":
        "f2e4e2d15ba9f2c65cb11e04ed2644196dd4b1df9ae03abff30a015f9f0e4cad",
    "policies/river-unpaired-blocker-tie-raise-matrix-free-cfrplus-10000.json":
        "ab9e7539cb4f424534c01a630a8f769a834273b286d258b820c976d7a41a5bc3",
    "policies/river-paired-short-spr-rank-extremes-materialized-cfrplus-10000.json":
        "81913dc5389c3f52a33fae67c40dc130c9768d8849835752ea087293b9381bfd",
    "policies/river-paired-short-spr-rank-extremes-matrix-free-cfrplus-10000.json":
        "c29c5a24f0b0a8e3f86849bc1792b2d422155aaa9b51c6815c36ae33b44c490e",
}
REQUIRED_SOURCE_LF_SHA256 = {
    "pokerlab/cards.py": "d748bc7960a3159ebe139b265782bcb3d5f065369951770c7928d6b5efeacadf",
    "pokerlab/river_config.py": "b4cff25ad217b3d0f472062ba062bf6e7fba2701ebdfd60e0632b4ecb5f2e9b3",
    "scripts/benchmark_river_heldout_quality.py": "1259777db93672f513d5a1f19f245996d692820370560746c4794b1a495a9587",
    "scripts/preflop_validation.py": "c4abe50a3f3ff814910ad2eaf653e6e2b29f7c31b28e6618f1718283794cfaa8",
    "scripts/river_heldout_preflight.py": "35216d3ca1ae60bdb8232783ed33917ef2a7bbb42ec8ae637981925328385a74",
    "scripts/turn_rational_certificate.py": "0c94bee344871a47d34a1291f65f85ac3e80a1a9389d7785e4baf6695b3967fb",
    "scripts/turn_river_validation.py": "779b8f1d47566e071d0ee24b82c99e79de46a0edcddbd43ecd08f4ee6e84c3c1",
}
EXPECTED_IDENTITIES = {
    (case["id"], backend, "cfrplus", 10_000)
    for case in runner.CASES
    for backend in runner.BACKENDS
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _as_fraction(value: str) -> Fraction:
    return Fraction(value)


class SavedHeldoutRiverArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report_path = ARTIFACT_ROOT / "report.json"
        claim_path = ARTIFACT_ROOT / "run-claim.json"
        status_path = ARTIFACT_ROOT / "run-status.json"
        cls.report_bytes = report_path.read_bytes()
        cls.claim_bytes = claim_path.read_bytes()
        cls.report = json.loads(cls.report_bytes.decode("utf-8"))
        cls.claim = json.loads(cls.claim_bytes.decode("utf-8"))
        cls.status = json.loads(status_path.read_text(encoding="utf-8"))
        cls.rows = cls.report["results"]
        cls.audits = {}

        # A saved-policy audit must remain independent of every solver/tree/
        # production evaluator entry point. _audit_policy builds only the
        # independent rules tree and calls the numeric and Fraction auditors.
        forbidden = (
            (runner, "solve_postflop"),
            (runner, "solve_matrix_free_river"),
            (runner.postflop_module, "_build_postflop_tree"),
            (runner.postflop_module, "train_public_batched"),
            (runner.postflop_module, "evaluate_profile"),
            (runner.matrix_free_module, "_build_tree"),
            (runner.matrix_free_module, "train_ranked_river"),
            (runner.matrix_free_module, "evaluate_ranked_profile"),
        )
        with ExitStack() as stack:
            for owner, name in forbidden:
                stack.enter_context(patch.object(
                    owner, name,
                    side_effect=AssertionError(f"forbidden production call: {name}"),
                ))
            for row in cls.rows:
                relative = row["policy_file"]
                raw = (ARTIFACT_ROOT / relative).read_bytes()
                policy = json.loads(raw.decode("utf-8"))
                case = runner._case_by_id(row["scenario"])
                cls.audits[(row["scenario"], row["backend"])] = (
                    raw, policy, runner._audit_policy(policy, case)
                )

    def test_report_claim_fixed_grid_and_all_target_misses_are_preserved(self):
        self.assertEqual(_sha256(self.report_bytes), EXPECTED_REPORT_SHA256)
        self.assertEqual(_sha256(self.claim_bytes), EXPECTED_CLAIM_SHA256)
        self.assertEqual(self.report["source_head"], EXPECTED_HEAD)
        self.assertEqual(self.claim["expected_source_commit"], EXPECTED_HEAD)
        self.assertEqual(self.report["claim_id"], self.claim["claim_id"])
        self.assertEqual(self.status["claim_id"], self.claim["claim_id"])
        self.assertEqual(self.status["status"], "completed")
        self.assertFalse(self.claim["retry_permitted"])
        self.assertTrue(self.claim["target_is_reporting_only"])
        self.assertFalse(self.status["retry_permitted"])
        self.assertEqual(self.report["benchmark_id"], "river-heldout-quality-v1")
        self.assertEqual(self.report["fixed_grid"]["algorithm"], "cfrplus")
        self.assertEqual(self.report["fixed_grid"]["iterations"], 10_000)
        self.assertEqual(self.report["fixed_grid"]["threshold_nash_conv_fraction"], "1/1000")
        self.assertTrue(self.report["fixed_grid"]["threshold_is_reporting_only"])
        self.assertEqual(
            {(row["scenario"], row["backend"], row["algorithm"], row["iterations"])
             for row in self.rows},
            EXPECTED_IDENTITIES,
        )
        self.assertEqual(
            {(row["scenario"], row["backend"], row["algorithm"], row["iterations"])
             for row in self.claim["profile_plan"]},
            EXPECTED_IDENTITIES,
        )
        self.assertEqual(len(self.rows), 4)
        self.assertEqual(len(self.claim["profile_plan"]), 4)
        self.assertTrue(all(row["target_met"] is False for row in self.rows))
        self.assertTrue(all(row["numeric_target_met"] is False for row in self.rows))
        self.assertTrue(all(row["exact_audit"]["status"] == "admitted" for row in self.rows))
        self.assertTrue(all(row["saved_reload_replay"] == "passed" for row in self.rows))

    def test_saved_policy_bytes_match(self):
        self.assertEqual(
            {row["policy_file"]: row["policy_sha256"] for row in self.rows},
            EXPECTED_POLICIES,
        )
        for row in self.rows:
            raw, policy, _audit = self.audits[(row["scenario"], row["backend"])]
            self.assertEqual(_sha256(raw), EXPECTED_POLICIES[row["policy_file"]])
            self.assertTrue(raw.endswith(b"\n"))
            self.assertNotIn(b"\r", raw)
            self.assertEqual(len(raw), row["policy_bytes"])
            self.assertEqual(policy["algorithm"], "cfrplus")
            self.assertEqual(policy["iterations"], 10_000)
            self.assertNotIn("convergence", policy)

    def test_reported_source_snapshot_is_complete_and_relevant_pins_match(self):
        snapshot = self.report["source_snapshot"]
        self.assertEqual(snapshot, self.report["source_sha256"])
        self.assertEqual(len(snapshot), 72)
        self.assertTrue({
            "pokerlab/cards.py", "scripts/turn_river_validation.py",
            "scripts/preflop_validation.py", "scripts/turn_rational_certificate.py",
            "scripts/river_heldout_preflight.py",
            "scripts/benchmark_river_heldout_quality.py",
        }.issubset(snapshot))
        for relative, expected_lf_digest in REQUIRED_SOURCE_LF_SHA256.items():
            entry = snapshot[relative]
            self.assertEqual(entry["normalized_lf_sha256"], expected_lf_digest, relative)
            current = (ROOT / relative).read_bytes()
            current_lf = current.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            self.assertTrue(_sha256(current_lf) == expected_lf_digest or
                            historical_preflop_rank_source_matches(ROOT / relative, expected_lf_digest), relative)

    def test_all_four_saved_profiles_replay_against_numeric_and_exact_auditors(self):
        for row in self.rows:
            key = (row["scenario"], row["backend"])
            _raw, policy, audit = self.audits[key]
            self.assertEqual(audit["worlds"], row["worlds"], key)
            self.assertEqual(audit["compatible_pairs"], row["compatible_pairs"], key)
            self.assertEqual(audit["information_sets"], row["information_sets"], key)
            self.assertEqual(audit["public_decision_nodes"], row["public_decision_nodes"], key)
            self.assertEqual(set(audit["metrics"]), set(runner.METRICS), key)
            self.assertEqual(set(audit["exact"]["metrics_fraction"]), set(runner.METRICS), key)
            for metric in runner.METRICS:
                self.assertLessEqual(
                    abs(audit["metrics"][metric] - row["metrics"][metric]), 1e-9,
                    f"{key}: numeric metric {metric}",
                )
            exact = audit["exact"]
            self.assertEqual(exact, row["exact_audit"], key)
            self.assertEqual(exact["status"], "admitted", key)
            self.assertEqual(exact["target_met"], row["target_met"], key)
            self.assertEqual(exact["nash_conv_target_fraction"], "1/1000", key)

            groupings = exact["chance_groupings"]
            self.assertEqual(set(groupings), {"scan", "partition"}, key)
            scan, partition = groupings["scan"], groupings["partition"]
            self.assertEqual(scan["metrics_fraction"], partition["metrics_fraction"], key)
            metrics = {name: _as_fraction(value)
                       for name, value in scan["metrics_fraction"].items()}
            lower = _as_fraction(exact["lower_value_bound_fraction"])
            upper = _as_fraction(exact["upper_value_bound_fraction"])
            self.assertEqual(lower, -metrics["ip_best_response_value"], key)
            self.assertEqual(upper, metrics["oop_best_response_value"], key)
            self.assertLessEqual(lower, metrics["value_oop"], key)
            self.assertLessEqual(metrics["value_oop"], upper, key)
            self.assertEqual(
                metrics["nash_conv"],
                metrics["oop_best_response_gain"] + metrics["ip_best_response_gain"],
                key,
            )
            self.assertEqual(metrics["exploitability"], metrics["nash_conv"] / 2, key)
            self.assertEqual(exact["target_met"], metrics["nash_conv"] <= Fraction(1, 1000), key)
            for mode, output in groupings.items():
                self.assertEqual(output["status"], "admitted", (key, mode))
                self.assertEqual(output["lower_value_bound_fraction"], str(lower), (key, mode))
                self.assertEqual(output["upper_value_bound_fraction"], str(upper), (key, mode))
                self.assertLessEqual(output["work"], output["work_limit"], (key, mode))
                self.assertLessEqual(output["tree_depth"], output["depth_limit"], (key, mode))
                self.assertLessEqual(
                    output["maximum_fraction_bits"], output["fraction_bit_limit"],
                    (key, mode),
                )
            case = runner._case_by_id(row["scenario"])
            self.assertEqual(policy["board"], list(runner.rules.cards(case["board"], 5)), key)


if __name__ == "__main__":
    unittest.main()
