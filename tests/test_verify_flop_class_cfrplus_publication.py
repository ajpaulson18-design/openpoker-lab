"""Fast immutability and quality-miss tests for the published class CFR+ pilot."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import flop_public_classes as proof
from scripts import verify_flop_class_cfrplus_publication as publication


def _summary(**updates):
    result = {
        "status": "saved-trained-policy-physically-verified",
        "training_calls": 0,
        "iterations": 140,
        "class_rows": 466,
        "physical_rows": 16_912,
        "nash_conv": 0.012537880082162792,
        "quality_target_met": False,
        "artifact_sha256": publication.ARTIFACT_SHA256,
    }
    result.update(updates)
    return result


class VerifyFlopClassCFRPlusPublicationTests(unittest.TestCase):
    def test_pinned_pilot_replay_preserves_quality_miss(self):
        with patch.object(publication.replay, "verify_saved", return_value=_summary()) as replay:
            checked = publication.verify_saved()
        replay.assert_called_once_with(publication.PUBLICATION)
        self.assertEqual(checked["publication_raw_sha256"], publication.RAW_SHA256)
        self.assertEqual(checked["publication_artifact_sha256"], publication.ARTIFACT_SHA256)
        self.assertEqual(checked["iterations"], 140)
        self.assertEqual(checked["class_rows"], 466)
        self.assertEqual(checked["physical_rows"], 16_912)
        self.assertFalse(checked["quality_target_met"])
        self.assertEqual(checked["nash_conv"], 0.012537880082162792)

    def test_raw_pin_mutation_rejects_before_generic_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pilot.json"
            shutil.copyfile(publication.PUBLICATION, path)
            raw = bytearray(path.read_bytes())
            raw[-2] = ord(" ") if raw[-2] != ord(" ") else ord("\n")
            path.write_bytes(raw)
            with patch.object(publication.replay, "verify_saved",
                              side_effect=AssertionError("generic replay")) as replay:
                with self.assertRaisesRegex(ValueError, "bytes changed"):
                    publication.verify_saved(path)
            replay.assert_not_called()

    def test_re_signed_content_cannot_change_canonical_artifact_pin(self):
        report = json.loads(publication.PUBLICATION.read_bytes())
        report["quality_target_met"] = True
        unsigned = {key: value for key, value in report.items() if key != "artifact_sha256"}
        report["artifact_sha256"] = proof._digest(unsigned)
        raw = json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        with patch.object(publication, "RAW_SHA256", hashlib.sha256(raw).hexdigest()):
            with self.assertRaisesRegex(ValueError, "artifact checksum"):
                publication._validate_bytes(raw)

    def test_generic_replay_cannot_turn_the_quality_miss_into_a_pass(self):
        with patch.object(publication.replay, "verify_saved",
                           return_value=_summary(quality_target_met=True)):
            with self.assertRaisesRegex(ValueError, "Generic replay differs"):
                publication.verify_saved()

    def test_generic_replay_must_preserve_the_exact_measured_gap(self):
        with patch.object(publication.replay, "verify_saved",
                           return_value=_summary(nash_conv=0.004)):
            with self.assertRaisesRegex(ValueError, "Generic replay differs"):
                publication.verify_saved()

    def test_report_change_during_replay_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pilot.json"
            shutil.copyfile(publication.PUBLICATION, path)

            def mutate_after_read(target):
                Path(target).write_bytes(Path(target).read_bytes() + b" ")
                return _summary()

            with patch.object(publication.replay, "verify_saved", side_effect=mutate_after_read):
                with self.assertRaisesRegex(ValueError, "bytes changed"):
                    publication.verify_saved(path)

    def test_duplicate_json_fields_are_rejected(self):
        raw = b'{"schema_version":"one","schema_version":"two"}'
        with patch.object(publication, "RAW_SHA256", hashlib.sha256(raw).hexdigest()):
            with self.assertRaisesRegex(ValueError, "Duplicate report JSON"):
                publication._validate_bytes(raw)


if __name__ == "__main__":
    unittest.main()
