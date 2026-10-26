"""Authentication precedes mathematics in the saved native-policy certificate."""
import hashlib
import json
import unittest
from unittest.mock import patch

from scripts import verify_native_four_street_sample as verifier


class SavedNativeAuthenticationTests(unittest.TestCase):
    def test_external_pin_shape_rejects_before_evidence_access(self):
        with patch.object(verifier, "_read") as read:
            with self.assertRaises(ValueError):
                verifier.verify(verifier.ROOT, "untrusted", "unused")
        read.assert_not_called()

    def test_wrong_external_pin_rejects_before_report_interpretation(self):
        with patch.object(verifier, "_read", return_value=b"invalid JSON"):
            with self.assertRaisesRegex(ValueError, "external pin"):
                verifier.verify(verifier.ROOT, "0" * 64, "unused")

    def test_dirty_source_rejects_before_source_reads_or_mathematics(self):
        report = {"benchmark_id": "native-four-street-v1", "outcome": "complete",
                  "failures": [], "policy_compatibility": "pass",
                  "source_before": {"status_porcelain": [" M source"]},
                  "source_after": {"status_porcelain": [" M source"]}}
        data = json.dumps(report).encode()
        with patch.object(verifier, "_read", return_value=data) as read:
            with self.assertRaisesRegex(ValueError, "clean and stable"):
                verifier.verify(verifier.ROOT, hashlib.sha256(data).hexdigest(), "unused")
        self.assertEqual(read.call_count, 1)


if __name__ == "__main__":
    unittest.main()
