"""Saved-policy conformance checks for the compiled fixed-river controls.

This module reloads only immutable policies and audits them with the independent
physical/numeric/exact validators. It never runs either trainer or the native
executable.
"""
from __future__ import annotations

from contextlib import ExitStack
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "benchmarks" / "results" / "native-river-controls-v1"
RUNNER_PATH = ARTIFACT_ROOT / "validate_compiled_river.py"
EXPECTED_SOURCE_HEAD = "e537ec82b756b3e69d87a3b4f574d7eda8becc4f"
EXPECTED_CLAIM_ID = "29f643a2201dd16cf93a6fbba487a362"
EXPECTED_REPORT_SHA256 = "a731d45d9356158eb2711ebf734616c05b174abb236c85406f0e65b87b8c6444"
EXPECTED_CLAIM_SHA256 = "7661066e157f285d49a52c8a6b25a14b3eed97cc6b313a7a38220c1f91e64172"
EXPECTED_STATUS_SHA256 = "831599649628f7068489821f041c7f9a6c1c56db14a6a7e4b7d93fe3cf258961"
EXPECTED_RUNNER_SHA256 = "a4155547d39b49c65a7fcb3b22a0ee5ce751de17a6183026ee713f62f88203b6"
EXPECTED_POLICIES = {
    "policies/river-unpaired-blocker-tie-raise-native-T10.json":
        "8a4228ae64ab93d59d80fc46c769d656ebd09dadef476969538890d60a3d3e8e",
    "policies/river-unpaired-blocker-tie-raise-python-T10.json":
        "e67e6d39e91c3c5e9697a89604232eb5ddd8fa6296f37b89bc06f6727cad8f13",
    "policies/river-unpaired-blocker-tie-raise-native-T100.json":
        "c5a96292535b6f81f602fa34dc58bdeb25dc257c0f2cf6aaf7d143c863f42b74",
    "policies/river-unpaired-blocker-tie-raise-python-T100.json":
        "b6df5e6f36a4d6d6505c8a71ec22818a4ee673903aa8bcb15d660e76ca65166b",
    "policies/river-paired-short-spr-rank-extremes-native-T10.json":
        "5360af2802868600067ab311f2dfc986d1e928673a2a1c1fae18a7dc4e5a5ed4",
    "policies/river-paired-short-spr-rank-extremes-python-T10.json":
        "c68fc5815d31dcb5d52f1d2eedaa20ad79564995acd6f841ddcb126e833339a2",
    "policies/river-paired-short-spr-rank-extremes-native-T100.json":
        "f82328492134bd6e9f8019036c38c1a5a7b54860e359d72a4df2624ba8026310",
    "policies/river-paired-short-spr-rank-extremes-python-T100.json":
        "7235d9099609f007753e82c6b6d8563b51318004b6885a869bff46ef929bff56",
    "policies/river-weighted-8x8-blocker-tie-short-refund-native-T10.json":
        "5c160d696f60ef00bbf4727f1b8922d36766aecf69b971213c2f69f7626094be",
    "policies/river-weighted-8x8-blocker-tie-short-refund-python-T10.json":
        "f0dc9f91be0b189cb31d1f4309a70bb0581abdb88ad32306a39445b121567291",
    "policies/river-weighted-8x8-blocker-tie-short-refund-native-T100.json":
        "804932c13675fd3fb2febc05c90688e00648b4ce61928832271cf4055c08a3d2",
    "policies/river-weighted-8x8-blocker-tie-short-refund-python-T100.json":
        "4ef1389b48a279bdea482e57fa6ae5d9a0258d0acf48db48399d4479cf62e100",
    "policies/river-royal-flush-tie-anchor-native-T10.json":
        "e1d5a96d56d173e8b6f7dbc5f562955f1e96a6658cb8586735bfc8c07694f88d",
    "policies/river-royal-flush-tie-anchor-python-T10.json":
        "1ec0238abaa571d6308388db6d13b3c45a63ee112bb46865a037b2f68244e70d",
    "policies/river-royal-flush-tie-anchor-native-T100.json":
        "e466946a20aa944fc5a20b6e08cafb901c7c0b959897c9dcc5a25bc206ab21e1",
    "policies/river-royal-flush-tie-anchor-python-T100.json":
        "a0f99f28583b197a791d2024523bed08a6470c7bd3c9b53530ab4487ead3551b",
}
REQUIRED_SOURCE_LF_SHA256 = {
    "pokerlab/cards.py": "d748bc7960a3159ebe139b265782bcb3d5f065369951770c7928d6b5efeacadf",
    "pokerlab/river_config.py": "b4cff25ad217b3d0f472062ba062bf6e7fba2701ebdfd60e0632b4ecb5f2e9b3",
    "pokerlab/native_river_solver.py": "db54f4339319cddf83eb8ccb6c6e98d2fb566d70a72623939504d57e60b22e86",
    "scripts/turn_river_validation.py": "779b8f1d47566e071d0ee24b82c99e79de46a0edcddbd43ecd08f4ee6e84c3c1",
    "scripts/preflop_validation.py": "c4abe50a3f3ff814910ad2eaf653e6e2b29f7c31b28e6618f1718283794cfaa8",
    "scripts/turn_rational_certificate.py": "0c94bee344871a47d34a1291f65f85ac3e80a1a9389d7785e4baf6695b3967fb",
    "scripts/benchmark_river_heldout_quality.py": "1259777db93672f513d5a1f19f245996d692820370560746c4794b1a495a9587",
}
BUILD_MANIFEST_SHA256 = "8046b7e7e85a3d2acff3d8e3c33dfd646dff23739d6bd929167994f34e4c8a7d"
BUILD_EXE_SHA256 = "d8f21a4598c65ef31770ab1ba44439510d122abb5fcc19800ac38bf5ef737bbc"
NATIVE_SOURCE_SHA256 = "2c1c31328b61306c7ae90512f2e4e7e1bdfd00cd23fc5d8dc50fffcba5b09b29"
NATIVE_SOURCE_LF_SHA256 = "5101bee03f7fd9d6d1b7cac8ea825144cd1a2471179de909ab22358264821676"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fraction(value) -> Fraction:
    return Fraction(str(value))


