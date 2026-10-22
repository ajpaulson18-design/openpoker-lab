import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import benchmark_flop_class_cost as cost
from scripts import flop_class_compact_budget as budget
from scripts import flop_public_classes as proof
from scripts import profile_flop_class_phases as profile
from scripts import verify_flop_class_phase_profile_publication as publication


def _payload():
    report = {"schema_version": "synthetic", "quality_target_met": True,
              "runtime": {"python": "synthetic"}, "result": [1, 2, 3]}
    report["artifact_sha256"] = proof._digest(report)
    raw = cost._canonical(report, newline=True)
    return report, raw


def _events():
    names = profile._targets()
    phases = [item[0] for item in names]
    selected = ["compact.publication.verify", "proof.build_model",
                "base._training_inputs", "cfr_plus.train",
                "policy.canonicalize_binary_rows", "proof.audit_policy",
                "proof.lift_policy"]
    rows = []
    for event_id, phase in enumerate(selected, 1):
        parent = 6 if phase == "proof.lift_policy" else (
            1 if phase == "proof.build_model" else None)
        rows.append({"event_id": event_id, "parent_event_id": parent,
                     "phase": phase, "status": "complete",
                     "started_at_utc": "2026-10-22T10:00:00+00:00",
                     "finished_at_utc": "2026-10-22T10:00:01+00:00",
                     "wall_seconds": 1.0, "process_seconds": 0.8})
    assert all(row["phase"] in phases for row in rows)
    return rows


def _write_evidence(directory, payload_raw=None, events=None):
    report, default_raw = _payload()
    payload_raw = default_raw if payload_raw is None else payload_raw
    compressed = gzip.compress(payload_raw, mtime=0)
    filename = "class-560-profiled.json.gz"
    (Path(directory) / filename).write_bytes(compressed)
    source = {"revision": publication.EXPECTED_REVISION, "status": "",
              "source_lf_sha256": {"pinned.py": "a" * 64}}
    protocol = profile._protocol()
    metadata = {"raw_sha256": hashlib.sha256(payload_raw).hexdigest(),
                "artifact_sha256": report["artifact_sha256"],
                "quality_target_met": True, "allocation_trace": False,
                "wall_seconds": 2.0, "process_seconds": 1.5,
                "python_traced_peak_bytes": None,
                "runtime": {"python": "synthetic", "implementation": "synthetic",
                            "platform": "synthetic"},
                "started_at_utc": "2026-10-22T10:00:00+00:00",
                "finished_at_utc": "2026-10-22T10:00:02+00:00"}
    index = {"protocol_id": protocol["protocol_id"], "protocol": protocol,
             "execution_state": {"mode": "direct-call", "system_required": False},
             "instrumentation_overhead": protocol["instrumentation_overhead"],
             "status": "complete", "errors": [], "request": {"method": "class-560",
                                                                    "iterations": 560},
             "admission": budget.admit_compact_request(560),
             "source_before": source, "source_after": source,
             "created_at_utc": "2026-10-22T10:00:00+00:00",
             "finished_at_utc": "2026-10-22T10:00:02+00:00",
             "measurement": metadata, "events": _events() if events is None else events,
             "raw_file": filename, "raw_sha256": hashlib.sha256(payload_raw).hexdigest(),
             "gzip_sha256": hashlib.sha256(compressed).hexdigest()}
    index["index_sha256"] = proof._digest(index)
    raw_index = json.dumps(index, sort_keys=True, indent=2,
                            allow_nan=False).encode() + b"\n"
    (Path(directory) / "index.json").write_bytes(raw_index)
    return raw_index, index, report, payload_raw


