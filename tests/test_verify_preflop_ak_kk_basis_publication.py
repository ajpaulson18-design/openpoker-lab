"""Saved AK/KK publication tests; no native build or numerical counting."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_preflop_ak_kk_basis_publication as publication
from scripts import preflop_publication_source_history as source_history


class SavedAKKKBasisPublicationTests(unittest.TestCase):
    def test_actual_corpus_authenticates_without_build_or_count_calls(self):
        stable = {"revision": publication.FROZEN_REVISION, "status": [],
                  "source_lf_sha256": "synthetic-source-attestation",
                  "current_context_lf_sha256": {}, "unmeasured_current_lf_sha256": {}}
        with (patch.object(publication, "_current_source_check", return_value=stable),
              patch.object(publication.five, "verify_saved", wraps=publication.five.verify_saved) as saved_verify,
              patch.object(publication.reference, "reference_preflop_counts",
                           side_effect=AssertionError("not called")),
              patch.object(publication.evidence.native, "prepare_native_preflop_equities",
                           side_effect=AssertionError("not called")),
              patch.object(publication.five, "backend", side_effect=AssertionError("build lookup")),
              patch.object(publication.five, "validate_five_dump",
                           side_effect=AssertionError("no rank replay")),
              patch("pokerlab.cfr_plus.train", side_effect=AssertionError("no training"))):
            result = publication.verify()
        saved_paths = {Path(call.args[0]) for call in saved_verify.call_args_list}
        self.assertEqual(saved_paths, {
            publication.ROOT / "benchmarks/results/preflop-five-basis-v1.json",
            publication.PUBLICATION / "aa-conformance-report.json"})
        self.assertEqual(result["status"], "authenticated-saved-counts-only")
        self.assertEqual(result["numerical_subprocesses_recorded"], 7)
        self.assertEqual(result["current_numerical_subprocesses"], 0)
        self.assertEqual(result["source_files_authenticated"], 783)
        self.assertFalse(result["equities_claimed"])
        self.assertFalse(result["counts_generated"])

    def test_requested_copy_is_used_instead_of_the_default_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            copied = Path(temp) / "copy"
            shutil.copytree(publication.PUBLICATION, copied)
            stable = {"revision": publication.FROZEN_REVISION, "status": [],
                      "source_lf_sha256": "stable", "current_context_lf_sha256": {},
                      "unmeasured_current_lf_sha256": {}}
            with (patch.object(publication, "PUBLICATION", Path(temp) / "must-not-read"),
                  patch.object(publication, "_current_source_check", return_value=stable)):
                self.assertEqual(publication.verify(copied)["benchmark_id"],
                                 "preflop-ak-kk-basis-v1")

    def test_index_raw_pin_rejects_mutation_before_json_parse(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "index.json").write_bytes(b"x" * publication.INDEX_BYTES)
            with patch.object(publication, "_json",
                               side_effect=AssertionError("index parsed before raw pin")):
                with self.assertRaisesRegex(ValueError, "Raw file pin differs"):
                    publication._validate_index(root)

    def test_report_raw_pin_rejects_mutation_before_parse(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(publication.PUBLICATION, root / "copy")
            report = root / "copy" / "report.json"
            raw = report.read_bytes()
            report.write_bytes(b"x" + raw[1:])
            original = publication._json
            def index_only(data):
                if len(data) != publication.INDEX_BYTES:
                    raise AssertionError("report parsed before raw pin")
                return original(data)
            with patch.object(publication, "_json", side_effect=index_only):
                with self.assertRaisesRegex(ValueError, "Raw file pin differs"):
                    publication.verify(root / "copy")

    def test_duplicate_and_nonfinite_json_are_rejected(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}'):
            with self.subTest(raw=raw), self.assertRaises((ValueError, OverflowError)):
                publication._json(raw)

    def test_unexpected_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "copy"
            shutil.copytree(publication.PUBLICATION, root)
            (root / "extra.txt").write_text("unexpected", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unexpected entries"):
                publication.verify(root)

    def test_stream_raw_hash_is_checked_before_parsing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "copy"
            shutil.copytree(publication.PUBLICATION, root)
            target = root / "streams" / "native-ak-suited.stdout.json"
            target.write_bytes(b"{}")
            original = publication._json
            def index_only(data):
                if len(data) != publication.INDEX_BYTES:
                    raise AssertionError("stream parsed before digest check")
                return original(data)
            with patch.object(publication, "_json", side_effect=index_only):
                with self.assertRaisesRegex(ValueError, "File size differs|Raw file pin differs"):
                    publication.verify(root)

    def test_source_record_rejects_bool_alias_and_incomplete_map(self):
        record = {"revision": publication.FROZEN_REVISION, "status": [],
                  "source_hashes": {"src.c": {"raw_sha256": "0" * 64,
                                                "lf_sha256": "0" * 64}}}
        with self.assertRaisesRegex(ValueError, "783 files"):
            publication._source_record(record)
        record["source_hashes"] = {f"{i}.c": {"raw_sha256": "0" * 64,
                                                "lf_sha256": "0" * 64}
                                   for i in range(783)}
        record["status"] = True
        with self.assertRaisesRegex(ValueError, "checkpoint differs"):
            publication._source_record(record)

    def test_source_transition_requires_exact_sealed_helper(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "src.c"
            target.write_bytes(b"new source\n")
            row = {"raw_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                   "lf_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
            historical = {"src.c": {"raw_sha256": "0" * 64, "lf_sha256": "0" * 64}}
            snapshot = {"revision": "a" * 40, "status": [], "source_hashes": {"src.c": row}}
            receipt = {"historical_lf_sha256": "0" * 64,
                       "current_lf_sha256": row["lf_sha256"], "archive": "archive/src.c.txt"}
            with (patch.object(publication, "ROOT", root),
                  patch.object(publication.evidence, "snapshot", return_value=snapshot),
                  patch.object(source_history, "authenticate_transition", return_value=receipt) as sealed):
                result = publication._current_source_check(historical)
            self.assertEqual(result["revision"], "a" * 40)
            sealed.assert_called_once_with("src.c", "0" * 64, row["lf_sha256"])
            self.assertEqual(result["sealed_transitions"]["src.c"], receipt)

    def test_unknown_additions_are_recorded_separately_from_measured_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "src.c").write_bytes(b"frozen\n")
            (root / "new.md").write_bytes(b"unmeasured\n")
            def row(path):
                raw = (root / path).read_bytes()
                return {"raw_sha256": hashlib.sha256(raw).hexdigest(),
                        "lf_sha256": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()}
            historical = {"src.c": row("src.c")}
            current = {"revision": "b" * 40, "status": [],
                       "source_hashes": {"src.c": row("src.c"), "new.md": row("new.md")}}
            with (patch.object(publication, "ROOT", root),
                  patch.object(publication.evidence, "snapshot", return_value=current)):
                result = publication._current_source_check(historical)
            self.assertEqual(result["unmeasured_current_lf_sha256"],
                             {"new.md": row("new.md")["lf_sha256"]})

    def test_current_source_drift_during_authentication_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "copy"
            shutil.copytree(publication.PUBLICATION, root)
            first = {"revision": "a" * 40, "status": [], "source_lf_sha256": "before",
                     "current_context_lf_sha256": {}, "unmeasured_current_lf_sha256": {}}
            second = {**first, "source_lf_sha256": "after"}
            with (patch.object(publication, "_current_source_check", side_effect=[first, second]),
                  self.assertRaisesRegex(ValueError, "source changed during saved authentication")):
                publication.verify(root)

    def test_first_current_source_check_precedes_conformance_saved_verification(self):
        with (patch.object(publication, "_current_source_check",
                           side_effect=ValueError("source check first")) as source_check,
              patch.object(publication, "_validate_report",
                           side_effect=AssertionError("metadata validated before source check"))):
            with self.assertRaisesRegex(ValueError, "source check first"):
                publication.verify()
        source_check.assert_called_once()

    def test_physical_row_and_native_receipt_reject_bool_integer_aliases(self):
        rows = [{"sb_hand": sb, "bb_hand": bb, "wins": 500_000, "ties": 10_000,
                 "losses": 1_202_304, "boards": 1_712_304}
                for sb, bb in (("AcKc", "KdKh"), ("AdKc", "KdKh"), ("AdKc", "KhKs"))]
        rows[0]["wins"] = True
        with self.assertRaisesRegex(ValueError, "exact physical row"):
            publication._validate_count_rows(rows, [(row["sb_hand"], row["bb_hand"]) for row in rows],
                                             "synthetic")
        native = {"schema_version": 1, "mode": "count", "boards_per_pair": 1_712_304,
                  "rank_calls": 3_424_608, "counts": [[1, 1, 1]]}
        native["rank_calls"] = True
        with self.assertRaisesRegex(ValueError, "schema/census"):
            publication._validate_native_stream(native, [{"wins": 1, "ties": 1, "losses": 1}],
                                                "synthetic")

    def test_profile_admission_and_native_work_counts_are_typed_and_exact(self):
        report = publication._json((publication.PUBLICATION / "report.json").read_bytes())
        profile = next(row for row in report["profiles"] if row["id"] == "ak-offsuit")
        query = publication.planner.admit_plan()["count_requests"][2]
        publication._validate_profile_metadata(profile, query, report["reference_build_before"],
                                                report["candidate_build_before"]["manifest"],
                                                publication.CONFORMANCE_ARTIFACT_SHA256)
        changed_admission = deepcopy(profile)
        changed_admission["reference"]["metadata"]["admission"]["compatible_pairs"] = True
        with self.assertRaisesRegex(ValueError, "source/build/query linkage"):
            publication._validate_profile_metadata(
                changed_admission, query, report["reference_build_before"],
                report["candidate_build_before"]["manifest"], publication.CONFORMANCE_ARTIFACT_SHA256)
        changed_native = deepcopy(profile)
        changed_native["native"]["metadata"]["rank_calls"] = True
        with self.assertRaisesRegex(ValueError, "source/build/query linkage"):
            publication._validate_profile_metadata(
                changed_native, query, report["reference_build_before"],
                report["candidate_build_before"]["manifest"], publication.CONFORMANCE_ARTIFACT_SHA256)

    def test_conformance_saved_gate_is_checked_against_current_report_file(self):
        raw = (publication.PUBLICATION / "aa-conformance-report.json").read_bytes()
        conformance = publication._json(raw)
        report = publication._json((publication.PUBLICATION / "report.json").read_bytes())
        with patch.object(publication.five, "verify_saved", return_value={"status": "failed"}) as saved:
            with self.assertRaisesRegex(ValueError, "Current AA conformance saved authentication"):
                publication._validate_conformance(
                    conformance, report, raw,
                    {"streams/native-aa-calibration.stdout.json":
                     (publication.PUBLICATION / "streams/native-aa-calibration.stdout.json").read_bytes()},
                    publication.PUBLICATION)
        saved.assert_called_once_with(publication.PUBLICATION / "aa-conformance-report.json")


if __name__ == "__main__":
    unittest.main()
