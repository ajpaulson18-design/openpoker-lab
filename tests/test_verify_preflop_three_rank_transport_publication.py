"""Saved-publication authentication tests; no count production or ranking."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_preflop_three_rank_transport_publication as verifier
from scripts import preflop_three_rank_transport_validation as independent


def _read_saved_report():
    raw = verifier._bounded_read(verifier.PUBLICATION / "report.json",
                                 verifier.MAX_REPORT_BYTES,
                                 expected_bytes=verifier.REPORT_BYTES,
                                 expected_sha256=verifier.REPORT_RAW_SHA256)
    return independent._load_json(raw)


class ThreeRankTransportPublicationTests(unittest.TestCase):
    def _clean_jj_metadata(self):
        # The publication and this new test file may be untracked during local
        # WIP. The wrapper still authenticates all actual saved AA/QQ/JJ data.
        return patch.object(independent.jj, "_current_source_check", return_value={})

    def _clean_snapshot(self):
        snapshot = deepcopy(verifier.audit.snapshot())
        snapshot["status"] = []
        return snapshot

    def test_actual_saved_corpus_authenticates_without_calculation(self):
        clean_snapshot = self._clean_snapshot()
        with self._clean_jj_metadata(), \
                patch.object(verifier.audit, "snapshot", return_value=clean_snapshot):
            result = verifier.verify()
        self.assertEqual(result["status"], "authenticated-saved-transport-only")
        self.assertEqual(result["physical_pair_rows_authenticated"], 108)
        self.assertEqual(result["exact_global_prior_mass"], "1")
        self.assertEqual(result["rank_calls"], 0)
        self.assertEqual(result["board_enumerations"], 0)
        self.assertEqual(result["training_calls"], 0)
        self.assertFalse(result["equilibrium_or_policy_claim"])

    def test_later_clean_head_with_same_frozen_lf_sources_is_accepted(self):
        report = _read_saved_report()
        clean_snapshot = self._clean_snapshot()
        clean_snapshot["revision"] = "a" * 40
        with patch.object(verifier.audit, "snapshot", return_value=clean_snapshot):
            current = verifier._current_source_attestation(report["source_before"])
        self.assertEqual(current["revision"], "a" * 40)
        self.assertNotEqual(current["revision"], verifier.FROZEN_REVISION)
        self.assertEqual(current["status"], [])

    def test_malformed_or_dirty_current_snapshot_is_rejected(self):
        report = _read_saved_report()
        for field, value, message in (
                ("revision", "not-a-commit", "revision is malformed"),
                ("status", [" M tracked.py"], "checkout must be clean")):
            changed = self._clean_snapshot()
            changed[field] = value
            with self.subTest(field=field), \
                    patch.object(verifier.audit, "snapshot", return_value=changed), \
                    self.assertRaisesRegex(ValueError, message):
                verifier._current_source_attestation(report["source_before"])

    def test_candidate_raw_pin_rejects_before_json_parse_or_source_auth(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copyfile(verifier.PUBLICATION / "candidate.json", root / "candidate.json")
            shutil.copyfile(verifier.PUBLICATION / "report.json", root / "report.json")
            raw = bytearray((root / "candidate.json").read_bytes())
            raw[-2] ^= 1
            (root / "candidate.json").write_bytes(raw)
            with patch.object(independent, "_load_json",
                              side_effect=AssertionError("parsed before raw pin")), \
                    patch.object(independent, "verify_candidate_report",
                                 side_effect=AssertionError("source auth before raw pin")):
                with self.assertRaisesRegex(ValueError, "raw saved bytes"):
                    verifier.verify(root)

    def test_unmapped_publication_file_rejects_before_authentication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copyfile(verifier.PUBLICATION / "candidate.json", root / "candidate.json")
            shutil.copyfile(verifier.PUBLICATION / "report.json", root / "report.json")
            (root / "unexpected.txt").write_text("extra", encoding="utf-8")
            with patch.object(independent, "verify_candidate_report",
                              side_effect=AssertionError("auth called")) as authenticate:
                with self.assertRaisesRegex(ValueError, "inventory"):
                    verifier.verify(root)
            authenticate.assert_not_called()

    def test_resigned_boolean_attempt_and_forbidden_counter_are_rejected(self):
        report = _read_saved_report()
        for mutator, message in (
                (lambda item: item.__setitem__("candidate_attempts", True), "attempt counts"),
                (lambda item: item["forbidden_calculation_calls"].__setitem__(
                    "pokerlab.preflop_full_board_equity.rank_hand", True), "forbidden-call")):
            changed = deepcopy(report)
            mutator(changed)
            digest = independent._artifact(changed)
            changed["artifact_sha256"] = digest
            raw = json.dumps(changed, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
            with self.subTest(message=message), \
                    patch.object(verifier, "REPORT_ARTIFACT_SHA256", digest), \
                    self.assertRaisesRegex(ValueError, message):
                verifier._parse_and_validate_report(raw)

    def test_source_lf_drift_during_verification_is_rejected(self):
        report = _read_saved_report()
        frozen = report["source_before"]
        clean_snapshot = self._clean_snapshot()
        with patch.object(verifier.audit, "snapshot", return_value=clean_snapshot):
            attestation = verifier._current_source_attestation(frozen)
        receipt = report["fresh_saved_file_verification"]
        changed = deepcopy(attestation)
        changed["source_hashes"][verifier.SOURCE_PATHS[0]]["lf_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copyfile(verifier.PUBLICATION / "candidate.json", root / "candidate.json")
            shutil.copyfile(verifier.PUBLICATION / "report.json", root / "report.json")
            with patch.object(verifier, "_current_source_attestation",
                              side_effect=(attestation, changed)), \
                    patch.object(independent, "verify_candidate_report", return_value=receipt), \
                    self.assertRaisesRegex(ValueError, "changed during"):
                verifier.verify(root)

    def test_corpus_report_mutation_after_authentication_is_rejected(self):
        report = _read_saved_report()
        receipt = report["fresh_saved_file_verification"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copyfile(verifier.PUBLICATION / "candidate.json", root / "candidate.json")
            shutil.copyfile(verifier.PUBLICATION / "report.json", root / "report.json")

            def mutate_after_check(path):
                (root / "report.json").write_bytes(
                    (root / "report.json").read_bytes() + b" ")
                return receipt

            with patch.object(verifier, "_current_source_attestation", return_value={
                    "revision": verifier.FROZEN_REVISION, "status": [],
                    "source_hashes": report["source_before"]["source_hashes"]}), \
                    patch.object(independent, "verify_candidate_report",
                                 side_effect=mutate_after_check), \
                    self.assertRaisesRegex(ValueError, "size differs or exceeds bound"):
                verifier.verify(root)


if __name__ == "__main__":
    unittest.main()
