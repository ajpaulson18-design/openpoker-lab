"""Bounded checks for pinned exact rational river-policy auditing."""
import copy
import json
import os
import subprocess
import unittest
from unittest import mock

from scripts import audit_river_rational_certificate as audit
from scripts import turn_river_validation as validator
from scripts.turn_rational_certificate import evaluate_exact


class RiverRationalCertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reports, cls.indexed = audit._load_parent_reports()

    def test_archive_pins_and_hardened_bridge_cover_all_fifteen_profiles(self):
        self.assertEqual(len(audit.POLICY_PINS), 15)
        self.assertEqual(sum(map(len, self.indexed.values())), 15)
        self.assertEqual(
            {source: len(rows) for source, rows in self.indexed.items()},
            {"river-cfrplus-accuracy-extension-v1": 12,
             "river-cfrplus-long-budget-v1": 3},
        )
        bridge = audit._validate_hardened_replay_bridge(self.reports)
        self.assertEqual(bridge["canonical_sha256"],
                         audit.HARDENED_REPLAY_BRIDGE_SHA256)
        self.assertEqual(bridge["verified_extension_policy_identities"], 12)
        audit._check_historical_model_sources(self.reports)

    def test_hardened_bridge_digest_tampering_is_rejected(self):
        with mock.patch.object(audit, "HARDENED_REPLAY_BRIDGE_SHA256", "0" * 64):
            with self.assertRaisesRegex(ValueError, "bridge differs"):
                audit._validate_hardened_replay_bridge(self.reports)

    def test_duplicate_polarised_10k_records_keep_both_byte_hashes(self):
        relation = audit._verify_duplicate_10k(self.reports)
        self.assertFalse(relation["raw_policy_bytes_equal"])
        self.assertTrue(relation["decoded_complete_payloads_equal"])
        self.assertNotEqual(relation["extension_archive_policy_sha256"],
                            relation["long_budget_policy_sha256"])

    def test_weighted_raised_profile_has_bounded_exact_certificate(self):
        key = ("river-cfrplus-accuracy-extension-v1", "river-weighted-raises",
               "matrix-free", 10000)
        row = audit._audit_profile(key[0], key, self.indexed[key[0]][key],
                                   self.reports)
        self.assertEqual(row["verified_worlds"], 4)
        self.assertEqual(row["verified_information_sets"], 36)
        self.assertEqual(row["verified_decision_nodes"], 18)
        self.assertEqual(row["verified_tree_depth"], 6)
        self.assertLessEqual(row["work"], 100_000)
        self.assertLessEqual(row["maximum_fraction_bits"], 65_536)
        self.assertLessEqual(max(map(abs, row["exact_vs_float_replay_deltas"].values())),
                             audit.FLOAT_TOLERANCE)
        self.assertIsNone(row["polarised_explicit_history_witness"])

    def test_polarised_profile_matches_all_eight_explicit_history_metrics(self):
        key = ("river-cfrplus-accuracy-extension-v1",
               "river-polarised-bluffcatcher", "matrix-free", 1000)
        row = audit._audit_profile(key[0], key, self.indexed[key[0]][key],
                                   self.reports)
        witness = row["polarised_explicit_history_witness"]
        self.assertEqual(set(witness["metrics_fractions"]), set(audit.METRIC_NAMES))
        self.assertEqual(witness["metrics_fractions"], row["exact_metrics_fractions"])
        self.assertEqual(witness["known_value_fraction"], "25")
        self.assertTrue(witness["known_value_in_interval"])

    def test_saved_row_verification_rejects_self_consistent_false_certificate(self):
        key = ("river-cfrplus-accuracy-extension-v1", "river-weighted-raises",
               "matrix-free", 1000)
        saved = audit._audit_profile(key[0], key, self.indexed[key[0]][key],
                                     self.reports)
        altered = copy.deepcopy(saved)
        altered["exact_metrics_fractions"] = {
            "value_oop": "0", "value_ip": "0",
            "oop_best_response_value": "0", "ip_best_response_value": "0",
            "oop_best_response_gain": "0", "ip_best_response_gain": "0",
            "nash_conv": "0", "exploitability": "0",
        }
        altered["exact_float_metrics"] = {name: 0.0 for name in audit.METRIC_NAMES}
        altered["lower_value_bound_fraction"] = "0"
        altered["upper_value_bound_fraction"] = "0"
        altered["benchmark_threshold_met"] = True
        altered["exact_vs_float_replay_deltas"] = {
            name: -saved["exact_float_metrics"][name] +
                  saved["exact_vs_float_replay_deltas"][name]
            for name in audit.METRIC_NAMES
        }
        with self.assertRaisesRegex(ValueError, "fresh policy replay and exact recomputation"):
            audit._verify_saved_profile_row(
                altered, key[0], key, self.indexed, self.reports)

    def test_policy_raw_hash_and_serialized_model_corruptions_fail_closed(self):
        key = ("river-cfrplus-accuracy-extension-v1", "river-weighted-raises",
               "matrix-free", 1000)
        filename, _ = audit.POLICY_PINS[key]
        with mock.patch.dict(audit.POLICY_PINS, {key: (filename, "0" * 64)}):
            with self.assertRaisesRegex(ValueError, "pinned SHA-256"):
                audit._read_policy(key[0], key)

        result, _, _, _ = audit._read_policy(key[0], key)
        fixture = audit.FIXTURES[key[1]]
        for corrupt in ("board", "action", "missing-row"):
            damaged = copy.deepcopy(result)
            if corrupt == "board":
                damaged["board"][0] = "As"
            elif corrupt == "action":
                damaged["strategy"][0]["actions"][0]["history_key"] = "forged"
            else:
                damaged["strategy"].pop()
            with self.subTest(corrupt=corrupt), self.assertRaises(ValueError):
                audit._independent_model(damaged, fixture)

        scalar_damage = copy.deepcopy(result)
        scalar_damage["value_oop"] = float(scalar_damage["value_oop"]) + 1.0
        float_oracle = validator.replay_policy(
            scalar_damage, fixture["oop"], fixture["ip"], board=fixture["board"],
            config=fixture["config"])
        with self.assertRaises(ValueError):
            validator.compare_result(scalar_damage, float_oracle,
                                     tolerance=audit.FLOAT_TOLERANCE)

    def test_saved_provenance_keeps_generation_head_and_allows_unrelated_inventory_drift(self):
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=audit.ROOT,
                                       text=True).strip()
        required = {
            "scripts/turn_rational_certificate.py",
            "scripts/audit_river_rational_certificate.py",
            "tests/test_audit_river_rational_certificate.py",
            "tests/test_river_rational_review.py",
            "scripts/preflop_validation.py",
            audit.HARDENED_REPLAY_BRIDGE.relative_to(audit.ROOT).as_posix(),
            audit.EXTENSION_REPORT.relative_to(audit.ROOT).as_posix(),
            audit.LONG_REPORT.relative_to(audit.ROOT).as_posix(),
        }
        required.update(
            audit.ARCHIVES[source]["policy_dir"].relative_to(audit.ROOT).as_posix()
            + "/" + filename
            for source, filename in ((key[0], value[0])
                                     for key, value in audit.POLICY_PINS.items()))
        provenance = {name: "0" * 64 for name in required}
        for path in (
                audit.ROOT / "scripts" / "turn_rational_certificate.py",
                audit.ROOT / "scripts" / "audit_river_rational_certificate.py",
                audit.ROOT / "tests" / "test_audit_river_rational_certificate.py",
                audit.ROOT / "tests" / "test_river_rational_review.py",
            audit.ROOT / "scripts" / "preflop_validation.py",
            audit.ROOT / "pokerlab" / "cards.py",
            audit.ROOT / "scripts" / "turn_river_validation.py",
            audit.ROOT / "scripts" / "benchmark_turn_river_independent.py",
            audit.ROOT / "benchmarks" / "turn-river-quality-v1.json",
                audit.HARDENED_REPLAY_BRIDGE, audit.EXTENSION_REPORT, audit.LONG_REPORT):
            provenance[path.relative_to(audit.ROOT).as_posix()] = audit._sha256(
                path.read_bytes())
        for key, (filename, _) in audit.POLICY_PINS.items():
            path = audit._policy_paths(key[0], filename)
            provenance[path.relative_to(audit.ROOT).as_posix()] = audit._sha256(
                path.read_bytes())
        model_source = audit.ROOT / "scripts" / "turn_rational_certificate.py"
        normalized = model_source.read_bytes().replace(b"\r\n", b"\n")
        provenance[model_source.relative_to(audit.ROOT).as_posix()] = audit._sha256(
            normalized.replace(b"\n", b"\r\n"))
        provenance["pokerlab/unrelated-preflop.py"] = "f" * 64
        saved = {"baseline_git_commit": head, "source_sha256": provenance}
        self.assertEqual(audit._validate_saved_provenance(saved), head)

        fresh = {"certificate_id": "river-rational-certificate-v1",
                 "baseline_git_commit": "1" * 40,
                 "source_sha256": {"pokerlab/new-unrelated.py": "2" * 64},
                 "results": []}
        archived = copy.deepcopy(fresh)
        archived["baseline_git_commit"] = head
        archived["source_sha256"] = provenance
        audit._compare_saved_to_fresh(archived, fresh)

    def test_saved_artifact_verifies_after_current_head_and_unrelated_inventory_change(self):
        artifact_dir = audit.ROOT / "work" / f"river-rational-test-{os.getpid()}"
        artifact_dir.mkdir(parents=True, exist_ok=False)
        artifact = artifact_dir / "saved-certificate.json"
        try:
            saved = audit.audit()
            saved["baseline_git_commit"] = "a" * 40
            saved["source_sha256"]["pokerlab/unrelated-module.py"] = "f" * 64
            artifact.write_text(json.dumps(saved), encoding="utf-8")
            self.assertEqual(audit.verify_saved_artifact(artifact), saved)

            tampered = copy.deepcopy(saved)
            row = tampered["results"][0]
            row["exact_metrics_fractions"] = {name: "0" for name in audit.METRIC_NAMES}
            row["exact_float_metrics"] = {name: 0.0 for name in audit.METRIC_NAMES}
            row["exact_vs_float_replay_deltas"] = {
                name: saved["results"][0]["exact_vs_float_replay_deltas"][name]
                     - saved["results"][0]["exact_float_metrics"][name]
                for name in audit.METRIC_NAMES}
            row["lower_value_bound_fraction"] = "0"
            row["upper_value_bound_fraction"] = "0"
            row["benchmark_threshold_met"] = True
            artifact.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fresh policy replay and exact recomputation"):
                audit.verify_saved_artifact(artifact)
        finally:
            artifact.unlink(missing_ok=True)
            artifact_dir.rmdir()

    def test_source_and_head_change_guards_reject_mid_audit_mutation(self):
        with self.assertRaisesRegex(RuntimeError, "source or policy input changed"):
            audit._assert_unchanged({"a": "1"}, {"a": "2"},
                                    "source or policy input")
        with self.assertRaisesRegex(RuntimeError, "Git HEAD changed"):
            audit._assert_unchanged("a" * 40, "b" * 40, "Git HEAD")
        audit._assert_unchanged({"a": "1"}, {"a": "1"}, "source or policy input")

        stable_sources = audit._source_fingerprints()
        with mock.patch.object(audit, "_source_fingerprints",
                               side_effect=[stable_sources, {**stable_sources, "late": "changed"}]):
            with self.assertRaisesRegex(RuntimeError, "source or policy input changed"):
                audit.audit()

        actual_head = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                              cwd=audit.ROOT, text=True).strip()
        with mock.patch.object(audit.subprocess, "check_output",
                               side_effect=[actual_head, "b" * 40]):
            with self.assertRaisesRegex(RuntimeError, "Git HEAD changed"):
                audit.audit()

    def test_exact_resource_caps_remain_fixed_and_exhaustion_is_rejected(self):
        self.assertEqual((audit.EXACT_WORK_LIMIT, audit.EXACT_DEPTH_LIMIT,
                          audit.EXACT_FRACTION_BIT_LIMIT),
                         (100_000, 64, 65_536))
        key = ("river-cfrplus-accuracy-extension-v1", "river-polarised-bluffcatcher",
               "materialized", 1000)
        result, _, _, _ = audit._read_policy(key[0], key)
        fixture = audit.FIXTURES[key[1]]
        _, config, worlds, root, _, policies = audit._independent_model(result, fixture)
        with self.assertRaisesRegex(ValueError, "work limit"):
            evaluate_exact(root, worlds, policies, config.pot, result=result, max_work=1)

    def test_parent_fixture_and_duplicate_or_missing_result_rows_are_rejected(self):
        altered = copy.deepcopy(self.reports["river-cfrplus-accuracy-extension-v1"])
        altered["fixtures"][0]["config"]["pot"] = 101
        with self.assertRaisesRegex(ValueError, "pinned canonical digest"):
            audit._validate_parent_document("river-cfrplus-accuracy-extension-v1", altered)

        sample = [{"archive": key[0], "scenario": key[1],
                   "backend": key[2], "iterations": key[3]}
                  for key in sorted(audit.POLICY_PINS)]
        self.assertEqual(len(audit._index_result_rows(sample)), 15)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            audit._index_result_rows(sample + [copy.deepcopy(sample[0])])
        with self.assertRaisesRegex(ValueError, "exactly the fifteen"):
            audit._index_result_rows(sample[:-1])
        bad = copy.deepcopy(sample)
        bad[0]["iterations"] = True
        with self.assertRaisesRegex(ValueError, "invalid identity"):
            audit._index_result_rows(bad)


if __name__ == "__main__":
    unittest.main()
