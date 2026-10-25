"""Saved-artifact authentication tests; these tests never invoke training."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify_four_street_integration_publication as verifier


class StrictArtifactTests(unittest.TestCase):
    def test_strict_json_rejects_duplicate_keys_and_nonfinite_constants(self):
        with self.assertRaises(ValueError):
            verifier._strict_json(b'{"x":1,"x":2}', max_bytes=1024)
        with self.assertRaises(ValueError):
            verifier._strict_json(b'{"x":NaN}', max_bytes=1024)
        with self.assertRaises(ValueError):
            verifier._strict_json(b'{"x":Infinity}', max_bytes=1024)

    def test_strict_json_enforces_artifact_byte_limit(self):
        with self.assertRaises(ValueError):
            verifier._strict_json(b'{"payload":"1234"}', max_bytes=4)

    def test_publication_requires_a_trusted_report_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises((TypeError, ValueError)):
                verifier.verify_publication(temp, None)

    def test_missing_report_fails_before_math_helpers_are_loaded(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(verifier, "_load_math",
                              side_effect=AssertionError("math imported before artifact auth")):
                with self.assertRaises((OSError, ValueError, RuntimeError)):
                    verifier.verify_publication(temp, hashlib.sha256(b"{}").hexdigest())

    def test_report_digest_mismatch_fails_before_math_helpers_are_loaded(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "report.json"
            report.write_bytes(b'{"schema":"four-street-attempt-report-v1"}\n')
            with patch.object(verifier, "_load_math",
                              side_effect=AssertionError("math imported before report pin")):
                with self.assertRaises((ValueError, RuntimeError)):
                    verifier.verify_publication(temp, hashlib.sha256(b"different bytes").hexdigest())

    def test_report_with_duplicate_keys_is_rejected_after_exact_byte_pin(self):
        with tempfile.TemporaryDirectory() as temp:
            raw = b'{"schema":"four-street-attempt-report-v1","outcome":"completed-met","outcome":"completed-missed"}\n'
            (Path(temp) / "report.json").write_bytes(raw)
            with patch.object(verifier, "_load_math",
                              side_effect=AssertionError("math loaded for malformed report")):
                with self.assertRaises(ValueError):
                    verifier.verify_publication(temp, hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
