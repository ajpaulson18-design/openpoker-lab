"""Fixed whole-native study schedule and isolated first-error retention."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import benchmark_native_exact_four_street as study
from pokerlab import native_exact_four_street as native

class NativeExactStudyProtocolTests(unittest.TestCase):
    def test_fixed_schedule_retains_pairs_traces_quality_and_original_rejections(self):
        self.assertEqual(len(study.SCHEDULE), 18)
        self.assertEqual(study.SCHEDULE[:4], (
            ("original-22-t10", "python", 0, False), ("original-22-t10", "native", 0, False),
            ("original-22-t10", "native", 1, False), ("original-22-t10", "python", 1, False)))
        self.assertEqual(sum(row[3] for row in study.SCHEDULE), 2)
        self.assertEqual(study.SCHEDULE[-2:], (
            ("original-22-qreject", "python", 0, False), ("original-22-qreject", "native", 0, False)))
        self.assertEqual(sum(row[0] == "payoff-varied-t100" for row in study.SCHEDULE), 2)

    def test_first_child_failure_streams_retained_once_without_global_process_mock(self):
        source = {"commit": "fixture", "status": "", "sha256": {}}
        failed = SimpleNamespace(returncode=1, stdout=b"partial study child", stderr=b"first failure")
        with TemporaryDirectory() as directory, patch.object(study, "_identity", return_value=source), \
                patch.object(native, "executable_identity", return_value={"scope": "fixture"}), \
                patch.object(study, "_run_child", return_value=failed) as calls:
            output = Path(directory) / "study"
            result = study.run(output, Path(directory) / "fixture.exe")
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(calls.call_count, 1)
            self.assertEqual((output / "original-22-t10-python-0.json").read_bytes(), b"partial study child")
            self.assertEqual((output / "original-22-t10-python-0.stderr.txt").read_bytes(), b"first failure")
            self.assertTrue((output / "original-22-t10-python-0-failure.json").is_file())
            self.assertTrue((output / "manifest.json").is_file())

if __name__ == "__main__":
    unittest.main()
