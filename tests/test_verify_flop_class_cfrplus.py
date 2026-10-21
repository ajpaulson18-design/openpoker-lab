"""Fast rejection tests for saved fixed-flop CFR+ policy artifacts."""
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from scripts import flop_class_cfrplus as trainer
from scripts import verify_flop_class_cfrplus as verifier
from scripts import flop_public_classes as proof


def _raw_rows(count=466):
    return [[0, "AdAs", [f"h{i}"], [0.5, 0.5]] for i in range(count)]


def _report(**overrides):
    report = {
        "schema_version": "fixed-flop-class-cfrplus-v1",
        "status": "trained-policy-physically-verified",
        "source_lf_sha256": {"pinned": "hash"},
        "artifact_sha256": "",
    }
    report.update(overrides)
    unsigned = {key: value for key, value in report.items() if key != "artifact_sha256"}
    report["artifact_sha256"] = proof._digest(unsigned)
    return report


def _valid_request_report(raw_rows=None, **overrides):
    raw_rows = _raw_rows() if raw_rows is None else raw_rows
    normalized, audit = verifier.policy.canonicalize_binary_rows(verifier._raw_rows(raw_rows))
    del normalized
    report = {
        "schema_version": "fixed-flop-class-cfrplus-v1",
        "status": "trained-policy-physically-verified",
        "source_lf_sha256": {"pinned": "hash"},
        "admission": trainer.admit_request(1),
        "physical_policy": {
            "iterations": 1,
            "algorithm": "cfrplus",
            "averaging_delay": 0,
            "research_adapter": "fixed-flop-public-classes-cfrplus-v1",
        },
        "raw_class_policy": raw_rows,
        "normalization": audit,
        "proof_receipt": {"receipt": "ok"},
        "census": {},
        "maximum_world_path_states": 1,
        "audit": {},
        "preparation_forbidden_calls": {},
        "diagnostic_forbidden_calls": {},
        "quality_target": 0.005,
        "quality_target_met": True,
    }
    report.update(overrides)
    unsigned = {key: value for key, value in report.items() if key != "artifact_sha256"}
    report["artifact_sha256"] = proof._digest(unsigned)
    return report


def _save_report(path, report):
    path.write_text(json.dumps(report), encoding="utf-8")


