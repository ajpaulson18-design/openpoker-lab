"""Pinned-input and saved-certificate integrity tests for the full44 auditor."""
import unittest

from scripts import audit_full_deck_turn_rational as auditor


class _ChangedPolicy:
    def __init__(self, payload):
        self.payload = payload

    def read_bytes(self):
        return self.payload + b" "


class FullDeckRationalAuditTests(unittest.TestCase):
    def test_parent_is_pinned_to_the_six_complete_full44_identities(self):
        report, rows, digest, case = auditor._pinned_parent(auditor.PARENT_REPORT)
        self.assertEqual(digest, auditor.PARENT_REPORT_CANONICAL_SHA256)
        self.assertEqual(report["baseline_git_commit"], auditor.EXPECTED_BASELINE)
        self.assertEqual(case["id"], auditor.EXPECTED_CASE_ID)
        self.assertEqual(set(rows), set(auditor.EXPECTED_POLICIES))

    def test_tampered_policy_bytes_fail_before_json_or_exact_replay(self):
        identity = ("matrix-free", 1_000)
        filename, _ = auditor.EXPECTED_POLICIES[identity]
        original = auditor.POLICY_DIRECTORY / filename

        class ChangedDirectory:
            def __truediv__(self, requested):
                self.asserted_filename = requested
                payload = (auditor.POLICY_DIRECTORY / requested).read_bytes()
                return _ChangedPolicy(payload)

        with self.assertRaisesRegex(ValueError, "pinned full-deck policy"):
            auditor._pinned_policy(identity, ChangedDirectory())

    def test_saved_fraction_rows_recheck_metric_and_normalization_identities(self):
        ledger = [{
            "player": "oop", "hand": "AhAs", "history": [],
            "input_row_sum_fraction": "1",
            "actions": [{
                "input_fraction": "1", "normalized_fraction": "1",
                "adjustment_fraction": "0",
            }],
        }]
        row = {
            "exact_metrics": {
                "value_oop": "0", "value_ip": "0",
                "oop_best_response_value": "2",
                "ip_best_response_value": "1",
                "oop_best_response_gain": "2",
                "ip_best_response_gain": "1",
                "nash_conv": "3", "exploitability": "3/2",
            },
            "lower_value_bound_fraction": "-1",
            "upper_value_bound_fraction": "2",
            "exact_nash_conv_threshold_met": False,
            "normalization_ledger": ledger,
            "normalization_ledger_sha256": auditor._sha256(auditor._canonical(ledger)),
            "maximum_row_adjustment_fraction": "0",
        }
        auditor._verify_fraction_row(row)
        broken = {**row, "exact_metrics": {**row["exact_metrics"],
                                            "nash_conv": "4"}}
        with self.assertRaisesRegex(ValueError, "metric fractions"):
            auditor._verify_fraction_row(broken)
        broken_ledger = {**row, "normalization_ledger": [dict(ledger[0]) ]}
        broken_ledger["normalization_ledger"][0]["actions"] = [{
            "input_fraction": "1", "normalized_fraction": "1",
            "adjustment_fraction": "1",
        }]
        broken_ledger["normalization_ledger_sha256"] = auditor._sha256(
            auditor._canonical(broken_ledger["normalization_ledger"]))
        with self.assertRaisesRegex(ValueError, "adjustment"):
            auditor._verify_fraction_row(broken_ledger)

    def test_self_consistent_but_wrong_saved_metrics_fail_recomputation_match(self):
        reference = {
            "backend": "matrix-free", "iterations": 1_000,
            "exact_metrics": {
                "value_oop": "0", "value_ip": "0",
                "oop_best_response_value": "2",
                "ip_best_response_value": "1",
                "oop_best_response_gain": "2",
                "ip_best_response_gain": "1",
                "nash_conv": "3", "exploitability": "3/2",
            },
            "lower_value_bound_fraction": "-1",
            "upper_value_bound_fraction": "2",
            "exact_nash_conv_threshold_met": False,
        }
        # This altered row remains internally consistent: it describes a
        # wider [-2, 2] interval, with matching metrics and threshold. It must
        # still fail because that is not the recomputed certificate.
        altered = {
            **reference,
            "exact_metrics": {
                "value_oop": "0", "value_ip": "0",
                "oop_best_response_value": "2",
                "ip_best_response_value": "2",
                "oop_best_response_gain": "2",
                "ip_best_response_gain": "2",
                "nash_conv": "4", "exploitability": "2",
            },
            "lower_value_bound_fraction": "-2",
        }
        auditor._verify_saved_row_matches_recomputation(reference, reference)
        with self.assertRaisesRegex(ValueError, "fresh replay and exact recomputation"):
            auditor._verify_saved_row_matches_recomputation(altered, reference)

    def test_gitattributes_keeps_this_certificate_rule_narrow(self):
        attrs = (auditor.ROOT / "benchmarks" / "results" / ".gitattributes").read_text()
        rules = [line.strip() for line in attrs.splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        expected = "full-deck-turn-rational-certificate-v1.json text eol=lf"
        self.assertEqual(rules.count(expected), 1)
        for rule in rules:
            pattern = rule.split()[0]
            self.assertNotIn("*", pattern, "broad wildcard attributes are not allowed")
            self.assertNotIn("?", pattern, "glob attributes are not allowed")


if __name__ == "__main__":
    unittest.main()