def _load_runner():
    spec = importlib.util.spec_from_file_location("saved_native_river_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the retained native conformance runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SavedNativeRiverControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report_raw = (ARTIFACT_ROOT / "report.json").read_bytes()
        cls.claim_raw = (ARTIFACT_ROOT / "claim.json").read_bytes()
        cls.status_raw = (ARTIFACT_ROOT / "status.json").read_bytes()
        cls.runner_raw = RUNNER_PATH.read_bytes()
        cls.report = json.loads(cls.report_raw.decode("utf-8"))
        cls.claim = json.loads(cls.claim_raw.decode("utf-8"))
        cls.status = json.loads(cls.status_raw.decode("utf-8"))
        cls.runner = _load_runner()
        cls.modules = cls.runner._load_modules(ROOT)
        cls.audits = {}

        # Exercise every retained policy only through the independent audit;
        # fail if any audit reaches a production solve/tree/train/eval/rank API.
        import pokerlab.cards as cards
        import pokerlab.native_fixed_street as native_backend
        import pokerlab.native_river_solver as native_solver
        import pokerlab.postflop_solver as postflop
        import pokerlab.public_cfr as public_cfr
        import pokerlab.public_diagnostics as diagnostics
        import pokerlab.ranked_river as ranked
        import pokerlab.river_tail_adapter as river_tail

        forbidden = (
            (native_solver, "solve_native_river"),
            (river_tail, "solve_river_tail"),
            (postflop, "_enumerate_worlds"),
            (postflop, "_build_postflop_tree"),
            (postflop, "_prefix_hand_index"),
            (public_cfr, "train_public_batched"),
            (public_cfr, "train_ranked_river"),
            (diagnostics, "evaluate_profile"),
            (ranked.RankedRiverPayoffs, "values"),
            (native_backend, "train_native_fixed_street"),
            (cards, "rank_hand"),
        )
        cls.rows = cls.report["profiles"]
        with ExitStack() as stack:
            for owner, name in forbidden:
                stack.enter_context(patch.object(
                    owner, name,
                    side_effect=AssertionError(f"forbidden production helper call: {name}"),
                ))
            for row in cls.rows:
                case = next(case for case in (
                    *cls.runner.BASE_CASES, cls.runner.FRESH_CASE, cls.runner.CHECK_ONLY
                ) if case["id"] == row["scenario"])
                for backend in ("native", "python"):
                    policy_receipt = row[f"{backend}_policy"]
                    relative = policy_receipt["file"]
                    raw = (ARTIFACT_ROOT / relative).read_bytes()
                    policy = json.loads(raw.decode("utf-8"))
                    audit = cls.runner._audit_policy(policy, case, cls.modules)
                    cls.audits[(row["scenario"], row["iterations"], backend)] = (
                        raw, policy, audit,
                    )

    def test_report_claim_status_runner_and_policy_bytes_are_pinned(self):
        self.assertEqual(_sha(self.report_raw), EXPECTED_REPORT_SHA256)
        self.assertEqual(_sha(self.claim_raw), EXPECTED_CLAIM_SHA256)
        self.assertEqual(_sha(self.status_raw), EXPECTED_STATUS_SHA256)
        self.assertEqual(_sha(self.runner_raw), EXPECTED_RUNNER_SHA256)
        self.assertEqual(self.report["schema"], "compiled-river-conformance-report-v1")
        self.assertEqual(self.report["status"], "completed")
        self.assertEqual(self.claim["schema"], "compiled-river-conformance-claim-v1")
        self.assertEqual(self.claim["claim_id"], EXPECTED_CLAIM_ID)
        self.assertEqual(self.report["claim_id"], EXPECTED_CLAIM_ID)
        self.assertEqual(self.status["claim_id"], EXPECTED_CLAIM_ID)
        self.assertEqual(self.status["status"], "completed")
        self.assertFalse(self.claim["retry_permitted"])
        self.assertFalse(self.status["retry_permitted"])
        self.assertFalse(self.claim["quality_search"])
        self.assertEqual(self.claim["algorithm"], "cfrplus")
        self.assertEqual(self.claim["discard"], 0)
        self.assertEqual(self.claim["iterations"], [10, 100])
        self.assertEqual(self.claim["source_head"], EXPECTED_SOURCE_HEAD)
        self.assertEqual(self.report["source_snapshot"]["head"], EXPECTED_SOURCE_HEAD)
        self.assertEqual(self.claim["source_snapshot"], self.report["source_snapshot"])
        self.assertEqual(self.claim["runner_snapshot"], self.report["source_snapshot"]["runner"])
        self.assertEqual(self.claim["runner_snapshot"]["raw_sha256"], EXPECTED_RUNNER_SHA256)

        expected_ids = {
            (case["id"], iterations)
            for case in (*self.runner.BASE_CASES, self.runner.FRESH_CASE, self.runner.CHECK_ONLY)
            for iterations in (10, 100)
        }
        self.assertEqual({(row["scenario"], row["iterations"]) for row in self.rows},
                         expected_ids)
        self.assertEqual(len(self.rows), 8)
        self.assertEqual(len(self.status["completed_profiles"]), 8)
        self.assertEqual(self.report["scope"],
                         "Fixed small correctness controls; not a convergence or performance study.")
        self.assertTrue(all("target" not in row for row in self.rows))

        actual_policy_hashes = {}
        for row in self.rows:
            for backend in ("native", "python"):
                receipt = row[f"{backend}_policy"]
                actual_policy_hashes[receipt["file"]] = receipt["sha256"]
                raw = (ARTIFACT_ROOT / receipt["file"]).read_bytes()
                self.assertEqual(_sha(raw), receipt["sha256"])
                self.assertEqual(len(raw), receipt["bytes"])
                self.assertTrue(raw.endswith(b"\n"))
                self.assertNotIn(b"\r", raw)
        self.assertEqual(actual_policy_hashes, EXPECTED_POLICIES)

    def test_historical_source_map_and_build_receipt_are_authenticated(self):
        snapshot = self.report["source_snapshot"]
        files = snapshot["files"]
        self.assertEqual(len(files), 77)
        self.assertEqual(set(files), set(self.claim["source_snapshot"]["files"]))
        for relative, entry in files.items():
            self.assertIs(type(entry["bytes"]), int)
            self.assertGreater(entry["bytes"], 0)
            self.assertRegex(entry["raw_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(entry["normalized_lf_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(entry["git_blob"], r"^[0-9a-f]{40}$")

        for relative, expected in REQUIRED_SOURCE_LF_SHA256.items():
            entry = files[relative]
            self.assertEqual(entry["normalized_lf_sha256"], expected, relative)
            current = (ROOT / relative).read_bytes()
            current_lf = current.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            self.assertEqual(_sha(current_lf), expected, relative)

        build = self.report["build_snapshot"]
        self.assertEqual(build["manifest_sha256"], BUILD_MANIFEST_SHA256)
        self.assertEqual(build["files"]["native-train-manifest.json"]["sha256"],
                         BUILD_MANIFEST_SHA256)
        manifest = build["manifest"]
        exe = manifest["executable"]
        self.assertEqual(manifest["executable_sha256"], BUILD_EXE_SHA256)
        self.assertEqual(build["files"][exe]["sha256"], BUILD_EXE_SHA256)
        native_source = files["native/fixed_street_train.c"]
        self.assertEqual(native_source["raw_sha256"], NATIVE_SOURCE_SHA256)
        self.assertEqual(native_source["normalized_lf_sha256"], NATIVE_SOURCE_LF_SHA256)
        self.assertEqual(manifest["source_sha256"], NATIVE_SOURCE_SHA256)
        self.assertEqual(manifest["source_lf_sha256"], NATIVE_SOURCE_LF_SHA256)
        self.assertEqual(manifest["protocol"], "OPENPOKER_FIXED_TRAIN_V2")
        self.assertEqual(manifest["work_model"], "native-fixed-street-work-v2")

    def test_all_sixteen_saved_policies_match_independent_numeric_and_exact_replay(self):
        for row in self.rows:
            scenario, iterations = row["scenario"], row["iterations"]
            for backend in ("native", "python"):
                key = (scenario, iterations, backend)
                raw, policy, audit = self.audits[key]
                receipt = row[f"{backend}_policy"]
                self.assertEqual(_sha(raw), EXPECTED_POLICIES[receipt["file"]], key)
                self.assertEqual(audit["blocked_production_helper_calls"], [], key)
                self.assertEqual(policy["iterations"], iterations, key)
                self.assertEqual(policy["requested_iterations"], iterations, key)
                self.assertEqual(policy["discard"], 0, key)
                self.assertEqual(policy["source_iteration_window"], [1, iterations], key)
                self.assertEqual(policy["average_weight_sum"], iterations * (iterations + 1) // 2, key)
                self.assertEqual(policy["requested_regret_passes"], 2 * iterations, key)
                self.assertEqual(policy["requested_average_passes"], iterations, key)
                self.assertEqual(policy["requested_total_traversal_passes"], 3 * iterations, key)
                self.assertEqual(audit["worlds"], row[f"{backend}_audit"]["worlds"], key)
                self.assertEqual(audit["compatible_pairs"],
                                 row[f"{backend}_audit"]["compatible_pairs"], key)
                self.assertEqual(audit["information_sets"],
                                 row[f"{backend}_audit"]["information_sets"], key)
                self.assertEqual(audit["public_decision_nodes"],
                                 row[f"{backend}_audit"]["public_decision_nodes"], key)
                self.assertEqual(set(audit["numeric_metrics"]), set(self.runner.METRICS), key)
                exact = audit["exact_audit"]
                stored_exact = row[f"{backend}_audit"]["exact_audit"]
                self.assertEqual(exact, stored_exact, key)
                self.assertEqual(exact["status"], "admitted", key)
                self.assertEqual(exact["chance_groupings"]["scan"]["metrics_fraction"],
                                 exact["chance_groupings"]["partition"]["metrics_fraction"], key)
                metrics = {name: _fraction(value)
                           for name, value in exact["metrics_fraction"].items()}
                self.assertEqual(set(metrics), set(self.runner.METRICS), key)
                lower = _fraction(exact["lower_value_bound_fraction"])
                upper = _fraction(exact["upper_value_bound_fraction"])
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
                self.assertEqual(metrics["exploitability"], metrics["nash_conv"] / 2, key)
                self.assertLessEqual(exact["chance_groupings"]["scan"]["work"],
                                     exact["chance_groupings"]["scan"]["work_limit"], key)
                self.assertLessEqual(exact["chance_groupings"]["partition"]["work"],
                                     exact["chance_groupings"]["partition"]["work_limit"], key)
                for mode in ("scan", "partition"):
                    summary = exact["chance_groupings"][mode]
                    self.assertEqual(summary["work_limit"], 100_000, (key, mode))
                    self.assertEqual(summary["depth_limit"], 64, (key, mode))
                    self.assertEqual(summary["fraction_bit_limit"], 65_536, (key, mode))
                    self.assertLessEqual(summary["tree_depth"], summary["depth_limit"], (key, mode))
                    self.assertLessEqual(summary["maximum_fraction_bits"], summary["fraction_bit_limit"], (key, mode))
                for metric in self.runner.METRICS:
                    self.assertLessEqual(
                        abs(audit["numeric_metrics"][metric] - float(metrics[metric])),
                        self.runner.METRIC_TOLERANCE, (key, metric),
                    )
                    self.assertLessEqual(
                        abs(audit["numeric_metrics"][metric] - float(policy[metric])),
                        self.runner.METRIC_TOLERANCE, (key, metric, "serialized"),
                    )
            native_raw, native_policy, _ = self.audits[(scenario, iterations, "native")]
            python_raw, python_policy, _ = self.audits[(scenario, iterations, "python")]
            self.assertEqual(row["max_policy_probability_delta"], 0.0, (scenario, iterations))
            self.assertEqual(row["native_vs_python_metric_deltas"],
                             {name: 0.0 for name in self.runner.METRICS}, (scenario, iterations))
            self.assertEqual(
                self.runner._strategy_metadata_and_probabilities(
                    native_policy, python_policy, self.runner.FLOAT_POLICY_TOLERANCE),
                0.0, (scenario, iterations),
            )
            self.assertTrue(native_raw and python_raw)

    def test_manual_anchor_and_trained_royal_flush_intervals_are_zero_sum(self):
        control = self.report["check_only_control"]
        self.assertEqual(control["fixture"]["id"], "river-royal-flush-tie-anchor")
        self.assertEqual(control["expected_value_oop_fraction"], "0")
        self.assertEqual(control["exact_metrics_fraction"]["value_oop"], "0")
        self.assertEqual(control["exact_metrics_fraction"]["value_ip"], "0")
        self.assertLessEqual(Fraction(control["lower_value_bound_fraction"]), 0)
        self.assertGreaterEqual(Fraction(control["upper_value_bound_fraction"]), 0)
        self.assertEqual(control["blocked_production_helper_calls"], [])
        self.assertEqual(control["worlds"], 4)
        self.assertEqual(control["compatible_pairs"], 4)

        for row in self.rows:
            if row["scenario"] != "river-royal-flush-tie-anchor":
                continue
            for backend in ("native", "python"):
                exact = row[f"{backend}_audit"]["exact_audit"]
                metrics = {name: _fraction(value)
                           for name, value in exact["metrics_fraction"].items()}
                lower = _fraction(exact["lower_value_bound_fraction"])
                upper = _fraction(exact["upper_value_bound_fraction"])
                self.assertLessEqual(lower, 0, (row["iterations"], backend))
                self.assertGreaterEqual(upper, 0, (row["iterations"], backend))
                self.assertGreaterEqual(metrics["oop_best_response_value"], 0)
                self.assertGreaterEqual(metrics["ip_best_response_value"], 0)


if __name__ == "__main__":
    unittest.main()
