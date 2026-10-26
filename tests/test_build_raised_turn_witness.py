import copy
import json
import os
import uuid
from contextlib import contextmanager, ExitStack
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

from scripts import build_raised_turn_witness as witness

SOURCE = witness.numeric_tail.POLICIES_DIR / witness._numeric_policy_name("materialized")
TEMP_ROOT = Path(__file__).resolve().parents[1] / "test-tmp"
TEMP_ROOT.mkdir(exist_ok=True)


@contextmanager
def scratch_directory():
    path = TEMP_ROOT / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        for current, dirs, files in os.walk(path, topdown=False):
            for name in files:
                (Path(current) / name).unlink()
            for name in dirs:
                (Path(current) / name).rmdir()
        path.rmdir()


def projection(policy):
    out = copy.deepcopy(policy)
    for row in out["strategy"]:
        for action in row["actions"]:
            action.pop("probability")
    return out


def synthetic_audit(metrics):
    return {
        "certificate": {
            "metrics": {"nash_conv": Fraction(0)},
            "normalization_ledger": [],
        },
        "full_numeric_metrics": metrics,
        "physical_worlds": 176,
        "physical_rows": 2404,
        "quotient_worlds": 12,
        "quotient_rows": 220,
    }


class RaisedTurnWitnessTests(unittest.TestCase):
    def test_actual_two_policy_bundle_publishes_and_replays_under_later_head(self):
        with scratch_directory() as tmp, ExitStack() as stack:
            for target in ('scripts.benchmark_turn_tail.capture',
                           'pokerlab.postflop_solver.solve_postflop',
                           'pokerlab.matrix_free_turn.solve_matrix_free_turn',
                           'pokerlab.postflop_solver.train_public_batched',
                           'pokerlab.matrix_free_turn.train_ranked_turn'):
                stack.enter_context(patch(target, side_effect=AssertionError('Production training called')))
            report, policies = Path(tmp) / 'report.json', Path(tmp) / 'policies'
            generated = witness.generate(report, policies)
            saved_bytes = report.read_bytes()
            rows = json.loads(saved_bytes)['results']
            self.assertEqual((generated['profiles'], generated['training_calls']), (2, 0))
            for row in rows:
                metrics = row['exact_certificate']['metrics']
                self.assertEqual(Fraction(metrics['nash_conv']), 0)
                self.assertEqual(Fraction(metrics['value_oop']), Fraction(-400, 21))
                self.assertEqual(set(row['full_physical_numeric_metrics']), set(witness.reference.METRICS))
            historical = json.loads(saved_bytes)['generation_git_commit']
            later = 'c' * 40 if historical != 'c' * 40 else 'd' * 40
            with patch.object(witness, 'current_head', return_value=later):
                replayed = witness.verify_saved(report, policies)
            self.assertEqual(replayed['report_sha256'], generated['report_sha256'])
            self.assertEqual(report.read_bytes(), saved_bytes)

    def load_materialized(self):
        raw = witness.capped(SOURCE, witness.MAX_POLICY_BYTES, "test input")
        return raw, json.loads(raw)

    def test_cleanup_is_nonmutating_and_preserves_all_legal_identity(self):
        raw, original = self.load_materialized()
        snapshot = copy.deepcopy(original)
        candidate, ledger = witness.cleanup_policy(original)
        self.assertEqual(original, snapshot)
        self.assertEqual(SOURCE.read_bytes(), raw)
        self.assertEqual(projection(candidate), projection(original))
        self.assertEqual(len(candidate["strategy"]), 2404)
        self.assertEqual(ledger["rows_changed"], 243)
        self.assertEqual(ledger["actions_changed"], 246)
        self.assertEqual(float.fromhex(ledger["max_absolute_probability_change_hex"]),
                         6.363731946721238e-20)

    def test_materialized_candidate_has_exact_zero_on_full_fixed_game(self):
        raw, original = self.load_materialized()
        candidate, ledger, metrics = witness._derived_candidate(
            "materialized", original, witness.sha(raw))
        audited = witness.exact_audit.audit_policy(candidate)
        witness._exact_zero(audited)
        self.assertEqual(audited["physical_worlds"], 176)
        self.assertEqual(audited["physical_rows"], 2404)
        self.assertEqual(audited["quotient_worlds"], 12)
        self.assertEqual(audited["quotient_rows"], 220)
        self.assertEqual(audited["certificate"]["work"], 9444)
        self.assertEqual(audited["certificate"]["metrics"]["nash_conv"], Fraction(0))
        self.assertTrue(audited["certificate"]["threshold_met"])
        self.assertEqual({key: metrics[key] for key in witness.reference.METRICS},
                         audited["full_numeric_metrics"])
        self.assertEqual(ledger["rows_total"], 2404)
        self.assertEqual(candidate["derived_provenance"]["source_policy_sha256"], witness.sha(raw))
        self.assertEqual(SOURCE.read_bytes(), raw)

    def test_matrix_free_candidate_has_exact_zero_on_full_fixed_game(self):
        source_path = witness.numeric_tail.POLICIES_DIR / witness._numeric_policy_name("matrix-free")
        raw = witness.capped(source_path, witness.MAX_POLICY_BYTES, "matrix-free test input")
        original = json.loads(raw)
        candidate, ledger, _ = witness._derived_candidate("matrix-free", original, witness.sha(raw))
        audited = witness.exact_audit.audit_policy(candidate)
        witness._exact_zero(audited)
        self.assertEqual(ledger["rows_changed"], 165)
        self.assertEqual(ledger["actions_changed"], 167)
        self.assertEqual(audited["physical_worlds"], 176)
        self.assertEqual(audited["physical_rows"], 2404)
        self.assertEqual(audited["certificate"]["work"], 9444)
        self.assertEqual(audited["certificate"]["metrics"]["nash_conv"], Fraction(0))
        self.assertEqual(source_path.read_bytes(), raw)

    def test_exact_nonzero_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "NashConv == 0"):
            witness._exact_zero({"certificate": {"metrics": {"nash_conv": Fraction(1, 10**9)}}})

    def test_both_empty_pins_refuse_generation_before_output_creation(self):
        with scratch_directory() as tmp, \
             patch.object(witness, "NUMERIC_REPORT_SHA256", ""), \
             patch.object(witness, "EXACT_TAIL_REPORT_SHA256", ""):
            report, policies = Path(tmp) / "report.json", Path(tmp) / "policies"
            with self.assertRaisesRegex(ValueError, "numeric tail report SHA-256 pin is empty"):
                witness.generate(report, policies)
            self.assertFalse(report.exists())
            self.assertFalse(policies.exists())
        with patch.object(witness, "NUMERIC_REPORT_SHA256", "a" * 64), \
             patch.object(witness, "EXACT_TAIL_REPORT_SHA256", ""):
            with self.assertRaisesRegex(ValueError, "exact tail report SHA-256 pin is empty"):
                witness._check_pins()

    def test_source_map_uses_full_proof_and_numeric_capture_paths(self):
        expected = (set(witness.exact_audit.SOURCES) |
                    set(witness.numeric_tail.REQUIRED_SOURCES) | set(witness.OPERATION_INPUTS) |
                    {"scripts/build_raised_turn_witness.py",
                     "tests/test_build_raised_turn_witness.py"})
        self.assertEqual(set(witness._source_files()), expected)

    def test_late_source_drift_is_detected(self):
        with patch.object(witness, "source_map", return_value={"s": "changed"}), \
             patch.object(witness, "current_head", return_value="same-head"):
            with self.assertRaisesRegex(ValueError, "Source files or Git HEAD changed"):
                witness._guards({"s": "original"}, "same-head", None, {}, None, None)

    def test_late_input_file_drift_is_detected(self):
        with patch.object(witness, "source_map", return_value={"s": "same"}), \
             patch.object(witness, "current_head", return_value="head"), \
             patch.object(witness, "capped", side_effect=[b"report", b"changed input"]):
            with self.assertRaisesRegex(ValueError, "input policy changed"):
                witness._guards({"s": "same"}, "head", b"report",
                                {"materialized": b"pinned input"}, None, None)

    def test_guard_drift_after_first_profile_stops_second_audit(self):
        zero_metrics = {name: 0.0 for name in witness.reference.METRICS}
        inputs = {backend: {} for backend in witness.BACKENDS}
        input_raws = {backend: backend.encode() for backend in witness.BACKENDS}
        load = (b"numeric", {"benchmark_id": "full-deck-raised-turn-tail-v1"},
                inputs, input_raws, b"reference", b"exact")
        with patch.object(witness, "source_map", return_value={"source": "frozen"}), \
             patch.object(witness, "current_head", return_value="a" * 40), \
             patch.object(witness, "_load_inputs", return_value=load), \
             patch.object(witness, "_derived_candidate", return_value=({}, {}, zero_metrics)), \
             patch.object(witness, "_guards", side_effect=[None, None, ValueError("late drift")]), \
             patch.object(witness.exact_audit, "audit_policy", return_value=synthetic_audit(zero_metrics)) as audit:
            with self.assertRaisesRegex(ValueError, "late drift"):
                witness._reconstruct()
            self.assertEqual(audit.call_count, 1)

    def test_saved_bundle_replays_historical_generation_under_new_current_head(self):
        historical, current = "a" * 40, "b" * 40
        metrics = {name: 0.25 for name in witness.reference.METRICS}
        saved_metrics = {name: value + 5e-13 for name, value in metrics.items()}
        expected_full = {**metrics, "pair_probabilities": {"pair": 0.5}, "checked_rows": 2404}
        saved_full = {**saved_metrics,
                      "pair_probabilities": {"pair": 0.5 + 5e-13}, "checked_rows": 2404}
        expected_policy = {**metrics, "strategy": [], "derived_provenance": {"fixed": True}}
        saved_policy = {**saved_metrics, "strategy": [], "derived_provenance": {"fixed": True}}
        expected_policies = {}
        saved_policies = {}
        expected_rows = []
        saved_rows = []
        certificate = witness.fraction_json(synthetic_audit(metrics)["certificate"])
        for backend in witness.BACKENDS:
            name = witness.POLICY_NAMES[backend]
            expected_bytes = witness.canonical(expected_policy)
            saved_bytes = witness.canonical(saved_policy)
            expected_policies[name] = expected_bytes
            saved_policies[name] = saved_bytes
            base = {
                "backend": backend,
                "policy_file": name,
                "exact_certificate": certificate,
                "canonical_normalized_rows": [],
                "exact_nash_conv": "0",
                "threshold_met": True,
            }
            expected_rows.append({**base, "policy_sha256": witness.sha(expected_bytes),
                                  "full_physical_numeric_metrics": expected_full})
            saved_rows.append({**base, "policy_sha256": witness.sha(saved_bytes),
                               "full_physical_numeric_metrics": saved_full})
        expected_report = {"schema_version": 1, "generation_git_commit": historical,
                           "source_sha256": {"proof": "pinned"}, "results": expected_rows}
        saved_report = {"schema_version": 1, "generation_git_commit": historical,
                        "source_sha256": {"proof": "pinned"}, "results": saved_rows}
        expected_report_bytes = witness.canonical(expected_report)
        saved_report_bytes = witness.canonical(saved_report)

        def reconstruct(*, generation_git_commit=None):
            self.assertEqual(generation_git_commit, historical)
            return expected_report_bytes, expected_policies

        with scratch_directory() as tmp:
            root = Path(tmp)
            report = root / "report.json"
            paths = {}
            report.write_bytes(saved_report_bytes)
            for name, raw in saved_policies.items():
                path = root / name
                path.write_bytes(raw)
                paths[name] = path
            with patch.object(witness, "_check_pins"), \
                 patch.object(witness, "source_map", return_value={"proof": "pinned"}), \
                 patch.object(witness, "current_head", return_value=current), \
                 patch.object(witness, "_load_inputs",
                              return_value=(b"numeric", {}, {}, {}, b"reference", b"exact")), \
                 patch.object(witness, "_guards"), \
                 patch.object(witness, "_reconstruct", side_effect=reconstruct), \
                 patch.object(witness.exact_audit, "audit_policy",
                              return_value=synthetic_audit(metrics)):
                result = witness.verify_bundle(report, paths)
            self.assertEqual(result["status"], "VERIFIED_RAISED_TURN_CLEAN_WITNESSES")
            self.assertNotEqual(historical, current)
            self.assertEqual(report.read_bytes(), saved_report_bytes)
            for name, raw in saved_policies.items():
                self.assertEqual(paths[name].read_bytes(), raw)
            first_name = witness.POLICY_NAMES[witness.BACKENDS[0]]
            first_path = paths[first_name]
            first_policy_bytes = first_path.read_bytes()
            tampered_report = copy.deepcopy(saved_report)
            tampered_report["results"][0]["exact_nash_conv"] = "1/10"
            report.write_bytes(witness.canonical(tampered_report))
            with patch.object(witness, "_check_pins"), \
                 patch.object(witness, "source_map", return_value={"proof": "pinned"}), \
                 patch.object(witness, "current_head", return_value=current), \
                 patch.object(witness, "_load_inputs",
                              return_value=(b"numeric", {}, {}, {}, b"reference", b"exact")), \
                 patch.object(witness, "_guards"), \
                 patch.object(witness, "_reconstruct", side_effect=reconstruct), \
                 patch.object(witness.exact_audit, "audit_policy",
                              return_value=synthetic_audit(metrics)):
                with self.assertRaisesRegex(ValueError, "exact threshold observation"):
                    witness.verify_bundle(report, paths)
            report.write_bytes(saved_report_bytes)
            changed_policy = json.loads(first_policy_bytes)
            changed_policy["derived_provenance"]["fixed"] = False
            changed_policy_bytes = witness.canonical(changed_policy)
            first_path.write_bytes(changed_policy_bytes)
            tampered_report = copy.deepcopy(saved_report)
            tampered_report["results"][0]["policy_sha256"] = witness.sha(changed_policy_bytes)
            report.write_bytes(witness.canonical(tampered_report))
            with patch.object(witness, "_check_pins"), \
                 patch.object(witness, "source_map", return_value={"proof": "pinned"}), \
                 patch.object(witness, "current_head", return_value=current), \
                 patch.object(witness, "_load_inputs",
                              return_value=(b"numeric", {}, {}, {}, b"reference", b"exact")), \
                 patch.object(witness, "_guards"), \
                 patch.object(witness, "_reconstruct", side_effect=reconstruct), \
                 patch.object(witness.exact_audit, "audit_policy",
                              return_value=synthetic_audit(metrics)):
                with self.assertRaisesRegex(ValueError, "policy strategy, probabilities, or metadata differ"):
                    witness.verify_bundle(report, paths)

    def test_first_policy_late_drift_is_detected_after_replays(self):
        with scratch_directory() as tmp:
            path = Path(tmp) / "first-policy.json"
            path.write_bytes(b"verified bytes")
            with patch.object(witness, "capped", return_value=b"changed bytes"):
                with self.assertRaisesRegex(ValueError, "changed after verification"):
                    witness._verify_observed_policy_bytes({"first": path}, {"first": b"verified bytes"})

    def test_publish_verifier_failure_rolls_back_owned_files_only(self):
        payloads = {name: f"candidate:{name}".encode() for name in witness.POLICY_NAMES.values()}
        report_bytes = witness.canonical({"synthetic_harness": True})
        with scratch_directory() as tmp:
            root = Path(tmp)
            report, policies = root / "report.json", root / "policies"
            policies.mkdir()
            unrelated = policies / "unrelated.txt"
            unrelated.write_text("keep", encoding="utf-8")
            with patch.object(witness, "_check_pins"), \
                 patch.object(witness, "_reconstruct", return_value=(report_bytes, payloads)), \
                 patch.object(witness, "verify_bundle"), \
                 patch.object(witness, "verify_saved", side_effect=RuntimeError("injected verifier failure")):
                with self.assertRaisesRegex(RuntimeError, "injected verifier failure"):
                    witness.generate(report, policies)
            self.assertFalse(report.exists())
            self.assertFalse(any((policies / name).exists() for name in payloads))
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