class PhaseProfilePublicationTests(unittest.TestCase):
    def setUp(self):
        old_raw, old_canonical = publication.INDEX_RAW_SHA256, publication.INDEX_SHA256
        self.addCleanup(setattr, publication, "INDEX_RAW_SHA256", old_raw)
        self.addCleanup(setattr, publication, "INDEX_SHA256", old_canonical)

    def _patch_validators(self, source, report, *, validate_raw=None):
        return (patch.object(profile, "_snapshot", return_value=source),
                patch.object(budget, "admit_compact_request",
                             return_value=budget.admit_compact_request(560)),
                patch.object(cost, "_pilot_expectations", return_value={
                    "class-560": cost._semantic_digest(report)}),
                patch.object(cost, "_validate_raw", wraps=cost._validate_raw)
                if validate_raw is None else validate_raw)

    def test_valid_immutable_profile_verifies_without_solver_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_index, _, report, _ = _write_evidence(tmp)
            publication.INDEX_RAW_SHA256 = hashlib.sha256(raw_index).hexdigest()
            publication.INDEX_SHA256 = json.loads(raw_index)["index_sha256"]
            source = {"revision": publication.EXPECTED_REVISION, "status": "",
                      "source_lf_sha256": {"pinned.py": "a" * 64}}
            p = self._patch_validators(source, report)
            with p[0], p[1], p[2], p[3]:
                result = publication.verify(tmp)
            self.assertEqual(result["status"], "saved-phase-profile-verified")
            self.assertEqual(len(result["root_phase_events"]), 5)

    def test_resigned_wrong_index_rejects_before_validation_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_index, index, _, _ = _write_evidence(tmp)
            publication.INDEX_RAW_SHA256 = hashlib.sha256(raw_index).hexdigest()
            publication.INDEX_SHA256 = index["index_sha256"]
            index["status"] = "error"
            index["index_sha256"] = proof._digest(
                {key: value for key, value in index.items() if key != "index_sha256"})
            (Path(tmp) / "index.json").write_bytes(json.dumps(
                index, sort_keys=True, indent=2).encode() + b"\n")
            with patch.object(profile, "_protocol") as protocol, \
                 patch.object(cost, "_validate_raw") as validate:
                with self.assertRaisesRegex(ValueError, "index bytes"):
                    publication.verify(tmp)
            protocol.assert_not_called()
            validate.assert_not_called()

    def test_malformed_nested_events_reject_before_payload_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = _events()
            events[-1]["parent_event_id"] = 99
            raw_index, index, _, _ = _write_evidence(tmp, events=events)
            publication.INDEX_RAW_SHA256 = hashlib.sha256(raw_index).hexdigest()
            publication.INDEX_SHA256 = index["index_sha256"]
            source = index["source_before"]
            p = self._patch_validators(source, _payload()[0])
            with p[0], p[1], p[2], p[3], patch.object(cost, "_bounded_gzip") as read_gzip:
                with self.assertRaisesRegex(ValueError, "parent is not an active ancestor"):
                    publication.verify(tmp)
            read_gzip.assert_not_called()

    def test_closed_event_cannot_be_used_as_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = _events()
            events[-1]["parent_event_id"] = 2  # child of a closed sibling subtree
            raw_index, index, _, _ = _write_evidence(tmp, events=events)
            publication.INDEX_RAW_SHA256 = hashlib.sha256(raw_index).hexdigest()
            publication.INDEX_SHA256 = index["index_sha256"]
            p = self._patch_validators(index["source_before"], _payload()[0])
            with p[0], p[1], p[2], p[3], patch.object(cost, "_bounded_gzip") as read_gzip:
                with self.assertRaisesRegex(ValueError, "active ancestor"):
                    publication.verify(tmp)
            read_gzip.assert_not_called()

    def test_source_revision_drift_during_verification_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_index, index, report, _ = _write_evidence(tmp)
            publication.INDEX_RAW_SHA256 = hashlib.sha256(raw_index).hexdigest()
            publication.INDEX_SHA256 = index["index_sha256"]
            original = index["source_before"]
            changed = {**original, "revision": "f" * 40}
            p = self._patch_validators(original, report)
            with patch.object(profile, "_snapshot", side_effect=[original, changed]), \
                 p[1], p[2], p[3]:
                with self.assertRaisesRegex(ValueError, "snapshot changed"):
                    publication.verify(tmp)

    def test_wrong_raw_policy_semantics_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_report, original_raw = _payload()
            changed = dict(original_report, result=[9, 8, 7])
            changed["artifact_sha256"] = proof._digest(
                {key: value for key, value in changed.items() if key != "artifact_sha256"})
            wrong_raw = cost._canonical(changed, newline=True)
            raw_index, index, _, _ = _write_evidence(tmp, payload_raw=wrong_raw)
            publication.INDEX_RAW_SHA256 = hashlib.sha256(raw_index).hexdigest()
            publication.INDEX_SHA256 = index["index_sha256"]
            source = index["source_before"]
            p = self._patch_validators(source, original_report)
            with p[0], p[1], p[2], p[3]:
                with self.assertRaisesRegex(ValueError, "pilot"):
                    publication.verify(tmp)

    def test_index_mutation_during_validation_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_index, index, report, _ = _write_evidence(tmp)
            publication.INDEX_RAW_SHA256 = hashlib.sha256(raw_index).hexdigest()
            publication.INDEX_SHA256 = index["index_sha256"]
            source = index["source_before"]
            p = self._patch_validators(source, report)
            original_validate = cost._validate_raw

            def mutate_after_validation(*args, **kwargs):
                checked = original_validate(*args, **kwargs)
                (Path(tmp) / "index.json").write_bytes(raw_index + b" ")
                return checked

            with p[0], p[1], p[2], patch.object(cost, "_validate_raw",
                                                side_effect=mutate_after_validation):
                with self.assertRaisesRegex(ValueError, "index bytes"):
                    publication.verify(tmp)


if __name__ == "__main__":
    unittest.main()
