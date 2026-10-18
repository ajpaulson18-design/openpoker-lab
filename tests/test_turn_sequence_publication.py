"""Publication-boundary tests for the cached turn-sequence certificate."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import turn_sequence_equilibrium as generator
from scripts import verify_turn_sequence as verifier

ROOT = Path(__file__).resolve().parents[1]
CACHED = ROOT / "benchmarks" / "results" / "turn-sequence-equilibrium-v1.json"


class TurnSequencePublicationTests(unittest.TestCase):
    def setUp(self):
        self.cached_report = json.loads(CACHED.read_text(encoding="utf-8"))
        self.cached_candidate = self.cached_report["results"][0]
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "published.json"
        self.output.write_bytes(b"previously-accepted-bytes\n")

    def _orchestration_mocks(self, report=None):
        snapshot = ("a" * 40, {"pinned": "b" * 64})
        stack = mock.patch.multiple(
            generator,
            OUTPUT=self.output,
            _snapshot=mock.Mock(return_value=snapshot),
            _build_model=mock.Mock(return_value=object()),
            _profile_candidate=mock.Mock(return_value=self.cached_candidate),
            _report=mock.Mock(return_value=report or self.cached_report),
        )
        return stack

    def test_bounded_limit_before_search_preserves_previous_output(self):
        before = self.output.read_bytes()
        with self._orchestration_mocks() as patches:
            generator._build_model.side_effect = generator._BoundedLimit("cap")
            with self.assertRaises(generator._BoundedLimit):
                generator.generate()
            generator._profile_candidate.assert_not_called()
        self.assertEqual(self.output.read_bytes(), before)

    def test_head_or_source_drift_before_staging_stops_publication(self):
        before = self.output.read_bytes()
        with self._orchestration_mocks():
            with mock.patch.object(generator, "_assert_unchanged", side_effect=ValueError("source/HEAD drift")):
                with mock.patch("scripts.verify_turn_sequence.verify_saved_artifact") as verify:
                    with self.assertRaisesRegex(ValueError, "drift"):
                        generator.generate()
                    verify.assert_not_called()
        self.assertEqual(self.output.read_bytes(), before)

    def test_head_or_source_drift_after_staging_stops_publication(self):
        before = self.output.read_bytes()
        with self._orchestration_mocks():
            with mock.patch.object(generator, "_assert_unchanged", side_effect=[None, ValueError("source/HEAD drift")]):
                with mock.patch("scripts.verify_turn_sequence.verify_saved_artifact") as verify:
                    with self.assertRaisesRegex(ValueError, "drift"):
                        generator.generate()
                    verify.assert_called_once()
        self.assertEqual(self.output.read_bytes(), before)
        self.assertEqual(list(Path(self.temp.name).glob(".*.tmp")), [])

    def test_independent_rejection_after_replace_restores_accepted_bytes(self):
        before = self.output.read_bytes()
        with self._orchestration_mocks():
            with mock.patch.object(generator, "_assert_unchanged"):
                with mock.patch("scripts.verify_turn_sequence.verify_saved_artifact", side_effect=[None, ValueError("independent reject")]):
                    with self.assertRaisesRegex(ValueError, "independent reject"):
                        generator.generate()
        self.assertEqual(self.output.read_bytes(), before)
        self.assertEqual(list(Path(self.temp.name).glob(".*.tmp")), [])

    def test_oversized_input_is_rejected_before_json_parsing(self):
        path = Path(self.temp.name) / "oversized.json"
        path.write_bytes(b"{" + b" " * 2_000_000)
        with mock.patch.object(verifier.json, "loads", side_effect=AssertionError("JSON parsing must not run")) as loads:
            with self.assertRaisesRegex(ValueError, "exceeds 2MB admission"):
                verifier.load(path)
            loads.assert_not_called()


if __name__ == "__main__":
    unittest.main()
