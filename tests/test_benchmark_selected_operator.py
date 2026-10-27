import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.benchmark_selected_operator import verify_saved, _retain_or_compare


class SelectedOperatorEvidenceTests(unittest.TestCase):
    def test_changed_manifest_rejects_before_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "manifest.json").write_text("{}")
            with patch("scripts.benchmark_selected_operator.evaluate_exact", side_effect=AssertionError("mathematics")):
                with self.assertRaisesRegex(ValueError, "externally supplied hash"):
                    verify_saved(root, "0" * 64)

    def test_changed_policy_rejects_before_source_or_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = b'{"strategy":[]}'
            (root / "operator-0.json").write_bytes(raw + b" ")
            manifest = json.dumps({"sha256": {"operator-0.json": hashlib.sha256(raw).hexdigest()}}).encode()
            (root / "manifest.json").write_bytes(manifest)
            with patch("scripts.benchmark_selected_operator._identity", side_effect=AssertionError("source")):
                with self.assertRaisesRegex(ValueError, "artifact changed"):
                    verify_saved(root, hashlib.sha256(manifest).hexdigest())

    def test_existing_audit_is_compared_and_never_rewritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "audit.json"
            _retain_or_compare(path, {"nash_conv": "1/2"})
            original = path.read_bytes()
            _retain_or_compare(path, {"nash_conv": "1/2"})
            with self.assertRaisesRegex(ValueError, "audit changed"):
                _retain_or_compare(path, {"nash_conv": "0"})
            self.assertEqual(original, path.read_bytes())
