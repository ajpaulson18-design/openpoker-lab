from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import benchmark_preflop_ak_kk_basis as ak_evidence
from scripts import preflop_aa_ak_transport_validation as independent
from scripts import verify_preflop_aa_ak_transport_publication as verifier


def _saved(name):
    path = verifier.PUBLICATION / name
    return verifier._read(path, verifier.MAX_CANDIDATE_BYTES if name == "candidate.json"
                          else verifier.MAX_REPORT_BYTES,
                          size=verifier.CANDIDATE_BYTES if name == "candidate.json"
                          else verifier.REPORT_BYTES,
                          sha256=verifier.CANDIDATE_RAW_SHA256 if name == "candidate.json"
                          else verifier.REPORT_RAW_SHA256)


class AAKKTransportPublicationTests(unittest.TestCase):
    def _current_snapshot(self, *, revision=None, source=None):
        snapshot = deepcopy(verifier.audit.snapshot())
        snapshot["status"] = []
        if source is not None:
            snapshot = deepcopy(source)
            snapshot["status"] = []
        if revision is not None:
            snapshot["revision"] = revision
        return snapshot

    def _local_clean_metadata(self):
        # The test and publication files are untracked during local WIP. This
        # masks only git status; all measured source bytes are still hashed.
        snap = self._current_snapshot()
        return patch.object(verifier.audit, "snapshot", return_value=snap)

    def _clean_ak_status(self):
        snap = deepcopy(ak_evidence.snapshot())
        snap["status"] = []
        return patch.object(ak_evidence, "snapshot", return_value=snap)

    def _baseline(self):
        return patch.object(verifier.audit, "published_baseline",
                            return_value=verifier.BASELINE_COMMIT)

    def test_actual_saved_corpus_authenticates_without_counting(self):
        with self._local_clean_metadata(), self._clean_ak_status(), self._baseline():
            result = verifier.verify()
        self.assertEqual(result["status"], "authenticated-saved-transport-only")
        self.assertEqual(result["physical_pair_rows_authenticated"], 84)
        self.assertEqual(result["source_classes_authenticated"], 6)
        self.assertEqual(result["exact_global_prior_mass"], "1")
        self.assertEqual((result["rank_calls"], result["board_enumerations"],
                          result["training_calls"]), (0, 0, 0))
        self.assertFalse(result["equilibrium_or_policy_claim"])

    def test_later_clean_head_with_identical_lf_sources_is_accepted(self):
        report = independent.io._load_json(_saved("report.json"))
        current = self._current_snapshot(revision="a" * 40, source=report["source_before"])
        with patch.object(verifier.audit, "snapshot", return_value=current):
            result = verifier._current_source_attestation(report["source_before"])
        self.assertEqual(result["revision"], "a" * 40)
        self.assertNotEqual(result["revision"], verifier.FROZEN_REVISION)

    def test_current_source_drift_and_dirty_status_reject(self):
        report = independent.io._load_json(_saved("report.json"))
        for change, message in (("lf_sha256", "measured source differs"), ("status", "must be clean")):
            snapshot = self._current_snapshot(source=report["source_before"])
            if change == "lf_sha256":
                snapshot["source_hashes"][verifier.SOURCE_PATHS[0]]["lf_sha256"] = "0" * 64
            else:
                snapshot["status"] = [" M measured.py"]
            with self.subTest(change=change), patch.object(verifier.audit, "snapshot", return_value=snapshot):
                with self.assertRaisesRegex(ValueError, message):
                    verifier._current_source_attestation(report["source_before"])

    def test_candidate_raw_pin_rejects_before_parse_or_source_auth(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("candidate.json", "report.json"):
                shutil.copyfile(verifier.PUBLICATION / name, root / name)
            raw = bytearray((root / "candidate.json").read_bytes())
            raw[-2] ^= 1
            (root / "candidate.json").write_bytes(raw)
            with patch.object(independent.io, "_load_json",
                              side_effect=AssertionError("parsed before raw pin")), \
                    patch.object(independent, "verify_candidate_report",
                                 side_effect=AssertionError("source auth before raw pin")):
                with self.assertRaisesRegex(ValueError, "Pinned raw bytes differ"):
                    verifier.verify(root)

    def test_exact_two_file_inventory_rejects_extra_before_auth(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("candidate.json", "report.json"):
                shutil.copyfile(verifier.PUBLICATION / name, root / name)
            (root / "extra.txt").write_text("unmapped", encoding="utf-8")
            with patch.object(independent, "verify_candidate_report",
                              side_effect=AssertionError("fresh auth called")) as fresh:
                with self.assertRaisesRegex(ValueError, "inventory"):
                    verifier.verify(root)
            fresh.assert_not_called()

    def test_resigned_boolean_counter_and_nonzero_guard_are_rejected(self):
        report = independent.io._load_json(_saved("report.json"))
        mutations = (
            (lambda value: value.__setitem__("candidate_attempts", True), "candidate_attempts"),
            (lambda value: value["forbidden_calculation_calls"].__setitem__(
                "pokerlab.cards.rank_hand", 1), "sixteen zero"),
        )
        candidate = verifier._validate_candidate(independent.io._load_json(_saved("candidate.json")))
        for mutate, message in mutations:
            changed = deepcopy(report)
            mutate(changed)
            changed["artifact_sha256"] = independent.io._artifact(changed)
            raw = json.dumps(changed, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
            with self.subTest(message=message), \
                    patch.object(verifier, "REPORT_ARTIFACT_SHA256", changed["artifact_sha256"]), \
                    self.assertRaisesRegex(ValueError, message):
                verifier._parse_report(raw, candidate)

    def test_report_byte_tampering_rejects_before_json_parse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("candidate.json", "report.json"):
                shutil.copyfile(verifier.PUBLICATION / name, root / name)
            with (root / "report.json").open("ab") as stream:
                stream.write(b" ")
            with patch.object(independent.io, "_load_json",
                              side_effect=AssertionError("parsed before report pin")):
                with self.assertRaisesRegex(ValueError, "Saved file size differs"):
                    verifier.verify(root)

    def test_corpus_change_after_fresh_replay_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("candidate.json", "report.json"):
                shutil.copyfile(verifier.PUBLICATION / name, root / name)
            report = independent.io._load_json(_saved("report.json"))
            clean = self._current_snapshot(source=report["source_before"])

            def mutate_report(_path):
                path = root / "report.json"
                path.write_bytes(path.read_bytes() + b" ")
                return report["fresh_saved_file_verification"]

            with patch.object(verifier.audit, "snapshot", return_value=clean), \
                    self._baseline(), \
                    patch.object(independent, "verify_candidate_report", side_effect=mutate_report), \
                    self.assertRaisesRegex(ValueError, "Saved file size differs"):
                verifier.verify(root)

    def test_source_revision_change_during_replay_rejects_successful_math(self):
        report = independent.io._load_json(_saved("report.json"))
        before = self._current_snapshot(source=report["source_before"])
        after = deepcopy(before)
        after["revision"] = "b" * 40
        with patch.object(verifier.audit, "snapshot", side_effect=(before, after)), \
                self._baseline(), \
                patch.object(independent, "verify_candidate_report",
                             return_value=report["fresh_saved_file_verification"]) as fresh:
            with self.assertRaisesRegex(ValueError, "Current clean source changed"):
                verifier.verify()
        self.assertEqual(fresh.call_count, 1)

    def test_receipt_integer_alias_for_false_policy_claim_is_rejected(self):
        report = independent.io._load_json(_saved("report.json"))
        receipt = deepcopy(report["independent_memory_verification"])
        receipt["equilibrium_or_policy_claim"] = 0
        with self.assertRaisesRegex(ValueError, "Independent saved transport receipt differs"):
            verifier._validate_receipt(receipt)


if __name__ == "__main__":
    unittest.main()
