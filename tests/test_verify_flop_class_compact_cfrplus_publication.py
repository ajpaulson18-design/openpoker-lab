"""Fast immutable-publication guard tests; generic replay is always mocked."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import flop_public_classes as proof
from scripts import verify_flop_class_compact_cfrplus_publication as publication


class CompactPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = publication.PUBLICATION.read_bytes()
        cls.report = json.loads(cls.raw)

    def _write(self, raw, directory):
        path = Path(directory) / "pilot.json"
        path.write_bytes(raw)
        return path

    def _resigned_mutation(self, mutate):
        changed = json.loads(json.dumps(self.report))
        mutate(changed)
        unsigned = {key: value for key, value in changed.items() if key != "artifact_sha256"}
        changed["artifact_sha256"] = proof._digest(unsigned)
        return json.dumps(changed, sort_keys=True, separators=(",", ":")).encode()

    def test_authenticates_actual_raw_report_without_replay(self):
        path, raw, report = publication._read(publication.PUBLICATION)
        self.assertEqual(raw, self.raw)
        self.assertEqual(report["artifact_sha256"], publication.ARTIFACT_SHA256)
        self.assertEqual(report["baseline_pilot"]["quality_target_met"], False)
        self.assertEqual(path, publication.PUBLICATION)

    def test_tampered_bytes_and_re_signed_metadata_mutations_reject(self):
        mutations = [
            self.raw + b" ",
            self._resigned_mutation(lambda report: report.__setitem__("quality_target_met", False)),
            self._resigned_mutation(lambda report: report["baseline_pilot"].__setitem__("quality_target_met", True)),
        ]
        for raw in mutations:
            with self.subTest(size=len(raw)), tempfile.TemporaryDirectory() as directory:
                path = self._write(raw, directory)
                with self.assertRaisesRegex(ValueError, "bytes changed"):
                    publication._read(path)

    def test_saved_replay_runs_only_after_raw_auth_and_returns_pinned_miss(self):
        expected = {
            "status": "saved-compact-policy-physically-verified", "training_calls": 0,
            "iterations": 560, "class_rows": 466, "physical_rows": 16912,
            "quality_target_met": True, "nash_conv": 0.0028924005277596834,
            "artifact_sha256": publication.ARTIFACT_SHA256,
        }
        with patch.object(publication.replay, "verify_saved", return_value=expected) as replay:
            result = publication.verify_saved(publication.PUBLICATION)
        replay.assert_called_once_with(publication.PUBLICATION)
        self.assertEqual(result["publication_raw_sha256"], publication.RAW_SHA256)
        self.assertEqual(result["publication_artifact_sha256"], publication.ARTIFACT_SHA256)
        # The newer pass does not overwrite the older fixed-pilot miss.
        self.assertFalse(self.report["baseline_pilot"]["quality_target_met"])

    def test_changed_during_replay_rejected_after_second_raw_authentication(self):
        expected = {
            "status": "saved-compact-policy-physically-verified", "training_calls": 0,
            "iterations": 560, "class_rows": 466, "physical_rows": 16912,
            "quality_target_met": True, "nash_conv": 0.0028924005277596834,
            "artifact_sha256": publication.ARTIFACT_SHA256,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(self.raw, directory)

            def mutate_during_replay(_path):
                path.write_bytes(self.raw + b" changed")
                return expected

            with patch.object(publication.replay, "verify_saved", side_effect=mutate_during_replay) as replay:
                with self.assertRaisesRegex(ValueError, "bytes changed"):
                    publication.verify_saved(path)
            replay.assert_called_once_with(path)


if __name__ == "__main__":
    unittest.main()
