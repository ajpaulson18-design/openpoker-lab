"""Replay the retained 8x8 river quality policies without training or a binary.

Byte pins authenticate this one completed batch. The independent physical rules
and rational best responses then re-evaluate every saved information-set row.
"""
from __future__ import annotations

from contextlib import ExitStack
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import benchmark_native_river_range_quality as runner

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "benchmarks" / "results" / "native-river-range-quality-v1"
EXPECTED_HEAD = "7371b450976a8b904afb7c7583070db4d5b84595"
EXPECTED_CLAIM = "9399dbdbf6de4d7397295c05269140de"
EXPECTED_HASHES = {
    "report.json": "e348d38048f2dc235caa7a8c1674cd92b56490cf6196152a7268b1b0badb52f5",
    "claim.json": "5244c65f875b57816b4602d850969a4c1eed921dd5a2c7849022143da8c64e00",
    "status.json": "9e4b41653b0153e2036efe716bbd72f74ce79f8f0a6d27006c325b382efb93b9",
    "policies/river-weighted-8x8-blocker-tie-short-refund-python-materialized-D0-T10000.json": "b9dabd5f728de0266d71c43a71acebf4bb7ae79bc18beafca4877c23294aa332",
    "policies/river-weighted-8x8-blocker-tie-short-refund-native-T10000.json": "daece189d6c46aae9f4436aa42c2a986ff55ea33e9576b22d5353068326d0d2a",
    "policies/river-paired-8x8-short-refund-zero-tie-python-materialized-D0-T10000.json": "471fa00fcc3fd5de78204e2ab7f98a3d1e8dbff6a8864e76f865c229b78bf61b",
    "policies/river-paired-8x8-short-refund-zero-tie-native-T10000.json": "f45b41ab8cf995b80a66f140945b1c72091a1d331c426a1eb1bb1021776569f0"
}
REQUIRED_MATH_LF_SHA256 = {
    "native/fixed_street_train.c": "5101bee03f7fd9d6d1b7cac8ea825144cd1a2471179de909ab22358264821676",
    "pokerlab/cards.py": "d748bc7960a3159ebe139b265782bcb3d5f065369951770c7928d6b5efeacadf",
    "pokerlab/river_config.py": "b4cff25ad217b3d0f472062ba062bf6e7fba2701ebdfd60e0632b4ecb5f2e9b3",
    "pokerlab/native_river_solver.py": "db54f4339319cddf83eb8ccb6c6e98d2fb566d70a72623939504d57e60b22e86",
    "pokerlab/river_tail_adapter.py": "0963a8df65d432415157a164618923bd2fcfede98ef0ed328ea8f1867e384e7d",
    "scripts/preflop_validation.py": "c4abe50a3f3ff814910ad2eaf653e6e2b29f7c31b28e6618f1718283794cfaa8",
    "scripts/turn_river_validation.py": "779b8f1d47566e071d0ee24b82c99e79de46a0edcddbd43ecd08f4ee6e84c3c1",
    "scripts/turn_rational_certificate.py": "0c94bee344871a47d34a1291f65f85ac3e80a1a9389d7785e4baf6695b3967fb",
    "scripts/river_heldout_preflight.py": "35216d3ca1ae60bdb8232783ed33917ef2a7bbb42ec8ae637981925328385a74",
    "scripts/benchmark_river_heldout_quality.py": "1259777db93672f513d5a1f19f245996d692820370560746c4794b1a495a9587"
}
NEW_SOURCE_LF_SHA256 = {
    "benchmarks/native-river-range-quality-v1.json": "49f8b00bd8ef43f8328b4fd4b485a98f9bc7ec991d2a68bfc0adf73d1ac2575f",
    "docs/native-river-range-quality-protocol.md": "ded2c08fc8348ab9dcfeb75ebed04457cca2b8545537a428c58a98e4fd55f7e7",
    "scripts/benchmark_native_river_range_quality.py": "8b4e3d098a216e31c600b412a5382979b0269b88c909d2f8831c0466269b334e"
}
CASES = (
    "river-weighted-8x8-blocker-tie-short-refund",
    "river-paired-8x8-short-refund-zero-tie",
)
GRID = tuple((case, backend) for case in CASES
             for backend in ("python-materialized-D0", "native"))
