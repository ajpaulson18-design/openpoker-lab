"""Saved-corpus authentication tests; they never rebuild or recount poker data."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_preflop_jj_kk_basis_publication as publication


class SavedJJKKBasisPublicationTests(unittest.TestCase):
    def test_actual_published_corpus_authenticates_without_build_or_count_calls(self):
        with (patch.object(publication.reference, "reference_preflop_counts",
                           side_effect=AssertionError("not called")),
              patch.object(publication.evidence.native, "prepare_native_preflop_equities",
                           side_effect=AssertionError("not called")),
              patch.object(publication.five, "backend", side_effect=AssertionError("build lookup")),
              patch.object(publication.five, "validate_five_dump", side_effect=AssertionError("rank replay")),
              patch("pokerlab.cfr_plus.train", side_effect=AssertionError("training")),
              patch.object(publication, "_current_source_check")):
            result = publication.verify()
        self.assertEqual(result["status"], "authenticated-saved-counts-only")
        self.assertEqual(result["numerical_subprocess_calls_recorded"], 5)
        self.assertEqual(result["physical_pair_censuses_recorded"], 4)
        self.assertIs(result["physical_counts_recomputed"], False)
        self.assertEqual(result["source_file_count"], 746)

    def test_index_raw_pin_rejects_resigned_mutation_before_json_parse(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "index.json"
            path.write_bytes(b"x" * publication.INDEX_BYTES)
            with (patch.object(publication, "_read", return_value=b"x" * publication.INDEX_BYTES),
                  patch.object(publication, "_json", side_effect=AssertionError("parsed before pin"))):
                with self.assertRaisesRegex(ValueError, "Pinned raw index"):
                    publication._validate_index(Path(temp))

    def test_duplicate_and_nonfinite_json_are_rejected(self):
        with self.assertRaises(ValueError):
            publication._json(b'{"x":1,"x":2}')
        with self.assertRaises(ValueError):
            publication._json(b'{"x":NaN}')
        with self.assertRaises(ValueError):
            publication._json(b'{"x":1e999}')

    def test_bool_aliases_are_rejected_in_physical_rows(self):
        valid = [{"sb_hand": sb, "bb_hand": bb, "wins": 1, "ties": 2,
                  "losses": 1_712_301, "boards": 1_712_304}
                 for sb, bb in publication.PAIR_ROWS]
        malformed = [dict(row) for row in valid]
        malformed[0]["wins"] = True
        with self.assertRaisesRegex(ValueError, "row census"):
            publication._validate_rows(malformed, stage="test")

    def test_bool_aliases_are_rejected_in_subprocess_receipt(self):
        calls = [{"ordinal": i, "stage": stage, "status": "returned", "returncode": 0,
                  "stdout": {}, "stderr": {}}
                 for i, stage in enumerate(publication.STAGES, start=1)]
        calls[0]["returncode"] = False
        with self.assertRaisesRegex(ValueError, "receipt order/status"):
            publication._validate_calls(calls, {}, {}, Path("."))

    def test_current_source_check_requires_clean_snapshot_and_exact_measured_files(self):
        historical = {"AGENTS.md": {"raw_sha256": "0" * 64, "lf_sha256": "0" * 64}}
        with patch.object(publication.five, "snapshot", return_value={"status": "dirty", "source_hashes": {}}):
            with self.assertRaisesRegex(ValueError, "committed and clean"):
                publication._current_source_check(historical)

    def _saved(self):
        root = publication.PUBLICATION
        index = json.loads((root / "index.json").read_bytes())
        report = json.loads((root / "report.json").read_bytes())
        return index, report, {row["path"]: row for row in index["files"]}

    def test_copied_corpus_authenticates_using_requested_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "copy"
            shutil.copytree(publication.PUBLICATION, root)
            with (patch.object(publication, "PUBLICATION", Path(temp) / "must-not-read"),
                  patch.object(publication, "_current_source_check")):
                self.assertEqual(publication.verify(root)["status"], "authenticated-saved-counts-only")

    def test_report_bitflip_rejects_before_report_json_parse(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "copy"
            shutil.copytree(publication.PUBLICATION, root)
            path = root / "report.json"
            raw = path.read_bytes()
            path.write_bytes(b"x" + raw[1:])
            original = publication._json
            def index_only(data):
                if len(data) == len(raw):
                    raise AssertionError("report parsed before raw hash")
                return original(data)
            with patch.object(publication, "_json", side_effect=index_only):
                with self.assertRaisesRegex(ValueError, "file bytes differ"):
                    publication.verify(root)

    def test_unindexed_extra_file_rejects(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "copy"
            shutil.copytree(publication.PUBLICATION, root)
            (root / "streams" / "extra.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "inventory"):
                publication.verify(root)

    def test_measured_source_allows_line_endings_but_rejects_lf_drift(self):
        raw = b"project-owned source\r\n"
        lf = raw.replace(b"\r\n", b"\n")
        historical = {"AGENTS.md": {"raw_sha256": hashlib.sha256(raw).hexdigest(),
                                     "lf_sha256": hashlib.sha256(lf).hexdigest()}}
        state = {"status": [], "source_hashes": {}}
        with (patch.object(publication.five, "snapshot", return_value=state),
              patch.object(publication, "_read", return_value=lf)):
            publication._current_source_check(historical)
        with (patch.object(publication.five, "snapshot", return_value=state),
              patch.object(publication, "_read", return_value=b"changed\n")):
            with self.assertRaisesRegex(ValueError, "LF bytes changed"):
                publication._current_source_check(historical)

    def test_build_manifest_source_tamper_reaches_semantic_guard(self):
        _, report, _ = self._saved()
        before = deepcopy(report["candidate_build_before"])
        before["manifest"]["source_lf_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source linkage"):
            publication._validate_build_pair(before, deepcopy(before), True,
                expected_source="native/preflop_equity.c",
                historical=report["source_before"]["source_hashes"])

    def test_raw_native_stream_and_report_count_disagreement_rejects(self):
        _, report, files = self._saved()
        report["native_physical_count_rows"][0]["wins"] += 1
        report["native_physical_count_rows"][0]["losses"] -= 1
        with self.assertRaisesRegex(ValueError, "Native JJ stdout differs"):
            publication._validate_calls(report["numerical_subprocess_calls"], files,
                                        report, publication.PUBLICATION)

    def test_observed_stream_count_rejects_bool_alias(self):
        _, report, files = self._saved()
        calls = deepcopy(report["numerical_subprocess_calls"])
        calls[0]["stderr"]["bytes_observed_at_most_limit_plus_one"] = False
        with self.assertRaisesRegex(ValueError, "observed-byte count"):
            publication._validate_calls(calls, files, report, publication.PUBLICATION)

    def test_metadata_build_and_raw_normalized_row_linkages_reject_tampering(self):
        _, report, _ = self._saved()
        aa = json.loads(publication.evidence.AA_REPORT.read_bytes())
        publication._validate_linkages(report, aa)
        cases = []
        changed = deepcopy(report)
        changed["reference_metadata"]["conformance_report_sha256"] = "0" * 64
        cases.append((changed, "build/conformance/admission"))
        changed = deepcopy(report)
        changed["candidate_metadata"]["rank_calls"] = True
        cases.append((changed, "physical-work metadata"))
        changed = deepcopy(report)
        changed["independent_physical_count_rows"][0]["wins"] += 1
        changed["independent_physical_count_rows"][0]["losses"] -= 1
        cases.append((changed, "original raw reference"))
        changed = deepcopy(report)
        changed["candidate_equity_table"]["counts"][0]["wins"] += 1
        cases.append((changed, "Candidate table rows"))
        for altered, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                publication._validate_linkages(altered, aa)


if __name__ == "__main__":
    unittest.main()
