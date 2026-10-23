"""No-training regression checks for the fixed river-tail policy artifact."""
from __future__ import annotations

from contextlib import ExitStack
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import benchmark_river_heldout_tail as runner


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "benchmarks" / "results" / "river-heldout-tail-v1"
EXPECTED_HEAD = "74b8fa8adb13838401b06d203d597476eada4274"
EXPECTED_REPORT_SHA256 = "d19caa11eeb013f25287406af10888015d544cc534e70ff03c08d16a09e86acf"
EXPECTED_CLAIM_SHA256 = "0756292ab435d463bff02d88aa3fa0074ee6c32a5050332d7540babda55da3f9"
EXPECTED_STATUS_SHA256 = "41ee6302bced18023b4b7730fecedee67f33f5efe229aa2326ecf62812b6ae56"
EXPECTED_POLICIES = {
    "policies/river-unpaired-blocker-tie-raise-T10000-D5000.json":
        "f1a14a174b1e64558b60d413ff77e51e3ddd70889f3d704f2d570de4fd3b96fb",
    "policies/river-unpaired-blocker-tie-raise-T50000-D25000.json":
        "e4bc1aaa94f39e27d1e9121c8633c131c97f337787f98e8e5ec7695f7155cd86",
    "policies/river-paired-short-spr-rank-extremes-T10000-D5000.json":
        "c21b3be7a378746784a904bdc156250db3c0e529f4119c458011e79f5c9d4d32",
    "policies/river-paired-short-spr-rank-extremes-T50000-D25000.json":
        "189ffcb9ca10dcd9de38501c14f19e76d44846fae73786bd8aff64eafe039a4c",
}
REQUIRED_MATH_SOURCE_LF_SHA256 = {
    "docs/river-heldout-tail-protocol.md": "e2b1af0d7a59565564eefddc9108b3a72c4921a4e1501829de7a8d48ca777fea",
    "pokerlab/cards.py": "d748bc7960a3159ebe139b265782bcb3d5f065369951770c7928d6b5efeacadf",
    "pokerlab/river_config.py": "b4cff25ad217b3d0f472062ba062bf6e7fba2701ebdfd60e0632b4ecb5f2e9b3",
    "pokerlab/river_tail_adapter.py": "0963a8df65d432415157a164618923bd2fcfede98ef0ed328ea8f1867e384e7d",
    "scripts/benchmark_river_heldout_quality.py":
        "1259777db93672f513d5a1f19f245996d692820370560746c4794b1a495a9587",
    "scripts/benchmark_river_heldout_tail.py":
        "da2436a86e12b16684b8d4c26d59be77c0a8f2e6cb74fcbbe9c790d7da993d3b",
    "scripts/preflop_validation.py": "c4abe50a3f3ff814910ad2eaf653e6e2b29f7c31b28e6618f1718283794cfaa8",
    "scripts/river_heldout_preflight.py":
        "35216d3ca1ae60bdb8232783ed33917ef2a7bbb42ec8ae637981925328385a74",
    "scripts/turn_rational_certificate.py":
        "0c94bee344871a47d34a1291f65f85ac3e80a1a9389d7785e4baf6695b3967fb",
    "scripts/turn_river_validation.py":
        "779b8f1d47566e071d0ee24b82c99e79de46a0edcddbd43ecd08f4ee6e84c3c1",
}
EXPECTED_IDENTITIES = {
    (case_id, iterations, discard)
    for case_id, iterations, discard in runner.GRID
}
TARGET = Fraction(1, 1000)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _lf(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _json_bytes(value) -> bytes:
    return runner._json_bytes(value)


class SavedHeldoutTailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report_raw = (ARTIFACT / "report.json").read_bytes()
        cls.claim_raw = (ARTIFACT / "run-claim.json").read_bytes()
        cls.status_raw = (ARTIFACT / "run-status.json").read_bytes()
        cls.report = json.loads(cls.report_raw.decode("utf-8"))
        cls.claim = json.loads(cls.claim_raw.decode("utf-8"))
        cls.status = json.loads(cls.status_raw.decode("utf-8"))
        cls.rows = cls.report["results"]
        cls.policies = {}
        cls.replays = {}

        # The independent audit may construct its own public tree and exact
        # rules model, but must never invoke a production solver/tree/evaluator.
        forbidden = (
            (runner, "_solve"),
            (runner, "_case_preflight"),
            (runner, "_preflight_all"),
            (runner.postflop, "_enumerate_worlds"),
            (runner.postflop, "_build_postflop_tree"),
            (runner.postflop, "_prefix_hand_index"),
            (runner.postflop, "solve_postflop"),
            (runner.postflop, "train_public_batched"),
            (runner.postflop, "evaluate_profile"),
            (runner.postflop, "best_response"),
            (runner.public_cfr, "train_ranked_river"),
            (runner.public_cfr, "train_public_batched"),
            (runner.tail, "solve_river_tail"),
            (runner.tail, "_enumerate_worlds"),
            (runner.tail, "_build_postflop_tree"),
            (runner.tail, "_train_original_weight_tail"),
            (runner.tail, "evaluate_profile"),
        )
        with ExitStack() as stack:
            for owner, name in forbidden:
                stack.enter_context(patch.object(
                    owner, name,
                    side_effect=AssertionError(f"forbidden production call: {name}"),
                ))
            for row in cls.rows:
                relative = row["policy_file"]
                raw = (ARTIFACT / relative).read_bytes()
                policy = json.loads(raw.decode("utf-8"))
                identity = (row["scenario"], row["iterations"], row["discard"])
                case = runner.base._case_by_id(row["scenario"])
                preflight = row["preflight"]
                cls.policies[relative] = (raw, policy)
                cls.replays[identity] = runner._tail_audit_policy(
                    policy, case, row["iterations"], row["discard"],
                    preflight=preflight,
                )

    def test_pinned_claim_report_status_and_fixed_schedule(self):
        self.assertEqual(_sha(self.report_raw), EXPECTED_REPORT_SHA256)
        self.assertEqual(_sha(self.claim_raw), EXPECTED_CLAIM_SHA256)
        self.assertEqual(_sha(self.status_raw), EXPECTED_STATUS_SHA256)
        self.assertEqual(self.report["source_head"], EXPECTED_HEAD)
        self.assertEqual(self.claim["expected_source_commit"], EXPECTED_HEAD)
        self.assertEqual(self.report["benchmark_id"], "river-heldout-tail-v1")
        self.assertEqual(self.claim["benchmark_id"], self.report["benchmark_id"])
        self.assertEqual(self.status["status"], "completed")
        self.assertEqual(self.report["status"], "completed")
        self.assertEqual(self.status["claim_id"], self.claim["claim_id"])
        self.assertEqual(self.report["claim_id"], self.claim["claim_id"])
        self.assertFalse(self.claim["retry_permitted"])
        self.assertFalse(self.status["retry_permitted"])
        self.assertTrue(self.claim["target_is_reporting_only"])
        self.assertEqual(self.claim["target_nash_conv_fraction"], "1/1000")
        self.assertEqual(self.claim["baseline_report_sha256"],
                         runner.BASELINE_REPORT_SHA256)
        self.assertEqual(self.report["fixed_grid"]["threshold_nash_conv_fraction"], "1/1000")
        self.assertTrue(self.report["fixed_grid"]["threshold_is_reporting_only"])
        self.assertEqual(self.report["fixed_grid"]["algorithm"], "cfrplus")
        self.assertEqual(self.claim["fixed_grid"], [
            runner._identity(*identity) for identity in runner.GRID
        ])
        self.assertEqual(self.report["fixed_grid"]["calls"], self.claim["fixed_grid"])
        runner._validate_preflight_receipt(self.report["preflight"])
        self.assertEqual([row["preflight"] for row in self.rows],
                         self.report["preflight"]["tail_calls"])
        identities = {(row["scenario"], row["iterations"], row["discard"])
                      for row in self.rows}
        self.assertEqual(identities, EXPECTED_IDENTITIES)
        self.assertEqual(len(self.rows), 4)
        self.assertEqual(self.status["completed_profiles"],
                         [row["policy_file"] for row in self.rows])

    def test_saved_policy_hashes_bytes_and_tail_schedule(self):
        self.assertEqual({row["policy_file"]: row["policy_sha256"] for row in self.rows},
                         EXPECTED_POLICIES)
        for row in self.rows:
            identity = (row["scenario"], row["iterations"], row["discard"])
            relative = row["policy_file"]
            raw, policy = self.policies[relative]
            self.assertEqual(_sha(raw), EXPECTED_POLICIES[relative])
            self.assertEqual(len(raw), row["policy_bytes"])
            self.assertTrue(raw.endswith(b"\n"))
            self.assertNotIn(b"\r", raw)
            self.assertEqual(raw, _json_bytes(policy))
            self.assertEqual(policy["algorithm"], "cfrplus")
            self.assertEqual(policy["iterations"], row["iterations"])
            self.assertEqual(policy["requested_iterations"], row["iterations"])
            self.assertEqual(policy["discard"], row["discard"])
            self.assertEqual(policy["source_iteration_window"],
                             [row["discard"] + 1, row["iterations"]])
            self.assertEqual(row["source_iteration_window"],
                             [row["discard"] + 1, row["iterations"]])
            expected_weight = (row["iterations"] * (row["iterations"] + 1) -
                               row["discard"] * (row["discard"] + 1)) // 2
            self.assertEqual(policy["average_weight_sum"], expected_weight)
            self.assertEqual(row["average_weight_sum"], expected_weight)
            self.assertEqual(policy["averaged_sweeps"],
                             row["iterations"] - row["discard"])
            self.assertEqual(row["saved_reload_replay"], "passed")
            self.assertNotIn("convergence", policy)
            self.assertIn(identity, self.replays)

    def test_relevant_source_snapshot_math_helpers_and_tail_adapter_are_pinned(self):
        snapshot = self.report["source_state"]["base"]["files"]
        extension = self.report["source_state"]["extension"]
        self.assertEqual(len(snapshot), 72)
        self.assertEqual(len(extension), 2)
        self.assertEqual(self.report["source_state"]["head"], EXPECTED_HEAD)
        self.assertEqual(extension[
            "scripts/benchmark_river_heldout_tail.py"]["normalized_lf_sha256"],
            REQUIRED_MATH_SOURCE_LF_SHA256["scripts/benchmark_river_heldout_tail.py"])
        self.assertIn("docs/river-heldout-tail-protocol.md", extension)
        for relative, expected_lf_hash in REQUIRED_MATH_SOURCE_LF_SHA256.items():
            source_map = extension if relative in extension else snapshot
            self.assertIn(relative, source_map, relative)
            self.assertEqual(source_map[relative]["normalized_lf_sha256"],
                             expected_lf_hash, relative)
            current = (ROOT / relative).read_bytes()
            self.assertEqual(_sha(_lf(current)), expected_lf_hash, relative)

    def test_four_policies_replay_with_independent_numeric_and_fraction_auditors(self):
        self.assertEqual(len(self.replays), 4)
        misses = []
        meets = []
        for row in self.rows:
            key = (row["scenario"], row["iterations"], row["discard"])
            replay = self.replays[key]
            self.assertEqual(replay["worlds"], row["worlds"], key)
            self.assertEqual(replay["compatible_pairs"], row["compatible_pairs"], key)
            self.assertEqual(replay["information_sets"], row["information_sets"], key)
            self.assertEqual(replay["public_decision_nodes"],
                             row["public_decision_nodes"], key)
            self.assertEqual(set(replay["metrics"]), set(runner.base.METRICS), key)
            self.assertEqual(set(replay["exact_audit"]["metrics_fraction"]),
                             set(runner.base.METRICS), key)
            self.assertEqual(replay["exact_audit"], row["exact_audit"], key)
            self.assertEqual(replay["exact_vs_result_differences"],
                             row["exact_vs_result_differences"], key)
            self.assertEqual(replay["exact_vs_numeric_differences"],
                             row["exact_vs_numeric_differences"], key)
            self.assertTrue(all(abs(replay["numeric_differences"][name]) <= 1e-9
                                for name in runner.base.METRICS), key)
            for name in runner.base.METRICS:
                self.assertLessEqual(abs(replay["metrics"][name] - row["metrics"][name]),
                                     1e-9, (key, name))
            exact = replay["exact_audit"]
            self.assertEqual(exact["status"], "admitted", key)
            groupings = exact["chance_groupings"]
            self.assertEqual(set(groupings), {"scan", "partition"}, key)
            scan = groupings["scan"]
            partition = groupings["partition"]
            self.assertEqual(scan["metrics_fraction"],
                             partition["metrics_fraction"], key)
            metrics = {name: Fraction(value)
                       for name, value in scan["metrics_fraction"].items()}
            lower = Fraction(exact["lower_value_bound_fraction"])
            upper = Fraction(exact["upper_value_bound_fraction"])
            self.assertEqual(lower, -metrics["ip_best_response_value"], key)
            self.assertEqual(upper, metrics["oop_best_response_value"], key)
            self.assertLessEqual(lower, metrics["value_oop"], key)
            self.assertLessEqual(metrics["value_oop"], upper, key)
            self.assertEqual(metrics["value_ip"], -metrics["value_oop"], key)
            self.assertEqual(metrics["oop_best_response_gain"],
                             upper - metrics["value_oop"], key)
            self.assertEqual(metrics["ip_best_response_gain"],
                             metrics["value_oop"] - lower, key)
            self.assertEqual(metrics["nash_conv"], upper - lower, key)
            self.assertEqual(metrics["nash_conv"],
                             metrics["oop_best_response_gain"] +
                             metrics["ip_best_response_gain"], key)
            self.assertEqual(metrics["exploitability"], metrics["nash_conv"] / 2, key)
            exact_met = metrics["nash_conv"] <= TARGET
            self.assertEqual(exact["target_met"], exact_met, key)
            self.assertEqual(row["exact_target_met"], exact_met, key)
            self.assertEqual(row["numeric_target_met"],
                             replay["numeric_target_met"], key)
            if exact_met:
                meets.append(key)
            else:
                misses.append(key)
            if exact["status"] == "admitted":
                for mode in ("scan", "partition"):
                    summary = groupings[mode]
                    self.assertLessEqual(summary["work"], summary["work_limit"],
                                         (key, mode))
                    self.assertLessEqual(summary["tree_depth"], summary["depth_limit"],
                                         (key, mode))
                    self.assertLessEqual(summary["maximum_fraction_bits"],
                                         summary["fraction_bit_limit"], (key, mode))

        self.assertEqual(len(meets), 2)
        self.assertEqual(len(misses), 2)
        self.assertEqual({key[1] for key in meets}, {50_000})
        self.assertEqual({key[1] for key in misses}, {10_000})


if __name__ == "__main__":
    unittest.main()