TARGET = Fraction(1, 1000)
COUNTS = {
    CASES[0]: {
        "worlds": 59, "compatible_pairs": 59, "information_sets": 72,
        "public_nodes": 9, "terminal_nodes": 15, "public_states": 24,
        "tree_actions": 23, "information_action_slots": 184,
        "world_iterations": 590000, "world_node_work": 15930000,
        "dense_hand_state_pass_work": 5760576, "prefix_hand_edges": 59,
        "independent_numeric_modeled_work": 2124,
    },
    CASES[1]: {
        "worlds": 60, "compatible_pairs": 60, "information_sets": 80,
        "public_nodes": 10, "terminal_nodes": 17, "public_states": 27,
        "tree_actions": 26, "information_action_slots": 208,
        "world_iterations": 600000, "world_node_work": 18000000,
        "dense_hand_state_pass_work": 6480648, "prefix_hand_edges": 60,
        "independent_numeric_modeled_work": 2400,
    },
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _lf(raw):
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _identity(row):
    return row["case"], row["backend"]


class SavedNativeRiverRangeQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = {name: (ARTIFACT / name).read_bytes()
                   for name in EXPECTED_HASHES}
        # Authenticate before importing policies into the replay model.
        for name, expected in EXPECTED_HASHES.items():
            if _sha(cls.raw[name]) != expected:
                raise AssertionError("retained artifact digest differs: " + name)
        cls.report = json.loads(cls.raw["report.json"])
        cls.claim = json.loads(cls.raw["claim.json"])
        cls.status = json.loads(cls.raw["status.json"])
        cls.manifest = cls.claim["manifest"]
        cls.cases = {case["id"]: case for case in cls.manifest["cases"]}
        cls.rows = cls.report["profiles"]
        cls.policies = {}
        cls.replays = {}
        # The constructor binds imports only. No native build directory needs
        # to exist, and all lifecycle/build/backend entry points are tripwired.
        runtime = runner.ProductionRuntime(ROOT, ARTIFACT / "absent-native-build")
        from pokerlab import native_fixed_street as fixed
        from scripts import build_native_train as builder
        forbidden = (
            (runner, "run"), (runner, "run_with_runtime"),
            (runtime, "call"), (runtime, "preflight"),
            (runtime, "source_snapshot"), (runtime, "build_snapshot"),
            (fixed, "_backend"), (fixed, "validate_backend"),
            (builder, "build"),
        )
        with ExitStack() as stack:
            for owner, name in forbidden:
                stack.enter_context(patch.object(
                    owner, name,
                    side_effect=AssertionError("forbidden saved-replay call: " + name),
                ))
            # ProductionRuntime.audit also disables every imported production
            # solve/train/rank/tree/evaluation alias using the pinned helper.
            for row in cls.rows:
                policy = json.loads(cls.raw[row["file"]])
                key = _identity(row)
                cls.policies[key] = policy
                cls.replays[key] = runtime.audit(
                    policy, cls.cases[row["case"]], cls.manifest["exact_limits"],
                )

    def test_bytes_claim_identity_no_retry_and_exact_four_call_grid(self):
        self.assertEqual(self.claim["schema"], "native-river-range-quality-claim-v1")
        self.assertEqual(self.report["schema"], "native-river-range-quality-report-v1")
        for document in (self.claim, self.report, self.status):
            self.assertEqual(document["claim_id"], EXPECTED_CLAIM)
        self.assertEqual(self.report["status"], "completed")
        self.assertEqual(self.status["status"], "completed")
        self.assertEqual(self.status["phase"], "done")
        self.assertIs(self.claim["retry_permitted"], False)
        self.assertIs(self.status["retry_permitted"], False)
        self.assertEqual(self.claim["target_nash_conv"], "1/1000")
        self.assertEqual(self.claim["source"], self.report["source"])
        self.assertEqual(self.claim["build"], self.report["build"])
        self.assertEqual(self.claim["preflight_admissions"],
                         self.report["preflight_admissions"])
        runner._validate_manifest(self.manifest)
        self.assertEqual([_identity(row) for row in self.rows], list(GRID))
        self.assertEqual(len(self.rows), 4)
        self.assertEqual([(c["case"], c["backend"])
                          for c in self.manifest["calls"]], list(GRID))
        self.assertEqual(self.manifest["iterations"], 10000)
        self.assertEqual(self.manifest["discard"], 0)
        receipts = [{key: row[key] for key in (
            "file", "bytes", "sha256", "case", "backend", "iterations"
        )} for row in self.rows]
        self.assertEqual(self.status["saved_policies"], receipts)
        self.assertEqual(self.status["completed_audits"], [
            {"case": row["case"], "backend": row["backend"], "replay_status": "valid"}
            for row in self.rows
        ])
        self.assertEqual(set(EXPECTED_HASHES) - {"report.json", "claim.json", "status.json"},
                         {row["file"] for row in self.rows})
        for row in self.rows:
            raw = self.raw[row["file"]]
            self.assertEqual(_sha(raw), row["sha256"])
            self.assertEqual(len(raw), row["bytes"])
            self.assertEqual(raw, runner._json_bytes(self.policies[_identity(row)]))
            self.assertTrue(raw.endswith(b"\n"))
            self.assertNotIn(b"\r", raw)

    def test_historical_source_maps_current_math_and_retained_build_are_pinned(self):
        source = self.report["source"]
        self.assertEqual(source["head"], EXPECTED_HEAD)
        self.assertEqual(source["status"], "clean")
        self.assertEqual(len(source["files"]), 77)
        self.assertEqual(len(source["study_source_files"]), 3)
        self.assertEqual(set(source["new_source_git_pins"]), set(NEW_SOURCE_LF_SHA256))
        for entry in source["files"].values():
            self.assertIs(type(entry["bytes"]), int)
            self.assertGreater(entry["bytes"], 0)
            self.assertRegex(entry["git_blob"], r"^[0-9a-f]{40}$")
            for name in ("raw_sha256", "normalized_lf_sha256"):
                self.assertRegex(entry[name], r"^[0-9a-f]{64}$")
        # Only current dependencies of this replay are fixed. The historical
        # full inventory stays authenticated by claim/report byte hashes.
        for relative, expected in REQUIRED_MATH_LF_SHA256.items():
            self.assertEqual(source["files"][relative]["normalized_lf_sha256"], expected)
            self.assertEqual(_sha(_lf((ROOT / relative).read_bytes())), expected, relative)
        for relative, expected in NEW_SOURCE_LF_SHA256.items():
            entry = source["new_source_git_pins"][relative]
            self.assertEqual(entry["normalized_lf_sha256"], expected)
            self.assertRegex(entry["git_blob"], r"^[0-9a-f]{40}$")
            self.assertEqual(_sha(_lf((ROOT / relative).read_bytes())), expected, relative)
        self.assertEqual(source["runner"]["raw_sha256"], runner.CONTROL_HELPER_SHA256)
        helper = ROOT / "benchmarks/results/native-river-controls-v1/validate_compiled_river.py"
        self.assertEqual(_sha(helper.read_bytes()), runner.CONTROL_HELPER_SHA256)
        control = runner.authenticate_control_corpus(
            ROOT / "benchmarks/results/native-river-controls-v1"
        )
        recorded = self.report["control_authentication"]
        for field in ("report_sha256", "claim_sha256", "status_sha256", "claim_id",
                      "status", "policy_count", "policies"):
            self.assertEqual(recorded[field], control[field], field)
        self.assertEqual(self.claim["control_authentication"], recorded)
        build = self.report["build"]
        self.assertEqual(build["manifest_sha256"],
                         "8046b7e7e85a3d2acff3d8e3c33dfd646dff23739d6bd929167994f34e4c8a7d")
        manifest = build["manifest"]
        self.assertEqual(manifest["executable_sha256"],
                         "d8f21a4598c65ef31770ab1ba44439510d122abb5fcc19800ac38bf5ef737bbc")
        self.assertEqual(manifest["source_lf_sha256"],
                         REQUIRED_MATH_LF_SHA256["native/fixed_street_train.c"])
        self.assertEqual(manifest["protocol"], "OPENPOKER_FIXED_TRAIN_V2")
        self.assertEqual(manifest["work_model"], "native-fixed-street-work-v2")
        self.assertEqual(build["files"][manifest["executable"]]["sha256"],
                         manifest["executable_sha256"])

    def test_saved_schedules_counts_and_full_request_admissions(self):
        admissions = self.report["preflight_admissions"]
        self.assertEqual([(row["case_id"], row["backend_cell"]) for row in admissions],
                         list(GRID))
        by_key = {(row["case_id"], row["backend_cell"]): row for row in admissions}
        for row in admissions:
            runner._validate_admission(row)
            expected = COUNTS[row["case_id"]]
            for name, count in expected.items():
                self.assertIs(type(row[name]), int, name)
                self.assertEqual(row[name], count, (row["case_id"], name))
            self.assertEqual(row["candidate_hand_pair_iterations"], 640000)
            self.assertEqual(row["native_active_hand_counts"], [8, 8])
            self.assertEqual(row["independent_max_world_count"], 200000)
            self.assertEqual(row["independent_numeric_modeled_work_limit"], 8000000)
            self.assertIs(row["trainer_or_build_lookup_called"], False)
            census = row["adapted_independent_census"]
            self.assertIs(census["production_tree_signature_matches"], True)
            self.assertIs(census["native_postflop_tree_signature_matches"], True)
            self.assertEqual(census["independent_tree_decisions"], expected["public_nodes"])
            self.assertEqual(census["independent_tree_terminals"], expected["terminal_nodes"])
            self.assertLessEqual(census["production_physical_world_crosscheck"]["mass_max_abs_difference"], 1e-15)
        count_fields = {
            "worlds": "worlds", "worlds_materialized": "worlds",
            "deals": "compatible_pairs", "compatible_pairs": "compatible_pairs",
            "info_sets": "information_sets", "public_nodes": "public_nodes",
            "public_states": "public_states", "terminal_nodes": "terminal_nodes",
            "tree_actions": "tree_actions",
        }
        for row in self.rows:
            key = _identity(row)
            policy = self.policies[key]
            runner._validate_return(policy, self.cases[row["case"]], row["backend"], 10000)
            self.assertEqual(policy["source_iteration_window"], [1, 10000])
            self.assertEqual(policy["average_weight_sum"], 50005000)
            self.assertEqual(policy["requested_regret_passes"], 20000)
            self.assertEqual(policy["requested_average_passes"], 10000)
            self.assertEqual(policy["requested_total_traversal_passes"], 30000)
            self.assertEqual(policy["training_calls"], 1)
            self.assertEqual(policy["chance_nodes"], 0)
            for field, count in count_fields.items():
                self.assertEqual(policy[field], COUNTS[row["case"]][count], (key, field))
            self.assertEqual(len(policy["strategy"]), COUNTS[row["case"]]["information_sets"])
            if row["backend"] == "native":
                runner._validate_native_receipt(
                    policy, self.report["build"], by_key[key]["native_shape_admission"],
                )

    def test_every_policy_matches_independent_physical_numeric_and_exact_replay(self):
        self.assertEqual(len(self.replays), 4)
        for row in self.rows:
            key = _identity(row)
            replay = self.replays[key]
            stored = row["independent_audit"]
            self.assertEqual(stored["replay_status"], "valid", key)
            self.assertEqual(replay["blocked_production_helper_calls"], [], key)
            for field, actual in replay.items():
                self.assertEqual(actual, stored[field], (key, field))
            expected = COUNTS[row["case"]]
            self.assertEqual(replay["world_count"], expected["worlds"])
            self.assertEqual(replay["compatible_pairs"], expected["compatible_pairs"])
            self.assertEqual(replay["information_sets"], expected["information_sets"])
            self.assertEqual(replay["public_decision_nodes"], expected["public_nodes"])
            self.assertEqual(replay["action_rows"], self.policies[key]["strategy"])
            self.assertEqual(set(replay["numeric_metrics"]), set(runner.METRICS))
            exact = replay["exact_audit"]
            self.assertEqual(exact["status"], "admitted", key)
            self.assertEqual(set(exact["chance_groupings"]), {"scan", "partition"})
            self.assertEqual(exact["chance_groupings"]["scan"]["metrics_fraction"],
                             exact["chance_groupings"]["partition"]["metrics_fraction"])
            metrics = {name: Fraction(value) for name, value in exact["metrics_fraction"].items()}
            self.assertEqual(set(metrics), set(runner.METRICS))
            lower = Fraction(exact["lower_value_bound_fraction"])
            upper = Fraction(exact["upper_value_bound_fraction"])
            self.assertEqual(lower, -metrics["ip_best_response_value"])
            self.assertEqual(upper, metrics["oop_best_response_value"])
            self.assertLessEqual(lower, metrics["value_oop"])
            self.assertLessEqual(metrics["value_oop"], upper)
            self.assertEqual(metrics["value_ip"], -metrics["value_oop"])
            self.assertEqual(metrics["oop_best_response_gain"], upper - metrics["value_oop"])
            self.assertEqual(metrics["ip_best_response_gain"], metrics["value_oop"] - lower)
            self.assertEqual(metrics["nash_conv"], upper - lower)
            self.assertEqual(metrics["exploitability"], metrics["nash_conv"] / 2)
            for mode, summary in exact["chance_groupings"].items():
                self.assertEqual(summary["status"], "admitted", (key, mode))
                for usage, limit, cap in (
                    ("work", "work_limit", 100000),
                    ("tree_depth", "depth_limit", 64),
                    ("maximum_fraction_bits", "fraction_bit_limit", 65536),
                ):
                    self.assertEqual(summary[limit], cap, (key, mode, limit))
                    self.assertLessEqual(summary[usage], cap, (key, mode, usage))
            for name in runner.METRICS:
                numeric = replay["numeric_metrics"][name]
                self.assertLessEqual(abs(numeric - float(metrics[name])), 1e-8, (key, name))
                self.assertLessEqual(abs(numeric - float(self.policies[key][name])), 1e-8,
                                     (key, name, "serialized"))
            numeric_met = replay["numeric_metrics"]["nash_conv"] <= float(TARGET)
            exact_met = metrics["nash_conv"] <= TARGET
            self.assertEqual(row["numeric_target_met"], numeric_met)
            self.assertEqual(row["exact_target_met"], exact_met)
            self.assertEqual(row["quality_gate"], exact_met)
            self.assertEqual(stored["numeric_target_met"], numeric_met)
            self.assertEqual(stored["exact_target_met"], exact_met)
            self.assertEqual(exact["target_met"], exact_met)
            self.assertIs(exact_met, True, key)

    def test_parity_is_recomputed_separately_from_accuracy_gates(self):
        expected = []
        for case in CASES:
            native, python = (case, "native"), (case, "python-materialized-D0")
            parity = runner._policy_parity(
                self.policies[native], self.policies[python],
                self.replays[native], self.replays[python], 1e-9, 1e-8,
            )
            expected.append({"case": case, **parity})
            self.assertEqual(parity["status"], "passed")
            self.assertEqual(parity["max_probability_delta"], 0.0)
            self.assertEqual(parity["metric_deltas"], {name: 0.0 for name in runner.METRICS})
        self.assertEqual(self.report["parity"], expected)
        self.assertEqual(self.status["parity"], expected)


if __name__ == "__main__":
    unittest.main()
