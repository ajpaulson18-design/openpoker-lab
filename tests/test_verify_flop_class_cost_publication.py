import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_flop_class_cost_publication as publication


REVISION = publication.EXPECTED_REVISION


def _make_evidence(directory):
    source = {"revision": REVISION, "status": "", "source_lf_sha256": {}}
    report = {"protocol_id": "fixed-flop-class-call-cost-v1", "status": "complete",
              "source_before": source, "source_after": source,
              "samples": [{"kind": "synthetic", "status": "complete"} for _ in range(8)]}
    unsigned = {key: value for key, value in report.items() if key != "index_sha256"}
    report["index_sha256"] = hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).hexdigest()
    raw = json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    (Path(directory) / "index.json").write_bytes(raw)
    return raw, report


def _pin(raw, report):
    publication.INDEX_RAW_SHA256 = hashlib.sha256(raw).hexdigest()
    publication.INDEX_SHA256 = report["index_sha256"]


class FlopClassCostPublicationTests(unittest.TestCase):
    def setUp(self):
        old_raw, old_canonical = publication.INDEX_RAW_SHA256, publication.INDEX_SHA256
        self.addCleanup(setattr, publication, "INDEX_RAW_SHA256", old_raw)
        self.addCleanup(setattr, publication, "INDEX_SHA256", old_canonical)

    def test_valid_pinned_index_calls_saved_verifier_and_returns_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, report = _make_evidence(tmp)
            _pin(raw, report)
            with patch.object(publication.runner, "verify_saved", return_value={
                    "status": "saved-measurement-verified"}) as verify_saved:
                result = publication.verify(tmp)
            verify_saved.assert_called_once_with(Path(tmp))
            self.assertEqual(result["status"], "published-measurement-verified")
            self.assertEqual(result["call_count"], 8)
            self.assertEqual(result["index_raw_sha256"], hashlib.sha256(raw).hexdigest())

    def test_wrong_resigned_raw_index_rejects_before_saved_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, report = _make_evidence(tmp)
            _pin(raw, report)
            report["source_before"]["revision"] = "c" * 40
            unsigned = {key: value for key, value in report.items() if key != "index_sha256"}
            report["index_sha256"] = hashlib.sha256(json.dumps(
                unsigned, sort_keys=True, separators=(",", ":"),
                allow_nan=False).encode("utf-8")).hexdigest()
            changed = json.dumps(report, sort_keys=True, indent=2,
                                 allow_nan=False).encode("utf-8") + b"\n"
            (Path(tmp) / "index.json").write_bytes(changed)
            with patch.object(publication.runner, "verify_saved") as verify_saved:
                with self.assertRaisesRegex(ValueError, "index bytes"):
                    publication.verify(tmp)
            verify_saved.assert_not_called()

    def test_index_change_during_saved_verification_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, report = _make_evidence(tmp)
            _pin(raw, report)

            def mutate(_directory):
                changed = raw + b" "
                (Path(tmp) / "index.json").write_bytes(changed)
                return {"status": "saved-measurement-verified"}

            with patch.object(publication.runner, "verify_saved", side_effect=mutate):
                with self.assertRaisesRegex(ValueError, "index bytes"):
                    publication.verify(tmp)


if __name__ == "__main__":
    unittest.main()
