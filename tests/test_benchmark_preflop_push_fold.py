"""Recovery evidence must reject edited outputs and changed source snapshots."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import benchmark_preflop_push_fold as benchmark


class PushFoldEvidenceTests(unittest.TestCase):
    def test_completed_checkpoint_roundtrip_and_edited_count_rejection(self):
        source = {"solver.py": "frozen"}
        data = {"schema_version": 1, "benchmark_id": benchmark.PREFIX,
                "provenance": {"source_sha256": source}, "counts": {"wins": 12}}
        with TemporaryDirectory() as directory, patch.object(benchmark, "hashes", return_value=source):
            path = Path(directory) / "pair.json"
            benchmark.write(path, data, source)
            self.assertEqual(benchmark.read(path, source)["counts"], {"wins": 12})
            edited = json.loads(path.read_text(encoding="utf-8"))
            edited["counts"]["wins"] = 13
            path.write_text(json.dumps(edited), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Edited or incomplete"):
                benchmark.read(path, source)

    def test_changed_source_refuses_output_and_stale_recovery(self):
        source = {"solver.py": "old"}
        changed = {"solver.py": "new"}
        data = {"schema_version": 1, "benchmark_id": benchmark.PREFIX,
                "provenance": {"source_sha256": source}}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pair.json"
            with patch.object(benchmark, "hashes", return_value=changed):
                with self.assertRaisesRegex(RuntimeError, "Source changed"):
                    benchmark.write(path, data, source)
            self.assertFalse(path.exists())
            with patch.object(benchmark, "hashes", return_value=source):
                benchmark.write(path, data, source)
            with self.assertRaisesRegex(ValueError, "Stale measurement source"):
                benchmark.read(path, changed)


if __name__ == "__main__":
    unittest.main()
