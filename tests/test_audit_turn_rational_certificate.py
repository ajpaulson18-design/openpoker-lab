"""Pinned public-auditor regressions over the already saved policy grid."""
import copy
import json
import unittest

from scripts import audit_turn_rational_certificate as audit_script
from scripts.benchmark_turn_river_independent import ROOT
from scripts.benchmark_turn_selected_accuracy import frozen_case


REPORT = ROOT / "benchmarks" / "results" / "turn-selected-accuracy-v1.json"
POLICIES = ROOT / "benchmarks" / "results" / "turn-selected-accuracy-policies-v1"


class TurnRationalAuditTests(unittest.TestCase):
    def test_parent_report_and_all_six_raw_policy_identities_are_pinned(self):
        report, rows, digest = audit_script._pinned_report(REPORT)
        self.assertEqual(len(rows), 6)
        self.assertEqual(report["fixture"], frozen_case())
        self.assertEqual(digest, audit_script.PARENT_REPORT_CANONICAL_SHA256)
        for identity, (filename, expected_hash) in audit_script.EXPECTED_POLICY_HASHES.items():
            row = rows[identity]
            self.assertEqual(row["policy_file"], filename)
            self.assertEqual(row["policy_sha256"], expected_hash)

    def test_historical_parent_gate_tracks_model_inputs_not_unrelated_solver_files(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        hashes = copy.copy(report["source_sha256"])
        self.assertTrue(audit_script._source_fingerprint_matches_report(hashes))

        unrelated = next(name for name in hashes
                         if name.replace("\\", "/") == "pokerlab/matrix_free_turn.py")
        hashes[unrelated] = "0" * 64
        self.assertTrue(audit_script._source_fingerprint_matches_report(hashes))

        numeric_rules = next(name for name in hashes
                             if name.replace("\\", "/") == "scripts/turn_river_validation.py")
        hashes[numeric_rules] = "0" * 64
        self.assertFalse(audit_script._source_fingerprint_matches_report(hashes))

    def test_public_audit_replays_and_certifies_all_six_saved_profiles(self):
        certificate = audit_script.audit(REPORT, POLICIES)
        self.assertEqual(len(certificate["results"]), 6)
        self.assertEqual(certificate["parent_report_canonical_sha256"],
                         audit_script.PARENT_REPORT_CANONICAL_SHA256)
        self.assertIn("not a raw-float-profile certificate", certificate["limitations"])
        for row in certificate["results"]:
            with self.subTest(profile=(row["backend"], row["iterations"])):
                self.assertEqual(row["verified_worlds"], 8)
                self.assertEqual(row["verified_public_tree_nodes"], 188)
                self.assertEqual(set(row["exact_metrics"]), set(audit_script.METRIC_FIELDS))
                self.assertTrue(all(abs(value) <= audit_script.FLOAT_TOLERANCE
                                    for value in row["exact_vs_float_replay_deltas"].values()))
                self.assertEqual(row["exact_nash_conv_threshold_fraction"], "1/1000")
                limits = row["resource_limits"]
                self.assertEqual(limits, {
                    "maximum_work": 100_000,
                    "maximum_depth": 64,
                    "maximum_fraction_bits": 65_536,
                })


if __name__ == "__main__":
    unittest.main()
