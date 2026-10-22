import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_flop_class_owned_fingerprint_publication as verifier


class SavedFingerprintPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "report.json"
        self.report, self.current = self._fixture()

    def _fixture(self):
        evidence = verifier.evidence
        _, spec = evidence._protocol()
        admission = evidence._preflight(spec)
        source_map = {f"source-{i:02d}": f"{i:064x}" for i in range(39)}
        recorded = {"revision": verifier.SOURCE_REVISION, "status": "",
                    "source_lf_sha256": source_map}
        current = {"revision": "b" * 40, "status": "",
                   "source_lf_sha256": source_map}
        limits = spec["limits"]
        stable = verifier._stable_census(limits)
        alias = verifier._alias_census(limits)
        digests = (verifier.STABLE_DIGEST, verifier.STABLE_DIGEST,
                   verifier.ACTION_DIGEST, verifier.STABLE_DIGEST,
                   verifier.ALIAS_DIGEST, verifier.STABLE_DIGEST)
        censuses = (stable, stable, stable, stable, alias, stable)
        compact = {"compact_action_slots": 932, "compact_chance_nodes": 58,
            "compact_decisions": 316, "compact_policy_rows": 466,
            "compact_public_states": 1001, "compact_terminals": 627,
            "compact_tree_sha256": "55d75a6563ffb595c044d92d73c4f452880717a01f394dfd6c176e106b531dec",
            "compact_worlds": 126, "physical_action_slots": 33824,
            "physical_branch_subtrees_compared": 11787, "physical_nodes_checked": 30812,
            "physical_policy_rows": 16912, "river_signatures": 19, "turn_classes": 11}
        report = {
            "schema_version": 1,
            "protocol_id": "fixed-flop-owned-fingerprint-v1",
            "status": "complete", "created_at_utc": "2026-10-22T20:33:40.513991+00:00",
            "finished_at_utc": "2026-10-22T20:37:24.497845+00:00",
            "protocol_sha256": evidence.SPEC_SHA256, "admission": admission,
            "source_before": recorded, "source_after": recorded,
            "prerequisite": {
                "publication_pr": 209,
                "index_raw_sha256": spec["prerequisite"]["diagnostic_index_raw_sha256"],
                "index_sha256": spec["prerequisite"]["diagnostic_index_sha256"],
                "status": "saved-baseline-diagnostic-authenticated",
                "recorded_training_calls": 2, "verification_training_calls": 0,
                "phase_events": 13},
            "physical_model_census": {
                "baseline_physical_worlds": 5940, "baseline_public_states": 30812,
                "compact_census": compact, "maximum_live_physical_oracles_reference": 2,
                "physical_oracle_builds": 2, "physical_world_rows_reference": 11880,
                "weighted_physical_worlds": 5940, "weighted_public_states": 30812},
            "fingerprints": [
                {"sample_id": sample, "status": "complete", "sha256": digest,
                 "census": census}
                for sample, digest, census in zip(verifier.SAMPLE_IDS, digests, censuses)],
            "fingerprint_calls": 6, "full_validations": 2, "training_calls": 0,
            "authority_calls": {key: 0 for key in verifier.AUTHORITY_KEYS},
            "runtime": {
                "python": "3.12.14 (main, Aug 25 2026, 14:01:42) [MSC v.1944 64 bit (AMD64)]",
                "implementation": "CPython", "platform": "Windows-10-10.0.19045-SP0"},
            "execution_state": {"mode": "windows-benchmark-thread",
                "system_required": True, "requested_flags": 0x80000001,
                "previous_flags": 0x80000000},
            "errors": [],
        }
        return report, current

    def _write_signed(self, report):
        report = json.loads(json.dumps(report))
        report["report_sha256"] = verifier.evidence.proof._digest(report)
        raw = json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
        self.path.write_bytes(raw)
        return raw, report

    def _verify_signed(self, report, *, snapshots=None):
        raw, signed = self._write_signed(report)
        snapshots = snapshots or (self.current, self.current)
        with patch.object(verifier, "RAW_REPORT_SHA256", hashlib.sha256(raw).hexdigest()), \
             patch.object(verifier, "REPORT_SHA256", signed["report_sha256"]), \
             patch.object(verifier.evidence, "_snapshot", side_effect=snapshots):
            return verifier.verify(self.path)

    def test_valid_fixture_accepts_clean_advanced_head_with_same_source_map(self):
        with patch.object(verifier.evidence, "fingerprint", side_effect=AssertionError("unexpected fingerprint")), \
             patch.object(verifier.evidence.reweighted, "build_model", side_effect=AssertionError("unexpected model")), \
             patch.object(verifier.evidence.reweighted, "validate_model", side_effect=AssertionError("unexpected model validation")), \
             patch.object(verifier.evidence.trainer.cfr_plus, "train", side_effect=AssertionError("unexpected training")):
            result = self._verify_signed(self.report)
        self.assertEqual(result["status"], "saved-owned-fingerprint-census-authenticated")
        self.assertEqual(result["source_revision"], verifier.SOURCE_REVISION)
        self.assertEqual(result["recorded_fingerprint_calls"], 6)
        self.assertEqual(result["recorded_full_validations"], 2)
        self.assertEqual(result["fingerprint_calls"], 0)
        self.assertEqual(result["full_validations"], 0)
        self.assertEqual(result["training_calls"], 0)

    def test_immutable_pins_match_the_completed_census(self):
        self.assertEqual(verifier.RAW_REPORT_SHA256,
            "8ac7091a289a5e131348bd86fed58e769d1e1413b797a408435b1b8c2a4d56a5")
        self.assertEqual(verifier.REPORT_SHA256,
            "48cb08101cd1d9a1c9141572609e89cf2518a06afb7fb96b1bf0591467b76afb")
        self.assertEqual(verifier.SOURCE_REVISION,
            "1b61d75f89c8960bf6aeca464611f899a2cbc841")

    def test_unpinned_raw_mutation_is_rejected(self):
        raw, _ = self._write_signed(self.report)
        self.path.write_bytes(raw + b" ")
        with patch.object(verifier.evidence, "_snapshot", return_value=self.current):
            with self.assertRaisesRegex(ValueError, "immutable raw pin"):
                verifier.verify(self.path)

    def test_resigned_typed_schema_alias_is_rejected(self):
        report = json.loads(json.dumps(self.report))
        report["schema_version"] = True
        with self.assertRaisesRegex(ValueError, "status or schema"):
            self._verify_signed(report)

    def test_resigned_bad_sample_census_is_rejected(self):
        report = json.loads(json.dumps(self.report))
        report["fingerprints"][0]["census"]["edges"] += 1
        with self.assertRaisesRegex(ValueError, "census differs"):
            self._verify_signed(report)

    def test_recorded_revision_must_match_frozen_checkpoint(self):
        report = json.loads(json.dumps(self.report))
        report["source_before"]["revision"] = "c" * 40
        report["source_after"]["revision"] = "c" * 40
        with self.assertRaisesRegex(ValueError, "Recorded census revision"):
            self._verify_signed(report)

    def test_current_head_drift_during_verification_is_rejected(self):
        drifted = dict(self.current, revision="d" * 40)
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            self._verify_signed(self.report, snapshots=(self.current, drifted))

    def test_duplicate_json_fields_are_rejected_even_when_raw_is_pinned(self):
        raw = b'{"schema_version":1,"schema_version":1}'
        self.path.write_bytes(raw)
        with patch.object(verifier, "RAW_REPORT_SHA256", hashlib.sha256(raw).hexdigest()), \
             patch.object(verifier, "REPORT_SHA256", "irrelevant"), \
             patch.object(verifier.evidence, "_snapshot", return_value=self.current):
            with self.assertRaisesRegex(ValueError, "Duplicate JSON field"):
                verifier.verify(self.path)

    def test_nonfinite_json_number_is_rejected_even_when_raw_is_pinned(self):
        raw = b'{"value":1e999}'
        self.path.write_bytes(raw)
        with patch.object(verifier, "RAW_REPORT_SHA256", hashlib.sha256(raw).hexdigest()), \
             patch.object(verifier, "REPORT_SHA256", "irrelevant"), \
             patch.object(verifier.evidence, "_snapshot", return_value=self.current):
            with self.assertRaisesRegex(ValueError, "Non-finite JSON number"):
                verifier.verify(self.path)

    def test_resigned_wrong_self_digest_is_rejected(self):
        raw, signed = self._write_signed(self.report)
        signed["report_sha256"] = "0" * 64
        raw = json.dumps(signed, sort_keys=True, indent=2).encode() + b"\n"
        self.path.write_bytes(raw)
        with patch.object(verifier, "RAW_REPORT_SHA256", hashlib.sha256(raw).hexdigest()), \
             patch.object(verifier, "REPORT_SHA256", "0" * 64), \
             patch.object(verifier.evidence, "_snapshot", return_value=self.current):
            with self.assertRaisesRegex(ValueError, "self-digest differs"):
                verifier.verify(self.path)

    def test_report_mutation_during_verification_is_rejected(self):
        raw, _ = self._write_signed(self.report)
        original_read = verifier._read
        calls = 0
        def mutate_after_first_read(path):
            nonlocal calls
            calls += 1
            result = original_read(path)
            if calls == 1:
                self.path.write_bytes(raw + b" ")
            return result
        with patch.object(verifier, "RAW_REPORT_SHA256", hashlib.sha256(raw).hexdigest()), \
             patch.object(verifier, "REPORT_SHA256", self.report["report_sha256"] if
                          "report_sha256" in self.report else
                          verifier.evidence.proof._digest(self.report)), \
             patch.object(verifier, "_read", side_effect=mutate_after_first_read), \
             patch.object(verifier.evidence, "_snapshot", return_value=self.current):
            with self.assertRaisesRegex(ValueError, "size changed during verification"):
                verifier.verify(self.path)


if __name__ == "__main__":
    unittest.main()