class VerifyFlopClassCFRPlusTests(unittest.TestCase):
    def test_raw_rows_reject_bad_keys_and_oversized_or_missing_tables(self):
        good = _raw_rows()
        for bad_row in (
            [True, "AdAs", ["h"], [0.5, 0.5]],
            [0, "bad", ["h"], [0.5, 0.5]],
            [0, "AdAs", ["x" * 65], [0.5, 0.5]],
        ):
            rows = [list(row) for row in good]
            rows[0] = bad_row
            with self.subTest(row=bad_row), self.assertRaises(ValueError):
                verifier._raw_rows(rows)
        for rows in (_raw_rows(465), _raw_rows(467)):
            with self.subTest(row_count=len(rows)), self.assertRaises(ValueError):
                verifier._raw_rows(rows)

    def test_raw_rows_reject_duplicate_information_set(self):
        rows = _raw_rows()
        rows[-1] = list(rows[0])
        with self.assertRaisesRegex(ValueError, "Duplicate raw compact"):
            verifier._raw_rows(rows)

    def test_malformed_json_rejects_before_publication_or_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "malformed.json"
            path.write_text('{"schema_version":', encoding="utf-8")
            with patch.object(verifier.publication, "verify",
                              side_effect=AssertionError("publication")) as publication, \
                 patch.object(verifier.proof, "build_model",
                              side_effect=AssertionError("tree")) as build:
                with self.assertRaises(json.JSONDecodeError):
                    verifier.verify_saved(path)
            publication.assert_not_called()
            build.assert_not_called()

    def test_duplicate_json_field_rejects_before_publication_or_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "duplicate.json"
            path.write_text(
                '{"schema_version":"fixed-flop-class-cfrplus-v1",'
                '"schema_version":"fixed-flop-class-cfrplus-v1"}', encoding="utf-8")
            with patch.object(verifier.publication, "verify",
                              side_effect=AssertionError("publication")) as publication, \
                 patch.object(verifier.proof, "build_model",
                              side_effect=AssertionError("tree")) as build:
                with self.assertRaisesRegex(ValueError, "Duplicate report JSON"):
                    verifier.verify_saved(path)
            publication.assert_not_called()
            build.assert_not_called()

    def test_checksum_mismatch_rejects_before_source_publication_or_tree(self):
        report = _report()
        report["artifact_sha256"] = "bad"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "checksum.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            with patch.object(verifier.trainer, "_source_hashes",
                              side_effect=AssertionError("sources")) as sources, \
                 patch.object(verifier.publication, "verify",
                              side_effect=AssertionError("publication")) as publication, \
                 patch.object(verifier.proof, "build_model",
                              side_effect=AssertionError("tree")) as build:
                with self.assertRaisesRegex(ValueError, "checksum"):
                    verifier.verify_saved(path)
            sources.assert_not_called()
            publication.assert_not_called()
            build.assert_not_called()

    def test_source_mismatch_rejects_before_publication_or_tree(self):
        report = _report()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            with patch.object(verifier.trainer, "_source_hashes", return_value={"other": "source"}), \
                 patch.object(verifier.publication, "verify",
                              side_effect=AssertionError("publication")) as publication, \
                 patch.object(verifier.proof, "build_model",
                              side_effect=AssertionError("tree")) as build:
                with self.assertRaisesRegex(ValueError, "executable sources"):
                    verifier.verify_saved(path)
            publication.assert_not_called()
            build.assert_not_called()

    def test_invalid_request_rejects_before_publication_or_tree(self):
        report = _report(
            source_lf_sha256={"pinned": "hash"},
            admission={},
            physical_policy={"iterations": 141},
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "request.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            with patch.object(verifier.trainer, "_source_hashes", return_value={"pinned": "hash"}), \
                 patch.object(verifier.publication, "verify",
                              side_effect=AssertionError("publication")) as publication, \
                 patch.object(verifier.proof, "build_model",
                              side_effect=AssertionError("tree")) as build:
                with self.assertRaises(ValueError):
                    verifier.verify_saved(path)
            publication.assert_not_called()
            build.assert_not_called()

    def test_malformed_history_container_is_rejected(self):
        rows = _raw_rows()
        rows[0][2] = "history-is-not-a-list"
        # The saved JSON contract represents histories as arrays.
        with self.assertRaises((TypeError, ValueError)):
            verifier._raw_rows(rows)

    def test_noncanonical_raw_hand_rejects_before_publication_or_tree(self):
        rows = _raw_rows()
        rows[0][1] = "1xAs"
        report = _valid_request_report.__wrapped__(rows) if hasattr(_valid_request_report, "__wrapped__") else None
        # Raw hand validation is part of the early canonicalization pass.
        report = {
            "schema_version": "fixed-flop-class-cfrplus-v1",
            "status": "trained-policy-physically-verified",
            "source_lf_sha256": {"pinned": "hash"},
            "admission": trainer.admit_request(1),
            "physical_policy": {"iterations": 1, "algorithm": "cfrplus", "averaging_delay": 0,
                                "research_adapter": "fixed-flop-public-classes-cfrplus-v1"},
            "raw_class_policy": rows,
        }
        report["artifact_sha256"] = proof._digest(report)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad-hand.json"
            _save_report(path, report)
            with patch.object(verifier.trainer, "_source_hashes", return_value={"pinned": "hash"}), \
                 patch.object(verifier.publication, "verify",
                              side_effect=AssertionError("publication")) as publication, \
                 patch.object(verifier.proof, "build_model",
                              side_effect=AssertionError("tree")) as build:
                with self.assertRaises(ValueError):
                    verifier.verify_saved(path)
            publication.assert_not_called()
            build.assert_not_called()

    def test_bool_averaging_delay_rejects_before_publication_or_tree(self):
        report = _valid_request_report()
        report["physical_policy"]["averaging_delay"] = False
        unsigned = {key: value for key, value in report.items() if key != "artifact_sha256"}
        report["artifact_sha256"] = proof._digest(unsigned)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bool-delay.json"
            _save_report(path, report)
            with patch.object(verifier.trainer, "_source_hashes", return_value={"pinned": "hash"}), \
                 patch.object(verifier.publication, "verify",
                              side_effect=AssertionError("publication")) as publication, \
                 patch.object(verifier.proof, "build_model",
                              side_effect=AssertionError("tree")) as build:
                with self.assertRaisesRegex(ValueError, "training method"):
                    verifier.verify_saved(path)
            publication.assert_not_called()
            build.assert_not_called()

    def test_receipt_type_mismatch_rejects_before_model_build(self):
        report = _valid_request_report(proof_receipt={"receipt": True})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "receipt.json"
            _save_report(path, report)
            with patch.object(verifier.trainer, "_source_hashes", return_value={"pinned": "hash"}), \
                 patch.object(verifier.publication, "verify", return_value={"receipt": 1}), \
                 patch.object(verifier.proof, "build_model",
                              side_effect=AssertionError("tree")) as build:
                with self.assertRaisesRegex(ValueError, "proof receipt"):
                    verifier.verify_saved(path)
            build.assert_not_called()

    def test_bool_path_state_count_rejects_before_policy_projection(self):
        report = _valid_request_report(maximum_world_path_states=True)
        infos = {tuple([row[0], row[1], tuple(row[2])]): 2
                 for row in report["raw_class_policy"]}
        model = SimpleNamespace(census={})

        @contextmanager
        def guard():
            yield {}

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bool-path-count.json"
            _save_report(path, report)
            with patch.object(verifier.trainer, "_source_hashes", return_value={"pinned": "hash"}), \
                 patch.object(verifier.publication, "verify", return_value={"receipt": "ok"}), \
                 patch.object(verifier.proof, "independent_guard", side_effect=guard), \
                 patch.object(verifier.proof, "build_model", return_value=model), \
                 patch.object(verifier.trainer, "_training_inputs", return_value=((), infos, 1)), \
                 patch.object(verifier.proof, "project_policy",
                              side_effect=AssertionError("projection")) as project:
                with self.assertRaisesRegex(ValueError, "compact model"):
                    verifier.verify_saved(path)
            project.assert_not_called()


if __name__ == "__main__":
    unittest.main()
