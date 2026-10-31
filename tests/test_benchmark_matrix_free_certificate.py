"""Saved-certificate runner controls; no saved-study mathematics are run here."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import benchmark_matrix_free_certificate as runner
from scripts import exact_selected_matrix_free_certificate as candidate
from scripts import four_street_certificate_v3 as literal
from tests.test_exact_selected_matrix_free_certificate import _compact, _literal_payload
from tests.test_four_street_validation import CASE
from tests.test_four_street_certificate import _case


def _synthetic_sample(case=None):
    case = json.loads(json.dumps(CASE if case is None else case))
    _, payload = _compact(case)
    payload_raw = runner._canonical(payload)
    payload_sha = runner._sha(payload_raw)
    label = "synthetic-original-t10"
    sample = {"artifact": label + ".raw.json", "case": label, "iterations": 10,
        "native_payoffs": "board-sweep", "native_traversal": "active-frames",
        "routing": "indexed", "sample": 0, "traced": False,
        "request_case": case, "native_admission": "indexed-v1",
        "counts": {"native_invoke": 1, "world": 0, "pair": 0},
        "native_observations": {"learning_completed": True, "rank_calls": 0},
        "payload_sha256": payload_sha, "payload_bytes": len(payload_raw)}
    raw = {**{key: sample[key] for key in (
        "case", "iterations", "native_payoffs", "native_traversal", "routing", "sample",
        "traced", "request_case", "native_admission", "counts", "native_observations",
        "payload_sha256", "payload_bytes")}, "status": "complete", "failure": None,
        "payload": payload}
    literal_exact = literal.evaluate_exact(case, _literal_payload(case, payload))
    old_exact = candidate.evaluate_exact(case, payload)
    if (old_exact["metrics"] != literal_exact["metrics"] or
            old_exact["normalized_policy_sha256"] != literal_exact["normalized_policy_sha256"] or
            old_exact["threshold_met"] != literal_exact["threshold_met"]):
        raise AssertionError("synthetic candidate does not match unchanged v3 oracle")
    verification = {"exact": {"status": "complete", "result": {
        "contract": "compact-exact-product-certificate-v1", "exact_certificate": literal_exact,
        "compact_input_canonical_sha256": payload_sha,
        "verification_expansion_canonical_sha256": literal_exact["input_policy_canonical_sha256"],
        "production_pair_rows": 0, "training_calls": 0, "native_calls": 0}},
        "numeric": {"status": "complete", "result": {"checked_information_sets": payload["info_sets"]}},
        "numeric_metric_gaps": {key: 0.0 for key in runner.METRICS}}
    return label, case, payload, sample, raw, verification, literal_exact


class SavedCertificateRunnerTests(unittest.TestCase):
    def test_fixed_schedule_and_historical_partition_have_expected_complete_sets(self):
        self.assertEqual(len(runner.FIXED_LABELS), 34)
        report = {"source_commit": runner.PRODUCER_COMMIT,
            "calls_planned": 34, "calls_attempted": 34, "calls_captured": 34,
            "failure": None, "samples": []}
        for case, iterations, mode, sample in runner._FIXED_ENTRIES:
            label = f"{case}-t{iterations}-{mode}-p{sample}"
            report["samples"].append({"artifact": label + ".raw.json",
                "status": "native-resource-rejected" if label in runner.PRODUCER_REJECTIONS else "complete"})
        samples, complete, rejected = runner._partition_inventory(report)
        self.assertEqual(len(samples), 34)
        self.assertEqual(len(complete), 28)
        self.assertEqual(set(rejected), runner.PRODUCER_REJECTIONS)
        self.assertEqual(len(runner.OLD_EXACT_UNKNOWN), 6)
        self.assertTrue(runner.OLD_EXACT_UNKNOWN <= set(complete))
        bad = deepcopy(report)
        bad["samples"].pop()
        with self.assertRaisesRegex(ValueError, "identity/status"):
            runner._partition_inventory(bad)

    def test_budget_labeled_resource_errors_are_distinct_from_structure_errors(self):
        for message in (
            "blocker: certificate integer bit limit exceeded",
            "terminal: certificate cumulative integer bit limit exceeded",
            "certificate work limit exceeded",
            "host: certificate entry limit exceeded",
            "Fraction text integer bit limit exceeded",
            "certificate JSON node/depth limit exceeded",
        ):
            with self.subTest(message=message):
                self.assertTrue(runner._known_resource_error(ValueError(message)))
        for message in ("unsupported input", "certificate policy rows mismatch",
                        "parser: escape capricious value", "certificate inputs malformed",
                        "Fraction text exceeded its forecast", "canonical JSON exceeded its ASCII forecast",
                        "public graph exceeded its admitted node census"):
            with self.subTest(message=message):
                self.assertFalse(runner._known_resource_error(ValueError(message)))
        self.assertFalse(runner._known_resource_error(RuntimeError("certificate work limit exceeded")))

    def test_large_exact_fraction_metrics_parse_without_global_digit_limit_changes(self):
        digits = "1" + "0" * 5000
        parsed = runner._parse_bounded_fraction(digits + "/" + digits)
        self.assertEqual(parsed.numerator, 1)
        self.assertEqual(parsed.denominator, 1)
        exact = {key: "1/1" for key in (
            "value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value",
            "sb_best_response_gain", "bb_best_response_gain", "nash_conv", "exploitability",
            "lower_value_bound", "upper_value_bound")}
        exact["value_sb"] = digits + "/" + digits
        gaps = runner._metric_gaps({"metrics": exact}, {key: 1.0 for key in runner.METRICS})
        self.assertEqual(gaps["value_sb"], 0.0)

    def test_exact_metric_fraction_parser_rejects_oversize_or_noncanonical_inputs(self):
        for text in ("1e0/1", "NaN/1", "01/1", "1/0", "1/-2", "-0", "-0/2",
                     "00", "01", "-01", "+1", " 0", "0 ",
                     "1" + "0" * (runner._MAX_DECIMAL_DIGITS + 1) + "/1"):
            with self.subTest(text=text[:30]), self.assertRaises(ValueError):
                runner._parse_bounded_fraction(text)
        with self.assertRaisesRegex(ValueError, "65536-bit"):
            runner._parse_bounded_fraction("9" * runner._MAX_DECIMAL_DIGITS + "/1")

    def test_integer_and_zero_exact_metrics_match_historical_format(self):
        for text, expected in (("0", 0), ("1", 1), ("-13", -13)):
            self.assertEqual(runner._parse_bounded_fraction(text), expected)
        exact = {key: "0" for key in (*runner.EXACT_TO_NUMERIC,
                                     "lower_value_bound", "upper_value_bound")}
        gaps = runner._metric_gaps({"metrics": exact}, {key: 0.0 for key in runner.METRICS})
        self.assertEqual(set(gaps.values()), {0.0})

    def test_source_and_build_provenance_files_exist_before_project_import_hook(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            output = Path(outside) / "certificate-run"
            producer_repo = Path(temporary) / "producer"
            study = Path(temporary) / "study"
            review = Path(temporary) / "review"
            current = {"root": "current", "commit": "c" * 40, "status": "", "sha256": {},
                "tree_blob_oid": {}, "git_normalized_blob_oid": {}, "closure_count": 0}
            producer = {"root": "producer", "commit": runner.PRODUCER_COMMIT, "status": "", "sha256": {},
                "tree_blob_oid": {}, "git_normalized_blob_oid": {}, "closure_count": 0}
            saved = {"proof": {"schema": "proof"}, "build_identity": {"schema": "build"},
                "complete": [], "samples": {}, "previous": {}}
            def dependencies_after_auth():
                for name in ("source-before.json", "producer-source-before.json",
                             "producer-artifact-auth.json", "producer-build-identity.json",
                             "protocol.json"):
                    self.assertTrue((output / name).is_file(), name)
                raise RuntimeError("intentional dependency-hook sentinel")
            with patch.object(runner, "_tree_identity", side_effect=[current, producer, current, producer]), \
                 patch.object(runner, "_tree_identity_shallow", side_effect=[
                     (current["commit"], current["status"], current["sha256"]),
                     (producer["commit"], producer["status"], producer["sha256"])]), \
                 patch.object(runner, "_authenticate_saved", return_value=saved), \
                 patch.object(runner, "_artifact_hashes", return_value=({}, {}, {})), \
                 patch.object(runner, "_dependencies_after_auth", side_effect=dependencies_after_auth):
                result = runner.run(output, producer_repo=producer_repo, study=study, review=review)
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(result["failure"]["message"], "intentional dependency-hook sentinel")
            self.assertTrue((output / "source-before.json").is_file())
            self.assertTrue((output / "producer-build-identity.json").is_file())

    def test_real_certificate_parent_row_flow_without_producer_or_old_decoder_patches(self):
        self._parent_row_flow()

    def test_real_parent_flow_accepts_zero_gain_integer_metrics(self):
        self._parent_row_flow(_case(stacks=(0.5, 1)))

    def _parent_row_flow(self, case=None):
        label, case, payload, sample, raw, verification, _old_exact = _synthetic_sample(case)
        if case["config"]["starting_stack"] == [0.5, 1]:
            self.assertIn("0", _old_exact["metrics"].values())
        with tempfile.TemporaryDirectory() as temporary:
            study = Path(temporary) / "study"
            output = Path(temporary) / "out"
            study.mkdir()
            raw_path = study / sample["artifact"]
            verification_path = study / (label + "-verification.json")
            raw_bytes = runner._json_bytes(raw)
            verification_bytes = runner._json_bytes(verification)
            raw_path.write_bytes(raw_bytes)
            verification_path.write_bytes(verification_bytes)
            sample["source_raw_sha256"] = runner._sha(raw_bytes)
            prior = {"status": "complete", "verification": verification,
                "artifact": verification_path.name, "artifact_sha256": runner._sha(verification_bytes),
                "source_raw_sha256": runner._sha(raw_bytes)}
            deps = runner._dependencies()
            calls = {key: 0 for key in ("solver", "prepare", "trainer", "packed_trainer",
                "production_kernel", "native", "native_train", "production_rank")}
            captured = {}
            def capture(name, content):
                self.assertNotIn(name, captured)
                path = output / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                captured[name] = content
                return runner._sha(content)
            def check_captured():
                runner._check_captured(output, {name: runner._sha(content) for name, content in captured.items()})
            with runner._protected(deps, calls):
                record, outcome, failure = runner._run_one(label, sample, prior, study, output,
                    deps, calls, capture, "b" * 64, check_captured)
            self.assertIsNone(failure)
            self.assertEqual(record["status"], "complete")
            self.assertEqual(record["producer_build_identity_sha256"], "b" * 64)
            self.assertEqual(record["old_exact_comparison"]["all_exact_metrics_identical"], True)
            self.assertTrue(all(value <= runner.NUMERIC_TOLERANCE for value in outcome["gaps"].values()))
            self.assertEqual(set(calls.values()), {0})
            self.assertIn(f"results/{label}-result.json", captured)
            self.assertIn(f"numeric/{label}-replay.json", captured)
            self.assertIn(f"records/{label}-certificate.json", captured)
            self.assertEqual(runner._decode(captured[f"records/{label}-certificate.json"])["status"], "complete")

    def test_tampered_prior_verification_is_rejected_before_candidate_certificate(self):
        label, _case, _payload, sample, raw, verification, _old_exact = _synthetic_sample()
        with tempfile.TemporaryDirectory() as temporary:
            study = Path(temporary) / "study"
            study.mkdir()
            raw_bytes = runner._json_bytes(raw)
            (study / sample["artifact"]).write_bytes(raw_bytes)
            verification_path = study / (label + "-verification.json")
            verification_path.write_bytes(runner._json_bytes(verification))
            sample["source_raw_sha256"] = runner._sha(raw_bytes)
            prior = {"status": "complete", "verification": verification,
                "artifact": verification_path.name, "artifact_sha256": "0" * 64,
                "source_raw_sha256": runner._sha(raw_bytes)}
            deps = runner._dependencies()
            calls = {key: 0 for key in ("solver", "prepare", "trainer", "packed_trainer",
                "production_kernel", "native", "native_train", "production_rank")}
            with patch.object(deps.certificate, "evaluate_exact",
                              side_effect=AssertionError("candidate entered before old-byte check")):
                with self.assertRaisesRegex(ValueError, "old verification SHA"):
                    runner._run_one(label, sample, prior, study, Path(temporary), deps, calls,
                                    lambda *_: "unused", "c" * 64, lambda: None)

    def test_exact_policy_comparison_binds_case_but_not_compact_input_representation(self):
        _label, case, payload, _sample, _raw, _verification, old_exact = _synthetic_sample()
        new_exact = candidate.evaluate_exact(case, payload)
        self.assertTrue(runner._compare_old_exact(new_exact, old_exact)["verified"])
        forged = deepcopy(new_exact)
        forged["legacy_model_case_canonical_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "input-case canonical hashes"):
            runner._compare_old_exact(forged, old_exact)

    def test_old_compact_and_expanded_fingerprints_are_bound_at_their_own_levels(self):
        _label, _case, _payload, sample, raw, verification, old = _synthetic_sample()
        self.assertNotEqual(sample["payload_sha256"], old["input_policy_canonical_sha256"])
        runner._validate_old_exact_binding(verification, sample, raw)
        broken = deepcopy(verification)
        broken["exact"]["result"]["compact_input_canonical_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "provenance"):
            runner._validate_old_exact_binding(broken, sample, raw)

    def test_capture_time_pin_rejects_saved_result_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); path = root / "result.json"
            path.write_bytes(b"original")
            pins = {"result.json": runner._sha(b"original")}
            runner._check_captured(root, pins)
            path.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "capture-time"):
                runner._check_captured(root, pins)

    def test_mutation_on_budget_failure_is_fatal_and_original_error_is_retained(self):
        label, _case, _payload, sample, raw, verification, _old = _synthetic_sample()
        with tempfile.TemporaryDirectory() as temporary:
            study = Path(temporary) / "study"; study.mkdir()
            output = Path(temporary) / "out"; output.mkdir()
            raw_bytes = runner._json_bytes(raw); prior_bytes = runner._json_bytes(verification)
            (study / sample["artifact"]).write_bytes(raw_bytes)
            name = label + "-verification.json"; (study / name).write_bytes(prior_bytes)
            sample["source_raw_sha256"] = runner._sha(raw_bytes)
            prior = {"status": "complete", "verification": verification, "artifact": name,
                     "artifact_sha256": runner._sha(prior_bytes)}
            captured = {}
            def capture(name, content):
                runner._check_captured(output, captured)
                path = output / name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content); captured[name] = runner._sha(content)
                return captured[name]
            def mutate_then_fail(_case, payload):
                payload["unexpected_mutation"] = True
                raise ValueError("certificate work limit exceeded")
            deps = runner._dependencies()
            with patch.object(deps.certificate, "evaluate_exact", side_effect=mutate_then_fail):
                record, outcome, failure = runner._run_one(label, sample, prior, study, output,
                    deps, {}, capture, "b" * 64, lambda: runner._check_captured(output, captured))
            self.assertEqual(record["status"], "failed")
            self.assertIsNone(outcome)
            self.assertIn("mutated", failure["message"])
            self.assertEqual(runner._decode((output / f"errors/{label}-error.json").read_bytes())["message"],
                             "certificate work limit exceeded")
            self.assertEqual((study / sample["artifact"]).read_bytes(), raw_bytes)


if __name__ == "__main__":
    unittest.main()
