"""External proof pins and fail-closed authentication before physical work."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_flop_public_classes_publication as publication


class FlopPublicClassesPublicationTests(unittest.TestCase):
    def test_published_record_authenticates_all_sources_and_policy_rows(self):
        record = publication.authenticate()
        self.assertEqual(len(record["source_lf_sha256"]), 6)
        self.assertEqual(len(record["controls"]), 4)
        for control in record["controls"].values():
            self.assertEqual(len(control["class_policy"]), 466)
            self.assertEqual(control["physical_rows_lifted"], 16912)
            self.assertEqual(len(control["exact_metrics"]), 8)
            self.assertLessEqual(control["maximum_numeric_gap"], 1e-10)

    def test_changed_proof_record_rejects_before_physical_preparation(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_bytes(publication.RESULT.read_bytes().replace(b'"training_calls": 0',
                                                                    b'"training_calls": 1'))
            with patch.object(publication, "RESULT", bad), patch.object(
                    publication.audit, "build_model", side_effect=AssertionError("must reject first")):
                with self.assertRaisesRegex(ValueError, "raw hash"):
                    publication.verify()

    def test_changed_interruption_receipt_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text('{}', encoding="utf-8")
            with patch.object(publication, "INTERRUPTION", bad):
                with self.assertRaisesRegex(ValueError, "raw hash"):
                    publication.authenticate()

    def test_current_source_drift_rejects(self):
        sources = publication.audit._source_hashes()
        sources["scripts/flop_public_classes.py"] = "0" * 64
        with patch.object(publication.audit, "_source_hashes", return_value=sources):
            with self.assertRaisesRegex(ValueError, "sources"):
                publication.authenticate()


if __name__ == "__main__":
    unittest.main()
