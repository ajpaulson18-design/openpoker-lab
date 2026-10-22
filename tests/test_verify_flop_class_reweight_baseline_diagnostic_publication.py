import gzip
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import diagnose_flop_class_reweight_baseline as diagnostic
from scripts import verify_flop_class_reweight_cfrplus_publication as pilot_publication
from scripts import flop_public_classes as proof
from scripts import verify_flop_class_reweight_baseline_diagnostic_publication as verifier


class DiagnosticPublicationTests(unittest.TestCase):
    def setUp(self):
        self._pins = (verifier.RAW_INDEX_SHA256, verifier.INDEX_SHA256,
                      verifier.EXPECTED_SOURCE_REVISION)
        self.addCleanup(self._restore_pins)
        raw_index, published = pilot_publication._read_index(
            pilot_publication.PUBLICATION / "index.json")
        row = next(row for row in published["files"] if row["path"] == "baseline-560.json.gz")
        self.raw, self.report = pilot_publication._read_gzip(pilot_publication.PUBLICATION, row)
        self.assertTrue(raw_index)
        self.source = {"revision": "a" * 40, "status": "",
                       "source_lf_sha256": {f"src-{i}": f"{i:064x}" for i in range(35)}}
        self.current = {"revision": "b" * 40, "status": "",
                        "source_lf_sha256": dict(self.source["source_lf_sha256"])}

    def _restore_pins(self):
        verifier.RAW_INDEX_SHA256, verifier.INDEX_SHA256, verifier.EXPECTED_SOURCE_REVISION = self._pins

    def _build_index(self, directory):
        _, protocol = diagnostic._protocol()
        requests, _ = diagnostic._preflight(protocol)
        runtime = {"python": "3.12.14 (synthetic test)", "implementation": "CPython",
                   "platform": "Windows synthetic"}
        samples = []
        for expected in protocol["samples"]:
            raw_sha = hashlib.sha256(self.raw).hexdigest()
            compressed = gzip.compress(self.raw, mtime=0)
            name = f"{expected['sample_id']}.json.gz"
            (directory / name).write_bytes(compressed)
            file_row = {"path": name, "raw_bytes": len(self.raw),
                        "gzip_bytes": len(compressed), "raw_sha256": raw_sha,
                        "gzip_sha256": hashlib.sha256(compressed).hexdigest()}
            allocation = expected["allocation_trace"]
            sample_start = datetime.fromisoformat(
                "2026-10-22T12:00:00+00:00" if not allocation else
                "2026-10-22T12:01:00+00:00")
            sample_finish = sample_start + timedelta(seconds=20 if not allocation else 1)
            measurement = {"started_at_utc": sample_start.isoformat(),
                           "finished_at_utc": sample_finish.isoformat(),
                           "wall_seconds": 1.0, "process_seconds": 0.5,
                           "raw_sha256": raw_sha,
                           "artifact_sha256": self.report["artifact_sha256"],
                           "quality_target_met": True, "allocation_trace": allocation,
                           "python_traced_peak_bytes": 123 if allocation else None,
                           "runtime": runtime}
            events = []
            if expected["phase_instrumentation"]:
                for event_id, phase in enumerate(protocol["instrumented_boundaries"], 1):
                    event_start = sample_start + timedelta(seconds=event_id - 1)
                    events.append({"event_id": event_id, "parent_event_id": None,
                                   "phase": phase, "started_at_utc": event_start.isoformat(),
                                   "finished_at_utc": (event_start + timedelta(seconds=0.2)).isoformat(),
                                   "wall_seconds": 0.2, "process_seconds": 0.1,
                                   "status": "complete"})
            samples.append({"sample_id": expected["sample_id"], "status": "complete",
                            "phase_instrumentation": expected["phase_instrumentation"],
                            "allocation_trace": allocation, "events": events, "error": None,
                            "source_before": self.source, "evidence_file": file_row,
                            "training_calls": 1, "measurement": measurement,
                            "report_matches_pilot": True, "source_after": self.source})
        preflight = {**protocol["preflight"], "requests": requests}
        index = {"schema_version": 1,
                 "protocol_id": "fixed-flop-prior-baseline-diagnostic-v1",
                 "status": "complete", "created_at_utc": "2026-10-22T11:59:00Z",
                 "finished_at_utc": "2026-10-22T12:02:00Z",
                 "execution_state": {"mode": "direct-call", "system_required": False},
                 "runtime": runtime, "protocol": protocol,
                 "protocol_sha256": diagnostic.SPEC_SHA256,
                 "preflight": preflight, "source_before": self.source,
                 "source_after": self.source,
                 "baseline": {"raw_sha256": protocol["pilot"]["baseline_raw_sha256"],
                              "artifact_sha256": protocol["pilot"]["baseline_artifact_sha256"],
                              "quality_target_met": True},
                 "samples": samples, "training_calls": 2, "errors": []}
        return index

    def _write(self, directory, index):
        unsigned = {key: value for key, value in index.items() if key != "index_sha256"}
        index["index_sha256"] = proof._digest(unsigned)
        raw = json.dumps(index, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
        (directory / "index.json").write_bytes(raw)
        verifier.RAW_INDEX_SHA256 = hashlib.sha256(raw).hexdigest()
        verifier.INDEX_SHA256 = index["index_sha256"]
        verifier.EXPECTED_SOURCE_REVISION = self.source["revision"]
        return raw

    def _snapshot_patch(self, *, drift=False):
        if not drift:
            return patch.object(diagnostic, "_snapshot", return_value=self.current)
        later = {"revision": "c" * 40, "status": "",
                 "source_lf_sha256": dict(self.current["source_lf_sha256"])}
        return patch.object(diagnostic, "_snapshot", side_effect=[self.current, later])

    def test_valid_record_authenticates_with_later_clean_checkout_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            index = self._build_index(directory)
            self._write(directory, index)
            with self._snapshot_patch(), patch.object(
                    diagnostic.adapter, "solve_reweighted") as solve:
                result = verifier.verify(directory)
            self.assertEqual(result["status"], "saved-baseline-diagnostic-authenticated")
            self.assertEqual(result["samples"], 2)
            self.assertEqual(result["recorded_training_calls"], 2)
            solve.assert_not_called()

    def test_resigned_wrong_sample_call_count_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            index = self._build_index(directory)
            index["samples"][0]["training_calls"] = 2
            self._write(directory, index)
            with self._snapshot_patch(), self.assertRaisesRegex(ValueError, "call count"):
                verifier.verify(directory)

    def test_resigned_closed_parent_reference_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            index = self._build_index(directory)
            # Event 3 points back into the prior root after event 2 closed that root.
            index["samples"][0]["events"][2]["parent_event_id"] = 1
            self._write(directory, index)
            with self._snapshot_patch(), self.assertRaisesRegex(ValueError, "active ancestor"):
                verifier.verify(directory)

    def test_gzip_byte_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            index = self._build_index(directory)
            self._write(directory, index)
            path = directory / "phase-profile.json.gz"
            content = bytearray(path.read_bytes())
            content[-1] ^= 1
            path.write_bytes(content)
            with self._snapshot_patch(), self.assertRaisesRegex(ValueError, "Compressed evidence"):
                verifier.verify(directory)

    def test_index_tampering_rejected_before_snapshot_or_other_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self._write(directory, self._build_index(directory))
            path = directory / "index.json"
            path.write_bytes(path.read_bytes() + b" ")
            with patch.object(diagnostic, "_snapshot") as snapshot, \
                 self.assertRaisesRegex(ValueError, "Index raw bytes"):
                verifier.verify(directory)
            snapshot.assert_not_called()

    def test_source_revision_or_map_drift_during_verification_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self._write(directory, self._build_index(directory))
            with self._snapshot_patch(drift=True), self.assertRaisesRegex(ValueError, "source HEAD"):
                verifier.verify(directory)

    def test_reversed_index_and_sample_intervals_rejected(self):
        for kind in ("index", "sample"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                index = self._build_index(directory)
                if kind == "index":
                    index["finished_at_utc"] = "2026-10-22T11:58:00Z"
                    message = "run UTC interval is reversed"
                else:
                    index["samples"][0]["measurement"]["started_at_utc"] = \
                        "2026-10-22T12:00:21Z"
                    message = "Sample interval is reversed"
                self._write(directory, index)
                with self._snapshot_patch(), self.assertRaisesRegex(ValueError, message):
                    verifier.verify(directory)

    def test_event_outside_parent_or_sample_is_rejected(self):
        for kind in ("parent", "sample"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                index = self._build_index(directory)
                events = index["samples"][0]["events"]
                if kind == "parent":
                    events[1]["parent_event_id"] = 1
                    message = "escapes parent interval"
                else:
                    events[0]["started_at_utc"] = "2026-10-22T11:59:59Z"
                    message = "outside its sample"
                self._write(directory, index)
                with self._snapshot_patch(), self.assertRaisesRegex(ValueError, message):
                    verifier.verify(directory)

    def test_overlapping_sample_and_root_intervals_are_rejected(self):
        for kind in ("samples", "roots"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                index = self._build_index(directory)
                if kind == "samples":
                    second = index["samples"][1]["measurement"]
                    second["started_at_utc"] = "2026-10-22T12:00:10Z"
                    second["finished_at_utc"] = "2026-10-22T12:00:11Z"
                    message = "Samples are not sequential"
                else:
                    index["samples"][0]["events"][1]["started_at_utc"] = \
                        "2026-10-22T12:00:00.1+00:00"
                    message = "overlap or reverse order"
                self._write(directory, index)
                with self._snapshot_patch(), self.assertRaisesRegex(ValueError, message):
                    verifier.verify(directory)

    def test_index_mutation_after_report_read_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self._write(directory, self._build_index(directory))
            original = verifier._read_gzip
            changed = {"done": False}
            def mutate_after_first_read(root, row):
                result = original(root, row)
                if not changed["done"]:
                    path = directory / "index.json"
                    path.write_bytes(path.read_bytes() + b" ")
                    changed["done"] = True
                return result
            with self._snapshot_patch(), patch.object(
                    verifier, "_read_gzip", side_effect=mutate_after_first_read), \
                 self.assertRaisesRegex(ValueError, "Index raw bytes"):
                verifier.verify(directory)


if __name__ == "__main__":
    unittest.main()
